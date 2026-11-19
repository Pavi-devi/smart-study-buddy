"""AI calls: turn a lecture transcript into notes, flashcards and a quiz.

Two providers are supported:
  - Gemini (Google AI Studio): has a FREE tier, no credit card needed (default if a key is set)
  - Claude (Anthropic API): paid
"""
import json
import os

import anthropic

CLAUDE_MODEL = "claude-sonnet-5-5"
# Gemini models tried in order; the first one is verified, the others are fallbacks.
# Override with the GEMINI_MODEL environment variable if Google renames models.
GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
MAX_WORDS = 20000  # about 2 hours of speech; longer transcripts are rejected

SYSTEM_PROMPT = """You are a study assistant. You turn a lecture transcript into study material.
Rules:
- Use ONLY information found in the transcript. Never add outside facts.
- Write in simple, clear language a student can revise from.
- Reply with ONE valid JSON object and nothing else (no markdown, no commentary).
"""

USER_PROMPT = """Create study material from the lecture transcript below.

Return JSON in exactly this shape:
{{
  "chapters": [
    {{"title": "short chapter title", "key_points": ["point", "point"], "summary": "2-3 sentence summary"}}
  ],
  "flashcards": [
    {{"chapter": 1, "question": "...", "answer": "..."}}
  ],
  "quiz": [
    {{"chapter": 1, "question": "...", "options": ["A", "B", "C", "D"],
      "correct_index": 0, "explanation": "why this answer is correct"}}
  ]
}}

Requirements:
- 4 to 8 chapters in the order the topics appear; 3 to 6 key points each.
- 10 to 20 flashcards spread across chapters.
- 6 to 10 multiple-choice questions with exactly 4 options, one correct.
- "chapter" is the 1-based number of the chapter the item belongs to.
- "correct_index" is the 0-based index of the correct option; vary its position.

Lecture title: {title}

TRANSCRIPT:
{transcript}
"""


class AIError(Exception):
    """Raised with a student-friendly message when generation fails."""


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in the reply.")
    return json.loads(text[start : end + 1])


def validate(data: dict) -> dict:
    """Check the AI output has the expected shape and fix small problems."""
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("No chapters returned.")
    clean_chapters = []
    for ch in chapters:
        if not all(k in ch for k in ("title", "key_points", "summary")):
            raise ValueError("A chapter is missing fields.")
        if not isinstance(ch["key_points"], list):
            raise ValueError("key_points must be a list.")
        clean_chapters.append(
            {
                "title": str(ch["title"]),
                "key_points": [str(p) for p in ch["key_points"]],
                "summary": str(ch["summary"]),
            }
        )
    n = len(clean_chapters)

    def chapter_no(item) -> int:
        try:
            c = int(item.get("chapter", 1))
        except (TypeError, ValueError):
            c = 1
        return min(max(c, 1), n)

    cards = []
    for c in data.get("flashcards", []):
        if "question" in c and "answer" in c:
            cards.append(
                {"chapter": chapter_no(c), "question": str(c["question"]), "answer": str(c["answer"])}
            )
    quiz = []
    for q in data.get("quiz", []):
        opts = q.get("options")
        idx = q.get("correct_index")
        if (
            "question" in q
            and isinstance(opts, list)
            and len(opts) == 4
            and isinstance(idx, int)
            and 0 <= idx < 4
        ):
            quiz.append(
                {
                    "chapter": chapter_no(q),
                    "question": str(q["question"]),
                    "options": [str(o) for o in opts],
                    "correct_index": idx,
                    "explanation": str(q.get("explanation", "")),
                }
            )
    if not cards or not quiz:
        raise ValueError("Flashcards or quiz were missing.")
    return {"chapters": clean_chapters, "flashcards": cards, "quiz": quiz}


def _call_claude(prompt: str, api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise AIError("The Claude API key was rejected. Check ANTHROPIC_API_KEY.")
    except anthropic.RateLimitError:
        raise AIError("Rate limit reached. Wait a minute and try again.")
    except anthropic.APIConnectionError:
        raise AIError("Could not reach the Claude API. Check your internet connection.")
    except anthropic.APIStatusError as e:
        raise AIError(f"The Claude API returned an error ({e.status_code}). {e.message}")
    return "".join(b.text for b in response.content if b.type == "text")


def _call_gemini(prompt: str, api_key: str) -> str:
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=api_key)
    override = os.environ.get("GEMINI_MODEL")
    models = [override] if override else GEMINI_MODELS
    last = None
    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    max_output_tokens=8000,
                ),
            )
            if not response.text:
                raise ValueError("Gemini returned an empty reply.")
            return response.text
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code in (400, 401, 403) and "API key" in str(e):
                raise AIError("The Gemini API key was rejected. Check GEMINI_API_KEY.")
            if code == 429:
                raise AIError(
                    "Free-tier limit reached. Wait a minute and try again "
                    "(daily limits reset at midnight Pacific time)."
                )
            last = e
            if code in (404, 503):  # model not available: try the next one
                continue
            raise AIError(f"The Gemini API returned an error ({code}). {getattr(e, 'message', e)}")
        except (OSError, ConnectionError):
            raise AIError("Could not reach the Gemini API. Check your internet connection.")
    raise AIError(f"No Gemini model was available ({last}). Set GEMINI_MODEL to a model shown in AI Studio.")


def generate_study_material(title: str, transcript: str, provider: str, api_key: str) -> dict:
    """provider is "gemini" (free tier available) or "claude" (paid)."""
    words = len(transcript.split())
    if words < 50:
        raise AIError("The transcript is too short. Please paste the full lecture transcript.")
    if words > MAX_WORDS:
        raise AIError(
            f"The transcript has {words:,} words, above the {MAX_WORDS:,}-word limit. "
            "Please paste a shorter lecture or split it into parts."
        )
    if not api_key:
        raise AIError("No API key found. Set GEMINI_API_KEY (free) or ANTHROPIC_API_KEY (see README).")

    prompt = USER_PROMPT.format(title=title, transcript=transcript)
    call = _call_gemini if provider == "gemini" else _call_claude
    last_error = "Unknown error"
    for _attempt in range(2):  # one retry if the reply is not valid JSON
        text = call(prompt, api_key)
        try:
            return validate(_extract_json(text))
        except (ValueError, json.JSONDecodeError) as e:
            last_error = str(e)
    raise AIError(f"The AI reply could not be read ({last_error}). Please try again.")

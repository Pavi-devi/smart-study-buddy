# Smart Study Buddy

Paste a lecture transcript and get chapter-wise notes, flashcards and a quiz.
Everything is saved to your account, and the app schedules revisions using spaced
repetition so you remember the lecture instead of forgetting it.

Built for the Touchcast India (A Napster Corporation Company) AI Solutions Architect
Internship assessment. Built with Claude as the coding partner. The app runs on the Gemini API (free tier) or the Claude API, plus Streamlit.

## The problem

Students watch long lectures, understand them in the moment, and forget most of it
within days. Most tools stop at a summary and never help the student revise.

## Features

- Sign up and log in (passwords stored as bcrypt hashes)
- Paste a transcript, get chapter-wise notes, flashcards and a quiz from Claude
- Personal library of saved lectures
- Revision plan: Smart (days 1, 3, 7, 14) or Simple (every 2 days for 2 weeks)
- "Due today" dashboard with a Done button
- Quiz score history chart
- Weak-topic detection: chapters answered wrongly come back tomorrow and in 4 days

## How it works

1. The transcript goes to Claude with a prompt that asks for JSON only and tells it to use
   only the transcript (`ai.py`).
2. The reply is validated (shape, 4 options per question, chapter numbers) and retried
   once if it is not valid JSON.
3. Notes, flashcards, quiz questions and revision dates are saved in SQLite under the
   user's ID (`db.py`).
4. The dashboard shows every revision whose date is today or earlier.
5. Wrong quiz answers add extra revisions for that chapter (`scheduler.py`).

## Tech stack

Python 3.10+, Streamlit, Gemini API (free tier, `google-genai`) or Claude API (`anthropic`), SQLite, bcrypt.

## Run it

```bash
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# FREE option: get a Gemini key at https://aistudio.google.com/apikey (no card needed)
# Windows PowerShell:  $env:GEMINI_API_KEY="your-key"
# Mac/Linux:           export GEMINI_API_KEY="your-key"

# PAID option (Claude): https://console.anthropic.com
#   set ANTHROPIC_API_KEY the same way. If both keys are set, Gemini is used.

streamlit run app.py
```

Alternatively, create `.streamlit/secrets.toml` with `GEMINI_API_KEY = "your-key"`.
Never commit your key to GitHub.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit pages: login, dashboard, new lecture, library |
| `ai.py` | Claude prompt, JSON parsing and validation |
| `db.py` | SQLite tables and queries |
| `auth.py` | Sign-up and login |
| `scheduler.py` | Revision dates |
| `sample/` | A sample transcript for testing |

## Next steps

Email reminders, YouTube link input (auto-fetch transcript), PDF export, Tamil/Hindi notes,
"ask your notes" chat.

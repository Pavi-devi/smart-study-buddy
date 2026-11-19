"""Smart Study Buddy: turn lecture transcripts into notes, flashcards, a quiz
and a spaced-repetition revision schedule."""
import os
from datetime import date

import streamlit as st

import ai
import auth
import db
import scheduler

st.set_page_config(page_title="Smart Study Buddy", page_icon="📚", layout="wide")
db.init_db()

PAGES = ["Dashboard", "New Lecture", "Library"]


# ---------------------------------------------------------------- helpers
def get_credentials() -> tuple[str, str]:
    """Return (provider, key). Gemini (free tier) is used first if its key is set."""
    def lookup(name: str) -> str:
        key = os.environ.get(name, "")
        if not key:
            try:
                key = st.secrets.get(name, "")
            except Exception:
                key = ""
        return key

    gemini = lookup("GEMINI_API_KEY") or lookup("GOOGLE_API_KEY")
    if gemini:
        return "gemini", gemini
    return "claude", lookup("ANTHROPIC_API_KEY")


def open_lecture(lecture_id: int) -> None:
    """Callback: jump to the Library page with this lecture open."""
    st.session_state["open_lecture"] = lecture_id
    st.session_state["goto"] = "Library"


def close_lecture() -> None:
    st.session_state["open_lecture"] = None


def log_out() -> None:
    st.session_state["user"] = None
    st.session_state["open_lecture"] = None


# ---------------------------------------------------------------- login
def login_screen() -> None:
    st.title("📚 Smart Study Buddy")
    st.caption("Paste a lecture transcript. Get notes, flashcards, a quiz and a revision plan.")
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in"):
                user = auth.log_in(email, password)
                if user:
                    st.session_state["user"] = {"id": user["id"], "email": user["email"]}
                    st.rerun()
                else:
                    st.error("Wrong email or password.")

    with tab_signup:
        with st.form("signup_form"):
            email = st.text_input("Email", key="su_email")
            password = st.text_input("Password (min 6 characters)", type="password", key="su_pw")
            if st.form_submit_button("Create account"):
                ok, msg = auth.sign_up(email, password)
                (st.success if ok else st.error)(msg)


# ---------------------------------------------------------------- lecture view
def render_notes(chapters) -> None:
    for ch in chapters:
        with st.expander(f"Chapter {ch['position']}: {ch['title']}", expanded=ch["position"] == 1):
            for point in ch["key_points"]:
                st.markdown(f"- {point}")
            st.info(ch["summary"])


def render_flashcards(cards) -> None:
    st.caption("Read the question, say the answer in your head, then open the card.")
    for i, card in enumerate(cards, start=1):
        with st.expander(f"Card {i}: {card['question']}"):
            st.success(card["answer"])
            st.caption(f"From: {card['chapter_title']}")


def render_quiz(user_id: int, lecture_id: int, questions) -> None:
    st.caption("Answer all questions, then press Submit. Wrong answers schedule extra revision.")
    with st.form(f"quiz_form_{lecture_id}"):
        picks = {}
        for i, q in enumerate(questions, start=1):
            picks[q["id"]] = st.radio(
                f"Q{i}. {q['question']}",
                q["options"],
                index=None,
                key=f"q_{lecture_id}_{q['id']}",
            )
        submitted = st.form_submit_button("Submit quiz")

    if not submitted:
        return
    if any(v is None for v in picks.values()):
        st.warning("Please answer every question before submitting.")
        return

    score, weak = 0, {}
    for q in questions:
        chosen = q["options"].index(picks[q["id"]])
        if chosen == q["correct_index"]:
            score += 1
        else:
            weak[q["chapter_id"]] = q["chapter_title"]

    db.save_attempt(user_id, lecture_id, score, len(questions))
    st.subheader(f"Your score: {score} / {len(questions)}")
    for i, q in enumerate(questions, start=1):
        chosen = q["options"].index(picks[q["id"]])
        correct = q["options"][q["correct_index"]]
        if chosen == q["correct_index"]:
            st.success(f"Q{i}: Correct. {q['explanation']}")
        else:
            st.error(f"Q{i}: Wrong. Correct answer: {correct}. {q['explanation']}")

    if weak:
        for chapter_id in weak:
            db.add_weak_revisions(
                user_id, lecture_id, chapter_id, scheduler.weak_topic_dates(date.today())
            )
        st.warning(
            "Weak topics added to your revision list (tomorrow and in 4 days): "
            + ", ".join(weak.values())
        )
    else:
        st.balloons()


def render_lecture(user_id: int, lecture_id: int) -> None:
    lecture = db.get_lecture(user_id, lecture_id)
    if lecture is None:
        st.error("Lecture not found.")
        return
    st.button("← Back to library", on_click=close_lecture)
    st.header(lecture["title"])
    chapters = db.get_chapters(lecture_id)
    tab_notes, tab_cards, tab_quiz = st.tabs(["📝 Notes", "🃏 Flashcards", "❓ Quiz"])
    with tab_notes:
        render_notes(chapters)
    with tab_cards:
        render_flashcards(db.get_flashcards(lecture_id))
    with tab_quiz:
        render_quiz(user_id, lecture_id, db.get_questions(lecture_id))


# ---------------------------------------------------------------- pages
def page_dashboard(user) -> None:
    st.header("Dashboard")
    today = date.today()
    due = db.due_revisions(user["id"], today)

    st.subheader(f"Due today: {len(due)}")
    if not due:
        st.success("Nothing to revise right now. Add a lecture or check back tomorrow.")
    for r in due:
        what = r["chapter_title"] or "Full lecture"
        overdue = r["due_date"] < today.isoformat()
        cols = st.columns([5, 1.2, 1.2])
        cols[0].markdown(
            f"**{r['lecture_title']}**  \n{what} · _{r['note']}_"
            + (f" · ⚠️ due {r['due_date']}" if overdue else "")
        )
        cols[1].button("Open", key=f"open_{r['id']}", on_click=open_lecture, args=(r["lecture_id"],))
        if cols[2].button("Done ✓", key=f"done_{r['id']}"):
            db.mark_revision_done(user["id"], r["id"])
            st.rerun()

    left, right = st.columns(2)
    with left:
        st.subheader("Coming up")
        upcoming = db.upcoming_revisions(user["id"], today)
        if not upcoming:
            st.write("No upcoming revisions.")
        for r in upcoming:
            st.write(f"{r['due_date']} · {r['lecture_title']} · {r['chapter_title'] or 'Full lecture'}")
    with right:
        st.subheader("Quiz score history")
        attempts = db.get_attempts(user["id"])
        if not attempts:
            st.write("Take a quiz to see your progress here.")
        else:
            st.line_chart([round(100 * a["score"] / a["total"]) for a in attempts])
            st.caption("Score (%) across your quiz attempts, oldest to newest.")


def page_new_lecture(user) -> None:
    st.header("New Lecture")
    st.write(
        "On YouTube: open the video, tap **...more**, choose **Show transcript**, "
        "copy the text and paste it below."
    )
    with st.form("new_lecture"):
        title = st.text_input("Lecture title", placeholder="e.g. Newton's Laws of Motion")
        transcript = st.text_area("Transcript", height=300)
        mode = st.radio(
            "Revision plan",
            list(scheduler.MODES.keys()),
            index=list(scheduler.MODES.keys()).index(scheduler.DEFAULT_MODE),
            help="Smart mode spaces reviews further apart as your memory strengthens.",
        )
        go = st.form_submit_button("Generate study material")

    if not go:
        return
    if not title.strip():
        st.error("Please give the lecture a title.")
        return
    try:
        with st.spinner("The AI is reading the lecture... this takes about 20 to 60 seconds."):
            provider, key = get_credentials()
            data = ai.generate_study_material(title.strip(), transcript, provider, key)
    except ai.AIError as e:
        st.error(str(e))
        return

    dates = scheduler.revision_dates(date.today(), mode)
    lecture_id = db.save_lecture(user["id"], title.strip(), transcript, data, dates)
    st.session_state["open_lecture"] = lecture_id
    st.session_state["goto"] = "Library"
    st.session_state["flash"] = (
        f"Saved! Revisions scheduled on: {', '.join(d.strftime('%d %b') for d in dates)}."
    )
    st.rerun()


def page_library(user) -> None:
    lecture_id = st.session_state.get("open_lecture")
    if lecture_id:
        msg = st.session_state.pop("flash", None)
        if msg:
            st.success(msg)
        render_lecture(user["id"], lecture_id)
        return

    st.header("My Library")
    lectures = db.list_lectures(user["id"])
    if not lectures:
        st.info("No lectures yet. Go to **New Lecture** to add your first one.")
        return
    for lec in lectures:
        cols = st.columns([5, 2, 1.2, 1.2])
        cols[0].markdown(f"**{lec['title']}**  \nAdded {lec['created_at'][:10]}")
        cols[1].write(f"Revisions done: {lec['done_rev']} / {lec['total_rev']}")
        cols[2].button("Open", key=f"lib_{lec['id']}", on_click=open_lecture, args=(lec["id"],))
        if cols[3].button("Delete", key=f"del_{lec['id']}"):
            db.delete_lecture(user["id"], lec["id"])
            st.rerun()
        st.divider()


# ---------------------------------------------------------------- main
def main() -> None:
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("open_lecture", None)

    user = st.session_state["user"]
    if user is None:
        login_screen()
        return

    # A page change requested by a button must be applied before the radio is drawn.
    if "goto" in st.session_state:
        st.session_state["page"] = st.session_state.pop("goto")

    with st.sidebar:
        st.title("📚 Study Buddy")
        st.caption(user["email"])
        page = st.radio("Go to", PAGES, key="page")
        st.button("Log out", on_click=log_out)

    provider, key = get_credentials()
    if not key:
        st.sidebar.warning("No API key set. Set GEMINI_API_KEY (free) to generate notes.")
    else:
        st.sidebar.caption(f"AI: {'Gemini (free tier)' if provider == 'gemini' else 'Claude'}")

    if page == "Dashboard":
        page_dashboard(user)
    elif page == "New Lecture":
        page_new_lecture(user)
    else:
        page_library(user)


main()

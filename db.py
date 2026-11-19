"""SQLite storage: users, lectures, chapters, flashcards, quiz, revisions."""
import json
import os
import sqlite3
from datetime import date

DB_PATH = os.environ.get("STUDY_BUDDY_DB", "study_buddy.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS lectures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                key_points TEXT NOT NULL,
                summary TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                explanation TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                taken_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                lecture_id INTEGER NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
                chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                note TEXT DEFAULT ''
            );
            """
        )


# ---------- users ----------
def create_user(email: str, password_hash: str):
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, password_hash),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(email: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


# ---------- lectures ----------
def save_lecture(user_id: int, title: str, transcript: str, data: dict, revision_days: list) -> int:
    """Save a lecture with its chapters, flashcards and quiz, plus its revision dates."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO lectures (user_id, title, transcript) VALUES (?, ?, ?)",
            (user_id, title, transcript),
        )
        lecture_id = cur.lastrowid

        chapter_ids = {}  # 1-based chapter number -> database id
        for i, ch in enumerate(data["chapters"], start=1):
            c = conn.execute(
                "INSERT INTO chapters (lecture_id, position, title, key_points, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (lecture_id, i, ch["title"], json.dumps(ch["key_points"]), ch["summary"]),
            )
            chapter_ids[i] = c.lastrowid

        for card in data["flashcards"]:
            conn.execute(
                "INSERT INTO flashcards (chapter_id, question, answer) VALUES (?, ?, ?)",
                (chapter_ids[card["chapter"]], card["question"], card["answer"]),
            )
        for q in data["quiz"]:
            conn.execute(
                "INSERT INTO quiz_questions "
                "(chapter_id, question, options, correct_index, explanation) VALUES (?, ?, ?, ?, ?)",
                (
                    chapter_ids[q["chapter"]],
                    q["question"],
                    json.dumps(q["options"]),
                    q["correct_index"],
                    q["explanation"],
                ),
            )
        for d in revision_days:
            conn.execute(
                "INSERT INTO revisions (user_id, lecture_id, due_date, note) VALUES (?, ?, ?, ?)",
                (user_id, lecture_id, d.isoformat(), "Full lecture revision"),
            )
        return lecture_id


def list_lectures(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT l.id, l.title, l.created_at,
                   (SELECT COUNT(*) FROM revisions r
                     WHERE r.lecture_id = l.id AND r.chapter_id IS NULL) AS total_rev,
                   (SELECT COUNT(*) FROM revisions r
                     WHERE r.lecture_id = l.id AND r.chapter_id IS NULL
                       AND r.status = 'done') AS done_rev
            FROM lectures l WHERE l.user_id = ? ORDER BY l.id DESC
            """,
            (user_id,),
        ).fetchall()


def get_lecture(user_id: int, lecture_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM lectures WHERE id = ? AND user_id = ?", (lecture_id, user_id)
        ).fetchone()


def delete_lecture(user_id: int, lecture_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM lectures WHERE id = ? AND user_id = ?", (lecture_id, user_id))


def get_chapters(lecture_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chapters WHERE lecture_id = ? ORDER BY position", (lecture_id,)
        ).fetchall()
    return [dict(r, key_points=json.loads(r["key_points"])) for r in rows]


def get_flashcards(lecture_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT f.question, f.answer, c.title AS chapter_title
               FROM flashcards f JOIN chapters c ON c.id = f.chapter_id
               WHERE c.lecture_id = ? ORDER BY c.position, f.id""",
            (lecture_id,),
        ).fetchall()


def get_questions(lecture_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.id, q.chapter_id, q.question, q.options, q.correct_index,
                      q.explanation, c.title AS chapter_title
               FROM quiz_questions q JOIN chapters c ON c.id = q.chapter_id
               WHERE c.lecture_id = ? ORDER BY c.position, q.id""",
            (lecture_id,),
        ).fetchall()
    return [dict(r, options=json.loads(r["options"])) for r in rows]


# ---------- quiz attempts ----------
def save_attempt(user_id: int, lecture_id: int, score: int, total: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO quiz_attempts (user_id, lecture_id, score, total) VALUES (?, ?, ?, ?)",
            (user_id, lecture_id, score, total),
        )


def get_attempts(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT a.score, a.total, a.taken_at, l.title
               FROM quiz_attempts a JOIN lectures l ON l.id = a.lecture_id
               WHERE a.user_id = ? ORDER BY a.id""",
            (user_id,),
        ).fetchall()


# ---------- revisions ----------
def add_weak_revisions(user_id: int, lecture_id: int, chapter_id: int, dates: list) -> None:
    """Schedule extra revisions for a chapter answered wrongly (no duplicates)."""
    with get_conn() as conn:
        for d in dates:
            exists = conn.execute(
                "SELECT 1 FROM revisions WHERE user_id = ? AND chapter_id = ? "
                "AND due_date = ? AND status = 'pending'",
                (user_id, chapter_id, d.isoformat()),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO revisions (user_id, lecture_id, chapter_id, due_date, note) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, lecture_id, chapter_id, d.isoformat(), "Weak topic from quiz"),
                )


def due_revisions(user_id: int, today: date):
    with get_conn() as conn:
        return conn.execute(
            """SELECT r.id, r.lecture_id, r.due_date, r.note,
                      l.title AS lecture_title, c.title AS chapter_title
               FROM revisions r
               JOIN lectures l ON l.id = r.lecture_id
               LEFT JOIN chapters c ON c.id = r.chapter_id
               WHERE r.user_id = ? AND r.status = 'pending' AND r.due_date <= ?
               ORDER BY r.due_date, r.id""",
            (user_id, today.isoformat()),
        ).fetchall()


def upcoming_revisions(user_id: int, today: date, limit: int = 10):
    with get_conn() as conn:
        return conn.execute(
            """SELECT r.due_date, r.note, l.title AS lecture_title, c.title AS chapter_title
               FROM revisions r
               JOIN lectures l ON l.id = r.lecture_id
               LEFT JOIN chapters c ON c.id = r.chapter_id
               WHERE r.user_id = ? AND r.status = 'pending' AND r.due_date > ?
               ORDER BY r.due_date, r.id LIMIT ?""",
            (user_id, today.isoformat(), limit),
        ).fetchall()


def mark_revision_done(user_id: int, revision_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE revisions SET status = 'done' WHERE id = ? AND user_id = ?",
            (revision_id, user_id),
        )

"""Sign-up and login with hashed passwords (bcrypt)."""
import re

import bcrypt

import db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def sign_up(email: str, password: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user_id = db.create_user(email, hashed)
    if user_id is None:
        return False, "An account with this email already exists."
    return True, "Account created. You can log in now."


def log_in(email: str, password: str):
    """Return the user row if the credentials are right, otherwise None."""
    user = db.get_user_by_email(email.strip().lower())
    if user is None:
        return None
    ok = bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8"))
    return user if ok else None

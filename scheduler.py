"""Revision-date logic (spaced repetition)."""
from datetime import date, timedelta

# Days after the lecture is saved on which the student should revise.
MODES = {
    "Smart (days 1, 3, 7, 14)": [1, 3, 7, 14],
    "Simple (every 2 days for 2 weeks)": [2, 4, 6, 8, 10, 12, 14],
}
DEFAULT_MODE = "Smart (days 1, 3, 7, 14)"


def revision_dates(start: date, mode: str = DEFAULT_MODE) -> list[date]:
    """Return the dates on which a new lecture should be revised."""
    gaps = MODES.get(mode, MODES[DEFAULT_MODE])
    return [start + timedelta(days=g) for g in gaps]


def weak_topic_dates(today: date) -> list[date]:
    """A chapter answered wrongly comes back tomorrow and again in 4 days."""
    return [today + timedelta(days=1), today + timedelta(days=4)]

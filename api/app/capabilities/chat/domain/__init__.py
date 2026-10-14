"""Chat's own domain types: conversation turns and answer feedback."""

from .conversation import MAX_HISTORY_TURNS, MAX_SOURCES, Turn, source_line, turns_from
from .feedback import (
    MAX_NOTE,
    MAX_PROJECT_IDS,
    MAX_QUESTION,
    Feedback,
    IssueCategory,
    Verdict,
)

__all__ = [
    "MAX_HISTORY_TURNS",
    "MAX_NOTE",
    "MAX_PROJECT_IDS",
    "MAX_QUESTION",
    "MAX_SOURCES",
    "Feedback",
    "IssueCategory",
    "Turn",
    "Verdict",
    "source_line",
    "turns_from",
]

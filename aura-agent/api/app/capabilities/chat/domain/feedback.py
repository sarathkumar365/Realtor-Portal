"""What a realtor tells us about an answer (AUR-59, AUR-60).

Categories are an enum, not free text: Sudhanshu works the queue by category,
and free text becomes forty spellings of "price wrong".

Deliberately absent: the answer text. It can carry commission and internal notes
in Realtor Mode, and until Phase 4 the store is a platform log. `answer_id`
joins to `ai_messages` once that exists.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

# Long enough for a real question, short enough to keep the log line one line.
MAX_QUESTION = 500
MAX_NOTE = 200
# Both bounds are load-bearing. Capping only the count left the field unbounded
# in practice: twelve ids of 200kB each is a valid body, and it produced a 2.3MB
# log line behind a 200 -- and until Phase 4 that log IS the storage.
MAX_PROJECT_IDS = 12
MAX_ID_LEN = 64

ProjectId = Annotated[str, StringConstraints(max_length=MAX_ID_LEN)]


class Verdict(StrEnum):
    UP = "up"
    DOWN = "down"


class IssueCategory(StrEnum):
    """The seven from AUR-60. An eighth is a product decision and a schema
    change together, not whatever the client happens to send."""

    PRICE = "price_incorrect"
    DEPOSIT = "deposit_incorrect"
    INCENTIVE = "incentive_outdated"
    OCCUPANCY = "occupancy_incorrect"
    MISSING_PROJECT = "missing_project"
    SOURCE = "source_outdated"
    OTHER = "other"


class Feedback(BaseModel):
    """One report about one answer.

    No `user` field on purpose: it comes from the verified token at the route,
    never the body.

    `verdict` is optional because a thumb judges the ANSWER (AUR-59) and a data
    issue reports the SHEET (AUR-60) -- a well-sourced answer can quote a stale
    price. Forcing every report to be a thumbs-down counted good answers as bad.
    """

    answer_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=MAX_QUESTION)
    verdict: Verdict | None = None
    category: IssueCategory | None = None
    note: str = Field(default="", max_length=MAX_NOTE)
    project_ids: list[ProjectId] = Field(default_factory=list, max_length=MAX_PROJECT_IDS)

    @model_validator(mode="after")
    def _says_something(self) -> "Feedback":
        """Optional on both does not mean optional on neither -- a body with no
        verdict, category or note is a queue row that reports nothing."""
        if self.verdict is None and self.category is None and not self.note.strip():
            raise ValueError("a report needs a verdict, a category or a note")
        return self

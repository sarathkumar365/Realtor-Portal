"""Conversation turns, in a shape no framework owns."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Turn(BaseModel):
    role: Role
    content: str = Field(max_length=8000)


MAX_HISTORY_TURNS = 20


MAX_SOURCES = 12
MAX_CONTENT = 8000


def source_line(sources: list[dict]) -> str:
    """The ids an answer was built from, as one line the model can read."""
    named = []
    for s in sources[:MAX_SOURCES]:
        pid = str(s.get("id") or "").strip()
        if not pid:
            continue
        name = str(s.get("name") or "").strip()
        named.append(f"{pid} {name}".strip())
    return f"[projects: {'; '.join(named)}]" if named else ""


def turns_from(rows: list[dict], *, limit: int = MAX_HISTORY_TURNS) -> list[Turn]:
    """Stored rows -> the turns the model is given."""
    out: list[Turn] = []
    for row in rows[-limit:]:
        role = str(row.get("role") or "")
        if role not in (Role.USER, Role.ASSISTANT):
            continue
        content = str(row.get("message") or "")
        if role == Role.ASSISTANT:
            line = source_line(row.get("sources") or [])
            if line:
                head = content[: MAX_CONTENT - len(line) - 1]
                content = f"{head}\n{line}" if head else line
        if not content:
            continue
        out.append(Turn(role=Role(role), content=content[:MAX_CONTENT]))
    return out

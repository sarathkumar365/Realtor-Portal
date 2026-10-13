"""Who the agent works for: one organization per deployment.

The only place in `app/` that names the brokerage or holds its brand. Capabilities
take the profile from the container; a second brokerage gets its own service and
database, not a second profile here.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HEX_COLOUR = r"^#[0-9A-Fa-f]{6}$"


class MarkWord(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(pattern=r"^[^\W\d_]+$")  # letters, accented ones too
    colour: str = Field(pattern=HEX_COLOUR)


class Brand(BaseModel):
    """The mark printed on every document the organization sends out."""

    model_config = ConfigDict(frozen=True)

    mark_words: tuple[MarkWord, ...] = Field(min_length=1, default=(
        MarkWord(text="AURA", colour="#0E1A24"),
        MarkWord(text="KEY", colour="#C9A227"),
        MarkWord(text="REALTY", colour="#0E1A24"),
    ))
    # A PDF base-14 family: every reader has it, so nothing is embedded.
    font: Literal["Times", "Helvetica", "Courier"] = "Times"
    size: float = Field(default=7.5, gt=0)      # points
    tracking: float = Field(default=1.6, ge=0)  # points between letters
    opacity: float = Field(default=0.55, gt=0, le=1)
    margin: float = Field(default=36, ge=0)     # points from the page edge

    @property
    def mark_text(self) -> str:
        return " ".join(word.text for word in self.mark_words)


class Organization(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "Aura Key Realty"
    short_name: str = "Aura Key"
    assistant_name: str = "Aura"
    region: str = "the Greater Toronto Area"
    brand: Brand = Brand()

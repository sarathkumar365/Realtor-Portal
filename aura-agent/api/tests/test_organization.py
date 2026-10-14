"""Who the agent works for comes from one profile, not from capability code."""

import re
from pathlib import Path

from app.capabilities.chat.prompts import system_prompt
from app.capabilities.unbrander.domain import Brief, HitList
from app.capabilities.unbrander.prompts import judge_prompt, sort_prompt
from app.domain import Brand, MarkWord, Organization

APP = Path(__file__).resolve().parents[1] / "app"

NORTH_STAR = Organization(
    name="North Star Homes", short_name="North Star", assistant_name="Polaris",
    region="the Ottawa Valley",
    brand=Brand(mark_words=(MarkWord(text="NORTH", colour="#123456"),
                            MarkWord(text="STAR", colour="#ABCDEF")), font="Helvetica"),
)


def test_the_chat_prompt_names_the_profiles_organization():
    prompt = system_prompt(NORTH_STAR, client_mode=False)
    assert prompt.startswith("You are Polaris, the assistant for realtors at North Star Homes")
    assert "the Ottawa Valley" in prompt
    assert "Aura" not in prompt


def test_the_default_profile_keeps_the_chat_prompts_opening():
    assert system_prompt(Organization(), client_mode=False).startswith(
        "You are Aura, the assistant for realtors at Aura Key Realty, a\n"
        "new-build brokerage in the Greater Toronto Area.")


def test_the_unbrand_prompts_name_the_profiles_organization_and_mark():
    brief = Brief(hits=HitList(builder="Arista Homes", project="SouthCal"), page_count=1,
                  organization=NORTH_STAR)
    assert "for North Star Homes" in sort_prompt(brief)
    judge = judge_prompt(brief)
    assert '"NORTH STAR"' in judge and "North Star Homes" in judge
    assert "Aura" not in sort_prompt(brief) + judge


def test_the_brokerage_is_named_only_in_the_organization_profile():
    """A second brokerage gets a new profile, not a hunt through capability code."""
    name = re.compile(r"aura\s+key|key\s+realty", re.IGNORECASE)
    named = [str(path.relative_to(APP)) for path in APP.rglob("*.py")
             if path.name != "organization.py" and name.search(path.read_text())]
    assert named == []

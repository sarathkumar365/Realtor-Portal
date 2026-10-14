from app.domain import Project


def a_project(**over) -> Project:
    base = dict(
        id="AK-0001", name="Reva Westfield", city="BRAMPTON", builder="Great Gulf",
        property_type="Townhome", categories=["townhome"], starting_price=899900,
        builder_login="agent@builder", commission="4%", internal_notes="push this one",
        broker_url="https://portal.example/x", website_url="https://public.example/x",
    )
    base.update(over)
    return Project(**base)


# Redaction moved to test_redaction.py, where it is exhaustive over
# (role x mode) rather than testing one audience here.


def test_ai_ready_requires_an_id():
    """AUR-31 -- a project with no PROJECT ID is never presented as linkable."""
    assert a_project().is_ai_ready
    assert not a_project(id=None).is_ai_ready

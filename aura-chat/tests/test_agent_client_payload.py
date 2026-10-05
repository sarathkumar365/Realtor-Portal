"""What the phone is handed for each project card.

The card is the reason the chat is worth opening on a phone -- a name with no
link is a dead end -- and it is also the last place a confidential field could
leak, because it is the one payload the model never touches.
"""

from app.adapters.agent_pydantic import _for_client, _for_model
from app.domain import CLIENT_HIDDEN, ChatMode, Project, Role, Viewer

REALTOR = Viewer(role=Role.REALTOR, mode=ChatMode.REALTOR)
CLIENT = Viewer(role=Role.REALTOR, mode=ChatMode.CLIENT)

FULL = Project(
    id="brampton:duo",
    name="DUO",
    city="Brampton",
    builder="National Homes",
    status="Focus Project",
    property_type="Condo",
    starting_price=370990,
    occupancy="2027",
    deposit_pct=10.0,
    deposit_schedule="$10k on signing, balance to 10% in 180 days",
    incentives="Free assignment + $10k credit",
    broker_url="https://broker.example/duo",
    drive_url="https://drive.example/duo",
    website_url="https://duo.example",
    commission="4%",
    internal_notes="call the rep first",
)


def test_carries_the_links_the_model_payload_drops():
    """The whole reason this function exists. _for_model carries website_url --
    the builder's public site, safe for a buyer -- and neither of the other
    two; the card is where those belong."""
    out = _for_client(FULL)
    assert out["website_url"] == "https://duo.example"
    assert out["drive_url"] == "https://drive.example/duo"
    assert out["broker_url"] == "https://broker.example/duo"
    model = _for_model(FULL)
    assert model["website_url"] == "https://duo.example"
    assert "drive_url" not in model
    assert "broker_url" not in model


def test_model_payload_omits_an_empty_website():
    """An empty string is not a link; the key must not appear at all."""
    assert "website_url" not in _for_model(Project(name="X", city="Y"))


def test_field_names_are_the_portals_not_the_domains():
    """projectCard() in the PWA renders a city-screen row and a chat result with
    the same code. Rename a key here and one of the two silently loses a field."""
    for key in ("name", "city", "builder", "status", "broker_url", "drive_url", "website_url"):
        assert key in _for_client(FULL)
    assert "property_type" not in _for_client(FULL)  # the portal calls it `type`
    assert "is_focus" not in _for_client(FULL)       # the pill is keyed on status


def test_client_mode_blanks_the_drive_link():
    """The regression. _for_model omitted every link column, so no chat card had
    one; _for_client carries all three, and that is what first put the
    brokerage's own Drive folder in front of a buyer. website_url is the builder's
    public site and stays."""
    out = _for_client(FULL.for_viewer(CLIENT))
    assert out["drive_url"] == ""
    assert out["website_url"] == "https://duo.example"


def test_client_mode_blanks_the_broker_link_and_the_status():
    """Redaction happens upstream, in RedactingProjectRepo -- this proves the
    payload does not reach around it. Blanking status is what makes the Focus
    pill disappear for a buyer."""
    out = _for_client(FULL.for_viewer(CLIENT))
    assert out["broker_url"] == ""
    assert out["status"] == ""
    assert out["website_url"] == "https://duo.example"   # a public link stays
    assert out["name"] == "DUO"


def test_realtor_mode_keeps_both():
    out = _for_client(FULL.for_viewer(REALTOR))
    assert out["broker_url"] == "https://broker.example/duo"
    assert out["drive_url"] == "https://drive.example/duo"
    assert out["status"] == "Focus Project"


def test_no_client_hidden_field_survives_as_a_key_with_a_value():
    """The leak probe. Every field on the client-hidden list must be absent from
    the payload or empty in it -- checked as a set so adding a ninth hidden
    field fails here instead of shipping."""
    out = _for_client(FULL.for_viewer(CLIENT))
    leaked = [f for f in CLIENT_HIDDEN if out.get(f)]
    assert leaked == []


def test_carries_the_deposit_and_incentive_the_card_now_shows():
    """AUR-46. _for_model only carried these, so the card had a price and
    nothing about the terms behind it."""
    out = _for_client(FULL)
    assert out["depositpct"] == 10.0
    assert out["depositsched"].startswith("$10k on signing")
    assert out["incentives"] == "Free assignment + $10k credit"


def test_the_deposit_keys_are_spelled_the_way_the_sheet_spells_them():
    """getCity_ emits these names, and one projectCard() renders both a city row
    and a chat result -- a domain-style key would need a translation layer."""
    out = _for_client(FULL)
    for key in ("depositpct", "depositsched", "incentives"):
        assert key in out
    assert "deposit_pct" not in out
    assert "deposit_schedule" not in out


def test_deposit_and_incentive_survive_client_mode():
    """Deliberate, and checked so it cannot be reversed by accident: AUR-55
    names what Client Mode strips and neither of these is on it."""
    out = _for_client(FULL.for_viewer(CLIENT))
    assert out["depositpct"] == 10.0
    assert out["incentives"] == "Free assignment + $10k credit"

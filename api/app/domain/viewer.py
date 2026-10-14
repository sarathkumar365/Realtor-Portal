"""Who is looking, and what they are allowed to see.

Two axes that both end in "hide this field", and they are not the same question:

* **role** — what this *account* may ever see. An admin sees builder-portal
  credentials; a realtor does not. Set at sign-in, not chosen.
* **mode** — what is on the screen *right now*. A realtor in Client Mode has
  turned their phone toward a buyer, so commission and internal notes must go,
  even though the account is entitled to them.

Keeping them separate matters: a realtor in Realtor Mode and an admin in Client
Mode hide different things, and collapsing the two into one flag would get one
of those wrong.
"""

from pydantic import BaseModel

from .identity import Claims, ChatMode, Role

# Fields nobody but an admin may see, in any mode. Builder-portal logins are
# other companies' credentials; the portal already gates them in getBuilders_.
ADMIN_ONLY = frozenset({"builder_login"})

# Fields no buyer may see over a realtor's shoulder, whatever the account is.
# This is the list AUR-55 and AUR-56 are measured against, and the leak test
# (AUR-58) probes for every one of them.
CLIENT_HIDDEN = frozenset(
    {
        "builder_login",
        "builder_office",
        "builder_contact",
        "fub_template",
        "commission",
        "internal_notes",
        "broker_url",
        # The brokerage's own Drive folder for a project -- collateral, pricing
        # worksheets, whatever the team keeps in there. Realtor-facing by nature,
        # and it only became reachable by a buyer when chat cards started carrying
        # the link columns; before that no card had any link on it at all.
        "drive_url",
        "status",
    }
)


class Viewer(BaseModel):
    """The audience for one answer."""

    role: Role = Role.REALTOR
    mode: ChatMode = ChatMode.REALTOR

    @classmethod
    def of(cls, claims: Claims, mode: ChatMode) -> "Viewer":
        return cls(role=claims.role, mode=mode)

    @property
    def hidden_fields(self) -> frozenset[str]:
        """Everything this viewer must not see, as one set.

        Union, never intersection: each axis can only take things away. An admin
        in Client Mode is still showing a buyer a screen, so admin entitlement
        does not buy back a client-hidden field.
        """
        hidden: frozenset[str] = frozenset()
        if self.role is not Role.ADMIN:
            hidden |= ADMIN_ONLY
        if self.mode is ChatMode.CLIENT:
            hidden |= CLIENT_HIDDEN
        return hidden


# The audience for anything that has not been given one. Deliberately the most
# restrictive: a missing viewer is a bug, and a bug must not open a field.
STRICTEST = Viewer(role=Role.REALTOR, mode=ChatMode.CLIENT)

"""Who is asking, and in what mode. No I/O, no framework."""

from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    REALTOR = "realtor"
    ADMIN = "admin"


class ChatMode(StrEnum):
    """Realtor mode shows everything the role allows. Client mode is what a
    buyer may see over the realtor's shoulder — enforced in code, before the
    model is called, never by asking the model to withhold something."""

    REALTOR = "realtor"
    CLIENT = "client"


class Claims(BaseModel):
    """The verified contents of a portal session token."""

    user: str
    role: Role
    issued_ms: int

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

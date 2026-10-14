from typing import Protocol

from app.domain import Organization


class OrganizationStore(Protocol):
    """The organization profile, stored so an admin can edit it without a deploy.

    A port so the container and the routes are tested without a database.
    """

    async def load(self) -> Organization | None:
        """The saved profile, or None when nobody has saved one: the defaults apply."""
        ...

    async def save(self, organization: Organization, *, by: str) -> None: ...

    async def healthy(self) -> bool: ...

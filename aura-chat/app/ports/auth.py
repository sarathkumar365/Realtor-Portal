from typing import Protocol

from app.domain import Claims


class AuthVerifier(Protocol):
    """Turns a bearer token into a verified identity, or nothing.

    Two levels on purpose. `verify_local` is signature and expiry only -- no
    network, so junk is rejected without a round trip. `verify` additionally
    confirms the account is still live, which for the portal adapter means
    asking the portal, because only it can see the LOGIN sheet.
    """

    def verify_local(self, token: str) -> Claims | None: ...

    async def verify(self, token: str) -> Claims | None: ...

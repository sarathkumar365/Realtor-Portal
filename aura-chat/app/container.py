"""Composition root -- the ONE place adapters are constructed."""

from dataclasses import dataclass, field

from app.adapters.auth_portal_hmac import PortalHmacAuthVerifier
from app.adapters.portal_client import PortalClient
from app.adapters.projects_exec import ExecApiProjectRepo
from app.adapters.projects_redacting import RedactingProjectRepo
from app.capabilities.chat.adapters.agent_pydantic import PydanticAgentRuntime
from app.capabilities.chat.adapters.store_postgres import PostgresConversationStore
from app.capabilities.chat.ports import AgentRuntime, ConversationStore, DocumentIndex
from app.config import Settings, load
from app.domain import Organization, Viewer
from app.ports import AuthVerifier, ProjectRepo


@dataclass(slots=True)
class Container:
    settings: Settings
    portal: PortalClient
    auth: AuthVerifier
    organization: Organization = field(default_factory=Organization)
    projects: ProjectRepo | None = None
    store: ConversationStore | None = None
    documents: DocumentIndex | None = None
    runtime: AgentRuntime | None = None

    def projects_for(self, viewer: Viewer) -> ProjectRepo:
        """The project repo as one viewer may see it."""
        if self.projects is None:
            raise RuntimeError("project repo is not configured")
        return RedactingProjectRepo(self.projects, viewer)

    async def aclose(self) -> None:
        await self.portal.aclose()
        closer = getattr(self.store, "aclose", None)
        if closer is not None:
            await closer()


def build(settings: Settings | None = None) -> Container:
    cfg = settings or load()
    portal = PortalClient(cfg.exec_url, timeout_s=cfg.exec_timeout_s)
    auth = PortalHmacAuthVerifier(cfg.token_secret, portal, session_ms=cfg.session_ms)
    projects = ExecApiProjectRepo(portal)
    # The defaults, until the profile is stored and editable.
    organization = Organization()
    runtime = PydanticAgentRuntime(
        api_key=cfg.openrouter_api_key,
        model_name=cfg.llm_model,
        organization=organization,
        max_tokens=cfg.llm_max_tokens,
    )
    store = PostgresConversationStore(cfg.database_url) if cfg.database_url else None
    return Container(
        settings=cfg, portal=portal, auth=auth, organization=organization, projects=projects,
        runtime=runtime, store=store
    )

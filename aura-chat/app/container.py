"""Composition root -- the ONE place adapters are constructed."""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from app.adapters.auth_portal_hmac import PortalHmacAuthVerifier
from app.adapters.organization_postgres import PostgresOrganizationStore
from app.adapters.portal_client import PortalClient
from app.adapters.projects_exec import ExecApiProjectRepo
from app.adapters.projects_redacting import RedactingProjectRepo
from app.capabilities.chat.adapters.agent_pydantic import PydanticAgentRuntime
from app.capabilities.chat.adapters.store_postgres import PostgresConversationStore
from app.capabilities.chat.ports import AgentRuntime, ConversationStore, DocumentIndex
from app.capabilities.unbrander.adapters.drive_google import GoogleDriveWriter
from app.capabilities.unbrander.adapters.jobs_postgres import PostgresJobStore
from app.capabilities.unbrander.adapters.models_langchain import LangChainUnbrandModels
from app.capabilities.unbrander.adapters.pdf_edit_pymupdf import PyMuPdfEditor
from app.capabilities.unbrander.adapters.pdf_pymupdf import PyMuPdfInspector
from app.capabilities.unbrander.files import JobFiles
from app.capabilities.unbrander.ports import GoogleWriter, JobStore, PdfEditor, PdfInspector
from app.capabilities.unbrander.worker import Worker, WorkerSettings
from app.config import Settings, load
from app.domain import Organization, Viewer
from app.ports import AuthVerifier, OrganizationStore, ProjectRepo

log = logging.getLogger("aura.container")


@dataclass(slots=True)
class Container:
    settings: Settings
    portal: PortalClient
    auth: AuthVerifier
    organization: Organization = field(default_factory=Organization)
    organization_store: OrganizationStore | None = None
    projects: ProjectRepo | None = None
    store: ConversationStore | None = None
    documents: DocumentIndex | None = None
    runtime: AgentRuntime | None = None
    # Builds the chat runtime for a profile: a saved profile replaces the runtime,
    # because the runtime caches agents with the brokerage's name in their prompt.
    runtime_for: Callable[[Organization], AgentRuntime] | None = None
    # Unbrander. Jobs and files are wired whenever there is a database, so uploads
    # queue even while the worker is switched off.
    jobs: JobStore | None = None
    job_files: JobFiles | None = None
    pdf_inspector: PdfInspector | None = None
    pdf_editor: PdfEditor | None = None  # page images and the mark preview for the admin app
    drive: GoogleWriter | None = None
    worker: Worker | None = None
    ocr_problem: Callable[[], str | None] | None = None
    worker_task: asyncio.Task | None = None

    def projects_for(self, viewer: Viewer) -> ProjectRepo:
        """The project repo as one viewer may see it."""
        if self.projects is None:
            raise RuntimeError("project repo is not configured")
        return RedactingProjectRepo(self.projects, viewer)

    async def start(self) -> None:
        """Load the saved profile and start the job worker. Called once at boot."""
        if self.organization_store is not None:
            try:
                saved = await self.organization_store.load()
            except Exception as exc:  # noqa: BLE001 -- a database outage must not stop chat
                # Chat runs without the database, so a profile it cannot read is
                # not a reason to stay down: serve the defaults until the next boot.
                log.warning("could not load the organization profile, using the defaults:"
                            " %s: %s", type(exc).__name__, exc)
                saved = None
            if saved is not None:
                self.use_organization(saved)
        if self.worker is not None:
            problem = self.ocr_problem() if self.ocr_problem else None
            if problem:
                # Fail the deploy, not the first PDF: verify() blocks every
                # document when OCR cannot run.
                raise RuntimeError(f"Unbrander is enabled but OCR cannot run: {problem}")
            self.worker_task = asyncio.create_task(self.worker.run_forever())

    def use_organization(self, organization: Organization) -> None:
        self.organization = organization
        if self.runtime_for is not None:
            self.runtime = self.runtime_for(organization)

    async def save_organization(self, organization: Organization, *, by: str) -> None:
        if self.organization_store is None:
            raise RuntimeError("organization store is not configured")
        await self.organization_store.save(organization, by=by)
        self.use_organization(organization)

    async def aclose(self) -> None:
        if self.worker_task is not None:
            self.worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker_task
        await self.portal.aclose()
        for resource in (self.store, self.jobs, self.drive, self.organization_store):
            closer = getattr(resource, "aclose", None)
            if closer is not None:
                await closer()


def build(settings: Settings | None = None) -> Container:
    cfg = settings or load()
    portal = PortalClient(cfg.exec_url, timeout_s=cfg.exec_timeout_s)
    auth = PortalHmacAuthVerifier(cfg.token_secret, portal, session_ms=cfg.session_ms)
    projects = ExecApiProjectRepo(portal)
    # The defaults until start() loads a saved profile.
    organization = Organization()

    def runtime_for(profile: Organization) -> AgentRuntime:
        return PydanticAgentRuntime(
            api_key=cfg.openrouter_api_key,
            model_name=cfg.llm_model,
            organization=profile,
            max_tokens=cfg.llm_max_tokens,
        )

    dsn = cfg.database_url
    container = Container(
        settings=cfg, portal=portal, auth=auth, organization=organization, projects=projects,
        runtime=runtime_for(organization), runtime_for=runtime_for,
        store=PostgresConversationStore(dsn) if dsn else None,
        organization_store=PostgresOrganizationStore(dsn) if dsn else None,
        jobs=PostgresJobStore(dsn) if dsn else None,
        job_files=JobFiles(cfg.unbrander_data_dir),
    )
    inspector = PyMuPdfInspector()
    container.pdf_inspector = inspector
    container.pdf_editor = PyMuPdfEditor()
    container.ocr_problem = inspector.ocr_problem
    container.drive = _drive(cfg)
    if cfg.unbrander_enabled:
        _wire_worker(container, cfg, inspector)
    return container


def _missing(*settings: tuple[str, str]) -> list[str]:
    return [name for name, value in settings if not value]


def _drive(cfg: Settings) -> GoogleWriter | None:
    """Drive is optional: without the key, jobs are unbranded and downloaded, and
    filing is refused. With it, every id it files under must be set too."""
    if not cfg.google_service_account_json:
        return None
    missing = _missing(("DRIVE_SHARED_DRIVE_ID", cfg.drive_shared_drive_id),
                       ("DRIVE_ROOT_FOLDER_ID", cfg.drive_root_folder_id),
                       ("DRIVE_TEST_ROOT_FOLDER_ID", cfg.drive_test_root_folder_id))
    if missing:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is set but these are not: "
                           + ", ".join(missing))
    return GoogleDriveWriter(cfg.google_service_account_json, cfg.drive_shared_drive_id)


def _wire_worker(container: Container, cfg: Settings, inspector: PyMuPdfInspector) -> None:
    missing = _missing(("DATABASE_URL", cfg.database_url),
                       ("OPENROUTER_API_KEY", cfg.openrouter_api_key))
    if missing:
        raise RuntimeError("UNBRANDER_ENABLED is true but these are not set: "
                           + ", ".join(missing))

    def new_models() -> LangChainUnbrandModels:
        return LangChainUnbrandModels(
            api_key=cfg.openrouter_api_key, sort_model=cfg.unbrander_sort_model,
            pick_model=cfg.unbrander_pick_model, judge_model=cfg.unbrander_judge_model,
            repair_model=cfg.unbrander_repair_model, thinking=cfg.unbrander_thinking,
        )

    container.worker = Worker(
        jobs=container.jobs, drive=container.drive, files=container.job_files,
        editor=container.pdf_editor, inspector=inspector, new_models=new_models,
        settings=WorkerSettings(
            drive_root_folder_id=cfg.drive_root_folder_id,
            drive_test_root_folder_id=cfg.drive_test_root_folder_id,
            max_repair_rounds=cfg.unbrander_max_rounds,
            docs_per_day=cfg.unbrander_docs_per_day,
            doc_timeout_s=cfg.unbrander_doc_timeout_min * 60,
            retention_days=cfg.unbrander_retention_days,
        ),
    )

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from ..domain import Job, JobDocument, JobEvent, JobStatus, NewJob


class JobStore(Protocol):
    """Jobs, their documents and the audit log.

    A port so the worker and the routes are tested without a database. Status is
    the state machine: the worker reads it to know which step to run next.
    """

    async def create(self, job: NewJob) -> Job:
        """The job in RECEIVED and its documents in PENDING, in one transaction."""
        ...

    async def get(self, job_id: str) -> Job | None:
        """The job with its documents, in upload order."""
        ...

    async def recent(self, *, status: JobStatus | None = None, limit: int = 50) -> list[Job]:
        """Newest first, without documents."""
        ...

    async def set_status(self, job_id: str, status: JobStatus, *, error: str | None = None) -> None:
        """Stamps ended_at when the status is one in ENDED, and clears it otherwise."""
        ...

    async def move(self, job_id: str, from_status: JobStatus, to_status: JobStatus) -> bool:
        """set_status, only if the job is still in `from_status`, in one statement.
        False when it was not: someone else moved it first."""
        ...

    async def set_drive_folder(self, job_id: str, folder_id: str) -> None: ...

    async def update_document(self, document: JobDocument) -> None:
        """Writes what the worker learns about a document; never its upload facts."""
        ...

    async def add_event(self, event: JobEvent) -> None: ...

    async def events(self, job_id: str) -> list[JobEvent]:
        """Oldest first."""
        ...

    async def documents_started_since(self, since: datetime) -> int: ...

    async def ended_before(self, before: datetime) -> list[str]:
        """Ids of jobs that ended before `before`: their files may be evicted."""
        ...

    def claim(self) -> AbstractAsyncContextManager[Job | None]:
        """Hold the oldest job that has not ended, for as long as the block runs.

        The hold is a Postgres advisory lock on one connection, so a worker that
        dies releases it with its connection. None when every open job is held
        or none is open.
        """
        ...

    async def healthy(self) -> bool: ...

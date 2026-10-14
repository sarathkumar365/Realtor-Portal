from typing import Protocol


class DriveWriteFailed(RuntimeError):
    """A Drive call failed for good: a permanent error, or a transient one that
    outlasted its retries. The job moves to FAILED with this message."""


class GoogleWriter(Protocol):
    """Writes to the Shared Drive. For now it only creates folders and uploads
    files, all private; sharing and the sheet arrive with publishing.

    A port so the worker is tested without Google, and because it holds the one
    credential that can write outside this service.
    """

    async def find_or_create_folder(self, parent_id: str, name: str) -> tuple[str, bool]:
        """The folder's id, and whether it already existed."""
        ...

    async def upload_pdf(self, folder_id: str, name: str, data: bytes) -> str:
        """The new file's id. Drive allows two files of the same name; this adds one."""
        ...

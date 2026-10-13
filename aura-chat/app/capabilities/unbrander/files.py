"""A job's files on the volume: the uploads and the cleaned outputs.

Plain pathlib, not a port: like the database driver and the HTTP framework, the
filesystem is not something the design expects to swap.

    <data_dir>/<job_id>/source/<position>.pdf
    <data_dir>/<job_id>/output/<position>.pdf
"""

import shutil
from pathlib import Path


class JobFiles:
    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)

    def save_source(self, job_id: str, position: int, data: bytes) -> None:
        self._write(self._path(job_id, "source", position), data)

    def source(self, job_id: str, position: int) -> bytes:
        return self._path(job_id, "source", position).read_bytes()

    def save_output(self, job_id: str, position: int, data: bytes) -> None:
        self._write(self._path(job_id, "output", position), data)

    def output(self, job_id: str, position: int) -> bytes:
        return self._path(job_id, "output", position).read_bytes()

    def evict(self, job_id: str) -> bool:
        """Delete everything the job has on the volume. False when nothing was there."""
        folder = self.root / job_id
        if not folder.exists():
            return False
        shutil.rmtree(folder)
        return True

    def _path(self, job_id: str, kind: str, position: int) -> Path:
        if "/" in job_id or job_id in ("", ".", ".."):
            raise ValueError(f"not a job id: {job_id!r}")
        return self.root / job_id / kind / f"{position}.pdf"

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        partial.write_bytes(data)
        partial.replace(path)  # a crash mid-write never leaves a half PDF under the real name

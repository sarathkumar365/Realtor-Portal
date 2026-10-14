"""JobStore on Postgres, with asyncpg like the chat store."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Collection
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import asyncpg

from ..domain import (
    ENDED,
    PASSED,
    WORKING,
    Job,
    JobCounts,
    JobDocument,
    JobEvent,
    JobStatus,
    NewJob,
)

SCHEMA = Path(__file__).with_name("schema.sql")

POOL_MIN, POOL_MAX = 1, 5
CONNECT_TIMEOUT_S = 5.0
# Open jobs looked at per claim. More than one, because the oldest may be held
# by a worker still running from the deploy before this one.
CLAIM_CANDIDATES = 20

JOB_COLUMNS = (
    "id, status, uploader, instructions, project, builder, short_forms, city, province,"
    " organization, dry_run, file_when_done, drive_folder_id, error, created_at, updated_at,"
    " ended_at"
)
DOCUMENT_COLUMNS = (
    "id, job_id, position, filename, sha256, page_count, status, doc_type, dropped_pages,"
    " removed_items, findings, rounds, usage, cost_usd, drive_file_id, started_at"
)
JSON_JOB = ("short_forms", "organization")
JSON_DOCUMENT = ("dropped_pages", "removed_items", "findings", "usage")


def _new_id() -> str:
    return str(uuid.uuid4())


class PostgresJobStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._lock = asyncio.Lock()

    async def _ready(self) -> asyncpg.Pool:
        """The pool, built once, and only assigned once the schema is on it."""
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is not None:
                return self._pool
            pool = await asyncpg.create_pool(
                self._dsn, min_size=POOL_MIN, max_size=POOL_MAX, timeout=CONNECT_TIMEOUT_S
            )
            try:
                async with pool.acquire() as con:
                    await con.execute(SCHEMA.read_text())
            except BaseException:
                await pool.close()
                raise
            self._pool = pool
            return self._pool

    async def create(self, job: NewJob) -> Job:
        pool = await self._ready()
        job_id = job.id
        async with pool.acquire() as con, con.transaction():
            await con.execute(
                "INSERT INTO unbrander_jobs (id, status, uploader, instructions, project, builder,"
                " short_forms, city, province, organization, dry_run, file_when_done)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10::jsonb, $11, $12)",
                job_id, JobStatus.RECEIVED.value, job.uploader, job.instructions, job.project,
                job.builder, json.dumps(job.short_forms), job.city, job.province,
                job.organization.model_dump_json(), job.dry_run, job.file_when_done,
            )
            await con.executemany(
                "INSERT INTO unbrander_documents (id, job_id, position, filename, sha256,"
                " page_count, status) VALUES ($1, $2, $3, $4, $5, $6, 'PENDING')",
                [(_new_id(), job_id, position, document.filename, document.sha256,
                  document.page_count)
                 for position, document in enumerate(job.documents, start=1)],
            )
        created = await self.get(job_id)
        assert created is not None
        return created

    async def get(self, job_id: str) -> Job | None:
        pool = await self._ready()
        row = await pool.fetchrow(f"SELECT {JOB_COLUMNS} FROM unbrander_jobs WHERE id = $1", job_id)
        if row is None:
            return None
        documents = await pool.fetch(
            f"SELECT {DOCUMENT_COLUMNS} FROM unbrander_documents WHERE job_id = $1"
            " ORDER BY position", job_id,
        )
        return _job(row, [_document(document) for document in documents])

    async def recent(self, *, statuses: Collection[JobStatus] = (), limit: int = 50,
                     documents: bool = False) -> list[Job]:
        pool = await self._ready()
        rows = await pool.fetch(
            f"SELECT {JOB_COLUMNS} FROM unbrander_jobs"
            " WHERE cardinality($1::text[]) = 0 OR status = ANY($1::text[])"
            " ORDER BY created_at DESC LIMIT $2",
            [status.value for status in statuses], min(limit, 200),
        )
        by_job: dict[str, list[JobDocument]] = {row["id"]: [] for row in rows}
        if documents and by_job:
            # One query for every job's documents, not one per job.
            for document in await pool.fetch(
                f"SELECT {DOCUMENT_COLUMNS} FROM unbrander_documents WHERE job_id = ANY($1::text[])"
                " ORDER BY job_id, position", list(by_job),
            ):
                by_job[document["job_id"]].append(_document(document))
        return [_job(row, by_job[row["id"]]) for row in rows]

    async def set_status(self, job_id: str, status: JobStatus, *, error: str | None = None) -> None:
        pool = await self._ready()
        await pool.execute(
            "UPDATE unbrander_jobs SET status = $2, error = $3, updated_at = now(),"
            # Cleared on leaving a resting status: a job sent from UNBRANDED to
            # FILING must not be evicted while it files.
            " ended_at = CASE WHEN $4 THEN now() ELSE NULL END WHERE id = $1",
            job_id, status.value, error, status in ENDED,
        )

    async def move(self, job_id: str, from_status: JobStatus, to_status: JobStatus) -> bool:
        pool = await self._ready()
        result = await pool.execute(
            "UPDATE unbrander_jobs SET status = $3, error = NULL, updated_at = now(),"
            " ended_at = CASE WHEN $4 THEN now() ELSE NULL END WHERE id = $1 AND status = $2",
            job_id, from_status.value, to_status.value, to_status in ENDED,
        )
        return result == "UPDATE 1"

    async def set_drive_folder(self, job_id: str, folder_id: str) -> None:
        pool = await self._ready()
        await pool.execute(
            "UPDATE unbrander_jobs SET drive_folder_id = $2, updated_at = now() WHERE id = $1",
            job_id, folder_id,
        )

    async def update_document(self, document: JobDocument) -> None:
        pool = await self._ready()
        await pool.execute(
            "UPDATE unbrander_documents SET status = $2, doc_type = $3, dropped_pages = $4::jsonb,"
            " removed_items = $5::jsonb, findings = $6::jsonb, rounds = $7, usage = $8::jsonb,"
            " cost_usd = $9, drive_file_id = $10, started_at = $11, updated_at = now()"
            " WHERE id = $1",
            document.id, document.status.value, document.doc_type,
            json.dumps(document.dropped_pages),
            json.dumps([item.model_dump(mode="json") for item in document.removed_items]),
            json.dumps([finding.model_dump(mode="json") for finding in document.findings]),
            document.rounds,
            json.dumps({role: usage.model_dump() for role, usage in document.usage.items()}),
            document.cost_usd, document.drive_file_id, document.started_at,
        )

    async def add_event(self, event: JobEvent) -> None:
        pool = await self._ready()
        await pool.execute(
            "INSERT INTO unbrander_job_events (job_id, document_id, actor, action, result, detail)"
            " VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
            event.job_id, event.document_id, event.actor, event.action, event.result,
            json.dumps(event.detail, default=str),
        )

    async def events(self, job_id: str) -> list[JobEvent]:
        pool = await self._ready()
        rows = await pool.fetch(
            "SELECT job_id, document_id, actor, action, result, detail, at"
            " FROM unbrander_job_events WHERE job_id = $1 ORDER BY at, id", job_id,
        )
        return [JobEvent(**{**dict(row), "detail": json.loads(row["detail"])}) for row in rows]

    async def documents_started_since(self, since: datetime) -> int:
        pool = await self._ready()
        return await pool.fetchval(
            "SELECT count(*) FROM unbrander_documents WHERE started_at >= $1", since
        )

    async def counts(self, since: datetime) -> JobCounts:
        pool = await self._ready()
        row = await pool.fetchrow(
            "SELECT"
            " (SELECT count(*) FROM unbrander_jobs WHERE status = $1) AS to_review,"
            " (SELECT count(*) FROM unbrander_jobs WHERE status = ANY($2::text[])) AS working,"
            " (SELECT count(*) FROM unbrander_jobs WHERE created_at >= $3) AS jobs_since,"
            " (SELECT coalesce(sum(d.page_count - jsonb_array_length(d.dropped_pages)), 0)"
            "    FROM unbrander_documents d JOIN unbrander_jobs j ON j.id = d.job_id"
            "    WHERE j.created_at >= $3 AND d.status = ANY($4::text[])) AS pages_cleaned_since",
            JobStatus.UNBRANDED.value, [status.value for status in WORKING], since,
            [status.value for status in PASSED],
        )
        return JobCounts(**dict(row))

    async def ended_before(self, before: datetime) -> list[str]:
        pool = await self._ready()
        rows = await pool.fetch("SELECT id FROM unbrander_jobs WHERE ended_at < $1", before)
        return [row["id"] for row in rows]

    @asynccontextmanager
    async def claim(self) -> AsyncIterator[Job | None]:
        pool = await self._ready()
        # One connection for the whole hold: an advisory lock belongs to the
        # session that took it, and dies with it.
        async with pool.acquire() as con:
            held = await self._hold_oldest(con)
            try:
                yield await self.get(held) if held else None
            finally:
                if held:
                    await con.execute("SELECT pg_advisory_unlock(hashtextextended($1, 0))", held)

    async def _hold_oldest(self, con: asyncpg.Connection) -> str | None:
        candidates = await con.fetch(
            "SELECT id FROM unbrander_jobs WHERE status <> ALL($1::text[])"
            " ORDER BY created_at LIMIT $2",
            [status.value for status in ENDED], CLAIM_CANDIDATES,
        )
        for row in candidates:
            job_id = row["id"]
            if not await con.fetchval("SELECT pg_try_advisory_lock(hashtextextended($1, 0))", job_id):
                continue
            # Another worker may have finished it between the select and the lock.
            status = await con.fetchval("SELECT status FROM unbrander_jobs WHERE id = $1", job_id)
            if status not in {ended.value for ended in ENDED}:
                return job_id
            await con.execute("SELECT pg_advisory_unlock(hashtextextended($1, 0))", job_id)
        return None

    async def healthy(self) -> bool:
        try:
            pool = await self._ready()
            return await pool.fetchval("SELECT 1") == 1
        except Exception:  # noqa: BLE001 -- a health check answers, it never raises
            return False

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


def _loaded(row: asyncpg.Record, json_columns: tuple[str, ...]) -> dict:
    values = dict(row)
    for column in json_columns:
        values[column] = json.loads(values[column])
    return values


def _job(row: asyncpg.Record, documents: list[JobDocument]) -> Job:
    return Job(**_loaded(row, JSON_JOB), documents=documents)


def _document(row: asyncpg.Record) -> JobDocument:
    values = _loaded(row, JSON_DOCUMENT)
    if values["cost_usd"] is not None:
        values["cost_usd"] = float(values["cost_usd"])  # NUMERIC arrives as Decimal
    return JobDocument(**values)

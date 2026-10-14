"""Exercise the real Postgres job store against a real database.

Not a pytest, for the same reason as check_store.py: the suite never needs a
database. Run by hand against a development database, never production:

    DATABASE_URL=postgresql://localhost/aura_chat_dev .venv/bin/python scripts/check_jobs.py
"""

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.capabilities.unbrander.adapters.jobs_postgres import PostgresJobStore
from app.capabilities.unbrander.domain import (
    DocumentStatus,
    JobEvent,
    JobStatus,
    NewDocument,
    NewJob,
    Usage,
)
from app.domain import Organization

OK, BAD = "  ok  ", "  FAIL"
fails = 0
RUN = uuid.uuid4().hex[:8]  # rows from earlier runs must not decide this one


def ok(cond: bool, msg: str) -> None:
    global fails
    print((OK if cond else BAD) + "  " + msg)
    if not cond:
        fails += 1


def new_job(project: str) -> NewJob:
    return NewJob(uploader=f"admin-{RUN}", project=project, builder="Arista Homes",
                  short_forms=["AH"], city="Vaughan", organization=Organization(), dry_run=True,
                  documents=[NewDocument(filename="prices.pdf", sha256="a", page_count=2),
                             NewDocument(filename="plans.pdf", sha256="b", page_count=9)])


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2
    store, other_worker = PostgresJobStore(dsn), PostgresJobStore(dsn)
    try:
        # Close every open job left by earlier runs, so the claims below see only ours.
        for stale in await store.recent(limit=200):
            if stale.uploader.startswith("admin-") and stale.status.value not in (
                    "FILED_PRIVATE", "FAILED"):
                await store.set_status(stale.id, JobStatus.FAILED, error="check_jobs cleanup")

        job = await store.create(new_job(f"First-{RUN}"))
        ok(job.status is JobStatus.RECEIVED and len(job.documents) == 2, "created with documents")
        ok([d.position for d in job.documents] == [1, 2], "documents in upload order")
        ok(job.organization == Organization(), "organization copy round-trips")

        second = await store.create(new_job(f"Second-{RUN}"))
        async with store.claim() as held:
            ok(held is not None and held.id == job.id, "claim takes the oldest open job")
            async with other_worker.claim() as next_held:
                ok(next_held is not None and next_held.id == second.id,
                   "a second connection skips the held job")
        async with other_worker.claim() as again:
            ok(again is not None and again.id == job.id, "the hold ends with the block")

        document = job.documents[0].model_copy(update={
            "status": DocumentStatus.VERIFIED, "doc_type": "price_list", "dropped_pages": [2],
            "rounds": 1, "usage": {"pick": Usage(calls=2, cost=0.01)}, "cost_usd": 0.0123,
            "started_at": datetime.now(UTC), "filename": "renamed.pdf"})
        await store.update_document(document)
        stored = (await store.get(job.id)).documents[0]
        ok(stored.status is DocumentStatus.VERIFIED and stored.doc_type == "price_list",
           "document status and type saved")
        ok(stored.usage["pick"].calls == 2 and stored.cost_usd == 0.0123, "usage and cost saved")
        ok(stored.filename == "prices.pdf", "upload facts never rewritten")
        ok(await store.documents_started_since(datetime.now(UTC) - timedelta(minutes=1)) >= 1,
           "documents started today are counted")

        await store.add_event(JobEvent(job_id=job.id, actor="agent", action="unbrand",
                                       result="ok", detail={"cost": 0.01}))
        events = await store.events(job.id)
        ok(len(events) == 1 and events[0].detail == {"cost": 0.01} and events[0].at,
           "event written and read back")

        await store.set_status(job.id, JobStatus.FILED_PRIVATE)
        ended = await store.get(job.id)
        ok(ended.ended_at is not None, "ended_at stamped on FILED_PRIVATE")
        ok(job.id in await store.ended_before(datetime.now(UTC) + timedelta(seconds=1)),
           "ended job listed for eviction")
        async with store.claim() as held:
            ok(held is None or held.id != job.id, "an ended job is never claimed")

        await store.set_status(second.id, JobStatus.FAILED, error="check_jobs")
        ok(await store.healthy(), "healthy")
    finally:
        await store.aclose()
        await other_worker.aclose()
    print(f"\n{'PASS' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

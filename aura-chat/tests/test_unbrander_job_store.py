"""The fake job store keeps the real store's rules, so the worker's tests mean
something. The real one is checked by hand: scripts/check_jobs.py."""

from app.capabilities.unbrander.domain import JobStatus, NewDocument, NewJob
from app.domain import Organization
from tests.fakes import FakeJobStore


def new_job(project: str = "SouthCal") -> NewJob:
    return NewJob(uploader="admin", project=project, builder="Arista Homes", city="Vaughan",
                  organization=Organization(), dry_run=True,
                  documents=[NewDocument(filename="prices.pdf", sha256="a", page_count=2),
                             NewDocument(filename="plans.pdf", sha256="b", page_count=9)])


async def test_a_new_job_is_received_with_its_documents_pending_in_upload_order():
    job = await FakeJobStore().create(new_job())
    assert job.status is JobStatus.RECEIVED
    assert [(d.position, d.filename, d.status.value) for d in job.documents] == [
        (1, "prices.pdf", "PENDING"), (2, "plans.pdf", "PENDING")]


async def test_a_held_job_is_not_handed_out_twice():
    store = FakeJobStore()
    first = await store.create(new_job("First"))
    second = await store.create(new_job("Second"))
    async with store.claim() as held, store.claim() as next_held, store.claim() as none_left:
        assert (held.id, next_held.id, none_left) == (first.id, second.id, None)
    async with store.claim() as again:
        assert again.id == first.id


async def test_an_ended_job_is_never_claimed_and_carries_when_it_ended():
    store = FakeJobStore()
    job = await store.create(new_job())
    await store.set_status(job.id, JobStatus.FILED_PRIVATE)
    async with store.claim() as held:
        assert held is None
    assert (await store.get(job.id)).ended_at is not None

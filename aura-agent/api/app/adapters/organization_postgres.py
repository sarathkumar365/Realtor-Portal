"""OrganizationStore on Postgres: one row, the profile as JSON."""

import asyncio
from pathlib import Path

import asyncpg

from app.domain import Organization

SCHEMA = Path(__file__).with_name("organization_schema.sql")
# Read once at boot and on each save: two connections are plenty.
POOL_MIN, POOL_MAX = 1, 2
CONNECT_TIMEOUT_S = 5.0


class PostgresOrganizationStore:
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

    async def load(self) -> Organization | None:
        pool = await self._ready()
        profile = await pool.fetchval("SELECT profile FROM organization WHERE id = 1")
        return Organization.model_validate_json(profile) if profile else None

    async def save(self, organization: Organization, *, by: str) -> None:
        pool = await self._ready()
        await pool.execute(
            "INSERT INTO organization (id, profile, updated_by) VALUES (1, $1::jsonb, $2)"
            " ON CONFLICT (id) DO UPDATE SET profile = EXCLUDED.profile,"
            " updated_by = EXCLUDED.updated_by, updated_at = now()",
            organization.model_dump_json(), by,
        )

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

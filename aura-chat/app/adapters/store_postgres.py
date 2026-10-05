"""ConversationStore on Postgres. The only file that imports a database driver."""

import asyncio
import json
import uuid
from pathlib import Path

import asyncpg

SCHEMA = Path(__file__).with_name("schema.sql")

POOL_MIN, POOL_MAX = 1, 5
CONNECT_TIMEOUT_S = 5.0

MAX_HISTORY = 20


def _new_id() -> str:
    return str(uuid.uuid4())


class PostgresConversationStore:
    """Conversations, messages and feedback."""

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

    async def create(self, *, user: str, title: str, mode: str = "realtor") -> str:
        pool = await self._ready()
        cid = _new_id()
        await pool.execute(
            "INSERT INTO ai_conversations (id, user_id, title, mode) VALUES ($1, $2, $3, $4)",
            cid, user, title[:200], mode,
        )
        return cid

    async def append(
        self,
        *,
        conversation_id: str,
        role: str,
        message: str,
        sources: list[dict] | None = None,
    ) -> str:
        pool = await self._ready()
        mid = _new_id()
        async with pool.acquire() as con, con.transaction():
            await con.execute(
                "INSERT INTO ai_messages (id, conversation_id, role, message, sources)"
                " VALUES ($1, $2, $3, $4, $5::jsonb)",
                mid, conversation_id, role, message, json.dumps(sources or []),
            )
            await con.execute(
                "UPDATE ai_conversations SET updated_at = now() WHERE id = $1", conversation_id
            )
        return mid

    async def history(
        self, *, conversation_id: str, user: str, limit: int = MAX_HISTORY
    ) -> list[dict]:
        """The last `limit` turns, oldest first."""
        pool = await self._ready()
        rows = await pool.fetch(
            "SELECT m.id, m.role, m.message, m.sources, m.created_at FROM ai_messages m"
            " JOIN ai_conversations c ON c.id = m.conversation_id"
            " WHERE m.conversation_id = $1 AND c.user_id = $2"
            " ORDER BY m.created_at DESC, m.id DESC LIMIT $3",
            conversation_id, user, max(1, limit),
        )
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "message": r["message"],
                "sources": json.loads(r["sources"] or "[]"),
                "created_at": r["created_at"].isoformat(),
            }
            for r in reversed(rows)
        ]

    async def list_for(self, *, user: str, limit: int = 30) -> list[dict]:
        pool = await self._ready()
        rows = await pool.fetch(
            "SELECT id, title, mode, updated_at FROM ai_conversations"
            " WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2",
            user, min(limit, 100),
        )
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "mode": r["mode"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]

    async def meta(self, *, conversation_id: str, user: str) -> dict | None:
        """The thread's own row, or None if it is not this realtor's."""
        pool = await self._ready()
        row = await pool.fetchrow(
            "SELECT id, title, mode, updated_at FROM ai_conversations"
            " WHERE id = $1 AND user_id = $2",
            conversation_id, user,
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "mode": row["mode"],
            "updated_at": row["updated_at"].isoformat(),
        }

    async def set_mode(self, *, conversation_id: str, user: str, mode: str) -> None:
        """Follow the mode a continued thread is actually being held in."""
        pool = await self._ready()
        await pool.execute(
            "UPDATE ai_conversations SET mode = $3 WHERE id = $1 AND user_id = $2",
            conversation_id, user, mode,
        )

    async def record_feedback(self, *, user: str, entry: dict) -> None:
        """One report, one row."""
        pool = await self._ready()
        await pool.execute(
            "INSERT INTO feedback (id, message_id, user_id, question, verdict, category,"
            " note, project_ids) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)",
            _new_id(),
            entry.get("answer_id"),
            user,
            entry.get("question", ""),
            entry.get("verdict"),
            entry.get("category"),
            entry.get("note", ""),
            json.dumps(entry.get("project_ids") or []),
        )

    async def list_feedback(self, *, limit: int = 100) -> list[dict]:
        """The review queue. No user filter: this is for whoever owns the data,
        and the route above it is what gates who may ask."""
        pool = await self._ready()
        rows = await pool.fetch(
            "SELECT id, message_id, user_id, question, verdict, category, note,"
            " project_ids, created_at FROM feedback ORDER BY created_at DESC LIMIT $1",
            min(limit, 500),
        )
        return [
            {
                **{k: r[k] for k in
                   ("id", "message_id", "user_id", "question", "verdict", "category", "note")},
                "project_ids": json.loads(r["project_ids"] or "[]"),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    async def healthy(self) -> bool:
        try:
            pool = await self._ready()
            return await pool.fetchval("SELECT 1") == 1
        except Exception:
            return False

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

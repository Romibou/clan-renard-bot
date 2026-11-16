"""Stockage des annonces : brouillons, modèles, images, programmées, historique."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from bot.features.announcements.model import normalize_draft

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS announcement_drafts (
        guild_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        data JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS announcement_templates (
        id BIGSERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        name VARCHAR(80) NOT NULL,
        data JSONB NOT NULL,
        created_by BIGINT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (guild_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS announcement_images (
        id BIGSERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        filename VARCHAR(120) NOT NULL,
        content_type VARCHAR(80),
        data BYTEA NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS announcement_scheduled (
        id BIGSERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        data JSONB NOT NULL,
        send_at TIMESTAMPTZ NOT NULL,
        created_by BIGINT NOT NULL,
        status VARCHAR(12) NOT NULL DEFAULT 'pending',
        message_id BIGINT,
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS announcement_scheduled_pending_idx
    ON announcement_scheduled (send_at)
    WHERE status = 'pending'
    """,
    """
    CREATE TABLE IF NOT EXISTS announcement_history (
        id BIGSERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL UNIQUE,
        author_id BIGINT NOT NULL,
        title VARCHAR(120) NOT NULL,
        data JSONB NOT NULL,
        scheduled BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        edited_at TIMESTAMPTZ,
        edited_by BIGINT
    )
    """,
    # Pleine largeur : une longue annonce est publiée en plusieurs messages.
    """
    ALTER TABLE announcement_history
    ADD COLUMN IF NOT EXISTS extra_message_ids BIGINT[] NOT NULL DEFAULT '{}'
    """,
)


def _load(value: Any) -> dict[str, Any]:
    return normalize_draft(json.loads(value) if isinstance(value, str) else value)


def _dump(draft: dict[str, Any]) -> str:
    return json.dumps(draft, ensure_ascii=False)


class AnnouncementRepository:
    def __init__(self, pool_getter) -> None:
        self._pool_getter = pool_getter

    @property
    def pool(self):
        return self._pool_getter()

    async def initialize(self) -> None:
        for statement in SCHEMA:
            await self.pool.execute(statement)

    # -------- brouillons --------

    async def get_draft(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        value = await self.pool.fetchval(
            "SELECT data FROM announcement_drafts WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

        return None if value is None else _load(value)

    async def save_draft(self, guild_id: int, user_id: int, draft: dict[str, Any]) -> None:
        await self.pool.execute(
            """
            INSERT INTO announcement_drafts (guild_id, user_id, data, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
            """,
            guild_id,
            user_id,
            _dump(draft),
        )

    async def delete_draft(self, guild_id: int, user_id: int) -> None:
        await self.pool.execute(
            "DELETE FROM announcement_drafts WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

    # -------- modèles --------

    async def list_templates(self, guild_id: int) -> list[dict[str, Any]]:
        records = await self.pool.fetch(
            """
            SELECT id, name, updated_at
            FROM announcement_templates
            WHERE guild_id = $1
            ORDER BY LOWER(name)
            LIMIT 25
            """,
            guild_id,
        )

        return [dict(record) for record in records]

    async def count_templates(self, guild_id: int) -> int:
        return int(
            await self.pool.fetchval(
                "SELECT COUNT(*) FROM announcement_templates WHERE guild_id = $1",
                guild_id,
            )
            or 0
        )

    async def get_template(self, guild_id: int, template_id: int) -> dict[str, Any] | None:
        value = await self.pool.fetchval(
            "SELECT data FROM announcement_templates WHERE guild_id = $1 AND id = $2",
            guild_id,
            template_id,
        )

        return None if value is None else _load(value)

    async def save_template(
        self, guild_id: int, name: str, draft: dict[str, Any], user_id: int
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO announcement_templates (guild_id, name, data, created_by)
            VALUES ($1, $2, $3::jsonb, $4)
            ON CONFLICT (guild_id, name)
            DO UPDATE SET data = EXCLUDED.data,
                          created_by = EXCLUDED.created_by,
                          updated_at = NOW()
            """,
            guild_id,
            name,
            _dump(draft),
            user_id,
        )

    async def delete_template(self, guild_id: int, template_id: int) -> str | None:
        return await self.pool.fetchval(
            "DELETE FROM announcement_templates WHERE guild_id = $1 AND id = $2 RETURNING name",
            guild_id,
            template_id,
        )

    # -------- images --------

    async def add_image(
        self, guild_id: int, filename: str, content_type: str | None, data: bytes
    ) -> int:
        return int(
            await self.pool.fetchval(
                """
                INSERT INTO announcement_images (guild_id, filename, content_type, data)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                guild_id,
                filename[:120],
                content_type,
                data,
            )
        )

    async def get_images(self, guild_id: int, ids: set[int]) -> dict[int, tuple[str, bytes]]:
        if not ids:
            return {}

        records = await self.pool.fetch(
            """
            SELECT id, filename, data
            FROM announcement_images
            WHERE guild_id = $1 AND id = ANY($2::bigint[])
            """,
            guild_id,
            list(ids),
        )

        return {int(r["id"]): (r["filename"], bytes(r["data"])) for r in records}

    async def get_image_names(self, guild_id: int, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}

        records = await self.pool.fetch(
            """
            SELECT id, filename
            FROM announcement_images
            WHERE guild_id = $1 AND id = ANY($2::bigint[])
            """,
            guild_id,
            list(ids),
        )

        return {int(r["id"]): r["filename"] for r in records}

    async def delete_orphan_images(self) -> int:
        """Images que plus aucun brouillon, modèle, envoi ou historique n'utilise."""
        result = await self.pool.execute(
            """
            DELETE FROM announcement_images AS image
            WHERE image.created_at < NOW() - INTERVAL '2 days'
              AND NOT EXISTS (
                SELECT 1 FROM announcement_drafts AS d
                WHERE d.data::text LIKE '%"upload:' || image.id || '"%'
              )
              AND NOT EXISTS (
                SELECT 1 FROM announcement_templates AS t
                WHERE t.data::text LIKE '%"upload:' || image.id || '"%'
              )
              AND NOT EXISTS (
                SELECT 1 FROM announcement_scheduled AS s
                WHERE s.status = 'pending'
                  AND s.data::text LIKE '%"upload:' || image.id || '"%'
              )
              AND NOT EXISTS (
                SELECT 1 FROM announcement_history AS h
                WHERE h.data::text LIKE '%"upload:' || image.id || '"%'
              )
            """
        )

        try:
            return int(str(result).rsplit(" ", 1)[-1])
        except ValueError:
            return 0

    # -------- programmées --------

    async def schedule(
        self,
        guild_id: int,
        channel_id: int,
        draft: dict[str, Any],
        send_at: datetime,
        user_id: int,
    ) -> int:
        return int(
            await self.pool.fetchval(
                """
                INSERT INTO announcement_scheduled
                    (guild_id, channel_id, data, send_at, created_by)
                VALUES ($1, $2, $3::jsonb, $4, $5)
                RETURNING id
                """,
                guild_id,
                channel_id,
                _dump(draft),
                send_at,
                user_id,
            )
        )

    async def list_scheduled(self, guild_id: int) -> list[dict[str, Any]]:
        records = await self.pool.fetch(
            """
            SELECT id, channel_id, data, send_at, created_by
            FROM announcement_scheduled
            WHERE guild_id = $1 AND status = 'pending'
            ORDER BY send_at
            LIMIT 25
            """,
            guild_id,
        )

        return [{**dict(r), "data": _load(r["data"])} for r in records]

    async def cancel_scheduled(self, guild_id: int, scheduled_id: int) -> dict[str, Any] | None:
        record = await self.pool.fetchrow(
            """
            UPDATE announcement_scheduled
            SET status = 'cancelled'
            WHERE guild_id = $1 AND id = $2 AND status = 'pending'
            RETURNING id, channel_id, data, send_at
            """,
            guild_id,
            scheduled_id,
        )

        return None if record is None else {**dict(record), "data": _load(record["data"])}

    async def claim_due(self) -> list[dict[str, Any]]:
        """Réserve les annonces à envoyer (une seule fois, même en cas de doublon)."""
        records = await self.pool.fetch(
            """
            UPDATE announcement_scheduled
            SET status = 'sending'
            WHERE status = 'pending' AND send_at <= NOW()
            RETURNING *
            """
        )

        return [{**dict(r), "data": _load(r["data"])} for r in records]

    async def finish_scheduled(
        self, scheduled_id: int, *, message_id: int | None, error: str | None
    ) -> None:
        await self.pool.execute(
            """
            UPDATE announcement_scheduled
            SET status = $2, message_id = $3, error = $4
            WHERE id = $1
            """,
            scheduled_id,
            "sent" if error is None else "failed",
            message_id,
            error,
        )

    async def recover_stuck(self) -> None:
        """Au démarrage : un envoi interrompu par un redémarrage est relancé."""
        await self.pool.execute(
            """
            UPDATE announcement_scheduled
            SET status = 'pending'
            WHERE status = 'sending'
            """
        )

    # -------- historique --------

    async def record_published(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        author_id: int,
        title: str,
        draft: dict[str, Any],
        *,
        scheduled: bool = False,
        extra_ids: list[int] | tuple[int, ...] = (),
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO announcement_history
                (guild_id, channel_id, message_id, author_id, title, data, scheduled,
                 extra_message_ids)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8::bigint[])
            ON CONFLICT (message_id) DO NOTHING
            """,
            guild_id,
            channel_id,
            message_id,
            author_id,
            title[:120],
            _dump(draft),
            scheduled,
            list(extra_ids),
        )

    async def record_edited(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        title: str,
        draft: dict[str, Any],
        extra_ids: list[int] | tuple[int, ...] = (),
    ) -> None:
        await self.pool.execute(
            """
            INSERT INTO announcement_history
                (guild_id, channel_id, message_id, author_id, title, data,
                 edited_at, edited_by, extra_message_ids)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW(), $4, $7::bigint[])
            ON CONFLICT (message_id)
            DO UPDATE SET title = EXCLUDED.title,
                          data = EXCLUDED.data,
                          edited_at = NOW(),
                          edited_by = EXCLUDED.edited_by,
                          extra_message_ids = EXCLUDED.extra_message_ids
            """,
            guild_id,
            channel_id,
            message_id,
            user_id,
            title[:120],
            _dump(draft),
            list(extra_ids),
        )

    async def find_published(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        """Retrouve une annonce par son message, ou par l'un de ses morceaux."""
        record = await self.pool.fetchrow(
            """
            SELECT message_id, channel_id, extra_message_ids, data
            FROM announcement_history
            WHERE guild_id = $1
              AND (message_id = $2 OR $2 = ANY(extra_message_ids))
            """,
            guild_id,
            message_id,
        )

        if record is None:
            return None

        return {
            "message_id": int(record["message_id"]),
            "channel_id": int(record["channel_id"]),
            "extra_ids": [int(value) for value in record["extra_message_ids"] or []],
            "data": _load(record["data"]),
        }

    async def get_published(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        value = await self.pool.fetchval(
            "SELECT data FROM announcement_history WHERE guild_id = $1 AND message_id = $2",
            guild_id,
            message_id,
        )

        return None if value is None else _load(value)

    async def list_history(self, guild_id: int, limit: int = 15) -> list[dict[str, Any]]:
        records = await self.pool.fetch(
            """
            SELECT channel_id, message_id, author_id, title, scheduled,
                   created_at, edited_at, edited_by
            FROM announcement_history
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            guild_id,
            limit,
        )

        return [dict(r) for r in records]

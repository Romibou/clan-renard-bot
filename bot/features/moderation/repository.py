"""Accès à la base de données de la modération."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from bot.features.moderation.core import (
    BAN,
    DEFAULT_ESCALATION,
    DEFAULT_WARN_EXPIRY_DAYS,
    WARN,
    parse_escalation,
    steps_to_json,
    utc_now,
)

DEFAULT_AUTOMOD: dict[str, Any] = {
    "invites": False,
    "mention_limit": 0,
    "words": [],
    "spam_messages": 0,
    "spam_seconds": 8,
    "spam_mute_minutes": 10,
}


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default

    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default

    return value


class ModerationRepository:
    def __init__(self, database: Any) -> None:
        self.database = database

    @property
    def pool(self):
        return self.database.require_pool()

    async def initialize(self) -> None:
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS mod_settings (
                guild_id BIGINT PRIMARY KEY,
                log_channel_id BIGINT,
                appeal_channel_id BIGINT,
                warn_expiry_days INTEGER NOT NULL DEFAULT 30
                    CHECK (warn_expiry_days BETWEEN 1 AND 3650),
                escalation JSONB,
                automod JSONB NOT NULL DEFAULT '{}'::JSONB,
                automod_rule_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS mod_cases (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                moderator_id BIGINT,
                action VARCHAR(20) NOT NULL,
                reason VARCHAR(500),
                duration_seconds BIGINT,
                expires_at TIMESTAMPTZ,
                amount BIGINT,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                revoked_at TIMESTAMPTZ,
                revoked_by BIGINT,
                revoke_reason VARCHAR(500),
                appeal_status VARCHAR(20),
                appeal_text VARCHAR(1000),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await self.pool.execute(
            """
            CREATE INDEX IF NOT EXISTS mod_cases_member_idx
            ON mod_cases (guild_id, user_id, created_at DESC)
            """
        )
        await self.pool.execute(
            """
            CREATE INDEX IF NOT EXISTS mod_cases_tempban_idx
            ON mod_cases (expires_at)
            WHERE action = 'ban' AND active = TRUE
            """
        )
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS mod_notes (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                author_id BIGINT NOT NULL,
                content VARCHAR(500) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    # ------------------------------------------------------------
    # Réglages
    # ------------------------------------------------------------

    async def get_settings(self, guild_id: int) -> dict[str, Any]:
        record = await self.pool.fetchrow(
            "SELECT * FROM mod_settings WHERE guild_id = $1",
            guild_id,
        )

        escalation = (
            _json(record["escalation"], None) if record is not None else None
        )

        if escalation is None:
            escalation = steps_to_json(parse_escalation(DEFAULT_ESCALATION))

        automod = dict(DEFAULT_AUTOMOD)

        if record is not None:
            automod.update(_json(record["automod"], {}))

        return {
            "log_channel_id": record["log_channel_id"] if record else None,
            "appeal_channel_id": record["appeal_channel_id"] if record else None,
            "warn_expiry_days": (
                int(record["warn_expiry_days"])
                if record
                else DEFAULT_WARN_EXPIRY_DAYS
            ),
            "escalation": escalation,
            "automod": automod,
            "automod_rule_ids": (
                _json(record["automod_rule_ids"], {}) if record else {}
            ),
        }

    async def update_settings(self, guild_id: int, **values: Any) -> None:
        allowed = {
            "log_channel_id",
            "appeal_channel_id",
            "warn_expiry_days",
            "escalation",
            "automod",
            "automod_rule_ids",
        }
        assert set(values) <= allowed

        await self.pool.execute(
            "INSERT INTO mod_settings (guild_id) VALUES ($1) "
            "ON CONFLICT (guild_id) DO NOTHING",
            guild_id,
        )

        for column, value in values.items():
            if column in {"escalation", "automod", "automod_rule_ids"}:
                value = json.dumps(value, ensure_ascii=False)
                placeholder = "$2::JSONB"
            else:
                placeholder = "$2"

            await self.pool.execute(
                f"UPDATE mod_settings SET {column} = {placeholder}, "
                "updated_at = NOW() WHERE guild_id = $1",
                guild_id,
                value,
            )

    # ------------------------------------------------------------
    # Sanctions
    # ------------------------------------------------------------

    async def create_case(
        self,
        *,
        guild_id: int,
        user_id: int,
        moderator_id: int | None,
        action: str,
        reason: str | None,
        duration: timedelta | None = None,
        amount: int | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        now = utc_now()
        record = await self.pool.fetchrow(
            """
            INSERT INTO mod_cases (
                guild_id, user_id, moderator_id, action, reason,
                duration_seconds, expires_at, amount, active, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            guild_id,
            user_id,
            moderator_id,
            action,
            (reason or "")[:500] or None,
            int(duration.total_seconds()) if duration else None,
            now + duration if duration else None,
            amount,
            active,
            now,
        )

        return dict(record)

    async def get_case(self, case_id: int) -> dict[str, Any] | None:
        record = await self.pool.fetchrow(
            "SELECT * FROM mod_cases WHERE id = $1",
            case_id,
        )

        return dict(record) if record is not None else None

    async def revoke_case(
        self,
        case_id: int,
        *,
        revoked_by: int | None,
        reason: str,
    ) -> dict[str, Any] | None:
        """Annule une sanction encore active. None si déjà annulée."""
        record = await self.pool.fetchrow(
            """
            UPDATE mod_cases
            SET
                active = FALSE,
                revoked_at = NOW(),
                revoked_by = $2,
                revoke_reason = $3
            WHERE id = $1
              AND revoked_at IS NULL
            RETURNING *
            """,
            case_id,
            revoked_by,
            reason[:500],
        )

        return dict(record) if record is not None else None

    async def close_case(self, case_id: int) -> None:
        """Fin normale d'une sanction (fin d'un bannissement temporaire)."""
        await self.pool.execute(
            "UPDATE mod_cases SET active = FALSE WHERE id = $1",
            case_id,
        )

    async def member_cases(
        self,
        guild_id: int,
        user_id: int,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        records = await self.pool.fetch(
            """
            SELECT *
            FROM mod_cases
            WHERE guild_id = $1
              AND user_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
        )

        return [dict(record) for record in records]

    async def count_by_action(
        self,
        guild_id: int,
        user_id: int,
    ) -> dict[str, int]:
        records = await self.pool.fetch(
            """
            SELECT action, COUNT(*) AS total
            FROM mod_cases
            WHERE guild_id = $1
              AND user_id = $2
              AND revoked_at IS NULL
            GROUP BY action
            """,
            guild_id,
            user_id,
        )

        return {str(row["action"]): int(row["total"]) for row in records}

    async def active_warn_count(
        self,
        guild_id: int,
        user_id: int,
        expiry_days: int,
        now: datetime | None = None,
    ) -> int:
        since = (now or utc_now()) - timedelta(days=expiry_days)

        return int(
            await self.pool.fetchval(
                """
                SELECT COUNT(*)
                FROM mod_cases
                WHERE guild_id = $1
                  AND user_id = $2
                  AND action = $3
                  AND revoked_at IS NULL
                  AND created_at >= $4
                """,
                guild_id,
                user_id,
                WARN,
                since,
            )
            or 0
        )

    async def latest_active_case(
        self,
        guild_id: int,
        user_id: int,
        action: str,
    ) -> dict[str, Any] | None:
        record = await self.pool.fetchrow(
            """
            SELECT *
            FROM mod_cases
            WHERE guild_id = $1
              AND user_id = $2
              AND action = $3
              AND active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            guild_id,
            user_id,
            action,
        )

        return dict(record) if record is not None else None

    async def expired_tempbans(self) -> list[dict[str, Any]]:
        records = await self.pool.fetch(
            """
            SELECT *
            FROM mod_cases
            WHERE action = $1
              AND active = TRUE
              AND expires_at IS NOT NULL
              AND expires_at <= NOW()
            """,
            BAN,
        )

        return [dict(record) for record in records]

    async def set_appeal(
        self,
        case_id: int,
        *,
        status: str,
        text: str | None = None,
        only_if_status: str | None = None,
    ) -> bool:
        """Met à jour la contestation. Retourne False si l'état a changé entre-temps."""
        result = await self.pool.execute(
            """
            UPDATE mod_cases
            SET
                appeal_status = $2,
                appeal_text = COALESCE($3, appeal_text)
            WHERE id = $1
              AND appeal_status IS NOT DISTINCT FROM $4
            """,
            case_id,
            status,
            text,
            only_if_status,
        )

        return result != "UPDATE 0"

    # ------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------

    async def add_note(
        self,
        guild_id: int,
        user_id: int,
        author_id: int,
        content: str,
    ) -> int:
        return int(
            await self.pool.fetchval(
                """
                INSERT INTO mod_notes (guild_id, user_id, author_id, content)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                guild_id,
                user_id,
                author_id,
                content[:500],
            )
        )

    async def member_notes(
        self,
        guild_id: int,
        user_id: int,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        records = await self.pool.fetch(
            """
            SELECT *
            FROM mod_notes
            WHERE guild_id = $1
              AND user_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            guild_id,
            user_id,
            limit,
        )

        return [dict(record) for record in records]

    async def delete_note(self, guild_id: int, note_id: int) -> bool:
        result = await self.pool.execute(
            "DELETE FROM mod_notes WHERE guild_id = $1 AND id = $2",
            guild_id,
            note_id,
        )

        return result != "DELETE 0"

    async def delete_case(self, case_id: int) -> None:
        """Retire un cas créé pour une action que Discord a refusée."""
        await self.pool.execute("DELETE FROM mod_cases WHERE id = $1", case_id)

    async def set_amount(self, case_id: int, amount: int) -> None:
        await self.pool.execute(
            "UPDATE mod_cases SET amount = $2 WHERE id = $1",
            case_id,
            amount,
        )

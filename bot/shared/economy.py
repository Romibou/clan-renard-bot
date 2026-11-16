from __future__ import annotations

from typing import Any


async def credit_progression(
    database: Any,
    *,
    guild_id: int,
    user_id: int,
    xp: int,
    coins: int,
    transaction_type: str,
    reason: str,
) -> tuple[int, int]:
    """
    Ajoute XP et pièces gagnées à un membre. Retourne (ancienne XP,
    nouvelle XP) pour mettre à jour ses rôles de niveau.

    Les pièces comptent comme de l'argent gagné (total historique,
    statistiques et missions).
    """
    async with database.transaction() as connection:
        await connection.execute(
            """
            SELECT pg_advisory_xact_lock(
                hashtextextended($1, 0)
            )
            """,
            f"progression:{guild_id}:{user_id}",
        )

        await connection.execute(
            """
            INSERT INTO progression_members (
                guild_id,
                user_id
            )
            VALUES ($1, $2)
            ON CONFLICT (guild_id, user_id)
            DO NOTHING
            """,
            guild_id,
            user_id,
        )

        old_xp = int(
            await connection.fetchval(
                """
                SELECT total_xp
                FROM progression_members
                WHERE guild_id = $1
                  AND user_id = $2
                FOR UPDATE
                """,
                guild_id,
                user_id,
            )
            or 0
        )

        await connection.execute(
            """
            UPDATE progression_members
            SET
                total_xp = total_xp + $3,
                wallet = wallet + $4,
                lifetime_coins = lifetime_coins + $4,
                updated_at = NOW()
            WHERE guild_id = $1
              AND user_id = $2
            """,
            guild_id,
            user_id,
            xp,
            coins,
        )

        if coins > 0:
            await connection.execute(
                """
                INSERT INTO progression_transactions (
                    guild_id,
                    user_id,
                    actor_id,
                    amount,
                    transaction_type,
                    reason
                )
                VALUES ($1, $2, NULL, $3, $4, $5)
                """,
                guild_id,
                user_id,
                coins,
                transaction_type,
                reason[:200],
            )

    return old_xp, old_xp + xp


async def refresh_level_roles(
    bot: Any,
    member: Any,
    old_xp: int,
    new_xp: int,
) -> None:
    """Donne le rôle de niveau si le membre a changé de niveau."""
    progression = bot.get_cog("ProgressionCog")

    if progression is None or member is None:
        return

    from bot.extensions.progression import level_from_xp

    if level_from_xp(new_xp) != level_from_xp(old_xp):
        await progression.grant_earned_level_roles(
            member,
            level_from_xp(new_xp),
        )

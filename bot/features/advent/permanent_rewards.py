from __future__ import annotations

import logging
import discord
from discord.ext import commands

from bot.features.advent.constants import (
    REWARD_COINS,
    REWARD_COSMETIC,
    REWARD_XP,
)
from bot.features.advent.models import AdventOpening
from bot.features.advent.service import AdventService
from bot.shared.economy import credit_progression, refresh_level_roles

logger = logging.getLogger(__name__)

# Récompenses de case versées dans les systèmes permanents du bot
# (portefeuille, XP, inventaire de profil) plutôt qu'en points d'Avent.
PERMANENT_REWARD_TYPES = {
    REWARD_COINS,
    REWARD_XP,
    REWARD_COSMETIC,
}


async def deliver_permanent_reward(
    *,
    bot: commands.Bot,
    guild: discord.Guild,
    member: discord.Member | None,
    user_id: int,
    opening: AdventOpening,
    service: AdventService,
) -> tuple[bool, str | None]:
    """
    Verse une récompense de type pièces, XP ou cosmétique.

    L'ouverture est déjà enregistrée : en cas d'échec, elle est marquée
    « failed » (visible par les admins) et le membre est prévenu.
    """
    snapshot = opening.reward_snapshot

    try:
        if opening.reward_type in (REWARD_COINS, REWARD_XP):
            old_xp, new_xp = await credit_progression(
                bot.database,  # type: ignore[attr-defined]
                guild_id=guild.id,
                user_id=user_id,
                xp=int(snapshot.get("xp", 0) or 0),
                coins=int(snapshot.get("coins", 0) or 0),
                transaction_type="advent_reward",
                reason=f"Calendrier de l'Avent — case {opening.day}",
            )

            await refresh_level_roles(bot, member, old_xp, new_xp)

        elif opening.reward_type == REWARD_COSMETIC:
            profile = bot.get_cog("ProfileCog")

            if profile is None:
                raise RuntimeError("Le module des profils est indisponible.")

            await profile.grant_cosmetic(
                guild_id=guild.id,
                user_id=user_id,
                cosmetic_id=int(snapshot["cosmetic_id"]),
                source=f"advent:{opening.campaign_id}:{opening.day}",
            )

        else:
            return True, None

    except Exception as error:
        logger.exception(
            "Impossible de verser la récompense de la case %s à %s",
            opening.day,
            user_id,
        )

        await service.mark_role_result(
            opening_id=opening.id,
            success=False,
            error=str(error)[:500],
        )

        return False, (
            "Elle n'a pas pu être créditée automatiquement. "
            "Préviens un administrateur."
        )

    await service.mark_role_result(
        opening_id=opening.id,
        success=True,
    )

    return True, None

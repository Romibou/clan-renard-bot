from __future__ import annotations

import logging

import discord

from bot.features.advent.models import OpenResult
from bot.features.advent.service import AdventService


logger = logging.getLogger(__name__)


async def grant_role_reward(
    *,
    guild: discord.Guild,
    member: discord.Member,
    result: OpenResult,
    service: AdventService,
) -> tuple[bool, str | None]:
    """
    Attribue un rôle gagné dans le calendrier.

    Le gain a déjà été enregistré dans PostgreSQL avant cette étape.
    Une erreur Discord ne provoque donc jamais un nouveau tirage.
    """
    role_id = result.role_id

    if role_id is None:
        return True, None

    role = guild.get_role(role_id)

    if role is None:
        error = (
            "Le rôle de récompense n'existe plus "
            f"sur le serveur (identifiant {role_id})."
        )
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=False,
            error=error,
        )
        return False, error

    bot_member = guild.me

    if bot_member is None:
        error = (
            "Le bot n'a pas pu retrouver son propre membre "
            "sur le serveur."
        )
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=False,
            error=error,
        )
        return False, error

    if not bot_member.guild_permissions.manage_roles:
        error = (
            "Le bot ne possède pas la permission "
            "« Gérer les rôles »."
        )
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=False,
            error=error,
        )
        return False, error

    if role >= bot_member.top_role:
        error = (
            "Le rôle gagné est placé au-dessus du rôle du bot. "
            "Place le rôle de Clan Renard plus haut dans la "
            "hiérarchie Discord."
        )
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=False,
            error=error,
        )
        return False, error

    if role in member.roles:
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=True,
        )
        return True, None

    try:
        await member.add_roles(
            role,
            reason=(
                "Récompense du calendrier de l'Avent "
                f"— jour {result.opening.day}"
            ),
        )
    except discord.Forbidden:
        error = (
            "Discord a refusé l'attribution du rôle. "
            "Vérifie les permissions et la hiérarchie."
        )
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=False,
            error=error,
        )
        return False, error
    except discord.HTTPException as exception:
        error = (
            "Discord a rencontré une erreur temporaire pendant "
            "l'attribution du rôle."
        )
        logger.warning(
            "Échec HTTP pendant l'attribution du rôle %s "
            "au membre %s : %s",
            role.id,
            member.id,
            exception,
        )
        await service.mark_role_result(
            opening_id=result.opening.id,
            success=False,
            error=str(exception)[:500],
        )
        return False, error

    await service.mark_role_result(
        opening_id=result.opening.id,
        success=True,
    )
    return True, None

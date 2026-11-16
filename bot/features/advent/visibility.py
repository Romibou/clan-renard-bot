"""
Visibilité de la commande /avent dans Discord.

Campagne désactivée dans /avent-admin → /avent est réservée aux
administrateurs : les membres ne la voient plus dans la liste des
commandes. Campagne activée → tout le monde la voit.

Discord ne permet pas à un bot de masquer une commande à certains
membres seulement ; on change donc la permission par défaut de la
commande, puis on renvoie la liste des commandes à Discord.
"""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

ADVENT_COMMAND = "avent"
HIDDEN_PERMISSIONS = discord.Permissions(administrator=True)


def apply_visibility(bot: commands.Bot, visible: bool) -> bool:
    """
    Règle la permission par défaut de /avent dans l'arbre local.
    Retourne True si elle a changé (il faut alors resynchroniser).
    """
    command = bot.tree.get_command(ADVENT_COMMAND)

    if command is None:
        return False

    wanted = None if visible else HIDDEN_PERMISSIONS
    current = command.default_permissions

    if (current is None and wanted is None) or (
        current is not None and wanted is not None and current.value == wanted.value
    ):
        return False

    command.default_permissions = wanted
    return True


async def any_campaign_enabled(repository: Any) -> bool:
    """Le bot ne sert qu'un serveur : une campagne activée suffit."""
    return bool(await repository.get_enabled_campaigns())


async def update_visibility(
    bot: commands.Bot,
    repository: Any,
) -> bool:
    """
    Met /avent en cohérence avec l'état des campagnes et prévient
    Discord si besoin. Retourne True si une mise à jour a été envoyée.
    """
    visible = await any_campaign_enabled(repository)

    if not apply_visibility(bot, visible):
        return False

    sync = getattr(bot, "_sync_application_commands", None)

    if sync is None:
        return False

    try:
        await sync()
    except discord.HTTPException:
        LOGGER.exception("Impossible de mettre à jour la visibilité de /avent")
        return False

    LOGGER.info(
        "/avent est maintenant %s",
        "visible par tous" if visible else "réservée aux administrateurs",
    )
    return True

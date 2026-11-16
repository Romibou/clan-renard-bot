from __future__ import annotations

from types import SimpleNamespace

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.advent.visibility import (
    HIDDEN_PERMISSIONS,
    apply_visibility,
    update_visibility,
)


def make_bot() -> commands.Bot:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())

    async def avent(interaction: discord.Interaction) -> None:
        return None

    bot.tree.add_command(
        app_commands.Command(name="avent", description="Calendrier", callback=avent)
    )
    return bot


def test_apply_visibility_toggles_the_default_permission() -> None:
    bot = make_bot()
    command = bot.tree.get_command("avent")

    assert apply_visibility(bot, visible=False) is True
    assert command.default_permissions.value == HIDDEN_PERMISSIONS.value

    # Même état demandé deux fois : rien à envoyer à Discord.
    assert apply_visibility(bot, visible=False) is False

    assert apply_visibility(bot, visible=True) is True
    assert command.default_permissions is None


async def test_update_visibility_syncs_only_when_needed() -> None:
    bot = make_bot()
    syncs: list[int] = []

    async def sync() -> None:
        syncs.append(1)

    bot._sync_application_commands = sync  # type: ignore[attr-defined]
    campaigns: list[object] = []

    async def get_enabled_campaigns() -> list[object]:
        return campaigns

    repository = SimpleNamespace(get_enabled_campaigns=get_enabled_campaigns)

    # Aucune campagne activée → /avent cachée, une synchronisation.
    assert await update_visibility(bot, repository) is True
    assert bot.tree.get_command("avent").default_permissions is not None
    assert len(syncs) == 1

    # Rien n'a changé → pas de nouvel envoi à Discord.
    assert await update_visibility(bot, repository) is False
    assert len(syncs) == 1

    # Campagne activée → /avent visible par tous.
    campaigns.append(object())
    assert await update_visibility(bot, repository) is True
    assert bot.tree.get_command("avent").default_permissions is None
    assert len(syncs) == 2

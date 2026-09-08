from __future__ import annotations

import discord
from discord import app_commands


def guild_only():
    async def predicate(
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()

        return True

    return app_commands.check(predicate)

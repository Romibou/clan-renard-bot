"""/ping : le bot répond-il, et à quelle vitesse ?"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

STARTED_AT = datetime.now(timezone.utc)


def rate(ms: float) -> str:
    if ms < 150:
        return "🟢"
    if ms < 400:
        return "🟡"
    return "🔴"


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, rest = divmod(seconds, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes = rest // 60

    if days:
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


class PingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def database_latency(self) -> float | None:
        database = getattr(self.bot, "database", None)

        try:
            pool = database.require_pool()
            start = time.perf_counter()
            await pool.fetchval("SELECT 1")
            return (time.perf_counter() - start) * 1000
        except Exception:
            return None

    @app_commands.command(name="ping", description="Vérifie que le bot répond, et à quelle vitesse.")
    async def ping(self, interaction: discord.Interaction) -> None:
        start = time.perf_counter()
        await interaction.response.send_message("🏓 Pong…", ephemeral=True)
        response_ms = (time.perf_counter() - start) * 1000
        gateway_ms = self.bot.latency * 1000
        database_ms = await self.database_latency()
        uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()

        lines = [
            f"{rate(gateway_ms)} **Connexion à Discord** : {gateway_ms:.0f} ms",
            f"{rate(response_ms)} **Temps de réponse** : {response_ms:.0f} ms",
            (
                f"{rate(database_ms)} **Base de données** : {database_ms:.0f} ms"
                if database_ms is not None
                else "🔴 **Base de données** : injoignable"
            ),
            f"⏱️ **En ligne depuis** : {format_uptime(uptime)}",
        ]
        await interaction.edit_original_response(
            content=None,
            embed=discord.Embed(
                title="🏓 Pong !",
                description="\n".join(lines),
                color=discord.Color.from_rgb(242, 140, 40),
            ),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PingCog(bot))
    LOGGER.info("Commande /ping chargée")

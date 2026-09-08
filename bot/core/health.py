from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from bot.core.bot import ClanRenardBot


logger = logging.getLogger(__name__)


class HealthServer:
    """
    Petit serveur HTTP utilisé par Render.

    Le bot Discord reste le programme principal. Le serveur web sert
    uniquement à répondre aux contrôles / et /health de Render.
    """

    def __init__(
        self,
        bot: "ClanRenardBot",
        port: int,
    ) -> None:
        self.bot = bot
        self.port = port
        self.runner: web.AppRunner | None = None

    async def root(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": "Clan Renard Bot",
                "status": "running",
            }
        )

    async def health(self, request: web.Request) -> web.Response:
        database_ok = await self.bot.database.ping()
        discord_ready = self.bot.is_ready()

        status = 200 if database_ok else 503

        return web.json_response(
            {
                "status": "ok" if status == 200 else "degraded",
                "discord_ready": discord_ready,
                "database_ready": database_ok,
                "latency_ms": (
                    round(self.bot.latency * 1000)
                    if discord_ready
                    else None
                ),
            },
            status=status,
        )

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self.root)
        app.router.add_get("/health", self.health)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        site = web.TCPSite(
            self.runner,
            host="0.0.0.0",
            port=self.port,
        )
        await site.start()

        logger.info(
            "Serveur de santé disponible sur le port %s",
            self.port,
        )

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
            logger.info("Serveur de santé arrêté")

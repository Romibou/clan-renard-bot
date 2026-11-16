from __future__ import annotations

import asyncio
import logging
import sys

import discord

from bot.core.bot import ClanRenardBot
from bot.core.config import Settings, SettingsError
from bot.core.logging_config import configure_logging


async def run_bot() -> None:
    settings = Settings.from_environment()
    configure_logging(settings.log_level)

    logger = logging.getLogger("clan_renard")
    logger.info("Démarrage de Clan Renard Bot")

    bot = ClanRenardBot(settings)

    try:
        try:
            async with bot:
                await bot.start(settings.discord_token)
        except discord.PrivilegedIntentsRequired:
            # « Message Content Intent » n'est pas activé sur le
            # Developer Portal : on redémarre sans lire les messages
            # plutôt que de laisser le bot hors ligne.
            logger.error(
                "Message Content Intent n'est pas activé sur le Discord "
                "Developer Portal (Bot → Privileged Gateway Intents). "
                "Redémarrage sans lecture des messages : le bingo passe "
                "par le bouton « Proposer un nombre »."
            )
            bot = ClanRenardBot(settings, read_messages=False)

            async with bot:
                await bot.start(settings.discord_token)
    finally:
        logger.info("Arrêt de Clan Renard Bot")


def main() -> None:
    try:
        asyncio.run(run_bot())
    except SettingsError as error:
        print(f"Erreur de configuration : {error}", file=sys.stderr)
        raise SystemExit(2) from error
    except KeyboardInterrupt:
        print("Arrêt demandé.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
import pkgutil

from discord.ext import commands

import bot.extensions


logger = logging.getLogger(__name__)


def discover_extensions() -> list[str]:
    """
    Détecte automatiquement les fichiers de bot/extensions/.

    Pour ajouter un module plus tard, il suffira donc de créer par exemple :
    bot/extensions/moderation.py
    """
    discovered: list[str] = []

    for module_info in pkgutil.iter_modules(bot.extensions.__path__):
        module_name = module_info.name

        if module_name.startswith("_"):
            continue

        discovered.append(f"bot.extensions.{module_name}")

    return sorted(discovered)


async def load_extensions(bot: commands.Bot) -> None:
    extensions = discover_extensions()

    if not extensions:
        logger.warning("Aucune extension n'a été trouvée")
        return

    failures: list[tuple[str, Exception]] = []

    for extension in extensions:
        try:
            await bot.load_extension(extension)
            logger.info("Extension chargée : %s", extension)
        except Exception as error:
            failures.append((extension, error))
            logger.exception(
                "Impossible de charger l'extension %s",
                extension,
            )

    if failures:
        failed_names = ", ".join(name for name, _ in failures)
        raise RuntimeError(
            f"Certaines extensions n'ont pas pu être chargées : "
            f"{failed_names}"
        )

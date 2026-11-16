"""Chargement du système de modération (voir bot/features/moderation/)."""

from __future__ import annotations

import logging

from discord.ext import commands

from bot.features.moderation.appeals import AppealButton, AppealDecisionButton
from bot.features.moderation.automod import AutomodCog
from bot.features.moderation.cog import ModerationCog
from bot.features.moderation.panel import ModerationPanelCog

LOGGER = logging.getLogger(__name__)


async def setup(bot: commands.Bot) -> None:
    # Boutons des messages privés et du salon des contestations :
    # ils doivent fonctionner après un redémarrage.
    bot.add_dynamic_items(AppealButton, AppealDecisionButton)

    moderation = ModerationCog(bot)
    await moderation.repository.initialize()

    await bot.add_cog(moderation)
    await bot.add_cog(AutomodCog(bot))
    await bot.add_cog(ModerationPanelCog(bot))

    LOGGER.info("Système de modération chargé")

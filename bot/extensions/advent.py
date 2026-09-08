from __future__ import annotations

import logging

from discord.ext import commands

from bot.core.bot import ClanRenardBot
from bot.features.advent.admin_commands import (
    AdventAdminCommands,
)
from bot.features.advent.admin_repository import (
    AdminAdventRepository,
)
from bot.features.advent.admin_rewards_commands import (
    AdventAdminRewardsCommands,
)
from bot.features.advent.commands import AdventCommands
from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.reward_service import RewardService
from bot.features.advent.service import AdventService
from bot.features.advent.tasks import (
    AdventAnnouncementTasks,
)
from bot.features.advent.transaction_repository import (
    AdventTransactionRepository,
)
from bot.features.advent.views import AdventView


logger = logging.getLogger(__name__)


async def setup(bot: commands.Bot) -> None:
    """
    Point d'entrée unique de la fonctionnalité Avent.

    Le chargeur automatique détecte ce fichier et appelle setup().
    Tous les services sont instanciés une seule fois puis partagés
    entre les commandes membres, l'administration et les tâches.
    """
    if not isinstance(bot, ClanRenardBot):
        raise TypeError(
            "L'extension Avent nécessite ClanRenardBot."
        )

    repository = AdminAdventRepository(
        bot.database
    )
    transactions = AdventTransactionRepository(
        bot.database
    )
    reward_service = RewardService()
    image_generator = AdventImageGenerator(
        bot.settings.project_root
    )
    service = AdventService(
        repository=repository,
        transactions=transactions,
        reward_service=reward_service,
        default_timezone=bot.settings.default_timezone,
    )

    # Enregistre les boutons persistants. Les messages contenant ces
    # boutons restent utilisables après un redémarrage de Render.
    bot.add_view(AdventView())

    await bot.add_cog(
        AdventCommands(
            bot,
            service=service,
            image_generator=image_generator,
        )
    )

    await bot.add_cog(
        AdventAdminCommands(
            bot,
            service=service,
            repository=repository,
            transactions=transactions,
            reward_service=reward_service,
            image_generator=image_generator,
        )
    )

    await bot.add_cog(
        AdventAdminRewardsCommands(
            bot,
            service=service,
            repository=repository,
            transactions=transactions,
            reward_service=reward_service,
            image_generator=image_generator,
        )
    )

    await bot.add_cog(
        AdventAnnouncementTasks(
            bot,
            service=service,
            transactions=transactions,
        )
    )

    logger.info(
        "Système du calendrier de l'Avent initialisé"
    )


async def teardown(bot: commands.Bot) -> None:
    """
    Décharge proprement les Cogs lors d'un rechargement manuel.
    """
    for cog_name in (
        "AdventAnnouncementTasks",
        "AdventAdminRewardsCommands",
        "AdventAdminCommands",
        "AdventCommands",
    ):
        await bot.remove_cog(cog_name)

    logger.info(
        "Système du calendrier de l'Avent déchargé"
    )

from __future__ import annotations

import logging

from discord.ext import commands

from bot.core.bot import ClanRenardBot
from bot.features.advent.admin_commands import (
    AdventAdminCommands,
)
from bot.features.advent.admin_panel import (
    AdventAdminPanel,
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


OLD_COMMANDS = (
    # Anciennes commandes membres.
    "avent-ouvrir",
    "avent-profil",
    "avent-recompenses",
    "avent-classement",
    "avent-aide",

    # Anciennes commandes administratives.
    "avent-admin-initialiser",
    "avent-admin-config",
    "avent-admin-activer",
    "avent-admin-canal",
    "avent-admin-fuseau",
    "avent-admin-heure",
    "avent-admin-rattrapage",
    "avent-admin-annonces",
    "avent-admin-recompense-message",
    "avent-admin-recompense-points",
    "avent-admin-recompense-role",
    "avent-admin-recompense-aleatoire",
    "avent-admin-recompenses",
    "avent-admin-recompense-supprimer",
    "avent-admin-apercu",
    "avent-admin-publier",
    "avent-admin-utilisateur",
    "avent-admin-reset-utilisateur",
)


async def setup(
    bot: commands.Bot,
) -> None:
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

    bot.add_view(
        AdventView()
    )

    await bot.add_cog(
        AdventCommands(
            bot,
            service=service,
            image_generator=image_generator,
        )
    )

    # On conserve ces deux Cogs pour que le panneau puisse appeler
    # leurs fonctions. Leurs commandes seront ensuite retirées
    # de l'arbre Discord.
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
        AdventAdminPanel(
            bot
        )
    )

    await bot.add_cog(
        AdventAnnouncementTasks(
            bot,
            service=service,
            transactions=transactions,
        )
    )

    # Les fonctions restent disponibles dans les Cogs,
    # mais les anciennes commandes disparaissent de Discord.
    for command_name in OLD_COMMANDS:
        bot.tree.remove_command(
            command_name
        )

    logger.info(
        "Système du calendrier de l'Avent initialisé"
    )


async def teardown(
    bot: commands.Bot,
) -> None:
    for cog_name in (
        "AdventAnnouncementTasks",
        "AdventAdminPanel",
        "AdventAdminRewardsCommands",
        "AdventAdminCommands",
        "AdventCommands",
    ):
        await bot.remove_cog(
            cog_name
        )

    logger.info(
        "Système du calendrier de l'Avent déchargé"
    )

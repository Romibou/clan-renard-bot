from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from bot.features.advent.announcement_texts import (
    AnnouncementTexts,
    AnnouncementTextsRepository,
    build_announcement,
)
from bot.features.advent.models import AdventCampaign
from bot.features.advent.service import AdventService
from bot.features.advent.transaction_repository import (
    AdventTransactionRepository,
)
from bot.features.advent.views import AdventView


logger = logging.getLogger(__name__)


class AdventAnnouncementTasks(commands.Cog):
    """
    Vérifie périodiquement les campagnes actives.

    Une annonce est publiée une seule fois pour chaque journée.
    PostgreSQL sert de verrou afin que les redémarrages du bot ou
    deux exécutions proches ne produisent pas de doublon.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: AdventService,
        transactions: AdventTransactionRepository,
    ) -> None:
        self.bot = bot
        self.service = service
        self.transactions = transactions
        self.texts = AnnouncementTextsRepository(
            lambda: bot.database.require_pool()
        )

        self.check_announcements.start()

    def cog_unload(self) -> None:
        self.check_announcements.cancel()

    @tasks.loop(minutes=1)
    async def check_announcements(self) -> None:
        try:
            campaigns = (
                await self.service.repository.get_enabled_campaigns()
            )
        except Exception:
            logger.exception(
                "Impossible de charger les campagnes pour "
                "les annonces quotidiennes"
            )
            return

        for campaign in campaigns:
            try:
                await self._process_campaign(campaign)
            except Exception:
                logger.exception(
                    "Échec de l'annonce automatique pour "
                    "la campagne %s du serveur %s",
                    campaign.id,
                    campaign.guild_id,
                )

    @check_announcements.before_loop
    async def before_check_announcements(self) -> None:
        await self.bot.wait_until_ready()

    async def _process_campaign(
        self,
        campaign: AdventCampaign,
    ) -> None:
        if not campaign.announcements_enabled:
            return

        if campaign.channel_id is None:
            return

        current_day = self.service.current_day(campaign)

        if current_day is None:
            return

        already_announced = (
            await self.transactions.announcement_exists(
                campaign.id,
                current_day,
            )
        )

        if already_announced:
            return

        guild = self.bot.get_guild(
            campaign.guild_id
        )

        if guild is None:
            logger.warning(
                "Serveur %s introuvable pour la campagne %s",
                campaign.guild_id,
                campaign.id,
            )
            return

        channel = guild.get_channel(
            campaign.channel_id
        )

        if not isinstance(
            channel,
            (
                discord.TextChannel,
                discord.Thread,
            ),
        ):
            logger.warning(
                "Canal %s introuvable ou incompatible pour "
                "la campagne %s",
                campaign.channel_id,
                campaign.id,
            )
            return

        reserved = (
            await self.transactions.reserve_announcement(
                campaign_id=campaign.id,
                day=current_day,
                channel_id=channel.id,
            )
        )

        if not reserved:
            # Une autre vérification ou instance a réservé l'annonce.
            return

        role = None

        if campaign.announcement_role_id is not None:
            role = guild.get_role(
                campaign.announcement_role_id
            )

        # Textes réglés dans /avent-admin (texte d'origine par défaut).
        try:
            texts = await self.texts.get(campaign.id)
        except Exception:
            logger.exception("Textes d'annonce illisibles : texte d'origine utilisé")
            texts = AnnouncementTexts()

        announcement = build_announcement(
            campaign=campaign,
            day=current_day,
            texts=texts,
            guild_name=guild.name,
            role=role,
        )

        try:
            message = await channel.send(
                **announcement,
                view=AdventView(),
            )
        except discord.HTTPException:
            await self.transactions.cancel_announcement_reservation(
                campaign_id=campaign.id,
                day=current_day,
            )
            raise

        await self.transactions.complete_announcement(
            campaign_id=campaign.id,
            day=current_day,
            message_id=message.id,
        )

        logger.info(
            "Annonce du jour %s publiée pour le serveur %s",
            current_day,
            guild.id,
        )

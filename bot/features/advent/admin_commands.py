from __future__ import annotations

import json
import logging
from datetime import date
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.advent.constants import (
    CATCHUP_DISABLED,
    CATCHUP_ENABLED,
    REWARD_MESSAGE,
    REWARD_POINTS,
    REWARD_RANDOM,
    REWARD_ROLE,
)
from bot.features.advent.discord_calendar import (
    build_calendar_response,
)
from bot.features.advent.exceptions import AdventError
from bot.features.advent.full_repository import (
    FullAdventRepository,
)
from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.reward_service import RewardService
from bot.features.advent.service import AdventService
from bot.features.advent.transaction_repository import (
    AdventTransactionRepository,
)
from bot.features.advent.views import (
    AdventView,
    ConfirmResetView,
)
from bot.shared.dates import validate_timezone
from bot.shared.embeds import (
    base_embed,
    error_embed,
    success_embed,
)


logger = logging.getLogger(__name__)


CatchupChoice = Literal["désactivé", "activé"]


class AdventAdminCommands(commands.Cog):
    """
    Commandes réservées aux administrateurs Discord.

    Le fichier est volontairement structuré en sections :
    - outils internes ;
    - configuration de campagne ;
    - récompenses ;
    - panneau public ;
    - gestion des membres.

    Les opérations dangereuses utilisent une confirmation.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: AdventService,
        repository: FullAdventRepository,
        transactions: AdventTransactionRepository,
        reward_service: RewardService,
        image_generator: AdventImageGenerator,
    ) -> None:
        self.bot = bot
        self.service = service
        self.repository = repository
        self.transactions = transactions
        self.reward_service = reward_service
        self.image_generator = image_generator

    # ----------------------------------------------------
    # OUTILS INTERNES
    # ----------------------------------------------------

    @staticmethod
    async def _guild_required(
        interaction: discord.Interaction,
    ) -> discord.Guild | None:
        guild = interaction.guild

        if guild is not None:
            return guild

        embed = error_embed(
            "Serveur requis",
            (
                "Cette commande administrative doit être utilisée "
                "dans un serveur Discord."
            ),
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

        return None

    @staticmethod
    async def _send_error(
        interaction: discord.Interaction,
        title: str,
        description: str,
    ) -> None:
        embed = error_embed(
            title,
            description,
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

    async def _campaign(
        self,
        guild_id: int,
        year: int | None = None,
    ):
        if year is not None:
            return await self.service.get_campaign_for_year(
                guild_id,
                year,
            )

        return await self.service.get_campaign_for_display(
            guild_id
        )

    async def _audit(
        self,
        interaction: discord.Interaction,
        *,
        campaign_id: int | None,
        action: str,
        details: dict | None = None,
    ) -> None:
        if interaction.guild_id is None:
            return

        try:
            await self.transactions.audit(
                guild_id=interaction.guild_id,
                campaign_id=campaign_id,
                actor_id=interaction.user.id,
                action=action,
                details=details,
            )
        except Exception:
            # Le journal d'audit est important, mais son échec ne doit
            # pas annuler une configuration déjà enregistrée.
            logger.exception(
                "Impossible d'enregistrer l'action d'audit %s",
                action,
            )

    @staticmethod
    def _campaign_embed(
        campaign,
    ) -> discord.Embed:
        enabled_text = (
            "Activée ✅"
            if campaign.enabled
            else "Désactivée ❌"
        )
        catchup_text = (
            "Activé"
            if campaign.catchup_mode == CATCHUP_ENABLED
            else "Désactivé"
        )
        channel_text = (
            f"<#{campaign.channel_id}>"
            if campaign.channel_id is not None
            else "Non configuré"
        )
        role_text = (
            f"<@&{campaign.announcement_role_id}>"
            if campaign.announcement_role_id is not None
            else "Aucun rôle"
        )

        embed = base_embed(
            f"⚙️ Configuration Avent {campaign.year}",
            (
                f"Campagne du serveur pour l'année "
                f"**{campaign.year}**."
            ),
        )

        embed.add_field(
            name="Titre",
            value=campaign.title,
            inline=False,
        )
        embed.add_field(
            name="État",
            value=enabled_text,
            inline=True,
        )
        embed.add_field(
            name="Période",
            value=(
                f"{campaign.start_date.strftime('%d/%m/%Y')}\n"
                f"au {campaign.end_date.strftime('%d/%m/%Y')}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Fuseau",
            value=f"`{campaign.timezone}`",
            inline=True,
        )
        embed.add_field(
            name="Heure d'ouverture",
            value=f"{campaign.opening_hour:02d}:00",
            inline=True,
        )
        embed.add_field(
            name="Rattrapage",
            value=catchup_text,
            inline=True,
        )
        embed.add_field(
            name="Canal",
            value=channel_text,
            inline=True,
        )
        embed.add_field(
            name="Annonces",
            value=(
                "Activées"
                if campaign.announcements_enabled
                else "Désactivées"
            ),
            inline=True,
        )
        embed.add_field(
            name="Rôle annoncé",
            value=role_text,
            inline=True,
        )

        return embed

    # ----------------------------------------------------
    # CRÉATION ET CONSULTATION DE LA CAMPAGNE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-initialiser",
        description=(
            "Crée ou actualise la campagne de décembre."
        ),
    )
    @app_commands.describe(
        annee="Année de la campagne, par exemple 2026.",
        fuseau=(
            "Fuseau horaire IANA, par exemple Europe/Paris."
        ),
        titre="Titre affiché sur le calendrier.",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def initialize_campaign(
        self,
        interaction: discord.Interaction,
        annee: app_commands.Range[int, 2020, 2200],
        fuseau: str = "Europe/Paris",
        titre: str = "Calendrier de l'Avent",
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        normalized_timezone = fuseau.strip()
        normalized_title = titre.strip()

        if not validate_timezone(normalized_timezone):
            await self._send_error(
                interaction,
                "Fuseau invalide",
                (
                    f"Le fuseau `{normalized_timezone}` est inconnu.\n"
                    "Exemple valide : `Europe/Paris`."
                ),
            )
            return

        if not normalized_title:
            normalized_title = "Calendrier de l'Avent"

        if len(normalized_title) > 60:
            await self._send_error(
                interaction,
                "Titre trop long",
                "Le titre ne doit pas dépasser 60 caractères.",
            )
            return

        campaign = await self.service.create_default_campaign(
            guild_id=guild.id,
            year=annee,
            timezone=normalized_timezone,
            title=normalized_title,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_initialized",
            details={
                "year": annee,
                "timezone": normalized_timezone,
                "title": normalized_title,
            },
        )

        embed = success_embed(
            "Campagne initialisée",
            (
                f"Le calendrier **{annee}** est prêt.\n\n"
                f"Il fonctionnera du **1er au 24 décembre {annee}** "
                f"dans le fuseau `{normalized_timezone}`."
            ),
        )
        embed.add_field(
            name="Étape suivante",
            value=(
                "Configure les récompenses, choisis le canal, "
                "puis utilise `/avent-admin-publier`."
            ),
            inline=False,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="avent-admin-config",
        description=(
            "Affiche la configuration actuelle du calendrier."
        ),
    )
    @app_commands.describe(
        annee=(
            "Année à consulter. Laisse vide pour la campagne active."
        )
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def show_configuration(
        self,
        interaction: discord.Interaction,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Configuration introuvable",
                str(error),
            )
            return

        rewards = await self.repository.list_rewards(
            campaign.id
        )
        openings = (
            await self.repository.count_campaign_openings(
                campaign.id
            )
        )
        members = (
            await self.repository.count_campaign_members(
                campaign.id
            )
        )

        embed = self._campaign_embed(campaign)
        embed.add_field(
            name="Récompenses configurées",
            value=f"**{len(rewards)}/24**",
            inline=True,
        )
        embed.add_field(
            name="Ouvertures enregistrées",
            value=str(openings),
            inline=True,
        )
        embed.add_field(
            name="Participants",
            value=str(members),
            inline=True,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    # ----------------------------------------------------
    # ACTIVATION ET DÉSACTIVATION
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-activer",
        description=(
            "Active ou désactive une campagne de l'Avent."
        ),
    )
    @app_commands.describe(
        actif="Choisis Oui pour activer ou Non pour désactiver.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_enabled(
        self,
        interaction: discord.Interaction,
        actif: bool,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        await self.repository.set_campaign_enabled(
            campaign.id,
            actif,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_enabled_changed",
            details={
                "enabled": actif,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Configuration enregistrée",
                (
                    f"La campagne **{campaign.year}** est maintenant "
                    f"{'activée ✅' if actif else 'désactivée ❌'}."
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # CANAL DU CALENDRIER
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-canal",
        description=(
            "Définit le canal public du calendrier."
        ),
    )
    @app_commands.describe(
        canal="Canal dans lequel publier le panneau et les annonces.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_channel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        if canal.guild.id != guild.id:
            await self._send_error(
                interaction,
                "Canal invalide",
                "Le canal doit appartenir à ce serveur.",
            )
            return

        bot_member = guild.me

        if bot_member is not None:
            permissions = canal.permissions_for(
                bot_member
            )
            missing: list[str] = []

            if not permissions.view_channel:
                missing.append("Voir le salon")

            if not permissions.send_messages:
                missing.append("Envoyer des messages")

            if not permissions.embed_links:
                missing.append("Intégrer des liens")

            if not permissions.attach_files:
                missing.append("Joindre des fichiers")

            if missing:
                await self._send_error(
                    interaction,
                    "Permissions insuffisantes",
                    (
                        f"Il me manque dans {canal.mention} :\n"
                        + "\n".join(
                            f"• {permission}"
                            for permission in missing
                        )
                    ),
                )
                return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        await self.repository.update_campaign_channel(
            campaign.id,
            canal.id,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_channel_changed",
            details={
                "channel_id": canal.id,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Canal configuré",
                (
                    f"Le panneau et les annonces de la campagne "
                    f"**{campaign.year}** utiliseront "
                    f"{canal.mention}."
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # FUSEAU HORAIRE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-fuseau",
        description=(
            "Modifie le fuseau horaire de la campagne."
        ),
    )
    @app_commands.describe(
        fuseau=(
            "Fuseau IANA, par exemple Europe/Paris ou America/Montreal."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_timezone(
        self,
        interaction: discord.Interaction,
        fuseau: str,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        normalized = fuseau.strip()

        if not validate_timezone(normalized):
            await self._send_error(
                interaction,
                "Fuseau invalide",
                (
                    f"`{normalized}` n'est pas un fuseau reconnu.\n"
                    "Exemples : `Europe/Paris`, "
                    "`Europe/Brussels`, `America/Montreal`."
                ),
            )
            return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        await self.repository.update_campaign_timezone(
            campaign.id,
            normalized,
        )
        await self.repository.set_guild_timezone(
            guild.id,
            normalized,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_timezone_changed",
            details={
                "timezone": normalized,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Fuseau horaire configuré",
                (
                    f"La campagne **{campaign.year}** utilise "
                    f"maintenant `{normalized}`."
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # HEURE D'OUVERTURE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-heure",
        description=(
            "Définit l'heure quotidienne d'ouverture des cases."
        ),
    )
    @app_commands.describe(
        heure=(
            "Heure entière de 0 à 23, dans le fuseau de la campagne."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_opening_hour(
        self,
        interaction: discord.Interaction,
        heure: app_commands.Range[int, 0, 23],
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        await self.repository.update_opening_hour(
            campaign.id,
            heure,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_opening_hour_changed",
            details={
                "opening_hour": heure,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Heure configurée",
                (
                    f"Les nouvelles cases de la campagne "
                    f"**{campaign.year}** seront disponibles à "
                    f"**{heure:02d}:00**, dans le fuseau "
                    f"`{campaign.timezone}`."
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # RATTRAPAGE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-rattrapage",
        description=(
            "Autorise ou interdit l'ouverture des anciennes cases."
        ),
    )
    @app_commands.describe(
        mode="Active ou désactive le rattrapage.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(
                name="Désactivé",
                value=CATCHUP_DISABLED,
            ),
            app_commands.Choice(
                name="Activé",
                value=CATCHUP_ENABLED,
            ),
        ]
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_catchup(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        await self.repository.update_campaign_catchup(
            campaign.id,
            mode.value,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_catchup_changed",
            details={
                "catchup_mode": mode.value,
            },
        )

        enabled = mode.value == CATCHUP_ENABLED

        await interaction.followup.send(
            embed=success_embed(
                "Rattrapage configuré",
                (
                    f"Le rattrapage est maintenant "
                    f"**{'activé' if enabled else 'désactivé'}** "
                    f"pour la campagne **{campaign.year}**."
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # ANNONCES AUTOMATIQUES
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-annonces",
        description=(
            "Configure les annonces quotidiennes du calendrier."
        ),
    )
    @app_commands.describe(
        actives="Active ou désactive les annonces.",
        role=(
            "Rôle à mentionner. Laisse vide pour ne mentionner "
            "aucun rôle."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_announcements(
        self,
        interaction: discord.Interaction,
        actives: bool,
        role: discord.Role | None = None,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        try:
            campaign = await self._campaign(
                guild.id,
                annee,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        if actives and campaign.channel_id is None:
            await self._send_error(
                interaction,
                "Canal manquant",
                (
                    "Configure d'abord un canal avec "
                    "`/avent-admin-canal`."
                ),
            )
            return

        await self.repository.update_announcements(
            campaign.id,
            enabled=actives,
            role_id=role.id if role is not None else None,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="campaign_announcements_changed",
            details={
                "enabled": actives,
                "role_id": (
                    role.id
                    if role is not None
                    else None
                ),
            },
        )

        role_text = (
            role.mention
            if role is not None
            else "aucun rôle"
        )

        await interaction.followup.send(
            embed=success_embed(
                "Annonces configurées",
                (
                    f"Les annonces sont maintenant "
                    f"**{'activées' if actives else 'désactivées'}**.\n"
                    f"Mention utilisée : {role_text}."
                ),
            ),
            ephemeral=True,
        )

    # Le paquet 4B-1B poursuit cette classe dans un second fichier
    # Cog consacré aux récompenses et aux opérations sensibles.

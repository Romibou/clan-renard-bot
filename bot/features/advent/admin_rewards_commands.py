from __future__ import annotations

import json
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.advent.admin_repository import (
    AdminAdventRepository,
)
from bot.features.advent.constants import (
    REWARD_MESSAGE,
    REWARD_POINTS,
    REWARD_RANDOM,
    REWARD_ROLE,
    VALID_REWARD_TYPES,
)
from bot.features.advent.discord_calendar import (
    build_calendar_response,
)
from bot.features.advent.exceptions import AdventError
from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.models import AdventReward
from bot.features.advent.reward_service import RewardService
from bot.features.advent.service import AdventService
from bot.features.advent.transaction_repository import (
    AdventTransactionRepository,
)
from bot.features.advent.views import (
    AdventView,
    ConfirmResetView,
)
from bot.shared.embeds import (
    base_embed,
    error_embed,
    success_embed,
)
from bot.shared.text import truncate


logger = logging.getLogger(__name__)


class AdventAdminRewardsCommands(commands.Cog):
    """
    Administration des récompenses et des données des membres.

    Ce second Cog évite de créer un fichier administratif gigantesque.
    Il utilise les mêmes services et la même connexion PostgreSQL que
    le reste du calendrier.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: AdventService,
        repository: AdminAdventRepository,
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
        year: int | None,
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
        details: dict[str, Any] | None = None,
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
            logger.exception(
                "Impossible d'enregistrer l'action d'audit %s",
                action,
            )

    async def _save_reward(
        self,
        interaction: discord.Interaction,
        *,
        day: int,
        reward_type: str,
        reward_data: dict[str, Any],
        year: int | None,
    ) -> None:
        guild = await self._guild_required(
            interaction
        )

        if guild is None:
            return

        try:
            campaign = await self._campaign(
                guild.id,
                year,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Campagne introuvable",
                str(error),
            )
            return

        reward = await self.repository.upsert_reward(
            campaign_id=campaign.id,
            day=day,
            reward_type=reward_type,
            reward_data=reward_data,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="reward_saved",
            details={
                "day": day,
                "reward_type": reward_type,
            },
        )

        description = self.reward_service.describe(
            reward.reward_type,
            reward.reward_data,
        )

        embed = success_embed(
            "Récompense enregistrée",
            (
                f"La récompense du jour **{day}** a été "
                f"configurée pour la campagne **{campaign.year}**."
            ),
        )
        embed.add_field(
            name="Type",
            value=f"`{reward.reward_type}`",
            inline=True,
        )
        embed.add_field(
            name="Contenu",
            value=truncate(description, 1000),
            inline=False,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @staticmethod
    def _validate_random_choices(
        value: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError(
                "Le JSON doit être une liste de possibilités."
            )

        if not value:
            raise ValueError(
                "La liste des possibilités est vide."
            )

        normalized: list[dict[str, Any]] = []

        for index, raw_choice in enumerate(
            value,
            start=1,
        ):
            if not isinstance(raw_choice, dict):
                raise ValueError(
                    f"Le choix n°{index} doit être un objet JSON."
                )

            reward_type = str(
                raw_choice.get("type", "")
            ).strip()
            reward_data = raw_choice.get("data", {})
            raw_weight = raw_choice.get("weight", 1)

            if reward_type not in VALID_REWARD_TYPES:
                raise ValueError(
                    f"Le choix n°{index} possède un type invalide."
                )

            if reward_type == REWARD_RANDOM:
                raise ValueError(
                    "Une récompense aléatoire ne peut pas contenir "
                    "une autre récompense aléatoire."
                )

            if not isinstance(reward_data, dict):
                raise ValueError(
                    f"Le champ data du choix n°{index} "
                    "doit être un objet JSON."
                )

            try:
                weight = float(raw_weight)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Le poids du choix n°{index} est invalide."
                ) from error

            if weight <= 0:
                raise ValueError(
                    f"Le poids du choix n°{index} doit être positif."
                )

            # Vérification de la structure sans conserver le résultat
            # aléatoire produit par resolve().
            temporary = AdventReward(
                id=0,
                campaign_id=0,
                day=1,
                reward_type=reward_type,
                reward_data=reward_data,
            )
            RewardService().resolve(temporary)

            normalized.append(
                {
                    "type": reward_type,
                    "weight": weight,
                    "data": reward_data,
                }
            )

        return normalized

    # ----------------------------------------------------
    # RÉCOMPENSE TEXTE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-recompense-message",
        description=(
            "Configure une récompense textuelle pour une journée."
        ),
    )
    @app_commands.describe(
        jour="Jour du calendrier, entre 1 et 24.",
        message="Message reçu par le membre.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def reward_message(
        self,
        interaction: discord.Interaction,
        jour: app_commands.Range[int, 1, 24],
        message: app_commands.Range[str, 1, 1000],
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await self._save_reward(
            interaction,
            day=jour,
            reward_type=REWARD_MESSAGE,
            reward_data={
                "message": message.strip(),
            },
            year=annee,
        )

    # ----------------------------------------------------
    # RÉCOMPENSE EN POINTS
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-recompense-points",
        description=(
            "Configure une récompense en points."
        ),
    )
    @app_commands.describe(
        jour="Jour du calendrier, entre 1 et 24.",
        points="Nombre de points à attribuer.",
        message=(
            "Message personnalisé facultatif affiché au membre."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def reward_points(
        self,
        interaction: discord.Interaction,
        jour: app_commands.Range[int, 1, 24],
        points: app_commands.Range[int, 0, 1_000_000],
        message: app_commands.Range[str, 1, 1000] | None = None,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        reward_data: dict[str, Any] = {
            "points": points,
        }

        if message is not None:
            reward_data["message"] = message.strip()

        await self._save_reward(
            interaction,
            day=jour,
            reward_type=REWARD_POINTS,
            reward_data=reward_data,
            year=annee,
        )

    # ----------------------------------------------------
    # RÉCOMPENSE DE RÔLE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-recompense-role",
        description=(
            "Configure un rôle Discord comme récompense."
        ),
    )
    @app_commands.describe(
        jour="Jour du calendrier, entre 1 et 24.",
        role="Rôle Discord à attribuer.",
        message=(
            "Message personnalisé facultatif affiché au membre."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def reward_role(
        self,
        interaction: discord.Interaction,
        jour: app_commands.Range[int, 1, 24],
        role: discord.Role,
        message: app_commands.Range[str, 1, 1000] | None = None,
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

        if role.is_default():
            await self._send_error(
                interaction,
                "Rôle invalide",
                "Le rôle `@everyone` ne peut pas être distribué.",
            )
            return

        if role.managed:
            await self._send_error(
                interaction,
                "Rôle invalide",
                (
                    "Ce rôle est géré par Discord ou une intégration "
                    "et ne peut pas être attribué manuellement."
                ),
            )
            return

        bot_member = guild.me

        if (
            bot_member is not None
            and role >= bot_member.top_role
        ):
            await self._send_error(
                interaction,
                "Hiérarchie incorrecte",
                (
                    f"Le rôle {role.mention} est placé au-dessus "
                    "du rôle du bot. Déplace d'abord le rôle "
                    "Clan Renard plus haut dans la hiérarchie."
                ),
            )
            return

        reward_data: dict[str, Any] = {
            "role_id": role.id,
        }

        if message is not None:
            reward_data["message"] = message.strip()

        await self._save_reward(
            interaction,
            day=jour,
            reward_type=REWARD_ROLE,
            reward_data=reward_data,
            year=annee,
        )

    # ----------------------------------------------------
    # RÉCOMPENSE ALÉATOIRE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-recompense-aleatoire",
        description=(
            "Configure plusieurs récompenses avec des probabilités."
        ),
    )
    @app_commands.describe(
        jour="Jour du calendrier, entre 1 et 24.",
        choix_json=(
            "Liste JSON des choix. Consulte docs/COMMANDS_ADMIN.md."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def reward_random(
        self,
        interaction: discord.Interaction,
        jour: app_commands.Range[int, 1, 24],
        choix_json: str,
        annee: app_commands.Range[int, 2020, 2200] | None = None,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            decoded = json.loads(
                choix_json
            )
            choices = self._validate_random_choices(
                decoded
            )
        except json.JSONDecodeError as error:
            await self._send_error(
                interaction,
                "JSON invalide",
                (
                    "Le texte fourni n'est pas un JSON valide.\n"
                    f"Erreur près du caractère {error.pos}."
                ),
            )
            return
        except ValueError as error:
            await self._send_error(
                interaction,
                "Configuration invalide",
                str(error),
            )
            return
        except AdventError as error:
            await self._send_error(
                interaction,
                "Récompense invalide",
                str(error),
            )
            return

        await self._save_reward(
            interaction,
            day=jour,
            reward_type=REWARD_RANDOM,
            reward_data={
                "choices": choices,
            },
            year=annee,
        )

    # ----------------------------------------------------
    # LISTE DES RÉCOMPENSES
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-recompenses",
        description=(
            "Affiche les récompenses configurées."
        ),
    )
    @app_commands.describe(
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        )
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def list_rewards(
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
                "Campagne introuvable",
                str(error),
            )
            return

        rewards = await self.repository.list_rewards(
            campaign.id
        )

        embed = base_embed(
            f"🎁 Récompenses Avent {campaign.year}",
            (
                f"**{len(rewards)}/24** journée(s) possèdent "
                "une récompense configurée."
            ),
        )

        if not rewards:
            embed.add_field(
                name="Aucune récompense",
                value=(
                    "Une case sans configuration peut quand même "
                    "être ouverte, mais elle n'attribuera aucun gain."
                ),
                inline=False,
            )
        else:
            lines: list[str] = []

            for reward in rewards:
                description = self.reward_service.describe(
                    reward.reward_type,
                    reward.reward_data,
                )
                lines.append(
                    f"**Jour {reward.day:02d}** — "
                    f"`{reward.reward_type}` — "
                    f"{truncate(description, 75)}"
                )

            first_half = lines[:12]
            second_half = lines[12:]

            embed.add_field(
                name="Jours 1 à 12 configurés",
                value="\n".join(first_half) or "Aucun",
                inline=False,
            )

            if second_half:
                embed.add_field(
                    name="Suite",
                    value="\n".join(second_half),
                    inline=False,
                )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    # ----------------------------------------------------
    # SUPPRESSION D'UNE RÉCOMPENSE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-recompense-supprimer",
        description=(
            "Supprime la récompense configurée d'une journée."
        ),
    )
    @app_commands.describe(
        jour="Jour concerné, entre 1 et 24.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def delete_reward(
        self,
        interaction: discord.Interaction,
        jour: app_commands.Range[int, 1, 24],
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

        deleted = await self.repository.delete_reward(
            campaign.id,
            jour,
        )

        if not deleted:
            await self._send_error(
                interaction,
                "Récompense introuvable",
                (
                    f"Aucune récompense n'était configurée "
                    f"pour le jour **{jour}**."
                ),
            )
            return

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="reward_deleted",
            details={
                "day": jour,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Récompense supprimée",
                (
                    f"La case **{jour}** ne possède plus "
                    "de récompense configurée."
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # APERÇU ADMINISTRATIF
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-apercu",
        description=(
            "Génère un aperçu personnel du calendrier."
        ),
    )
    @app_commands.describe(
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        )
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    @app_commands.checks.cooldown(
        1,
        5.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def preview(
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
            state = await self.service.get_calendar_state(
                guild_id=guild.id,
                user_id=interaction.user.id,
                campaign=campaign,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Aperçu indisponible",
                str(error),
            )
            return

        embed, file, view = await build_calendar_response(
            state=state,
            member=interaction.user,
            image_generator=self.image_generator,
            preview=True,
        )

        await interaction.followup.send(
            embed=embed,
            file=file,
            view=view,
            ephemeral=True,
        )

    # ----------------------------------------------------
    # PUBLICATION DU PANNEAU
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-publier",
        description=(
            "Publie le panneau public du calendrier."
        ),
    )
    @app_commands.describe(
        canal=(
            "Canal de publication. Laisse vide pour utiliser "
            "le canal configuré."
        ),
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def publish_panel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel | None = None,
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

        target_channel = canal

        if target_channel is None:
            if campaign.channel_id is None:
                await self._send_error(
                    interaction,
                    "Canal manquant",
                    (
                        "Indique un canal dans la commande ou utilise "
                        "d'abord `/avent-admin-canal`."
                    ),
                )
                return

            resolved_channel = guild.get_channel(
                campaign.channel_id
            )

            if not isinstance(
                resolved_channel,
                discord.TextChannel,
            ):
                await self._send_error(
                    interaction,
                    "Canal introuvable",
                    (
                        "Le canal enregistré n'existe plus ou "
                        "n'est pas un salon textuel."
                    ),
                )
                return

            target_channel = resolved_channel

        bot_member = guild.me

        if bot_member is not None:
            permissions = target_channel.permissions_for(
                bot_member
            )
            missing: list[str] = []

            if not permissions.view_channel:
                missing.append("Voir le salon")

            if not permissions.send_messages:
                missing.append("Envoyer des messages")

            if not permissions.embed_links:
                missing.append("Intégrer des liens")

            if missing:
                await self._send_error(
                    interaction,
                    "Permissions insuffisantes",
                    (
                        f"Permissions manquantes dans "
                        f"{target_channel.mention} :\n"
                        + "\n".join(
                            f"• {item}"
                            for item in missing
                        )
                    ),
                )
                return

        panel_embed = base_embed(
            f"🎄 {campaign.title} {campaign.year}",
            (
                "Le calendrier de l'Avent de **Clan Renard** "
                "est disponible !\n\n"
                "Chaque membre possède son propre calendrier et "
                "ses propres récompenses.\n\n"
                "Clique sur **Ouvrir la case** pour recevoir la "
                "surprise du jour, ou sur **Actualiser** pour "
                "afficher ton calendrier personnel."
            ),
        )
        panel_embed.add_field(
            name="Période",
            value=(
                f"Du **{campaign.start_date.strftime('%d/%m/%Y')}** "
                f"au **{campaign.end_date.strftime('%d/%m/%Y')}**"
            ),
            inline=False,
        )
        panel_embed.add_field(
            name="Ouverture quotidienne",
            value=(
                f"À **{campaign.opening_hour:02d}:00** "
                f"— fuseau `{campaign.timezone}`"
            ),
            inline=False,
        )

        try:
            message = await target_channel.send(
                embed=panel_embed,
                view=AdventView(),
            )
        except discord.HTTPException:
            logger.exception(
                "Impossible de publier le panneau Avent"
            )
            await self._send_error(
                interaction,
                "Publication impossible",
                (
                    "Discord a refusé la publication du panneau. "
                    "Vérifie les permissions du bot."
                ),
            )
            return

        await self.repository.update_campaign_channel(
            campaign.id,
            target_channel.id,
        )
        await self.transactions.save_panel(
            campaign_id=campaign.id,
            guild_id=guild.id,
            channel_id=target_channel.id,
            message_id=message.id,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="panel_published",
            details={
                "channel_id": target_channel.id,
                "message_id": message.id,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Panneau publié",
                (
                    f"Le panneau a été publié dans "
                    f"{target_channel.mention}.\n"
                    f"[Afficher le message]({message.jump_url})"
                ),
            ),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # CONSULTATION D'UN MEMBRE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-utilisateur",
        description=(
            "Consulte la progression Avent d'un membre."
        ),
    )
    @app_commands.describe(
        membre="Membre à consulter.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def inspect_user(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
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
            state = await self.service.get_calendar_state(
                guild_id=guild.id,
                user_id=membre.id,
                campaign=campaign,
            )
            history = await self.service.get_reward_history(
                campaign_id=campaign.id,
                user_id=membre.id,
            )
        except AdventError as error:
            await self._send_error(
                interaction,
                "Consultation impossible",
                str(error),
            )
            return

        opened_days = sorted(state.opened_days)
        missed_days = sorted(state.missed_days)

        embed = base_embed(
            f"🦊 Avent — {truncate(membre.display_name, 40)}",
            (
                f"Progression administrative pour la campagne "
                f"**{campaign.year}**."
            ),
        )
        embed.set_thumbnail(
            url=membre.display_avatar.url
        )
        embed.add_field(
            name="Cases ouvertes",
            value=(
                f"**{len(opened_days)}/24**\n"
                + (
                    ", ".join(
                        str(day)
                        for day in opened_days
                    )
                    if opened_days
                    else "Aucune"
                )
            ),
            inline=False,
        )
        embed.add_field(
            name="Cases manquées",
            value=(
                f"**{len(missed_days)}**\n"
                + (
                    ", ".join(
                        str(day)
                        for day in missed_days
                    )
                    if missed_days
                    else "Aucune"
                )
            ),
            inline=False,
        )
        embed.add_field(
            name="Points",
            value=str(state.total_points),
            inline=True,
        )
        embed.add_field(
            name="Récompenses",
            value=str(len(history)),
            inline=True,
        )
        embed.add_field(
            name="Identifiant Discord",
            value=f"`{membre.id}`",
            inline=True,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    # ----------------------------------------------------
    # RÉINITIALISATION D'UN MEMBRE
    # ----------------------------------------------------

    @app_commands.command(
        name="avent-admin-reset-utilisateur",
        description=(
            "Efface les ouvertures Avent d'un membre."
        ),
    )
    @app_commands.describe(
        membre="Membre dont les données doivent être effacées.",
        annee=(
            "Année ciblée. Laisse vide pour la campagne active."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def reset_user(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
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

        openings = await self.repository.get_user_openings(
            campaign.id,
            membre.id,
        )

        if not openings:
            await self._send_error(
                interaction,
                "Aucune donnée",
                (
                    f"{membre.mention} ne possède aucune ouverture "
                    f"pour la campagne **{campaign.year}**."
                ),
            )
            return

        view = ConfirmResetView(
            author_id=interaction.user.id,
        )
        warning = error_embed(
            "Confirmation obligatoire",
            (
                f"Tu vas supprimer **{len(openings)} ouverture(s)** "
                f"de {membre.mention} pour la campagne "
                f"**{campaign.year}**.\n\n"
                "Cette action ne retire pas automatiquement les rôles "
                "Discord déjà attribués et ne peut pas être annulée."
            ),
        )

        confirmation_message = await interaction.followup.send(
            embed=warning,
            view=view,
            ephemeral=True,
            wait=True,
        )
        view.message = confirmation_message

        timed_out = await view.wait()

        if timed_out or view.confirmed is None:
            await interaction.followup.send(
                embed=error_embed(
                    "Confirmation expirée",
                    "Aucune donnée n'a été supprimée.",
                ),
                ephemeral=True,
            )
            return

        if not view.confirmed:
            await interaction.followup.send(
                embed=base_embed(
                    "Action annulée",
                    "Aucune donnée n'a été supprimée.",
                ),
                ephemeral=True,
            )
            return

        deleted_count = await self.transactions.reset_user(
            campaign_id=campaign.id,
            user_id=membre.id,
        )

        await self._audit(
            interaction,
            campaign_id=campaign.id,
            action="user_reset",
            details={
                "user_id": membre.id,
                "deleted_openings": deleted_count,
            },
        )

        await interaction.followup.send(
            embed=success_embed(
                "Utilisateur réinitialisé",
                (
                    f"**{deleted_count} ouverture(s)** ont été "
                    f"supprimées pour {membre.mention}."
                ),
            ),
            ephemeral=True,
        )

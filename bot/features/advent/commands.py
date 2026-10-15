from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.features.advent.discord_calendar import (
    build_calendar_response,
)
from bot.features.advent.discord_rewards import (
    grant_role_reward,
)
from bot.features.advent.exceptions import AdventError
from bot.features.advent.image_generator import (
    AdventImageGenerator,
)
from bot.features.advent.presentation import (
    help_embed,
    leaderboard_embed,
    profile_embed,
    reward_history_embed,
)
from bot.features.advent.service import AdventService
from bot.shared.embeds import (
    base_embed,
    error_embed,
    success_embed,
)

from bot.features.advent.views import CatchupDayView

logger = logging.getLogger(__name__)


class AdventCommands(commands.Cog):
    """
    Commandes accessibles aux membres.

    Cette classe contient également les méthodes appelées par les
    boutons persistants définis dans views.py.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        service: AdventService,
        image_generator: AdventImageGenerator,
    ) -> None:
        self.bot = bot
        self.service = service
        self.image_generator = image_generator

    # ----------------------------------------------------
    # OUTILS INTERNES
    # ----------------------------------------------------

    @staticmethod
    def _guild_from_interaction(
        interaction: discord.Interaction,
    ) -> discord.Guild | None:
        return interaction.guild

    @staticmethod
    async def _send_guild_required(
        interaction: discord.Interaction,
    ) -> None:
        embed = error_embed(
            "Serveur requis",
            (
                "Le calendrier de l'Avent ne peut être utilisé "
                "que dans un serveur Discord."
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

    @staticmethod
    async def _send_advent_error(
        interaction: discord.Interaction,
        error: AdventError,
        *,
        title: str = "Calendrier indisponible",
    ) -> None:
        embed = error_embed(
            title,
            str(error),
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

    async def _get_member(
        self,
        interaction: discord.Interaction,
    ) -> discord.Member | None:
        guild = interaction.guild

        if guild is None:
            return None

        if isinstance(
            interaction.user,
            discord.Member,
        ):
            return interaction.user

        member = guild.get_member(
            interaction.user.id
        )

        if member is not None:
            return member

        try:
            return await guild.fetch_member(
                interaction.user.id
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return None

    async def _send_calendar(
        self,
        interaction: discord.Interaction,
        *,
        ephemeral: bool = True,
        preview: bool = False,
    ) -> None:
        guild = self._guild_from_interaction(
            interaction
        )

        if guild is None:
            await self._send_guild_required(
                interaction
            )
            return

        try:
            campaign = (
                await self.service.get_campaign_for_display(
                    guild.id
                )
            )
            state = (
                await self.service.get_calendar_state(
                    guild_id=guild.id,
                    user_id=interaction.user.id,
                    campaign=campaign,
                )
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
            )
            return

        embed, file, view = (
            await build_calendar_response(
                state=state,
                member=interaction.user,
                image_generator=self.image_generator,
                preview=preview,
            )
        )

        await interaction.followup.send(
            embed=embed,
            file=file,
            view=view,
            ephemeral=ephemeral,
        )

    async def _open_case(
        self,
        interaction: discord.Interaction,
        *,
        requested_day: int | None = None,
    ) -> None:
        guild = self._guild_from_interaction(
            interaction
        )

        if guild is None:
            await self._send_guild_required(
                interaction
            )
            return

        member = await self._get_member(
            interaction
        )

        try:
            campaign = (
                await self.service.get_campaign_for_display(
                    guild.id
                )
            )
            result = await self.service.open_day(
                guild_id=guild.id,
                user_id=interaction.user.id,
                requested_day=requested_day,
                campaign=campaign,
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Impossible d'ouvrir cette case",
            )
            return

        role_warning: str | None = None

        if result.role_id is not None:
            if member is None:
                role_warning = (
                    "La récompense a bien été enregistrée, "
                    "mais je n'ai pas pu retrouver ton profil "
                    "de membre afin d'attribuer le rôle."
                )

                await self.service.mark_role_result(
                    opening_id=result.opening.id,
                    success=False,
                    error=role_warning,
                )
            else:
                role_success, role_error = (
                    await grant_role_reward(
                        guild=guild,
                        member=member,
                        result=result,
                        service=self.service,
                    )
                )

                if not role_success:
                    role_warning = role_error

        reward_description = (
            f"Tu as ouvert la case "
            f"**n°{result.opening.day}** !\n\n"
            f"{result.reward_message}"
        )

        if role_warning is not None:
            reward_description += (
                "\n\n⚠️ **La récompense est sauvegardée**, "
                "mais le rôle n'a pas pu être attribué "
                "automatiquement.\n"
                f"{role_warning}"
            )

        reward_embed = success_embed(
            "Case ouverte !",
            reward_description,
        )

        reward_embed.add_field(
            name="Jour",
            value=str(result.opening.day),
            inline=True,
        )
        reward_embed.add_field(
            name="Points gagnés",
            value=str(result.opening.points_awarded),
            inline=True,
        )
        reward_embed.add_field(
            name="Récompense enregistrée",
            value="Oui ✅",
            inline=True,
        )

        await interaction.followup.send(
            embed=reward_embed,
            ephemeral=True,
        )

        # Un calendrier actualisé est envoyé juste après le gain.
        try:
            updated_state = (
                await self.service.get_calendar_state(
                    guild_id=guild.id,
                    user_id=interaction.user.id,
                    campaign=campaign,
                )
            )

            embed, file, view = (
                await build_calendar_response(
                    state=updated_state,
                    member=interaction.user,
                    image_generator=self.image_generator,
                )
            )

            await interaction.followup.send(
                embed=embed,
                file=file,
                view=view,
                ephemeral=True,
            )
        except Exception:
            # La récompense est déjà sauvegardée. Une panne du rendu
            # ne doit pas transformer l'ouverture en échec.
            logger.exception(
                "Impossible de générer le calendrier actualisé "
                "après l'ouverture de la case %s pour %s",
                result.opening.day,
                interaction.user.id,
            )

    async def _send_reward_history(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = self._guild_from_interaction(
            interaction
        )

        if guild is None:
            await self._send_guild_required(
                interaction
            )
            return

        try:
            campaign = (
                await self.service.get_campaign_for_display(
                    guild.id
                )
            )
            history = (
                await self.service.get_reward_history(
                    campaign_id=campaign.id,
                    user_id=interaction.user.id,
                )
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Récompenses indisponibles",
            )
            return

        embed = reward_history_embed(
            campaign,
            interaction.user,
            history,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    # ----------------------------------------------------
    # COMMANDES SLASH
    # ----------------------------------------------------

    @app_commands.command(
        name="avent",
        description=("Affiche ton calendrier de l'Avent personnel."),
        default_member_permissions=discord.Permissions(administrator=True), # SUPPRIMER CETTE LUGNE POUR REDONNER ACCES AUX MEMBRES A LA COMMANDE AVENT
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        4.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def advent(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await self._send_calendar(
            interaction,
            ephemeral=True,
        )

    @app_commands.command(
        name="avent-profil",
        description=(
            "Affiche ta progression dans le calendrier."
        ),
    )
    @app_commands.guild_only()
    async def advent_profile(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await self._send_guild_required(
                interaction
            )
            return

        try:
            campaign = (
                await self.service.get_campaign_for_display(
                    guild.id
                )
            )
            state = (
                await self.service.get_calendar_state(
                    guild_id=guild.id,
                    user_id=interaction.user.id,
                    campaign=campaign,
                )
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Profil indisponible",
            )
            return

        embed = profile_embed(
            state,
            interaction.user,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="avent-recompenses",
        description=(
            "Affiche les récompenses que tu as obtenues."
        ),
    )
    @app_commands.guild_only()
    async def advent_rewards(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await self._send_reward_history(
            interaction
        )

    @app_commands.command(
        name="avent-classement",
        description=(
            "Affiche le classement du calendrier."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        8.0,
        key=lambda interaction: (
            interaction.guild_id,
            interaction.user.id,
        ),
    )
    async def advent_leaderboard(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=False,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await self._send_guild_required(
                interaction
            )
            return

        try:
            campaign = (
                await self.service.get_campaign_for_display(
                    guild.id
                )
            )
            ranking = await self.service.get_leaderboard(
                campaign.id,
                limit=10,
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Classement indisponible",
            )
            return

        embed = leaderboard_embed(
            campaign,
            guild,
            ranking,
        )

        await interaction.followup.send(
            embed=embed,
        )

    @app_commands.command(
        name="avent-aide",
        description=(
            "Explique le fonctionnement du calendrier."
        ),
    )
    async def advent_help(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            embed=help_embed(),
            ephemeral=True,
        )

    # ----------------------------------------------------
    # MÉTHODES APPELÉES PAR LES BOUTONS
    # ----------------------------------------------------

    async def handle_open_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await self._send_guild_required(interaction)
            return

        try:
            campaign = await self.service.get_campaign_for_display(
                guild.id
            )

            state = await self.service.get_calendar_state(
                guild_id=guild.id,
                user_id=interaction.user.id,
                campaign=campaign,
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Impossible d'ouvrir une case",
            )
            return

        available_days = sorted(state.available_days)

        if not available_days:
            await interaction.response.defer(
                ephemeral=True,
                thinking=True,
            )

            await self._open_case(interaction)
            return

        # S'il n'y a que la case du jour, on l'ouvre directement.
        if len(available_days) == 1:
            await interaction.response.defer(
                ephemeral=True,
                thinking=True,
            )

            await self._open_case(
                interaction,
                requested_day=available_days[0],
            )
            return

        # En mode rattrapage, plusieurs cases peuvent être ouvertes.
        view = CatchupDayView(
            owner_id=interaction.user.id,
            days=available_days,
        )

        embed = base_embed(
            "🎁 Choisis une case",
            (
                "Plusieurs cases sont disponibles grâce au "
                "rattrapage.\n\n"
                "Choisis la case que tu souhaites ouvrir dans "
                "le menu ci-dessous."
            ),
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )

    async def handle_refresh_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await self._send_calendar(
            interaction,
            ephemeral=True,
        )

    async def handle_rewards_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        await self._send_reward_history(interaction)

    async def handle_profile_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await self._send_guild_required(interaction)
            return

        try:
            campaign = await self.service.get_campaign_for_display(
                guild.id
            )

            state = await self.service.get_calendar_state(
                guild_id=guild.id,
                user_id=interaction.user.id,
                campaign=campaign,
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Profil indisponible",
            )
            return

        embed = profile_embed(
            state,
            interaction.user,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    async def handle_leaderboard_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await self._send_guild_required(interaction)
            return

        try:
            campaign = await self.service.get_campaign_for_display(
                guild.id
            )

            ranking = await self.service.get_leaderboard(
                campaign.id,
                limit=10,
            )
        except AdventError as error:
            await self._send_advent_error(
                interaction,
                error,
                title="Classement indisponible",
            )
            return

        embed = leaderboard_embed(
            campaign,
            guild,
            ranking,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    async def handle_shop_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        shop_cog = self.bot.get_cog("AdventShop")

        if shop_cog is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Boutique indisponible",
                    (
                        "Le module de la boutique de l'Avent "
                        "n'est pas chargé."
                    ),
                ),
                ephemeral=True,
            )
            return

        shop_command = getattr(shop_cog, "shop", None)
        callback = getattr(shop_command, "callback", None)

        if callback is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Boutique indisponible",
                    (
                        "La commande de la boutique est "
                        "introuvable."
                    ),
                ),
                ephemeral=True,
            )
            return

        # Le callback de la commande /avent-boutique attend
        # l'instance du Cog puis l'interaction.
        await callback(
            shop_cog,
            interaction,
        )

    async def handle_help_button(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_message(
            embed=help_embed(),
            ephemeral=True,
        )



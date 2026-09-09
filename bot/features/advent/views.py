from __future__ import annotations

import logging
from typing import Any

import discord


logger = logging.getLogger(__name__)


def get_advent_cog(
    interaction: discord.Interaction,
) -> Any | None:
    """
    Retrouve le cog contenant les commandes du calendrier.

    Any est volontairement utilisé ici pour éviter une importation
    circulaire entre views.py et commands.py.
    """
    client = interaction.client

    if not isinstance(client, discord.Client):
        return None

    get_cog = getattr(client, "get_cog", None)

    if get_cog is None:
        return None

    return get_cog("AdventCommands")


async def unavailable(
    interaction: discord.Interaction,
) -> None:
    message = (
        "❌ Le module du calendrier n'est pas disponible. "
        "Préviens un administrateur du serveur."
    )

    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True,
        )


class AdventView(discord.ui.View):
    """
    Vue persistante du calendrier.
    """

    def __init__(self) -> None:
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="Ouvrir la case",
        emoji="🎁",
        style=discord.ButtonStyle.success,
        custom_id="clan_renard:advent:open",
        row=0,
    )
    async def open_case(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_open_button(
            interaction
        )

    @discord.ui.button(
        label="Actualiser",
        emoji="🔄",
        style=discord.ButtonStyle.primary,
        custom_id="clan_renard:advent:refresh",
        row=0,
    )
    async def refresh_calendar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_refresh_button(
            interaction
        )

    @discord.ui.button(
        label="Profil",
        emoji="👤",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:profile",
        row=0,
    )
    async def show_profile(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_profile_button(
            interaction
        )

    @discord.ui.button(
        label="Récompenses",
        emoji="🏆",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:rewards",
        row=1,
    )
    async def show_rewards(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_rewards_button(
            interaction
        )

    @discord.ui.button(
        label="Classement",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:leaderboard",
        row=1,
    )
    async def show_leaderboard(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_leaderboard_button(
            interaction
        )

    @discord.ui.button(
        label="Boutique",
        emoji="🛍️",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:shop",
        row=1,
    )
    async def show_shop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_shop_button(
            interaction
        )

    @discord.ui.button(
        label="Aide",
        emoji="❔",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:help",
        row=1,
    )
    async def show_help(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(
            interaction
        )

        if cog is None:
            await unavailable(
                interaction
            )
            return

        await cog.handle_help_button(
            interaction
        )


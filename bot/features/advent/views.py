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
            await unavailable(interaction)
            return
            
        await cog.handle_help_button(interaction)


class CatchupDaySelect(discord.ui.Select):
    """Menu permettant de choisir une case disponible."""

    def __init__(
        self,
        *,
        days: list[int],
    ) -> None:
        options = [
            discord.SelectOption(
                label=f"Case n°{day}",
                value=str(day),
                emoji="🎁",
                description=f"Ouvrir la case du {day} décembre",
            )
            for day in sorted(days)
        ]

        super().__init__(
            placeholder="Choisis la case à ouvrir…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        cog = get_advent_cog(interaction)

        if cog is None:
            await unavailable(interaction)
            return

        try:
            selected_day = int(self.values[0])
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "❌ La case sélectionnée est invalide.",
                ephemeral=True,
            )
            return

        # Empêche une seconde utilisation du même menu.
        self.disabled = True

        await interaction.response.edit_message(
            view=self.view,
        )

        await cog._open_case(
            interaction,
            requested_day=selected_day,
        )

        if self.view is not None:
            self.view.stop()


class CatchupDayView(discord.ui.View):
    """Vue personnelle pour sélectionner une ancienne case."""

    def __init__(
        self,
        *,
        owner_id: int,
        days: list[int],
    ) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id

        self.add_item(
            CatchupDaySelect(days=days)
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            (
                "❌ Ce menu appartient à un autre membre.\n"
                "Utilise le bouton **Ouvrir la case** "
                "pour ouvrir ton propre calendrier."
            ),
            ephemeral=True,
        )
        return False





class ConfirmResetView(discord.ui.View):
    """
    Confirmation non persistante pour une opération dangereuse.

    Seul l'administrateur ayant lancé la commande peut utiliser
    ces boutons.
    """

    def __init__(
        self,
        *,
        author_id: int,
        timeout: float = 60,
    ) -> None:
        super().__init__(timeout=timeout)

        self.author_id = author_id
        self.confirmed: bool | None = None
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id == self.author_id:
            return True

        await interaction.response.send_message(
            (
                "❌ Seule la personne ayant lancé cette action "
                "peut utiliser ces boutons."
            ),
            ephemeral=True,
        )
        return False

    async def disable_all(
        self,
        interaction: discord.Interaction,
    ) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        try:
            await interaction.response.edit_message(
                view=self,
            )
        except discord.HTTPException:
            logger.warning(
                "Impossible de désactiver les boutons "
                "de confirmation.",
                exc_info=True,
            )

    @discord.ui.button(
        label="Confirmer",
        emoji="✅",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.confirmed = True

        await self.disable_all(interaction)

        self.stop()

    @discord.ui.button(
        label="Annuler",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.confirmed = False

        await self.disable_all(interaction)

        self.stop()

    async def on_timeout(self) -> None:
        self.confirmed = None

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message is not None:
            try:
                await self.message.edit(
                    view=self,
                )
            except discord.HTTPException:
                logger.debug(
                    "Le message de confirmation n'est plus "
                    "modifiable.",
                    exc_info=True,
                )

        await cog.handle_help_button(
            interaction
        )


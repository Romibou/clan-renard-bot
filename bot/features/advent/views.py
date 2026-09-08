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

    timeout=None et des custom_id fixes permettent aux boutons de
    continuer à fonctionner après un redémarrage du bot.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

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
        cog = get_advent_cog(interaction)

        if cog is None:
            await unavailable(interaction)
            return

        await cog.handle_open_button(interaction)

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
        cog = get_advent_cog(interaction)

        if cog is None:
            await unavailable(interaction)
            return

        await cog.handle_refresh_button(interaction)

    @discord.ui.button(
        label="Mes récompenses",
        emoji="🏆",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:rewards",
        row=0,
    )
    async def show_rewards(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(interaction)

        if cog is None:
            await unavailable(interaction)
            return

        await cog.handle_rewards_button(interaction)

    @discord.ui.button(
        label="Aide",
        emoji="❔",
        style=discord.ButtonStyle.secondary,
        custom_id="clan_renard:advent:help",
        row=0,
    )
    async def show_help(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        cog = get_advent_cog(interaction)

        if cog is None:
            await unavailable(interaction)
            return

        await cog.handle_help_button(interaction)


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
            "❌ Seule la personne ayant lancé cette action "
            "peut utiliser ces boutons.",
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
                view=self
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
                await self.message.edit(view=self)
            except discord.HTTPException:
                logger.debug(
                    "Le message de confirmation n'est plus "
                    "modifiable.",
                    exc_info=True,
                )

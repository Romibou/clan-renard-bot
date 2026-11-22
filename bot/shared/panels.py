"""
Outils pour les panneaux d'administration (messages privés avec menus).

Deux soucis qu'on évite partout :

1. Un menu déroulant Discord garde l'option choisie affichée, et la
   rechoisir ne déclenche rien. Après chaque action, `reset_selection`
   renvoie le panneau tel quel : le menu redevient vide et on peut
   relancer la même action sans retaper la commande.

2. Une action ne doit pas *remplacer* le panneau par un sous-menu :
   `send_panel` ouvre le sous-menu dans un nouveau message privé et
   retient comment le modifier plus tard.
"""

from __future__ import annotations

import logging
from typing import Any

import discord

LOGGER = logging.getLogger(__name__)


def remember_origin(view: discord.ui.View, interaction: discord.Interaction) -> None:
    """Le panneau a été envoyé en réponse à `interaction` : on pourra le modifier."""
    view.panel_origin = interaction  # type: ignore[attr-defined]


async def send_panel(
    interaction: discord.Interaction,
    *,
    view: discord.ui.View,
    ephemeral: bool = True,
    **kwargs: Any,
) -> None:
    """Envoie un panneau dans un nouveau message (privé par défaut)."""
    if interaction.response.is_done():
        message = await interaction.followup.send(view=view, ephemeral=ephemeral, wait=True, **kwargs)
        view.panel_message = message  # type: ignore[attr-defined]
        return

    await interaction.response.send_message(view=view, ephemeral=ephemeral, **kwargs)
    remember_origin(view, interaction)


async def reset_selection(view: discord.ui.View | None) -> None:
    """Remet les menus du panneau à zéro (sans rien changer d'autre)."""
    if view is None or view.is_finished():
        return

    origin = getattr(view, "panel_origin", None)
    message = getattr(view, "panel_message", None)

    try:
        if origin is not None:
            await origin.edit_original_response(view=view)
        elif message is not None:
            await message.edit(view=view)
    except (discord.HTTPException, ValueError, TypeError):
        # Panneau expiré ou supprimé : rien de grave, il suffit de le rouvrir.
        LOGGER.debug("Menu du panneau non remis à zéro", exc_info=True)


def first_value(select: Any, fallback: Any = None) -> Any:
    """
    Choix d'un menu dans un formulaire, sans planter s'il est resté vide.

    Discord n'envoie rien pour un menu non touché : on reprend alors
    l'option cochée par défaut (ou la valeur par défaut d'un menu de
    salons / rôles / membres), sinon `fallback`.
    """
    if select.values:
        return select.values[0]

    for option in getattr(select, "options", None) or []:
        if option.default:
            return option.value

    defaults = getattr(select, "default_values", None)

    if defaults:
        return defaults[0]

    return fallback

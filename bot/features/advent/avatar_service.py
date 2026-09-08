from __future__ import annotations

import logging

import discord


logger = logging.getLogger(__name__)


async def read_avatar(
    user: discord.User | discord.Member,
) -> bytes | None:
    """
    Télécharge l'avatar Discord en petite taille.

    Un problème de téléchargement ne doit jamais empêcher
    l'affichage du calendrier : None déclenche le médaillon
    de remplacement dessiné par Pillow.
    """
    try:
        asset = user.display_avatar.replace(
            size=128,
            static_format="png",
        )
        return await asset.read()
    except (
        discord.HTTPException,
        discord.InvalidArgument,
        OSError,
    ):
        logger.warning(
            "Impossible de télécharger l'avatar de %s",
            user.id,
            exc_info=True,
        )
        return None

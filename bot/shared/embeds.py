from __future__ import annotations

import discord


CLAN_RENARD_PINK = 0xE590B3
CLAN_RENARD_DARK = 0x2B172F
CLAN_RENARD_SUCCESS = 0x79C99E
CLAN_RENARD_ERROR = 0xD85C78
CLAN_RENARD_GOLD = 0xE7A2AF


def base_embed(
    title: str,
    description: str | None = None,
    *,
    colour: int = CLAN_RENARD_PINK,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour(colour),
    )
    embed.set_footer(text="Clan Renard • Calendrier de l'Avent")
    return embed


def success_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return base_embed(
        title,
        description,
        colour=CLAN_RENARD_SUCCESS,
    )


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return base_embed(
        title,
        description,
        colour=CLAN_RENARD_ERROR,
    )

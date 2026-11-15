from __future__ import annotations

from discord.ext import commands


def present_member_ids(
    bot: commands.Bot,
    guild_id: int,
) -> list[int] | None:
    """
    Identifiants des membres actuellement sur le serveur.

    Les classements et les rangs ignorent les membres partis : leurs
    données sont conservées et ils retrouvent leur place s'ils
    reviennent.

    Retourne None (aucun filtre) tant que la liste des membres n'est
    pas entièrement chargée, pour ne masquer personne à tort.
    """
    guild = bot.get_guild(guild_id)

    if guild is None or not guild.chunked:
        return None

    return [
        member.id
        for member in guild.members
    ]

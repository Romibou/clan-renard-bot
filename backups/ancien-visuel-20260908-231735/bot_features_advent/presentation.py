from __future__ import annotations

from typing import Any

import discord

from bot.features.advent.models import (
    AdventCampaign,
    CalendarState,
)
from bot.shared.embeds import (
    CLAN_RENARD_GOLD,
    CLAN_RENARD_PINK,
    base_embed,
)
from bot.shared.text import plural, truncate


def calendar_embed(
    state: CalendarState,
    member: discord.Member | discord.User,
    *,
    filename: str,
) -> discord.Embed:
    campaign = state.campaign

    if state.current_day is None:
        if state.today < campaign.start_date:
            availability = (
                "Le calendrier n'a pas encore commencé."
            )
        elif state.today > campaign.end_date:
            availability = (
                "La campagne est terminée."
            )
        else:
            availability = (
                "Aucune case n'est disponible actuellement."
            )
    elif state.current_day in state.opened_days:
        availability = (
            f"La case du jour, la **n°{state.current_day}**, "
            "a déjà été ouverte."
        )
    else:
        availability = (
            f"La case **n°{state.current_day}** est disponible !"
        )

    description = (
        f"Calendrier personnel de {member.mention}\n\n"
        f"{availability}\n\n"
        "Utilise les boutons sous ce message pour ouvrir ta case, "
        "actualiser l'image ou consulter tes récompenses."
    )

    embed = base_embed(
        f"🎄 {campaign.title} {campaign.year}",
        description,
        colour=CLAN_RENARD_PINK,
    )
    embed.set_image(
        url=f"attachment://{filename}"
    )

    opened_count = len(state.opened_days)
    missed_count = len(state.missed_days)

    embed.add_field(
        name="🎁 Progression",
        value=(
            f"**{opened_count}/24** "
            f"{plural(opened_count, 'case ouverte', 'cases ouvertes')}"
        ),
        inline=True,
    )
    embed.add_field(
        name="❌ Manquées",
        value=str(missed_count),
        inline=True,
    )
    embed.add_field(
        name="✨ Points",
        value=f"{state.total_points:,}".replace(",", " "),
        inline=True,
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    return embed


def profile_embed(
    state: CalendarState,
    member: discord.Member | discord.User,
) -> discord.Embed:
    opened = sorted(state.opened_days)
    missed = sorted(state.missed_days)

    opened_text = (
        ", ".join(str(day) for day in opened)
        if opened
        else "Aucune"
    )
    missed_text = (
        ", ".join(str(day) for day in missed)
        if missed
        else "Aucune"
    )

    embed = base_embed(
        f"🦊 Profil Avent de {truncate(member.display_name, 40)}",
        colour=CLAN_RENARD_PINK,
    )

    embed.add_field(
        name="Cases ouvertes",
        value=(
            f"**{len(opened)}/24**\n"
            f"{opened_text}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Cases manquées",
        value=(
            f"**{len(missed)}**\n"
            f"{missed_text}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Points remportés",
        value=(
            f"**{state.total_points:,}**"
            .replace(",", " ")
        ),
        inline=True,
    )

    if state.current_day is not None:
        day_status = f"Jour n°{state.current_day}"
    elif state.today < state.campaign.start_date:
        day_status = "Pas encore commencé"
    else:
        day_status = "Terminé"

    embed.add_field(
        name="État de la campagne",
        value=day_status,
        inline=True,
    )
    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    return embed


def reward_history_embed(
    campaign: AdventCampaign,
    member: discord.Member | discord.User,
    history: list[dict[str, Any]],
) -> discord.Embed:
    embed = base_embed(
        f"🎁 Récompenses de {truncate(member.display_name, 40)}",
        (
            f"Historique personnel pour le calendrier "
            f"**{campaign.year}**."
        ),
        colour=CLAN_RENARD_GOLD,
    )

    if not history:
        embed.add_field(
            name="Aucune récompense",
            value=(
                "Tu n'as encore ouvert aucune case "
                "sur cette campagne."
            ),
            inline=False,
        )
        return embed

    lines: list[str] = []

    for item in history:
        day = int(item["day"])
        reward_type = str(item["reward_type"])
        snapshot = item.get("snapshot", {})
        points = int(item.get("points", 0))

        if reward_type == "points":
            description = (
                f"{points} point"
                f"{'s' if points != 1 else ''}"
            )
        elif reward_type == "role":
            role_id = snapshot.get("role_id")
            description = (
                f"Rôle <@&{role_id}>"
                if role_id
                else "Rôle Discord"
            )

            status = item.get("external_status")

            if status == "failed":
                description += " ⚠️ attribution échouée"
            elif status == "pending":
                description += " ⏳ en attente"
        else:
            description = str(
                snapshot.get(
                    "message",
                    "Surprise du Clan Renard",
                )
            )

        lines.append(
            f"**Jour {day}** — "
            f"{truncate(description, 90)}"
        )

    # Un champ Discord ne peut pas dépasser 1024 caractères.
    current_chunk: list[str] = []
    current_size = 0
    part = 1

    for line in lines:
        additional_size = len(line) + 1

        if (
            current_chunk
            and current_size + additional_size > 950
        ):
            embed.add_field(
                name=(
                    "Récompenses"
                    if part == 1
                    else f"Récompenses — suite {part}"
                ),
                value="\n".join(current_chunk),
                inline=False,
            )
            current_chunk = []
            current_size = 0
            part += 1

        current_chunk.append(line)
        current_size += additional_size

    if current_chunk:
        embed.add_field(
            name=(
                "Récompenses"
                if part == 1
                else f"Récompenses — suite {part}"
            ),
            value="\n".join(current_chunk),
            inline=False,
        )

    return embed


def leaderboard_embed(
    campaign: AdventCampaign,
    guild: discord.Guild,
    ranking: list[dict[str, int]],
) -> discord.Embed:
    embed = base_embed(
        f"🏆 Classement Avent {campaign.year}",
        (
            f"Classement du serveur **{guild.name}**.\n"
            "Les membres sont d'abord classés par nombre de cases "
            "ouvertes, puis par nombre de points."
        ),
        colour=CLAN_RENARD_GOLD,
    )

    if not ranking:
        embed.description = (
            f"{embed.description}\n\n"
            "Personne n'a encore ouvert de case."
        )
        return embed

    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉",
    }

    lines: list[str] = []

    for position, entry in enumerate(
        ranking,
        start=1,
    ):
        user_id = entry["user_id"]
        opened_count = entry["opened_count"]
        total_points = entry["total_points"]
        medal = medals.get(
            position,
            f"`{position:02d}.`",
        )

        member = guild.get_member(user_id)

        if member is not None:
            member_text = member.mention
        else:
            member_text = f"<@{user_id}>"

        lines.append(
            f"{medal} {member_text} — "
            f"**{opened_count}/24** case"
            f"{'s' if opened_count != 1 else ''} • "
            f"**{total_points:,}** point"
            f"{'s' if total_points != 1 else ''}"
            .replace(",", " ")
        )

    embed.add_field(
        name="Top 10",
        value="\n".join(lines),
        inline=False,
    )

    return embed


def help_embed() -> discord.Embed:
    embed = base_embed(
        "❔ Aide — Calendrier de l'Avent",
        (
            "Chaque membre possède son propre calendrier. "
            "Une nouvelle case devient disponible chaque jour "
            "pendant la campagne."
        ),
        colour=CLAN_RENARD_PINK,
    )

    embed.add_field(
        name="Commandes",
        value=(
            "`/avent` — affiche ton calendrier\n"
            "`/avent-ouvrir` — ouvre la case du jour\n"
            "`/avent-profil` — affiche ta progression\n"
            "`/avent-recompenses` — affiche tes gains\n"
            "`/avent-classement` — affiche le classement\n"
            "`/avent-aide` — affiche cette aide"
        ),
        inline=False,
    )
    embed.add_field(
        name="Cases",
        value=(
            "🎁 **Disponible** — peut être ouverte\n"
            "✅ **Ouverte** — récompense déjà obtenue\n"
            "🔒 **Verrouillée** — appartient au futur\n"
            "❌ **Manquée** — n'a pas été ouverte à temps"
        ),
        inline=False,
    )
    embed.add_field(
        name="Rattrapage",
        value=(
            "Le serveur peut autoriser ou interdire l'ouverture "
            "des anciennes cases. La configuration active est "
            "appliquée automatiquement."
        ),
        inline=False,
    )

    return embed

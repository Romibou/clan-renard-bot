"""
Textes personnalisables des annonces quotidiennes de l'Avent.

Sans réglage, l'annonce garde exactement le texte d'origine. Les
administrateurs peuvent changer le titre et le message par défaut,
le message de la dernière case, écrire un message spécial pour
certains jours, et choisir les jours où @everyone est mentionné.

Variables : {jour} {jours_restants} {titre} {serveur} {heure}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import discord

from bot.features.advent.models import AdventCampaign
from bot.shared.embeds import base_embed

DEFAULT_TITLE = "🎄 Jour {jour} — {titre}"
DEFAULT_MESSAGE = (
    "La case **n°{jour}** du calendrier de **Clan Renard** est maintenant disponible !\n\n"
    "Clique sur le bouton ci-dessous pour ouvrir ta case personnelle et découvrir ta récompense."
)
DEFAULT_LAST_MESSAGE = (
    "La grande case **n°{jour}** est enfin disponible ! 🎉\n\n"
    "Clique sur le bouton ci-dessous pour découvrir la dernière surprise du calendrier de Clan Renard."
)
LAST_DAY = 24

MAX_TITLE = 200
MAX_MESSAGE = 3000

VARIABLES_HELP = (
    "`{jour}` numéro du jour · `{jours_restants}` jours avant la dernière case\n"
    "`{titre}` titre de la campagne · `{serveur}` nom du serveur · `{heure}` heure d'ouverture"
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS advent_announcement_texts (
    campaign_id BIGINT PRIMARY KEY
        REFERENCES advent_campaigns(id) ON DELETE CASCADE,
    title TEXT,
    message TEXT,
    last_message TEXT,
    day_messages JSONB NOT NULL DEFAULT '{}'::JSONB,
    everyone_days SMALLINT[] NOT NULL DEFAULT '{}',
    show_opening BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


@dataclass
class AnnouncementTexts:
    title: str | None = None
    message: str | None = None
    last_message: str | None = None
    day_messages: dict[int, str] = field(default_factory=dict)
    everyone_days: set[int] = field(default_factory=set)
    show_opening: bool = True

    def template_for(self, day: int) -> str:
        """Message du jour : spécial s'il existe, sinon celui par défaut."""
        if day in self.day_messages:
            return self.day_messages[day]

        if day == LAST_DAY:
            return self.last_message or DEFAULT_LAST_MESSAGE

        return self.message or DEFAULT_MESSAGE

    def is_default(self) -> bool:
        return (
            not self.title
            and not self.message
            and not self.last_message
            and not self.day_messages
            and not self.everyone_days
            and self.show_opening
        )


def fill(template: str, *, campaign: AdventCampaign, day: int, guild_name: str) -> str:
    values = {
        "{jour}": str(day),
        "{jours_restants}": str(max(0, LAST_DAY - day)),
        "{titre}": campaign.title,
        "{serveur}": guild_name,
        "{heure}": f"{campaign.opening_hour:02d}:00",
    }

    for key, value in values.items():
        template = template.replace(key, value)

    return template


def build_announcement(
    *,
    campaign: AdventCampaign,
    day: int,
    texts: AnnouncementTexts,
    guild_name: str,
    role: discord.Role | None,
) -> dict[str, Any]:
    """Contenu, cadre et mentions autorisées de l'annonce d'un jour."""
    title = fill(texts.title or DEFAULT_TITLE, campaign=campaign, day=day, guild_name=guild_name)
    description = fill(texts.template_for(day), campaign=campaign, day=day, guild_name=guild_name)
    embed = base_embed(title[:256], description[:4096])

    if texts.show_opening:
        embed.add_field(
            name="Ouverture",
            value=(
                f"Disponible depuis **{campaign.opening_hour:02d}:00** "
                f"dans le fuseau `{campaign.timezone}`."
            ),
            inline=False,
        )

    everyone = day in texts.everyone_days
    mentions = []

    if everyone:
        mentions.append("@everyone")
    elif role is not None:
        mentions.append(role.mention)

    return {
        "content": " ".join(mentions) or None,
        "embed": embed,
        "allowed_mentions": discord.AllowedMentions(
            everyone=everyone,
            users=False,
            roles=role is not None and not everyone,
            replied_user=False,
        ),
    }


def parse_days(text: str) -> set[int]:
    """« 1, 6, 24 » ou « 1 6 24 » → {1, 6, 24}."""
    days: set[int] = set()

    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue

        if not token.isdigit() or not 1 <= int(token) <= LAST_DAY:
            raise ValueError(f"« {token[:10]} » n'est pas un jour entre 1 et {LAST_DAY}.")

        days.add(int(token))

    return days


def format_days(days: set[int]) -> str:
    return ", ".join(str(day) for day in sorted(days))


# ------------------------------------------------------------
# BASE DE DONNÉES
# ------------------------------------------------------------


class AnnouncementTextsRepository:
    def __init__(self, pool_getter) -> None:
        self._pool_getter = pool_getter
        self._ready = False

    async def _pool(self):
        pool = self._pool_getter()

        if not self._ready:
            await pool.execute(CREATE_TABLE)
            self._ready = True

        return pool

    async def get(self, campaign_id: int) -> AnnouncementTexts:
        pool = await self._pool()
        record = await pool.fetchrow(
            "SELECT * FROM advent_announcement_texts WHERE campaign_id = $1",
            campaign_id,
        )

        if record is None:
            return AnnouncementTexts()

        days = record["day_messages"]
        days = json.loads(days) if isinstance(days, str) else (days or {})

        return AnnouncementTexts(
            title=record["title"],
            message=record["message"],
            last_message=record["last_message"],
            day_messages={int(day): str(text) for day, text in days.items()},
            everyone_days={int(day) for day in record["everyone_days"] or []},
            show_opening=bool(record["show_opening"]),
        )

    async def save(self, campaign_id: int, texts: AnnouncementTexts) -> None:
        pool = await self._pool()
        await pool.execute(
            """
            INSERT INTO advent_announcement_texts
                (campaign_id, title, message, last_message, day_messages, everyone_days, show_opening)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::smallint[], $7)
            ON CONFLICT (campaign_id)
            DO UPDATE SET title = EXCLUDED.title,
                          message = EXCLUDED.message,
                          last_message = EXCLUDED.last_message,
                          day_messages = EXCLUDED.day_messages,
                          everyone_days = EXCLUDED.everyone_days,
                          show_opening = EXCLUDED.show_opening,
                          updated_at = NOW()
            """,
            campaign_id,
            texts.title,
            texts.message,
            texts.last_message,
            json.dumps({str(day): text for day, text in sorted(texts.day_messages.items())}, ensure_ascii=False),
            sorted(texts.everyone_days),
            texts.show_opening,
        )

    async def reset(self, campaign_id: int) -> None:
        pool = await self._pool()
        await pool.execute("DELETE FROM advent_announcement_texts WHERE campaign_id = $1", campaign_id)

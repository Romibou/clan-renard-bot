"""
Briques communes du système de modération : types de sanctions,
lecture des durées et de l'échelle automatique, contrôles de
hiérarchie et mise en forme des messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import discord

from bot.extensions.rappel import parse_duration

WARN = "warn"
MUTE = "mute"
KICK = "kick"
BAN = "ban"
FINE = "fine"
UNMUTE = "unmute"
UNBAN = "unban"

# Durée maximale d'une exclusion temporaire imposée par Discord.
MAXIMUM_MUTE = timedelta(days=28)
MAXIMUM_BAN = timedelta(days=365)

ACTION_LABELS = {
    WARN: ("⚠️", "Avertissement"),
    MUTE: ("🔇", "Exclusion temporaire"),
    KICK: ("👢", "Expulsion"),
    BAN: ("🔨", "Bannissement"),
    FINE: ("💸", "Amende"),
    UNMUTE: ("🔊", "Fin d'exclusion"),
    UNBAN: ("🕊️", "Débannissement"),
}

ACTION_COLORS = {
    WARN: discord.Color.from_rgb(255, 196, 64),
    MUTE: discord.Color.from_rgb(255, 151, 84),
    KICK: discord.Color.from_rgb(255, 116, 125),
    BAN: discord.Color.from_rgb(200, 40, 60),
    FINE: discord.Color.from_rgb(188, 120, 255),
    UNMUTE: discord.Color.from_rgb(88, 191, 126),
    UNBAN: discord.Color.from_rgb(88, 191, 126),
}

# Phrase envoyée au membre en message privé.
DM_PHRASES = {
    WARN: "Tu as reçu un **avertissement**",
    MUTE: "Tu as été **exclu temporairement** (tu ne peux plus écrire ni parler)",
    KICK: "Tu as été **expulsé**",
    BAN: "Tu as été **banni**",
    FINE: "Tu as reçu une **amende**",
}

# Sanctions qu'un membre peut contester avec le bouton du message privé.
APPEALABLE = {WARN, MUTE, BAN, FINE}

DEFAULT_ESCALATION = "3 = mute 1h\n5 = mute 1j\n7 = ban 7j"
DEFAULT_WARN_EXPIRY_DAYS = 30


def label(action: str) -> str:
    emoji, name = ACTION_LABELS.get(action, ("📌", action))
    return f"{emoji} {name}"


def format_duration(seconds: int | None) -> str:
    """3600 → « 1 h » ; None → « définitive »."""
    if not seconds:
        return "définitive"

    seconds = int(seconds)
    parts = []

    for unit, size in (("j", 86_400), ("h", 3_600), ("min", 60), ("s", 1)):
        value, seconds = divmod(seconds, size)

        if value:
            parts.append(f"{value} {unit}")

    return " ".join(parts[:2])


def parse_sanction_duration(
    text: str | None,
    *,
    maximum: timedelta,
) -> timedelta | None:
    """
    Durée d'une sanction : « 10m », « 2h », « 7j », « 1sem »…
    Vide → None (sanction sans fin). Lève ValueError si invalide.
    """
    if text is None or not text.strip():
        return None

    duration = parse_duration(text)

    if duration is None or duration < timedelta(seconds=30):
        raise ValueError(
            f"Durée « {text} » incomprise. Exemples : 10m, 2h, 3j, 1sem."
        )

    if duration > maximum:
        raise ValueError(
            f"Durée trop longue : {format_duration(int(maximum.total_seconds()))} "
            "au maximum."
        )

    return duration


# ------------------------------------------------------------------
# Échelle de sanctions automatiques
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EscalationStep:
    warns: int
    action: str
    duration: timedelta | None

    def describe(self) -> str:
        if self.action == MUTE:
            return f"exclusion de {format_duration(int(self.duration.total_seconds()))}"

        if self.action == BAN:
            return (
                f"bannissement de {format_duration(int(self.duration.total_seconds()))}"
                if self.duration
                else "bannissement définitif"
            )

        return "expulsion"


ESCALATION_LINE = re.compile(
    r"^\s*(?P<warns>\d+)\s*(?:avertissements?|warns?)?\s*[=:→>-]+\s*"
    r"(?P<action>mute|kick|ban|exclusion|expulsion|bannissement)"
    r"(?:\s+(?P<duration>\S+))?\s*$",
    re.IGNORECASE,
)

ACTION_ALIASES = {
    "mute": MUTE,
    "exclusion": MUTE,
    "kick": KICK,
    "expulsion": KICK,
    "ban": BAN,
    "bannissement": BAN,
}


def parse_escalation(text: str) -> list[EscalationStep]:
    """
    Une ligne par palier :

        3 = mute 1h
        5 = kick
        7 = ban 7j
        9 = ban          (définitif)
    """
    steps: dict[int, EscalationStep] = {}

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        match = ESCALATION_LINE.match(line)

        if match is None:
            raise ValueError(
                f"Ligne {number} incomprise : « {line.strip()} ». "
                "Exemple : 3 = mute 1h"
            )

        warns = int(match["warns"])
        action = ACTION_ALIASES[match["action"].lower()]
        duration = None

        if not 1 <= warns <= 50:
            raise ValueError(f"Ligne {number} : entre 1 et 50 avertissements.")

        if action == MUTE:
            duration = parse_sanction_duration(
                match["duration"] or "",
                maximum=MAXIMUM_MUTE,
            )

            if duration is None:
                raise ValueError(f"Ligne {number} : indique la durée du mute.")

        elif action == BAN and match["duration"]:
            duration = parse_sanction_duration(
                match["duration"],
                maximum=MAXIMUM_BAN,
            )

        steps[warns] = EscalationStep(warns, action, duration)

    return [steps[key] for key in sorted(steps)]


def escalation_to_text(steps: list[EscalationStep]) -> str:
    lines = []

    for step in steps:
        line = f"{step.warns} = {step.action}"

        if step.duration is not None:
            line += f" {format_duration(int(step.duration.total_seconds())).replace(' ', '')}"

        lines.append(line)

    return "\n".join(lines)


def steps_from_json(data: Any) -> list[EscalationStep]:
    steps = []

    for item in data or []:
        duration = item.get("duration")
        steps.append(
            EscalationStep(
                warns=int(item["warns"]),
                action=str(item["action"]),
                duration=timedelta(seconds=int(duration)) if duration else None,
            )
        )

    return sorted(steps, key=lambda step: step.warns)


def steps_to_json(steps: list[EscalationStep]) -> list[dict[str, Any]]:
    return [
        {
            "warns": step.warns,
            "action": step.action,
            "duration": int(step.duration.total_seconds()) if step.duration else None,
        }
        for step in steps
    ]


def step_for(steps: list[EscalationStep], warns: int) -> EscalationStep | None:
    return next((step for step in steps if step.warns == warns), None)


def next_step(steps: list[EscalationStep], warns: int) -> EscalationStep | None:
    return next((step for step in steps if step.warns > warns), None)


# ------------------------------------------------------------------
# Hiérarchie
# ------------------------------------------------------------------


def hierarchy_error(
    moderator: discord.Member,
    target: discord.Member,
    *,
    needs_bot_power: bool,
) -> str | None:
    """
    Raison pour laquelle ce modérateur ne peut pas sanctionner ce
    membre, ou None si c'est possible.
    """
    guild = target.guild
    me = guild.me

    if target.id == moderator.id:
        return "Tu ne peux pas te sanctionner toi-même."

    if me is not None and target.id == me.id:
        return "Je ne peux pas me sanctionner moi-même."

    if target.id == guild.owner_id:
        return "Le propriétaire du serveur ne peut pas être sanctionné."

    if moderator.id != guild.owner_id and target.top_role >= moderator.top_role:
        return (
            f"{target.mention} a un rôle égal ou supérieur au tien : "
            "tu ne peux pas le sanctionner."
        )

    if needs_bot_power and me is not None and target.top_role >= me.top_role:
        return (
            f"{target.mention} a un rôle égal ou supérieur au mien : "
            "place mon rôle plus haut dans la liste des rôles."
        )

    return None


# ------------------------------------------------------------------
# Messages
# ------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def case_embed(
    case: dict[str, Any],
    *,
    title: str | None = None,
) -> discord.Embed:
    """Fiche d'une sanction, pour le journal et les confirmations."""
    action = str(case["action"])
    embed = discord.Embed(
        title=title or f"{label(action)} • cas n°{case['id']}",
        color=ACTION_COLORS.get(action, discord.Color.light_grey()),
        timestamp=case.get("created_at") or utc_now(),
    )
    embed.add_field(name="Membre", value=f"<@{case['user_id']}>", inline=True)
    embed.add_field(
        name="Par",
        value=(
            f"<@{case['moderator_id']}>"
            if case.get("moderator_id")
            else "🤖 Modération automatique"
        ),
        inline=True,
    )

    if case.get("duration_seconds"):
        embed.add_field(
            name="Durée",
            value=format_duration(case["duration_seconds"]),
            inline=True,
        )

    if case.get("amount"):
        embed.add_field(
            name="Montant",
            value=f"{int(case['amount']):,} pièces".replace(",", " "),
            inline=True,
        )

    embed.add_field(
        name="Raison",
        value=str(case.get("reason") or "Aucune raison indiquée.")[:1024],
        inline=False,
    )

    return embed


def dm_embed(
    case: dict[str, Any],
    guild_name: str,
    *,
    appeal_possible: bool,
) -> discord.Embed:
    action = str(case["action"])
    lines = [
        f"{DM_PHRASES.get(action, label(action))} sur **{guild_name}**.",
        "",
        f"**Raison :** {case.get('reason') or 'aucune raison indiquée'}",
    ]

    if case.get("duration_seconds"):
        lines.append(f"**Durée :** {format_duration(case['duration_seconds'])}")

        if case.get("expires_at"):
            lines.append(f"**Fin :** <t:{int(case['expires_at'].timestamp())}:R>")

    if case.get("amount"):
        lines.append(
            f"**Montant :** {int(case['amount']):,} pièces".replace(",", " ")
        )

    lines.append(f"**Cas n°{case['id']}**")

    if appeal_possible:
        lines += [
            "",
            "Si tu penses que c'est une erreur, tu peux **contester** cette "
            "sanction avec le bouton ci-dessous. L'équipe de modération "
            "examinera ta demande.",
        ]

    return discord.Embed(
        title=label(action),
        description="\n".join(lines),
        color=ACTION_COLORS.get(action, discord.Color.light_grey()),
    )

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from bot.shared.statistics_card import (
    BLUE_ACCENT,
    CARD_WIDTH,
    GOLD_ACCENT,
    GREEN_ACCENT,
    MUTED_TEXT_COLOR,
    ORANGE_ACCENT,
    PANEL_COLOR,
    PINK_ACCENT,
    PURPLE_ACCENT,
    RED_ACCENT,
    SECONDARY_TEXT_COLOR,
    TEXT_COLOR,
    _draw_avatar,
    _draw_stat_card,
    _load_background,
    _load_font,
    _truncate_text,
)


@dataclass(frozen=True, slots=True)
class RecapStats:
    year: int
    xp_gained: int
    year_rank: int | None
    ranked_members: int
    rewarded_messages: int
    voice_minutes: int
    coins_gained: int
    best_day: str | None
    best_day_xp: int
    daily_claims: int
    best_streak: int
    advent_openings: int | None
    stats_since: str | None


def format_number(value: int) -> str:
    return f"{max(0, int(value)):,}".replace(",", " ")


def format_voice(minutes: int) -> str:
    hours, rest = divmod(max(0, int(minutes)), 60)

    if hours == 0:
        return f"{rest} min"

    return f"{format_number(hours)} h {rest:02d}"


def build_recap_cards(stats: RecapStats) -> list[tuple[str, str, tuple]]:
    """Les 9 cases de la carte : (titre, valeur, couleur)."""
    rank = (
        f"#{stats.year_rank} sur {stats.ranked_members}"
        if stats.year_rank is not None
        else "Non classé"
    )
    best_day = (
        f"{stats.best_day} • {format_number(stats.best_day_xp)} XP"
        if stats.best_day is not None and stats.best_day_xp > 0
        else "—"
    )
    advent = (
        f"{stats.advent_openings}/24 cases"
        if stats.advent_openings is not None
        else "—"
    )
    streak = (
        f"{format_number(stats.best_streak)} jour"
        f"{'s' if stats.best_streak > 1 else ''}"
    )

    return [
        ("XP GAGNÉE", f"{format_number(stats.xp_gained)} XP", PURPLE_ACCENT),
        ("CLASSEMENT DE L'ANNÉE", rank, GOLD_ACCENT),
        ("MESSAGES", format_number(stats.rewarded_messages), BLUE_ACCENT),
        ("TEMPS EN VOCAL", format_voice(stats.voice_minutes), GREEN_ACCENT),
        ("PIÈCES GAGNÉES", format_number(stats.coins_gained), GOLD_ACCENT),
        ("JOUR LE PLUS ACTIF", best_day, PINK_ACCENT),
        ("RÉCOMPENSES QUOTIDIENNES", format_number(stats.daily_claims), ORANGE_ACCENT),
        ("MEILLEURE SÉRIE", streak, RED_ACCENT),
        ("CALENDRIER DE L'AVENT", advent, PINK_ACCENT),
    ]


def render_recap_card(
    *,
    display_name: str,
    avatar_bytes: bytes | None,
    stats: RecapStats,
    background_path: str | Path | None = None,
) -> io.BytesIO:
    image = _load_background(background_path)
    image = Image.alpha_composite(
        image,
        Image.new("RGBA", image.size, (11, 8, 22, 160)),
    )
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (38, 30, CARD_WIDTH - 38, 184),
        radius=28,
        fill=PANEL_COLOR,
        outline=(255, 255, 255, 30),
        width=2,
    )

    _draw_avatar(image, avatar_bytes, x=67, y=56, size=102)

    title_font = _load_font(44, bold=True)
    name_font = _load_font(28, bold=True)
    subtitle_font = _load_font(19)

    draw.text(
        (200, 88),
        f"BILAN {stats.year}",
        font=title_font,
        fill=GOLD_ACCENT,
        anchor="ls",
    )
    draw.text(
        (200, 128),
        _truncate_text(draw, display_name, name_font, 900),
        font=name_font,
        fill=TEXT_COLOR,
        anchor="ls",
    )
    draw.text(
        (200, 160),
        "Ton année sur le Clan Renard",
        font=subtitle_font,
        fill=SECONDARY_TEXT_COLOR,
        anchor="ls",
    )

    cards = build_recap_cards(stats)
    left, top, gap = 38, 210, 20
    width = (CARD_WIDTH - 2 * left - 2 * gap) // 3
    height = 150

    for index, (label, value, accent) in enumerate(cards):
        row, column = divmod(index, 3)
        x = left + column * (width + gap)
        y = top + row * (height + gap)

        _draw_stat_card(
            draw,
            box=(x, y, x + width, y + height),
            label=label,
            value=_truncate_text(draw, value, _load_font(30, bold=True), width - 60),
            accent=accent,
        )

    footer = "Clan Renard"

    if stats.stats_since is not None:
        footer = f"Statistiques enregistrées depuis le {stats.stats_since} • {footer}"

    draw.text(
        (CARD_WIDTH // 2, 755),
        footer,
        font=_load_font(18),
        fill=MUTED_TEXT_COLOR,
        anchor="ms",
    )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", compress_level=3)
    output.seek(0)

    return output

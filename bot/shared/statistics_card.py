from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)


CARD_WIDTH = 1200
CARD_HEIGHT = 800

TEXT_COLOR = (250, 247, 255, 255)
SECONDARY_TEXT_COLOR = (211, 202, 224, 255)
MUTED_TEXT_COLOR = (171, 162, 188, 255)

PANEL_COLOR = (20, 14, 35, 205)
CARD_COLOR = (29, 20, 48, 215)
CARD_BORDER = (255, 255, 255, 32)

PINK_ACCENT = (241, 124, 184, 255)
PURPLE_ACCENT = (188, 120, 255, 255)
GOLD_ACCENT = (255, 195, 87, 255)
GREEN_ACCENT = (104, 216, 151, 255)
BLUE_ACCENT = (102, 179, 255, 255)
RED_ACCENT = (255, 116, 125, 255)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=32)
def _load_font(
    size: int,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    root = _project_root()

    if bold:
        candidates = [
            root / "assets/fonts/NotoSans-Bold.ttf",
            root / "assets/fonts/DejaVuSans-Bold.ttf",
            root / "assets/fonts/Montserrat-Bold.ttf",
            root / "assets/fonts/Poppins-Bold.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ]
    else:
        candidates = [
            root / "assets/fonts/NotoSans-Regular.ttf",
            root / "assets/fonts/DejaVuSans.ttf",
            root / "assets/fonts/Montserrat-Regular.ttf",
            root / "assets/fonts/Poppins-Regular.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]

    for candidate in candidates:
        if not candidate.is_file():
            continue

        try:
            return ImageFont.truetype(
                str(candidate),
                size=size,
            )
        except OSError:
            continue

    return ImageFont.load_default()


def _create_fallback_background() -> Image.Image:
    image = Image.new(
        "RGBA",
        (CARD_WIDTH, CARD_HEIGHT),
        (22, 13, 34, 255),
    )

    draw = ImageDraw.Draw(image)

    top_color = (60, 30, 76)
    bottom_color = (17, 11, 28)

    for y in range(CARD_HEIGHT):
        ratio = y / max(
            1,
            CARD_HEIGHT - 1,
        )

        red = int(
            top_color[0]
            + (
                bottom_color[0]
                - top_color[0]
            )
            * ratio
        )

        green = int(
            top_color[1]
            + (
                bottom_color[1]
                - top_color[1]
            )
            * ratio
        )

        blue = int(
            top_color[2]
            + (
                bottom_color[2]
                - top_color[2]
            )
            * ratio
        )

        draw.line(
            (0, y, CARD_WIDTH, y),
            fill=(red, green, blue, 255),
        )

    glow_layer = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    glow_draw = ImageDraw.Draw(
        glow_layer
    )

    glow_draw.ellipse(
        (-250, -280, 520, 460),
        fill=(225, 91, 165, 115),
    )

    glow_draw.ellipse(
        (
            CARD_WIDTH - 470,
            CARD_HEIGHT - 520,
            CARD_WIDTH + 250,
            CARD_HEIGHT + 170,
        ),
        fill=(120, 75, 220, 110),
    )

    glow_layer = glow_layer.filter(
        ImageFilter.GaussianBlur(110)
    )

    return Image.alpha_composite(
        image,
        glow_layer,
    )


@lru_cache(maxsize=8)
def _load_background_cached(
    path: str,
    modified_at: float,
) -> Image.Image:
    del modified_at

    try:
        with Image.open(path) as source:
            background = source.convert("RGBA")

        return ImageOps.fit(
            background,
            (CARD_WIDTH, CARD_HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    except (OSError, ValueError):
        return _create_fallback_background()


def _load_background(
    background_path: str | Path | None,
) -> Image.Image:
    if background_path is None:
        return _create_fallback_background()

    path = Path(background_path)

    if not path.is_file():
        return _create_fallback_background()

    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return _create_fallback_background()

    return _load_background_cached(
        str(path.resolve()),
        modified_at,
    ).copy()


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    box = draw.textbbox(
        (0, 0),
        str(text),
        font=font,
    )

    return box[2] - box[0]


def _truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    maximum_width: int,
) -> str:
    text = str(text).strip()

    if not text:
        return "Utilisateur inconnu"

    if _text_width(
        draw,
        text,
        font,
    ) <= maximum_width:
        return text

    ellipsis = "…"

    while text:
        candidate = (
            text.rstrip()
            + ellipsis
        )

        if _text_width(
            draw,
            candidate,
            font,
        ) <= maximum_width:
            return candidate

        text = text[:-1]

    return ellipsis


def _format_number(
    value: int,
) -> str:
    return f"{int(value):,}".replace(
        ",",
        " ",
    )


def _format_duration(
    minutes: int,
) -> str:
    minutes = max(
        0,
        int(minutes),
    )

    hours, remaining_minutes = divmod(
        minutes,
        60,
    )

    if hours <= 0:
        return f"{remaining_minutes} min"

    if remaining_minutes == 0:
        return f"{hours} h"

    return (
        f"{hours} h "
        f"{remaining_minutes:02d}"
    )


def _format_rank(
    rank: int | None,
) -> str:
    if rank is None or rank <= 0:
        return "Non classé"

    return f"#{rank}"


def _format_rank_change(
    change: int | None,
) -> tuple[str, tuple[int, int, int, int]]:
    if change is None:
        return "Variation indisponible", MUTED_TEXT_COLOR

    if change > 0:
        return (
            f"▲ {change} place"
            if change == 1
            else f"▲ {change} places",
            GREEN_ACCENT,
        )

    if change < 0:
        lost = abs(change)

        return (
            f"▼ {lost} place"
            if lost == 1
            else f"▼ {lost} places",
            RED_ACCENT,
        )

    return "— Aucune variation", MUTED_TEXT_COLOR


def _draw_avatar(
    image: Image.Image,
    avatar_bytes: bytes | None,
    *,
    x: int,
    y: int,
    size: int,
) -> None:
    if avatar_bytes is None:
        avatar = Image.new(
            "RGBA",
            (size, size),
            (77, 55, 94, 255),
        )
    else:
        try:
            with Image.open(
                io.BytesIO(avatar_bytes)
            ) as source:
                avatar = source.convert("RGBA")

            avatar = ImageOps.fit(
                avatar,
                (size, size),
                method=Image.Resampling.LANCZOS,
            )
        except (OSError, ValueError):
            avatar = Image.new(
                "RGBA",
                (size, size),
                (77, 55, 94, 255),
            )

    mask = Image.new(
        "L",
        (size, size),
        0,
    )

    mask_draw = ImageDraw.Draw(mask)

    mask_draw.ellipse(
        (0, 0, size - 1, size - 1),
        fill=255,
    )

    border_size = size + 12

    border = Image.new(
        "RGBA",
        (border_size, border_size),
        (0, 0, 0, 0),
    )

    border_draw = ImageDraw.Draw(
        border
    )

    border_draw.ellipse(
        (
            0,
            0,
            border_size - 1,
            border_size - 1,
        ),
        fill=PINK_ACCENT,
    )

    image.alpha_composite(
        border,
        (
            x - 6,
            y - 6,
        ),
    )

    image.paste(
        avatar,
        (x, y),
        mask,
    )


def _draw_stat_card(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    accent: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box

    draw.rounded_rectangle(
        box,
        radius=22,
        fill=CARD_COLOR,
        outline=CARD_BORDER,
        width=2,
    )

    draw.rounded_rectangle(
        (
            left + 17,
            top + 18,
            left + 25,
            bottom - 18,
        ),
        radius=4,
        fill=accent,
    )

    label_font = _load_font(
        18,
        bold=True,
    )

    value_font = _load_font(
        30,
        bold=True,
    )

    draw.text(
        (
            left + 43,
            top + 17,
        ),
        label.upper(),
        font=label_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    draw.text(
        (
            left + 43,
            top + 49,
        ),
        value,
        font=value_font,
        fill=TEXT_COLOR,
    )


def _draw_rank_card(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    title: str,
    rank: int | None,
    change: int | None,
    accent: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box

    draw.rounded_rectangle(
        box,
        radius=22,
        fill=CARD_COLOR,
        outline=CARD_BORDER,
        width=2,
    )

    draw.rounded_rectangle(
        (
            left + 17,
            top + 18,
            left + 25,
            bottom - 18,
        ),
        radius=4,
        fill=accent,
    )

    title_font = _load_font(
        18,
        bold=True,
    )

    rank_font = _load_font(
        34,
        bold=True,
    )

    variation_font = _load_font(
        17,
        bold=True,
    )

    draw.text(
        (
            left + 43,
            top + 16,
        ),
        title.upper(),
        font=title_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    draw.text(
        (
            left + 43,
            top + 47,
        ),
        _format_rank(rank),
        font=rank_font,
        fill=TEXT_COLOR,
    )

    variation_text, variation_color = (
        _format_rank_change(change)
    )

    variation_width = _text_width(
        draw,
        variation_text,
        variation_font,
    )

    draw.text(
        (
            right - variation_width - 22,
            top + 59,
        ),
        variation_text,
        font=variation_font,
        fill=variation_color,
    )


def render_statistics_card(
    *,
    display_name: str,
    avatar_bytes: bytes | None,
    period_label: str,
    level: int,
    total_xp: int,
    wallet: int,
    xp_to_next_level: int,
    xp_gained: int,
    coins_gained: int,
    coins_spent: int,
    rewarded_messages: int,
    voice_minutes: int,
    xp_rank: int | None,
    money_rank: int | None,
    xp_rank_change: int | None,
    money_rank_change: int | None,
    background_path: str | Path | None = None,
) -> io.BytesIO:
    image = _load_background(
        background_path
    )

    overlay = Image.new(
        "RGBA",
        image.size,
        (11, 8, 22, 145),
    )

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(image)

    title_font = _load_font(
        42,
        bold=True,
    )

    username_font = _load_font(
        30,
        bold=True,
    )

    period_font = _load_font(
        19,
        bold=True,
    )

    summary_font = _load_font(
        20,
        bold=False,
    )

    draw.rounded_rectangle(
        (
            38,
            30,
            CARD_WIDTH - 38,
            184,
        ),
        radius=28,
        fill=PANEL_COLOR,
        outline=(255, 255, 255, 30),
        width=2,
    )

    _draw_avatar(
        image,
        avatar_bytes,
        x=67,
        y=56,
        size=102,
    )

    fitted_name = _truncate_text(
        draw,
        display_name,
        username_font,
        565,
    )

    draw.text(
        (205, 54),
        fitted_name,
        font=username_font,
        fill=TEXT_COLOR,
    )

    draw.text(
        (205, 101),
        (
            f"Niveau {_format_number(level)}"
            f"  •  "
            f"{_format_number(total_xp)} XP"
            f"  •  "
            f"{_format_number(wallet)} pièces"
        ),
        font=summary_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    period_width = _text_width(
        draw,
        period_label,
        period_font,
    )

    period_left = (
        CARD_WIDTH
        - 67
        - period_width
        - 38
    )

    draw.rounded_rectangle(
        (
            period_left,
            72,
            CARD_WIDTH - 67,
            121,
        ),
        radius=16,
        fill=(119, 55, 105, 220),
        outline=(255, 183, 220, 90),
        width=2,
    )

    draw.text(
        (
            period_left + 19,
            84,
        ),
        period_label,
        font=period_font,
        fill=(255, 221, 238, 255),
    )

    draw.text(
        (48, 216),
        "PROGRESSION SUR LA PÉRIODE",
        font=title_font,
        fill=TEXT_COLOR,
    )

    first_column_left = 38
    first_column_right = 402

    second_column_left = 418
    second_column_right = 782

    third_column_left = 798
    third_column_right = 1162

    first_row_top = 282
    first_row_bottom = 396

    second_row_top = 412
    second_row_bottom = 526

    _draw_stat_card(
        draw,
        box=(
            first_column_left,
            first_row_top,
            first_column_right,
            first_row_bottom,
        ),
        label="XP gagnée",
        value=(
            f"+{_format_number(xp_gained)} XP"
        ),
        accent=PURPLE_ACCENT,
    )

    _draw_stat_card(
        draw,
        box=(
            second_column_left,
            first_row_top,
            second_column_right,
            first_row_bottom,
        ),
        label="Pièces gagnées",
        value=(
            f"+{_format_number(coins_gained)}"
        ),
        accent=GOLD_ACCENT,
    )

    _draw_stat_card(
        draw,
        box=(
            third_column_left,
            first_row_top,
            third_column_right,
            first_row_bottom,
        ),
        label="Pièces dépensées",
        value=(
            f"-{_format_number(coins_spent)}"
        ),
        accent=RED_ACCENT,
    )

    _draw_stat_card(
        draw,
        box=(
            first_column_left,
            second_row_top,
            first_column_right,
            second_row_bottom,
        ),
        label="Messages récompensés",
        value=_format_number(
            rewarded_messages
        ),
        accent=PINK_ACCENT,
    )

    _draw_stat_card(
        draw,
        box=(
            second_column_left,
            second_row_top,
            second_column_right,
            second_row_bottom,
        ),
        label="Temps vocal récompensé",
        value=_format_duration(
            voice_minutes
        ),
        accent=BLUE_ACCENT,
    )

    _draw_stat_card(
        draw,
        box=(
            third_column_left,
            second_row_top,
            third_column_right,
            second_row_bottom,
        ),
        label="Activités récompensées",
        value=_format_number(
            rewarded_messages
            + voice_minutes
        ),
        accent=GREEN_ACCENT,
    )

    draw.text(
        (48, 558),
        "CLASSEMENTS ACTUELS",
        font=title_font,
        fill=TEXT_COLOR,
    )

    _draw_rank_card(
        draw,
        box=(
            38,
            624,
            590,
            758,
        ),
        title="Classement XP",
        rank=xp_rank,
        change=xp_rank_change,
        accent=PURPLE_ACCENT,
    )

    _draw_rank_card(
        draw,
        box=(
            610,
            624,
            1162,
            758,
        ),
        title="Classement argent",
        rank=money_rank,
        change=money_rank_change,
        accent=GOLD_ACCENT,
    )

    output = io.BytesIO()

    image.convert("RGB").save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(0)

    return output

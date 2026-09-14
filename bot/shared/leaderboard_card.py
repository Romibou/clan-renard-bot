from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


CARD_WIDTH = 1200
CARD_HEIGHT = 920

BACKGROUND_OVERLAY = (12, 9, 24, 155)

TEXT_COLOR = (250, 247, 255, 255)
SECONDARY_TEXT_COLOR = (207, 198, 220, 255)
MUTED_TEXT_COLOR = (166, 156, 180, 255)

HEADER_BACKGROUND = (18, 13, 31, 205)
ROW_BACKGROUND = (22, 16, 38, 188)
ROW_BORDER = (255, 255, 255, 32)

PERSONAL_BACKGROUND = (94, 43, 81, 225)
PERSONAL_BORDER = (245, 145, 194, 220)

XP_ACCENT = (197, 120, 255, 255)
MONEY_ACCENT = (255, 194, 91, 255)

GOLD_COLOR = (255, 206, 84, 255)
SILVER_COLOR = (205, 213, 225, 255)
BRONZE_COLOR = (205, 140, 91, 255)


def _font_candidates(
    *,
    bold: bool,
) -> list[str]:
    if bold:
        return [
            "assets/fonts/DejaVuSans-Bold.ttf",
            "assets/fonts/Montserrat-Bold.ttf",
            "assets/fonts/Poppins-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]

    return [
        "assets/fonts/DejaVuSans.ttf",
        "assets/fonts/Montserrat-Regular.ttf",
        "assets/fonts/Poppins-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]


@lru_cache(maxsize=32)
def _load_font(
    size: int,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    project_root = Path(__file__).resolve().parents[2]

    for candidate in _font_candidates(bold=bold):
        candidate_path = Path(candidate)

        if not candidate_path.is_absolute():
            candidate_path = project_root / candidate_path

        if not candidate_path.exists():
            continue

        try:
            return ImageFont.truetype(
                str(candidate_path),
                size=size,
            )
        except OSError:
            continue

    return ImageFont.load_default()




@lru_cache(maxsize=16)
def _load_username_font(
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    project_root = Path(__file__).resolve().parents[2]

    candidates = [
        project_root
        / "assets"
        / "fonts"
        / "NotoSansMath-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSans-Regular.ttf",

        Path(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),

        Path(
            "C:/Windows/Fonts/arial.ttf"
        ),
    ]

    for font_path in candidates:
        if not font_path.is_file():
            continue

        try:
            return ImageFont.truetype(
                str(font_path),
                size=size,
            )
        except OSError:
            continue

    LOGGER.warning(
        "Aucune police Unicode compatible trouvée pour les pseudos."
    )

    return ImageFont.load_default()




def _create_fallback_background() -> Image.Image:
    image = Image.new(
        "RGBA",
        (CARD_WIDTH, CARD_HEIGHT),
        (24, 14, 36, 255),
    )

    draw = ImageDraw.Draw(image)

    top_color = (51, 27, 69)
    bottom_color = (18, 12, 29)

    for y in range(CARD_HEIGHT):
        ratio = y / max(1, CARD_HEIGHT - 1)

        red = int(
            top_color[0]
            + (bottom_color[0] - top_color[0]) * ratio
        )
        green = int(
            top_color[1]
            + (bottom_color[1] - top_color[1]) * ratio
        )
        blue = int(
            top_color[2]
            + (bottom_color[2] - top_color[2]) * ratio
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
    glow_draw = ImageDraw.Draw(glow_layer)

    glow_draw.ellipse(
        (-250, -300, 500, 450),
        fill=(196, 95, 164, 115),
    )
    glow_draw.ellipse(
        (
            CARD_WIDTH - 430,
            CARD_HEIGHT - 500,
            CARD_WIDTH + 220,
            CARD_HEIGHT + 180,
        ),
        fill=(115, 70, 206, 100),
    )

    glow_layer = glow_layer.filter(
        ImageFilter.GaussianBlur(100)
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
        text,
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

    if _text_width(draw, text, font) <= maximum_width:
        return text

    ellipsis = "…"

    while text:
        candidate = text.rstrip() + ellipsis

        if _text_width(
            draw,
            candidate,
            font,
        ) <= maximum_width:
            return candidate

        text = text[:-1]

    return ellipsis


def _format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box

    text_box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]

    x = left + ((right - left) - text_width) / 2
    y = top + ((bottom - top) - text_height) / 2 - text_box[1]

    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
    )


def _draw_right_aligned_text(
    draw: ImageDraw.ImageDraw,
    *,
    right: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
) -> None:
    width = _text_width(
        draw,
        text,
        font,
    )

    draw.text(
        (right - width, y),
        text,
        font=font,
        fill=fill,
    )


def _rank_color(rank: int) -> tuple[int, int, int, int]:
    if rank == 1:
        return GOLD_COLOR

    if rank == 2:
        return SILVER_COLOR

    if rank == 3:
        return BRONZE_COLOR

    return TEXT_COLOR


def _rank_text(rank: int | None) -> str:
    if rank is None or rank <= 0:
        return "—"

    return f"#{rank}"


def _get_row_value(
    row: Mapping[str, Any],
    key: str,
    default: Any,
) -> Any:
    value = row.get(key, default)

    if value is None:
        return default

    return value


def render_leaderboard_card(
    *,
    ranking_type: str,
    page: int,
    total_pages: int,
    rows: Sequence[Mapping[str, Any]],
    personal_row: Mapping[str, Any],
    background_path: str | Path | None = None,
) -> io.BytesIO:
    """
    Génère une image de classement.

    Chaque élément de ``rows`` doit contenir :

    - ``rank`` : position dans le classement ;
    - ``display_name`` : nom affiché du membre ;
    - ``value`` : quantité d'XP ou d'argent.

    ``personal_row`` utilise les mêmes clés. Son rang peut être ``None``
    lorsque le membre ne possède encore aucune entrée en base.
    """

    normalized_type = str(ranking_type).lower().strip()

    if normalized_type not in {
        "xp",
        "money",
    }:
        normalized_type = "xp"

    page = max(1, int(page))
    total_pages = max(1, int(total_pages))
    page = min(page, total_pages)

    image = _load_background(background_path)

    overlay = Image.new(
        "RGBA",
        image.size,
        BACKGROUND_OVERLAY,
    )
    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(image)

    title_font = _load_font(50, bold=True)
    subtitle_font = _load_font(22)
    header_font = _load_font(21, bold=True)
    row_font = _load_font(25, bold=True)
    row_value_font = _load_font(24, bold=True)
    footer_label_font = _load_font(17, bold=True)
    footer_font = _load_font(23, bold=True)
    username_font = _load_username_font(25)
    personal_username_font = _load_username_font(23)


    if normalized_type == "money":
        title = "CLASSEMENT ARGENT"
        value_header = "ARGENT"
        value_suffix = " pièces"
        accent_color = MONEY_ACCENT
    else:
        title = "CLASSEMENT XP"
        value_header = "XP"
        value_suffix = " XP"
        accent_color = XP_ACCENT

    draw.rounded_rectangle(
        (38, 30, CARD_WIDTH - 38, 138),
        radius=26,
        fill=(16, 11, 28, 185),
        outline=(255, 255, 255, 28),
        width=2,
    )

    draw.rounded_rectangle(
        (56, 51, 67, 117),
        radius=6,
        fill=accent_color,
    )

    draw.text(
        (88, 47),
        title,
        font=title_font,
        fill=TEXT_COLOR,
    )

    page_text = f"PAGE {page} / {total_pages}"

    _draw_right_aligned_text(
        draw,
        right=CARD_WIDTH - 68,
        y=72,
        text=page_text,
        font=subtitle_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    header_top = 157
    header_bottom = 207

    draw.rounded_rectangle(
        (
            38,
            header_top,
            CARD_WIDTH - 38,
            header_bottom,
        ),
        radius=16,
        fill=HEADER_BACKGROUND,
        outline=(255, 255, 255, 30),
        width=2,
    )

    rank_column = (55, header_top, 205, header_bottom)
    user_column = (220, header_top, 835, header_bottom)
    value_column = (
        850,
        header_top,
        CARD_WIDTH - 55,
        header_bottom,
    )

    _draw_centered_text(
        draw,
        box=rank_column,
        text="RANG",
        font=header_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    draw.text(
        (250, 169),
        "UTILISATEUR",
        font=header_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    _draw_centered_text(
        draw,
        box=value_column,
        text=value_header,
        font=header_font,
        fill=SECONDARY_TEXT_COLOR,
    )

    row_start_y = 220
    row_height = 54
    row_gap = 7

    displayed_rows = list(rows[:10])

    for index in range(10):
        y = row_start_y + index * (
            row_height + row_gap
        )

        row = (
            displayed_rows[index]
            if index < len(displayed_rows)
            else None
        )

        draw.rounded_rectangle(
            (
                38,
                y,
                CARD_WIDTH - 38,
                y + row_height,
            ),
            radius=15,
            fill=ROW_BACKGROUND,
            outline=ROW_BORDER,
            width=2,
        )

        if row is None:
            continue

        rank = int(
            _get_row_value(
                row,
                "rank",
                index + 1,
            )
        )

        display_name = str(
            _get_row_value(
                row,
                "display_name",
                "Utilisateur inconnu",
            )
        )

        value = int(
            _get_row_value(
                row,
                "value",
                0,
            )
        )

        rank_value = _rank_text(rank)

        _draw_centered_text(
            draw,
            box=(
                55,
                y,
                205,
                y + row_height,
            ),
            text=rank_value,
            font=row_font,
            fill=_rank_color(rank),
        )

        fitted_name = _truncate_text(
            draw,
            display_name,
            username_font,
            560,
        )

        name_box = draw.textbbox(
            (0, 0),
            fitted_name,
            font=username_font,
        )

        name_height = name_box[3] - name_box[1]
        name_y = (
            y
            + (row_height - name_height) / 2
            - name_box[1]
        )

        draw.text(
            (250, name_y),
            fitted_name,
            font=username_font,
            fill=TEXT_COLOR,
        )

        formatted_value = (
            _format_number(value)
            + value_suffix
        )

        _draw_right_aligned_text(
            draw,
            right=CARD_WIDTH - 72,
            y=y + 13,
            text=formatted_value,
            font=row_value_font,
            fill=accent_color,
        )

    personal_top = 846
    personal_bottom = 902

    draw.rounded_rectangle(
        (
            38,
            personal_top,
            CARD_WIDTH - 38,
            personal_bottom,
        ),
        radius=17,
        fill=PERSONAL_BACKGROUND,
        outline=PERSONAL_BORDER,
        width=3,
    )

    personal_rank_raw = personal_row.get("rank")
    personal_rank = (
        int(personal_rank_raw)
        if personal_rank_raw is not None
        else None
    )

    personal_name = str(
        _get_row_value(
            personal_row,
            "display_name",
            "Utilisateur inconnu",
        )
    )

    personal_value = int(
        _get_row_value(
            personal_row,
            "value",
            0,
        )
    )

    draw.text(
        (58, personal_top + 5),
        "TON CLASSEMENT",
        font=footer_label_font,
        fill=(255, 201, 229, 255),
    )

    _draw_centered_text(
        draw,
        box=(
            55,
            personal_top + 18,
            205,
            personal_bottom,
        ),
        text=_rank_text(personal_rank),
        font=footer_font,
        fill=TEXT_COLOR,
    )

    fitted_personal_name = _truncate_text(
        draw,
        personal_name,
        personal_username_font,
        545,
    )

    draw.text(
        (250, personal_top + 20),
        fitted_personal_name,
        font=personal_username_font,
        fill=TEXT_COLOR,
    )

    formatted_personal_value = (
        _format_number(personal_value)
        + value_suffix
    )

    _draw_right_aligned_text(
        draw,
        right=CARD_WIDTH - 72,
        y=personal_top + 20,
        text=formatted_personal_value,
        font=footer_font,
        fill=accent_color,
    )

    output = io.BytesIO()

    image.convert("RGB").save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(0)

    return output

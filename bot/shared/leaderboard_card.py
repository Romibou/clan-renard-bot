from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)


LOGGER = logging.getLogger(__name__)

CARD_WIDTH = 1200
CARD_HEIGHT = 920

BACKGROUND_OVERLAY = (12, 9, 24, 155)

TEXT_COLOR = (250, 247, 255, 255)
SECONDARY_TEXT_COLOR = (207, 198, 220, 255)

HEADER_BACKGROUND = (18, 13, 31, 205)
ROW_BACKGROUND = (22, 16, 38, 188)
ROW_BORDER = (255, 255, 255, 32)

PERSONAL_BACKGROUND = (94, 43, 81, 225)
PERSONAL_BORDER = (245, 145, 194, 220)

XP_ACCENT = (197, 120, 255, 255)
MONEY_ACCENT = (255, 194, 91, 255)
STREAK_ACCENT = (255, 126, 76, 255)

GOLD_COLOR = (255, 206, 84, 255)
SILVER_COLOR = (205, 213, 225, 255)
BRONZE_COLOR = (205, 140, 91, 255)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _font_candidates(
    *,
    bold: bool,
) -> list[Path]:
    project_root = _project_root()

    if bold:
        return [
            project_root
            / "assets"
            / "fonts"
            / "DejaVuSans-Bold.ttf",

            project_root
            / "assets"
            / "fonts"
            / "NotoSans-Bold.ttf",

            project_root
            / "assets"
            / "fonts"
            / "Montserrat-Bold.ttf",

            project_root
            / "assets"
            / "fonts"
            / "Poppins-Bold.ttf",

            Path(
                "C:/Windows/Fonts/arialbd.ttf"
            ),

            Path(
                "C:/Windows/Fonts/segoeuib.ttf"
            ),

            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),

            Path(
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Bold.ttf"
            ),
        ]

    return [
        project_root
        / "assets"
        / "fonts"
        / "DejaVuSans.ttf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSans-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "Montserrat-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "Poppins-Regular.ttf",

        Path(
            "C:/Windows/Fonts/arial.ttf"
        ),

        Path(
            "C:/Windows/Fonts/segoeui.ttf"
        ),

        Path(
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf"
        ),

        Path(
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSans-Regular.ttf"
        ),
    ]


def _load_first_available_font(
    *,
    candidates: Sequence[Path],
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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

    return ImageFont.load_default()


@lru_cache(maxsize=32)
def _load_font(
    size: int,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _load_first_available_font(
        candidates=_font_candidates(
            bold=bold,
        ),
        size=size,
    )


@lru_cache(maxsize=16)
def _load_username_font(
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Police utilisée pour les pseudos classiques.
    """
    project_root = _project_root()

    candidates = [
        project_root
        / "assets"
        / "fonts"
        / "NotoSans-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "DejaVuSans.ttf",

        Path(
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf"
        ),

        Path(
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSans-Regular.ttf"
        ),

        Path(
            "C:/Windows/Fonts/segoeui.ttf"
        ),

        Path(
            "C:/Windows/Fonts/arial.ttf"
        ),
    ]

    loaded_font = _load_first_available_font(
        candidates=candidates,
        size=size,
    )

    if isinstance(
        loaded_font,
        ImageFont.FreeTypeFont,
    ):
        return loaded_font

    LOGGER.warning(
        (
            "Aucune police Unicode classique "
            "n'a été trouvée pour les pseudos."
        )
    )

    return loaded_font


@lru_cache(maxsize=16)
def _load_math_font(
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Police utilisée pour les lettres Unicode fantaisie.
    """
    project_root = _project_root()

    candidates = [
        project_root
        / "assets"
        / "fonts"
        / "NotoSansMath-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSansSymbols2-Regular.ttf",

        Path(
            "/usr/share/fonts/truetype/noto/"
            "NotoSansMath-Regular.ttf"
        ),

        Path(
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf"
        ),

        Path(
            "C:/Windows/Fonts/seguisym.ttf"
        ),

        Path(
            "C:/Windows/Fonts/segoeui.ttf"
        ),
    ]

    loaded_font = _load_first_available_font(
        candidates=candidates,
        size=size,
    )

    if isinstance(
        loaded_font,
        ImageFont.FreeTypeFont,
    ):
        return loaded_font

    LOGGER.warning(
        (
            "Aucune police Unicode mathématique "
            "n'a été trouvée pour les pseudos fantaisie."
        )
    )

    return _load_username_font(
        size
    )


@lru_cache(maxsize=16)
def _load_cjk_font(
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Police utilisée pour les caractères chinois,
    japonais et coréens.
    """
    project_root = _project_root()

    candidates = [
        project_root
        / "assets"
        / "fonts"
        / "NotoSansSC-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSansSC-VariableFont_wght.ttf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSansCJKsc-Regular.otf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSansCJK-Regular.ttc",

        project_root
        / "assets"
        / "fonts"
        / "NotoSansJP-Regular.ttf",

        project_root
        / "assets"
        / "fonts"
        / "NotoSansKR-Regular.ttf",

        Path(
            "/usr/share/fonts/opentype/noto/"
            "NotoSansCJK-Regular.ttc"
        ),

        Path(
            "/usr/share/fonts/opentype/noto/"
            "NotoSansCJKsc-Regular.otf"
        ),

        Path(
            "/usr/share/fonts/truetype/noto/"
            "NotoSansCJK-Regular.ttc"
        ),

        Path(
            "C:/Windows/Fonts/msyh.ttc"
        ),

        Path(
            "C:/Windows/Fonts/msyhbd.ttc"
        ),

        Path(
            "C:/Windows/Fonts/msgothic.ttc"
        ),

        Path(
            "C:/Windows/Fonts/meiryo.ttc"
        ),

        Path(
            "C:/Windows/Fonts/malgun.ttf"
        ),
    ]

    loaded_font = _load_first_available_font(
        candidates=candidates,
        size=size,
    )

    if isinstance(
        loaded_font,
        ImageFont.FreeTypeFont,
    ):
        return loaded_font

    LOGGER.warning(
        (
            "Aucune police CJK n'a été trouvée. "
            "Ajoute NotoSansSC-Regular.ttf "
            "dans assets/fonts."
        )
    )

    return _load_username_font(
        size
    )


def _contains_cjk(
    text: str,
) -> bool:
    """
    Détecte la présence de caractères chinois,
    japonais ou coréens.
    """
    for character in str(text):
        codepoint = ord(character)

        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x20000 <= codepoint <= 0x2A6DF
            or 0x2A700 <= codepoint <= 0x2B73F
            or 0x2B740 <= codepoint <= 0x2B81F
            or 0x2B820 <= codepoint <= 0x2CEAF
            or 0x2CEB0 <= codepoint <= 0x2EBEF
            or 0x30000 <= codepoint <= 0x3134F
            or 0x3040 <= codepoint <= 0x309F
            or 0x30A0 <= codepoint <= 0x30FF
            or 0x31F0 <= codepoint <= 0x31FF
            or 0xAC00 <= codepoint <= 0xD7AF
            or 0x1100 <= codepoint <= 0x11FF
            or 0x3130 <= codepoint <= 0x318F
        ):
            return True

    return False


def _contains_styled_characters(
    text: str,
) -> bool:
    """
    Détecte les lettres mathématiques ou fantaisie
    souvent utilisées dans les pseudos Discord.
    """
    for character in str(text):
        codepoint = ord(character)

        if (
            0x1D400 <= codepoint <= 0x1D7FF
            or 0x2100 <= codepoint <= 0x214F
            or 0x1D2C <= codepoint <= 0x1D7F
            or 0x1D80 <= codepoint <= 0x1DBF
            or 0x2460 <= codepoint <= 0x24FF
            or 0xFF00 <= codepoint <= 0xFFEF
        ):
            return True

    return False


def _get_username_font(
    text: str,
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Sélectionne automatiquement la meilleure police
    selon le contenu du pseudo.
    """
    normalized_text = str(
        text
    )

    if _contains_cjk(
        normalized_text
    ):
        return _load_cjk_font(
            size
        )

    if _contains_styled_characters(
        normalized_text
    ):
        return _load_math_font(
            size
        )

    return _load_username_font(
        size
    )


def _create_fallback_background() -> Image.Image:
    image = Image.new(
        "RGBA",
        (
            CARD_WIDTH,
            CARD_HEIGHT,
        ),
        (
            24,
            14,
            36,
            255,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    top_color = (
        51,
        27,
        69,
    )

    bottom_color = (
        18,
        12,
        29,
    )

    for y in range(
        CARD_HEIGHT
    ):
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
            (
                0,
                y,
                CARD_WIDTH,
                y,
            ),
            fill=(
                red,
                green,
                blue,
                255,
            ),
        )

    glow_layer = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    glow_draw = ImageDraw.Draw(
        glow_layer
    )

    glow_draw.ellipse(
        (
            -250,
            -300,
            500,
            450,
        ),
        fill=(
            196,
            95,
            164,
            115,
        ),
    )

    glow_draw.ellipse(
        (
            CARD_WIDTH - 430,
            CARD_HEIGHT - 500,
            CARD_WIDTH + 220,
            CARD_HEIGHT + 180,
        ),
        fill=(
            115,
            70,
            206,
            100,
        ),
    )

    glow_layer = glow_layer.filter(
        ImageFilter.GaussianBlur(
            100
        )
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
        with Image.open(
            path
        ) as source:
            background = source.convert(
                "RGBA"
            )

        return ImageOps.fit(
            background,
            (
                CARD_WIDTH,
                CARD_HEIGHT,
            ),
            method=Image.Resampling.LANCZOS,
            centering=(
                0.5,
                0.5,
            ),
        )

    except (
        OSError,
        ValueError,
    ):
        return _create_fallback_background()


def _load_background(
    background_path: str | Path | None,
) -> Image.Image:
    if background_path is None:
        return _create_fallback_background()

    path = Path(
        background_path
    )

    if not path.is_file():
        return _create_fallback_background()

    try:
        modified_at = (
            path.stat().st_mtime
        )
    except OSError:
        return _create_fallback_background()

    return _load_background_cached(
        str(
            path.resolve()
        ),
        modified_at,
    ).copy()


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    box = draw.textbbox(
        (
            0,
            0,
        ),
        str(text),
        font=font,
    )

    return (
        box[2]
        - box[0]
    )


def _truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    maximum_width: int,
) -> str:
    text = str(
        text
    ).strip()

    if not text:
        return "Utilisateur inconnu"

    if (
        _text_width(
            draw,
            text,
            font,
        )
        <= maximum_width
    ):
        return text

    ellipsis = "…"

    while text:
        candidate = (
            text.rstrip()
            + ellipsis
        )

        if (
            _text_width(
                draw,
                candidate,
                font,
            )
            <= maximum_width
        ):
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


def _format_value(
    value: int,
    ranking_type: str,
) -> str:
    normalized_value = max(
        0,
        int(value),
    )

    formatted_value = _format_number(
        normalized_value
    )

    if ranking_type == "money":
        return (
            f"{formatted_value} pièces"
        )

    if ranking_type == "streak":
        suffix = (
            "jour"
            if normalized_value == 1
            else "jours"
        )

        return (
            f"{formatted_value} {suffix}"
        )

    return (
        f"{formatted_value} XP"
    )


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
        (
            0,
            0,
        ),
        text,
        font=font,
    )

    text_width = (
        text_box[2]
        - text_box[0]
    )

    text_height = (
        text_box[3]
        - text_box[1]
    )

    x = (
        left
        + (
            (
                right
                - left
            )
            - text_width
        )
        / 2
    )

    y = (
        top
        + (
            (
                bottom
                - top
            )
            - text_height
        )
        / 2
        - text_box[1]
    )

    draw.text(
        (
            x,
            y,
        ),
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
        (
            right - width,
            y,
        ),
        text,
        font=font,
        fill=fill,
    )


def _rank_color(
    rank: int,
) -> tuple[int, int, int, int]:
    if rank == 1:
        return GOLD_COLOR

    if rank == 2:
        return SILVER_COLOR

    if rank == 3:
        return BRONZE_COLOR

    return TEXT_COLOR


def _rank_text(
    rank: int | None,
) -> str:
    if (
        rank is None
        or rank <= 0
    ):
        return "—"

    return f"#{rank}"


def _get_row_value(
    row: Mapping[str, Any],
    key: str,
    default: Any,
) -> Any:
    value = row.get(
        key,
        default,
    )

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

    Types disponibles :
    - xp ;
    - money ;
    - streak.

    Pour le classement streak, la valeur correspond
    uniquement à la meilleure série quotidienne.
    """
    normalized_type = (
        str(
            ranking_type
        )
        .lower()
        .strip()
    )

    if normalized_type not in {
        "xp",
        "money",
        "streak",
    }:
        normalized_type = "xp"

    page = max(
        1,
        int(page),
    )

    total_pages = max(
        1,
        int(total_pages),
    )

    page = min(
        page,
        total_pages,
    )

    image = _load_background(
        background_path
    )

    overlay = Image.new(
        "RGBA",
        image.size,
        BACKGROUND_OVERLAY,
    )

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(
        image
    )

    title_font = _load_font(
        50,
        bold=True,
    )

    subtitle_font = _load_font(
        22
    )

    header_font = _load_font(
        21,
        bold=True,
    )

    row_font = _load_font(
        25,
        bold=True,
    )

    row_value_font = _load_font(
        24,
        bold=True,
    )

    footer_label_font = _load_font(
        17,
        bold=True,
    )

    footer_font = _load_font(
        23,
        bold=True,
    )

    if normalized_type == "money":
        title = "CLASSEMENT ARGENT"
        value_header = "ARGENT"
        accent_color = MONEY_ACCENT

    elif normalized_type == "streak":
        title = "CLASSEMENT SÉRIE"
        value_header = "MEILLEURE SÉRIE"
        accent_color = STREAK_ACCENT

    else:
        title = "CLASSEMENT XP"
        value_header = "XP"
        accent_color = XP_ACCENT

    draw.rounded_rectangle(
        (
            38,
            30,
            CARD_WIDTH - 38,
            138,
        ),
        radius=26,
        fill=(
            16,
            11,
            28,
            185,
        ),
        outline=(
            255,
            255,
            255,
            28,
        ),
        width=2,
    )

    draw.rounded_rectangle(
        (
            56,
            51,
            67,
            117,
        ),
        radius=6,
        fill=accent_color,
    )

    draw.text(
        (
            88,
            47,
        ),
        title,
        font=title_font,
        fill=TEXT_COLOR,
    )

    page_text = (
        f"PAGE {page} / {total_pages}"
    )

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
        outline=(
            255,
            255,
            255,
            30,
        ),
        width=2,
    )

    rank_column = (
        55,
        header_top,
        205,
        header_bottom,
    )

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
        (
            250,
            169,
        ),
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

    displayed_rows = list(
        rows[:10]
    )

    for index in range(
        10
    ):
        y = (
            row_start_y
            + index
            * (
                row_height
                + row_gap
            )
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

        username_font = (
            _get_username_font(
                display_name,
                25,
            )
        )

        value = int(
            _get_row_value(
                row,
                "value",
                0,
            )
        )

        _draw_centered_text(
            draw,
            box=(
                55,
                y,
                205,
                y + row_height,
            ),
            text=_rank_text(
                rank
            ),
            font=row_font,
            fill=_rank_color(
                rank
            ),
        )

        fitted_name = _truncate_text(
            draw,
            display_name,
            username_font,
            560,
        )

        name_box = draw.textbbox(
            (
                0,
                0,
            ),
            fitted_name,
            font=username_font,
        )

        name_height = (
            name_box[3]
            - name_box[1]
        )

        name_y = (
            y
            + (
                row_height
                - name_height
            )
            / 2
            - name_box[1]
        )

        draw.text(
            (
                250,
                name_y,
            ),
            fitted_name,
            font=username_font,
            fill=TEXT_COLOR,
        )

        formatted_value = _format_value(
            value,
            normalized_type,
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

    personal_rank_raw = (
        personal_row.get(
            "rank"
        )
    )

    personal_rank = (
        int(
            personal_rank_raw
        )
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

    personal_username_font = (
        _get_username_font(
            personal_name,
            23,
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
        (
            58,
            personal_top + 5,
        ),
        "TON CLASSEMENT",
        font=footer_label_font,
        fill=(
            255,
            201,
            229,
            255,
        ),
    )

    _draw_centered_text(
        draw,
        box=(
            55,
            personal_top + 18,
            205,
            personal_bottom,
        ),
        text=_rank_text(
            personal_rank
        ),
        font=footer_font,
        fill=TEXT_COLOR,
    )

    fitted_personal_name = (
        _truncate_text(
            draw,
            personal_name,
            personal_username_font,
            545,
        )
    )

    personal_name_box = draw.textbbox(
        (
            0,
            0,
        ),
        fitted_personal_name,
        font=personal_username_font,
    )

    personal_name_height = (
        personal_name_box[3]
        - personal_name_box[1]
    )

    personal_name_y = (
        personal_top
        + (
            personal_bottom
            - personal_top
            - personal_name_height
        )
        / 2
        - personal_name_box[1]
    )

    draw.text(
        (
            250,
            personal_name_y,
        ),
        fitted_personal_name,
        font=personal_username_font,
        fill=TEXT_COLOR,
    )

    formatted_personal_value = (
        _format_value(
            personal_value,
            normalized_type,
        )
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

    image.convert(
        "RGB"
    ).save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(
        0
    )

    return output

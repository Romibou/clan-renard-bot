from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


CARD_WIDTH = 1200
CARD_HEIGHT = 460

BACKGROUND_TOP = (18, 20, 31)
BACKGROUND_BOTTOM = (30, 24, 43)

PANEL_COLOR = (255, 255, 255, 18)
PANEL_BORDER_COLOR = (255, 255, 255, 28)

TEXT_COLOR = (248, 248, 252)
SECONDARY_TEXT_COLOR = (177, 179, 193)
MUTED_TEXT_COLOR = (130, 132, 148)

ACCENT_START = (226, 104, 161)
ACCENT_END = (154, 98, 255)

PROGRESS_BACKGROUND = (55, 57, 72)
AVATAR_BACKGROUND = (47, 42, 61)


@lru_cache(maxsize=32)
def get_font(
    size: int,
    *,
    bold: bool = False,
) -> ImageFont.FreeTypeFont:
    paths = (
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ),
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ),
    )

    for path in paths:
        try:
            return ImageFont.truetype(
                path,
                size=size,
            )
        except OSError:
            continue

    return ImageFont.load_default()


def format_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def create_vertical_gradient() -> Image.Image:
    image = Image.new(
        "RGBA",
        (CARD_WIDTH, CARD_HEIGHT),
    )

    pixels = image.load()

    for y in range(CARD_HEIGHT):
        ratio = y / max(1, CARD_HEIGHT - 1)

        red = round(
            BACKGROUND_TOP[0]
            + (
                BACKGROUND_BOTTOM[0]
                - BACKGROUND_TOP[0]
            )
            * ratio
        )
        green = round(
            BACKGROUND_TOP[1]
            + (
                BACKGROUND_BOTTOM[1]
                - BACKGROUND_TOP[1]
            )
            * ratio
        )
        blue = round(
            BACKGROUND_TOP[2]
            + (
                BACKGROUND_BOTTOM[2]
                - BACKGROUND_TOP[2]
            )
            * ratio
        )

        for x in range(CARD_WIDTH):
            pixels[x, y] = (
                red,
                green,
                blue,
                255,
            )

    return image


def add_glows(
    image: Image.Image,
) -> None:
    glow_layer = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )
    glow_draw = ImageDraw.Draw(glow_layer)

    glow_draw.ellipse(
        (820, -260, 1370, 290),
        fill=(226, 104, 161, 90),
    )

    glow_draw.ellipse(
        (-260, 250, 310, 820),
        fill=(124, 92, 255, 65),
    )

    glow_layer = glow_layer.filter(
        ImageFilter.GaussianBlur(95)
    )

    image.alpha_composite(glow_layer)


def draw_panel(
    image: Image.Image,
    coordinates: tuple[int, int, int, int],
    *,
    radius: int = 24,
) -> None:
    panel = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )
    panel_draw = ImageDraw.Draw(panel)

    panel_draw.rounded_rectangle(
        coordinates,
        radius=radius,
        fill=PANEL_COLOR,
        outline=PANEL_BORDER_COLOR,
        width=1,
    )

    image.alpha_composite(panel)


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    maximum_width: int,
    font_size: int,
    minimum_size: int = 18,
    bold: bool = False,
) -> ImageFont.ImageFont:
    size = font_size

    while size > minimum_size:
        font = get_font(
            size,
            bold=bold,
        )

        box = draw.textbbox(
            (0, 0),
            text,
            font=font,
        )

        if box[2] - box[0] <= maximum_width:
            return font

        size -= 1

    return get_font(
        minimum_size,
        bold=bold,
    )


def prepare_avatar(
    avatar_bytes: bytes | None,
    *,
    size: int,
    display_name: str,
) -> Image.Image:
    if avatar_bytes:
        try:
            avatar = Image.open(
                io.BytesIO(avatar_bytes)
            ).convert("RGBA")

            return ImageOps.fit(
                avatar,
                (size, size),
                method=Image.Resampling.LANCZOS,
            )
        except Exception:
            pass

    avatar = Image.new(
        "RGBA",
        (size, size),
        AVATAR_BACKGROUND,
    )
    draw = ImageDraw.Draw(avatar)

    initial = (
        display_name.strip()[:1].upper()
        if display_name.strip()
        else "?"
    )

    font = get_font(
        round(size * 0.44),
        bold=True,
    )

    box = draw.textbbox(
        (0, 0),
        initial,
        font=font,
    )

    text_width = box[2] - box[0]
    text_height = box[3] - box[1]

    draw.text(
        (
            (size - text_width) / 2,
            (size - text_height) / 2 - box[1],
        ),
        initial,
        font=font,
        fill=TEXT_COLOR,
    )

    return avatar


def draw_circular_avatar(
    image: Image.Image,
    *,
    avatar_bytes: bytes | None,
    display_name: str,
    x: int,
    y: int,
    size: int,
) -> None:
    avatar = prepare_avatar(
        avatar_bytes,
        size=size,
        display_name=display_name,
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

    border_size = 8

    border = Image.new(
        "RGBA",
        (
            size + border_size * 2,
            size + border_size * 2,
        ),
        (0, 0, 0, 0),
    )
    border_draw = ImageDraw.Draw(border)

    border_draw.ellipse(
        (
            0,
            0,
            border.width - 1,
            border.height - 1,
        ),
        fill=ACCENT_START + (255,),
    )

    border_draw.ellipse(
        (
            border_size,
            border_size,
            border.width - border_size - 1,
            border.height - border_size - 1,
        ),
        fill=(28, 27, 40, 255),
    )

    image.alpha_composite(
        border,
        (
            x - border_size,
            y - border_size,
        ),
    )

    image.paste(
        avatar,
        (x, y),
        mask,
    )


def draw_progress_bar(
    image: Image.Image,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    ratio: float,
) -> None:
    ratio = max(
        0.0,
        min(1.0, ratio),
    )

    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (
            x,
            y,
            x + width,
            y + height,
        ),
        radius=height // 2,
        fill=PROGRESS_BACKGROUND,
    )

    filled_width = round(
        width * ratio
    )

    if filled_width <= 0:
        return

    filled_width = max(
        height,
        filled_width,
    )
    filled_width = min(
        width,
        filled_width,
    )

    gradient = Image.new(
        "RGBA",
        (filled_width, height),
        (0, 0, 0, 0),
    )
    gradient_draw = ImageDraw.Draw(gradient)

    for current_x in range(filled_width):
        gradient_ratio = (
            current_x / max(1, filled_width - 1)
        )

        red = round(
            ACCENT_START[0]
            + (
                ACCENT_END[0]
                - ACCENT_START[0]
            )
            * gradient_ratio
        )
        green = round(
            ACCENT_START[1]
            + (
                ACCENT_END[1]
                - ACCENT_START[1]
            )
            * gradient_ratio
        )
        blue = round(
            ACCENT_START[2]
            + (
                ACCENT_END[2]
                - ACCENT_START[2]
            )
            * gradient_ratio
        )

        gradient_draw.line(
            (
                current_x,
                0,
                current_x,
                height,
            ),
            fill=(red, green, blue, 255),
        )

    mask = Image.new(
        "L",
        (filled_width, height),
        0,
    )
    mask_draw = ImageDraw.Draw(mask)

    mask_draw.rounded_rectangle(
        (
            0,
            0,
            filled_width,
            height,
        ),
        radius=height // 2,
        fill=255,
    )

    image.paste(
        gradient,
        (x, y),
        mask,
    )


def draw_stat_box(
    image: Image.Image,
    *,
    x: int,
    y: int,
    width: int,
    title: str,
    value: str,
) -> None:
    height = 94

    draw_panel(
        image,
        (
            x,
            y,
            x + width,
            y + height,
        ),
        radius=20,
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (x + 22, y + 17),
        title.upper(),
        font=get_font(16, bold=True),
        fill=MUTED_TEXT_COLOR,
    )

    value_font = fit_text(
        draw,
        value,
        maximum_width=width - 44,
        font_size=27,
        minimum_size=19,
        bold=True,
    )

    draw.text(
        (x + 22, y + 48),
        value,
        font=value_font,
        fill=TEXT_COLOR,
    )


def render_progression_card(
    *,
    avatar_bytes: bytes | None,
    display_name: str,
    level: int,
    rank: int | None,
    total_xp: int,
    current_xp: int,
    required_xp: int,
    wallet: int,
    lifetime_coins: int,
) -> io.BytesIO:
    image = create_vertical_gradient()
    add_glows(image)

    draw_panel(
        image,
        (28, 28, CARD_WIDTH - 28, CARD_HEIGHT - 28),
        radius=34,
    )

    draw_circular_avatar(
        image,
        avatar_bytes=avatar_bytes,
        display_name=display_name,
        x=68,
        y=93,
        size=220,
    )

    draw = ImageDraw.Draw(image)

    name_font = fit_text(
        draw,
        display_name,
        maximum_width=560,
        font_size=46,
        minimum_size=25,
        bold=True,
    )

    draw.text(
        (342, 58),
        display_name,
        font=name_font,
        fill=TEXT_COLOR,
    )

    rank_text = (
        f"RANG #{rank}"
        if rank is not None
        else "NON CLASSE"
    )

    rank_box = draw.textbbox(
        (0, 0),
        rank_text,
        font=get_font(17, bold=True),
    )
    rank_width = rank_box[2] - rank_box[0]

    draw.rounded_rectangle(
        (
            1018 - rank_width,
            61,
            1150,
            101,
        ),
        radius=20,
        fill=(226, 104, 161, 35),
        outline=(226, 104, 161, 100),
        width=1,
    )

    draw.text(
        (
            1084 - rank_width / 2,
            81,
        ),
        rank_text,
        anchor="mm",
        font=get_font(17, bold=True),
        fill=(242, 159, 198),
    )

    draw.text(
        (342, 127),
        f"NIVEAU {level}",
        font=get_font(24, bold=True),
        fill=(237, 139, 185),
    )

    draw.text(
        (1148, 129),
        f"{format_number(total_xp)} XP TOTAL",
        anchor="ra",
        font=get_font(19, bold=True),
        fill=SECONDARY_TEXT_COLOR,
    )

    progress_ratio = (
        current_xp / required_xp
        if required_xp > 0
        else 1.0
    )

    draw_progress_bar(
        image,
        x=342,
        y=174,
        width=806,
        height=31,
        ratio=progress_ratio,
    )

    percentage = round(
        progress_ratio * 100
    )

    draw.text(
        (342, 221),
        (
            f"{format_number(current_xp)} / "
            f"{format_number(required_xp)} XP"
        ),
        font=get_font(19, bold=True),
        fill=TEXT_COLOR,
    )

    draw.text(
        (1148, 221),
        f"{percentage} %",
        anchor="ra",
        font=get_font(19, bold=True),
        fill=SECONDARY_TEXT_COLOR,
    )

    draw_stat_box(
        image,
        x=342,
        y=279,
        width=390,
        title="ARGENT",
        value=f"{format_number(wallet)} pièces",
    )
    
    draw_stat_box(
        image,
        x=758,
        y=279,
        width=390,
        title="ARGENT GAGNÉ AU TOTAL",
        value=f"{format_number(lifetime_coins)} pièces",
    )



    draw.text(
        (68, 390),
        "CLAN RENARD",
        font=get_font(16, bold=True),
        fill=MUTED_TEXT_COLOR,
    )


    output = io.BytesIO()

    image.convert("RGB").save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(0)
    return output

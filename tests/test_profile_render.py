from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from bot.extensions.profile import (
    ProfileCog,
    detect_frame_shape,
    fit_layer,
    readability_overlay,
    shape_card,
)


def solid(size: tuple[int, int], color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", size, color)


def test_fit_layer_keeps_the_whole_frame() -> None:
    frame = solid((1400, 500), (0, 0, 0, 0))
    # Bords gauche et droit opaques : ils doivent survivre à l'adaptation.
    for x in (0, 1399):
        for y in range(500):
            frame.putpixel((x, y), (255, 0, 0, 255))

    fitted = fit_layer(frame, (1200, 500))

    assert fitted.size == (1200, 500)
    assert fitted.getpixel((0, 250))[3] > 0
    assert fitted.getpixel((1199, 250))[3] > 0


def test_fit_layer_leaves_the_right_size_untouched() -> None:
    layer = solid((1200, 500), (1, 2, 3, 4))

    assert fit_layer(layer, (1200, 500)) is layer


def test_readability_overlay_is_darker_behind_the_text() -> None:
    overlay = readability_overlay((1200, 500))
    alpha = [overlay.getpixel((x, 250))[3] for x in (50, 300, 600, 900, 1199)]

    assert alpha[2] > alpha[0]
    assert alpha[2] > alpha[4]
    # Pas de marche brutale : écart limité entre deux pixels voisins.
    row = [overlay.getpixel((x, 250))[3] for x in range(1200)]
    assert max(abs(a - b) for a, b in zip(row, row[1:])) <= 2


def render_with(tmp_path: Path, equipped_files: dict[str, Image.Image]) -> Image.Image:
    equipped = {}

    for kind, image in equipped_files.items():
        image.save(tmp_path / f"{kind}.png")
        equipped[kind] = {
            "asset_path": f"{kind}.png",
            "value": None,
            "identifier": f"{kind}-test-2026",
        }

    cog = ProfileCog.__new__(ProfileCog)
    cog.assets_root = tmp_path

    avatar = io.BytesIO()
    solid((64, 64), (255, 255, 255, 255)).save(avatar, format="PNG")

    output = cog._render_profile_sync(
        1,
        "Renard",
        avatar.getvalue(),
        {"bio": "Bio", "color_hex": "#E268A1"},
        equipped,
        3,
    )

    return Image.open(output).convert("RGB")


def test_card_without_frame_keeps_the_colored_border(tmp_path: Path) -> None:
    card = render_with(tmp_path, {})

    # La carte est découpée sur sa bordure : la bordure couleur du
    # membre (rose) se trouve donc tout au bord de l'image.
    assert card.size == (1130, 430)
    red, green, blue = card.getpixel((2, 215))
    assert red > 150 and red > green


def test_equipped_frame_replaces_the_colored_border(tmp_path: Path) -> None:
    frame = solid((1400, 500), (0, 0, 0, 0))
    background = solid((1400, 500), (20, 120, 40, 255))

    card = render_with(tmp_path, {"background": background, "frame": frame})

    assert card.size == (1200, 500)
    red, green, blue = card.getpixel((36, 250))
    # Plus de bordure rose : on voit le fond vert.
    assert green > red


def drawn_frame(inset: int, radius: int) -> Image.Image:
    frame = solid((1200, 500), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle(
        (inset, inset, 1199 - inset, 499 - inset),
        radius=radius,
        outline=(0, 200, 255, 255),
        width=6,
    )
    return frame


def test_detect_frame_shape() -> None:
    box, radius = detect_frame_shape(drawn_frame(12, 30))

    assert box == (12, 12, 1188, 488)
    assert 20 <= radius <= 40
    assert detect_frame_shape(solid((1200, 500), (0, 0, 0, 0))) is None


def test_card_is_cut_to_its_frame_with_transparent_corners() -> None:
    card = solid((1200, 500), (20, 120, 40, 255))
    shaped = shape_card(card, drawn_frame(12, 30))

    assert shaped.size == (1176, 476)
    # Coin extérieur transparent, centre opaque.
    assert shaped.getpixel((0, 0))[3] == 0
    assert shaped.getpixel((588, 238))[3] == 255

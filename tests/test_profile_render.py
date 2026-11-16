from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from bot.extensions.profile import ProfileCog, fit_layer, readability_overlay


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

    # Bordure couleur du membre (rose) sur le côté gauche de la carte.
    red, green, blue = card.getpixel((36, 250))
    assert red > 150 and red > green


def test_equipped_frame_replaces_the_colored_border(tmp_path: Path) -> None:
    frame = solid((1400, 500), (0, 0, 0, 0))
    background = solid((1400, 500), (20, 120, 40, 255))

    card = render_with(tmp_path, {"background": background, "frame": frame})

    assert card.size == (1200, 500)
    red, green, blue = card.getpixel((36, 250))
    # Plus de bordure rose : on voit le fond vert.
    assert green > red

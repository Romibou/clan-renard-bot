from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import discord
import pytest
from PIL import Image, ImageDraw

from bot.features import cosmetics_studio as studio


def png(size, color=(200, 30, 30, 255), *, hole: bool = False, mostly_clear: bool = False) -> bytes:
    image = Image.new("RGBA", size, color)

    if hole:  # cadre : centre transparent
        w, h = size
        ImageDraw.Draw(image).rectangle((int(w * 0.1), int(h * 0.15), int(w * 0.9), int(h * 0.85)), fill=(0, 0, 0, 0))

    if mostly_clear:  # effet : quelques points sur fond transparent
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for x in range(0, size[0], 60):
            draw.ellipse((x, 40, x + 10, 50), fill=(255, 255, 255, 255))

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# ---------------------------------------------------------------
# Identifiants et types
# ---------------------------------------------------------------


def test_identifiers() -> None:
    assert studio.slugify("Volcan 2026") == "volcan-2026"
    assert studio.slugify("  Hiver Éternel !! ") == "hiver-eternel"
    assert studio.make_identifier("frame", "Volcan 2026") == "frame-volcan-2026"


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("volcan-fond.png", "background"),
        ("Volcan_Cadre.png", "frame"),
        ("badge volcan.png", "badge"),
        ("effet-lave.png", "effect"),
        ("frame.png", "frame"),
    ],
)
def test_guess_type_from_filename(filename, expected) -> None:
    assert studio.guess_type(filename, opened(png((1200, 500)))) == expected


def test_guess_type_from_image() -> None:
    assert studio.guess_type("a.png", opened(png((256, 256)))) == "badge"
    assert studio.guess_type("b.png", opened(png((1200, 500)))) == "background"
    assert studio.guess_type("c.png", opened(png((1200, 500), hole=True))) == "frame"
    assert studio.guess_type("d.png", opened(png((1200, 500), mostly_clear=True))) == "effect"


# ---------------------------------------------------------------
# Préparation des images
# ---------------------------------------------------------------


def test_prepare_each_type() -> None:
    background, warnings = studio.prepare_image(png((1920, 1080)), "background")
    assert opened(background).size == (1200, 500)
    assert warnings  # format éloigné : recadré

    frame, _ = studio.prepare_image(png((1200, 500), hole=True), "frame")
    assert opened(frame).size == (1200, 500)

    effect, _ = studio.prepare_image(png((1200, 500), mostly_clear=True), "effect")
    assert opened(effect).size == (1200, 500)

    badge, warnings = studio.prepare_image(png((400, 200)), "badge")
    assert opened(badge).size == (256, 256)
    assert len(warnings) == 2  # pas de transparence, pas carré


def test_prepare_refuses_bad_images() -> None:
    with pytest.raises(ValueError, match="centre transparent"):
        studio.prepare_image(png((1200, 500)), "frame")

    with pytest.raises(ValueError, match="transparent"):
        studio.prepare_image(png((1200, 500)), "effect")

    with pytest.raises(ValueError, match="lisible"):
        studio.prepare_image(b"pas une image", "background")

    with pytest.raises(ValueError):
        studio.prepare_image(png((10, 10)), "title")


# ---------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------


class FakePool:
    def __init__(self) -> None:
        self.images: dict = {}

    async def execute(self, query, *args):
        if "INSERT INTO profile_cosmetic_images" in query:
            self.images[(args[0], args[1])] = args[2]

    async def fetch(self, query, *args):
        if "FROM profile_cosmetic_images" in query:
            return [{"guild_id": g, "identifier": i, "data": d} for (g, i), d in self.images.items()]
        return []


async def test_saved_images_survive_a_redeploy(tmp_path: Path) -> None:
    pool = FakePool()
    cog = SimpleNamespace(get_pool=lambda: pool, assets_root=tmp_path)
    data = png((10, 10))

    relative = await studio.save_image(cog, 1, "frame-volcan-2026", data)
    assert relative == "uploaded/1/frame-volcan-2026.png"
    assert (tmp_path / relative).read_bytes() == data

    # Render efface les fichiers… le bot les remet au démarrage.
    (tmp_path / relative).unlink()
    assert await studio.restore_images(cog) == 1
    assert (tmp_path / relative).read_bytes() == data


async def test_preview_cleans_temporary_files(tmp_path: Path) -> None:
    rendered: list = []

    def render(user_id, name, avatar, profile, equipped, streak):
        rendered.append(equipped)
        for item in equipped.values():
            if item.get("asset_path"):
                assert (tmp_path / item["asset_path"]).exists()
        return io.BytesIO(b"png")

    async def get_profile(**kwargs):
        return {"color_hex": "#ffffff"}

    async def get_equipped(**kwargs):
        return {"badge": {"identifier": "badge-old"}}

    async def streak(**kwargs):
        return 3

    async def avatar_read():
        return b"avatar"

    cog = SimpleNamespace(
        assets_root=tmp_path, get_profile=get_profile, get_equipped_cosmetics=get_equipped,
        get_current_daily_streak=streak, _render_profile_sync=render,
    )
    interaction = SimpleNamespace(
        guild_id=1,
        user=SimpleNamespace(
            id=7, display_name="Romi",
            display_avatar=SimpleNamespace(replace=lambda **kw: SimpleNamespace(read=avatar_read)),
        ),
    )
    planned = [studio.PlannedCosmetic("frame", "frame-x", "Cadre X", image=png((10, 10)))]
    file = await studio.render_preview(cog, interaction, planned)

    assert isinstance(file, discord.File)
    assert rendered[0]["frame"]["identifier"] == "frame-x" and rendered[0]["badge"]["identifier"] == "badge-old"
    assert not list((tmp_path / "uploaded" / "_apercu").glob("*.png"))  # fichiers d'aperçu supprimés


# ---------------------------------------------------------------
# Fenêtres
# ---------------------------------------------------------------


@pytest.mark.parametrize("modal_class", [studio.CreateCosmeticModal, studio.CollectionModal, studio.ReplaceImageModal])
def test_modals_respect_discord_limits(modal_class) -> None:
    modal = modal_class(SimpleNamespace())
    assert len(modal.title) <= 45 and len(modal.children) <= 5

    for item in modal.children:
        assert len(item.text) <= 45, item.text
        assert item.description is None or len(item.description) <= 100, item.description


def test_guide_and_admin_panel_buttons() -> None:
    from bot.extensions.profile import ProfileAdminView

    assert len(studio.GUIDE) < 4096
    view = ProfileAdminView(cog=SimpleNamespace(), guild_id=1)
    labels = [item.label for item in view.children]

    for label in ("Créer un cosmétique", "Créer une collection", "Changer l'image", "Guide des images", "Catalogue"):
        assert label in labels

    assert len(view.children) <= 25

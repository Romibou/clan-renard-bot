from bot.core.extension_loader import discover_extensions


def test_advent_extension_is_discovered() -> None:
    extensions = discover_extensions()

    assert "bot.extensions.advent" in extensions

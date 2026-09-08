from bot.core.extension_loader import discover_extensions


def test_private_extensions_are_ignored() -> None:
    extensions = discover_extensions()

    assert not any(
        extension.rsplit(".", maxsplit=1)[-1].startswith("_")
        for extension in extensions
    )


def test_only_python_extensions_are_discovered() -> None:
    extensions = discover_extensions()

    assert all(
        extension.startswith("bot.extensions.")
        for extension in extensions
    )

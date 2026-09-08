from __future__ import annotations


def truncate(
    value: str,
    maximum: int,
    suffix: str = "…",
) -> str:
    value = str(value)

    if len(value) <= maximum:
        return value

    usable = max(0, maximum - len(suffix))
    return value[:usable].rstrip() + suffix


def plural(
    amount: int,
    singular: str,
    plural_form: str | None = None,
) -> str:
    if amount == 1:
        return singular

    return plural_form or f"{singular}s"

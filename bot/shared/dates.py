from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"Le fuseau horaire « {name} » est inconnu."
        ) from error


def now_in_timezone(name: str) -> datetime:
    return datetime.now(tz=get_timezone(name))


def validate_timezone(name: str) -> bool:
    try:
        get_timezone(name)
    except ValueError:
        return False

    return True

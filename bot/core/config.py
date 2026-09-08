from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SettingsError(RuntimeError):
    """Erreur provoquée par une variable d'environnement absente ou invalide."""


def _optional_int(name: str) -> int | None:
    raw_value = os.getenv(name, "").strip()

    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError as error:
        raise SettingsError(
            f"La variable {name} doit contenir un identifiant numérique."
        ) from error


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    database_url: str
    default_timezone: str
    environment: str
    log_level: str
    dev_guild_id: int | None
    owner_id: int | None
    port: int
    project_root: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")

        discord_token = os.getenv("DISCORD_TOKEN", "").strip()
        database_url = os.getenv("DATABASE_URL", "").strip()

        if not discord_token:
            raise SettingsError(
                "DISCORD_TOKEN est absent. Copie .env.example vers .env "
                "pour le développement local, ou ajoute la variable sur Render."
            )

        if not database_url:
            raise SettingsError(
                "DATABASE_URL est absente. Une base PostgreSQL est obligatoire."
            )

        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://",
                "postgresql://",
                1,
            )

        port_raw = os.getenv("PORT", "10000").strip()

        try:
            port = int(port_raw)
        except ValueError as error:
            raise SettingsError("PORT doit être un nombre entier.") from error

        return cls(
            discord_token=discord_token,
            database_url=database_url,
            default_timezone=os.getenv(
                "DEFAULT_TIMEZONE",
                "Europe/Paris",
            ).strip(),
            environment=os.getenv(
                "ENVIRONMENT",
                "development",
            ).strip().lower(),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            dev_guild_id=_optional_int("DEV_GUILD_ID"),
            owner_id=_optional_int("OWNER_ID"),
            port=port,
            project_root=PROJECT_ROOT,
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

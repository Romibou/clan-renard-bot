from __future__ import annotations

import asyncio
import sys

from bot.core.config import Settings, SettingsError
from bot.core.database import Database


async def run_migration() -> None:
    settings = Settings.from_environment()

    database = Database(
        settings.database_url,
        settings.project_root,
    )

    await database.connect()

    try:
        await database.apply_schema()
    finally:
        await database.close()

    print("Schéma PostgreSQL appliqué avec succès.")


def main() -> int:
    try:
        asyncio.run(run_migration())
    except SettingsError as error:
        print(f"Configuration invalide : {error}")

        return 1
    except Exception as error:
        print(f"Échec de la migration : {error}")

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

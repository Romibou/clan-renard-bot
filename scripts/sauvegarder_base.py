"""
Sauvegarde complète de la base PostgreSQL du bot (Supabase).

Utilisation, depuis le dossier du bot :

    python scripts/sauvegarder_base.py

La variable DATABASE_URL est lue dans le fichier .env du bot (jamais
envoyé sur GitHub) ou dans les variables d'environnement.

Résultat : un fichier sauvegardes/clan-renard-AAAA-MM-JJ_HH-MM.zip
contenant un fichier CSV par table et un fichier informations.json.
Le dossier sauvegardes/ est exclu de git : la base contient les
identifiants Discord des membres.

Pour remettre une sauvegarde dans une base : scripts/restaurer_base.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIRECTORY = PROJECT_ROOT / "sauvegardes"


def get_database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env")

    url = os.getenv("DATABASE_URL", "").strip()

    if not url:
        raise SystemExit(
            "DATABASE_URL est absente.\n"
            "Ajoute la ligne DATABASE_URL=... (la même que sur Render) "
            "dans le fichier .env du bot, puis relance le script."
        )

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


async def list_tables(
    connection: asyncpg.Connection,
) -> list[str]:
    records = await connection.fetch(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
        """
    )

    return [str(record["tablename"]) for record in records]


async def export_table(
    connection: asyncpg.Connection,
    table: str,
) -> bytes:
    buffer = io.BytesIO()

    await connection.copy_from_table(
        table,
        schema_name="public",
        output=buffer,
        format="csv",
        header=True,
    )

    return buffer.getvalue()


async def backup() -> Path:
    connection = await asyncpg.connect(
        dsn=get_database_url(),
        statement_cache_size=0,
    )

    try:
        # Instantané cohérent : toutes les tables sont lues au même
        # instant, même si le bot écrit pendant la sauvegarde.
        async with connection.transaction(
            isolation="repeatable_read",
            readonly=True,
        ):
            tables = await list_tables(connection)
            exports: dict[str, bytes] = {}

            for table in tables:
                exports[table] = await export_table(connection, table)
                print(f"  {table} : OK")
    finally:
        await connection.close()

    BACKUP_DIRECTORY.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = BACKUP_DIRECTORY / f"clan-renard-{stamp}.zip"

    information = {
        "created_at": datetime.now().astimezone().isoformat(),
        "tables": {
            table: max(0, content.count(b"\n") - 1)
            for table, content in exports.items()
        },
        "format": "Un fichier CSV par table (avec en-tête).",
    }

    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for table, content in exports.items():
            archive.writestr(f"{table}.csv", content)

        archive.writestr(
            "informations.json",
            json.dumps(information, ensure_ascii=False, indent=2),
        )

    return path


def main() -> int:
    print("Sauvegarde de la base en cours…")

    try:
        path = asyncio.run(backup())
    except (OSError, asyncpg.PostgresError) as error:
        print(f"Échec de la sauvegarde : {error}")
        return 1

    size = path.stat().st_size / 1024
    print(f"\nSauvegarde terminée : {path} ({size:.0f} Ko)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

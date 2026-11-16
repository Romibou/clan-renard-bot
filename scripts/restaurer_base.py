"""
Remet une sauvegarde faite par scripts/sauvegarder_base.py dans la
base PostgreSQL désignée par DATABASE_URL.

Utilisation, depuis le dossier du bot :

    python scripts/restaurer_base.py sauvegardes/clan-renard-AAAA-MM-JJ_HH-MM.zip

ATTENTION : les tables présentes dans la sauvegarde sont VIDÉES puis
remplies avec son contenu. Tout ce qui a été fait depuis la
sauvegarde est perdu. Le script demande une confirmation.

Pour une base neuve (changement d'hébergeur) : démarre d'abord le bot
une fois dessus pour qu'il crée les tables, arrête-le, puis lance ce
script. Arrête aussi le bot pendant toute restauration.
"""

from __future__ import annotations

import asyncio
import io
import sys
import zipfile
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sauvegarder_base import get_database_url, list_tables  # noqa: E402


async def dependency_order(
    connection: asyncpg.Connection,
    tables: list[str],
) -> list[str]:
    """
    Trie les tables pour remplir une table avant celles qui la
    référencent (clés étrangères).
    """
    records = await connection.fetch(
        """
        SELECT
            child.relname AS child,
            parent.relname AS parent
        FROM pg_constraint AS constraint_info
        JOIN pg_class AS child
            ON child.oid = constraint_info.conrelid
        JOIN pg_class AS parent
            ON parent.oid = constraint_info.confrelid
        JOIN pg_namespace AS namespace
            ON namespace.oid = child.relnamespace
        WHERE constraint_info.contype = 'f'
          AND namespace.nspname = 'public'
        """
    )

    parents: dict[str, set[str]] = {table: set() for table in tables}

    for record in records:
        child = str(record["child"])
        parent = str(record["parent"])

        if child in parents and parent in parents and child != parent:
            parents[child].add(parent)

    ordered: list[str] = []
    remaining = dict(parents)

    while remaining:
        ready = sorted(
            table
            for table, needed in remaining.items()
            if needed <= set(ordered)
        )

        if not ready:
            # Dépendance circulaire : ordre alphabétique en dernier recours.
            ready = sorted(remaining)

        for table in ready:
            ordered.append(table)
            remaining.pop(table)

    return ordered


async def reset_sequences(
    connection: asyncpg.Connection,
    table: str,
) -> None:
    """Recale les compteurs BIGSERIAL après l'import des lignes."""
    columns = await connection.fetch(
        """
        SELECT
            column_name,
            pg_get_serial_sequence(
                format('public.%I', table_name),
                column_name
            ) AS sequence_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
        """,
        table,
    )

    for column in columns:
        sequence = column["sequence_name"]

        if sequence is None:
            continue

        name = str(column["column_name"]).replace('"', '""')
        quoted_table = table.replace('"', '""')

        await connection.execute(
            f"""
            SELECT setval(
                $1::regclass,
                COALESCE(
                    (SELECT MAX("{name}") FROM public."{quoted_table}"),
                    0
                ) + 1,
                false
            )
            """,
            sequence,
        )


async def restore(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        contents = {
            Path(name).stem: archive.read(name)
            for name in archive.namelist()
            if name.endswith(".csv")
        }

    connection = await asyncpg.connect(
        dsn=get_database_url(),
        statement_cache_size=0,
    )

    try:
        existing = set(await list_tables(connection))
        missing = sorted(set(contents) - existing)

        if missing:
            print(
                "Tables absentes de la base (démarre le bot une fois "
                "pour les créer) : " + ", ".join(missing)
            )
            raise SystemExit(1)

        tables = await dependency_order(connection, sorted(contents))

        async with connection.transaction():
            quoted = ", ".join(
                f'public."{table}"' for table in tables
            )
            await connection.execute(f"TRUNCATE {quoted}")

            for table in tables:
                await connection.copy_to_table(
                    table,
                    schema_name="public",
                    source=io.BytesIO(contents[table]),
                    format="csv",
                    header=True,
                )
                await reset_sequences(connection, table)
                print(f"  {table} : OK")
    finally:
        await connection.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Utilisation : python scripts/restaurer_base.py "
            "sauvegardes/clan-renard-....zip"
        )
        return 1

    path = Path(sys.argv[1])

    if not path.is_file():
        print(f"Fichier introuvable : {path}")
        return 1

    print(
        f"Les tables de la base vont être REMPLACÉES par le contenu "
        f"de {path.name}.\n"
        "Tout ce qui a changé depuis cette sauvegarde sera perdu."
    )
    answer = input("Tape RESTAURER pour confirmer : ").strip()

    if answer != "RESTAURER":
        print("Restauration annulée.")
        return 1

    try:
        asyncio.run(restore(path))
    except (OSError, asyncpg.PostgresError) as error:
        print(f"Échec de la restauration (rien n'a été modifié) : {error}")
        return 1

    print("\nRestauration terminée. Tu peux redémarrer le bot.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

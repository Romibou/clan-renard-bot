from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import asyncpg

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


logger = logging.getLogger(__name__)


class Database:
    def __init__(
        self,
        database_url: str,
        project_root: Path,
    ) -> None:
        self.database_url = database_url
        self.project_root = project_root
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.pool is not None:
            return

        self.pool = await asyncpg.create_pool(
            dsn=self.database_url,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )

        logger.info("Connexion PostgreSQL établie")

    async def close(self) -> None:
        if self.pool is None:
            return

        await self.pool.close()
        self.pool = None
        logger.info("Connexion PostgreSQL fermée")

    def require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("La base de données n'est pas connectée.")

        return self.pool


    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        pool = self.require_pool()
    
        async with pool.acquire() as connection:
            async with connection.transaction():
                yield connection

    async def apply_schema(self) -> None:
        """
        Applique le schéma de manière idempotente.

        Le fichier SQL utilise CREATE TABLE IF NOT EXISTS et peut donc
        être exécuté à chaque démarrage sans effacer les données.
        """
        schema_path = self.project_root / "database" / "schema.sql"

        if not schema_path.exists():
            raise FileNotFoundError(
                f"Schéma PostgreSQL introuvable : {schema_path}"
            )

        schema = schema_path.read_text(encoding="utf-8")
        pool = self.require_pool()

        async with pool.acquire() as connection:
            await connection.execute(schema)

        logger.info("Schéma PostgreSQL vérifié")

    async def ping(self) -> bool:
        try:
            pool = self.require_pool()

            async with pool.acquire() as connection:
                value = await connection.fetchval("SELECT 1")

            return value == 1
        except Exception:
            logger.exception("Échec du contrôle PostgreSQL")
            return False

    async def fetch(
        self,
        query: str,
        *args: Any,
    ) -> list[asyncpg.Record]:
        pool = self.require_pool()

        async with pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(
        self,
        query: str,
        *args: Any,
    ) -> asyncpg.Record | None:
        pool = self.require_pool()

        async with pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(
        self,
        query: str,
        *args: Any,
    ) -> Any:
        pool = self.require_pool()

        async with pool.acquire() as connection:
            return await connection.fetchval(query, *args)

    async def execute(
        self,
        query: str,
        *args: Any,
    ) -> str:
        pool = self.require_pool()

        async with pool.acquire() as connection:
            return await connection.execute(query, *args)

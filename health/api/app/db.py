"""psycopg3 connection pool + a tiny SQL-file migration runner.

Migrations live in ../migrations/NNNN_name.sql and run in filename order inside
one transaction each; applied versions are recorded in schema_migrations.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

log = logging.getLogger("health.db")
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.require_pg(),
            min_size=settings.pool_min,
            max_size=settings.pool_max,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def conn() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """A pooled connection; commits on clean exit, rolls back on exception."""
    with pool().connection() as c:
        yield c


def jsonb(value: Any) -> Jsonb:
    """Wrap a Python object for a jsonb parameter."""
    return Jsonb(value)


def migrate(pg_url: str | None = None) -> list[str]:
    """Apply pending migrations; returns the versions applied."""
    url = pg_url or settings.require_pg()
    applied: list[str] = []
    with psycopg.connect(url, row_factory=dict_row) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["version"] for r in c.execute("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in done:
                continue
            log.info("applying migration %s", version)
            with c.transaction():
                c.execute(path.read_text())
                c.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("applied:", migrate() or "nothing to do")

"""Shared DB connection — every DeepFrag script imports this.

Defaults to the **production Cloud SQL Postgres** instance so local commands hit
live data by default. Override with:

  export DEEPFRAG_PG_URL=postgresql://...        # other PG
  export DEEPFRAG_USE_SQLITE=1                   # legacy local file (read-only safety net)

Inside Cloud Run we pass DEEPFRAG_PG_URL via the unix-socket form
(host=/cloudsql/PROJECT:REGION:INSTANCE) so we don't need to expose the DB to
the public internet.
"""

import os
import sqlite3
from pathlib import Path

import psycopg2
import psycopg2.extras

# Public-IP default for local dev. Cloud Run overrides this via env var with the
# unix-socket form. Password is intentionally not committed — local devs export
# DEEPFRAG_PG_PASSWORD or paste it into a shell-sourced .env.
DEFAULT_HOST = "34.72.226.56"
DEFAULT_DB = "deepfrag"
DEFAULT_USER = "postgres"

SQLITE_PATH = Path(__file__).parent / "data" / "qw-stats.db"


def _pg_url_from_env() -> str:
    """Build a Postgres URL from env vars, falling back to the prod Cloud SQL public IP."""
    if "DEEPFRAG_PG_URL" in os.environ:
        return os.environ["DEEPFRAG_PG_URL"]
    pw = os.environ.get("DEEPFRAG_PG_PASSWORD")
    if not pw:
        # Last-resort: read the password file the bootstrap script created.
        pw_file = Path("/tmp/deepfrag_pg_pw.txt")
        if pw_file.exists():
            pw = pw_file.read_text().strip()
    if not pw:
        raise RuntimeError(
            "No DEEPFRAG_PG_URL or DEEPFRAG_PG_PASSWORD set, and /tmp/deepfrag_pg_pw.txt missing. "
            "Either export DEEPFRAG_PG_URL or DEEPFRAG_PG_PASSWORD."
        )
    return f"postgresql://{DEFAULT_USER}:{pw}@{DEFAULT_HOST}:5432/{DEFAULT_DB}"


def connect(read_only: bool = False, dict_rows: bool = True):
    """Return a connection to the active DB (Postgres by default).

    If `DEEPFRAG_USE_SQLITE=1`, falls back to the local SQLite file — useful for
    offline work or migration replay, but writes from there don't reach prod.
    """
    if os.environ.get("DEEPFRAG_USE_SQLITE"):
        conn = sqlite3.connect(SQLITE_PATH)
        if dict_rows:
            conn.row_factory = sqlite3.Row
        return conn

    factory = psycopg2.extras.RealDictCursor if dict_rows else None
    return psycopg2.connect(_pg_url_from_env(), cursor_factory=factory)


def is_postgres(conn) -> bool:
    """True when we're talking to PG (so callers can branch on dialect)."""
    return isinstance(conn, psycopg2.extensions.connection)

#!/usr/bin/env python3
"""Migrate SQLite (data/qw-stats.db) → Postgres for DeepFrag.

Creates the schema in Postgres (drops if --reset), then bulk-copies every row
from SQLite using psycopg2's COPY for speed (~10× INSERT throughput on large
tables like `players` at 515k rows).

Usage:
  python migrate_sqlite_to_pg.py --pg "postgresql:///deepfrag"
  python migrate_sqlite_to_pg.py --reset       # drop + recreate
  python migrate_sqlite_to_pg.py --only matches,ratings
"""

import argparse
import io
import sqlite3
import sys
import time
from pathlib import Path

import psycopg2

DEFAULT_SQLITE = Path(__file__).parent / "data" / "qw-stats.db"
DEFAULT_PG = "postgresql:///deepfrag"

# Schema port. INTEGER → BIGINT for ids that could grow; column order matches
# the SQLite definitions so we can blindly stream rows.
SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id BIGINT PRIMARY KEY,
    match_date TEXT NOT NULL,
    match_mode TEXT NOT NULL,
    match_map TEXT NOT NULL,
    match_tag TEXT,
    server_hostname TEXT,
    server_port INTEGER,
    match_dmm INTEGER,
    match_tp INTEGER,
    match_time_limit_mins INTEGER,
    match_duration_secs INTEGER,
    match_demo_sha256 TEXT,
    demo_source_url TEXT,
    has_bots INTEGER DEFAULT 0,
    ktx_fetched INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_mode ON matches(match_mode);
CREATE INDEX IF NOT EXISTS idx_matches_map ON matches(match_map);
CREATE INDEX IF NOT EXISTS idx_matches_server ON matches(server_hostname);
CREATE INDEX IF NOT EXISTS idx_matches_dmm ON matches(match_dmm);

CREATE TABLE IF NOT EXISTS players (
    match_id BIGINT NOT NULL,
    player_name TEXT NOT NULL,
    player_login TEXT,
    player_team TEXT,
    player_is_bot INTEGER DEFAULT 0,
    player_top_color INTEGER,
    player_bottom_color INTEGER,
    player_ping INTEGER,
    player_frags INTEGER,
    player_deaths INTEGER,
    player_teamkills INTEGER,
    player_spawnfrags INTEGER,
    player_suicides INTEGER,
    player_damage_taken INTEGER,
    player_damage_given INTEGER,
    player_damage_team INTEGER,
    player_damage_self INTEGER,
    player_damage_team_weapons INTEGER,
    player_damage_enemy_weapons INTEGER,
    player_damage_to_die INTEGER,
    player_spree_frag INTEGER,
    player_spree_quad INTEGER,
    player_speed_max DOUBLE PRECISION,
    player_speed_avg DOUBLE PRECISION,
    player_sg_attacks INTEGER, player_sg_hits INTEGER,
    player_sg_damage_enemy INTEGER, player_sg_damage_team INTEGER,
    player_ssg_attacks INTEGER, player_ssg_hits INTEGER,
    player_ssg_damage_enemy INTEGER, player_ssg_damage_team INTEGER,
    player_gl_attacks INTEGER, player_gl_directs INTEGER, player_gl_virtual INTEGER,
    player_rl_attacks INTEGER, player_rl_directs INTEGER, player_rl_virtual INTEGER,
    player_rl_dropped INTEGER, player_rl_taken INTEGER, player_rl_transfer INTEGER,
    player_rl_damage_enemy INTEGER, player_rl_damage_team INTEGER,
    player_rl_kills_enemy INTEGER, player_rl_kills_team INTEGER,
    player_lg_attacks INTEGER, player_lg_hits INTEGER,
    player_lg_dropped INTEGER, player_lg_taken INTEGER, player_lg_transfer INTEGER,
    player_lg_damage_enemy INTEGER, player_lg_damage_team INTEGER,
    player_lg_kills_enemy INTEGER, player_lg_kills_team INTEGER,
    player_health15_taken INTEGER, player_health25_taken INTEGER, player_health100_taken INTEGER,
    player_ga_taken INTEGER, player_ya_taken INTEGER, player_ra_taken INTEGER,
    player_quad_taken INTEGER, player_quad_time INTEGER,
    player_pent_taken INTEGER, player_ring_taken INTEGER, player_ring_time INTEGER,
    canonical_id TEXT,
    PRIMARY KEY (match_id, player_name)
);
CREATE INDEX IF NOT EXISTS idx_players_name ON players(player_name);
CREATE INDEX IF NOT EXISTS idx_players_canonical_id ON players(canonical_id);

CREATE TABLE IF NOT EXISTS career_totals (
    player_name TEXT PRIMARY KEY,
    total_matches INTEGER, total_4on4 INTEGER, total_2on2 INTEGER, total_1on1 INTEGER,
    total_time_mins INTEGER, total_frags INTEGER, fpm DOUBLE PRECISION,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players_canonical (
    canonical_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    login TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_players_canonical_login ON players_canonical(login);

CREATE TABLE IF NOT EXISTS player_name_map (
    raw_name TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL REFERENCES players_canonical(canonical_id),
    source TEXT NOT NULL,
    confidence DOUBLE PRECISION,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_player_name_map_canonical ON player_name_map(canonical_id);

CREATE TABLE IF NOT EXISTS ratings (
    canonical_id   TEXT NOT NULL,
    mode           TEXT NOT NULL,
    map            TEXT NOT NULL DEFAULT '',
    mu             DOUBLE PRECISION NOT NULL,
    sigma          DOUBLE PRECISION NOT NULL,
    conservative   DOUBLE PRECISION,
    matches_rated  INTEGER DEFAULT 0,
    wins           INTEGER DEFAULT 0,
    losses         INTEGER DEFAULT 0,
    draws          INTEGER DEFAULT 0,
    last_match_id  BIGINT,
    last_match_date TEXT,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (canonical_id, mode, map)
);
CREATE INDEX IF NOT EXISTS idx_ratings_mode_map_mu ON ratings(mode, map, mu DESC);
CREATE INDEX IF NOT EXISTS idx_ratings_mode_map_cons ON ratings(mode, map, conservative DESC);
CREATE INDEX IF NOT EXISTS idx_ratings_player ON ratings(canonical_id);

CREATE TABLE IF NOT EXISTS rating_history (
    canonical_id   TEXT NOT NULL,
    mode           TEXT NOT NULL,
    map            TEXT NOT NULL DEFAULT '',
    match_id       BIGINT NOT NULL,
    match_date     TEXT,
    opponent_cid   TEXT,
    outcome        TEXT,
    mu_before      DOUBLE PRECISION,
    mu_after       DOUBLE PRECISION,
    sigma_before   DOUBLE PRECISION,
    sigma_after    DOUBLE PRECISION,
    delta          DOUBLE PRECISION,
    PRIMARY KEY (canonical_id, mode, map, match_id)
);
CREATE INDEX IF NOT EXISTS idx_rating_history_player_date
    ON rating_history(canonical_id, mode, map, match_date);
"""

DROP = """
DROP TABLE IF EXISTS rating_history;
DROP TABLE IF EXISTS ratings;
DROP TABLE IF EXISTS player_name_map;
DROP TABLE IF EXISTS players_canonical;
DROP TABLE IF EXISTS career_totals;
DROP TABLE IF EXISTS players;
DROP TABLE IF EXISTS matches;
"""

# Table-name → (column_list, sqlite_select). Order matters — FKs require
# players_canonical before player_name_map.
TABLES = [
    "matches",
    "players_canonical",
    "player_name_map",
    "career_totals",
    "players",
    "ratings",
    "rating_history",
]


def get_columns(sqlite_conn, table):
    """Return column names in SQLite definition order."""
    return [r[1] for r in sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()]


def copy_table(sqlite_conn, pg_conn, table, batch_size=50_000):
    """Stream rows SQLite → Postgres using COPY FROM (binary-safe text format)."""
    cols = get_columns(sqlite_conn, table)
    col_list = ",".join(cols)

    total = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total == 0:
        print(f"  {table:22s} 0 rows (skip)")
        return 0

    cur = sqlite_conn.execute(f"SELECT {col_list} FROM {table}")
    pg_cur = pg_conn.cursor()

    start = time.time()
    written = 0
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        # Build a tab-delimited buffer for COPY. Postgres COPY treats \N as NULL
        # and requires escaping of \t, \n, \r, \\.
        buf = io.StringIO()
        for row in rows:
            line = "\t".join(_escape(v) for v in row)
            buf.write(line + "\n")
        buf.seek(0)
        pg_cur.copy_expert(
            f"COPY {table} ({col_list}) FROM STDIN WITH (FORMAT text, NULL '\\N')",
            buf,
        )
        written += len(rows)
        elapsed = time.time() - start
        rate = written / elapsed if elapsed else 0
        eta = (total - written) / rate if rate else 0
        print(f"\r  {table:22s} {written:,}/{total:,}  {rate:,.0f}/s  eta {eta:.0f}s   ",
              end="", flush=True)
    pg_conn.commit()
    pg_cur.close()
    print()
    return written


def _escape(v):
    """Format a Python value for Postgres COPY text format."""
    if v is None:
        return "\\N"
    if isinstance(v, str):
        # Escape backslash first, then tab/newline/CR.
        return v.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    ap.add_argument("--pg", default=DEFAULT_PG,
                    help="Postgres URL (default: postgresql:///deepfrag — local socket)")
    ap.add_argument("--reset", action="store_true", help="Drop existing tables first")
    ap.add_argument("--only", help="Comma-separated table list (default: all)")
    args = ap.parse_args()

    if not Path(args.sqlite).exists():
        sys.exit(f"SQLite DB not found: {args.sqlite}")

    print(f"Source: {args.sqlite}")
    print(f"Target: {args.pg}")

    sqlite_conn = sqlite3.connect(args.sqlite)
    pg_conn = psycopg2.connect(args.pg)

    if args.reset:
        print("Dropping existing tables…")
        pg_conn.cursor().execute(DROP)
        pg_conn.commit()

    print("Creating schema…")
    pg_conn.cursor().execute(SCHEMA)
    pg_conn.commit()

    only = set(args.only.split(",")) if args.only else set(TABLES)
    print(f"\nCopying {len(only)} tables…")
    total_rows = 0
    start = time.time()
    for t in TABLES:
        if t in only:
            total_rows += copy_table(sqlite_conn, pg_conn, t)

    elapsed = time.time() - start
    print(f"\nDone: {total_rows:,} rows in {elapsed:.1f}s ({total_rows / elapsed:,.0f}/s)")

    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()

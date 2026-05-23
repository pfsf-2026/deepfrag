#!/usr/bin/env python3
"""Compute TrueSkill ratings — Phase A (1on1 only, W/L-based).

Walks every 1on1 match in chronological order, updates both players' ratings,
persists current state in `ratings` and per-match deltas in `rating_history`.

Outcomes:
  - Higher player_frags wins → trueskill.rate_1vs1(winner, loser)
  - Equal frags → drawn

Run after canonicalize.py (needs players.canonical_id populated).

Defaults: full rebuild each run (clears existing 1on1 rows). Use --incremental
to only rate matches newer than the latest in rating_history (much faster on re-runs).

Usage:
  python rate.py                 # full rebuild for 1on1
  python rate.py --mode 1on1
  python rate.py --incremental
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras
import trueskill

import db as dbmod

DEFAULT_DB = Path(__file__).parent / "data" / "qw-stats.db"

# TrueSkill environment — defaults tuned for 1v1.
# Higher tau allows ratings to drift over time (important for 1on1 where skill changes).
# Small but non-zero draw_probability so equal-frag duels don't blow up the math.
ENV = trueskill.TrueSkill(mu=1500.0, sigma=500.0, beta=250.0, tau=5.0, draw_probability=0.01)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ratings (
    canonical_id   TEXT NOT NULL,
    mode           TEXT NOT NULL,
    map            TEXT NOT NULL DEFAULT '',   -- '' = overall (all maps); else map name
    mu             REAL NOT NULL,
    sigma          REAL NOT NULL,
    conservative   REAL,            -- mu - 3*sigma, used for "settled" leaderboard sort
    matches_rated  INTEGER DEFAULT 0,
    wins           INTEGER DEFAULT 0,
    losses         INTEGER DEFAULT 0,
    draws          INTEGER DEFAULT 0,
    last_match_id  INTEGER,
    last_match_date TEXT,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (canonical_id, mode, map)
);
CREATE INDEX IF NOT EXISTS idx_ratings_mode_map_mu ON ratings(mode, map, mu DESC);
CREATE INDEX IF NOT EXISTS idx_ratings_player ON ratings(canonical_id);

CREATE TABLE IF NOT EXISTS rating_history (
    canonical_id   TEXT NOT NULL,
    mode           TEXT NOT NULL,
    map            TEXT NOT NULL DEFAULT '',
    match_id       INTEGER NOT NULL,
    match_date     TEXT,
    opponent_cid   TEXT,
    outcome        TEXT,             -- 'win' | 'loss' | 'draw'
    mu_before      REAL,
    mu_after       REAL,
    sigma_before   REAL,
    sigma_after    REAL,
    delta          REAL,
    PRIMARY KEY (canonical_id, mode, map, match_id)
);
CREATE INDEX IF NOT EXISTS idx_rating_history_player_date
    ON rating_history(canonical_id, mode, map, match_date);
"""


def ensure_schema(conn):
    """Schema lives in Postgres now — created once by migrate_sqlite_to_pg.py.
    Kept as a no-op for legacy compatibility; we don't auto-migrate here anymore."""
    pass


def _bulk_insert_history(cur, rows):
    """Single round-trip insert via execute_values. ~100× faster than executemany.
    Dedupes by PK (canonical_id, mode, map, match_id) first — rare but real when a
    player has multiple `players` rows in one match (joined/disconnected/rejoined)."""
    # Keep the last row per PK (most recent update wins).
    by_pk = {}
    for r in rows:
        by_pk[(r[0], r[1], r[2], r[3])] = r
    deduped = list(by_pk.values())
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO rating_history
           (canonical_id, mode, map, match_id, match_date, opponent_cid, outcome,
            mu_before, mu_after, sigma_before, sigma_after, delta)
           VALUES %s
           ON CONFLICT (canonical_id, mode, map, match_id) DO UPDATE
           SET match_date=EXCLUDED.match_date, opponent_cid=EXCLUDED.opponent_cid,
               outcome=EXCLUDED.outcome, mu_before=EXCLUDED.mu_before,
               mu_after=EXCLUDED.mu_after, sigma_before=EXCLUDED.sigma_before,
               sigma_after=EXCLUDED.sigma_after, delta=EXCLUDED.delta""",
        deduped,
        page_size=2000,
    )


def _bulk_insert_ratings(cur, rows):
    """Same trick for the per-player ratings table. unique_opponents added 2026-05-21
    for the diversity penalty — counts distinct opponents in this bucket."""
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO ratings
           (canonical_id, mode, map, mu, sigma, conservative,
            matches_rated, wins, losses, draws,
            last_match_id, last_match_date, updated_at, unique_opponents)
           VALUES %s
           ON CONFLICT (canonical_id, mode, map) DO UPDATE SET
             mu=EXCLUDED.mu, sigma=EXCLUDED.sigma, conservative=EXCLUDED.conservative,
             matches_rated=EXCLUDED.matches_rated, wins=EXCLUDED.wins,
             losses=EXCLUDED.losses, draws=EXCLUDED.draws,
             last_match_id=EXCLUDED.last_match_id, last_match_date=EXCLUDED.last_match_date,
             updated_at=EXCLUDED.updated_at, unique_opponents=EXCLUDED.unique_opponents""",
        rows,
        page_size=2000,
    )


def load_existing_ratings(conn, mode, map_bucket=''):
    """Return (cache, stats) for incremental runs within a single (mode, map) bucket."""
    cache = {}
    stats = {}
    cur = conn.cursor()
    cur.execute(
        "SELECT canonical_id, mu, sigma, matches_rated, wins, losses, draws "
        "FROM ratings WHERE mode=%s AND map=%s",
        (mode, map_bucket),
    )
    for r in cur.fetchall():
        cid = r["canonical_id"]
        cache[cid] = ENV.create_rating(mu=r["mu"], sigma=r["sigma"])
        stats[cid] = {"matches": r["matches_rated"] or 0, "wins": r["wins"] or 0,
                      "losses": r["losses"] or 0, "draws": r["draws"] or 0}
    cur.close()
    return cache, stats


def list_maps_for_mode(conn, mode, min_matches=10):
    """Return distinct maps with at least `min_matches` matches in this mode."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT match_map FROM matches
        WHERE match_mode = %s AND match_map IS NOT NULL
        GROUP BY match_map
        HAVING count(*) >= %s
        ORDER BY count(*) DESC
        """,
        (mode, min_matches),
    )
    out = [r["match_map"] for r in cur.fetchall()]
    cur.close()
    return out


def fetch_matches(conn, mode, since_date=None, map_filter=None):
    """Yield (match_id, match_date, cid_a, frags_a, cid_b, frags_b) for every match in chronological order.

    If map_filter is set, restricts to that map. If None, returns all maps for the mode.
    Self-join on match_id with canonical_id ordering so each match yields exactly one row.
    """
    where_extra = ""
    params = {"mode": mode}
    if since_date:
        where_extra += " AND m.match_date > %(since)s"
        params["since"] = since_date
    if map_filter:
        where_extra += " AND m.match_map = %(map)s"
        params["map"] = map_filter
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT m.match_id, m.match_date,
               p1.canonical_id AS cid_a, p1.player_frags AS f_a,
               p2.canonical_id AS cid_b, p2.player_frags AS f_b
        FROM matches m
        JOIN players p1 ON p1.match_id = m.match_id
        JOIN players p2 ON p2.match_id = m.match_id
        WHERE m.match_mode = %(mode)s
          AND p1.canonical_id IS NOT NULL
          AND p2.canonical_id IS NOT NULL
          AND p1.canonical_id < p2.canonical_id
          {where_extra}
        ORDER BY m.match_date
        """,
        params,
    )
    for r in cur.fetchall():
        yield r["match_id"], r["match_date"], r["cid_a"], r["f_a"], r["cid_b"], r["f_b"]
    cur.close()


def rate_bucket(db, mode, map_bucket, now, full_rebuild=True, per_map_min=5):
    """Run TrueSkill over all matches in (mode, map_bucket).
       map_bucket='' = overall (all maps in the mode).
       For per-map buckets we only emit ratings for players with >= per_map_min matches.

    Returns (n_rated, n_players_written).
    """
    cur = db.cursor()
    if full_rebuild:
        cur.execute("DELETE FROM ratings WHERE mode=%s AND map=%s", (mode, map_bucket))
        cur.execute("DELETE FROM rating_history WHERE mode=%s AND map=%s", (mode, map_bucket))
        db.commit()
        cache, stats = {}, {}
    else:
        cache, stats = load_existing_ratings(db, mode, map_bucket)

    map_filter = map_bucket if map_bucket else None
    matches = list(fetch_matches(db, mode, map_filter=map_filter))
    if not matches:
        return 0, 0

    history_rows = []
    n_skipped = 0
    for match_id, match_date, cid_a, f_a, cid_b, f_b in matches:
        if cid_a == cid_b or f_a is None or f_b is None:
            n_skipped += 1
            continue

        ra = cache.setdefault(cid_a, ENV.create_rating())
        rb = cache.setdefault(cid_b, ENV.create_rating())
        sa = stats.setdefault(cid_a, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        sb = stats.setdefault(cid_b, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        mu_a_b, sig_a_b = ra.mu, ra.sigma
        mu_b_b, sig_b_b = rb.mu, rb.sigma

        if f_a > f_b:
            ra_new, rb_new = ENV.rate_1vs1(ra, rb)
            out_a, out_b = "win", "loss"
            sa["wins"] += 1; sb["losses"] += 1
        elif f_b > f_a:
            rb_new, ra_new = ENV.rate_1vs1(rb, ra)
            out_a, out_b = "loss", "win"
            sb["wins"] += 1; sa["losses"] += 1
        else:
            ra_new, rb_new = ENV.rate_1vs1(ra, rb, drawn=True)
            out_a = out_b = "draw"
            sa["draws"] += 1; sb["draws"] += 1

        cache[cid_a] = ra_new; cache[cid_b] = rb_new
        sa["matches"] += 1; sb["matches"] += 1

        history_rows.append((cid_a, mode, map_bucket, match_id, match_date, cid_b, out_a,
                             mu_a_b, ra_new.mu, sig_a_b, ra_new.sigma, ra_new.mu - mu_a_b))
        history_rows.append((cid_b, mode, map_bucket, match_id, match_date, cid_a, out_b,
                             mu_b_b, rb_new.mu, sig_b_b, rb_new.sigma, rb_new.mu - mu_b_b))

        if len(history_rows) >= 5000:
            _bulk_insert_history(cur, history_rows)
            history_rows = []
            db.commit()

    if history_rows:
        _bulk_insert_history(cur, history_rows)

    # Write ratings — bulk insert via execute_values for speed. For per-map, apply
    # the matches threshold so we don't store noise for someone who played twice.
    # Overall (map_bucket='') always stored. unique_opponents tracks each player's
    # distinct opponents in this bucket, used by the diversity penalty downstream.
    unique_opps = {}
    for cid in cache:
        unique_opps[cid] = set()
    # Track from history_rows BEFORE we batched them, but they were already inserted.
    # Re-query history for this bucket to compute unique opponents per player.
    cur.execute("""
        SELECT canonical_id, COUNT(DISTINCT opponent_cid) AS n
        FROM rating_history WHERE mode = %s AND map = %s AND opponent_cid IS NOT NULL
        GROUP BY canonical_id
    """, (mode, map_bucket))
    # db.connect() uses RealDictCursor → access by column name, not index.
    uniq_counts = {r["canonical_id"]: r["n"] for r in cur.fetchall()}

    rating_rows = []
    for cid, r in cache.items():
        s = stats.get(cid, {})
        if map_bucket and s["matches"] < per_map_min:
            continue
        rating_rows.append((cid, mode, map_bucket, r.mu, r.sigma, r.mu - 3 * r.sigma,
                            s["matches"], s["wins"], s["losses"], s["draws"],
                            None, None, now, uniq_counts.get(cid, 0)))
    if rating_rows:
        _bulk_insert_ratings(cur, rating_rows)
    db.commit()
    cur.close()
    return len(matches), len(rating_rows)


def run(db_path: Path, mode: str = "1on1", incremental: bool = False, per_map_min: int = 5):
    # db_path retained for legacy CLI compatibility — actual connection comes from db.connect()
    # which defaults to Cloud SQL Postgres (override via DEEPFRAG_PG_URL / DEEPFRAG_USE_SQLITE=1).
    db = dbmod.connect()
    ensure_schema(db)
    now = datetime.now(timezone.utc).isoformat()
    full_rebuild = not incremental

    # 1. Overall mode rating (all maps lumped together)
    print(f"Rating {mode} overall…")
    start = datetime.now()
    n_matches, n_players = rate_bucket(db, mode, '', now, full_rebuild=full_rebuild, per_map_min=0)
    elapsed = (datetime.now() - start).total_seconds()
    print(f"  {n_matches:,} matches → {n_players:,} players rated in {elapsed:.1f}s")

    # 2. Per-map ratings: one independent TrueSkill series per map
    maps = list_maps_for_mode(db, mode, min_matches=50)
    print(f"\nRating {mode} per-map across {len(maps)} maps "
          f"(min {per_map_min} matches per player to be stored)…")
    start = datetime.now()
    total_matches = 0
    total_players = 0
    for m in maps:
        n_matches, n_players = rate_bucket(db, mode, m, now, full_rebuild=full_rebuild,
                                            per_map_min=per_map_min)
        total_matches += n_matches
        total_players += n_players
    elapsed = (datetime.now() - start).total_seconds()
    print(f"  {total_matches:,} match-events → {total_players:,} per-map ratings written in {elapsed:.1f}s")

    # Sanity: top 10 overall + per-map sample for aerowalk
    print(f"\nTop 10 {mode} OVERALL (by conservative rating):")
    sanity_cur = db.cursor()
    sanity_cur.execute(
        """
        SELECT r.canonical_id, pc.display_name, r.mu, r.sigma, r.conservative,
               r.matches_rated, r.wins, r.losses
        FROM ratings r
        LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
        WHERE r.mode = %s AND r.map = '' AND r.matches_rated >= 50
        ORDER BY r.conservative DESC LIMIT 10
        """,
        (mode,),
    )
    top = sanity_cur.fetchall()
    for t in top:
        name = t["display_name"] or t["canonical_id"]
        print(f"  μ={t['mu']:7.1f} σ={t['sigma']:5.1f} cons={t['conservative']:7.1f}  "
              f"{t['wins']:5}W-{t['losses']:5}L  {name}")

    print(f"\nTop 10 {mode} on AEROWALK (per-map rating):")
    sanity_cur.execute(
        """
        SELECT r.canonical_id, pc.display_name, r.mu, r.sigma, r.conservative,
               r.matches_rated, r.wins, r.losses
        FROM ratings r
        LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
        WHERE r.mode = %s AND r.map = 'aerowalk'
        ORDER BY r.conservative DESC LIMIT 10
        """,
        (mode,),
    )
    aero = sanity_cur.fetchall()
    sanity_cur.close()
    for t in aero:
        name = t["display_name"] or t["canonical_id"]
        print(f"  μ={t['mu']:7.1f} σ={t['sigma']:5.1f} cons={t['conservative']:7.1f}  "
              f"{t['wins']:5}W-{t['losses']:5}L  {name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--mode", default="1on1", choices=["1on1", "2on2", "4on4"])
    p.add_argument("--incremental", action="store_true",
                   help="Only rate matches after the latest match_date in rating_history")
    args = p.parse_args()
    run(Path(args.db), args.mode, args.incremental)

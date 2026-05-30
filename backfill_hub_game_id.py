#!/usr/bin/env python3
"""Backfill matches.hub_game_id — the real hub gameId for every match.

THE BUG THIS FIXES: matches has two epochs. NEW rows (sync.py) have
match_id == hub gameId. OLD rows (migrate_sqlite_to_pg.py, ~141k) have a
synthetic NEGATIVE match_id that is NOT a hub id and carry no demo_sha256 —
only a demo filename in demo_source_url. The mvd-api (demo parsing) only
accepts the real hub gameId. So every demo-addressing feature silently broke
on old data. hub_game_id becomes the single source of truth for reaching a
demo, for BOTH epochs.

Strategy:
  - positives: hub_game_id = match_id (already true; re-affirmed, idempotent).
  - negatives: correlate by demo FILENAME. We pull the hub's (id, filename)
    index once (paged), build filename->id in memory, then UPDATE in batches.
    Far fewer round-trips than per-row LIKE queries, and re-runnable.

demo_source_url forms:
  ours (old):  "duel_a_vs_b[dm4]20240629-1333.mvd"   (bare filename)
  ours (new):  same bare filename
  hub:         "http://host:port/dl/demos/duel_a_vs_b[dm4]....mvd"  (full URL)
We key on the basename (last path segment) on both sides.

Usage:
  python backfill_hub_game_id.py            # full run
  python backfill_hub_game_id.py --dry      # report only, no writes
"""
from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
import sync

PG_URL = os.environ.get("DEEPFRAG_PG_URL", "postgresql:///deepfrag")
DRY = "--dry" in sys.argv
PROGRESS = "/tmp/backfill_progress.txt"


def log(msg):
    with open(PROGRESS, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)


def basename(url: str) -> str:
    if not url:
        return ""
    return url.rstrip("/").split("/")[-1].strip()


def build_hub_index() -> dict:
    """filename(basename) -> hub id, pulled from the hub via plain limit/offset
    pagination (verified working; the Range-header form silently returned
    nothing). Loops until a short page."""
    # PostgREST caps each response at 1000 rows regardless of the limit param,
    # so we page in 1000s through all ~167k hub games.
    idx = {}
    offset = 0
    page = 1000
    empty_streak = 0
    while True:
        r = sync.SESSION.get(
            sync.HUB_URL,
            params={"select": "id,demo_source_url", "order": "id.asc",
                    "limit": str(page), "offset": str(offset)},
            headers=sync.HUB_HEADERS,
            timeout=90,
        )
        if r.status_code not in (200, 206):
            log(f"  hub page offset={offset} HTTP {r.status_code}: {r.text[:120]}")
            # transient — retry a couple times before giving up
            empty_streak += 1
            if empty_streak >= 3:
                break
            time.sleep(2)
            continue
        rows = r.json()
        if not rows:
            break
        empty_streak = 0
        for row in rows:
            bn = basename(row.get("demo_source_url") or "")
            if bn:
                idx[bn] = row["id"]
        if offset % 20000 == 0:
            log(f"  hub index: offset={offset} keys={len(idx)}")
        if len(rows) < page:
            break
        offset += len(rows)
    log(f"  hub index complete: {len(idx)} filenames from offset {offset}")
    return idx


def main():
    open(PROGRESS, "w").close()
    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM matches WHERE match_id<0 AND hub_game_id IS NULL AND demo_source_url IS NOT NULL")
    todo = cur.fetchone()[0]
    log(f"old matches needing hub_game_id: {todo}")

    log("building hub filename->id index…")
    hub = build_hub_index()
    log(f"hub index built: {len(hub)} filenames")

    # Pull the old matches' (match_id, filename), match in memory.
    cur.execute("SELECT match_id, demo_source_url FROM matches WHERE match_id<0 AND hub_game_id IS NULL AND demo_source_url IS NOT NULL")
    rows = cur.fetchall()
    updates = []
    misses = 0
    for mid, url in rows:
        gid = hub.get(basename(url))
        if gid is not None:
            updates.append((gid, mid))
        else:
            misses += 1
    log(f"matched {len(updates)}/{len(rows)} ({100*len(updates)//max(len(rows),1)}%), misses={misses}")

    if DRY:
        log("DRY RUN — no writes. sample matches: " + str(updates[:3]))
        conn.close()
        return

    # Batched UPDATE via execute_values temp join.
    from psycopg2.extras import execute_values
    B = 5000
    done = 0
    for i in range(0, len(updates), B):
        chunk = updates[i:i+B]
        execute_values(
            cur,
            "UPDATE matches m SET hub_game_id = v.gid FROM (VALUES %s) AS v(gid, mid) WHERE m.match_id = v.mid",
            chunk,
        )
        conn.commit()
        done += len(chunk)
        log(f"  updated {done}/{len(updates)}")

    cur.execute("SELECT count(*) FROM matches WHERE hub_game_id IS NOT NULL")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM matches WHERE hub_game_id IS NULL")
    still = cur.fetchone()[0]
    log(f"DONE backfill. hub_game_id populated: {total}, still null: {still}")

    # Dedup cross-epoch duplicates: the SAME game imported as both an old
    # (negative match_id) row and a new (positive) row double-counts in stats.
    # Now that hub_game_id is the canonical key, drop the negative copy where a
    # positive twin exists. Transactional; safe to re-run (no-op once clean).
    cur.execute("""
        CREATE TEMP TABLE _dups ON COMMIT DROP AS
        SELECT min(match_id) FILTER (WHERE match_id < 0) AS neg_id
        FROM matches WHERE demo_source_url IS NOT NULL
        GROUP BY demo_source_url
        HAVING count(*) > 1 AND bool_or(match_id>0) AND bool_or(match_id<0)
    """)
    cur.execute("SELECT count(*) FROM _dups WHERE neg_id IS NOT NULL")
    ndup = cur.fetchone()[0]
    if ndup:
        cur.execute("DELETE FROM players WHERE match_id IN (SELECT neg_id FROM _dups WHERE neg_id IS NOT NULL)")
        pdel = cur.rowcount
        cur.execute("DELETE FROM rating_history WHERE match_id IN (SELECT neg_id FROM _dups WHERE neg_id IS NOT NULL)")
        rdel = cur.rowcount
        cur.execute("DELETE FROM matches WHERE match_id IN (SELECT neg_id FROM _dups WHERE neg_id IS NOT NULL)")
        mdel = cur.rowcount
        conn.commit()
        log(f"DEDUP: removed {mdel} duplicate old-epoch games ({pdel} player rows, {rdel} rating rows)")
    else:
        conn.commit()
        log("DEDUP: no cross-epoch duplicates found")
    conn.close()


if __name__ == "__main__":
    main()

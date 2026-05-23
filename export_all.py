#!/usr/bin/env python3
"""Generate profile.json for every canonical player above a match threshold.

Parallelized via thread pool — each worker holds its own SQLite connection
(SQLite handles concurrent reads fine; we never write during export).

Outputs:
  public/profiles/{canonical_id}.json   — per-player profile (~2 MB each)
  public/profiles/index.json            — list of all generated players with
                                          counts + display names, for a UI listing page

Usage:
  python export_all.py                      # default threshold 100
  python export_all.py --threshold 50       # more players
  python export_all.py --workers 4
  python export_all.py --limit 20           # testing
"""

import argparse
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from export import build_profile, ratings_for_player

DEFAULT_DB = Path(__file__).parent / "data" / "qw-stats.db"
# Nuxt reads from nuxt/public at build/runtime — write straight there to avoid
# the silent two-directory drift bug we hit in May 2026.
DEFAULT_OUT = Path(__file__).parent / "nuxt" / "public" / "profiles"


def list_players(db_path: Path, threshold: int, new_player_recent_min: int = 5,
                 new_player_window_days: int = 90):
    """Return players to profile.

    Rule: include if lifetime matches >= `threshold` (default 10) OR they're a
    new player with at least `new_player_recent_min` matches in the last
    `new_player_window_days` days. The second clause catches active newcomers
    who don't yet have a long history but are clearly engaged.
    """
    from datetime import datetime, timedelta, timezone
    recent_cutoff = (datetime.now(timezone.utc) - timedelta(days=new_player_window_days)).isoformat()
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute("""
        SELECT p.canonical_id,
               pc.display_name,
               pc.login,
               count(DISTINCT p.match_id) AS matches,
               sum(CASE WHEN m.match_date >= :since THEN 1 ELSE 0 END) AS recent_matches,
               min(m.match_date) AS first_seen,
               max(m.match_date) AS last_seen
        FROM players p
        JOIN matches m ON m.match_id = p.match_id
        LEFT JOIN players_canonical pc ON pc.canonical_id = p.canonical_id
        WHERE p.canonical_id IS NOT NULL
        GROUP BY p.canonical_id
        HAVING matches >= :threshold
            OR recent_matches >= :recent_min
        ORDER BY matches DESC
    """, {
        "since": recent_cutoff,
        "threshold": threshold,
        "recent_min": new_player_recent_min,
    }).fetchall()
    db.close()
    return [dict(r) for r in rows]


def export_one(db_path: Path, out_dir: Path, player: dict) -> tuple:
    """Export a single player's profile JSON. Returns (canonical_id, bytes_written, err_or_None)."""
    cid = player["canonical_id"]
    display = player["display_name"] or cid
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    # WAL mode + readonly-friendly pragmas. Each worker has its own connection.
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
    db.execute("PRAGMA temp_store = MEMORY")
    db.execute("PRAGMA cache_size = -64000")  # 64 MB per worker
    try:
        profile = build_profile(db, display, cid)
        profile["canonical_id"] = cid
        profile["ratings"] = ratings_for_player(db, cid)
    except Exception as e:
        return cid, 0, str(e)
    finally:
        db.close()
    path = out_dir / f"{cid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, separators=(",", ":")))
    return cid, path.stat().st_size, None


def write_index(out_dir: Path, players: list):
    """Write index.json — lightweight player list for the UI's browse page."""
    idx = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(players),
        "players": [
            {
                "canonical_id": p["canonical_id"],
                "display": p["display_name"] or p["canonical_id"],
                "matches": p["matches"],
                "first_seen": p["first_seen"],
                "last_seen": p["last_seen"],
            }
            for p in players
        ],
    }
    (out_dir / "index.json").write_text(json.dumps(idx, separators=(",", ":")))


def find_changed_since(db_path: Path, checkpoint_iso: str) -> set:
    """Return canonical_ids whose match list or rating row changed after checkpoint."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        changed = set()
        for r in db.execute("""
            SELECT DISTINCT p.canonical_id
            FROM players p JOIN matches m ON m.match_id = p.match_id
            WHERE m.match_date > ? AND p.canonical_id IS NOT NULL
        """, (checkpoint_iso,)):
            changed.add(r["canonical_id"])
        for r in db.execute(
            "SELECT DISTINCT canonical_id FROM ratings WHERE updated_at > ?",
            (checkpoint_iso,),
        ):
            changed.add(r["canonical_id"])
        return changed
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--threshold", type=int, default=10,
                        help="Minimum lifetime matches to generate a profile (default 10). "
                             "New players with ≥5 matches in last 90 days are always included.")
    parser.add_argument("--recent-min", type=int, default=5,
                        help="A player with this many matches in last 90d is always profiled (default 5)")
    parser.add_argument("--workers", type=int, default=16,
                        help="Parallel workers. Default 16 (~1.6× CPU count on 10-core box).")
    parser.add_argument("--limit", type=int, help="Cap how many players to export (testing)")
    parser.add_argument("--full", action="store_true",
                        help="Force a full regenerate (ignore checkpoint).")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out)
    checkpoint_path = out_dir / "_last_export.txt"
    run_start = datetime.now(timezone.utc).isoformat()

    print(f"Selecting players: lifetime ≥ {args.threshold} matches OR ≥ {args.recent_min} matches in last 90d…")
    players = list_players(db_path, args.threshold, new_player_recent_min=args.recent_min)
    if args.limit:
        players = players[: args.limit]
    print(f"  {len(players):,} players in cohort")

    # Incremental: filter cohort to only players touched since last successful export.
    # Falls back to full if checkpoint missing, --full flag, or any player JSON missing
    # (catches new players who joined the cohort since last run).
    if not args.full and checkpoint_path.exists():
        checkpoint_iso = checkpoint_path.read_text().strip()
        changed = find_changed_since(db_path, checkpoint_iso)
        new_to_cohort = {p["canonical_id"] for p in players
                         if not (out_dir / f"{p['canonical_id']}.json").exists()}
        needs_regen = changed | new_to_cohort
        before = len(players)
        players = [p for p in players if p["canonical_id"] in needs_regen]
        print(f"  incremental: {len(players):,} need regen ({before - len(players):,} skipped, "
              f"checkpoint {checkpoint_iso})")
    else:
        print(f"  full rebuild (no checkpoint or --full)")
    if not players:
        print("Nothing to regen. Updating index + checkpoint…")
        write_index(out_dir, list_players(db_path, args.threshold, new_player_recent_min=args.recent_min))
        checkpoint_path.write_text(run_start)
        return

    print(f"\nGenerating profiles ({args.workers} workers)…")
    start = datetime.now()
    n_done = n_err = total_bytes = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(export_one, db_path, out_dir, p): p for p in players}
        for fut in as_completed(futures):
            cid, size, err = fut.result()
            if err:
                n_err += 1
                if n_err <= 5:
                    print(f"  ERR {cid}: {err}", flush=True)
            else:
                n_done += 1
                total_bytes += size
            done = n_done + n_err
            if done % 20 == 0 or done == len(players):
                elapsed = (datetime.now() - start).total_seconds()
                rate = done / elapsed if elapsed else 0
                eta_sec = (len(players) - done) / rate if rate else 0
                print(f"  {done:4}/{len(players)}: {n_done:4} ok, {n_err:3} err, "
                      f"{total_bytes/1e6:.1f} MB, {rate:.1f}/s, eta {eta_sec/60:.1f} min",
                      flush=True)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\nDone: {n_done:,} profiles ({total_bytes/1e6:.1f} MB total) in {elapsed:.0f}s")

    print("\nWriting index.json…")
    # Always write index from the full cohort, not just the regen'd subset, so
    # players we skipped this run still appear on the browse page.
    full_cohort = list_players(db_path, args.threshold, new_player_recent_min=args.recent_min)
    write_index(out_dir, [p for p in full_cohort if (out_dir / f"{p['canonical_id']}.json").exists()])
    print(f"  index covers {len(full_cohort):,} players")

    # Save checkpoint last — only on a successful run, so a crashed export
    # doesn't silently skip players on the next attempt.
    checkpoint_path.write_text(run_start)
    print(f"Checkpoint written: {checkpoint_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Find and remove near-duplicate matches across sources.

The original "10-min bucket" approach failed because hub and xantom record
timestamps at DIFFERENT match phases:
  - Hub:    match-start time (server registration)
  - Xantom: demo-end time   ≈ start + timelimit (10/15/20 min) + small overhead

So a 1on1 hub match at 00:54:06 has its xantom twin at 01:04:16 — exactly 10:10
later. The 10-min bucket window missed it.

New strategy: group matches by (map, canonical_player_set), sort by time, then
walk pairs — any two within THRESHOLD_MINUTES of each other are dupes. The
threshold should be slightly more than the longest match timelimit + recording
delay; 30 minutes covers 4on4 (20-min timelimit + buffer).
"""

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

THRESHOLD_MINUTES = 30


def parse_iso(s):
    # SQLite stores '2024-04-11T21:29:03+00:00' — datetime.fromisoformat handles it.
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def find_dups(db):
    """Scan ALL matches, grouping by (map, sorted_canonical_player_set).
    Within each group, find pairs within THRESHOLD_MINUTES → mark dups.

    Returns: (groups_processed, dup_pairs_found, ids_to_delete_list)
    """
    # Pull matches with their canonical player sets in one big query.
    print("  Building match→signature table (this scans the whole DB)…")
    rows = db.execute("""
        SELECT m.match_id, m.match_date, m.match_map,
               (SELECT GROUP_CONCAT(lower(COALESCE(p2.canonical_id, p2.player_name)), '|')
                FROM (SELECT canonical_id, player_name FROM players
                      WHERE match_id = m.match_id
                      ORDER BY lower(COALESCE(canonical_id, player_name))) p2
               ) AS cids
        FROM matches m
    """).fetchall()
    print(f"  Loaded {len(rows):,} matches; bucketing by (map, players)…")

    # Group by (map, cids) -> [(match_id, parsed_datetime), ...]
    groups = defaultdict(list)
    for r in rows:
        if not r[3]:
            continue
        dt = parse_iso(r[1])
        if dt is None:
            continue
        groups[(r[2], r[3])].append((r[0], dt))

    # Dedup ONLY across sources (hub ↔ xantom). Same-source matches with same
    # content + close time are legit rematches — never dedup those.
    # Reason: hub is one event stream (one ID per match, no internal dupes),
    # xantom is another (each demo = unique file). A genuine 10:45-apart rematch
    # on same map vs same opponent will appear in BOTH sources, but it's two
    # separate matches in real life.
    print(f"  Walking {len(groups):,} (map, player_set) groups (cross-source only)…")
    to_delete = set()
    n_dup_pairs = 0
    threshold_sec = THRESHOLD_MINUTES * 60

    for (mp, cids), entries in groups.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda x: x[1])
        # For each entry, check if a cross-source neighbor (within threshold) exists.
        # If so, dedup by deleting the negative-ID (xantom) one.
        n = len(entries)
        for i in range(n):
            if entries[i][0] in to_delete:
                continue
            for j in range(i + 1, n):
                if entries[j][0] in to_delete:
                    continue
                gap_sec = (entries[j][1] - entries[i][1]).total_seconds()
                if gap_sec > threshold_sec:
                    break  # entries are sorted; further ones only get further
                # Both must be defined AND different sources (one pos, one neg)
                a_id, b_id = entries[i][0], entries[j][0]
                if (a_id > 0) == (b_id > 0):
                    continue  # same source → legit rematch, skip
                # Cross-source pair within window → dedup. Keep hub, delete xantom.
                to_delete.add(b_id if b_id < 0 else a_id)
                n_dup_pairs += 1

    return len(groups), n_dup_pairs, to_delete


def run(db_path: str, dry_run: bool):
    db = sqlite3.connect(db_path)
    print(f"Scanning {db_path} for near-duplicates (window = {THRESHOLD_MINUTES} min)…")
    n_groups, n_pairs, ids_to_delete = find_dups(db)
    print(f"  {n_groups:,} (map, player_set) groups examined")
    print(f"  {n_pairs:,} dup pairs found")
    print(f"  {len(ids_to_delete):,} matches will be deleted")

    if dry_run:
        print("\n[dry-run] First 5 IDs to delete:", list(ids_to_delete)[:5])
        return

    if not ids_to_delete:
        print("Nothing to delete.")
        return

    print("\nDeleting…")
    # Delete in batches to avoid SQL too-many-vars limit.
    ids = list(ids_to_delete)
    batch = 500
    n_deleted = 0
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        ph = ",".join("?" * len(chunk))
        db.execute(f"DELETE FROM players WHERE match_id IN ({ph})", chunk)
        db.execute(f"DELETE FROM matches WHERE match_id IN ({ph})", chunk)
        n_deleted += len(chunk)
    db.commit()
    print(f"  Deleted {n_deleted:,} duplicate matches")

    # Final counts
    n_matches = db.execute("SELECT count(*) FROM matches").fetchone()[0]
    n_players = db.execute("SELECT count(*) FROM players").fetchone()[0]
    n_cronus = db.execute("SELECT count(*) FROM players WHERE canonical_id = 'cronus'").fetchone()[0]
    print(f"\nAfter cleanup:")
    print(f"  Total matches: {n_matches:,}")
    print(f"  Total player rows: {n_players:,}")
    print(f"  Cronus matches: {n_cronus:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).parent / "data" / "qw-stats.db"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=int, default=THRESHOLD_MINUTES,
                        help="Dedup window in minutes (default 30)")
    args = parser.parse_args()
    THRESHOLD_MINUTES = args.threshold
    run(args.db, args.dry_run)

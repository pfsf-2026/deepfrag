#!/usr/bin/env python3
"""Backfill canonical_id for every player row in the database.

Run this:
  - Once, after deploying name_canon.py + new schema (initial backfill)
  - Any time aliases.yaml changes (re-run to apply new manual aliases)
  - After --apply-reviews on the canonicalizer to commit accepted/rejected fuzzy matches

What it does:
  1. Ensures players_canonical, player_name_map tables exist
  2. Ensures players.canonical_id column exists (adds it if missing)
  3. Iterates every DISTINCT player_name in the players table
  4. Resolves each through the canonicalizer (login → aliases.yaml → fuzzy → new)
  5. Inserts/upserts into players_canonical and player_name_map
  6. Updates players.canonical_id for every row
  7. Saves the review queue (.review_queue.yaml) for human inspection

Reports a summary at the end including:
  - How many distinct names mapped to how many canonical players
  - How many went into the fuzzy review queue
  - The top 10 most-common canonicals by match count
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras

import db as dbmod
from name_canon import Canonicalizer, clean_for_display


def ensure_schema(db):
    """Schema lives in Postgres now — created once by migrate_sqlite_to_pg.py.
    The canonical_id column is already there. No-op for legacy compat."""
    pass


def get_distinct_names(db):
    """Return [(raw_name, login_or_None, match_count)] for every distinct player_name."""
    cur = db.cursor()
    cur.execute("""
        SELECT player_name,
               COALESCE(NULLIF(player_login, ''), NULL) AS login,
               count(*) AS n
        FROM players
        GROUP BY player_name, player_login
        ORDER BY n DESC
    """)
    rows = [(r["player_name"], r["login"], r["n"]) for r in cur.fetchall()]
    cur.close()
    return rows


def upsert_canonical(cur, cid: str, display: str, login: str, now: str):
    cur.execute("""
        INSERT INTO players_canonical (canonical_id, display_name, login, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(canonical_id) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            login = COALESCE(NULLIF(EXCLUDED.login, ''), players_canonical.login),
            updated_at = EXCLUDED.updated_at
    """, (cid, display, login or "", now, now))


def upsert_name_map(cur, raw_name: str, cid: str, source: str, confidence: float, now: str):
    cur.execute("""
        INSERT INTO player_name_map (raw_name, canonical_id, source, confidence, created_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(raw_name) DO UPDATE SET
            canonical_id = EXCLUDED.canonical_id,
            source = EXCLUDED.source,
            confidence = EXCLUDED.confidence
    """, (raw_name, cid, source, confidence, now))


def best_display_for(rows_with_counts):
    """Pick the cleanest readable variant as display name.

    Prefer variants whose CLEANED form (stripped of color codes, decorative chars)
    is non-empty and matches the variant verbatim — that means the variant is
    already plain ASCII without escape junk. Among those, pick the most common.
    Otherwise fall back to clean-up the most-common variant.
    """
    if not rows_with_counts:
        return None
    clean_unchanged = [(raw, n) for raw, n in rows_with_counts
                       if clean_for_display(raw) == raw and raw]
    if clean_unchanged:
        return max(clean_unchanged, key=lambda x: x[1])[0]
    # No fully-clean variant exists — return the cleaned form of the most common
    raw_best = max(rows_with_counts, key=lambda x: x[1])[0]
    cleaned = clean_for_display(raw_best)
    return cleaned or raw_best


def run(db_path: str, dry_run: bool = False):
    db = dbmod.connect()
    ensure_schema(db)
    c = Canonicalizer.load()
    now = datetime.now(timezone.utc).isoformat()

    print(f"Loading distinct player names from {db_path}…")
    names = get_distinct_names(db)
    print(f"  {len(names):,} distinct raw names across {sum(n for _, _, n in names):,} player-rows")

    # Resolve every name → (cid, decision), tracking everything we need for the upsert
    decisions = Counter()
    resolved = []            # [(raw, cid, decision, count, login), ...]
    cid_to_variants = {}     # cid → [(raw_name, match_count), ...]
    cid_to_login = {}        # cid → login (first non-empty seen)

    for raw, login, count in names:
        cid, decision = c.resolve(raw, login)
        decisions[decision] += 1
        resolved.append((raw, cid, decision, count, login))
        cid_to_variants.setdefault(cid, []).append((raw, count))
        if login and cid not in cid_to_login:
            cid_to_login[cid] = login

    # Pick display name per canonical:
    #   1. If aliases.yaml has a `display` for this cid → use it (and isn't just the slug)
    #   2. Else pick the most-common raw variant
    cid_displays = {}
    for cid in cid_to_variants:
        rec = c.records.get(cid)
        if rec and rec.display and rec.display != cid:
            cid_displays[cid] = rec.display
        else:
            cid_displays[cid] = best_display_for(cid_to_variants[cid])

    if dry_run:
        print("\n[dry-run] Would update database. Summary:")
    else:
        print("\nWriting to database…")
        cur = db.cursor()
        # 1. players_canonical
        for cid, display in cid_displays.items():
            upsert_canonical(cur, cid, display, cid_to_login.get(cid, ""), now)
        # 2. player_name_map (one row per raw name with its real decision)
        for raw, cid, decision, _, _ in resolved:
            upsert_name_map(cur, raw, cid, decision, 1.0, now)
        # 3. Bulk-update players.canonical_id using a one-shot CTE — much faster than
        # one UPDATE per name (which would be ~8k round trips over public internet).
        update_rows = [(cid, raw) for raw, cid, _, _, _ in resolved]
        psycopg2.extras.execute_values(
            cur,
            "UPDATE players SET canonical_id = data.cid FROM (VALUES %s) AS data(cid, raw_name) "
            "WHERE players.player_name = data.raw_name",
            update_rows,
            page_size=2000,
        )
        n_rows_updated = cur.rowcount
        cur.close()
        db.commit()
        print(f"  Updated {n_rows_updated:,} player rows with canonical_id")

    # Persist review queue for human inspection
    c.save_review_queue()

    # ─── Report ───────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"Decision summary:")
    for src, count in decisions.most_common():
        print(f"  {src:10} {count:6,}")

    print(f"\nCanonical identities: {len(cid_displays):,}")
    top_by_matches = sorted(
        ((cid, sum(c for _, c in vs)) for cid, vs in cid_to_variants.items()),
        key=lambda x: -x[1],
    )[:15]
    print(f"\nTop 15 canonicals by match count:")
    for cid, n in top_by_matches:
        variants = cid_to_variants[cid]
        var_str = ", ".join(f"{v!r}({n})" for v, n in sorted(variants, key=lambda x: -x[1])[:3])
        print(f"  {n:6,}  {cid:25} [{len(variants)} variants] {var_str}")

    if c.review_queue:
        print(f"\n⚠️  {len(c.review_queue)} fuzzy matches need human review")
        print(f"    See .review_queue.yaml")
        print(f"    Top 10 pending:")
        for entry in sorted(c.review_queue.values(), key=lambda x: -x.seen_count)[:10]:
            print(f"      score={entry.score:.2f}  raw={entry.raw_name!r}  →?  {entry.suggested_canonical!r}  (seen {entry.seen_count}x)")
        print(f"\n    To accept/reject: edit .review_queue.yaml (set decision: accept|reject),")
        print(f"    then run: python name_canon.py apply-reviews && python canonicalize.py")
    else:
        print(f"\n✓ No fuzzy matches needing review")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(Path(__file__).parent / "data" / "qw-stats.db"))
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    run(args.db, args.dry_run)

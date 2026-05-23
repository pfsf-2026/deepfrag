#!/usr/bin/env python3
"""Assign each canonical player a primary region (NA/EU/OC/SA/AS/AF) based on
where they play the majority of their matches. LAN tournaments excluded so a
visiting player at QHLAN Stockholm doesn't get mis-tagged as EU.

Output: players_canonical.region (text) + region_confidence (0-1) + region_distribution (jsonb).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import db as dbmod

# LAN tournament filter — a match counts as "LAN" only when BOTH
#   (a) its match_tag contains a tournament token, AND
#   (b) its date falls inside that tournament's known window.
# Reason: some players tag random pickup games as "qhlan" outside the event window
# (joke/solidarity). Date+tag together prevents the false positives.
#
# QHLAN runs biennially in Stockholm. Month of the year has fluctuated over editions
# so we use full-year windows for each event year. A qhlan-tagged match in 2025 (a
# non-event year) is a false positive and will NOT be excluded from region counting.
LAN_EVENTS = [
    {"tag_pattern": "qhlan", "start": "2018-01-01", "end": "2018-12-31", "name": "QHLAN 2018"},
    {"tag_pattern": "qhlan", "start": "2020-01-01", "end": "2020-12-31", "name": "QHLAN 2020"},
    {"tag_pattern": "qhlan", "start": "2022-01-01", "end": "2022-12-31", "name": "QHLAN 2022"},
    {"tag_pattern": "qhlan", "start": "2024-01-01", "end": "2024-12-31", "name": "QHLAN 2024"},
    {"tag_pattern": "qhlan", "start": "2026-01-01", "end": "2026-12-31", "name": "QHLAN 2026"},
    {"tag_pattern": "qhlan", "start": "2028-01-01", "end": "2028-12-31", "name": "QHLAN 2028"},
]


SCHEMA = """
ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS region TEXT;
ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS region_confidence DOUBLE PRECISION;
ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS region_distribution JSONB;
ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS region_assigned_at TEXT;
CREATE INDEX IF NOT EXISTS idx_players_canonical_region ON players_canonical(region);
"""


def lan_exclusion_sql() -> str:
    """Exclude matches that BOTH tagged with a LAN token AND fall in that LAN's window."""
    if not LAN_EVENTS:
        return ""
    parts = []
    for ev in LAN_EVENTS:
        parts.append(
            f"(LOWER(m.match_tag) LIKE '%{ev['tag_pattern']}%'"
            f" AND m.match_date::timestamptz BETWEEN '{ev['start']}' AND '{ev['end']}')"
        )
    return " AND NOT (m.match_tag IS NOT NULL AND (" + " OR ".join(parts) + "))"


def main():
    db = dbmod.connect()
    cur = db.cursor()

    print("Ensuring schema…")
    cur.execute(SCHEMA)
    db.commit()

    # Group player matches by region (using server.region), excluding LAN events.
    # Join via host_root (port-stripped) since matches and servers can differ on port.
    lan_clause = lan_exclusion_sql()
    sql = f"""
        WITH server_region_by_root AS (
            -- Pick a region per host_root (prefer rows with country populated).
            SELECT DISTINCT ON (split_part(hostname, ':', 1))
                   split_part(hostname, ':', 1) AS host_root,
                   region
            FROM servers
            WHERE region IS NOT NULL AND region != ''
            ORDER BY split_part(hostname, ':', 1), country NULLS LAST
        ),
        player_region_counts AS (
            SELECT p.canonical_id,
                   srbr.region,
                   COUNT(*) AS n
            FROM players p
            JOIN matches m ON m.match_id = p.match_id
            JOIN server_region_by_root srbr
              ON srbr.host_root = split_part(m.server_hostname, ':', 1)
            WHERE p.canonical_id IS NOT NULL
              {lan_clause}
            GROUP BY p.canonical_id, srbr.region
        )
        SELECT canonical_id, region, n
        FROM player_region_counts
        ORDER BY canonical_id, n DESC
    """
    print("Computing region counts (may take 30-60s on large table)…")
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"  {len(rows)} (player, region) pairs")

    # Aggregate per-player. Collapse Asia + Africa into a combined 'AS-AF' bucket —
    # individual counts are tiny (8 AS, 7 AF players) so a merged region is more
    # useful than two underpopulated ones. Servers table keeps the precise code.
    def merge_region(r: str) -> str:
        return "AS-AF" if r in ("AS", "AF") else r

    by_player: dict[str, dict[str, int]] = {}
    for r in rows:
        region = merge_region(r["region"])
        by_player.setdefault(r["canonical_id"], {})[region] = \
            by_player.get(r["canonical_id"], {}).get(region, 0) + r["n"]

    print(f"  {len(by_player)} players with at least one regional match")

    now = datetime.now(timezone.utc).isoformat()
    n_updated = 0
    region_counts: dict[str, int] = {}
    for cid, dist in by_player.items():
        total = sum(dist.values())
        primary = max(dist, key=dist.get)
        confidence = dist[primary] / total
        region_counts[primary] = region_counts.get(primary, 0) + 1
        cur.execute("""
            UPDATE players_canonical
            SET region = %s, region_confidence = %s, region_distribution = %s, region_assigned_at = %s
            WHERE canonical_id = %s
        """, (primary, round(confidence, 3), json.dumps(dist), now, cid))
        n_updated += 1
        if n_updated % 500 == 0:
            db.commit()
            print(f"  {n_updated}/{len(by_player)} players assigned")

    db.commit()
    print(f"\nDone: {n_updated} players assigned regions.")

    print("\nDistribution:")
    for region, n in sorted(region_counts.items(), key=lambda x: -x[1]):
        print(f"  {region:6} {n:5} players")

    # Show a few "mixed region" players (low confidence — interesting cases)
    cur.execute("""
        SELECT canonical_id, display_name, region, region_confidence, region_distribution
        FROM players_canonical
        WHERE region_confidence IS NOT NULL AND region_confidence < 0.7
        ORDER BY region_confidence ASC LIMIT 10
    """)
    print("\nTop 10 multi-region players (lowest confidence):")
    for r in cur.fetchall():
        dist_str = ", ".join(f"{k}:{v}" for k, v in sorted(r["region_distribution"].items(), key=lambda x: -x[1])[:4])
        print(f"  {r['display_name']:22s} primary={r['region']} conf={r['region_confidence']:.2f}  ({dist_str})")


if __name__ == "__main__":
    main()

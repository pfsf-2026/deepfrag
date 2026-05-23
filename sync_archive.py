#!/usr/bin/env python3
"""Import xantom's KTX stats archives (.tar.gz) into the local SQLite DB.

These archives cover the entire QW community going back to ~2021, predating
our hub sync by 2.7 years. After import, run canonicalize.py to merge new
player name variants into the identity layer.

Usage:
  python sync_archive.py                          # import all archives in data/xantom-imports/
  python sync_archive.py --archive 1on1           # just one mode
  python sync_archive.py --limit 500              # cap per archive (testing)
  python sync_archive.py --dry-run                # report what would be imported

Dedup strategy:
  - Each xantom match gets a SYNTHETIC negative match_id (hash of content).
  - Hub matches have POSITIVE Supabase IDs, so the two ID spaces never collide.
  - To avoid double-counting matches that exist in BOTH hub and xantom, we
    build a dedup-key set from existing matches first (date_minute + map + sorted
    canonical_ids) and skip xantom matches whose key already exists.
"""

import argparse
import hashlib
import json
import re
import sqlite3
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from name_canon import Canonicalizer, normalize

ARCHIVE_DIR = Path(__file__).parent / "data" / "xantom-imports"
DEFAULT_DB = Path(__file__).parent / "data" / "qw-stats.db"


def synthetic_match_id(ktx):
    """Stable hash of match content → unique negative int.
    Negative so it can't collide with positive Supabase hub IDs."""
    parts = [
        str(ktx.get("date", "")),
        str(ktx.get("map", "")),
        str(ktx.get("hostname", "")),
        ":".join(sorted(str(p.get("name", "")) for p in ktx.get("players", []))),
    ]
    key = "|".join(parts).encode("utf-8", errors="replace")
    # Take the first 60 bits of the hash → fits in a signed int64
    return -int(hashlib.sha256(key).hexdigest()[:15], 16)


def parse_ktx_date(date_str):
    """xantom: '2026-04-01 00:19:31 +0000' → ISO 8601 string."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S %z").isoformat()
    except (ValueError, TypeError):
        return date_str


def parse_server_port(hostname):
    """'host:port [name]' → ('host', port_or_None)."""
    if not hostname:
        return hostname, None
    m = re.match(r"^(.*?):(\d+)(?:\s|$)", hostname)
    if m:
        return m.group(1), int(m.group(2))
    return hostname, None


def dig(root, *path, default=None):
    """Safe nested-dict access."""
    for key in path:
        if not isinstance(root, dict) or key not in root:
            return default
        root = root[key]
    return root if root is not None else default


def build_dedup_keys(db, canon: Canonicalizer):
    """Pre-build set of (date_minute, map, sorted_canonical_id_tuple) for every existing match.

    Used to skip xantom matches that are already in our hub data.
    """
    keys = set()
    rows = db.execute("""
        SELECT m.match_id, m.match_date, m.match_map,
               GROUP_CONCAT(DISTINCT lower(COALESCE(p.canonical_id, p.player_name))) AS player_cids
        FROM matches m
        LEFT JOIN players p ON p.match_id = m.match_id
        GROUP BY m.match_id
    """).fetchall()
    for r in rows:
        date = (r[1] or "")[:16]   # truncate to minute precision (YYYY-MM-DDTHH:MM)
        map_ = r[2] or ""
        cids = tuple(sorted((r[3] or "").split(","))) if r[3] else ()
        keys.add((date, map_, cids))
    return keys


def make_dedup_key(ktx, mode, canon: Canonicalizer):
    """Compute the same (date_minute, map, sorted_cids) key for a xantom match."""
    iso = parse_ktx_date(ktx.get("date"))
    date_min = (iso or "")[:16]
    map_ = ktx.get("map") or ""
    cids = []
    for p in ktx.get("players", []):
        raw = p.get("name", "")
        cid, _ = canon.resolve(raw, p.get("login"))
        cids.append(cid)
    return (date_min, map_, tuple(sorted(set(c.lower() for c in cids))))


def iter_archive(path):
    """Stream (filename, parsed_json) entries from a .tar.gz."""
    with tarfile.open(path, "r:gz") as tar:
        for member in tar:
            if not member.name.endswith(".json"):
                continue
            try:
                data = tar.extractfile(member).read()
                yield member.name, json.loads(data)
            except Exception as e:
                print(f"  skip {member.name}: {e}", flush=True)


def insert_archive_match(db, match_id, mode, ktx):
    """Insert match row + every player row from a xantom KTX record."""
    server_hostname, server_port = parse_server_port(ktx.get("hostname"))
    db.execute(
        """
        INSERT OR REPLACE INTO matches (
            match_id, match_date, match_mode, match_map, match_tag,
            server_hostname, server_port,
            match_dmm, match_tp, match_time_limit_mins, match_duration_secs,
            match_demo_sha256, demo_source_url, has_bots, ktx_fetched
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 0, 1)
        """,
        (
            match_id,
            parse_ktx_date(ktx.get("date")),
            mode,
            ktx.get("map"),
            ktx.get("matchtag"),
            server_hostname, server_port,
            ktx.get("dm"), ktx.get("tp"), ktx.get("tl"), ktx.get("duration"),
            ktx.get("demo"),  # demo filename, not SHA — we don't have it
        ),
    )
    # De-dupe players within a single match (KTX can list the same player twice on rejoin)
    seen = set()
    for player in ktx.get("players", []):
        name = player.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        row = _player_row(match_id, player)
        cols = ",".join(row.keys())
        placeholders = ",".join(f":{k}" for k in row.keys())
        db.execute(f"INSERT OR REPLACE INTO players ({cols}) VALUES ({placeholders})", row)


def _player_row(match_id, player):
    """Build the players-table row dict. Schema mirrors sync.py — keep in lockstep."""
    return {
        "match_id": match_id,
        "player_name": player.get("name", ""),
        "player_login": player.get("login", ""),
        "player_team": player.get("team", ""),
        "player_is_bot": 0,
        "player_top_color": dig(player, "top-color"),
        "player_bottom_color": dig(player, "bottom-color"),
        "player_ping": player.get("ping"),
        "player_frags": dig(player, "stats", "frags"),
        "player_deaths": dig(player, "stats", "deaths"),
        "player_teamkills": dig(player, "stats", "tk"),
        "player_spawnfrags": dig(player, "stats", "spawn-frags"),
        "player_suicides": dig(player, "stats", "suicides"),
        "player_damage_taken": dig(player, "dmg", "taken"),
        "player_damage_given": dig(player, "dmg", "given"),
        "player_damage_team": dig(player, "dmg", "team"),
        "player_damage_self": dig(player, "dmg", "self"),
        "player_damage_team_weapons": dig(player, "dmg", "team-weapons"),
        "player_damage_enemy_weapons": dig(player, "dmg", "enemy-weapons"),
        "player_damage_to_die": dig(player, "dmg", "taken-to-die"),
        "player_spree_frag": dig(player, "spree", "max"),
        "player_spree_quad": dig(player, "spree", "quad"),
        "player_speed_max": dig(player, "speed", "max"),
        "player_speed_avg": dig(player, "speed", "avg"),
        "player_sg_attacks": dig(player, "weapons", "sg", "acc", "attacks", default=0),
        "player_sg_hits": dig(player, "weapons", "sg", "acc", "hits", default=0),
        "player_sg_damage_enemy": dig(player, "weapons", "sg", "damage", "enemy", default=0),
        "player_sg_damage_team": dig(player, "weapons", "sg", "damage", "team", default=0),
        "player_ssg_attacks": dig(player, "weapons", "ssg", "acc", "attacks", default=0),
        "player_ssg_hits": dig(player, "weapons", "ssg", "acc", "hits", default=0),
        "player_ssg_damage_enemy": dig(player, "weapons", "ssg", "damage", "enemy", default=0),
        "player_ssg_damage_team": dig(player, "weapons", "ssg", "damage", "team", default=0),
        "player_gl_attacks": dig(player, "weapons", "gl", "acc", "attacks", default=0),
        "player_gl_directs": dig(player, "weapons", "gl", "acc", "hits", default=0),
        "player_gl_virtual": dig(player, "weapons", "gl", "acc", "virtual", default=0),
        "player_rl_attacks": dig(player, "weapons", "rl", "acc", "attacks", default=0),
        "player_rl_directs": dig(player, "weapons", "rl", "acc", "hits", default=0),
        "player_rl_virtual": dig(player, "weapons", "rl", "acc", "virtual", default=0),
        "player_rl_dropped": dig(player, "weapons", "rl", "pickups", "dropped", default=0),
        "player_rl_taken": dig(player, "weapons", "rl", "pickups", "taken", default=0),
        "player_rl_transfer": dig(player, "xferRL", default=0),
        "player_rl_damage_enemy": dig(player, "weapons", "rl", "damage", "enemy", default=0),
        "player_rl_damage_team": dig(player, "weapons", "rl", "damage", "team", default=0),
        "player_rl_kills_enemy": dig(player, "weapons", "rl", "kills", "enemy", default=0),
        "player_rl_kills_team": dig(player, "weapons", "rl", "kills", "team", default=0),
        "player_lg_attacks": dig(player, "weapons", "lg", "acc", "attacks", default=0),
        "player_lg_hits": dig(player, "weapons", "lg", "acc", "hits", default=0),
        "player_lg_dropped": dig(player, "weapons", "lg", "pickups", "dropped", default=0),
        "player_lg_taken": dig(player, "weapons", "lg", "pickups", "taken", default=0),
        "player_lg_transfer": dig(player, "xferLG", default=0),
        "player_lg_damage_enemy": dig(player, "weapons", "lg", "damage", "enemy", default=0),
        "player_lg_damage_team": dig(player, "weapons", "lg", "damage", "team", default=0),
        "player_lg_kills_enemy": dig(player, "weapons", "lg", "kills", "enemy", default=0),
        "player_lg_kills_team": dig(player, "weapons", "lg", "kills", "team", default=0),
        "player_health15_taken": dig(player, "items", "health_15", "took", default=0),
        "player_health25_taken": dig(player, "items", "health_25", "took", default=0),
        "player_health100_taken": dig(player, "items", "health_100", "took", default=0),
        "player_ga_taken": dig(player, "items", "ga", "took", default=0),
        "player_ya_taken": dig(player, "items", "ya", "took", default=0),
        "player_ra_taken": dig(player, "items", "ra", "took", default=0),
        "player_quad_taken": dig(player, "items", "q", "took", default=0),
        "player_quad_time": dig(player, "items", "q", "time", default=0),
        "player_pent_taken": dig(player, "items", "p", "took", default=0),
        "player_ring_taken": dig(player, "items", "r", "took", default=0),
        "player_ring_time": dig(player, "items", "r", "time", default=0),
    }


def import_archive(db, archive_path: Path, mode: str, dedup_keys: set, canon: Canonicalizer,
                   limit=None, dry_run=False):
    print(f"\n=== Importing {archive_path.name} ({mode}) ===", flush=True)
    inserted = skipped_dup = failed = scanned = 0
    start = datetime.now()
    for filename, ktx in iter_archive(archive_path):
        scanned += 1
        if limit is not None and inserted >= limit:
            break

        # Dedup: does this match (date_min, map, players) already exist?
        key = make_dedup_key(ktx, mode, canon)
        if key in dedup_keys:
            skipped_dup += 1
        else:
            if not dry_run:
                try:
                    insert_archive_match(db, synthetic_match_id(ktx), mode, ktx)
                    inserted += 1
                except sqlite3.Error as e:
                    failed += 1
                    if failed <= 5:
                        print(f"  fail {filename}: {e}", flush=True)
            else:
                inserted += 1   # in dry-run, count as if it would have been inserted
            dedup_keys.add(key)

        if scanned % 5000 == 0:
            if not dry_run:
                db.commit()
            elapsed = (datetime.now() - start).total_seconds()
            rate = scanned / elapsed if elapsed else 0
            print(f"  scanned {scanned:,}: {inserted:,} new, {skipped_dup:,} dup, "
                  f"{failed:,} failed, {rate:.0f}/s", flush=True)

    if not dry_run:
        db.commit()
    elapsed = (datetime.now() - start).total_seconds()
    print(f"  DONE {mode}: {inserted:,} new, {skipped_dup:,} dup, {failed:,} failed "
          f"in {elapsed:.0f}s")
    return inserted, skipped_dup, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--archive-dir", default=str(ARCHIVE_DIR))
    parser.add_argument("--archive", choices=["1on1", "2on2", "4on4"],
                        help="just import one mode (default: all)")
    parser.add_argument("--limit", type=int, help="cap new inserts per archive (testing)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    print("Loading canonicalizer (aliases.yaml)…")
    canon = Canonicalizer.load()

    print("Building dedup-key set from existing matches…")
    dedup_keys = build_dedup_keys(db, canon)
    print(f"  {len(dedup_keys):,} existing match keys indexed for dedup")

    modes = [args.archive] if args.archive else ["1on1", "2on2", "4on4"]
    archive_dir = Path(args.archive_dir)
    totals = {"inserted": 0, "skipped_dup": 0, "failed": 0}
    for mode in modes:
        # Match archive file by mode prefix
        candidates = sorted(archive_dir.glob(f"ktxstats_{mode}_*.tar.gz"))
        if not candidates:
            print(f"WARNING: no archive for {mode} in {archive_dir}")
            continue
        for arch in candidates:
            ins, dup, fail = import_archive(
                db, arch, mode, dedup_keys, canon,
                limit=args.limit, dry_run=args.dry_run,
            )
            totals["inserted"] += ins
            totals["skipped_dup"] += dup
            totals["failed"] += fail

    print(f"\n{'─' * 60}")
    print(f"All archives: {totals['inserted']:,} inserted, "
          f"{totals['skipped_dup']:,} skipped (dup), "
          f"{totals['failed']:,} failed")
    print("\nNEXT: run `python canonicalize.py` to canonicalize new player names")


if __name__ == "__main__":
    main()

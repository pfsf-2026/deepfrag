#!/usr/bin/env python3
"""Sync QuakeWorld match history for a single player from the hub into SQLite.

Pipeline per run:
  1. Query hub Supabase for any match (any mode) where the player appears, since the
     last seen match_date in the local DB.
  2. For each new match, fetch the KTX stats JSON from d.quake.world and upsert the
     match + every player's full per-weapon stats into the local DB.
  3. Scrape stats.quakeworld.nu for the player's lifetime totals.

The hub-data fetch pattern is lifted from phylter-qw/qw-4on4-ratings (sync.py),
but filters on `players_fts` instead of `mode=4on4`.
"""

import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
import psycopg2.extras
from bs4 import BeautifulSoup

import db as dbmod

# Single Session reuses TCP+TLS connections across requests (huge speedup vs
# requests.get(), which opens a new connection each time).
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "DeepFrag/0.1 (+github.com/peteryeargin)"})

# Hub Supabase endpoint. Anon keys are public (baked into the website JS).
HUB_URL = "https://ncsphkjfominimxztjip.supabase.co/rest/v1/v1_games"
HUB_HEADERS = {
    "apikey": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5jc3Boa2pmb21pbmlteHp0amlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTY5Mzg1NjMsImV4cCI6MjAxMjUxNDU2M30.NN6hjlEW-qB4Og9hWAVlgvUdwrbBO13s8OkAJuBGVbo",
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5jc3Boa2pmb21pbmlteHp0amlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTY5Mzg1NjMsImV4cCI6MjAxMjUxNDU2M30.NN6hjlEW-qB4Og9hWAVlgvUdwrbBO13s8OkAJuBGVbo",
}
KTX_URL = "https://d.quake.world/{prefix}/{sha}.mvd.ktxstats.json"
QWSTATS_URL = "http://stats.quakeworld.nu/index.php?a=qwplayer&currentPlayer={name}&page=1&order=10&search=Search"

PAGE_SIZE = 1000


def dig(root, *path, default=None):
    """Pull a nested key from a dict-of-dicts, returning default if anything is missing."""
    for key in path:
        if not isinstance(root, dict) or key not in root:
            return default
        root = root[key]
    return root if root is not None else default


def escape_qw(s):
    """Escape QW color codes / unprintable characters in a player or server name.

    Lifted from phylter-qw/qw-4on4-ratings sync.py:escape.
    """
    if s is None:
        return None
    if isinstance(s, (bytes, bytearray)):
        ords = list(s)
    else:
        ords = [ord(c) for c in str(s)]

    def to_chr(o):
        if o == 0x10:
            return "\\1["
        if o == 0x11:
            return "\\1]"
        if 0x12 <= o <= 0x1B:
            return f"\\2{chr(o + 30)}"
        if 0x20 <= o <= 0x7E:
            return "\\\\" if o == 0x5C else chr(o)
        if o == 0x90:
            return "\\3["
        if o == 0x91:
            return "\\3]"
        if 0x92 <= o <= 0x9B:
            return f"\\4{chr(o - 98)}"
        if 0xA0 <= o <= 0xFE:
            return "\\5\\\\" if o == 0xDC else f"\\5{chr(o - 128)}"
        return f"\\x{o:02x}"

    return "".join(to_chr(o) for o in ords)


def open_db(path=None):
    """Connect to whichever DB db.py points at (default = Cloud SQL Postgres).
    `path` ignored — schema lives in Postgres now, created by migrate_sqlite_to_pg.py."""
    return dbmod.connect()


def fetch_hub_matches(player_name, since):
    """Yield hub match metadata records for matches involving `player_name` after `since`.

    Pages through PostgREST 1000 at a time. `since` is an ISO-8601 timestamp string.
    """
    offset = 0
    while True:
        params = {
            "select": "id,timestamp,mode,map,matchtag,server_hostname,demo_sha256,demo_source_url,players",
            "players_fts": f"fts.{player_name.lower()}",
            "timestamp": f"gt.{since}",
            "order": "timestamp.asc",
            "offset": offset,
            "limit": PAGE_SIZE,
        }
        r = SESSION.get(HUB_URL, params=params, headers=HUB_HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        # Confirm player actually appears (fts may match substrings / nicknames).
        for match in batch:
            if any(p.get("name", "").lower() == player_name.lower() for p in match.get("players", [])):
                yield match
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE


def parse_server_port(hostname):
    """'The-Den:28502' -> ('The-Den', 28502); 'ny.quake.world:28501 NAQW' -> ('ny.quake.world', 28501).

    Returns (cleaned_hostname, port_or_None).
    """
    if not hostname:
        return hostname, None
    m = re.match(r"^(.*?):(\d+)(?:\s|$)", hostname)
    if m:
        return m.group(1), int(m.group(2))
    return hostname, None


def insert_match(db, match, ktx):
    """Insert match + every player into the DB. Idempotent via ON CONFLICT upsert."""
    server_hostname, server_port = parse_server_port(match.get("server_hostname"))
    has_bots = 1 if any(p.get("is_bot") for p in match.get("players", [])) else 0
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO matches (
            match_id, match_date, match_mode, match_map, match_tag,
            server_hostname, server_port,
            match_dmm, match_tp, match_time_limit_mins, match_duration_secs,
            match_demo_sha256, demo_source_url, has_bots, hub_game_id, ktx_fetched
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
        ON CONFLICT (match_id) DO UPDATE SET
          match_date=EXCLUDED.match_date, match_mode=EXCLUDED.match_mode,
          match_map=EXCLUDED.match_map, match_tag=EXCLUDED.match_tag,
          server_hostname=EXCLUDED.server_hostname, server_port=EXCLUDED.server_port,
          match_dmm=EXCLUDED.match_dmm, match_tp=EXCLUDED.match_tp,
          match_time_limit_mins=EXCLUDED.match_time_limit_mins,
          match_duration_secs=EXCLUDED.match_duration_secs,
          match_demo_sha256=EXCLUDED.match_demo_sha256,
          demo_source_url=EXCLUDED.demo_source_url, has_bots=EXCLUDED.has_bots,
          hub_game_id=EXCLUDED.hub_game_id,
          ktx_fetched=1
        """,
        (
            match["id"],
            match["timestamp"],
            match["mode"],
            match.get("map"),
            ktx.get("matchtag"),
            server_hostname,
            server_port,
            ktx.get("dm"),
            ktx.get("tp"),
            ktx.get("tl"),
            ktx.get("duration"),
            match["demo_sha256"],
            match.get("demo_source_url"),
            has_bots,
            match["id"],  # hub_game_id: live-synced rows have hub id == match_id
        ),
    )

    # Build a quick lookup of is_bot per name from the hub metadata (KTX doesn't include is_bot).
    bot_by_name = {p.get("name"): bool(p.get("is_bot")) for p in match.get("players", [])}

    seen_names = set()
    for player in ktx.get("players", []):
        raw_name = player.get("name")
        if raw_name in seen_names:
            continue  # KTX can list the same player twice if they disconnect + rejoin
        seen_names.add(raw_name)
        row = {
            "match_id": match["id"],
            "player_name": escape_qw(raw_name),
            "player_login": player.get("login"),
            "player_team": escape_qw(player.get("team")),
            "player_is_bot": 1 if bot_by_name.get(raw_name) else 0,
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
        cols = list(row.keys())
        col_sql = ",".join(cols)
        placeholders = ",".join(f"%({k})s" for k in cols)
        # players PK is (match_id, player_name) — upsert everything else.
        updates = ",".join(f"{c}=EXCLUDED.{c}" for c in cols
                           if c not in ("match_id", "player_name"))
        cur.execute(
            f"INSERT INTO players ({col_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT (match_id, player_name) DO UPDATE SET {updates}",
            row,
        )
    cur.close()


def fetch_ktx(sha):
    url = KTX_URL.format(prefix=sha[:3], sha=sha)
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all_hub_matches(since, modes=("1on1", "2on2", "4on4")):
    """Yield every hub match in supported modes since `since`. No player filter.
    Powers the periodic full-pull sync (every 2h) used by /api/admin/sync."""
    offset = 0
    mode_filter = "in.(" + ",".join(modes) + ")"
    while True:
        params = {
            "select": "id,timestamp,mode,map,matchtag,server_hostname,demo_sha256,demo_source_url,players",
            "mode": mode_filter,
            "timestamp": f"gt.{since}",
            "order": "timestamp.asc",
            "offset": offset,
            "limit": PAGE_SIZE,
        }
        r = SESSION.get(HUB_URL, params=params, headers=HUB_HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for match in batch:
            yield match
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE


def sync_all_recent(db, since=None, limit=None, workers=8):
    """Pull every new hub match (any player, 1on1/2on2/4on4) into the DB.

    `since` defaults to max(match_date) in matches table — i.e. only fetch
    matches we haven't seen yet. Designed to run every 2h via Cloud Scheduler.

    Returns dict with run summary: { matches_fetched, matches_failed,
    elapsed_secs, since }.
    """
    cur = db.cursor()
    if since is None:
        cur.execute("SELECT max(match_date) AS last FROM matches")
        row = cur.fetchone()
        since = (row["last"] if row else None) or "1970-01-01T00:00:00+00:00"
    print(f"sync_all_recent: pulling new matches since {since} (workers={workers})")

    candidates = []
    for match in fetch_all_hub_matches(since):
        if limit is not None and len(candidates) >= limit:
            break
        cur.execute("SELECT ktx_fetched FROM matches WHERE match_id=%s", (match["id"],))
        existing = cur.fetchone()
        if existing and existing["ktx_fetched"]:
            continue
        candidates.append(match)
    cur.close()
    print(f"  {len(candidates)} new matches to fetch KTX for")

    processed = 0
    failed = 0
    start = datetime.now()
    if candidates:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_match = {pool.submit(fetch_ktx, m["demo_sha256"]): m for m in candidates}
            for future in as_completed(future_to_match):
                match = future_to_match[future]
                try:
                    ktx = future.result()
                except requests.RequestException as e:
                    failed += 1
                    print(f"  [{match['id']}] KTX fetch failed: {e}")
                    continue
                insert_match(db, match, ktx)
                processed += 1
                if processed % 100 == 0:
                    db.commit()
        db.commit()
    elapsed = (datetime.now() - start).total_seconds()
    print(f"sync_all_recent done: {processed} fetched, {failed} failed in {elapsed:.0f}s")
    return {
        "since": since,
        "matches_fetched": processed,
        "matches_failed": failed,
        "elapsed_secs": round(elapsed, 1),
    }


def sync_matches(db, player_name, since=None, limit=None, workers=8):
    cur = db.cursor()
    if since is None:
        cur.execute("SELECT max(match_date) AS last FROM matches")
        row = cur.fetchone()
        since = (row["last"] if row else None) or "1970-01-01T00:00:00+00:00"
    print(f"Syncing matches for '{player_name}' since {since} (workers={workers})")

    # Collect candidate matches first (cheap — paginated metadata), then fetch KTX in parallel.
    candidates = []
    for match in fetch_hub_matches(player_name, since):
        if limit is not None and len(candidates) >= limit:
            break
        cur.execute("SELECT ktx_fetched FROM matches WHERE match_id=%s", (match["id"],))
        existing = cur.fetchone()
        if existing and existing["ktx_fetched"]:
            continue
        candidates.append(match)
    cur.close()
    print(f"  {len(candidates)} new matches to fetch")

    processed = 0
    failed = 0
    start = datetime.now()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_match = {pool.submit(fetch_ktx, m["demo_sha256"]): m for m in candidates}
        for future in as_completed(future_to_match):
            match = future_to_match[future]
            try:
                ktx = future.result()
            except requests.RequestException as e:
                failed += 1
                print(f"  [{match['id']}] KTX fetch failed: {e}")
                continue
            insert_match(db, match, ktx)
            processed += 1
            if processed % 100 == 0:
                db.commit()
                elapsed = (datetime.now() - start).total_seconds()
                rate = processed / elapsed if elapsed else 0
                eta = (len(candidates) - processed) / rate if rate else 0
                print(f"  {processed}/{len(candidates)} done, {failed} failed, {rate:.1f}/s, eta {eta/60:.1f} min")
    db.commit()
    elapsed = (datetime.now() - start).total_seconds()
    print(f"Done: {processed} fetched, {failed} failed in {elapsed:.0f}s ({processed/elapsed if elapsed else 0:.1f}/s)")


def sync_career_totals(db, player_name):
    url = QWSTATS_URL.format(name=player_name)
    print(f"Scraping career totals for '{player_name}' from stats.quakeworld.nu")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  Failed: {e}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    # The first table on the page lists: Total Matches / 4on4 / 2on2 / 1on1 / Time / Frags / FPM.
    table = soup.find("table", class_="wide")
    if not table:
        print("  Could not find totals table")
        return
    rows = table.find_all("tr")
    if len(rows) < 2:
        print("  Unexpected table shape")
        return
    headers = [td.get_text(strip=True) for td in rows[0].find_all("td")]
    values = [td.get_text(strip=True) for td in rows[1].find_all("td")]
    data = dict(zip(headers, values))

    def to_int(s):
        try:
            return int(s.replace(",", ""))
        except (ValueError, AttributeError):
            return None

    def to_float(s):
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    # "Total Time:" is rendered as a single integer in minutes on stats.quakeworld.nu.
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO career_totals (
            player_name, total_matches, total_4on4, total_2on2, total_1on1,
            total_time_mins, total_frags, fpm, scraped_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_name) DO UPDATE SET
          total_matches=EXCLUDED.total_matches, total_4on4=EXCLUDED.total_4on4,
          total_2on2=EXCLUDED.total_2on2, total_1on1=EXCLUDED.total_1on1,
          total_time_mins=EXCLUDED.total_time_mins, total_frags=EXCLUDED.total_frags,
          fpm=EXCLUDED.fpm, scraped_at=EXCLUDED.scraped_at
        """,
        (
            player_name,
            to_int(data.get("Total Matches")),
            to_int(data.get("Total 4on4")),
            to_int(data.get("Total 2on2")),
            to_int(data.get("Total 1on1")),
            to_int(data.get("Total Time:")),
            to_int(data.get("Total Frags")),
            to_float(data.get("FPM")),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    cur.close()
    db.commit()
    print(f"  {data}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("player", help="player name to sync (e.g. cronus)")
    parser.add_argument(
        "--db",
        default=str(Path(__file__).parent / "data" / "qw-stats.db"),
        help="path to SQLite database",
    )
    parser.add_argument("--since", help="ISO-8601 timestamp; defaults to max(match_date) in DB")
    parser.add_argument("--limit", type=int, help="cap number of new matches per run")
    parser.add_argument("--no-matches", action="store_true", help="skip match sync")
    parser.add_argument("--no-career", action="store_true", help="skip career totals scrape")
    parser.add_argument("--workers", type=int, default=8, help="parallel KTX fetches (default 8)")
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = open_db(args.db)
    try:
        if not args.no_matches:
            sync_matches(db, args.player, since=args.since, limit=args.limit, workers=args.workers)
        if not args.no_career:
            sync_career_totals(db, args.player)
    finally:
        db.close()


if __name__ == "__main__":
    main()

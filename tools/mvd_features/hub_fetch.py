"""Fetch games from the QuakeWorld hub (Supabase v1_games) into a manifest JSON.

Standalone CLI — does not touch the local DB. Pages through PostgREST's
`v1_games` table (same endpoint/headers as sync.py's fetch_all_hub_matches),
filters by mode/map/since, optionally by server-hostname substring and/or
player-name substring, and writes a JSON list of games with exactly:

    {"id": <int>, "timestamp": "<iso>", "map": <str>, "mode": <str>,
     "server_hostname": <str>, "players": [ ... ], "demo_sha256": <hex str>}

Only games that have a demo_sha256 are kept (no demo -> nothing to analyze).

Usage:
  python tools/mvd_features/hub_fetch.py --map dm3 --mode 4on4 \
      --since 2025-09-21 --out manifest_eu_dm3.json \
      --exclude-host la.quake.world --exclude-host NAQW \
      --include-host quake.se
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

HUB_URL = "https://ncsphkjfominimxztjip.supabase.co/rest/v1/v1_games"
HUB_HEADERS = {
    "apikey": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5jc3Boa2pmb21pbmlteHp0amlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTY5Mzg1NjMsImV4cCI6MjAxMjUxNDU2M30.NN6hjlEW-qB4Og9hWAVlgvUdwrbBO13s8OkAJuBGVbo",
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5jc3Boa2pmb21pbmlteHp0amlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE2OTY5Mzg1NjMsImV4cCI6MjAxMjUxNDU2M30.NN6hjlEW-qB4Og9hWAVlgvUdwrbBO13s8OkAJuBGVbo",
}
SELECT = "id,timestamp,mode,map,server_hostname,demo_sha256,players"
PAGE_SIZE = 1000
SLEEP_SECS = 0.25

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "DeepFrag/0.1 (+github.com/peteryeargin)"})


def fetch_games(mode, map_name, since):
    """Yield raw hub game records matching mode/map/since, oldest first.

    Pages through PostgREST PAGE_SIZE at a time via offset, ordered by id so
    paging is stable even as new games land during the run.
    """
    offset = 0
    while True:
        params = {
            "select": SELECT,
            "order": "id.asc",
            "offset": offset,
            "limit": PAGE_SIZE,
        }
        if mode:
            params["mode"] = f"eq.{mode}"
        if map_name:
            params["map"] = f"eq.{map_name}"
        if since:
            params["timestamp"] = f"gte.{since}"
        r = SESSION.get(HUB_URL, params=params, headers=HUB_HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for game in batch:
            yield game
        print(f"  ...page at offset {offset}: {len(batch)} games", file=sys.stderr)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(SLEEP_SECS)


def keep_game(game, exclude_hosts, include_hosts, players):
    if not game.get("demo_sha256"):
        return False
    host = (game.get("server_hostname") or "").lower()
    if exclude_hosts and any(h.lower() in host for h in exclude_hosts):
        return False
    if include_hosts and not any(h.lower() in host for h in include_hosts):
        return False
    if players:
        names = [p.get("name", "") or "" for p in game.get("players", [])]
        names_lower = [n.lower() for n in names]
        if not any(any(sub.lower() in n for n in names_lower) for sub in players):
            return False
    return True


def to_manifest_entry(game):
    return {
        "id": game["id"],
        "timestamp": game["timestamp"],
        "map": game.get("map"),
        "mode": game.get("mode"),
        "server_hostname": game.get("server_hostname"),
        "players": game.get("players") or [],
        "demo_sha256": game["demo_sha256"],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", help="exact map name (e.g. dm3)")
    ap.add_argument("--mode", help="exact mode (e.g. 4on4)")
    ap.add_argument("--since", required=True, help="ISO date/timestamp; keep games with timestamp >= this")
    ap.add_argument("--out", required=True, help="output manifest JSON path")
    ap.add_argument("--exclude-host", action="append", default=[],
                     help="drop games whose server_hostname contains this substring (repeatable)")
    ap.add_argument("--include-host", action="append", default=[],
                     help="keep only games whose server_hostname contains this substring (repeatable)")
    ap.add_argument("--player", action="append", default=[],
                     help="keep only games where some player name contains this substring, "
                          "case-insensitive (repeatable)")
    args = ap.parse_args()

    print(f"Fetching mode={args.mode} map={args.map} since={args.since} from hub...", file=sys.stderr)
    kept = []
    seen = 0
    for game in fetch_games(args.mode, args.map, args.since):
        seen += 1
        if keep_game(game, args.exclude_host, args.include_host, args.player):
            kept.append(to_manifest_entry(game))

    kept.sort(key=lambda g: g["id"])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(kept, f, indent=2)

    print(f"Scanned {seen} games, kept {len(kept)} (with demo, after host/player filters) -> {out_path}",
          file=sys.stderr)


if __name__ == "__main__":
    main()

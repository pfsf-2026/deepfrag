#!/usr/bin/env python3
"""Sync live server data from hubapi.quakeworld.nu into our `servers` table.

The hub aggregates real-time `status` queries from every QW server that registers
with it — so we get IP+port, current map/mode, current players, QTV streams,
geo (city, country, region, coords), MVDSV version, admin contact, etc.

Run on a cron (every 5-15 min) to keep server profiles fresh.

Schema additions (idempotent):
  live_address       — "ip:port" as the hub knows it
  mvdsv_version      — "MVDSV 1.20-dev"
  admin              — operator email (*admin)
  qtv_stream_url     — live QTV stream URL
  gamedir            — "ktx" / mod name
  current_map        — what's loaded right now
  current_mode       — 1on1 / 2on2 / 4on4
  current_players    — non-bot player count
  current_specs      — spectator count
  max_clients        — server slot count
  fraglimit, timelimit, teamplay, deathmatch  — server settings
  qtv_viewer_count   — QTV stream audience
  is_live            — TRUE if hub saw it during this sync
  last_seen_live     — ISO timestamp of last hub sighting
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import requests

import db as dbmod

HUB_URL = "https://hubapi.quakeworld.nu/v2/servers"

# Hub returns geo.region as natural-language strings; map to our compact codes.
HUB_REGION_MAP = {
    "North America": "NA",
    "Europe": "EU",
    "South America": "SA",
    "Oceania": "OC",
    "Asia": "AS",
    "Africa": "AF",
}


SCHEMA_MIGRATION = """
ALTER TABLE servers ADD COLUMN IF NOT EXISTS live_address       TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS mvdsv_version      TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS admin              TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS qtv_stream_url     TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS gamedir            TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS current_map        TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS current_mode       TEXT;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS current_players    INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS current_specs      INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS max_clients        INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS fraglimit          INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS timelimit          INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS teamplay           INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS deathmatch         INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS qtv_viewer_count   INTEGER;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_live            BOOLEAN DEFAULT FALSE;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS last_seen_live     TEXT;
CREATE INDEX IF NOT EXISTS idx_servers_is_live ON servers(is_live);
CREATE INDEX IF NOT EXISTS idx_servers_last_seen_live ON servers(last_seen_live);
"""


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def extract_row(s: dict, now: str) -> dict:
    """Pull every field we care about out of one hub server entry."""
    settings = s.get("settings", {}) or {}
    geo = s.get("geo", {}) or {}
    extra = s.get("extra_info", {}) or {}
    qtv = extra.get("qtv_stream", {}) or {}

    address = s.get("address", "") or ""
    ip = address.split(":")[0] if ":" in address else address or None

    coords = geo.get("coordinates") or [None, None]
    lat = coords[0] if len(coords) > 0 else None
    lon = coords[1] if len(coords) > 1 else None

    # Count actual players (non-bot, non-spec).
    clients = s.get("clients", []) or []
    players_active = sum(1 for c in clients if not c.get("is_bot"))

    return {
        "hostname":         (settings.get("hostname") or "").strip(),
        "ip":               ip,
        "country":          geo.get("cc"),
        "region":           HUB_REGION_MAP.get(geo.get("region"), geo.get("region")),
        "city":             geo.get("city"),
        "lat":              lat,
        "lon":              lon,
        "live_address":     address or None,
        "mvdsv_version":    s.get("version"),
        "admin":            settings.get("*admin"),
        "qtv_stream_url":   qtv.get("url"),
        "gamedir":          settings.get("*gamedir"),
        "current_map":      settings.get("map"),
        "current_mode":     settings.get("mode"),
        "current_players":  players_active,
        "current_specs":    to_int(qtv.get("spectator_names") and len(qtv["spectator_names"])),
        "max_clients":      to_int(settings.get("maxclients")),
        "fraglimit":        to_int(settings.get("fraglimit")),
        "timelimit":        to_int(settings.get("timelimit")),
        "teamplay":         to_int(settings.get("teamplay")),
        "deathmatch":       to_int(settings.get("deathmatch")),
        "qtv_viewer_count": to_int(qtv.get("viewer_count")),
        "last_seen_live":   now,
        "resolved_at":      now,
    }


def main():
    print("Fetching hub live-server list…")
    r = requests.get(HUB_URL, timeout=30, headers={"User-Agent": "DeepFrag/0.1"})
    r.raise_for_status()
    live = r.json()
    print(f"  {len(live)} live servers reported")

    db = dbmod.connect()
    cur = db.cursor()

    print("Ensuring schema…")
    cur.execute(SCHEMA_MIGRATION)
    db.commit()

    print("Resetting is_live flags…")
    cur.execute("UPDATE servers SET is_live = FALSE")

    inserts = updates = skipped = 0
    now = datetime.now(timezone.utc).isoformat()
    for s in live:
        row = extract_row(s, now)
        if not row["hostname"]:
            skipped += 1
            continue
        cur.execute("""
            INSERT INTO servers (
                hostname, ip, country, region, city, lat, lon, resolved_at,
                live_address, mvdsv_version, admin, qtv_stream_url, gamedir,
                current_map, current_mode, current_players, current_specs,
                max_clients, fraglimit, timelimit, teamplay, deathmatch,
                qtv_viewer_count, last_seen_live, is_live
            ) VALUES (
                %(hostname)s, %(ip)s, %(country)s, %(region)s, %(city)s, %(lat)s, %(lon)s, %(resolved_at)s,
                %(live_address)s, %(mvdsv_version)s, %(admin)s, %(qtv_stream_url)s, %(gamedir)s,
                %(current_map)s, %(current_mode)s, %(current_players)s, %(current_specs)s,
                %(max_clients)s, %(fraglimit)s, %(timelimit)s, %(teamplay)s, %(deathmatch)s,
                %(qtv_viewer_count)s, %(last_seen_live)s, TRUE
            )
            ON CONFLICT (hostname) DO UPDATE SET
              ip = COALESCE(EXCLUDED.ip, servers.ip),
              country = COALESCE(EXCLUDED.country, servers.country),
              region = COALESCE(EXCLUDED.region, servers.region),
              city = COALESCE(EXCLUDED.city, servers.city),
              lat = COALESCE(EXCLUDED.lat, servers.lat),
              lon = COALESCE(EXCLUDED.lon, servers.lon),
              live_address = EXCLUDED.live_address,
              mvdsv_version = EXCLUDED.mvdsv_version,
              admin = EXCLUDED.admin,
              qtv_stream_url = EXCLUDED.qtv_stream_url,
              gamedir = EXCLUDED.gamedir,
              current_map = EXCLUDED.current_map,
              current_mode = EXCLUDED.current_mode,
              current_players = EXCLUDED.current_players,
              current_specs = EXCLUDED.current_specs,
              max_clients = EXCLUDED.max_clients,
              fraglimit = EXCLUDED.fraglimit,
              timelimit = EXCLUDED.timelimit,
              teamplay = EXCLUDED.teamplay,
              deathmatch = EXCLUDED.deathmatch,
              qtv_viewer_count = EXCLUDED.qtv_viewer_count,
              last_seen_live = EXCLUDED.last_seen_live,
              is_live = TRUE,
              resolve_error = NULL
        """, row)
        if cur.statusmessage and cur.statusmessage.startswith("INSERT 0 1"):
            inserts += 1
        else:
            updates += 1

    db.commit()
    print(f"\n{inserts} inserted, {updates} updated, {skipped} skipped (empty hostname)")

    # Reports
    cur.execute("SELECT COUNT(*) AS n FROM servers WHERE is_live")
    print(f"Live servers right now: {cur.fetchone()['n']}")
    cur.execute("""
        SELECT region, COUNT(*) AS n FROM servers WHERE is_live AND region IS NOT NULL
        GROUP BY region ORDER BY n DESC
    """)
    print("Live by region:")
    for r in cur.fetchall():
        print(f"  {r['region'] or '?':6} {r['n']:4} servers")

    cur.execute("""
        SELECT hostname, city, country, current_map, current_mode, current_players, max_clients
        FROM servers WHERE is_live AND current_players >= 2
        ORDER BY current_players DESC LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        print(f"\nTop 10 active servers right now:")
        for r in rows:
            print(f"  {r['hostname']:35s}  {(r['city'] or '')[:18]:18s}{r['country'] or '--':3s}  {r['current_map'] or '?':12s} {r['current_mode'] or '?':5s}  {r['current_players']}/{r['max_clients']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Seed player_configs from the community config Google Sheet.

The sheet (https://docs.google.com/spreadsheets/d/1wwg-uEVPv0aj1p7Mom1AqacCE-Rtq0olvNA8wckee5U)
tracks ~104 players' hardware/config (sens cm/360, DPI, grip, hand, movement,
mouse, mousepad, FOV, resolution, refresh, weapon binds, nationality, and for a
few a precise lat/lon). We import it as the STARTING point; users then correct
their own via the profile edit button.

Matching: sheet nick -> canonical_id via players_canonical (case-insensitive
display_name or canonical_id). Unmatched rows are kept with canonical_id=NULL
and the raw nick so they can be linked later.

Idempotent: re-running refreshes 'sheet'-sourced rows but never clobbers rows a
user/admin has edited (source in 'user','admin').

Usage:
  python seed_player_configs.py            # pull live sheet
  CONFIG_CSV=/tmp/qw_configs.csv python seed_player_configs.py   # local CSV
"""
from __future__ import annotations
import csv
import io
import os
import sys
import urllib.request

import psycopg2

PG_URL = os.environ.get("DEEPFRAG_PG_URL", "postgresql:///deepfrag")
SHEET_ID = "1wwg-uEVPv0aj1p7Mom1AqacCE-Rtq0olvNA8wckee5U"
SHEET_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"

# Sheet column indices (header is on row 4 / index 3).
COLS = {
    "nick": 0, "nationality": 1, "geo": 2, "sens_cm360": 3, "dpi": 4,
    "grip": 5, "hand": 6, "movement": 7, "invert_y": 8, "invert_x": 9,
    "accel": 10, "mouse": 11, "wireless": 12, "shaft_lower_sens": 13,
    "mousepad": 15, "mousepad_size": 16, "mousepad_type": 17,
    "fov": 19, "viewheight": 20, "rollangle": 21, "fwd_side_ratio": 22,
    "resolution": 23, "conwidth_conheight": 24, "refresh_hz": 25,
    "monitor_inches": 26, "eye_distance_cm": 27, "monitor": 28,
    "bind_weapon_change": 30, "bind_jump": 31, "bind_movement": 32,
    "bind_rl": 34, "bind_lg": 35, "bind_gl": 36, "bind_sng": 37,
    "bind_ng": 38, "bind_ssg": 39, "bind_sg": 40, "bind_axe": 41,
}


def get(row, key):
    i = COLS[key]
    return row[i].strip() if i < len(row) and row[i].strip() else None


def parse_latlon(geo):
    if not geo or "," not in geo:
        return None, None
    try:
        a, b = geo.split(",", 1)
        return float(a.strip()), float(b.strip())
    except Exception:
        return None, None


def load_csv() -> list:
    path = os.environ.get("CONFIG_CSV")
    if path:
        return list(csv.reader(open(path)))
    with urllib.request.urlopen(SHEET_CSV, timeout=30) as r:
        return list(csv.reader(io.StringIO(r.read().decode("utf-8"))))


def main():
    rows = load_csv()
    data = rows[4:]  # skip the 4 header rows

    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()
    # Resolve canonical_id for a nick (case-insensitive display_name OR id).
    matched = unmatched = 0
    for row in data:
        nick = (row[0].strip() if row and row[0].strip() else None)
        if not nick:
            continue
        cur.execute("""
            SELECT canonical_id FROM players_canonical
            WHERE LOWER(display_name) = LOWER(%s) OR LOWER(canonical_id) = LOWER(%s)
            LIMIT 1
        """, (nick, nick))
        hit = cur.fetchone()
        cid = hit[0] if hit else None
        lat, lon = parse_latlon(get(row, "geo"))
        # Build the config bag from every non-empty sheet field (except the
        # geo/nick/nationality columns we store as first-class).
        cfg = {}
        for key in COLS:
            if key in ("nick", "nationality", "geo"):
                continue
            v = get(row, key)
            if v:
                cfg[key] = v
        if cid:
            matched += 1
        else:
            unmatched += 1
        # Upsert. Never clobber user/admin edits.
        cur.execute("""
            INSERT INTO player_configs
                (canonical_id, nick, nationality, lat, lon, config, source, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'sheet', 'seed_script', now())
            ON CONFLICT (canonical_id) WHERE canonical_id IS NOT NULL
            DO UPDATE SET
                nick = EXCLUDED.nick,
                nationality = EXCLUDED.nationality,
                lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                config = EXCLUDED.config,
                updated_at = now()
            WHERE player_configs.source = 'sheet'
        """, (cid, nick, get(row, "nationality"), lat, lon,
              __import__("json").dumps(cfg)))
    conn.commit()
    conn.close()
    print(f"Seeded configs: {matched} matched to players, {unmatched} unmatched (kept by nick).")


if __name__ == "__main__":
    main()

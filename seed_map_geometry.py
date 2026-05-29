#!/usr/bin/env python3
"""Seed / refresh map_annotations.geometry from the mvd_analyzer maps endpoint.

The annotator UI renders each map from cached loc/triangle geometry. Rather
than hit the external mvd_analyzer preview URL at runtime (it rate-limits and
is a deploy-preview branch that could vanish), we fetch each map's geometry
ONCE and cache it in map_annotations.geometry. Re-run this script to refresh
(e.g. when new maps are added or the upstream geometry improves).

Geometry shape (from {BASE}/maps/{map}.json):
  {map, version, bounds:{minX,maxX,minY,maxY}, locs:[{name,z,tris:[x,y,...]}]}

Spawns/teles are NOT touched here — those are user-authored via the annotator.
On first seed we DO import any spawns from the legacy _spawn_points.json so the
4 hand-annotated maps aren't lost.

Usage:
  python seed_map_geometry.py                 # fetch the default map list
  python seed_map_geometry.py dm2 dm3 aerowalk
  DEEPFRAG_PG_URL=... python seed_map_geometry.py --all
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

import psycopg2
import psycopg2.extras

PG_URL = os.environ.get("DEEPFRAG_PG_URL", "postgresql:///deepfrag")

# Geometry sources (see memory: reference_deepfrag_map_geometry_sources):
#   GEO_BASE  — mvd_analyzer maps endpoint, returns PRE-TRIANGULATED geometry
#               {bounds, locs:[{name,z,tris}]}. This is what the annotator
#               renders. ~33 maps with real locs; a few bbox-only. It's a
#               Netlify deploy-preview URL (rate-limits, may vanish) — which is
#               exactly why we cache its output into map_annotations.geometry.
#   LOC_BASE  — maps.quakeworld.nu/locs/, the authoritative .loc waypoint
#               library (438 maps), but POINTS ONLY, no triangle mesh. Fallback
#               for loc names/points or maps GEO_BASE lacks; not directly
#               renderable as regions. Wiring a .loc importer is a TODO.
GEO_BASE = os.environ.get(
    "MVD_MAPS_BASE", "https://add-steals--mvdanalyzer.netlify.app/maps"
)
LOC_BASE = os.environ.get("QW_LOCS_BASE", "https://maps.quakeworld.nu/locs")

# Maps confirmed to return real loc geometry (>1 loc) from the probe 2026-05-29.
# bbox-only maps (metron, tron, faust, halo, panzer, povdmm4, midair, travelert6)
# return a single bounding loc — still renderable, just no interior locs.
DEFAULT_MAPS = [
    # 1on1 core
    "aerowalk", "bravado", "ztndm3", "ztndm3q", "dm4", "dm2", "dm6", "skull",
    "pocket", "shifter", "catalyst", "toxicity", "katt", "sabbath", "monsoon",
    "ultrav", "ztndm1", "zite", "thor", "zerg", "nova",
    # 4on4 / 2on2 core
    "dm3", "e1m2", "schloss", "phantombase", "dm5", "dm1", "cmt3", "cmt4",
    "dm7", "e2m2", "end",
    # bbox-only but still useful
    "metron", "tron", "faust", "halo", "panzer", "povdmm4", "midair",
]

LEGACY_SPAWNS = os.path.join(
    os.path.dirname(__file__), "..", "..", "tmp", "4on4-sandbox", "_spawn_points.json"
)


def fetch_geometry(map_name: str, retries: int = 3) -> dict | None:
    url = f"{GEO_BASE}/{map_name}.json"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                if r.status == 200:
                    return json.loads(r.read())
        except Exception as e:
            if attempt == retries - 1:
                print(f"  {map_name}: FAILED ({e})")
                return None
        time.sleep(3)  # be gentle — upstream rate-limits
    return None


def load_legacy_spawns() -> dict:
    """Return {map: [spawn,...]} from the hand-annotated sandbox file, if present."""
    path = os.environ.get("LEGACY_SPAWNS_PATH", "/tmp/4on4-sandbox/_spawn_points.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    maps = DEFAULT_MAPS if (not args or "--all" in sys.argv) else args
    legacy = load_legacy_spawns()

    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()
    ok = skipped = 0
    for m in maps:
        geo = fetch_geometry(m)
        if geo is None:
            skipped += 1
            continue
        spawns = json.dumps(legacy.get(m, []))
        # Upsert: set geometry always; only seed spawns if the row is new/empty
        # (never clobber user-authored spawns on a geometry refresh).
        cur.execute(
            """
            INSERT INTO map_annotations (map, geometry, spawns, updated_by, updated_at)
            VALUES (%s, %s, %s::jsonb, 'seed_script', now())
            ON CONFLICT (map) DO UPDATE SET
                geometry = EXCLUDED.geometry,
                spawns = CASE
                    WHEN map_annotations.spawns = '[]'::jsonb
                    THEN EXCLUDED.spawns
                    ELSE map_annotations.spawns
                END,
                updated_at = now()
            """,
            (m, json.dumps(geo), spawns),
        )
        n_locs = len(geo.get("locs", []))
        n_spawns = len(legacy.get(m, []))
        print(f"  {m}: geometry({n_locs} locs)" + (f" + {n_spawns} legacy spawns" if n_spawns else ""))
        ok += 1
        time.sleep(3)  # rate-limit friendly

    conn.commit()
    conn.close()
    print(f"\nSeeded {ok} maps, skipped {skipped}.")


if __name__ == "__main__":
    main()

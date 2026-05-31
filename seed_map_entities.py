#!/usr/bin/env python3
"""Seed map_annotations.entities from the mvd_analyzer BSP map-entity corpus.

REPLACES our hand-annotated spawns/teles with authoritative BSP-derived data
and ADDS item locations (which we never had). Source: galfthan/mvd_analyzer
branch read-dmg, mvd-analytics/mapents/data.

Corpus entity schema (verified aerowalk.json):
  {type: item|spawn|teleportSrc|teleportDst, class, kind(items), name, loc,
   x, y, z, target(src), targetName(dst), bounds(src)}

Normalized into map_annotations.entities (JSONB):
  { source:"bsp-corpus",
    spawns:[{x,y,z,loc}],
    items: [{kind,x,y,z,loc}],   # ra/ya/ga, rl/lg/sg/ssg/gl/ng/sng, mh, h25,
                                 # quad/pent/ring/suit, cells/nails/rockets/shells
    teles: [{from:{x,y,z,loc}, to:{x,y,z,loc}|null, target}] }

KEEPS map_annotations.geometry (render mesh) untouched — corpus has no geometry.

Usage:
  CORPUS_DIR=work/mapcorpus python seed_map_entities.py   # local (fast)
  python seed_map_entities.py                             # fetch from GitHub
  python seed_map_entities.py dm2 aerowalk                # specific maps
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import psycopg2

PG_URL = os.environ.get("DEEPFRAG_PG_URL", "postgresql:///deepfrag")
BRANCH = os.environ.get("CORPUS_BRANCH", "read-dmg")
GH_API = f"https://api.github.com/repos/galfthan/mvd_analyzer/contents/mvd-analytics/mapents/data?ref={BRANCH}"
RAW = f"https://raw.githubusercontent.com/galfthan/mvd_analyzer/{BRANCH}/mvd-analytics/mapents/data/"
CORPUS_DIR = os.environ.get("CORPUS_DIR")


def normalize(doc: dict) -> dict:
    spawns, items, tele_src, tele_dst = [], [], [], []
    for e in doc.get("entities", []):
        t = e.get("type")
        x, y, z = e.get("x"), e.get("y"), e.get("z", 0)
        if t == "spawn":
            spawns.append({"x": x, "y": y, "z": z, "loc": e.get("loc")})
        elif t == "teleportSrc":
            tele_src.append({"x": x, "y": y, "z": z, "loc": e.get("loc"),
                             "target": e.get("target")})
        elif t == "teleportDst":
            tele_dst.append({"x": x, "y": y, "z": z, "loc": e.get("loc"),
                             "targetName": e.get("targetName")})
        elif t == "item" and e.get("kind"):
            items.append({"kind": e["kind"], "x": x, "y": y, "z": z, "loc": e.get("loc")})
    dst_by_name = {d.get("targetName"): d for d in tele_dst if d.get("targetName")}
    teles = []
    for s in tele_src:
        d = dst_by_name.get(s.get("target"))
        teles.append({
            "from": {"x": s["x"], "y": s["y"], "z": s["z"], "loc": s.get("loc")},
            "to": ({"x": d["x"], "y": d["y"], "z": d["z"], "loc": d.get("loc")} if d else None),
            "target": s.get("target"),
        })
    return {"source": "bsp-corpus", "spawns": spawns, "items": items, "teles": teles}


def list_maps():
    if CORPUS_DIR:
        return sorted(f[:-5] for f in os.listdir(CORPUS_DIR) if f.endswith(".json"))
    req = urllib.request.Request(GH_API, headers={"User-Agent": "deepfrag"})
    items = json.load(urllib.request.urlopen(req, timeout=30))
    return [i["name"][:-5] for i in items
            if i["name"].endswith(".json") and i["size"] > 5]


def load_doc(m):
    if CORPUS_DIR:
        return json.load(open(os.path.join(CORPUS_DIR, m + ".json")))
    url = RAW + urllib.parse.quote(m + ".json")
    return json.loads(urllib.request.urlopen(url, timeout=30).read())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    maps = args or list_maps()
    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()
    cur.execute("ALTER TABLE map_annotations ADD COLUMN IF NOT EXISTS entities JSONB")
    conn.commit()
    ok = skip = 0
    for m in maps:
        try:
            ent = normalize(load_doc(m))
            if not ent["spawns"] and not ent["items"]:
                skip += 1
                continue
            cur.execute("""
                INSERT INTO map_annotations (map, entities, updated_by, updated_at)
                VALUES (%s, %s::jsonb, 'entity_seed', now())
                ON CONFLICT (map) DO UPDATE SET
                    entities = EXCLUDED.entities, updated_at = now()
            """, (m, json.dumps(ent)))
            ok += 1
            if ok % 25 == 0:
                conn.commit()
                print(f"  {ok}...", flush=True)
        except Exception as e:
            print(f"  {m}: FAIL {e}", flush=True)
            skip += 1
        if not CORPUS_DIR:
            time.sleep(0.04)
    conn.commit()
    conn.close()
    print(f"Seeded entities for {ok} maps, skipped {skip}.")


if __name__ == "__main__":
    main()

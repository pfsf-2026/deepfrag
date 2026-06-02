"""Extract first-spawn pathing runs into the spawn_runs training table.

For each of the 9 main 1on1 maps, take the top-5 players by per-map OpenSkill
conservative rating. For each player, pull their recent 1on1 games on that map
(cheap windowed 13ms buckets), determine:

  own_spawn / enemy_spawn  -- first-alive position snapped to nearest BSP spawn
  path                     -- [x,y,z] per 13ms bucket over the FIRST life
  items_outcome            -- full_start(RA+MH) / ra / mh_only / ya_ga / nothing
  opening_result           -- won / traded / lost / survived  (from the frag log)

Coverage-driven: stop pulling a player's games once every own_spawn they've
used has >=TARGET_PER_SPAWN runs, or after GAME_CAP games. Padding sparse spawns
with the next-best player is done at SERVE time (the pool of all top-5 runs per
map is the padding material) -- here we just fill the pool.

Idempotent: skips (map, player, game_id) rows that already exist.

Connection: db.py (prod Cloud SQL by default). For local dev:
  DEEPFRAG_PG_URL=postgresql:///deepfrag .venv/bin/python extract_spawn_runs.py --map aerowalk
"""
import argparse
import json
import math
import sys
import time
import urllib.request

import db

MVD = "https://deepfrag-mvd-api-751658372467.us-central1.run.app"
MAPS = ["aerowalk", "bravado", "ztndm3", "dm4", "dm2", "dm6", "skull", "metron", "pocket"]
WIN_MS, TO_S = 13, 12
TARGET_PER_SPAWN = 3
GAME_CAP = 50

DDL = """
CREATE TABLE IF NOT EXISTS spawn_runs (
  id             BIGSERIAL PRIMARY KEY,
  map            TEXT    NOT NULL,
  player         TEXT    NOT NULL,           -- canonical_id (who actually played it)
  rank_on_map    INTEGER,                    -- 1..5 by per-map conservative rating
  game_id        BIGINT  NOT NULL,           -- hub_game_id
  match_date     TIMESTAMPTZ,
  own_spawn      TEXT    NOT NULL,           -- BSP spawn loc label
  enemy_spawn    TEXT,                       -- enemy's spawn loc (conditioning var)
  items_outcome  TEXT    NOT NULL,           -- full_start/ra/mh_only/ya_ga/nothing
  opening_result TEXT    NOT NULL,           -- won/traded/lost/survived
  first_kill_ms  INTEGER,
  first_death_ms INTEGER,
  duration_s     REAL,
  path           JSONB   NOT NULL,           -- [{x,y,z,h,a,at,state},...] per 13ms bucket, first life
  enemy_path     JSONB,                      -- enemy [{x,y,z}|null,...] over the SAME window (null=dead); replay ghost
  created_at     TIMESTAMPTZ DEFAULT now(),
  UNIQUE (map, player, game_id)
);
CREATE INDEX IF NOT EXISTS spawn_runs_map_player_spawn ON spawn_runs (map, player, own_spawn);
CREATE INDEX IF NOT EXISTS spawn_runs_map_spawn        ON spawn_runs (map, own_spawn);
"""


def http_get(path, retries=3):
    last = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(MVD + path, timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5)
    raise last


def label_spawns(spawns):
    """Ensure every spawn has a non-null `loc`. Unlabeled maps (e.g. metron, whose
    spawns were never annotated) get stable index labels S1..Sn so runs still
    group and never violate own_spawn NOT NULL. The annotator can label them
    properly later and a re-extract will pick up the real names."""
    for i, s in enumerate(spawns):
        if not s.get("loc"):
            s["loc"] = f"S{i + 1}"
    return spawns


def snap_spawn(spawns, x, y, z):
    best, bd = None, 1e9
    for s in spawns:
        d = math.sqrt((x - s["x"]) ** 2 + (y - s["y"]) ** 2 + (z - s["z"]) ** 2)
        if d < bd:
            bd, best = d, s
    return best["loc"], round(bd)


def first_alive(p):
    for i, a in enumerate(p.get("alive", [])):
        if a:
            return i
    return 0


def extract_run(game_id, player_key, spawns):
    """Return a dict describing player's first-spawn run, or None if unusable."""
    b = http_get(f"/v1/demos/gameId:{game_id}/buckets?windowMs={WIN_MS}&from=0&to={TO_S}&layout=column")
    pls = b.get("players", {})
    pk = next((k for k in pls if k.lower() == player_key.lower()), None)
    if not pk:
        return None
    ek = next((k for k in pls if k != pk), None)
    me, en = pls[pk], pls.get(ek)

    i0 = first_alive(me)
    zlist = me.get("z", [])
    own = snap_spawn(spawns, me["x"][i0], me["y"][i0], zlist[i0] if i0 < len(zlist) else 0)[0]
    enemy = None
    if en:
        j0 = first_alive(en)
        ez = en.get("z", [])
        enemy = snap_spawn(spawns, en["x"][j0], en["y"][j0], ez[j0] if j0 < len(ez) else 0)[0]

    n = me["n"]
    X, Y, Z, A, H, alive = me["x"], me["y"], me.get("z", [0] * n), me["a"], me["h"], me["alive"]
    AT = me.get("at", [])            # armor type per bucket: '', 'ga', 'ya', 'ra'
    RL, LG = me.get("rl", []), me.get("lg", [])  # power-weapon possession flags
    path, max_a, mega, died = [], 0, False, None
    for i in range(n):
        if i < len(alive) and not alive[i]:
            died = i
            break
        hv = H[i] if i < len(H) else 0
        av = A[i] if i < len(A) else 0
        armed = bool((i < len(RL) and RL[i]) or (i < len(LG) and LG[i]))
        # state mirrors the existing playback tool: 0 naked / 1 armored / 2 armed / 3 stacked
        state = (1 if av > 0 else 0) + (2 if armed else 0)
        path.append({
            "x": X[i], "y": Y[i], "z": Z[i] if i < len(Z) else 0,
            "h": hv, "a": av, "at": AT[i] if i < len(AT) else "", "state": state,
        })
        max_a = max(max_a, av)
        if hv > 100:
            mega = True
    if not path:
        return None

    # enemy path over the SAME bucket window (for synced replay); positions only.
    enemy_path = None
    if en:
        eX, eY, eZ = en.get("x", []), en.get("y", []), en.get("z", [])
        ea = en.get("alive", [])
        enemy_path = []
        for i in range(len(path)):
            if i < len(ea) and not ea[i]:
                enemy_path.append(None)  # enemy dead this bucket
            elif i < len(eX):
                enemy_path.append({"x": eX[i], "y": eY[i], "z": eZ[i] if i < len(eZ) else 0})
            else:
                enemy_path.append(None)

    if max_a >= 150 and mega:
        items = "full_start"
    elif max_a >= 150:
        items = "ra"
    elif mega:
        items = "mh_only"
    elif max_a >= 50:
        items = "ya_ga"
    else:
        items = "nothing"

    fr = http_get(f"/v1/demos/gameId:{game_id}/frags").get("frags", [])
    win_ms = (died * WIN_MS if died else TO_S * 1000) + 1500
    cutoff = max(win_ms, 6000)
    early = [f for f in fr if f.get("time", 0) <= cutoff]
    my_kill = next((f["time"] for f in early if f.get("killer") == pk and f.get("victim") != pk), None)
    my_death = next((f["time"] for f in early if f.get("victim") == pk and f.get("killer") != pk), None)
    if my_kill and my_death:
        result = "traded" if abs(my_kill - my_death) < 2000 else ("won" if my_kill < my_death else "lost")
    elif my_kill:
        result = "won"
    elif my_death:
        result = "lost"
    else:
        result = "survived"

    return dict(
        own_spawn=own, enemy_spawn=enemy, items_outcome=items, opening_result=result,
        first_kill_ms=my_kill, first_death_ms=my_death,
        duration_s=round(len(path) * WIN_MS / 1000, 2), path=path, enemy_path=enemy_path,
    )


def top5(cur, mp):
    cur.execute(
        """SELECT canonical_id FROM ratings
           WHERE mode='1on1' AND map=%s AND matches_rated>=10
           ORDER BY conservative DESC LIMIT 5""", (mp,))
    return [r["canonical_id"] for r in cur.fetchall()]


def player_games(cur, mp, canon):
    """Recent 1on1 games on this map for this player, newest first, with hub id."""
    cur.execute(
        """SELECT m.hub_game_id AS gid, m.match_date AS mdate, p.player_name AS pname
           FROM players p
           JOIN matches m ON m.match_id = p.match_id
           WHERE p.canonical_id=%s AND m.match_mode='1on1' AND m.match_map=%s
                 AND m.hub_game_id IS NOT NULL
           ORDER BY m.match_date DESC LIMIT %s""", (canon, mp, GAME_CAP))
    return cur.fetchall()


def run_map(conn, mp, verbose=True):
    cur = conn.cursor()
    cur.execute("SELECT entities->'spawns' AS s FROM map_annotations WHERE map=%s", (mp,))
    row = cur.fetchone()
    if not row or not row["s"]:
        print(f"  {mp}: NO spawn entities — skip")
        return
    spawns = label_spawns(row["s"])
    players = top5(cur, mp)
    print(f"\n=== {mp} === top5: {players}")

    for rank, canon in enumerate(players, 1):
        games = player_games(cur, mp, canon)
        cur.execute("SELECT game_id FROM spawn_runs WHERE map=%s AND player=%s", (mp, canon))
        done = {r["game_id"] for r in cur.fetchall()}
        # seed per-spawn counts from already-stored runs
        cur.execute("SELECT own_spawn, COUNT(*) c FROM spawn_runs WHERE map=%s AND player=%s GROUP BY own_spawn", (mp, canon))
        counts = {r["own_spawn"]: r["c"] for r in cur.fetchall()}
        added = 0
        for g in games:
            gid = g["gid"]
            if gid in done:
                continue
            if counts and all(v >= TARGET_PER_SPAWN for v in counts.values()) and len(counts) >= len(spawns):
                break  # full coverage for this player
            try:
                run = extract_run(gid, g["pname"], spawns)
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print(f"    g{gid} {canon}: ERR {e}")
                continue
            if not run:
                continue
            cur.execute(
                """INSERT INTO spawn_runs
                   (map, player, rank_on_map, game_id, match_date, own_spawn, enemy_spawn,
                    items_outcome, opening_result, first_kill_ms, first_death_ms, duration_s, path, enemy_path)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (map, player, game_id) DO NOTHING""",
                (mp, canon, rank, gid, g["mdate"], run["own_spawn"], run["enemy_spawn"],
                 run["items_outcome"], run["opening_result"], run["first_kill_ms"],
                 run["first_death_ms"], run["duration_s"], json.dumps(run["path"]),
                 json.dumps(run["enemy_path"]) if run["enemy_path"] is not None else None))
            conn.commit()
            counts[run["own_spawn"]] = counts.get(run["own_spawn"], 0) + 1
            added += 1
        cov = ", ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
        print(f"  #{rank} {canon:12} +{added} runs | coverage[{cov}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", help="single map (default: all 9)")
    ap.add_argument("--init-only", action="store_true", help="create table and exit")
    args = ap.parse_args()

    conn = db.connect(dict_rows=True)
    with conn.cursor() as c:
        c.execute(DDL)
    conn.commit()
    if args.init_only:
        print("spawn_runs table ready")
        return

    maps = [args.map] if args.map else MAPS
    for mp in maps:
        run_map(conn, mp)
    conn.close()


if __name__ == "__main__":
    main()

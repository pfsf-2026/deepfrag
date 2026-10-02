#!/usr/bin/env python3
"""Fill the movement report: per-hop air-strafe analysis for every player in recent duels.

    DEEPFRAG_SYNC_SECRET=... python3 tools/movement/extract_movement.py [--days 45] [--mode 1on1] [--max 4000] [--workers 6]

Asks the API which games are not processed yet (`/api/admin/movement/todo`), pulls each game's
raw timestamped track from the mvd-api (`stream-slice`, ~7 MB, under a second), runs
`movement.analyze_track` for every rostered player and pushes the summaries to
`/api/admin/movement/load`. Safe to re-run: finished games are skipped. A player who cannot
be found in the demo is pushed with empty metrics so the game is not retried forever.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import coaching as C      # noqa: E402  (mvd-api client + demo-name resolver)
import movement as M      # noqa: E402

API = os.environ.get("DEEPFRAG_API", "https://deepfrag-api-751658372467.us-central1.run.app")
SECRET = os.environ.get("DEEPFRAG_SYNC_SECRET") or os.environ.get("SYNC_SECRET")


def call(method, path, body=None, timeout=120):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Authorization", "Bearer " + SECRET)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def process(game, mode, version):
    gid = game["gid"]
    rows = []
    b = C._get(f"/v1/demos/gameId:{gid}/stream-slice?from=0&to=99999&fields=pos,view,hgt", timeout=240)
    tracks = {p["name"]: p for p in (b or {}).get("players", [])}
    for pl in game["players"]:
        row = {"hub_game_id": gid, "canonical_id": pl["cid"], "player_name": pl["name"], "map": game["map"],
               "played_at": game["date"], "mode": mode, "version": version,
               "clean_hops": None, "minutes": None, "metrics": {}}
        key = (C._resolve_player_key(pl["name"], list(tracks)) or C._resolve_player_key(pl["cid"], list(tracks))) if tracks else None
        if key:
            try:
                r = M.analyze_track(tracks[key])
            except Exception as e:          # one bad track must not sink the batch
                r = None
                print(f"  analyse failed {gid} {pl['name']}: {e}", file=sys.stderr)
            if r:
                s = r["summary"]
                row.update(clean_hops=s["clean_hops"], minutes=s["minutes"], metrics=s)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--mode", default="1on1")
    ap.add_argument("--max", type=int, default=4000, help="stop after this many games")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if not SECRET:
        sys.exit("set DEEPFRAG_SYNC_SECRET")
    done = ok = 0
    t0 = time.time()
    while done < a.max:
        todo = call("GET", f"/api/admin/movement/todo?mode={a.mode}&days={a.days}&limit={min(500, a.max - done)}")
        games, version = todo["games"], todo["version"]
        if not games:
            break
        rows = []
        # processes, not threads: the analysis is pure-Python CPU work
        with cf.ProcessPoolExecutor(a.workers) as ex:
            for out in ex.map(process, games, [a.mode] * len(games), [version] * len(games), chunksize=4):
                rows.extend(out)
                if len(rows) >= 200:
                    call("POST", "/api/admin/movement/load", {"rows": rows})
                    ok += sum(1 for r in rows if r["clean_hops"] is not None)
                    rows = []
        if rows:
            call("POST", "/api/admin/movement/load", {"rows": rows})
            ok += sum(1 for r in rows if r["clean_hops"] is not None)
        done += len(games)
        print(f"{done} games done, {ok} player-games analysed, {time.time() - t0:.0f}s", flush=True)
    print(f"finished: {done} games, {ok} player-games with movement data")


if __name__ == "__main__":
    main()

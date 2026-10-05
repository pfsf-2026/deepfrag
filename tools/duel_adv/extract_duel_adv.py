#!/usr/bin/env python3
"""Bulk-fill the duel advanced stats (duel_advanced_stats) from the mvd-api.

    DEEPFRAG_SYNC_SECRET=... python3 tools/duel_adv/extract_duel_adv.py [--days 60] [--max 10000] [--workers 8]

Asks the API which duels are not scored at the current version (`/api/admin/duel-advanced/todo`),
scores each one with `duel_adv.rows_for_game` (four small mvd-api calls per game) and pushes the
rows to `/api/admin/duel-advanced/load`. Games that cannot be scored are sent as skips so they are
not retried. Safe to re-run. Day to day this is not needed: the ladder tick scores new duels a few
at a time. Use it after a version bump or to fill a long window.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import coaching as C      # noqa: E402  (mvd-api client)
import duel_adv as D      # noqa: E402

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


def process(game):
    try:
        rows, reason = D.rows_for_game(game, lambda path: C._get(path, timeout=120))
    except Exception as e:                    # one bad demo must not sink the batch
        rows, reason = None, f"error: {type(e).__name__}"
    return game["gid"], rows, reason


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--max", type=int, default=10000, help="stop after this many games")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if not SECRET:
        sys.exit("set DEEPFRAG_SYNC_SECRET")
    done = ok = 0
    reasons = {}
    t0 = time.time()
    while done < a.max:
        games = call("GET", f"/api/admin/duel-advanced/todo?days={a.days}&limit={min(500, a.max - done)}")["games"]
        if not games:
            break
        rows, skips = [], []

        def flush():
            nonlocal rows, skips
            if rows or skips:
                call("POST", "/api/admin/duel-advanced/load", {"rows": rows, "skips": skips})
            rows, skips = [], []

        # threads: the work is waiting on the mvd-api, the scoring itself is a few milliseconds
        with cf.ThreadPoolExecutor(a.workers) as ex:
            for gid, out, reason in ex.map(process, games):
                if out:
                    rows.extend(out)
                    ok += 1
                else:
                    skips.append({"hub_game_id": gid, "reason": reason})
                    reasons[reason] = reasons.get(reason, 0) + 1
                if len(rows) + len(skips) >= 200:
                    flush()
        flush()
        done += len(games)
        print(f"{done} games done, {ok} scored, skipped {reasons}, {time.time() - t0:.0f}s", flush=True)
    print(f"finished: {done} games, {ok} scored, skipped {reasons}")


if __name__ == "__main__":
    main()

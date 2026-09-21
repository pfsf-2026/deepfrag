"""Push per-player-per-duel advanced rows from the corpus (player_duel in
data/mvd_features.sqlite, built by duel_corpus.py) into production
`duel_advanced_stats` via POST /api/admin/duel-advanced/load (god key).

Names are mapped to canonical ids with canon.py (the same resolver production
uses); rows whose name does not resolve are skipped and counted. hub_game_id =
the corpus game id (the hub id the demo was fetched by).

Usage:
  SYNC_SECRET=... python tools/mvd_features/push_duel_adv.py [db] [--api https://app.deepfrag.gg] [--since 2026-01-01] [--dry]
"""
import json, os, sqlite3, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import canon  # noqa: E402

_OPTVALS = {sys.argv[i + 1] for i, a in enumerate(sys.argv) if a in ('--api', '--since') and i + 1 < len(sys.argv)}
DB = next((a for a in sys.argv[1:] if not a.startswith('--') and a not in _OPTVALS), str(HERE.parents[1] / 'data' / 'mvd_features.sqlite'))
API = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--api'), 'https://app.deepfrag.gg')
SINCE = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--since'), None)
DRY = '--dry' in sys.argv
VERSION = 1
COLS = ["hub_game_id", "canonical_id", "played_at", "map", "opponent_id", "win", "minutes",
        "frags", "kills", "deaths", "adj_kills", "dmg", "taken", "stacked_given", "stacked_taken",
        "spawn_deaths", "spawnfrags_vs", "chained_real",
        "fights", "started", "started_behind", "started_ahead",
        "even_w", "even_n", "behind_w", "behind_n", "ahead_w", "ahead_n",
        "item_first", "ra", "ra_on_timer", "ya", "mh", "plus_minus", "model_version"]


def main():
    secret = os.environ.get('SYNC_SECRET')
    if not secret and not DRY:
        sys.exit('SYNC_SECRET not set (use --dry to only count rows)')
    con = sqlite3.connect(DB, timeout=120)
    cmap = canon.load(con)
    q = """SELECT d.game_id, d.ts, d.map, d.name, d.opp, d.win, d.minutes, d.frags, d.kills, d.deaths, d.adj_kills, d.dmg, d.taken,
                  p.stacked_given, p.stacked_taken, d.spawn_deaths, d.spawnfrags_vs, d.chained_real,
                  d.fights, d.started, d.started_behind, d.started_ahead, d.even_w, d.even_n, d.behind_w, d.behind_n, d.ahead_w, d.ahead_n,
                  d.item_first, d.ra, d.ra_on_timer, d.ya, d.mh, d.plus_minus
           FROM player_duel d JOIN players p ON p.game_id=d.game_id AND p.name=d.name"""
    args = ()
    if SINCE:
        q += " WHERE d.ts >= ?"; args = (SINCE,)
    q += " ORDER BY d.ts"
    rows, skipped = [], 0
    for r in con.execute(q, args):
        cid = cmap.get(r[3]); ocid = cmap.get(r[4])
        if not cid:
            skipped += 1; continue
        rows.append(dict(zip(COLS, [r[0], cid, r[1], r[2], ocid, r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14],
                                     r[15], r[16], r[17], r[18], r[19], r[20], r[21], r[22], r[23], r[24], r[25], r[26], r[27],
                                     r[28], r[29], r[30], r[31], r[32], r[33], VERSION])))
    # one row per (game, canonical id): a player who reconnected under a second spelling of his
    # name (crïnus / cronus, BLooD_DoG(D_P / BLooD_DoG(D_P)) resolves to the same id twice in one
    # game — keep the row with the most minutes, so the upsert never sees the key twice.
    best = {}
    for r in rows:
        k = (r['hub_game_id'], r['canonical_id'])
        if k not in best or (r.get('minutes') or 0) > (best[k].get('minutes') or 0):
            best[k] = r
    dups = len(rows) - len(best); rows = list(best.values())
    print(f'{dups} duplicate (game, player) rows collapsed', flush=True)
    print(f'{len(rows)} rows to push, {skipped} skipped (name did not resolve)', flush=True)
    if DRY:
        print(json.dumps(rows[:2], indent=1)); return
    t0 = time.time(); done = 0
    for i in range(0, len(rows), 1500):
        batch = rows[i:i + 1500]
        req = urllib.request.Request(f'{API}/api/admin/duel-advanced/load', data=json.dumps({'rows': batch}).encode(),
                                     headers={'Authorization': f'Bearer {secret}', 'Content-Type': 'application/json',
                                              'User-Agent': 'DeepFrag push_duel_adv'}, method='POST')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    out = json.load(resp); done += out.get('upserted', 0); break
            except Exception as e:
                if attempt == 2: raise
                print('retry', i, e, flush=True); time.sleep(3)
        print(f'{done}/{len(rows)} upserted, {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()

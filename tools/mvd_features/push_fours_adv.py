"""Push per-player-per-fours rows from the corpus into production
`fours_advanced_stats` via POST /api/admin/fours-advanced/load (god key).

Joins player_agi (scored metrics, canonical id in `cid`), player_war (+/- above
average / replacement), players (stacked damage, item takes), ra_timing (on-timer
reds), powerup_runs (quad runs aggregated per holder-game), player_fights (fight
selection, teamkills, team damage) and player_shots (rockets).

Usage:
  SYNC_SECRET=... python tools/mvd_features/push_fours_adv.py [db] [--api https://app.deepfrag.gg] [--since 2026-01-01] [--dry]
"""
import json, os, sqlite3, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = next((a for a in sys.argv[1:] if not a.startswith('--')), str(HERE.parents[1] / 'data' / 'mvd_features.sqlite'))
API = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--api'), 'https://app.deepfrag.gg')
SINCE = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == '--since'), None)
DRY = '--dry' in sys.argv
VERSION = 1
COLS = ["hub_game_id", "canonical_id", "played_at", "map", "team", "win", "minutes",
        "frags", "kills", "deaths", "adj_kills", "dmg", "taken", "stacked_given", "stacked_taken",
        "spawn_deaths", "chained_real", "multi", "take_ra", "take_ya", "take_mh", "take_quad", "take_pent",
        "ra_on_timer", "ra_median_wait_s", "quad_runs", "quad_full_runs", "quad_frags_full", "quad_died", "quad_wasted",
        "rockets_fired", "rl_dmg", "rl_connect_pct",
        "fights", "started", "started_behind", "started_ahead", "even_w", "even_n", "behind_w", "behind_n", "ahead_w", "ahead_n",
        "teamkills", "tk_launcher", "team_dmg",
        "plus_minus", "expected", "above_avg", "above_repl", "agi",
        "game_ra", "game_ya", "game_mh", "game_quad", "model_version"]

Q = """
WITH q AS (
  SELECT game_id, holder, COUNT(*) runs, SUM(CASE WHEN dur_s>=28 THEN 1 ELSE 0 END) full_runs,
         SUM(CASE WHEN dur_s>=28 THEN holder_frags ELSE 0 END) frags_full, SUM(holder_died) died, SUM(wasted) wasted
  FROM powerup_runs WHERE kind='quad' GROUP BY game_id, holder)
SELECT a.game_id, a.cid, a.ts, a.map, a.team, a.win, a.minutes,
       a.frags, a.kills, a.deaths, a.adj_kills, a.dmg, a.taken, p.stacked_given, p.stacked_taken,
       a.spawn_deaths, a.chained_real, a.multi, a.take_ra, p.take_ya, p.take_mh, a.take_quad, a.take_pent,
       r.ra_on_timer, r.ra_median_wait_s, q.runs, q.full_runs, q.frags_full, q.died, q.wasted,
       a.rockets_fired, a.rl_dmg, a.rl_connect_pct,
       f.fights, f.started, f.started_behind, f.started_ahead, f.even_w, f.even_n, f.behind_w, f.behind_n, f.ahead_w, f.ahead_n,
       f.teamkills, f.tk_launcher, f.team_dmg,
       a.plus_minus, w.expected, w.above_avg, w.above_repl, a.agi,
       gt.g_ra, gt.g_ya, gt.g_mh, gt.g_quad
FROM player_agi a
JOIN (SELECT game_id, SUM(take_ra) g_ra, SUM(take_ya) g_ya, SUM(take_mh) g_mh, SUM(take_quad) g_quad FROM players GROUP BY game_id) gt ON gt.game_id=a.game_id
JOIN player_war w ON w.game_id=a.game_id AND w.canonical_id=a.cid
JOIN players p ON p.game_id=a.game_id AND p.name=a.name
LEFT JOIN ra_timing r ON r.game_id=a.game_id AND r.name=a.name
LEFT JOIN q ON q.game_id=a.game_id AND q.holder=a.name
LEFT JOIN player_fights f ON f.game_id=a.game_id AND f.name=a.name
WHERE a.minutes > 0 {since}
ORDER BY a.ts
"""


def main():
    secret = os.environ.get('SYNC_SECRET')
    if not secret and not DRY:
        sys.exit('SYNC_SECRET not set (use --dry to only count rows)')
    con = sqlite3.connect(DB, timeout=120)
    sql = Q.format(since=("AND a.ts >= ?" if SINCE else "")); args = (SINCE,) if SINCE else ()
    rows = []
    for r in con.execute(sql, args):
        if not r[1]:
            continue
        rows.append(dict(zip(COLS, list(r) + [VERSION])))
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
    print(f'{len(rows)} rows to push', flush=True)
    if DRY:
        print(json.dumps(rows[-1], indent=1, default=str)); return
    t0 = time.time(); done = 0
    for i in range(0, len(rows), 1500):
        batch = rows[i:i + 1500]
        req = urllib.request.Request(f'{API}/api/admin/fours-advanced/load', data=json.dumps({'rows': batch}, default=str).encode(),
                                     headers={'Authorization': f'Bearer {secret}', 'Content-Type': 'application/json',
                                              'User-Agent': 'DeepFrag push_fours_adv'}, method='POST')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    out = json.load(resp); done += out.get('upserted', 0); break
            except Exception as e:
                if attempt == 2: raise
                print('retry', i, e, flush=True); time.sleep(3)
        print(f'{done}/{len(rows)} upserted, {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()

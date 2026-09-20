"""Fours re-pass: quad CONTESTS per player per game -> `player_quad`.

Peter's definition (2026-09-20): a player contested a quad spawn if he was within 650 u of
the quad at any point in the last 10 s before it spawned, up to the spawn, including the case
where he died there before it spawned. The exact count comes from quad_exact_pass.py (100 ms
positions); this pass is the FALLBACK for games without exact rows: it approximates the rule
from the 10-second state samples (`player_state10s.loc`, a named spot) using each map's quad
zone (`quad_zones.json`, per-map radius calibrated so the proxy matches the exact count).

Spawn times come from `item_takes` (t - wait_ms). Untaken quad spawns are not recorded, but
nearly every quad is taken.

Columns: game_id, name, quad_spawns, quad_contests, quad_contest_takes, quad_contest_died.
"""
import sqlite3, sys, json, os, collections, time
DB = sys.argv[1] if len(sys.argv) > 1 else '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
HERE = os.path.dirname(os.path.abspath(__file__))
Z = json.load(open(os.path.join(HERE, 'quad_zones.json')))
con = sqlite3.connect(DB, timeout=300)
con.executescript("""DROP TABLE IF EXISTS player_quad;
CREATE TABLE player_quad(game_id INT, name TEXT, quad_spawns INT, quad_contests INT, quad_contest_takes INT, quad_contest_died INT);""")
games = con.execute("SELECT id, map FROM games WHERE mode='4on4'").fetchall()
out = []; t0 = time.time(); skipped = 0
for gi, (gid, mp) in enumerate(games):
    zone = set(Z.get(mp, {}).get('zone', []))
    if not zone:
        skipped += 1; continue
    names = [r[0] for r in con.execute("SELECT name FROM players WHERE game_id=?", (gid,))]
    spawns = [(t - (w or 0), n) for t, n, w in con.execute("SELECT t, name, wait_ms FROM item_takes WHERE game_id=? AND kind='quad' ORDER BY t", (gid,))]
    st = collections.defaultdict(dict)
    for t, n, al, loc in con.execute("SELECT t, name, alive, loc FROM player_state10s WHERE game_id=?", (gid,)):
        st[n][t] = (al, loc)
    deaths = collections.defaultdict(list)
    for t, v in con.execute("SELECT t, vic FROM events WHERE game_id=? AND kind='frag' AND selfd=0", (gid,)):
        deaths[v].append(t)
    for n in names:
        c = tk = dd = 0
        for sp, taker in spawns:
            lo = sp - 10000
            samples = [st[n].get(t) for t in range(((lo // 10000) + 1) * 10000, sp + 1, 10000)] + [st[n].get((lo // 10000) * 10000)]
            inzone = any(s and s[0] and s[1] in zone for s in samples if s)
            died_close = False
            if not inzone:
                for dt in deaths.get(n, []):
                    if lo <= dt <= sp:
                        prev = st[n].get((dt // 10000) * 10000)
                        if prev and prev[1] in zone:
                            died_close = True; break
            if inzone or died_close:
                c += 1; tk += (taker == n); dd += died_close
        out.append((gid, n, len(spawns), c, tk, dd))
    if gi % 500 == 0: print(f'{gi}/{len(games)} {time.time()-t0:.0f}s', flush=True)
con.executemany("INSERT INTO player_quad VALUES (?,?,?,?,?,?)", out); con.commit()
print(f'player_quad rows {len(out)}, games skipped (no zone for map) {skipped}', flush=True)

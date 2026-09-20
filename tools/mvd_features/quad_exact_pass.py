"""Exact quad attendance for every fours game -> `player_quad_exact`.

Peter's rule (2026-09-20): a player CONTESTED a quad spawn if he was within 650 u of the
quad at any point in the last 10 s before it spawned, up to the spawn (nothing after the
spawn counts), including dying there before it spawned. 400 u is kept as a second column. This pass re-downloads each demo and runs the analyzer WITH positions (100 ms
samples), so it is the exact version of the 10-s-sample proxy in quad_contest_pass.py.
Resumable: games already in the table are skipped. ~15 s per game per worker.

Columns: game_id, name, quad_spawns, then per radius (650 = the rule, 400 = tight):
  quad_contests, quad_contest_takes, quad_contest_died, quad_at_spawn, c400, t400, d400, a400.
Usage: quad_exact_pass.py [workers] [limit]   (run from a dir where ../qw-analyze exists, e.g. scratchpad/mvdfeat)
"""
import json, sqlite3, subprocess, os, sys, time, math, bisect, urllib.request, gzip, shutil, tempfile
from multiprocessing import Pool
ANALYZER = os.path.abspath('../qw-analyze'); DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
MANIFEST = os.path.abspath('manifest_all.json')
RADII, WIN = (650.0, 400.0), 10000

def process(g):
    gid = g['id']; sha = g['demo_sha256']; tmp = tempfile.mkdtemp(prefix='qx_')
    try:
        url = f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz"; gz = os.path.join(tmp, 'd.mvd.gz'); mvd = os.path.join(tmp, 'd.mvd')
        with urllib.request.urlopen(url, timeout=60) as r, open(gz, 'wb') as f: shutil.copyfileobj(r, f)
        with gzip.open(gz, 'rb') as fi, open(mvd, 'wb') as fo: shutil.copyfileobj(fi, fo)
        out = subprocess.run([ANALYZER, '-view', 'full', '-include', 'positions', mvd], capture_output=True, timeout=240)
        d = json.loads(out.stdout); END = d['streams']['global']['matchEnd']
        P = {p['name']: p for p in d['streams']['players']}
        quads = [it for it in d['items']['items'] if it['kind'] == 'quad']
        if not quads: return {'id': gid, 'rows': [], 'note': 'no quad'}
        q = quads[0]; QP = (q['x'], q['y'], q['z'])
        SP = [(ph['availableFrom'], ph.get('takenBy')) for ph in q['phases'] if ph.get('availableFrom') is not None and ph['availableFrom'] <= END]
        rows = []
        for n, p in P.items():
            if not p.get('pos') or not p['pos'].get('t'): continue   # no position stream (joined late / spectator)
            sp = p.get('sp', []); dd = p.get('d', []); pt = p['pos']['t']; px, py, pz = p['pos']['x'], p['pos']['y'], p['pos']['z']
            def alive(t):
                ls = max([x for x in sp if x <= t], default=0); ld = max([x for x in dd if x <= t], default=-1); return ls >= ld
            def dist(t):
                i = bisect.bisect_left(pt, t); i = min(max(i, 0), len(pt) - 1)
                if i > 0 and abs(pt[i - 1] - t) < abs(pt[i] - t): i -= 1
                return math.dist((px[i], py[i], pz[i]), QP)
            acc = {R: [0, 0, 0, 0] for R in RADII}
            for t, taker in SP:
                # min distance while alive over the last 10 s up to the spawn (100 ms steps), plus death-in-window
                samples = [(tt, dist(tt)) for tt in range(max(t - WIN, 0), t + 1, 100) if alive(tt)]
                ds = [x for x in dd if t - WIN <= x <= t]
                dpos = dist(ds[-1] - 200) if ds and alive(ds[-1] - 200) else None
                for R in RADII:
                    # died within R in the window counts as contesting (and is reported as quad_contest_died)
                    dc = dpos is not None and dpos <= R
                    close = any(d_ <= R for _, d_ in samples) or dc
                    a = acc[R]; a[0] += close; a[1] += (taker == n and close); a[2] += dc; a[3] += (alive(t) and dist(t) <= R)
            rows.append((gid, n, len(SP), *acc[650.0], *acc[400.0]))
        return {'id': gid, 'rows': rows}
    except Exception as e:
        return {'id': gid, 'error': f'{type(e).__name__}: {str(e)[:120]}'}
    finally: shutil.rmtree(tmp, ignore_errors=True)

if __name__ == '__main__':
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4; limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
    con = sqlite3.connect(DB, timeout=300)
    con.execute("CREATE TABLE IF NOT EXISTS player_quad_exact(game_id INT, name TEXT, quad_spawns INT, quad_contests INT, quad_contest_takes INT, quad_contest_died INT, quad_at_spawn INT, c400 INT, t400 INT, d400 INT, a400 INT)")
    con.execute("CREATE TABLE IF NOT EXISTS quad_exact_done(game_id INT PRIMARY KEY, note TEXT)")
    done = {r[0] for r in con.execute("SELECT game_id FROM quad_exact_done")}
    ids = {r[0]: r[1] for r in con.execute("SELECT id, ts FROM games WHERE mode='4on4'")}
    games = sorted([g for g in json.load(open(MANIFEST)) if g['id'] in ids and g['id'] not in done], key=lambda g: -g['id'])[:limit]
    print(f'todo {len(games)} fours (newest first)', flush=True); t0 = time.time(); n = 0; errs = 0
    with Pool(workers) as pool:
        for res in pool.imap_unordered(process, games, chunksize=2):
            n += 1
            if 'error' in res:
                errs += 1; con.execute("INSERT OR REPLACE INTO quad_exact_done VALUES (?,?)", (res['id'], res['error'])); print('ERR', res['id'], res['error'], flush=True)
            else:
                con.executemany("INSERT INTO player_quad_exact VALUES (?,?,?,?,?,?,?,?,?,?,?)", res['rows']); con.execute("INSERT OR REPLACE INTO quad_exact_done VALUES (?,?)", (res['id'], res.get('note')))
            if n % 25 == 0:
                con.commit(); print(f'{n}/{len(games)} {errs} errors {time.time()-t0:.0f}s ({(time.time()-t0)/n:.1f}s/game)', flush=True)
    con.commit(); print(f'FINISHED {n} {errs} errors {time.time()-t0:.0f}s', flush=True)

"""Where quad contesters come from, and who wins it -> `quad_approach` (per spawn, per player).

Peter (2026-09-21): the ways into quad differ per map (schloss one door; e1m2 two; dm2 and dm3
several), so "hold the door" is wrong advice. This pass records, for every quad spawn in every
fours game, each player's position 10 s / 5 s / 2 s before the spawn and at the spawn, his stack
at 2 s before, whether he contested it (650 u rule), took it, or died before it spawned, and when he
first got within 650 u. Positions are then clustered per map into approaches (quad_approach_report.py)
to say which way in converts, with what stack, and how early the takers arrive.

Also stores each map's item coordinates once (`map_items_xyz`) for naming the clusters.
Resumable (quad_approach_done). Usage: quad_approach_pass.py [workers] [limit]  (run from scratchpad/inc)
"""
import json, sqlite3, subprocess, os, sys, time, math, bisect, urllib.request, gzip, shutil, tempfile
from multiprocessing import Pool
ANALYZER = os.path.abspath('../qw-analyze'); DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
MANIFEST = os.path.abspath('manifest_all.json')
R, WIN = 650.0, 10000
SOAK = {'ra': 0.8, 'ya': 0.6, 'ga': 0.3}

def step(series):
    ts = [e['t'] for e in series]; vs = [e['v'] for e in series]
    def at(t):
        i = bisect.bisect_right(ts, t) - 1
        return vs[i] if i >= 0 else None
    return at

def process(g):
    gid = g['id']; sha = g['demo_sha256']; tmp = tempfile.mkdtemp(prefix='qa_')
    try:
        url = f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz"; gz = os.path.join(tmp, 'd.mvd.gz'); mvd = os.path.join(tmp, 'd.mvd')
        with urllib.request.urlopen(url, timeout=60) as r, open(gz, 'wb') as f: shutil.copyfileobj(r, f)
        with gzip.open(gz, 'rb') as fi, open(mvd, 'wb') as fo: shutil.copyfileobj(fi, fo)
        out = subprocess.run([ANALYZER, '-view', 'full', '-include', 'positions', mvd], capture_output=True, timeout=240)
        d = json.loads(out.stdout); END = d['streams']['global']['matchEnd']
        items = [(it['kind'], it.get('x'), it.get('y'), it.get('z')) for it in d['items']['items'] if it.get('x') is not None]
        quads = [it for it in d['items']['items'] if it['kind'] == 'quad']
        if not quads: return {'id': gid, 'rows': [], 'items': items, 'note': 'no quad'}
        q = quads[0]; QP = (q['x'], q['y'], q['z'])
        SP = [(ph['availableFrom'], ph.get('takenBy')) for ph in q['phases'] if ph.get('availableFrom') is not None and ph['availableFrom'] <= END]
        rows = []
        for p in d['streams']['players']:
            n = p['name']; team = p.get('team')
            if not p.get('pos') or not p['pos'].get('t'): continue
            sp = p.get('sp', []); dd = p.get('d', []); pt = p['pos']['t']; px, py, pz = p['pos']['x'], p['pos']['y'], p['pos']['z']
            H, A, AT = step(p.get('h', [])), step(p.get('a', [])), step(p.get('at', []))
            def alive(t):
                ls = max([x for x in sp if x <= t], default=0); ld = max([x for x in dd if x <= t], default=-1); return ls >= ld
            def pos(t):
                i = bisect.bisect_left(pt, t); i = min(max(i, 0), len(pt) - 1)
                if i > 0 and abs(pt[i - 1] - t) < abs(pt[i] - t): i -= 1
                return (px[i], py[i], pz[i])
            def dist(t): return math.dist(pos(t), QP)
            for si, (t, taker) in enumerate(SP):
                samples = [(tt, dist(tt)) for tt in range(max(t - WIN, 0), t + 1, 100) if alive(tt)]
                ds = [x for x in dd if t - WIN <= x <= t]
                dpos = dist(ds[-1] - 200) if ds and alive(ds[-1] - 200) else None
                died_pre = 1 if (dpos is not None and dpos <= R) else 0
                close = any(d_ <= R for _, d_ in samples) or died_pre
                enter = next((tt for tt, d_ in samples if d_ <= R), None)
                def snap(off):
                    tt = t - off
                    if tt < 0 or not alive(tt): return (None, None, None, None)
                    x, y, z = pos(tt); return (round(dist(tt)), x, y, z)
                d10, x10, y10, z10 = snap(10000); d5, x5, y5, z5 = snap(5000); d2, x2, y2, z2 = snap(2000); d0, x0, y0, z0 = snap(0)
                t2 = t - 2000 if t >= 2000 else 0
                h = H(t2) if alive(t2) else None; a = A(t2) if alive(t2) else None; at = AT(t2) if alive(t2) else None
                eff = None
                if h is not None:
                    a = a or 0; f = SOAK.get(at or '', 0.0)
                    eff = round(min(h / (1 - f), h + a)) if f else h
                rows.append((gid, t, 1 if si == 0 else 0, n, team, 1 if taker == n else 0, 1 if close else 0, died_pre,
                             d10, d5, d2, d0, x10, y10, z10, x5, y5, z5, x2, y2, z2, x0, y0, z0, h, a, at, eff,
                             1 if alive(t) else 0, (t - enter) if enter is not None else None))
        return {'id': gid, 'rows': rows, 'items': items}
    except Exception as e:
        return {'id': gid, 'error': f'{type(e).__name__}: {str(e)[:120]}'}
    finally: shutil.rmtree(tmp, ignore_errors=True)

COLS = "game_id,spawn_t,first,name,team,took,contested,died_pre,d10,d5,d2,d0,x10,y10,z10,x5,y5,z5,x2,y2,z2,x0,y0,z0,h,a,at,eff,alive0,enter_before_ms"
if __name__ == '__main__':
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4; limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
    con = sqlite3.connect(DB, timeout=300)
    con.execute(f"CREATE TABLE IF NOT EXISTS quad_approach({COLS})")
    con.execute("CREATE TABLE IF NOT EXISTS quad_approach_done(game_id INT PRIMARY KEY, note TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS map_items_xyz(map TEXT, kind TEXT, x REAL, y REAL, z REAL)")
    done = {r[0] for r in con.execute("SELECT game_id FROM quad_approach_done")}
    maps = {r[0]: r[1] for r in con.execute("SELECT id, map FROM games WHERE mode='4on4'")}
    have_items = {r[0] for r in con.execute("SELECT DISTINCT map FROM map_items_xyz")}
    games = sorted([g for g in json.load(open(MANIFEST)) if g['id'] in maps and g['id'] not in done], key=lambda g: -g['id'])[:limit]
    print(f'todo {len(games)} fours (newest first)', flush=True); t0 = time.time(); n = 0; errs = 0
    ph = ",".join("?" * len(COLS.split(",")))
    with Pool(workers) as pool:
        for res in pool.imap_unordered(process, games, chunksize=2):
            n += 1; gid = res['id']; mp = maps.get(gid)
            if 'error' in res:
                errs += 1; con.execute("INSERT OR REPLACE INTO quad_approach_done VALUES (?,?)", (gid, res['error'])); print('ERR', gid, res['error'], flush=True)
            else:
                con.executemany(f"INSERT INTO quad_approach VALUES ({ph})", res['rows'])
                con.execute("INSERT OR REPLACE INTO quad_approach_done VALUES (?,?)", (gid, res.get('note')))
                if mp and mp not in have_items and res.get('items'):
                    con.executemany("INSERT INTO map_items_xyz VALUES (?,?,?,?,?)", [(mp, k, x, y, z) for k, x, y, z in res['items']]); have_items.add(mp)
            if n % 25 == 0:
                con.commit(); print(f'{n}/{len(games)} {errs} errors {time.time()-t0:.0f}s ({(time.time()-t0)/n:.1f}s/game)', flush=True)
    con.commit(); print(f'FINISHED {n} {errs} errors {time.time()-t0:.0f}s', flush=True)

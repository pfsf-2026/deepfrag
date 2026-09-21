"""Second-by-second tracks of every player for the 20 s before each quad spawn -> `quad_tracks`.

For the top-player quad study (Peter, 2026-09-21: "deep analysis of their positioning the 20
seconds before quad on dm3, stack levels, when they show up, their % taking quad, what paths they
took"). Per (game, quad spawn, player) one row with, for t = -20..0 s in 1 s steps:
  loc  = the server's named location the player stood in (analyzer locTable via pos.li)
  dist = distance to the quad in units
  eff  = effective HP (health / (1 - armor soak), capped at health + armor)
  alive flags, plus: took, contested (650 u in the last 10 s), died_pre, enter_before_ms,
  team, source tag (na / eu), the player's frags in the game, and whether he held the RL / LG.

Input: a manifest JSON (hub entries with id, map, demo_sha256, players) — the same format as
scratchpad/inc/manifest_all.json — plus a source tag and an optional map filter.
Usage: quad_track_pass.py MANIFEST SOURCE [--map dm3] [--workers 6] [--limit N]
Run from a dir where ../qw-analyze exists (scratchpad/inc). Resumable per (source, game).
"""
import json, sqlite3, subprocess, os, sys, time, math, bisect, urllib.request, gzip, shutil, tempfile
from multiprocessing import Pool
ANALYZER = os.path.abspath('../qw-analyze'); DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
R, WIN, PRE = 650.0, 10000, 20
SOAK = {'ra': 0.8, 'ya': 0.6, 'ga': 0.3}

def step(series):
    ts = [e['t'] for e in series]; vs = [e['v'] for e in series]
    def at(t):
        i = bisect.bisect_right(ts, t) - 1
        return vs[i] if i >= 0 else None
    return at

def process(g):
    gid = g['id']; sha = g['demo_sha256']; tmp = tempfile.mkdtemp(prefix='qt_')
    try:
        url = f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz"; gz = os.path.join(tmp, 'd.mvd.gz'); mvd = os.path.join(tmp, 'd.mvd')
        with urllib.request.urlopen(url, timeout=60) as r, open(gz, 'wb') as f: shutil.copyfileobj(r, f)
        with gzip.open(gz, 'rb') as fi, open(mvd, 'wb') as fo: shutil.copyfileobj(fi, fo)
        out = subprocess.run([ANALYZER, '-view', 'full', '-include', 'positions', mvd], capture_output=True, timeout=300)
        d = json.loads(out.stdout); END = d['streams']['global']['matchEnd']
        loctab = d.get('timelineAnalysis', {}).get('locTable') or []
        quads = [it for it in d['items']['items'] if it['kind'] == 'quad']
        if not quads: return {'id': gid, 'rows': [], 'note': 'no quad'}
        q = quads[0]; QP = (q['x'], q['y'], q['z'])
        SP = [(ph['availableFrom'], ph.get('takenBy')) for ph in q['phases'] if ph.get('availableFrom') is not None and ph['availableFrom'] <= END]
        frags = {p['name']: p.get('frags') for p in d.get('match', {}).get('players', [])} if isinstance(d.get('match', {}).get('players'), list) else {}
        rows = []
        for p in d['streams']['players']:
            n = p['name']; team = p.get('team')
            if not p.get('pos') or not p['pos'].get('t'): continue
            sp = p.get('sp', []); dd = p.get('d', []); pt = p['pos']['t']; px, py, pz, pli = p['pos']['x'], p['pos']['y'], p['pos']['z'], p['pos'].get('li') or []
            H, A, AT = step(p.get('h', [])), step(p.get('a', [])), step(p.get('at', []))
            rl_iv = [(x['s'], x['e']) for x in p.get('rl', []) if isinstance(x, dict)]; lg_iv = [(x['s'], x['e']) for x in p.get('lg', []) if isinstance(x, dict)]
            def holds(iv, t): return any(s <= t <= e for s, e in iv)
            def alive(t):
                ls = max([x for x in sp if x <= t], default=0); ld = max([x for x in dd if x <= t], default=-1); return ls >= ld
            def idx(t):
                i = bisect.bisect_left(pt, t); i = min(max(i, 0), len(pt) - 1)
                if i > 0 and abs(pt[i - 1] - t) < abs(pt[i] - t): i -= 1
                return i
            def dist(t):
                i = idx(t); return math.dist((px[i], py[i], pz[i]), QP)
            def loc(t):
                i = idx(t); li = pli[i] if i < len(pli) else 0
                return loctab[li] if 0 <= li < len(loctab) else ''
            def eff(t):
                if not alive(t): return None
                h = H(t); a = A(t) or 0; at = AT(t)
                if h is None: return None
                f = SOAK.get(at or '', 0.0); return round(min(h / (1 - f), h + a)) if f else h
            for si, (t, taker) in enumerate(SP):
                samples = [(tt, dist(tt)) for tt in range(max(t - WIN, 0), t + 1, 100) if alive(tt)]
                ds = [x for x in dd if t - WIN <= x <= t]
                dpos = dist(ds[-1] - 200) if ds and alive(ds[-1] - 200) else None
                died_pre = 1 if (dpos is not None and dpos <= R) else 0
                close = any(d_ <= R for _, d_ in samples) or died_pre
                enter = next((tt for tt, d_ in samples if d_ <= R), None)
                track = []
                for k in range(-PRE, 1):
                    tt = t + k * 1000
                    if tt < 0: track.append(None); continue
                    a_ = alive(tt)
                    track.append({'s': k, 'loc': loc(tt) if a_ else None, 'd': round(dist(tt)) if a_ else None, 'eff': eff(tt) if a_ else None,
                                  'rl': 1 if (a_ and holds(rl_iv, tt)) else 0, 'lg': 1 if (a_ and holds(lg_iv, tt)) else 0})
                rows.append((gid, t, 1 if si == 0 else 0, n, team, 1 if taker == n else 0, 1 if close else 0, died_pre,
                             (t - enter) if enter is not None else None, frags.get(n), json.dumps(track, separators=(',', ':'))))
        return {'id': gid, 'rows': rows}
    except Exception as e:
        return {'id': gid, 'error': f'{type(e).__name__}: {str(e)[:120]}'}
    finally: shutil.rmtree(tmp, ignore_errors=True)

if __name__ == '__main__':
    manifest = sys.argv[1]; source = sys.argv[2]
    mapf = sys.argv[sys.argv.index('--map') + 1] if '--map' in sys.argv else None
    workers = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else 4
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 10 ** 9
    con = sqlite3.connect(DB, timeout=300)
    con.execute("""CREATE TABLE IF NOT EXISTS quad_tracks(source TEXT, game_id INT, map TEXT, ts TEXT, spawn_t INT, first INT, name TEXT, team TEXT,
                   took INT, contested INT, died_pre INT, enter_before_ms INT, frags INT, track TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS quad_tracks_done(source TEXT, game_id INT, note TEXT, PRIMARY KEY(source, game_id))")
    done = {r[0] for r in con.execute("SELECT game_id FROM quad_tracks_done WHERE source=?", (source,))}
    games = [g for g in json.load(open(manifest)) if g.get('demo_sha256') and (not mapf or g.get('map') == mapf) and g['id'] not in done]
    games = sorted(games, key=lambda g: -g['id'])[:limit]
    meta = {g['id']: (g.get('map'), g.get('timestamp')) for g in games}
    print(f'{source}: todo {len(games)} games', flush=True); t0 = time.time(); n = 0; errs = 0
    with Pool(workers) as pool:
        for res in pool.imap_unordered(process, games, chunksize=1):
            n += 1; gid = res['id']; mp, ts = meta[gid]
            if 'error' in res:
                errs += 1; con.execute("INSERT OR REPLACE INTO quad_tracks_done VALUES (?,?,?)", (source, gid, res['error'])); print('ERR', gid, res['error'], flush=True)
            else:
                con.executemany("INSERT INTO quad_tracks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                [(source, r[0], mp, ts, *r[1:]) for r in res['rows']])
                con.execute("INSERT OR REPLACE INTO quad_tracks_done VALUES (?,?,?)", (source, gid, res.get('note')))
            if n % 10 == 0:
                con.commit(); print(f'{n}/{len(games)} {errs} errors {time.time()-t0:.0f}s ({(time.time()-t0)/n:.1f}s/game)', flush=True)
    con.commit(); print(f'FINISHED {n} {errs} errors {time.time()-t0:.0f}s', flush=True)

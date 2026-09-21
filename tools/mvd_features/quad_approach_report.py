"""Per-map quad playbook numbers from `quad_approach` (quad_approach_pass.py).

For each map: cluster where contesters were 5 s before the spawn into approaches (k-means on
x/y/z, k per map), name them by the nearest map items, and report per approach: share of
contests, conversion (takes / contests), the taker's stack, how early takers get within 650 u.
Then the things that decide the quad regardless of approach: conversion by stack at -2 s, by
distance at -2 s, and how often the closest / most-stacked contester is the one who takes it.

Usage: quad_approach_report.py [--json out.json] [--names names.json]
  names.json = {map: {cluster_index: "name"}} to label clusters after a first look.
"""
import sqlite3, sys, json, statistics as st, math
import numpy as np
from sklearn.cluster import KMeans

DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
K = {'dm3': 5, 'dm2': 6, 'e1m2': 4, 'schloss': 4}
con = sqlite3.connect(DB, timeout=120)
names = json.load(open(sys.argv[sys.argv.index('--names') + 1])) if '--names' in sys.argv else {}
out_json = sys.argv[sys.argv.index('--json') + 1] if '--json' in sys.argv else None
items = {}
for mp, kind, x, y, z in con.execute("SELECT map, kind, x, y, z FROM map_items_xyz"):
    items.setdefault(mp, []).append((kind, x, y, z))

def nearest_items(mp, p, n=3):
    L = sorted(((math.dist(p, (x, y, z)), kind) for kind, x, y, z in items.get(mp, [])))[:n]
    return ", ".join(f"{k}@{int(d)}" for d, k in L)

def bucket_conv(rows, key, edges, labels):
    out = []
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        sel = [r for r in rows if r[key] is not None and lo <= r[key] < hi]
        if sel: out.append({"bucket": lab, "n": len(sel), "conv": round(100 * sum(r['took'] for r in sel) / len(sel), 1)})
    return out

report = {}
for mp in ('dm3', 'dm2', 'e1m2', 'schloss'):
    cur = con.execute("""SELECT q.game_id, q.spawn_t, q.name, q.took, q.died_pre, q.d5, q.x5, q.y5, q.z5, q.d2, q.x2, q.y2, q.z2, q.eff, q.enter_before_ms, q.alive0, q.d0
                         FROM quad_approach q JOIN games g ON g.id=q.game_id WHERE g.map=? AND q.contested=1 AND q.first=0""", (mp,))
    cols = [c[0] for c in cur.description]; rows = [dict(zip(cols, r)) for r in cur]
    if len(rows) < 200:
        print(f"{mp}: only {len(rows)} contested rows, skipping"); continue
    quad = next(((x, y, z) for k, x, y, z in items.get(mp, []) if k == 'quad'), None)
    # approach = where you were 5 s out (fall back to 2 s out if you spawned in between)
    pts = []; keep = []
    for r in rows:
        p = (r['x5'], r['y5'], r['z5']) if r['x5'] is not None else (r['x2'], r['y2'], r['z2'])
        if p[0] is None: continue
        pts.append(p); keep.append(r)
    X = np.array(pts, dtype=float)
    km = KMeans(n_clusters=K[mp], n_init=10, random_state=0).fit(X)
    lab = km.labels_
    clusters = []
    for c in range(K[mp]):
        sel = [r for r, l in zip(keep, lab) if l == c]
        cen = km.cluster_centers_[c]; dq = math.dist(cen, quad) if quad else None
        takers = [r for r in sel if r['took']]
        clusters.append({
            "idx": c, "name": names.get(mp, {}).get(str(c)), "n": len(sel), "share": round(100 * len(sel) / len(keep), 1),
            "conv": round(100 * len(takers) / len(sel), 1) if sel else None,
            "taker_eff": round(st.median([r['eff'] for r in takers if r['eff'] is not None])) if takers else None,
            "other_eff": round(st.median([r['eff'] for r in sel if not r['took'] and r['eff'] is not None])) if sel else None,
            "died_pre_pct": round(100 * sum(r['died_pre'] for r in sel) / len(sel), 1) if sel else None,
            "taker_enter_s": round(st.median([r['enter_before_ms'] for r in takers if r['enter_before_ms'] is not None]) / 1000, 1) if takers else None,
            "centroid": [round(float(v)) for v in cen], "dist_to_quad": round(dq) if dq else None, "near": nearest_items(mp, cen),
        })
    clusters.sort(key=lambda c: -c['n'])
    # approach by NAMED SPOT: the KTX location the player stood in ~5 s before the spawn (player_state10s
    # samples every 10 s; take the nearest sample within 5 s). Players' own vocabulary, no clustering needed.
    locs = {}
    for gid, t, nm, loc in con.execute("""SELECT s.game_id, s.t, s.name, s.loc FROM player_state10s s JOIN games g ON g.id=s.game_id
                                           WHERE g.map=? AND s.alive=1 AND s.loc IS NOT NULL""", (mp,)):
        locs.setdefault((gid, nm), []).append((t, loc))
    for v in locs.values(): v.sort()
    import bisect as _b
    def loc_at(gid, nm, t):
        L = locs.get((gid, nm))
        if not L: return None
        ts = [x[0] for x in L]; i = _b.bisect_left(ts, t)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(L) and abs(L[j][0] - t) <= 5000 and (best is None or abs(L[j][0] - t) < abs(best[0] - t)): best = L[j]
        return best[1] if best else None
    by_loc = {}
    for r in keep:
        lc = loc_at(r['game_id'], r['name'], r['spawn_t'] - 5000)
        if lc: by_loc.setdefault(lc, []).append(r)
    spots = []
    for lc, sel in by_loc.items():
        tk = [r for r in sel if r['took']]
        spots.append({"loc": lc, "n": len(sel), "share": round(100 * len(sel) / max(1, sum(len(v) for v in by_loc.values())), 1),
                      "conv": round(100 * len(tk) / len(sel), 1),
                      "taker_eff": round(st.median([r['eff'] for r in tk if r['eff'] is not None])) if tk else None,
                      "died_pre_pct": round(100 * sum(r['died_pre'] for r in sel) / len(sel), 1),
                      "taker_enter_s": round(st.median([r['enter_before_ms'] for r in tk if r['enter_before_ms'] is not None]) / 1000, 1) if tk else None})
    spots.sort(key=lambda x: -x['n'])
    # what decides it, regardless of approach
    by_eff = bucket_conv(keep, 'eff', [0, 100, 150, 250, 10000], ['<100 (naked)', '100-149', '150-249', '250+'])
    by_d2 = bucket_conv(keep, 'd2', [0, 150, 300, 450, 651], ['<150 u', '150-300', '300-450', '450-650'])
    # per spawn: did the closest at -2 s / the most stacked take it?
    spawns = {}
    for r in keep: spawns.setdefault((r['game_id'], r['spawn_t']), []).append(r)
    closest_wins = stacked_wins = n_sp = 0
    for k, sel in spawns.items():
        tk = [r for r in sel if r['took']]
        if not tk or len(sel) < 2: continue
        n_sp += 1
        c2 = [r for r in sel if r['d2'] is not None]; e2 = [r for r in sel if r['eff'] is not None]
        if c2 and min(c2, key=lambda r: r['d2'])['took']: closest_wins += 1
        if e2 and max(e2, key=lambda r: r['eff'])['took']: stacked_wins += 1
    report[mp] = {"contests": len(keep), "spawns_contested_by_2plus": n_sp,
                  "closest_at_minus2_takes_pct": round(100 * closest_wins / n_sp, 1) if n_sp else None,
                  "most_stacked_takes_pct": round(100 * stacked_wins / n_sp, 1) if n_sp else None,
                  "by_eff": by_eff, "by_d2": by_d2, "approaches": clusters, "spots": spots}
    print(f"\n=== {mp}: {len(keep)} contests, {n_sp} spawns with 2+ contesters · closest@-2s takes {report[mp]['closest_at_minus2_takes_pct']}% · most stacked takes {report[mp]['most_stacked_takes_pct']}%")
    print("  by stack @-2s:", "  ".join(f"{b['bucket']} {b['conv']}% (n={b['n']})" for b in by_eff))
    print("  by dist  @-2s:", "  ".join(f"{b['bucket']} {b['conv']}% (n={b['n']})" for b in by_d2))
    for sp_ in spots[:12]:
        print(f"  spot {sp_['loc']:16s} n={sp_['n']:5d} share={sp_['share']:5.1f}% conv={sp_['conv']:5.1f}% taker_eff={sp_['taker_eff']} died_pre={sp_['died_pre_pct']}% enter={sp_['taker_enter_s']}s")
    for c in clusters:
        print(f"  [{c['idx']}] {c['name'] or '?':22s} n={c['n']:5d} share={c['share']:5.1f}% conv={c['conv']:5.1f}% taker_eff={c['taker_eff']} other_eff={c['other_eff']} died_pre={c['died_pre_pct']}% enter={c['taker_enter_s']}s  centroid={c['centroid']} dq={c['dist_to_quad']}  near: {c['near']}")
if out_json:
    json.dump(report, open(out_json, 'w'), indent=1); print('wrote', out_json)

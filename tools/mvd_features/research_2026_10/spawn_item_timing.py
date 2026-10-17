"""First move off a spawn vs the item timers at that second (60 one-second games).
For each (map, spawn point) and each key item within 900 u of it: at the spawn second the item is 'up', 'in 1-8 s',
'in 9-20 s' or '20 s+ away'. Outcomes: took that item inside 20 s, died inside 14 s, stayed in the spawn area."""
import json, glob, collections, math, bisect, sys
sys.path.insert(0, '.')
from spawn_defs import SP, spawn_label
KEY = ('rl', 'lg', 'ya', 'ra', 'mh', 'quad')
def dist(a, b): return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
rows = collections.defaultdict(list)   # (map, spawn, item key) -> list of dict
for f in sorted(glob.glob('compact_*.json')):
    d = json.load(open(f)); mp = 'dm3' if d['map'] == 'The Abandoned Base' else d['map']
    if mp not in SP: continue
    locs = d['locs']; end = d['end']
    # items with phases sorted
    items = [it for it in d['items'] if it['kind'] in KEY]
    for it in items: it['_ph'] = sorted((ph for ph in it['phases'] if ph.get('from') is not None), key=lambda p: p['from'])
    # lock margin per second (same as spawn_points.py)
    tm = list(d['teams']); N = end // 1000 + 1; M = {}
    for s in range(N):
        st = {t: 0 for t in tm}; rl = {t: 0 for t in tm}
        for n, p in d['P'].items():
            if s < len(p['alive']) and p['alive'][s]: st[p['team']] += p['eff'][s]; rl[p['team']] += p['rl'][s]
        for t in tm:
            o = [x for x in tm if x != t][0]; M[(t, s)] = (st[o] - st[t]) + 100 * (rl[o] - rl[t])
    THR = {'dm3': 386, 'dm2': 400, 'e1m2': 234, 'schloss': 375}[mp]
    for n, p in d['P'].items():
        for s0, nd, tr in p['tracks']:
            if not tr: continue
            k, x, y, z, li = tr[0]; lab = spawn_label(mp, x, y, z)
            if lab == 'other': continue
            sp_xyz = next(s_[1:] for s_ in SP[mp] if s_[0] == lab)
            ent = next(((t, locs[l] if l < len(locs) else '?') for t, l, at in p['entries'] if s0 + 300 < t < nd), None)
            chained = (nd - s0) < 14000; locked = M.get((p['team'], s0 // 1000), 0) >= THR
            for it in items:
                if dist(sp_xyz, (it['x'], it['y'], it['z'])) > 900: continue
                ph = it['_ph']
                # state at s0
                cur = next((q for q in ph if q['from'] <= s0 and (q.get('takenAt') is None or q['takenAt'] > s0)), None)
                if cur: ttu = 0
                else:
                    nxt = next((q for q in ph if q['from'] > s0), None)
                    if not nxt: continue
                    ttu = (nxt['from'] - s0) / 1000
                took = any(q.get('takenBy') == n and q.get('takenAt') is not None and s0 <= q['takenAt'] <= s0 + 20000 for q in ph)
                b = 'up' if ttu == 0 else '1-8 s' if ttu <= 8 else '9-20 s' if ttu <= 20 else '20 s+'
                rows[(mp, lab, f"{it['kind']}@{it['loc']}")].append(dict(b=b, took=took, chained=chained, stayed=ent is None, locked=locked, life=(nd - s0) / 1000))
pct = lambda L: f"{100*sum(L)/len(L):3.0f}%" if L else '  - '
order = ['up', '1-8 s', '9-20 s', '20 s+']
for (mp, lab, item), L in sorted(rows.items()):
    if len(L) < 150: continue
    print(f"\n{mp} · {lab} spawn · {item}  (n={len(L)})")
    print(f"  {'item at spawn':<10} {'n':>5} {'took<=20s':>10} {'died<14s':>9} {'stayed':>7} | stayed: died {'':>3} | left: died")
    for b in order:
        S = [r for r in L if r['b'] == b]
        if len(S) < 30: continue
        st = [r for r in S if r['stayed']]; lf = [r for r in S if not r['stayed']]
        print(f"  {b:<10} {len(S):>5} {pct([r['took'] for r in S]):>10} {pct([r['chained'] for r in S]):>9} {pct([r['stayed'] for r in S]):>7} | {pct([r['chained'] for r in st]):>12} | {pct([r['chained'] for r in lf]):>9}   (took if stayed {pct([r['took'] for r in st])}, if left {pct([r['took'] for r in lf])})")

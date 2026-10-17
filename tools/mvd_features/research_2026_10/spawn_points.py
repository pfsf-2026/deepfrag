"""Survival by REAL spawn point (not 'area at the first 10 s tick'), from the 60 one-second games (compact_*.json).
Lock margin from per-second data: M = (enemy alive stack - own) + 100*(enemy alive RLs - own); locked = M >= per-map 85th pct."""
import json, glob, collections, sys, bisect
sys.path.insert(0, '.')
from select_games import canon, TOP, FIELD
from spawn_defs import SP, spawn_label
games = []
for f in sorted(glob.glob('compact_*.json')):
    d = json.load(open(f)); mp = 'dm3' if d['map'] == 'The Abandoned Base' else d['map']
    if mp not in SP: continue
    d['map'] = mp; games.append(d)
# lock margin per (game, team, second)
M = {}
for d in games:
    N = d['end'] // 1000 + 1
    tm = list(d['teams'])
    for s in range(N):
        stack = {t: 0 for t in tm}; rls = {t: 0 for t in tm}
        for n, p in d['P'].items():
            if s < len(p['alive']) and p['alive'][s]:
                stack[p['team']] += p['eff'][s]; rls[p['team']] += p['rl'][s]
        for t in tm:
            o = [x for x in tm if x != t][0]
            M[(d['gid'], t, s)] = (stack[o] - stack[t]) + 100 * (rls[o] - rls[t])
THR = {}
for mp in SP:
    v = sorted(m for (g, t, s), m in M.items() if next(x['map'] for x in games if x['gid'] == g) == mp)
    THR[mp] = v[int(len(v) * 0.85)] if v else 0
print('lock thresholds', THR)
lives = collections.defaultdict(list)
for d in games:
    mp = d['map']; locs = d['locs']
    for n, p in d['P'].items():
        grp = 'TOP' if p['canon'] in TOP else 'FIELD' if p['canon'] in FIELD else 'other'
        taken = sorted((ph['takenAt'], it['kind']) for it in d['items'] for ph in it['phases'] if ph.get('takenBy') == n and ph.get('takenAt') is not None)
        dealt = sorted((e['time'], e['damage']) for e in d['dmg'] if e['attacker'] == n and e['victim'] in d['P'] and d['P'][e['victim']]['team'] != p['team'])
        dt = [t for t, _ in dealt]
        for s0, nd, tr in p['tracks']:
            if not tr: continue
            k, x, y, z, li = tr[0]
            lab = spawn_label(mp, x, y, z)
            m = M.get((d['gid'], p['team'], s0 // 1000))
            if m is None: continue
            life = nd - s0
            # first room entry after the spawn (before death); 'stayed' if none
            ent = next(((t, locs[l] if l < len(locs) else '?') for t, l, at in p['entries'] if s0 + 300 < t < nd), None)
            item = next((kd for t, kd in taken if s0 <= t <= s0 + 14000), None)
            dmg = sum(dm for t, dm in dealt[bisect.bisect_left(dt, s0):bisect.bisect_right(dt, nd)])
            lives[mp].append(dict(sp=lab, locked=m >= THR[mp], M=m, chained=life < 14000, life=life / 1000, grp=grp, name=p['canon'],
                                  dest=ent[1] if ent else 'stayed', dest_dt=(ent[0] - s0) / 1000 if ent else None, item=item, dmg=dmg,
                                  loc5=(locs[tr[50][4]] if len(tr) > 50 and tr[50][4] < len(locs) else None)))
pct = lambda L: f"{100*sum(L)/len(L):3.0f}% (n={len(L)})" if L else '  -  '
for mp in SP:
    L = lives[mp]; lk = [l for l in L if l['locked']]; fr = [l for l in L if not l['locked']]
    print(f"\n=== {mp}: {len(L)} spawns in {sum(1 for d in games if d['map']==mp)} games; locked {100*len(lk)/len(L):.0f}% of spawns; chained locked {pct([l['chained'] for l in lk])} vs free {pct([l['chained'] for l in fr])}")
    print(f"  {'spawn point':<16} {'n':>5} {'chained all':>14} {'chained locked':>17} {'TOP lk':>14} {'FIELD lk':>14} {'item<=14s lk':>14} {'dmg/lk spawn':>12}")
    for lab, *_ in SP[mp] + [('other', 0, 0, 0)]:
        S = [l for l in L if l['sp'] == lab]
        if not S: continue
        Sl = [l for l in S if l['locked']]
        print(f"  {lab:<16} {len(S):>5} {pct([l['chained'] for l in S]):>14} {pct([l['chained'] for l in Sl]):>17} {pct([l['chained'] for l in Sl if l['grp']=='TOP']):>14} {pct([l['chained'] for l in Sl if l['grp']=='FIELD']):>14} {pct([l['item'] is not None for l in Sl]):>14} {sum(l['dmg'] for l in Sl)/max(1,len(Sl)):>12.0f}")
    print("  under lock, by spawn point -> first room entered (survival to 14 s; 'stayed' = never left the spawn area), cells with n>=25:")
    for lab, *_ in SP[mp]:
        Sl = [l for l in L if l['sp'] == lab and l['locked']]
        by = collections.defaultdict(list)
        for l in Sl: by[l['dest']].append(l['chained'])
        rows = sorted(((k, v) for k, v in by.items() if len(v) >= 25), key=lambda kv: sum(kv[1]) / len(kv[1]))
        if rows: print(f"    {lab:<16} " + ' | '.join(f"{k} {100*(1-sum(v)/len(v)):.0f}% ({len(v)})" for k, v in rows))
json.dump({mp: lives[mp] for mp in SP}, open('spawn_points_out.json', 'w'))

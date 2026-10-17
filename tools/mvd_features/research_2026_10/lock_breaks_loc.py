"""Out of control: what players who survive their spawn under a lock do differently, per map, and what breaks a lock.
Data: data/mvd_features.sqlite (4on4 games since 2025 on dm3/dm2/e1m2/schloss).
Lock margin for team T at a 10 s sample: M = (enemy stack - own stack) + 100*(enemy RLs - own RLs) + 100*(enemy RAs - own RAs).
A spawn is 'under lock' when M >= THR at the sample it falls in. A life is chained if it ends inside 14 s."""
import sqlite3, collections, statistics, sys
DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
MAPS = ['dm3', 'dm2', 'e1m2', 'schloss']
PCT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.85
THR_BY_MAP = {}
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
gids = {r['id']: r['map'] for r in con.execute("SELECT id, map FROM games WHERE mode='4on4' AND map IN ('dm3','dm2','e1m2','schloss') AND ts >= '2025-01-01' AND n_players = 8")}
print(len(gids), 'games')
ids = tuple(gids)
q = lambda sql: con.execute(sql.replace('IDS', ','.join('?' * len(ids))), ids)
state = collections.defaultdict(dict)          # (gid, team) -> {t: row}
for r in q("SELECT * FROM state10s WHERE game_id IN (IDS)"):
    state[(r['game_id'], r['team'])][r['t']] = dict(r)
ps = collections.defaultdict(dict)             # (gid, name) -> {t: row}
teams_of = {}
for r in q("SELECT game_id, t, name, team, alive, eff, rl, lg, loc FROM player_state10s WHERE game_id IN (IDS)"):
    ps[(r['game_id'], r['name'])][r['t']] = dict(r); teams_of[(r['game_id'], r['name'])] = r['team']
takes = collections.defaultdict(list)          # (gid, name) -> [(t, kind, loc)]
for r in q("SELECT game_id, t, name, kind, loc FROM item_takes WHERE game_id IN (IDS) AND kind IN ('ra','ya','ga','mh','rl','lg','quad','pent','ring','gl','sng')"):
    takes[(r['game_id'], r['name'])].append((r['t'], r['kind'], r['loc']))
for v in takes.values(): v.sort()
print('loaded state, player state, takes')
# per-map lock threshold = PCT quantile of the margin over all samples on that map
_m = collections.defaultdict(list)
for (g, tm), rows in state.items():
    other = next((t2 for (g2, t2) in state if g2 == g and t2 != tm), None)
    if not other: continue
    for t, r in rows.items():
        o = state[(g, other)].get(t)
        if o: _m[gids[g]].append((o['stack_sum'] - r['stack_sum']) + 100 * (o['rl_n'] - r['rl_n']) + 100 * (o['ra_n'] - r['ra_n']))
for mp, v in _m.items():
    v.sort(); THR_BY_MAP[mp] = v[int(len(v) * PCT)]
print('lock thresholds (margin at the', PCT, 'quantile):', THR_BY_MAP)

def margin(gid, team, t):
    s = state.get((gid, team), {}); ts = (t // 10000) * 10000
    mine = s.get(ts); other_team = next((tm for (g, tm) in state if g == gid and tm != team), None)
    theirs = state.get((gid, other_team), {}).get(ts) if other_team else None
    if not mine or not theirs: return None
    return (theirs['stack_sum'] - mine['stack_sum']) + 100 * (theirs['rl_n'] - mine['rl_n']) + 100 * (theirs['ra_n'] - mine['ra_n'])

# per map accumulators
lives = collections.defaultdict(list)   # map -> list of dict(life)
breaks = collections.defaultdict(collections.Counter)
margins = collections.defaultdict(list)
episodes = collections.defaultdict(list)
for gid, mp in gids.items():
    deaths = collections.defaultdict(list)   # name -> [(t, tss, killer, killer_team)]
    frags = []
    for r in con.execute("SELECT t, att, vic, vic_tss, vic_eff, weapon FROM events WHERE game_id=? AND kind='frag' AND t > 0 ORDER BY t", (gid,)):
        deaths[r['vic']].append((r['t'], r['vic_tss'] or 0, r['att'], teams_of.get((gid, r['att']))))
        frags.append(dict(r))
    dmg_by = collections.defaultdict(list)
    for r in con.execute("SELECT t, att, vic, dmg FROM events WHERE game_id=? AND kind='dmg' AND t > 0", (gid,)):
        dmg_by[r['att']].append((r['t'], r['dmg']))
    for name, ds in deaths.items():
        team = teams_of.get((gid, name))
        if not team: continue
        for i in range(1, len(ds)):
            t_prev = ds[i - 1][0]; t_this, tss = ds[i][0], ds[i][1]
            spawn = t_this - tss
            if spawn <= t_prev: continue           # tss missing / inconsistent
            dead_wait = (spawn - t_prev) / 1000
            M = margin(gid, team, spawn)
            if M is None: continue
            THR = THR_BY_MAP[mp]
            margins[mp].append(M)
            chained = tss < 14000
            s10 = ps.get((gid, name), {}).get(((spawn // 10000) + 1) * 10000)
            first_take = next(((t, k, l) for (t, k, l) in takes.get((gid, name), []) if spawn <= t <= spawn + 14000), None)
            dealt = sum(d for (t, d) in dmg_by.get(name, []) if spawn <= t <= t_this)
            mates_same_loc = None
            if s10:
                mates_same_loc = sum(1 for (g, n), st in ps.items() if g == gid and n != name and teams_of.get((g, n)) == team and st.get(s10['t'], {}).get('alive') and st[s10['t']].get('loc') == s10['loc'])
            lives[mp].append({'locked': M >= THR, 'M': M, 'chained': chained, 'life_s': tss / 1000, 'wait': dead_wait,
                              'loc10': s10['loc'] if s10 else None, 'rl10': bool(s10 and s10['rl']), 'eff10': s10['eff'] if s10 else None,
                              'first_kind': first_take[1] if first_take else None, 'first_loc': first_take[2] if first_take else None,
                              'first_dt': (first_take[0] - spawn) / 1000 if first_take else None, 'dealt': dealt, 'mates10': mates_same_loc})
    # lock episodes and what ended them
    THR = THR_BY_MAP[mp]
    def concentration(team, t):
        # alive players of `team` at sample t: how many share the most-populated area (1..4)
        locs = [st[t]['loc'] for (g, n), st in ps.items() if g == gid and teams_of.get((g, n)) == team and st.get(t, {}).get('alive') and st[t].get('loc')]
        return max(collections.Counter(locs).values()) if locs else 0
    for team in {tm for (g, tm) in state if g == gid}:
        ts_sorted = sorted(state[(gid, team)])
        in_lock = None; conc = []
        for t in ts_sorted:
            M = margin(gid, team, t)
            if M is None: continue
            if in_lock is not None: conc.append(concentration(team, t))
            if M >= THR and in_lock is None: in_lock = t; conc = []
            elif in_lock is not None and M < THR // 2:
                if t - in_lock >= 30000:
                    w0, w1 = t - 30000, t
                    tk = [k for (g, n), lst in takes.items() if g == gid and teams_of.get((g, n)) == team for (tt, k, l) in lst if w0 <= tt <= w1]
                    tkl = {(k, l) for (g, n), lst in takes.items() if g == gid and teams_of.get((g, n)) == team for (tt, k, l) in lst if w0 <= tt <= w1 and k in ('mh', 'ra', 'ya', 'quad', 'rl')}
                    for (k, l) in tkl: breaks[mp][f'@took {k} {l}'] += 1
                    fr = [f for f in frags if w0 <= f['t'] <= w1 and teams_of.get((gid, f['att'])) == team and teams_of.get((gid, f['vic'])) not in (None, team)]
                    trig = []
                    if 'quad' in tk: trig.append('took quad')
                    if 'pent' in tk: trig.append('took pent')
                    if 'ra' in tk: trig.append('took RA')
                    if 'mh' in tk: trig.append('took mega')
                    if any((f['vic_eff'] or 0) >= 150 for f in fr): trig.append('killed a stacked enemy')
                    if sum(1 for f in fr if (f['vic_tss'] or 99999) < 6000) >= 2: trig.append('2+ spawn frags')
                    if len(fr) >= 3: trig.append('3+ frags in 30 s')
                    if not trig: trig.append('no clear trigger')
                    for x in trig: breaks[mp][x] += 1
                    breaks[mp]['_episodes'] += 1
                    episodes[mp].append({'len_s': (t - in_lock) / 1000, 'conc': sum(conc) / len(conc) if conc else None})
                in_lock = None
            elif in_lock is not None and t == ts_sorted[-1] and t - in_lock >= 30000:
                episodes[mp].append({'len_s': (t - in_lock) / 1000, 'conc': sum(conc) / len(conc) if conc else None, 'unbroken': True})

def pct(v): return f"{100 * sum(v) / len(v):.0f}%" if v else '—'
for mp in MAPS:
    L = lives[mp]; ms = sorted(margins[mp])
    if not L: continue
    locked = [l for l in L if l['locked']]; free = [l for l in L if not l['locked']]
    print(f"\n=== {mp}: {len(L)} spawns in {sum(1 for g in gids.values() if g == mp)} games | margin quartiles {ms[len(ms)//4]:.0f} / {ms[len(ms)//2]:.0f} / {ms[3*len(ms)//4]:.0f} | locked (M>={THR_BY_MAP[mp]}): {100*len(locked)/len(L):.0f}% of spawns")
    print(f"  chained-death rate: locked {pct([l['chained'] for l in locked])}  vs  not locked {pct([l['chained'] for l in free])}   | spawn-killed (<6 s): {pct([l['life_s']<6 for l in locked])} vs {pct([l['life_s']<6 for l in free])}")
    surv = [l for l in locked if not l['chained']]; dead = [l for l in locked if l['chained']]
    print(f"  under lock, survivors ({len(surv)}) vs chained ({len(dead)}):")
    print(f"    waited before respawn ≥3 s: {pct([l['wait']>=3 for l in surv])} vs {pct([l['wait']>=3 for l in dead])} | median wait {statistics.median([l['wait'] for l in surv]):.1f}s vs {statistics.median([l['wait'] for l in dead]):.1f}s")
    fk = lambda L_: collections.Counter(l['first_kind'] or 'nothing' for l in L_)
    def top(c, n=5): tot = sum(c.values()) or 1; return ', '.join(f"{k} {100*v/tot:.0f}%" for k, v in c.most_common(n))
    print(f"    first item inside 14 s — survivors: {top(fk(surv))}")
    print(f"                             chained:   {top(fk(dead))}")
    print(f"    had a teammate in the same area at +10 s: {pct([(l['mates10'] or 0) > 0 for l in surv if l['mates10'] is not None])} vs {pct([(l['mates10'] or 0) > 0 for l in dead if l['mates10'] is not None])}")
    print(f"    RL in hand at +10 s: {pct([l['rl10'] for l in surv if l['loc10']])} vs {pct([l['rl10'] for l in dead if l['loc10']])}")
    # where survivors are at +10 s vs where the chained died (first loc) — survival rate by area
    by_loc = collections.defaultdict(lambda: [0, 0])
    for l in locked:
        if l['loc10']: by_loc[l['loc10']][1] += 1; by_loc[l['loc10']][0] += 0 if l['chained'] else 1
    rows = sorted(((loc, s, n) for loc, (s, n) in by_loc.items() if n >= 40), key=lambda x: -x[1] / x[2])
    print("    area at +10 s after a locked spawn → share surviving to 14 s (areas with 40+ spawns):")
    for loc, s, n in rows[:6]: print(f"      {loc:<16} {100*s/n:3.0f}%  (n={n})")
    for loc, s, n in rows[-3:]: print(f"      {loc:<16} {100*s/n:3.0f}%  (n={n})  <- worst")
    E = [e for e in episodes[mp] if e['conc'] is not None]
    if E:
        E.sort(key=lambda e: e['conc'])
        lo, hi = E[:len(E)//3], E[-(len(E)//3):]
        med = lambda L_: statistics.median([e['len_s'] for e in L_])
        print(f"  flood test — locked team's concentration (how many of its alive players share one area, avg over the lock): spread (bottom third, avg {statistics.mean(e['conc'] for e in lo):.2f}) → median lock {med(lo):.0f} s, unbroken to match end {pct([e.get('unbroken', False) for e in lo])}; bunched (top third, avg {statistics.mean(e['conc'] for e in hi):.2f}) → median lock {med(hi):.0f} s, unbroken {pct([e.get('unbroken', False) for e in hi])}")
    b = breaks[mp]; ep = b.pop('_episodes', 0)
    print(f"  lock episodes (≥30 s) that ended: {ep} | what happened in the last 30 s before the break: " + ', '.join(f"{k} {100*v/max(1,ep):.0f}%" for k, v in b.most_common(8)))

print('\n=== item takes by LOCATION in the 30 s before a lock broke (share of broken episodes) ===')
for mp in MAPS:
    n = breaks[mp]['_episodes'] or 1
    rows = sorted(((k, v) for k, v in breaks[mp].items() if k.startswith('@')), key=lambda kv: -kv[1])
    print(mp, f'episodes={n}:', ', '.join(f"{k[6:]} {100*v/n:.0f}%" for k, v in rows[:14]))

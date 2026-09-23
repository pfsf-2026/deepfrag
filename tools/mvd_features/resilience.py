"""Resilience: does a player keep producing when his team is losing? (Peter, 2026-09-23)

Every game is cut into 10 s buckets. Each bucket is labelled by the player's OWN team's frag
deficit at that moment (state10s):
    deep   = 30 or more behind      behind = 10..29 behind
    even   = within 9               ahead  = 10 or more ahead
For every player we measure, per minute ALIVE in each state: damage dealt, kills, deaths, and
items (RA/YA/MH/quad). Everyone drops when deep behind (the other team is stacked, you are
spawning), so a player's "deep" rate is compared with his own "even" rate, and that ratio is
compared with the pool's ratio. Resilience 100 = holds up like the typical player; 120 = keeps
fighting; 80 = folds. Components: damage (weight .4), kills (.2), deaths inverted (.2), items (.2).
Also reported: the last-5-minutes-while-deep rate (the "already lost" tell), and the player's
game-to-game SD of above-average (for the balancer).

Writes `player_resilience` (canonical_id, games, min_even, min_deep, rates, ratios, score).
Usage: resilience.py [--days 365] [--min-deep-min 12]
"""
import sqlite3, sys, statistics as st, collections, datetime as dt, math

DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
DAYS = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 365
MIN_DEEP = float(sys.argv[sys.argv.index('--min-deep-min') + 1]) if '--min-deep-min' in sys.argv else 12.0
con = sqlite3.connect(DB, timeout=300)
cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DAYS)).isoformat()
STATES = ('deep', 'behind', 'even', 'ahead')
def state(d):
    return 'deep' if d <= -30 else 'behind' if d <= -10 else 'even' if d < 10 else 'ahead'

games = con.execute("select id from games where mode='4on4' and ts>=? order by id", (cut,)).fetchall()
print(f"{len(games)} fours in the last {DAYS} days")
# canonical ids
cid = {(g, n): c for g, n, c in con.execute("select game_id, name, cid from player_agi where cid is not null")}
agg = collections.defaultdict(lambda: collections.Counter())      # cid -> counters
per_game_aa = collections.defaultdict(list)
for g, c, aa in con.execute("select game_id, canonical_id, above_avg from player_war"):
    if aa is not None: per_game_aa[c].append(float(aa))
games_seen = collections.defaultdict(set)
for (gid,) in games:
    bs = {}   # (team, bucket) -> state ; bucket = t // 10000
    late = {}  # (team, bucket) -> True when time_left <= 5 min
    for team, t, d, tl in con.execute("select team, t, frag_diff, time_left from state10s where game_id=?", (gid,)):
        bs[(team, t // 10000)] = state(d); late[(team, t // 10000)] = (tl is not None and tl <= 300000)
    pteam = {n: tm for n, tm in con.execute("select name, team from players where game_id=?", (gid,))}
    # alive time per state (player_state10s: one row per player per 10 s)
    for n, t, alive in con.execute("select name, t, alive from player_state10s where game_id=?", (gid,)):
        c = cid.get((gid, n)); tm = pteam.get(n)
        if not c or tm is None or not alive: continue
        s = bs.get((tm, t // 10000))
        if not s: continue
        a = agg[c]; a[f'min_{s}'] += 10 / 60; games_seen[c].add(gid)
        if s == 'deep' and late.get((tm, t // 10000)): a['min_deep_late'] += 10 / 60
    # damage / kills / deaths per state
    for t, kind, att, vic, dmg, teamd, selfd in con.execute("select t, kind, att, vic, dmg_cap, teamd, selfd from events where game_id=?", (gid,)):
        b = t // 10000
        if att and not teamd and not selfd:
            c = cid.get((gid, att)); tm = pteam.get(att); s = bs.get((tm, b)) if tm else None
            if c and s:
                a = agg[c]; a[f'dmg_{s}'] += int(dmg or 0)
                if kind == 'frag': a[f'kills_{s}'] += 1
                if s == 'deep' and late.get((tm, b)):
                    a['dmg_deep_late'] += int(dmg or 0)
                    if kind == 'frag': a['kills_deep_late'] += 1
        if kind == 'frag' and vic:
            c = cid.get((gid, vic)); tm = pteam.get(vic); s = bs.get((tm, b)) if tm else None
            if c and s: agg[c][f'deaths_{s}'] += 1
    for n, t in con.execute("select name, t from item_takes where game_id=? and kind in ('ra','ya','mh','quad')", (gid,)):
        c = cid.get((gid, n)); tm = pteam.get(n); s = bs.get((tm, t // 10000)) if tm else None
        if c and s: agg[c][f'items_{s}'] += 1

def rates(a, s):
    m = a.get(f'min_{s}', 0)
    if m <= 0: return None
    return {'dmg': a.get(f'dmg_{s}', 0) / m, 'kills': a.get(f'kills_{s}', 0) / m, 'deaths': a.get(f'deaths_{s}', 0) / m, 'items': a.get(f'items_{s}', 0) / m, 'min': m}
rows = []
for c, a in agg.items():
    e, d = rates(a, 'even'), rates(a, 'deep')
    if not e or not d or e['min'] < 15 or d['min'] < MIN_DEEP: continue
    def ratio(k):
        return (d[k] / e[k]) if e[k] > 0 else None
    r = {k: ratio(k) for k in ('dmg', 'kills', 'deaths', 'items')}
    if any(v is None for v in r.values()): continue
    ml = a.get('min_deep_late', 0)
    late_dmg = (a.get('dmg_deep_late', 0) / ml / e['dmg']) if ml >= 5 and e['dmg'] > 0 else None
    aas = per_game_aa.get(c, [])
    rows.append({'cid': c, 'games': len(games_seen[c]), 'min_even': e['min'], 'min_deep': d['min'], 'min_deep_late': ml,
                 'even': e, 'deep': d, 'ratio': r, 'late_ratio': late_dmg,
                 'aa_mean': st.mean(aas) if aas else None, 'aa_sd': st.pstdev(aas) if len(aas) > 5 else None})
pool = {k: st.median(x['ratio'][k] for x in rows) for k in ('dmg', 'kills', 'deaths', 'items')}
pool_late = st.median(x['late_ratio'] for x in rows if x['late_ratio'] is not None)
print(f"\npool ({len(rows)} players with 15+ min even and {MIN_DEEP:.0f}+ min deep): when 30+ behind the typical player keeps "
      f"{100*pool['dmg']:.0f}% of his even damage rate, {100*pool['kills']:.0f}% of kills, {100*pool['items']:.0f}% of items, and dies {100*pool['deaths']:.0f}% as often; "
      f"in the last 5 minutes while deep: {100*pool_late:.0f}% of even damage")
W = {'dmg': .4, 'kills': .2, 'deaths': .2, 'items': .2}
for x in rows:
    r = x['ratio']
    comp = {'dmg': r['dmg'] / pool['dmg'], 'kills': r['kills'] / pool['kills'], 'deaths': pool['deaths'] / r['deaths'] if r['deaths'] > 0 else 1.0, 'items': r['items'] / pool['items'] if pool['items'] > 0 else 1.0}
    x['comp'] = comp
    x['score'] = 100 * math.exp(sum(W[k] * math.log(max(0.2, min(5.0, comp[k]))) for k in W))
    x['late_score'] = (100 * x['late_ratio'] / pool_late) if x['late_ratio'] is not None else None
con.execute("DROP TABLE IF EXISTS player_resilience")
con.execute("""CREATE TABLE player_resilience(canonical_id TEXT PRIMARY KEY, games INT, min_even REAL, min_deep REAL, min_deep_late REAL,
    dmg_even REAL, dmg_deep REAL, deaths_even REAL, deaths_deep REAL, kills_even REAL, kills_deep REAL, items_even REAL, items_deep REAL,
    r_dmg REAL, r_kills REAL, r_deaths REAL, r_items REAL, r_late REAL, score REAL, late_score REAL, aa_mean REAL, aa_sd REAL)""")
con.executemany("INSERT INTO player_resilience VALUES (" + ",".join("?" * 22) + ")",
                [(x['cid'], x['games'], x['min_even'], x['min_deep'], x['min_deep_late'], x['even']['dmg'], x['deep']['dmg'], x['even']['deaths'], x['deep']['deaths'],
                  x['even']['kills'], x['deep']['kills'], x['even']['items'], x['deep']['items'], x['ratio']['dmg'], x['ratio']['kills'], x['ratio']['deaths'], x['ratio']['items'],
                  x['late_ratio'], x['score'], x['late_score'], x['aa_mean'], x['aa_sd']) for x in rows])
con.commit()
rows.sort(key=lambda x: -x['score'])
print(f"\n{'player':18s} {'games':>5s} {'deep min':>8s} {'score':>5s} {'late':>5s} | {'dmg':>5s} {'kills':>5s} {'deaths':>6s} {'items':>5s} | {'dmg/min even->deep':>19s} {'deaths/min even->deep':>21s} | {'above avg':>9s} {'game SD':>7s}")
for x in rows:
    r = x['ratio']
    print(f"{x['cid'][:18]:18s} {x['games']:5d} {x['min_deep']:8.0f} {x['score']:5.0f} {(x['late_score'] or 0):5.0f} | {100*r['dmg']:4.0f}% {100*r['kills']:4.0f}% {100*r['deaths']:5.0f}% {100*r['items']:4.0f}% | {x['even']['dmg']:6.0f} -> {x['deep']['dmg']:5.0f}      {x['even']['deaths']:5.2f} -> {x['deep']['deaths']:5.2f}    | {x['aa_mean'] or 0:+9.1f} {x['aa_sd'] or 0:7.1f}")
# does resilience predict variance?
import numpy as np
xs = np.array([x['score'] for x in rows if x['aa_sd']]); ys = np.array([x['aa_sd'] for x in rows if x['aa_sd']]); zs = np.array([x['aa_mean'] for x in rows if x['aa_sd']])
print(f"\ncorrelation resilience vs game-to-game SD of above avg: r={np.corrcoef(xs, ys)[0,1]:+.2f} · vs mean above avg: r={np.corrcoef(xs, zs)[0,1]:+.2f}")

"""How much does ping change outcomes in NA fours? (Peter, 2026-09-23)

Pings come from the hub manifest (per player per game). Two views:
 1. Fight by fight: every pairwise fight that ended in a frag, with the stack edge at first
    contact (the fight table's input) plus the two players' pings. Logistic regression of
    "starter wins" on edge and ping difference; win rate by ping-gap bucket in even fights.
 2. Within player: a player's above-average per game, LG accuracy and RL connect against
    how far his ping in that game sat from his own usual ping (player fixed effects).
Usage: ping_effect.py MANIFEST [--since 2025-01-01]
"""
import sys, json, sqlite3, statistics as st, collections, math
import numpy as np
from sklearn.linear_model import LogisticRegression, LinearRegression

DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
man = json.load(open(sys.argv[1]))
ping = {}
for g in man:
    for p in g.get('players') or []:
        if p.get('ping') is not None and p['ping'] >= 8: ping[(g['id'], p['name'])] = p['ping']
con = sqlite3.connect(DB, timeout=300)
games = [r[0] for r in con.execute("select id from games where mode='4on4'")]
print(f"{len(games)} fours; pings for {len(ping)} player-games")
# skill control: each name's career mean above-average (via canonical id); usual ping per name
name_cid = {(g, n): c for g, n, c in con.execute("select game_id, name, cid from player_agi where cid is not null")}
aa_by_cid = collections.defaultdict(list)
for g, c, aa in con.execute("select game_id, canonical_id, above_avg from player_war"):
    if aa is not None: aa_by_cid[c].append(float(aa))
skill = {c: st.mean(v) for c, v in aa_by_cid.items() if len(v) >= 10}
usual = collections.defaultdict(list)
for (g, n), p in ping.items(): usual[n].append(p)
usual = {n: st.median(v) for n, v in usual.items() if len(v) >= 10}

# ── 1. fights ──────────────────────────────────────────────────────────────
X = []; y = []; even = collections.defaultdict(lambda: [0, 0])
for gid in games:
    ev = con.execute("SELECT t, kind, att, vic, att_eff, vic_eff FROM events WHERE game_id=? AND selfd=0 AND teamd=0 ORDER BY t", (gid,)).fetchall()
    cur = {}
    def close(pair):
        first, last_t, frag = cur.pop(pair)
        if not frag: return
        s, o = first[2], first[3]; edge = (first[4] or 0) - (first[5] or 0)
        ps, po = ping.get((gid, s)), ping.get((gid, o))
        if ps is None or po is None: return
        win = 1 if frag[2] == s else 0
        cs, co = name_cid.get((gid, s)), name_cid.get((gid, o))
        if cs not in skill or co not in skill or s not in usual or o not in usual: return
        X.append((edge, ps - po, skill[cs] - skill[co], (ps - usual[s]) - (po - usual[o]))); y.append(win)
        if abs(edge) < 60:
            d = ps - po; b = '<-75' if d < -75 else '-75..-30' if d < -30 else '-30..30' if d <= 30 else '30..75' if d <= 75 else '>75'
            even[b][0] += win; even[b][1] += 1
    for r in ev:
        pair = frozenset((r[2], r[3]))
        if pair in cur and r[0] - cur[pair][1] > 4000: close(pair)
        if pair not in cur: cur[pair] = [r, r[0], None]
        cur[pair][1] = r[0]
        if r[1] == 'frag' and cur[pair][2] is None: cur[pair][2] = r
    for pair in list(cur): close(pair)
X = np.array(X, float); y = np.array(y)
print(f"\nfights with an outcome and both pings: {len(y)}")
print("even fights (|stack edge| < 60), starter's win rate by (starter ping - opponent ping):")
for b in ('<-75', '-75..-30', '-30..30', '30..75', '>75'):
    w, n = even[b]; print(f"  {b:>9s} ms: {100*w/n:5.1f}%  (n={n})")
m0 = LogisticRegression(max_iter=500).fit(np.c_[X[:, 0] / 100, X[:, 1] / 50], y)
print(f"logistic, no skill control: per +100 stack edge {m0.coef_[0][0]:+.3f} logit · per +50 ms MORE ping than the opponent {m0.coef_[0][1]:+.3f} logit")
m = LogisticRegression(max_iter=500).fit(np.c_[X[:, 0] / 100, X[:, 1] / 50, X[:, 2] / 20], y)
b_edge, b_ping, b_skill = m.coef_[0]
print(f"logistic WITH skill control: per +100 stack edge {b_edge:+.3f} · per +50 ms more ping {b_ping:+.3f} · per +20 frags/game of skill edge {b_skill:+.3f}")
for gap in (-100, -50, 0, 50, 100):
    p = 1 / (1 + math.exp(-(m.intercept_[0] + b_ping * gap / 50)))
    print(f"  even stack, equal skill, ping gap {gap:+4d} ms -> starter wins {100*p:.1f}%")
print(f"  50 ms of ping is worth about {abs(b_ping / b_edge) * 100:.0f} stack points, or {abs(b_ping / b_skill) * 20:.1f} frags/game of skill")
m2 = LogisticRegression(max_iter=500).fit(np.c_[X[:, 0] / 100, X[:, 3] / 50, X[:, 2] / 20], y)
print(f"same model with ping measured against each player's USUAL ping: per +50 ms worse than usual (relative) {m2.coef_[0][1]:+.3f} logit")
# even fights, skill-matched (|skill gap| < 10), by ping gap
print("even fights, |skill gap| < 10 frags/game, starter win rate by ping gap:")
sel = (np.abs(X[:, 0]) < 60) & (np.abs(X[:, 2]) < 10)
for lo, hi, lab in ((-1000, -75, '<-75'), (-75, -30, '-75..-30'), (-30, 30, '-30..30'), (30, 75, '30..75'), (75, 1000, '>75')):
    k = sel & (X[:, 1] > lo) & (X[:, 1] <= hi)
    if k.sum(): print(f"  {lab:>9s} ms: {100*y[k].mean():5.1f}%  (n={k.sum()})")

# ── 2. within player ───────────────────────────────────────────────────────
rows = con.execute("""SELECT w.game_id, w.canonical_id, w.above_avg, a.name, g.map, s.cells_fired, s.lg_dmg, a.rl_connect_pct
                      FROM player_war w JOIN player_agi a ON a.game_id=w.game_id AND a.cid=w.canonical_id
                      JOIN games g ON g.id=w.game_id LEFT JOIN player_shots s ON s.game_id=a.game_id AND s.name=a.name
                      WHERE g.mode='4on4'""").fetchall()
byp = collections.defaultdict(list)
for gid, cid, aa, name, mp, cells, lgd, rlc in rows:
    p = ping.get((gid, name))
    if p is None or aa is None: continue
    lg = (lgd / 30.0) / cells if (cells and cells >= 50 and mp == 'dm3') else None
    byp[cid].append((p, float(aa), lg, rlc))
med = {c: st.median(p for p, *_ in v) for c, v in byp.items() if len(v) >= 20}
def fe(idx, label, scale=1.0, minn=20):
    xs = []; ys = []
    for c, v in byp.items():
        if c not in med: continue
        vv = [(t[0], t[1 + idx]) for t in v if t[1 + idx] is not None]
        if len(vv) < minn: continue
        my = st.mean(q for _, q in vv)
        for p, q in vv: xs.append(p - med[c]); ys.append((q - my) * scale)
    xs = np.array(xs); ys = np.array(ys)
    lr = LinearRegression().fit(xs[:, None], ys)
    r = np.corrcoef(xs, ys)[0, 1]
    print(f"  {label}: per +50 ms above the player's usual ping {50*lr.coef_[0]:+.2f} (r={r:+.3f}, n={len(xs)}, players={sum(1 for c in med)})")
    # buckets
    for lo, hi, lab in ((-1000, -30, '30+ ms better than usual'), (-30, -10, '10-30 better'), (-10, 10, 'usual'), (10, 30, '10-30 worse'), (30, 1000, '30+ worse')):
        sel = (xs > lo) & (xs <= hi)
        if sel.sum() >= 100: print(f"      {lab:26s} n={sel.sum():6d}  mean {ys[sel].mean():+.2f}")
print("\nwithin-player effect of ping (each player against his own usual ping):")
fe(0, "above average per game (frags)")
fe(1, "LG accuracy on dm3 (pct points)", scale=100.0)
fe(2, "RL connect % (pct points)")

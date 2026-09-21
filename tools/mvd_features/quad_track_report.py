"""Top-player quad study from `quad_tracks` (quad_track_pass.py): what the best players do in
the 20 s before a quad spawn on one map, versus everyone else in the same games.

Per player group: games, spawns seen, contested, takes, conversion, died-before rate; then for
takes / contested-but-missed / not-contested, at t = -20 -15 -10 -5 -2 0: where they stood (top
named spots), distance to the quad, stack, RL in hand, share already inside 650 u; the paths the
takes came by (distinct named spots -20..0, collapsed), the spot they entered the 650 u zone from,
how early they entered, and stack at the spawn. "pool" = every other player in the same games.

Usage: quad_track_report.py --map dm3 --players "BLooD_DoG,yeti,sane,chr1s" [--source na|eu] [--json out]
Player match = case-insensitive substring on the demo name; group by the given label.
"""
import sqlite3, sys, json, statistics as st
from collections import Counter, defaultdict

DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
args = sys.argv[1:]
def opt(k, default=None):
    return args[args.index(k) + 1] if k in args else default
MAP = opt('--map', 'dm3'); PLAYERS = [p.strip() for p in opt('--players', '').split(',') if p.strip()]; SOURCE = opt('--source'); OUT = opt('--json')
STEPS = [-20, -15, -10, -5, -2, 0]
con = sqlite3.connect(DB, timeout=120)
q = "SELECT source, game_id, spawn_t, first, name, team, took, contested, died_pre, enter_before_ms, track FROM quad_tracks WHERE map=? AND first=0"
params = [MAP]
if SOURCE: q += " AND source=?"; params.append(SOURCE)
rows = con.execute(q, params).fetchall()
print(f"{MAP}: {len(rows)} player-spawn rows from {len({r[1] for r in rows})} games ({SOURCE or 'all sources'})")

def label_for(name):
    n = name.lower()
    for p in PLAYERS:
        if p.lower() in n: return p
    return None

def at(track, s):
    i = s + 20
    return track[i] if 0 <= i < len(track) and track[i] else None

def summarize(sel, title):
    """sel: list of (row, track) for one group."""
    n = len(sel)
    if not n: print(f"  {title}: none"); return None
    out = {"n": n, "steps": {}}
    print(f"  {title} (n={n})")
    for s in STEPS:
        pts = [at(t, s) for _, t in sel]; alive = [p for p in pts if p and p['d'] is not None]
        if not alive: continue
        locs = Counter(p['loc'] or '?' for p in alive).most_common(4)
        d = st.median(p['d'] for p in alive); e = [p['eff'] for p in alive if p['eff'] is not None]
        rl = 100 * sum(p['rl'] for p in alive) / len(alive); inside = 100 * sum(1 for p in alive if p['d'] <= 650) / len(alive)
        out["steps"][s] = {"alive_pct": round(100 * len(alive) / n), "median_dist": round(d), "median_eff": round(st.median(e)) if e else None,
                           "rl_pct": round(rl), "inside650_pct": round(inside), "locs": [(l, round(100 * c / len(alive))) for l, c in locs]}
        print(f"    t{s:+3d}s  alive {out['steps'][s]['alive_pct']:3d}%  dist {round(d):5d}  stack {out['steps'][s]['median_eff'] or '-':>4}  RL {round(rl):3d}%  inside650 {round(inside):3d}%  at: " + ", ".join(f"{l} {pc}%" for l, pc in out['steps'][s]['locs']))
    return out

def paths(sel, k=8):
    c = Counter(); entry = Counter(); enter_s = []; eff0 = []; eff10 = []
    for r, t in sel:
        seq = []
        for p in t:
            if not p or not p['loc']: continue
            if not seq or seq[-1] != p['loc']: seq.append(p['loc'])
        c[" > ".join(seq[-5:])] += 1
        # entry spot: first sample inside 650 u
        first_in = next((p for p in t if p and p['d'] is not None and p['d'] <= 650), None)
        if first_in: entry[first_in['loc'] or '?'] += 1
        if r[9] is not None: enter_s.append(r[9] / 1000)
        p0 = at(t, 0); p10 = at(t, -10)
        if p0 and p0['eff'] is not None: eff0.append(p0['eff'])
        if p10 and p10['eff'] is not None: eff10.append(p10['eff'])
    return {"paths": c.most_common(k), "entry": entry.most_common(6),
            "enter_median_s": round(st.median(enter_s), 1) if enter_s else None,
            "enter_ge10_pct": round(100 * sum(1 for x in enter_s if x >= 10) / len(enter_s)) if enter_s else None,
            "enter_ge5_pct": round(100 * sum(1 for x in enter_s if x >= 5) / len(enter_s)) if enter_s else None,
            "eff0_median": round(st.median(eff0)) if eff0 else None, "eff10_median": round(st.median(eff10)) if eff10 else None}

groups = defaultdict(list); pool = []
for r in rows:
    lab = label_for(r[4]); tr = json.loads(r[10])
    (groups[lab] if lab else pool).append((r, tr))
report = {}
def block(label, sel):
    games = {(r[0], r[1]) for r, _ in sel}; spawns = len(sel)
    contested = [(r, t) for r, t in sel if r[7]]; took = [(r, t) for r, t in sel if r[6]]
    missed = [(r, t) for r, t in contested if not r[6]]; away = [(r, t) for r, t in sel if not r[7]]
    conv = 100 * len(took) / len(contested) if contested else 0
    print(f"\n=== {label}: {len(games)} games, {spawns} spawns seen, contested {len(contested)} ({100*len(contested)/spawns:.0f}%), took {len(took)} ({conv:.0f}% of contested, {100*len(took)/spawns:.0f}% of all), died before spawn {sum(r[8] for r,_ in sel)} ({100*sum(r[8] for r,_ in sel)/spawns:.0f}%)")
    rep = {"games": len(games), "spawns": spawns, "contested": len(contested), "took": len(took), "conv_pct": round(conv, 1),
           "take_pct_all": round(100 * len(took) / spawns, 1), "died_pre_pct": round(100 * sum(r[8] for r, _ in sel) / spawns, 1)}
    rep["takes"] = summarize(took, "TAKES: where he was before the quads he took")
    rep["missed"] = summarize(missed, "MISSED: contested but did not take")
    rep["away"] = summarize(away, "AWAY: not contesting")
    if took:
        pt = paths(took); rep["take_paths"] = pt
        print(f"  take paths (last 5 spots before the spawn): " + " | ".join(f"{p} ×{c}" for p, c in pt['paths'][:6]))
        print(f"  entered the 650 u zone from: " + ", ".join(f"{l} {c}" for l, c in pt['entry']) + f" · median {pt['enter_median_s']} s early · ≥10 s early {pt['enter_ge10_pct']}% · ≥5 s {pt['enter_ge5_pct']}% · stack at -10 s {pt['eff10_median']} / at spawn {pt['eff0_median']}")
    if missed:
        pm = paths(missed); rep["miss_paths"] = pm
        print(f"  missed: entered from " + ", ".join(f"{l} {c}" for l, c in pm['entry']) + f" · median {pm['enter_median_s']} s early · stack at -10 s {pm['eff10_median']} / at spawn {pm['eff0_median']}")
    return rep

for lab in PLAYERS:
    if groups.get(lab): report[lab] = block(lab, groups[lab])
    else: print(f"\n=== {lab}: no rows")
report["pool"] = block("POOL (everyone else in these games)", pool)
if OUT: json.dump(report, open(OUT, 'w'), indent=1); print("wrote", OUT)

"""Page-friendly summary of the top-player quad study for one map -> quadTopData.json.

Reads the JSON files written by quad_track_report.py --json (one per region) and writes, per
map, a list of player rows plus the region pools, for the "what the best players do" section of
/coach/quad/{map}. Usage:
  quad_top_extract.py MAP out.json na=/path/na.json eu=/path/eu.json
"""
import json, sys

MAP = sys.argv[1]; OUT = sys.argv[2]
files = dict(a.split('=', 1) for a in sys.argv[3:])
LABELS = {'BLooD_DoG': 'Blood Dog', 'chr1s': 'chris', 'Milton': 'milton', 'XantoM': 'xantom', 'ParadokS': 'paradoks', 'Javve': 'javve', 'Hto': 'hto', 'eKz': 'ekz', 'jOn': 'jon', 'bAs': 'bas', 'Anza': 'anza'}

def row(label, region, d):
    if not d or not d.get('takes'): return None
    tk = d['takes']['steps']; sp = d.get('splits') or {}; tp = d.get('take_paths') or {}
    def step(s, k): return (tk.get(str(s)) or tk.get(s) or {}).get(k)
    stack = sp.get('stack') or {}; rl = sp.get('rl_at_-5') or {}; arr = sp.get('arrival') or {}
    entries = sorted((sp.get('entry') or {}).items(), key=lambda kv: -kv[1][0])
    return {
        'player': LABELS.get(label, label), 'region': region, 'games': d['games'], 'spawns': d['spawns'],
        'contest_pct': round(100 * d['contested'] / d['spawns']), 'conv_pct': round(d['conv_pct']), 'take_pct_all': round(d['take_pct_all']),
        'takes_per_game': round(d['took'] / d['games'], 1), 'died_pre_pct': round(d['died_pre_pct']),
        'stack_m10': step(-10, 'median_eff'), 'stack_m5': step(-5, 'median_eff'), 'rl_m5': step(-5, 'rl_pct'), 'inside_m10': step(-10, 'inside650_pct'),
        'enter_median_s': tp.get('enter_median_s'), 'early10_pct': tp.get('enter_ge10_pct'),
        'conv_150': (stack.get('150+') or [None, None])[1], 'conv_naked': (stack.get('<150') or [None, None])[1],
        'stacked_share': round(100 * (stack.get('150+') or [0])[0] / max(1, (stack.get('150+') or [0])[0] + (stack.get('<150') or [0])[0])),
        'conv_rl': (rl.get('RL') or [None, None])[1], 'conv_norl': (rl.get('no RL') or [None, None])[1],
        'conv_early': (arr.get('>=10s') or [None, None])[1], 'conv_late': (arr.get('<5s') or [None, None])[1],
        'entries': [{'spot': k, 'n': v[0], 'conv': v[1]} for k, v in entries[:5]],
        'paths': [p for p, c in (tp.get('paths') or [])[:3]],
    }

out = {'players': [], 'pools': {}}
for region, path in files.items():
    rep = json.load(open(path))
    for label, d in rep.items():
        r = row(label, region.upper(), d)
        if not r: continue
        if label == 'pool': out['pools'][region.upper()] = r
        else: out['players'].append(r)
out['players'].sort(key=lambda r: -r['conv_pct'])
existing = {}
try: existing = json.load(open(OUT))
except Exception: pass
existing[MAP] = out
json.dump(existing, open(OUT, 'w'), indent=1)
print('wrote', OUT, 'players', [(r['player'], r['region'], r['games'], r['conv_pct']) for r in out['players']], 'pools', list(out['pools']))

"""Walk-forward backtest of the 4on4 rating engine with a +/- contribution term (Peter, 2026-09-23).

Reproduces rate.py's shipped team engine (PlackettLuce 4v4, continuous margin outcome, map
layer, contribution weighting) on the NA fours that have demos, and swaps the contribution
signal: damage share (shipped) vs the demo +/- (leverage-weighted, from player_agi), vs both.
Every game is predicted BEFORE it updates anything, from ratings built only on earlier games,
so the log-loss is honest. Scored games: no draw and all 8 players with >= MIN_PRIOR earlier
games in this set.

+/- contribution: expected_i = expected team margin (AMP*tanh(mean gap/SCALE)) * mu_i / sum(team mu);
resid_i = pm_i - expected_i, centred within the team (sum to zero, so the team's margin surprise
stays in the team score); contribution = CW * tanh(resid_i / NORM).

Usage: rating_backtest_4on4.py [--min-prior 10] [--json out.json]
"""
import sqlite3, sys, math, json, collections, statistics as st
sys.path.insert(0, '/Users/peteryeargin/Projects/qw-stats')
import rate as R

DB = '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
MIN_PRIOR = int(sys.argv[sys.argv.index('--min-prior') + 1]) if '--min-prior' in sys.argv else 10
OUT = sys.argv[sys.argv.index('--json') + 1] if '--json' in sys.argv else None
con = sqlite3.connect(DB, timeout=300)

# ── data: one row per (game, cid) ────────────────────────────────────────────
games = {}
for gid, ts, mp in con.execute("select id, ts, map from games where mode='4on4' order by ts, id"):
    games[gid] = {'ts': ts, 'map': mp, 'teams': collections.defaultdict(dict)}
for gid, name, cid, team, fr, dmg, pm, mins, agi in con.execute("select game_id, name, cid, team, frags, dmg, plus_minus, minutes, agi from player_agi where cid is not null"):
    g = games.get(gid)
    if not g: continue
    cur = g['teams'][team].get(cid)
    if cur is None or (mins or 0) > cur['min']:
        g['teams'][team][cid] = {'fr': fr or 0, 'dmg': dmg or 0, 'pm': float(pm or 0), 'min': mins or 0, 'agi': float(agi) if agi is not None else None}
matches = []
for gid, g in games.items():
    teams = [t for t in g['teams'].values() if len(t) == 4]
    if len(teams) != 2 or len(g['teams']) != 2: continue
    A, B = teams
    fa, fb = sum(p['fr'] for p in A.values()), sum(p['fr'] for p in B.values())
    matches.append((gid, g['ts'], g['map'], A, B, fa, fb))
matches.sort(key=lambda m: (m[1], m[0]))
print(f"{len(games)} fours, {len(matches)} with two full teams of 4 resolved players")

def run(cw_dmg=0.0, cw_pm=0.0, norm_pm=40.0, map_layer=True, label='', k_ind=0.0, min_prior=None, detail=False, quiet=False, trace=None, cw_agi=0.0, norm_agi=0.25):
    MP = min_prior or MIN_PRIOR
    keys = []; py = []; tr = []
    cache = {}; cells = {}; nprior = collections.Counter()
    ll = []; hits = []; brier = []
    for gid, ts, mp, A, B, fa, fb in matches:
        ids_a, ids_b = list(A), list(B)
        for c in ids_a + ids_b: cache.setdefault(c, (1500.0, 500.0))
        ra = [cache[c] for c in ids_a]; rb = [cache[c] for c in ids_b]
        # map-adjusted prediction (scored), exactly as rate.py forms it
        def eff(c):
            m, g = cache[c]
            if map_layer and mp:
                cell = cells.get((c, mp))
                if cell and cell['n']: m += R.team_map_delta(cell['rs'], cell['n'])
            return m, g
        ea = [eff(c) for c in ids_a]; eb = [eff(c) for c in ids_b]
        p = R.predict_team(ea, eb)
        scored = fa != fb and all(nprior[c] >= MP for c in ids_a + ids_b)
        if scored:
            y = 1.0 if fa > fb else 0.0; pc = min(1 - 1e-6, max(1e-6, p))
            ll.append(-(y * math.log(pc) + (1 - y) * math.log(1 - pc))); hits.append((p > 0.5) == (y == 1.0)); brier.append((p - y) ** 2); keys.append(gid); py.append((p, y))
        # map residuals
        if map_layer and mp and fa != fb:
            y = 1.0 if fa > fb else 0.0
            for c in ids_a:
                cell = cells.setdefault((c, mp), {'rs': 0.0, 'n': 0}); cell['rs'] += y - p; cell['n'] += 1
            for c in ids_b:
                cell = cells.setdefault((c, mp), {'rs': 0.0, 'n': 0}); cell['rs'] += (1 - y) - (1 - p); cell['n'] += 1
        # team outcome + contribution
        mean_a = sum(m for m, _ in ra) / 4; mean_b = sum(m for m, _ in rb) / 4
        s_team = R.team_outcome_score(mean_a, mean_b, fa, fb)
        exp_margin = R.TEAM_EXP_AMP * math.tanh((mean_a - mean_b) / R.TEAM_EXP_SCALE)
        mu_all = (sum(m for m, _ in ra) + sum(m for m, _ in rb)) / 8
        def contribs(T, ids, rr, s, sign):
            mu_sum = sum(m for m, _ in rr); tdg = sum(T[c]['dmg'] for c in ids)
            out = []
            # Game Impact Score term: agi is normalised to the 8-player game mean (1.00), so a player's
            # expected agi is his mu over the game's mean mu; residuals centred within the team
            agi_ok = cw_agi and all(T[c]['agi'] is not None for c in ids)
            if agi_ok:
                ares = {c: T[c]['agi'] - (cache[c][0] / mu_all) for c in ids}; mares = sum(ares.values()) / 4
            # +/- residuals, centred within the team
            # expected +/- for each player: his share of the expected team margin PLUS a skill split
            # within the team (k_ind frags per mu point above the team mean), so a strong player is
            # expected to out-produce weak teammates and the residual self-corrects as his mu rises
            mean_mu = mu_sum / 4
            exp_i = {c: sign * exp_margin * (cache[c][0] / mu_sum) + k_ind * (cache[c][0] - mean_mu) for c in ids}
            res = {c: T[c]['pm'] - exp_i[c] for c in ids}
            mres = sum(res.values()) / 4
            for c, (om, og) in zip(ids, rr):
                si = s
                if cw_dmg and tdg:
                    si += cw_dmg * (T[c]['dmg'] / tdg - om / mu_sum)
                if cw_pm:
                    si += cw_pm * math.tanh((res[c] - mres) / norm_pm)
                if agi_ok:
                    si += cw_agi * math.tanh((ares[c] - mares) / norm_agi)
                out.append(min(1.0, max(0.0, si)))
            return out
        si_a = contribs(A, ids_a, ra, s_team, +1.0); si_b = contribs(B, ids_b, rb, 1.0 - s_team, -1.0)
        RA = [R.TEAM_MODEL.rating(mu=m, sigma=g) for m, g in ra]; RB = [R.TEAM_MODEL.rating(mu=m, sigma=g) for m, g in rb]
        [wa, wb] = R.TEAM_MODEL.rate([RA, RB], ranks=[0, 1])
        RA2 = [R.TEAM_MODEL.rating(mu=m, sigma=g) for m, g in ra]; RB2 = [R.TEAM_MODEL.rating(mu=m, sigma=g) for m, g in rb]
        [la, lb] = R.TEAM_MODEL.rate([RA2, RB2], ranks=[1, 0])
        before = {c: cache[c][0] for c in ids_a + ids_b}
        for c, si, w, l in zip(ids_a, si_a, wa, la):
            cache[c] = (si * w.mu + (1 - si) * l.mu, max(R.TEAM_SIGMA_FLOOR, si * w.sigma + (1 - si) * l.sigma))
        for c, si, w, l in zip(ids_b, si_b, wb, lb):
            cache[c] = (si * l.mu + (1 - si) * w.mu, max(R.TEAM_SIGMA_FLOOR, si * l.sigma + (1 - si) * w.sigma))
        if trace and trace in before:
            side = 'A' if trace in ids_a else 'B'; s_me = s_team if side == 'A' else 1 - s_team; si_me = (si_a if side == 'A' else si_b)[(ids_a if side == 'A' else ids_b).index(trace)]
            tr.append({'gid': gid, 'map': mp, 'side': side, 'fa': fa, 'fb': fb, 'mean_a': mean_a, 'mean_b': mean_b, 'exp_margin': exp_margin, 's_team': s_me, 'si': si_me, 'before': before[trace], 'after': cache[trace][0], 'pm': (A if side == 'A' else B)[trace]['pm']})
        for c in ids_a + ids_b: nprior[c] += 1
    res = {'label': label, 'cw_dmg': cw_dmg, 'cw_pm': cw_pm, 'norm_pm': norm_pm, 'k_ind': k_ind, 'cw_agi': cw_agi, 'norm_agi': norm_agi, 'min_prior': MP, 'map': map_layer, 'n': len(ll),
           'logloss': round(st.mean(ll), 4), 'acc': round(100 * st.mean(hits), 1), 'brier': round(st.mean(brier), 4)}
    if not quiet: print(f"  {label:44s} n={res['n']:5d}  logloss {res['logloss']:.4f}  acc {res['acc']:.1f}%  brier {res['brier']:.4f}", flush=True)
    if detail: res['per_game'] = dict(zip(keys, ll)); res['ratings'] = dict(cache); res['nprior'] = dict(nprior); res['py'] = py; res['cells'] = dict(cells); res['trace'] = tr
    return res

if __name__ == '__main__':
    results = []
    print("\nbaselines")
    results.append(run(0, 0, label='no contribution'))
    results.append(run(1.1, 0, label='SHIPPED: damage share CW=1.1'))
    results.append(run(3.0, 0, label='damage share CW=3.0 (local optimum)'))
    print("\n+/- alone, with a skill split in the expectation (k_ind frags per mu point)")
    for k in (0.05, 0.1, 0.15, 0.2, 0.3):
        for cw in (0.2, 0.3, 0.5, 0.8):
            results.append(run(0, cw, 40.0, label=f'+/- CW={cw} k_ind={k}', k_ind=k))
    print("\nboth: damage share CW=1.1 + +/-")
    for k in (0.1, 0.15, 0.2, 0.3):
        for cw in (0.2, 0.3, 0.5):
            results.append(run(1.1, cw, 40.0, label=f'damage 1.1 + +/- CW={cw} k_ind={k}', k_ind=k))
    best = min(results, key=lambda r: r['logloss'])
    print(f"\nbest: {best}")
    print("\nrobustness of the top configs at min-prior 5 (more scored games) and 20 (cleaner priors)")
    top = sorted(results, key=lambda r: r['logloss'])[:4] + [results[1]]
    for r in top:
        for mp in (5, 20):
            run(r['cw_dmg'], r['cw_pm'], r['norm_pm'], label=f"{r['label']} @prior>={mp}", k_ind=r['k_ind'], min_prior=mp)
    if OUT: json.dump(results, open(OUT, 'w'), indent=1); print('wrote', OUT)

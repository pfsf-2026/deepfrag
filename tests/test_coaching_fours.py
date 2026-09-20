#!/usr/bin/env python3
"""Tests for the 4on4 coach engine (coaching_fours.py): levels, gates, lever
ranking, one-focus prescriptions and grading. Synthetic rows, no database.
Run: python tests/test_coaching_fours.py"""
import os, sys, random
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import coaching_fours as C  # noqa: E402

random.seed(7)
T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)


def row(i, *, above, deaths=50, dmg=8000, ra=6, quad=2, adj=40, win=None, mapname="dm3", even=(10, 20), started=(20, 5), sg=6000, st=4000, chained=20):
    return {"hub_game_id": 1000 + i, "played_at": (T0 + timedelta(hours=i)).isoformat(), "map": mapname, "win": (i % 2 == 0) if win is None else win,
            "minutes": 20.0, "frags": 40, "kills": 40, "deaths": deaths, "adj_kills": adj, "dmg": dmg, "taken": 7000,
            "stacked_given": sg, "stacked_taken": st, "spawn_deaths": 6, "chained_real": chained, "take_ra": ra, "take_ya": 8, "take_mh": 2,
            "take_quad": quad, "ra_on_timer": ra * 0.6, "quad_runs": quad, "quad_full_runs": max(quad - 1, 0), "quad_frags_full": 3.5 * max(quad - 1, 0),
            "quad_died": quad * 0.4, "rockets_fired": 100, "rl_dmg": 3500, "fights": 40, "started": started[0], "started_behind": started[1],
            "even_w": even[0], "even_n": even[1], "teamkills": 2, "team_dmg": 300, "plus_minus": above, "above_avg": above, "agi": 1.0 + above / 100}


def player(n, above, **kw):
    # jitter the counting stats too, so per-game explainers have a spread to work with
    out = []
    for i in range(n):
        k = dict(kw)
        for key, spread in (("deaths", 8), ("dmg", 1500), ("ra", 2), ("adj", 8)):
            if key in k: k[key] = max(0, k[key] + random.uniform(-spread, spread))
        out.append(row(i, above=above + random.uniform(-15, 15), **k))
    return out


def pool():
    P = {}
    specs = [(-45, dict(deaths=72, dmg=4600, ra=2.5, quad=0.7, adj=25, even=(7, 20))),
             (-22, dict(deaths=64, dmg=7200, ra=5, quad=1.9, adj=38, even=(9, 20))),
             (0, dict(deaths=56, dmg=8400, ra=6, quad=2, adj=45, even=(11, 20))),
             (25, dict(deaths=53, dmg=9800, ra=7.8, quad=3.4, adj=53, even=(12, 20), sg=8000)),
             (60, dict(deaths=48, dmg=13000, ra=8.9, quad=4, adj=71, even=(13, 20), sg=11000))]
    k = 0
    for above, kw in specs:
        for j in range(4):
            P[f"p{k}"] = player(30, above, **kw); k += 1
    return P


checks = []
def check(name):
    def d(f): checks.append((name, f)); return f
    return d


@check("levels: bands from above-average, unplaced under 15 games")
def _():
    assert C.level_for(-40, 30)["level"] == 1 and C.level_for(-30, 30)["level"] == 2
    assert C.level_for(-10, 30)["level"] == 3 and C.level_for(15, 30)["level"] == 4 and C.level_for(99, 30)["level"] == 5
    assert C.level_for(50, 10)["level"] == 0 and not C.level_for(50, 10)["placed"]


@check("metrics: reds exclude e1m2 games, ratios undefined when no denominator")
def _():
    rows = [row(0, above=0, ra=8, mapname="dm3"), row(1, above=0, ra=0, mapname="e1m2")]
    m = C.metrics(rows)
    assert m["ra_pg"] == 8.0, m["ra_pg"]
    assert m["games"] == 2 and abs(m["deaths_pm"] - 2.5) < 1e-9
    m2 = C.metrics([row(0, above=0, even=(0, 0), started=(0, 0), quad=0)])
    assert m2["even_win_pct"] is None and m2["started_behind_pct"] is None and m2["quad_died_pct"] is None


@check("pool baselines: five levels populated, medians ordered the right way")
def _():
    base = C.pool_baselines(pool())
    assert base["n"] == 20 and all(base["levels"][l]["n"] == 4 for l in range(1, 6)), base["levels"]
    med = lambda l, k: base["levels"][l]["median"][k]
    assert med(1, "deaths_pm") > med(3, "deaths_pm") > med(5, "deaths_pm")
    assert med(1, "ra_pg") < med(4, "ra_pg") and med(2, "even_win_pct") < med(3, "even_win_pct")
    assert base["sd"]["adj_kills_pm"] > 0


@check("ranking: only levers active at the level; gates first on ties; L1 never sees quad_died")
def _():
    base = C.pool_baselines(pool())
    rows = player(30, -45, deaths=72, dmg=4600, ra=2.5, quad=0.7, adj=25, even=(7, 20))
    r = C.rank_levers(rows, 1, base)
    keys = [l["key"] for l in r["levers"]]
    assert keys and "quad_died_pct" not in keys and "sddr" not in keys, keys
    assert set(keys) <= {k for k, L in C.LEVERS.items() if 1 in L["levels"] or k in C.GATES[1]}
    top = r["levers"][0]
    assert top["short_sd"] > 0 and top["target"] != "—"


@check("gates: L1 gates are reds and damage, judged against the promotion-line bar")
def _():
    base = C.pool_baselines(pool())
    m = C.metrics(player(30, -45, deaths=72, dmg=4600, ra=2.5, quad=0.7, adj=25, even=(7, 20)))
    g = C.gate_status(m, 1, base)
    assert [x["key"] for x in g] == ["ra_pg", "dmg_pm"] and all(x["passed"] is False for x in g), g
    m2 = C.metrics(player(30, -45, deaths=72, dmg=9000, ra=7, quad=0.7, adj=25, even=(7, 20)))
    assert all(x["passed"] for x in C.gate_status(m2, 1, base))
    # the bar is the line, and the line sits between own median and next median
    line = base["levels"][1]["line"]; own = base["levels"][1]["median"]; nxt = base["levels"][2]["median"]
    for k in ("ra_pg", "dmg_pm"):
        assert own[k] <= line[k] <= nxt[k], (k, own[k], line[k], nxt[k])
        assert g[[x["key"] for x in g].index(k)]["target_raw"] == line[k]
    # lower-is-better lever: clamped the other way round
    l2 = base["levels"][2]["line"]; assert base["levels"][3]["median"]["deaths_pm"] <= l2["deaths_pm"] <= base["levels"][2]["median"]["deaths_pm"]
    assert "line" not in base["levels"][5] or base["levels"][5]["line"] == {}


@check("chained deaths and teamkills are display-only in fours (never ranked)")
def _():
    assert C.LEVERS["chained_pct"]["levels"] == set() and C.LEVERS["tk_pg"]["levels"] == set()
    assert "chained_pct" not in sum(C.GATES.values(), [])


@check("prescription: pending inside the window, then hit / improved / worse")
def _():
    prev = {"lever": "deaths_pm", "you": 3.6, "target": 3.2, "window_games": 10, "issued_at": T0.isoformat(),
            "issued_after": (T0 + timedelta(hours=9)).isoformat()}
    rows = [row(i, above=0, deaths=72) for i in range(10)]                 # all before/at issue
    assert C.grade_prescription(prev, rows)["status"] == "pending"
    rows += [row(10 + i, above=0, deaths=60) for i in range(10)]           # 3.0/min after -> hit
    assert C.grade_prescription(prev, rows)["status"] == "hit"
    rows2 = [row(i, above=0, deaths=72) for i in range(10)] + [row(10 + i, above=0, deaths=69) for i in range(10)]  # 3.45: moved 0.15 of 0.4 gap
    assert C.grade_prescription(prev, rows2)["status"] == "improved"
    rows3 = [row(i, above=0, deaths=72) for i in range(10)] + [row(10 + i, above=0, deaths=78) for i in range(10)]
    assert C.grade_prescription(prev, rows3)["status"] == "worse"
    assert C.grade_prescription(None, rows) is None


@check("focus: one at a time; an open prescription is kept, a graded one is replaced")
def _():
    base = C.pool_baselines(pool())
    rows = player(30, -22, deaths=64, dmg=7200, ra=5, quad=1.9, adj=38, even=(9, 20))
    ranked = C.rank_levers(rows, 2, base)["levers"]
    f = C.choose_focus(ranked, None, None, rows)
    assert f["status"] == "new" and f["window_games"] == 10 and f["lever"] == ranked[0]["key"]
    prev = {"lever": ranked[-1]["key"], "you": 1, "target": 2, "window_games": 10, "issued_at": T0.isoformat(),
            "issued_after": rows[-3]["played_at"]}
    graded = C.grade_prescription(prev, rows)
    assert graded["status"] == "pending"
    f2 = C.choose_focus(ranked, prev, graded, rows)
    assert f2["lever"] == prev["lever"] and f2["status"] == "in_progress"


@check("report: level, gates, one focus, game cards newest first with two explainers")
def _():
    base = C.pool_baselines(pool())
    rows = player(30, 25, deaths=53, dmg=9800, ra=7.8, quad=3.4, adj=53, even=(12, 20), sg=8000)
    rep = C.build_report(rows, base, None, "tester")
    assert rep["level"]["level"] == 4, rep["level"]
    assert [g["key"] for g in rep["level"]["gates"]] == ["adj_kills_pm", "sddr"], rep["level"]["gates"]
    assert rep["focus"] and rep["focus"]["status"] == "new", rep["focus"]
    assert rep["games"][0]["hub_game_id"] > rep["games"][-1]["hub_game_id"], [g["hub_game_id"] for g in rep["games"]]
    assert len(rep["games"][0]["explain"]) == 2, rep["games"][0]
    assert rep["previous"] is None and 0 < len(rep["levers"]) <= 6


def main():
    failed = 0
    for name, fn in checks:
        try:
            fn(); print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL {name}: {e}")
        except Exception as e:
            failed += 1; print(f"  ERR  {name}: {type(e).__name__}: {e}")
    print(f"{len(checks) - failed}/{len(checks)} passed"); return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""First Spawn Optimization (FSO) — a coaching lever.

Scores how well a player opens off their (random) first spawn vs the elite
reference in spawn_runs, conditioned on (own_spawn × enemy_spawn). The v1 metric
(item secured + survived) didn't discriminate skill — both terms saturate. v2
(this) centres on EFFICIENCY (time-to-stack: elites hit RA+MH ~2.5s, weak ~5s)
and OPENING-WIN (survival is no longer cheap), with item-secured a minor term.
Validated 2026-06-02: elites ~70-76% vs weak ~43-58% on aerowalk; holds across
weightings. Weights are efficiency-leaning per Peter.

Reuses extract_spawn_runs for the proven first-spawn extraction/snap logic.
"""
from __future__ import annotations

import statistics

import extract_spawn_runs as E

WIN_MS = 13
ITEM_TIER = {"full_start": 1.0, "ra": 0.75, "mh_only": 0.5, "ya_ga": 0.3, "nothing": 0.0}
RESULT_SCORE = {"won": 1.0, "traded": 0.5, "survived": 0.3, "lost": 0.0}
W_EFF, W_RES, W_ITEM = 0.5, 0.3, 0.2   # efficiency-leaning (Peter, 2026-06-02)
MIN_EN = 4                              # min enemy-conditioned sample to use the tighter benchmark
NEVER_STACK_S = 12.0
# Observed elite-cohort FSO under these weights (locust/bps ~70-76%); the lever's
# benchmark "ceiling" so a player's score is framed against the elite line, not 100.
ELITE_FSO = 0.75


def _tts(path) -> float | None:
    """Time (s) to Full Start = first bucket where state==3 (RA + Mega)."""
    for i, t in enumerate(path):
        if t.get("state") == 3:
            return i * WIN_MS / 1000
    return None


def load_benchmark(cur, maps) -> dict:
    """Elite reference per map from spawn_runs: median time-to-stack + mean item
    tier, keyed by ('spawn', own) and ('combo', (own, enemy)). {map: {...}}."""
    maps = [m for m in maps if m]
    if not maps:
        return {}
    cur.execute(
        "SELECT map, own_spawn, enemy_spawn, items_outcome, path "
        "FROM spawn_runs WHERE map = ANY(%s)", (maps,))
    acc: dict = {}
    for r in cur.fetchall():
        mp = acc.setdefault(r["map"], {"tts": {}, "tier": {}})
        tts = _tts(r["path"])
        tier = ITEM_TIER.get(r["items_outcome"], 0)
        for k in (("spawn", r["own_spawn"]), ("combo", (r["own_spawn"], r["enemy_spawn"]))):
            mp["tier"].setdefault(k, []).append(tier)
            if tts is not None:
                mp["tts"].setdefault(k, []).append(tts)
    return acc


def _bench(map_ref, own, enemy):
    ck, sk = ("combo", (own, enemy)), ("spawn", own)
    tts = map_ref["tts"].get(ck) if len(map_ref["tts"].get(ck, [])) >= MIN_EN else map_ref["tts"].get(sk, [])
    tier = map_ref["tier"].get(ck) if len(map_ref["tier"].get(ck, [])) >= MIN_EN else map_ref["tier"].get(sk, [])
    med_tts = statistics.median(tts) if tts else NEVER_STACK_S
    mean_tier = (sum(tier) / len(tier)) if tier else 0.6
    return med_tts, mean_tier


def score_run(run: dict, map_ref: dict) -> dict | None:
    """Score one extracted first-spawn run (from E.extract_run) vs the map ref."""
    if not run or not map_ref:
        return None
    med_tts, mean_tier = _bench(map_ref, run["own_spawn"], run["enemy_spawn"])
    p_tts = _tts(run["path"]) or NEVER_STACK_S
    eff = min(1.0, med_tts / max(p_tts, 0.3))
    res = RESULT_SCORE.get(run["opening_result"], 0)
    item = min(1.0, ITEM_TIER.get(run["items_outcome"], 0) / max(mean_tier, 0.5))
    return {
        "score": W_EFF * eff + W_RES * res + W_ITEM * item,
        "own_spawn": run["own_spawn"], "enemy_spawn": run["enemy_spawn"],
        "time_to_stack": round(p_tts, 1), "elite_tts": round(med_tts, 1),
        "items": run["items_outcome"], "result": run["opening_result"],
    }


def player_fso(matches, display, benchmark, spawn_locs_by_map, cap: int = 10) -> dict:
    """Aggregate FSO% over a player's matches.

    matches: rows with .game_id and .map. benchmark: load_benchmark() result.
    spawn_locs_by_map: {map: spawn entities}. `cap` bounds the first-spawn pulls
    (2 mvd-api calls each) so the coaching report stays well under the CDN's
    ~100s origin timeout. Returns {fso, n, runs}.
    """
    runs = []
    scored = 0
    for mrow in matches:
        if scored >= cap:
            break
        mp = mrow["map"]
        ref = benchmark.get(mp)
        locs = spawn_locs_by_map.get(mp)
        if not ref or not locs:
            continue
        scored += 1
        try:
            run = E.extract_run(mrow["game_id"], display, E.label_spawns(locs))
        except Exception:
            continue
        s = score_run(run, ref)
        if s:
            runs.append(s)
    if not runs:
        return {"fso": None, "n": 0, "runs": []}
    return {
        "fso": round(sum(r["score"] for r in runs) / len(runs), 3),
        "elite_fso": ELITE_FSO,
        "n": len(runs),
        "runs": runs,
    }

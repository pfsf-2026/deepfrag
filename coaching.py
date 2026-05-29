#!/usr/bin/env python3
"""Coaching metric layer — the deterministic primitives behind the AI coach.

Productionizes the one-off duel analysis (the Cronus diagnosis, 2026-05-29)
into a reusable module. For a player's recent matches it pulls per-bucket
time-series + frag/item data from the mvd-api and computes coaching primitives:

  - item control (RA/MH/YA/quad pickup share)
  - stack-at-engagement (your stack vs enemy stack at your kills/deaths)
  - restack efficiency (sec to re-armor after death)
  - accuracy (LG/RL, from the per-match stats we already store)
  - death weapons + clustering

The weakness engine (separate) ranks these vs the player's OWN win-state
baseline and a tier benchmark; the LLM narrates the ranked result.

mvd-api addressing: our matches.match_id IS the hub gameId for recent matches
(positive ids). Legacy rows (negative match_id) aren't reachable yet — they'd
need a demo_sha256 -> hub id lookup; recent form is what coaching needs.

This module is intentionally dependency-light (urllib + psycopg2) so it runs
both inside the Cloud Run container and as a standalone backfill worker.
"""
from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict

MVD_API = os.environ.get(
    "MVD_API_BASE", "https://deepfrag-mvd-api-751658372467.us-central1.run.app"
)
STACK_ARMOR = 50            # "stacked" armor floor (duel-relevant)
BUCKET_MS = 50              # resolution for stack/position walk
MAJOR_ITEMS = ("ra", "mh", "ya", "quad", "ga")


def _get(path: str, timeout: int = 90):
    url = f"{MVD_API}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status == 200:
                return json.loads(r.read())
    except Exception:
        return None
    return None


def match_metrics(game_id: int, player: str) -> dict | None:
    """Compute coaching primitives for one player in one match.

    Returns None if the demo isn't parseable or the player isn't in it.
    `player` is the in-demo name (display_name); mvd-api keys players by name.
    """
    buckets = _get(f"/v1/demos/gameId:{game_id}/buckets?windowMs={BUCKET_MS}&layout=column")
    if not buckets or "players" not in buckets:
        return None
    players = buckets["players"]
    if player not in players:
        # try case-insensitive match
        match = next((k for k in players if k.lower() == player.lower()), None)
        if not match:
            return None
        player = match
    me = players[player]
    opp_key = next((k for k in players if k != player), None)
    en = players.get(opp_key) if opp_key else None
    n = me.get("n", 0)
    if not n:
        return None

    arm, hp, alive = me.get("a", []), me.get("h", []), me.get("alive", [])
    alive_idx = [i for i in range(n) if i < len(alive) and alive[i]]
    if not alive_idx:
        return None

    def stack_at(p, i):
        a = p["a"][i] if p and i < len(p.get("a", [])) else 0
        h = p["h"][i] if p and i < len(p.get("h", [])) else 0
        return a + h

    avg_armor = sum(arm[i] for i in alive_idx) / len(alive_idx)
    pct_stacked = sum(1 for i in alive_idx if arm[i] >= STACK_ARMOR) / len(alive_idx)

    en_avg_armor = en_pct_stacked = 0.0
    if en:
        en_n = en.get("n", 0)
        en_alive = [i for i in range(en_n) if i < len(en.get("alive", [])) and en["alive"][i]]
        if en_alive:
            en_avg_armor = sum(en["a"][i] for i in en_alive) / len(en_alive)
            en_pct_stacked = sum(1 for i in en_alive if en["a"][i] >= STACK_ARMOR) / len(en_alive)

    # frags: stack at my kills/deaths + enemy stack at those moments
    frags = _get(f"/v1/demos/gameId:{game_id}/frags")
    my_kill_stack, my_kill_enemy, my_death_stack, my_death_enemy = [], [], [], []
    death_wpns = defaultdict(int)
    if frags:
        for f in frags.get("frags", []):
            t = f.get("time", 0)
            idx = min(int(t / BUCKET_MS), n - 1)
            k, v, wpn = f.get("killer"), f.get("victim"), f.get("weapon", "?")
            if k == player and v != player:
                my_kill_stack.append(stack_at(me, idx))
                my_kill_enemy.append(stack_at(en, idx))
            elif v == player and k != player:
                my_death_stack.append(stack_at(me, idx))
                my_death_enemy.append(stack_at(en, idx))
                death_wpns[wpn] += 1

    # item control
    items = _get(f"/v1/demos/gameId:{game_id}/items")
    item_ctrl = {}
    if items:
        for kind in MAJOR_ITEMS:
            mine = total = 0
            for it in items.get("items", []):
                if it.get("kind") != kind:
                    continue
                for ph in it.get("phases", []):
                    tb = ph.get("takenBy")
                    if tb is None:
                        continue
                    total += 1
                    if tb == player:
                        mine += 1
            if total:
                item_ctrl[kind] = {"mine": mine, "total": total, "share": round(mine / total, 3)}

    # restack: sec from each death (alive 1->0) to armor>=50 again
    restacks = []
    i = 1
    while i < n:
        if i < len(alive) and alive[i] == 0 and alive[i - 1] == 1:
            j = i
            while j < n and not (j < len(arm) and alive[j] and arm[j] >= STACK_ARMOR):
                j += 1
            if j < n:
                restacks.append((j - i) * BUCKET_MS / 1000.0)
            i = j + 1
        else:
            i += 1

    def avg(x):
        return round(sum(x) / len(x), 1) if x else None

    return {
        "game_id": game_id,
        "player": player,
        "n_buckets": n,
        "avg_armor": round(avg_armor),
        "pct_stacked": round(pct_stacked, 3),
        "enemy_avg_armor": round(en_avg_armor),
        "enemy_pct_stacked": round(en_pct_stacked, 3),
        "stack_at_kill": avg(my_kill_stack),
        "enemy_stack_at_my_kill": avg(my_kill_enemy),
        "stack_at_death": avg(my_death_stack),
        "enemy_stack_at_my_death": avg(my_death_enemy),
        "n_kills": len(my_kill_stack),
        "n_deaths": len(my_death_stack),
        "item_control": item_ctrl,
        "restack_med_sec": (sorted(restacks)[len(restacks) // 2] if restacks else None),
        "restack_avg_sec": avg(restacks),
        "death_weapons": dict(death_wpns),
    }


def aggregate(per_match: list, results: list) -> dict:
    """Aggregate per-match metrics into win-state-split coaching primitives.

    per_match: list of match_metrics() dicts (None entries filtered).
    results:   parallel list of 'W'/'L' for each match.
    """
    rows = [(m, r) for m, r in zip(per_match, results) if m]
    W = [m for m, r in rows if r == "W"]
    L = [m for m, r in rows if r == "L"]

    def mean(ms, key):
        vals = [m[key] for m in ms if m.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def item_share(ms, kind):
        mine = sum(m["item_control"].get(kind, {}).get("mine", 0) for m in ms)
        tot = sum(m["item_control"].get(kind, {}).get("total", 0) for m in ms)
        return round(mine / tot, 3) if tot else None

    def split(key):
        return {"win": mean(W, key), "loss": mean(L, key), "all": mean([m for m, _ in rows], key)}

    death_wpns = defaultdict(int)
    for m, _ in rows:
        for w, c in m.get("death_weapons", {}).items():
            death_wpns[w] += c

    return {
        "matches_analyzed": len(rows),
        "wins": len(W), "losses": len(L),
        "pct_stacked": split("pct_stacked"),
        "enemy_pct_stacked": split("enemy_pct_stacked"),
        "stack_at_kill": split("stack_at_kill"),
        "stack_at_death": split("stack_at_death"),
        "enemy_stack_at_my_death": split("enemy_stack_at_my_death"),
        "avg_armor": split("avg_armor"),
        "restack_avg_sec": split("restack_avg_sec"),
        "item_control": {
            kind: {"win": item_share(W, kind), "loss": item_share(L, kind), "all": item_share([m for m, _ in rows], kind)}
            for kind in MAJOR_ITEMS
        },
        "death_weapons": dict(sorted(death_wpns.items(), key=lambda x: -x[1])),
    }

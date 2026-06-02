#!/usr/bin/env python3
"""Deep Analyze This Match — a full LLM read of ONE duel.

Assembles a STRUCTURED timeline from a single match (movement-derived stacks,
item pickups + timing, first-spawn read, the frag-by-frag fight log with each
side's stack at the moment), then has Claude narrate what went right/wrong and
what to do differently — grounded in the numbers, citing timestamps.

Complements the aggregate coach (multi-match levers): this is the per-match
"here's the exact 6:20 fight where it broke" view. On-demand + persisted in
match_analysis (one Claude call per game+player, immutable demo).

Reuses coaching.match_metrics (per-match primitives) + extract_spawn_runs
(first-spawn) + the Anthropic REST pattern from coaching_narrate.
"""
from __future__ import annotations

import json
import os
import urllib.request

import coaching as C
import extract_spawn_runs as E

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("COACHING_MODEL", "claude-opus-4-8")
BUCKET_MS = C.BUCKET_MS

SYSTEM = (
    "You are a QuakeWorld 1on1 dueling coach giving a DEEP single-match review. "
    "You receive a structured timeline of ONE duel (the opening spawn read, item "
    "control, and a frag-by-frag log with each player's stack at every kill/death) "
    "plus movement-derived metrics. Write a specific, honest review. RULES: "
    "(1) Ground every claim in the given numbers/timestamps — never invent events. "
    "(2) Structure: a 1-sentence verdict, then the OPENING (spawn read + first "
    "stack), the KEY MOMENTS (cite mm:ss for the turning points and any naked/"
    "under-armored deaths), what WENT RIGHT (keep it), and 2-3 DO-DIFFERENTLY "
    "fixes. (3) QW context: duels are won by item control (RA every 20s, Mega), "
    "fighting from stack, resetting when naked. (4) Be direct and concrete, cite "
    "timestamps so the player can scrub to them."
)


def _mmss(ms: int) -> str:
    s = int(ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


def build_timeline(game_id: int, display: str, result: str | None,
                   spawn_locs: list | None, item_locs: list | None) -> dict | None:
    """Structured single-match summary for the LLM (and for the UI to show)."""
    metrics = C.match_metrics(game_id, display, item_locs=item_locs)
    if not metrics:
        return None
    resolved = metrics["player"]

    # First-spawn read (13ms extraction; best-effort).
    first_spawn = None
    if spawn_locs:
        try:
            run = E.extract_run(game_id, resolved, E.label_spawns(spawn_locs))
            if run:
                first_spawn = {
                    "own_spawn": run["own_spawn"], "enemy_spawn": run["enemy_spawn"],
                    "items_secured": run["items_outcome"], "opening_result": run["opening_result"],
                    "first_kill_ms": run["first_kill_ms"], "first_death_ms": run["first_death_ms"],
                }
        except Exception:
            first_spawn = None

    # Frag-by-frag fight log with each side's stack at the moment.
    buckets = C._get(f"/v1/demos/gameId:{game_id}/buckets?windowMs={BUCKET_MS}&layout=column")
    frags = C._get(f"/v1/demos/gameId:{game_id}/frags") or {"frags": []}
    fight_log = []
    if buckets and "players" in buckets:
        players = buckets["players"]
        me = players.get(resolved)
        opp_key = next((k for k in players if k != resolved), None)
        en = players.get(opp_key) if opp_key else None
        n = me.get("n", 0) if me else 0

        def stack_at(p, idx):
            if not p:
                return None
            a = p["a"][idx] if idx < len(p.get("a", [])) else 0
            h = p["h"][idx] if idx < len(p.get("h", [])) else 0
            return a + h

        for f in frags.get("frags", []):
            t = f.get("time", 0)
            idx = min(int(t / BUCKET_MS), max(n - 1, 0))
            k, v, wpn = f.get("killer"), f.get("victim"), f.get("weapon", "?")
            if k == resolved and v != resolved:
                ev = "kill"
            elif v == resolved and k != resolved:
                ev = "death"
            else:
                continue
            mine, theirs = stack_at(me, idx), stack_at(en, idx)
            entry = {"t": _mmss(t), "event": ev, "weapon": wpn,
                     "my_stack": mine, "enemy_stack": theirs}
            if ev == "death" and mine is not None and mine < 130:
                entry["note"] = "under-armored" if mine >= 50 else "naked"
            fight_log.append(entry)

    return {
        "game_id": game_id, "player": resolved, "result": result,
        "first_spawn": first_spawn,
        "metrics": {
            "pct_stacked": metrics["pct_stacked"],
            "stack_at_kill": metrics["stack_at_kill"],
            "stack_at_death": metrics["stack_at_death"],
            "enemy_stack_at_my_death": metrics["enemy_stack_at_my_death"],
            "restack_avg_sec": metrics["restack_avg_sec"],
            "armor_first": (metrics.get("first_item") or {}).get("armor_first_rate"),
            "item_control": {k: v.get("share") for k, v in metrics.get("item_control", {}).items()},
            "death_weapons": metrics.get("death_weapons", {}),
            "n_kills": metrics["n_kills"], "n_deaths": metrics["n_deaths"],
        },
        "fight_log": fight_log,
    }


def _llm(timeline: dict, display: str, map_name: str) -> dict | None:
    if not ANTHROPIC_KEY:
        return None
    body = {
        "model": MODEL, "max_tokens": 1400, "system": SYSTEM,
        "messages": [{"role": "user", "content":
            f"Player: {display}. Map: {map_name}. Result: {timeline.get('result')}.\n\n"
            f"Match timeline (structured):\n{json.dumps(timeline, indent=2)}\n\n"
            "Write the deep single-match review."}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": ANTHROPIC_KEY,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
            return {"text": "".join(b.get("text", "") for b in data.get("content", [])),
                    "source": "llm", "model": MODEL}
    except Exception:
        return None


def _template(timeline: dict, display: str, map_name: str) -> dict:
    """Deterministic fallback when no model key — honest, terse."""
    fs = timeline.get("first_spawn") or {}
    m = timeline["metrics"]
    parts = [f"Deep read — {display} on {map_name} ({timeline.get('result') or '?'})."]
    if fs:
        parts.append(f"Opening: spawned {fs['own_spawn']} vs enemy {fs['enemy_spawn']} → "
                     f"{fs['items_secured']}, {fs['opening_result']}.")
    if m.get("stack_at_death") is not None:
        parts.append(f"You died at avg stack {m['stack_at_death']} (enemy "
                     f"{m['enemy_stack_at_my_death']}); restack {m['restack_avg_sec']}s.")
    naked = [e for e in timeline["fight_log"] if e.get("note")]
    if naked:
        parts.append(f"{len(naked)} under-armored/naked deaths — e.g. "
                     + ", ".join(f"{e['t']} ({e['note']}, {e['weapon']})" for e in naked[:3]) + ".")
    parts.append("(Connect the coaching model for the full narrative review.)")
    return {"text": " ".join(parts), "source": "template"}


def analyze(game_id: int, display: str, map_name: str, result: str | None,
            spawn_locs: list | None, item_locs: list | None) -> dict | None:
    timeline = build_timeline(game_id, display, result, spawn_locs, item_locs)
    if not timeline:
        return None
    narr = _llm(timeline, display, map_name) or _template(timeline, display, map_name)
    return {"game_id": game_id, "display": display, "map": map_name,
            "timeline": timeline, "analysis": narr}

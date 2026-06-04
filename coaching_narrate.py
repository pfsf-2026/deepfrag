#!/usr/bin/env python3
"""Coaching narration — turn ranked levers into a human coaching read.

Two modes:
  - LLM (preferred): if ANTHROPIC_API_KEY is set, Claude narrates the ranked
    levers into a diagnosis + prioritized fixes + drills. It receives the
    COMPUTED levers as structured input and is instructed to explain them, not
    invent new ones (grounded coaching — never hallucinate the analysis).
  - Template (fallback): a deterministic narration from the levers so the Coach
    endpoint works before a key is configured. Honest, just less fluent.

Uses the Anthropic Messages REST API directly (urllib) — no SDK dependency, so
the container stays slim. Prompt is small + cache-friendly.
"""
from __future__ import annotations

import json
import os
import urllib.request

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("COACHING_MODEL", "claude-opus-4-8")

SYSTEM = (
    "You are a QuakeWorld 1on1 dueling coach. You receive a player's COMPUTED "
    "performance levers (already ranked by a deterministic engine from their "
    "demo data) and write a sharp, specific coaching read. RULES: (1) Explain "
    "the computed levers — never invent metrics or numbers not given. (2) Lead "
    "with the single root cause. (3) Give 2-3 concrete, prioritized fixes tied "
    "to the levers, with the QW-specific 'how'. (4) Be direct and encouraging, "
    "not generic. (5) If a lever has a 'detail' field, use its specifics. "
    "QW context (priority order): the biggest separator is STACK DISCIPLINE — "
    "elites fight from ahead (out-stacked) and disengage when behind, and keep a "
    "high average stack. Then item control by TIER (Red Armor and Mega are tier-1 "
    "and roughly equal; YA tier-2; GA tier-3), timing the Mega respawn, and "
    "resetting when naked instead of re-contesting under-stacked. Keep it under 250 words."
)


def _llm_narrate(payload: dict) -> str | None:
    if not ANTHROPIC_KEY:
        return None
    body = {
        "model": MODEL,
        "max_tokens": 800,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": "Player: {display} ({record}). Mode: {mode}. "
                       "Win-state baseline available: {has_win}.\n\n"
                       "Ranked levers (priority desc):\n{levers}\n\n"
                       "Write the coaching read.".format(
                           display=payload["display"],
                           record=payload["record"],
                           mode=payload["mode"],
                           has_win=payload["has_win_baseline"],
                           levers=json.dumps(payload["levers"], indent=2),
                       ),
        }],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return "".join(b.get("text", "") for b in data.get("content", []))
    except Exception:
        return None


def _template_narrate(payload: dict) -> str:
    levers = payload["levers"]
    if not levers:
        return ("Not enough recent demo data to diagnose. Play a few more rated "
                "1on1 matches and check back.")
    top = levers[0]
    lines = []
    rec = payload["record"]
    lines.append(f"**{payload['display']}** — last {payload.get('matches_analyzed','?')} "
                 f"1on1s ({rec['wins']}W / {rec['losses']}L).")
    # Root cause = top lever
    if payload["has_win_baseline"] and top.get("win"):
        lines.append(f"\n**Your #1 lever: {top['label']}.** In your wins it's "
                     f"{top['win']}; in your losses it drops to {top['loss']} "
                     f"(elite is {top['elite']}). That gap is the difference "
                     f"between your winning and losing self.")
    else:
        lines.append(f"\n**Your #1 lever: {top['label']}** — you're at {top['you']} "
                     f"vs an elite {top['elite']}.")
    # Item-control framing if RA is high on the list
    ra = next((l for l in levers if l["key"] == "ra_control"), None)
    if ra and ra in levers[:3]:
        lines.append(f"\nThe through-line is **item control**: your Red Armor share "
                     f"({ra['you']}) is below the {ra['elite']} elite mark. Duels are "
                     f"won on the RA timer — be standing on it when it spawns (every "
                     f"20s) with stack already, instead of fighting for it naked.")
    # Next levers
    rest = [l['label'] for l in levers[1:3]]
    if rest:
        lines.append(f"\nNext: {', '.join(rest)}. Fix the top lever first — the "
                     f"others tend to follow once you're fighting from stack.")
    lines.append("\n_(Auto-generated from your demo metrics. Richer AI narration "
                 "activates once the coaching model is connected.)_")
    return "\n".join(lines)


def narrate(display: str, mode: str, weakness: dict) -> dict:
    """Return {text, source}. source = 'llm' | 'template'."""
    payload = {
        "display": display,
        "mode": mode,
        "record": weakness.get("record", {}),
        "has_win_baseline": weakness.get("has_win_baseline", False),
        "matches_analyzed": weakness.get("matches_analyzed", 0),
        "levers": weakness.get("levers", []),
    }
    text = _llm_narrate(payload)
    if text:
        return {"text": text, "source": "llm", "model": MODEL}
    return {"text": _template_narrate(payload), "source": "template"}

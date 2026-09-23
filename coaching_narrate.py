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
import urllib.error

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("COACHING_MODEL", "claude-opus-5")
# Server-side refusal fallback (beta): on a policy decline the API re-runs the request on a
# fallback model inside the same call, so a coaching read never silently drops to the template.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
import sys


def _post(body: dict) -> str | None:
    """One Messages API call. Returns the text, or None after logging WHY it failed —
    the coach was falling back to the template with no trace of the cause (2026-09-20)."""
    body = {**body, "fallbacks": "default"}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": ANTHROPIC_KEY,
                 "anthropic-version": "2023-06-01", "anthropic-beta": FALLBACK_BETA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        if data.get("stop_reason") == "refusal":
            print(f"[coaching_narrate] refusal: {data.get('stop_details')}", file=sys.stderr, flush=True)
            return None
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return text or None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()[:400]
        except Exception:
            detail = ""
        print(f"[coaching_narrate] HTTP {e.code} from the Messages API (model {body.get('model')}): {detail}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[coaching_narrate] {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    return None


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
    return _post(body)


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


# ── 4on4 coach narration ─────────────────────────────────────────────────────
SYSTEM_4ON4 = (
    "You are a QuakeWorld 4on4 coach for a North American pickup community. You receive ONE "
    "player's computed report from their demos: their LEVEL (1 Survive, 2 Stack, 3 Fight, "
    "4 Control, 5 Carry — bands of +/- above an average player), the two GATES to the next level "
    "with their numbers, ONE focus lever with the player's number, their own wins-vs-losses split, "
    "their level's median and the next level's target, the RESULT of the previous prescription if "
    "there was one, the top levers, and their last games with the two metrics that explain each. "
    "RULES: (1) Use only the numbers given; never invent a metric, a number or a game. (2) One focus. "
    "Do not list other things to work on beyond one sentence. (3) If a previous prescription exists, "
    "open with its result honestly (hit, improved, flat, worse) in one or two sentences. (4) Explain the "
    "focus lever in Quake terms with the player's own numbers against their wins, their level and the "
    "next level, then give the drill as concrete in-game behaviour. (5) Register by level: levels 1-2 "
    "get three plain rules and short sentences, no theory; level 3 gets fight selection and stack talk; "
    "levels 4-5 get leverage, quad escorting and map control. (6) Reference the last games only through "
    "the cards given, and only where they show the focus lever. (7) Never generic advice: if a sentence "
    "could be sent to any player, cut it. Under 200 words for levels 1-2, under 300 otherwise. "
    "Markdown, no headings."
)


def _fours_payload(report: dict) -> dict:
    lv = report.get("level") or {}
    keep = ("key", "label", "you", "win", "loss", "level_median", "target", "is_gate", "why")
    return {
        "display": report.get("display"), "record": report.get("record"),
        "level": {k: lv.get(k) for k in ("level", "name", "blurb", "above_avg_pg", "games", "ready")},
        "gates": lv.get("gates"), "previous": report.get("previous"),
        "focus": {k: v for k, v in (report.get("focus") or {}).items() if k in ("lever", "label", "you_fmt", "target_fmt", "status", "games_since", "now_fmt", "why", "drill", "window_games")},
        "levers": [{k: l.get(k) for k in keep} for l in (report.get("levers") or [])[:3]],
        "games": [{k: g.get(k) for k in ("map", "win", "frags", "deaths", "agi", "above_avg", "explain")} for g in (report.get("games") or [])[:4]],
        "maps": (report.get("metrics") or {}).get("maps"),
    }


def _fours_template(report: dict) -> str:
    lv = report.get("level") or {}; f = report.get("focus"); prev = report.get("previous"); rec = report.get("record") or {}
    if not lv.get("placed"):
        return (f"**{report.get('display')}** has {lv.get('games', 0)} scored fours; a level needs 15. "
                "Play a few more pickup nights and the coach will place you.")
    lines = [f"**{report.get('display')}** — Level {lv['level']} {lv['name']}, {lv.get('above_avg_pg')} above average per game "
             f"over the last {lv.get('games')} fours ({rec.get('wins')}W/{rec.get('losses')}L)."]
    if prev and prev.get("status") != "pending":
        verdict = {"hit": "you hit it", "improved": "it moved the right way but is not there yet", "flat": "it did not move", "worse": "it went the wrong way"}[prev["status"]]
        lines.append(f"\nLast focus, **{prev['label']}**: {prev['at_issue_fmt']} at issue, target {prev['target_fmt']}, now {prev['now_fmt']} over {prev['games_since']} games — {verdict}.")
    if f:
        if f.get("status") == "in_progress":
            lines.append(f"\n**Focus stays: {f['label']}.** {f.get('games_since', 0)} of {f.get('window_games')} games in; you are at {f.get('now_fmt')} against a target of {f.get('target_fmt')}.")
        else:
            lines.append(f"\n**Your one focus: {f['label']}.** You are at {f.get('you_fmt')}; the next level sits at {f.get('target_fmt')}. {f.get('why')}")
        lines.append(f"\n**The drill:** {f.get('drill')}")
    g = lv.get("gates") or []
    if g:
        lines.append("\nGates to the next level: " + "; ".join(f"{x['label']} {x['you']} vs {x['target']} ({'passed' if x['passed'] else 'not yet'})" for x in g) + ".")
    lines.append("\n_(Auto-generated from your demo metrics. Richer AI narration activates once the coaching model is connected.)_")
    return "\n".join(lines)


def narrate_fours(report: dict) -> dict:
    """{text, source, reason} for the 4on4 coach. LLM when a key is configured and the call
    succeeds, else the template with reason = no_key | unplaced | model_error."""
    text = None; reason = None
    if not ANTHROPIC_KEY:
        reason = "no_key"
    elif not (report.get("level") or {}).get("placed"):
        reason = "unplaced"
    if ANTHROPIC_KEY and (report.get("level") or {}).get("placed"):
        payload = _fours_payload(report)
        lvl = (report.get("level") or {}).get("level") or 3
        body = {"model": MODEL, "max_tokens": 900, "system": SYSTEM_4ON4,
                "messages": [{"role": "user", "content": f"Player level {lvl}. Report JSON:\n{json.dumps(payload, indent=1, default=str)}\n\nWrite the coaching read."}]}
        text = _post(body)
        if not text:
            reason = "model_error"      # the cause is in the Cloud Run log ([coaching_narrate] ...)
    if text:
        return {"text": text, "source": "llm", "reason": None}
    return {"text": _fours_template(report), "source": "template", "reason": reason}

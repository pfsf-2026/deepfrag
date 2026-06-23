"""Match-preview narration for the KOTH 2on2 ladder.

Writes a fun, ESPN-gamecast-style 3-4 paragraph preview of an upcoming challenge,
grounded in the structured data we pass it (rosters + 1on1 divisions, ladder
records, head-to-head with per-map scores, individual stat lines from prior
meetings, and the model's prediction).

LLM (Claude) when ANTHROPIC_API_KEY is set; otherwise a deterministic multi-
paragraph template so the page always has a real write-up. Uses the Anthropic
Messages REST API directly via urllib (no SDK dependency) — mirrors
coaching_narrate.py. The caller is responsible for caching the result.
"""
from __future__ import annotations

import json
import os
import urllib.request

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("LADDER_PREVIEW_MODEL", os.environ.get("COACHING_MODEL", "claude-opus-4-8"))

SYSTEM = (
    "You are a QuakeWorld 2on2 ladder match-preview writer — think an ESPN gamecast "
    "preview, but for QuakeWorld team duels and written for the QW community. You are "
    "given structured DATA about an upcoming King-of-the-Hill 2v2 challenge: the two "
    "teams and their rosters (with 1on1 ratings/divisions and career W-L), each team's "
    "ladder record, their head-to-head history with per-map scores, individual player "
    "stat lines from that meeting, and a model PREDICTION (win %, the pick, moneyline, "
    "total-frags O/U, and predicted first-map picks). "
    "Write a vivid, sharp preview of 3-4 short paragraphs. RULES: "
    "(1) CRITICAL — every NUMBER you write (frags, efficiency, ratings, RL directs, "
    "scores, percentages, odds) MUST appear VERBATIM in the DATA. Do NOT compute, "
    "average, sum, round, or estimate any new number, and never invent players, "
    "matches or maps not present. If a stat isn't in the DATA, describe it in words "
    "instead of guessing a figure. "
    "(2) Lead with the matchup and what's at stake. "
    "(3) Cover the previous meeting(s) map-by-map and what swung them. "
    "(4) Tell individual-player storylines — who carried, surprising lines, and any "
    "rating-vs-results mismatch (e.g. a lower-division player outfragging a higher one). "
    "(5) Note recent form where the data shows it; if data is thin (e.g. only one prior "
    "meeting), say so honestly instead of padding. "
    "(6) End on the prediction with a concrete reason. "
    "Be a little playful and QW-flavored, but accurate. Use **bold** sparingly for "
    "names/keys. Separate paragraphs with a blank line. Target 200-340 words."
)


def _llm(ctx: dict) -> str | None:
    if not ANTHROPIC_KEY:
        return None
    body = {
        "model": MODEL,
        "max_tokens": 900,
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": "Write the match preview from this data:\n\n" + json.dumps(ctx, indent=2),
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
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
            return text or None
    except Exception:
        return None


def _template(ctx: dict) -> str:
    """Deterministic 3-paragraph fallback (still real prose, just not LLM)."""
    a, b = ctx["teams"]["challenger"], ctx["teams"]["defender"]
    pred = ctx["prediction"]
    h = ctx.get("head_to_head") or {}
    paras = []

    # 1 — the matchup + stakes + the pick
    paras.append(
        f"**{a['name']}** ({a['ladder_record']}) climb the ladder to challenge "
        f"**{b['name']}** ({b['ladder_record']}) in a best-of-three for rung {b['rung']}. "
        f"The model makes **{pred['pick']}** the pick at **{pred['pick_win_pct']}%** "
        f"— {pred['confidence']} confidence — with {a['tag']} at {pred['moneyline'].get(a['tag'],'—')} "
        f"and {b['tag']} at {pred['moneyline'].get(b['tag'],'—')} to win outright."
    )

    # 2 — the previous meeting
    if h.get("played"):
        maps_txt = ", ".join(f"{m['map']} {m['A_frags']}–{m['B_frags']}" for m in h.get("maps", []))
        paras.append(
            f"These two have history: {h.get('result') or 'they have met before'}. "
            f"Map by map it ran {maps_txt} — series frags "
            f"{h['series_frags'][a['tag']]}–{h['series_frags'][b['tag']]}. "
            "One series is a small sample, so treat the edge as a lean, not a lock."
        )
    else:
        paras.append(
            "There's no prior meeting on record, so this is fresh ground — the lean "
            "comes from each side's ladder form rather than a head-to-head."
        )

    # 3 — player storyline
    lines = ctx.get("player_lines_from_meeting") or []
    if lines:
        top = max(lines, key=lambda p: p.get("frags_per_map", 0))
        paras.append(
            f"Watch **{top['name']}** ({top['team_tag']}) — {top['frags_per_map']} frags/map "
            f"at {top['eff']}% efficiency in the meeting led all players. "
            f"The model's first-map reads: {a['tag']} toward {pred['first_picks'].get(a['tag'],'?')}, "
            f"{b['tag']} toward {pred['first_picks'].get(b['tag'],'?')}, with the total set at "
            f"{pred['total_frags_ou']} frags."
        )
    else:
        paras.append(
            f"First-map reads: {a['tag']} toward {pred['first_picks'].get(a['tag'],'?')}, "
            f"{b['tag']} toward {pred['first_picks'].get(b['tag'],'?')}; total set at "
            f"{pred['total_frags_ou']} frags."
        )
    return "\n\n".join(paras)


def narrate(ctx: dict) -> dict:
    """Return {'text', 'source'}. LLM when available, else template."""
    txt = _llm(ctx)
    if txt:
        return {"text": txt, "source": "llm"}
    return {"text": _template(ctx), "source": "template"}

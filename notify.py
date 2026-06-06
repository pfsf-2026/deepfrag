#!/usr/bin/env python3
"""Discord webhook notifications for the Speakeasy ladder.

Best-effort: every send is wrapped so a webhook outage NEVER breaks the API
call that triggered it. Posts to DISCORD_WEBHOOK_URL (a channel webhook, not the
bot/OAuth app). Set it in Cloud Run env to enable; unset = silently no-op.

Events: challenge issued, result reported (with movement), forfeit, KotH change.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone


def fmt_et(iso: str | None) -> str:
    """Format an ISO-8601 UTC timestamp as US Eastern (this is an NA ladder).
    Falls back gracefully if tz data is unavailable or the input is odd."""
    if not iso:
        return "TBD"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            et = dt.astimezone(ZoneInfo("America/New_York"))
            tag = et.tzname() or "ET"   # EST / EDT
        except Exception:
            et, tag = dt, "UTC"
        # e.g. "Mon Jun 9, 9:00 PM EDT" (strip leading zeros, portable enough on Linux)
        return et.strftime("%a %b %-d, %-I:%M %p ") + tag
    except Exception:
        return str(iso)

# DeepFrag teal, matches the site accent.
COLOR = 0x14E6C0
COLOR_WIN = 0x22C55E
COLOR_WARN = 0xF59E0B
COLOR_CHALLENGE = 0xEF4444
LADDER_URL = "https://deepfrag.pages.dev/ladder"


def _url() -> str | None:
    return os.environ.get("DISCORD_WEBHOOK_URL")


def send(content: str | None = None, embed: dict | None = None) -> bool:
    """Post to the configured webhook. Returns True on 2xx, False otherwise (or
    if no webhook configured). Never raises."""
    url = _url()
    if not url:
        return False
    payload: dict = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    if not payload:
        return False
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            # Discord webhooks sit behind Cloudflare, which 403s the default
            # python-urllib User-Agent with "error code: 1010". Send a real UA
            # (same gotcha as the OAuth token call) or the post silently fails.
            headers={"Content-Type": "application/json",
                     "User-Agent": "DeepFrag-KOTH/1.0 (+https://deepfrag.pages.dev)"},
            method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _embed(title: str, description: str, color: int) -> dict:
    return {"title": title, "description": description, "color": color,
            "url": LADDER_URL}


# ── event builders ───────────────────────────────────────────────────────────

def challenge_issued(challenger: str, challenged: str, rungs_up: int, deadline_iso: str | None,
                     mention: str | None = None):
    by = f"in by **{deadline_iso[:10]}**" if deadline_iso else "soon"
    return send(content=mention or None, embed=_embed(
        "⚔️ New challenge",
        f"**{challenger}** challenged **{challenged}** "
        f"({rungs_up} rung{'s' if rungs_up != 1 else ''} up).\nPlay {by}.",
        COLOR_CHALLENGE))


def ladder_signup(player: str):
    """A player linked their profile / joined the ladder pool."""
    return send(embed=_embed("🎮 New ladder signup",
                             f"**{player}** signed up for the KOTH ladder.", COLOR))


def team_signup(name: str, tag: str | None, players: list, pending: bool = True):
    """A captain registered a team (players, name, tag)."""
    title = f"[{tag}] {name}" if tag else name
    roster = ", ".join(players) if players else "—"
    desc = f"**{title}**\nRoster: {roster}"
    if pending:
        desc += "\n_Awaiting admin approval._"
    return send(embed=_embed("🆕 New team signup", desc, COLOR))


def availability_posted(challenger: str, challenged: str, n_slots: int, mention: str | None = None):
    """Challenger posted availability — nudge the challenged team to pick a time."""
    return send(content=mention or None, embed=_embed(
        "🗓️ Availability posted",
        f"**{challenger}** posted {n_slots} time slot{'s' if n_slots != 1 else ''} vs "
        f"**{challenged}**.\n**{challenged}** — pick a time on the ladder.",
        COLOR_CHALLENGE))


def game_scheduled(team_a: str, team_b: str, when: str | None, server: str | None,
                   mention: str | None = None):
    """A match was scheduled. Time shown in US Eastern (NA ladder)."""
    bits = [f"**{team_a}** vs **{team_b}**", f"🗓️ {fmt_et(when)}"]
    if server:
        bits.append(f"🖥️ {server}")
    return send(content=mention or None, embed=_embed("📅 Game scheduled", "\n".join(bits), COLOR_CHALLENGE))


def result_posted(winner: str, loser: str, maps_line: str | None = None,
                  movement: str | None = None, score: str | None = None, mention: str | None = None):
    """Bo3 result: per-map scoreline + the ladder movement it caused."""
    head = f"**{winner}** def. **{loser}**" + (f" — {score}" if score else "")
    parts = [head]
    if maps_line:
        parts.append(maps_line)
    parts.append(movement or "Ranks unchanged.")
    return send(content=mention or None, embed=_embed("🏆 Game result", "\n".join(parts), COLOR_WIN))


def forfeit_posted(challenged: str):
    return send(embed=_embed(
        "⏳ Forfeit",
        f"**{challenged}** didn't play in time and drops a rung.",
        COLOR_WARN))


def koth_changed(team: str):
    return send(embed=_embed(
        "👑 New King of the Hill",
        f"**{team}** takes the top of the ladder!",
        COLOR))

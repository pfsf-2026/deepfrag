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
    """challenger/challenged are team LABELS ('**Name** (@p1 @p2)'), challenger
    first. Pings live in content."""
    by = f" Play by **{deadline_iso[:10]}**." if deadline_iso else ""
    ups = f" ({rungs_up} rung{'s' if rungs_up != 1 else ''} up)"
    return send(content=f"⚔️ {challenger} challenged {challenged}{ups}.{by}")


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


def match_proposal(proposer: str, other: str, slots_iso: list, *, initial: bool,
                   challenger: str, challenged: str, rungs_up: int | None = None,
                   deadline_iso: str | None = None, mention: str | None = None):
    """One combined message when a team posts times.

    - initial (the challenger's opening proposal): announce the challenge AND list
      the proposed times in a single post — we hold the challenge ping until now.
    - otherwise (a counter-proposal): "new times suggested", nudge the other team.

    All times shown in US Eastern (NA ladder).
    """
    shown = slots_iso[:12]
    times = "\n".join(f"• {fmt_et(s)}" for s in shown)
    if len(slots_iso) > len(shown):
        times += f"\n…and {len(slots_iso) - len(shown)} more"
    # proposer/other/challenger/challenged are team LABELS (name + parens pings)
    if initial:
        ups = f" ({rungs_up} rung{'s' if rungs_up != 1 else ''} up)" if rungs_up else ""
        by = f" Play by **{deadline_iso[:10]}**." if deadline_iso else ""
        content = (f"⚔️ {challenger} challenged {challenged}{ups}.{by}\n\n"
                   f"{challenger} can play:\n{times}\n\n"
                   f"{challenged} — pick a time (or suggest your own) on the ladder.")
    else:
        content = (f"🔄 {proposer} suggested new times vs {other}:\n{times}\n\n"
                   f"{other} — pick one (or counter) on the ladder.")
    return send(content=content)


def game_scheduled(team_a: str, team_b: str, when: str | None, server: str | None,
                   mention: str | None = None):
    """Match scheduled. team_a/team_b are LABELS, challenger (team_a) first."""
    extra = f"\n🖥️ {server}" if server else ""
    return send(content=f"📅 {team_a} vs {team_b}\n🗓️ {fmt_et(when)}{extra}")


def result_posted(winner: str, loser: str, maps_line: str | None = None,
                  movement: str | None = None, score: str | None = None, mention: str | None = None):
    """Bo3 result: per-map scoreline + the ladder movement it caused."""
    head = f"**{winner}** def. **{loser}**" + (f" — {score}" if score else "")
    parts = [head]
    if maps_line:
        parts.append(maps_line)
    parts.append(movement or "Ranks unchanged.")
    return send(content=mention or None, embed=_embed("🏆 Game result", "\n".join(parts), COLOR_WIN))


def result_grouped(winner: str, winner_ping: str, loser: str, loser_ping: str,
                   score: str | None = None, maps_line: str | None = None,
                   movement: str | None = None, preview: bool = False):
    """Bo3 result, WINNER-first, players grouped + pinged BY TEAM:
        🏆 Winner (@a @b) def. Loser (@c @d) — 2-0
    Pings live in `content` (Discord embeds don't trigger mentions); the embed
    carries the per-map + movement breakdown. score/maps must already be
    winner-first (the caller orients them)."""
    wp = f" ({winner_ping})" if winner_ping else ""
    lp = f" ({loser_ping})" if loser_ping else ""
    head = f"**{winner}**{wp} def. **{loser}**{lp}" + (f" — **{score}**" if score else "")
    content = ("🧪 *result format preview*\n" if preview else "") + "🏆 " + head
    desc = []
    if maps_line:
        desc.append(maps_line)
    desc.append(movement or "Ranks unchanged.")
    return send(content=content, embed=_embed("🏆 Game result", "\n".join(desc), COLOR_WIN))


def forfeit_posted(challenged: str, challenger: str | None = None):
    """challenged/challenger are LABELS. Challenged drops; challenger takes it."""
    tail = f" — {challenger} takes the position." if challenger else " and drops a rung."
    return send(content=f"⏳ {challenged} didn't play in time{tail}")


def challenge_withdrawn(challenger: str, challenged: str, mention: str | None = None):
    """The challenger pulled their (not-yet-scheduled) challenge. Both teams free.
    challenger/challenged are LABELS, challenger first."""
    return send(content=f"↩️ {challenger} withdrew their challenge against {challenged}. "
                        f"Both teams are free again.")


def match_reminder(team_a: str, team_b: str, when: str | None, server: str | None,
                   kind: str = "1h", mention: str | None = None):
    """Upcoming-match reminder. team_a/team_b are LABELS, challenger first."""
    head = "🔴 Match in ~10 minutes" if kind == "10m" else "🔔 Match in ~1 hour"
    extra = f"\n🖥️ {server}" if server else ""
    return send(content=f"{head}\n{team_a} vs {team_b}\n🗓️ {fmt_et(when)}{extra}")


def match_rescheduled(team_a: str, team_b: str, when: str | None, server: str | None,
                      mention: str | None = None):
    """An admin moved a scheduled match. team_a/team_b are LABELS, challenger first."""
    extra = f"\n🖥️ {server}" if server else ""
    return send(content=f"🔁 Match rescheduled\n{team_a} vs {team_b}\n🗓️ New time: **{fmt_et(when)}**{extra}")


def challenge_overdue(team_a: str, team_b: str, deadline: str | None, mention: str | None = None):
    """A challenge blew past its play-by deadline. team_a/team_b are LABELS."""
    return send(content=f"⏳ Challenge overdue — {team_a} vs {team_b} wasn't played by "
                        f"{fmt_et(deadline)}.\nAdmins — review (forfeit the challenged team, or extend).")


def data_health_alert(problems: list, latest: str | None):
    """Pipeline-stall alert (ingestion stale or canonicalize behind). Quiet (no
    @mention) — it posts to the channel for admins to see."""
    desc = ("**The DeepFrag data pipeline looks stalled:**\n\n"
            + "\n".join(f"• {p}" for p in problems)
            + f"\n\nNewest match in DB: `{latest or 'unknown'}`\n"
            "Check `/api/debug/ingest`; the 2h sync + canonicalize should self-heal.")
    return send(embed=_embed("🚨 Data health alert", desc, COLOR_WARN))


def support_ticket(num: int, area: str | None, title: str, who: str | None):
    """New support ticket — surface to admins in the channel."""
    return send(embed=_embed(
        f"🆘 Support ticket #{num}",
        f"**{title}**\nArea: {area or '—'} · From: {who or 'anonymous'}",
        COLOR_WARN))


def koth_changed(team: str):
    """team is a LABEL ('**Name** (@p1 @p2)')."""
    return send(content=f"👑 {team} takes the top of the ladder — new King of the Hill!")

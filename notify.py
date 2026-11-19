#!/usr/bin/env python3
"""Discord webhook notifications for the Speakeasy ladder.

Best-effort: every send is wrapped so a webhook outage NEVER breaks the API
call that triggered it. Posts to DISCORD_WEBHOOK_URL (a channel webhook, not the
bot/OAuth app). Set it in Cloud Run env to enable; unset = silently no-op.

Events: challenge issued, result reported (with movement), forfeit, KotH change.
"""
from __future__ import annotations

import contextvars
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

def ts(iso, style: str = "F") -> str:
    """Discord timestamp markup (what sesh.fyi/timestamp generates): Discord renders it in each
    reader's OWN time zone (Peter, 2026-11-19). Styles: F 'Thursday, November 19, 2026 9:00 PM',
    f without the weekday, D date, t time, R relative ('in 3 hours'). Falls back to ET text."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return f"<t:{int(dt.timestamp())}:{style}>"
    except Exception:
        return fmt_et(iso)


def when(iso: str | None) -> str:
    """A match time for Discord: local full date + relative ('… (in 2 hours)')."""
    return f"{ts(iso)} ({ts(iso, 'R')})" if iso else "TBD"


def _et(iso):
    """ISO instant → aware datetime in US Eastern (None if unparseable)."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return None


def fmt_day_et(iso: str | None) -> str:
    """'Sat Oct 3' — a deadline needs the day, not the minute."""
    et = _et(iso)
    return et.strftime("%a %b %-d") if et else (str(iso)[:10] if iso else "TBD")


def _clock(et) -> str:
    """'9:30 PM' / '10 PM'."""
    return et.strftime("%-I:%M %p").replace(":00", "")


def fmt_slots(slots_iso: list, max_days: int = 7) -> str:
    """Offered times, one line per EVENING, as Discord timestamps so each reader sees their
    own zone ('Thursday, November 19, 2026 9:30 PM, 10:00 PM'). Evenings are grouped in ET
    with 12am–6am riding with the evening before. A run of 3+ half-hour slots collapses to
    a range ('8:00 PM – 10:30 PM')."""
    from datetime import timedelta
    days: dict = {}
    for s in sorted(str(x) for x in slots_iso or []):
        et = _et(s)
        if not et:
            continue
        key = (et - timedelta(hours=6)).date()
        days.setdefault(key, []).append(et)
    lines = []
    for key in sorted(days)[:max_days]:
        ts, parts, i = days[key], [], 0
        while i < len(ts):
            j = i
            while j + 1 < len(ts) and (ts[j + 1] - ts[j]) == timedelta(minutes=30):
                j += 1
            parts.append(f"{_t(ts[i])} – {_t(ts[j])}" if j - i >= 2 else ", ".join(_t(x) for x in ts[i:j + 1]))
            i = j + 1
        first = days[key][0]
        parts[0] = f"<t:{int(first.timestamp())}:F>" + parts[0][len(_t(first)):]
        lines.append(", ".join(parts))
    if len(days) > max_days:
        lines.append(f"…and {len(days) - max_days} more day(s)")
    return "\n".join(lines)


def _t(dt) -> str:
    return f"<t:{int(dt.timestamp())}:t>"


def _name(label: str) -> str:
    """'**Name** (@p1 @p2)' → '**Name**' — for the second mention in a post, so nobody is pinged twice."""
    import re as _re
    return _re.sub(r"\s*\(<@[^)]*\)\s*$", "", label or "").strip() or (label or "")


# DeepFrag teal, matches the site accent.
COLOR = 0x14E6C0
COLOR_WIN = 0x22C55E
COLOR_WARN = 0xF59E0B
COLOR_CHALLENGE = 0xEF4444
LADDER_URL = "https://deepfrag.pages.dev/ladder"


# Channel routing (2026-09-24): the 1v1 ladder has its own Discord channel. Handlers
# call set_route(mode) once they know which ladder they're acting on (api._notify_route);
# every send() in that request/tick row then goes to that ladder's webhook. A mode with a
# dedicated webhook NEVER falls back to the 2v2 channel (Peter, 2026-09-24): if its env var
# is unset the post is simply dropped. Modes without a dedicated webhook use
# DISCORD_WEBHOOK_URL. FastAPI runs each sync handler in a copied context, so a route set
# in one request never leaks.
_ROUTE: contextvars.ContextVar = contextvars.ContextVar("deepfrag_notify_route", default=None)
ROUTES = {"1on1": "DISCORD_WEBHOOK_URL_1V1"}
LADDER_QUERY = {"1on1": "?l=1v1"}


def set_route(mode: str | None) -> None:
    _ROUTE.set(mode)


def current_route() -> str | None:
    return _ROUTE.get()


def unit(plural: bool = False, cap: bool = False) -> str:
    """'team'/'teams' on team ladders, 'player'/'players' on the 1v1 ladder (by the current route)."""
    w = ("players" if plural else "player") if _ROUTE.get() == "1on1" else ("teams" if plural else "team")
    return w.capitalize() if cap else w


def _url() -> str | None:
    env = ROUTES.get(_ROUTE.get() or "")
    if env:
        return os.environ.get(env) or None      # dedicated channel only; unset = no post
    return os.environ.get("DISCORD_WEBHOOK_URL")


def ladder_url() -> str:
    return LADDER_URL + LADDER_QUERY.get(_ROUTE.get() or "", "")


def challenge_link(challenge_id: int | None, text: str = "Schedule it") -> str:
    """'\n🔗 [Schedule it](<…/ladder?l=1v1&c=158>)': opens that challenge's scheduler on
    DeepFrag (players in it can pick or offer times; anyone else, unless an admin, only views).
    The angle brackets stop Discord unfurling a preview card. Empty when no id."""
    if not challenge_id:
        return ""
    u = ladder_url()
    return f"\n🔗 [{text}](<{u}{'&' if '?' in u else '?'}c={int(challenge_id)}>)"


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
            url + ("&" if "?" in url else "?") + "wait=true",   # wait=true → Discord returns the message (we keep its id for edits)
            data=json.dumps(payload).encode(),
            # Discord webhooks sit behind Cloudflare, which 403s the default
            # python-urllib User-Agent with "error code: 1010". Send a real UA
            # (same gotcha as the OAuth token call) or the post silently fails.
            headers={"Content-Type": "application/json",
                     "User-Agent": "DeepFrag-KOTH/1.0 (+https://deepfrag.pages.dev)"},
            method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            ok = 200 <= r.status < 300
            try:
                _LAST_ID.set(str(json.loads(r.read() or b"{}").get("id") or ""))
            except Exception:
                pass
            return ok
    except Exception:
        return False


_LAST_ID: contextvars.ContextVar = contextvars.ContextVar("deepfrag_notify_last_id", default="")


def last_message_id() -> str:
    """Discord id of the last message send() posted in this request (empty if none)."""
    return _LAST_ID.get()


def edit(message_id: str, content: str) -> bool:
    """Edit a previous webhook post (same channel as the current route). Never raises."""
    url = _url()
    if not url or not message_id:
        return False
    try:
        req = urllib.request.Request(
            url.split("?")[0] + f"/messages/{message_id}", data=json.dumps({"content": content}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "DeepFrag-KOTH/1.0 (+https://deepfrag.pages.dev)"},
            method="PATCH")
        with urllib.request.urlopen(req, timeout=8) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _embed(title: str, description: str, color: int) -> dict:
    return {"title": title, "description": description, "color": color,
            "url": ladder_url()}


# ── event builders ───────────────────────────────────────────────────────────

def challenge_issued(challenger: str, challenged: str, rungs_up: int, deadline_iso: str | None,
                     mention: str | None = None):
    """challenger/challenged are team LABELS ('**Name** (@p1 @p2)'), challenger
    first. Pings live in content."""
    by = f" · play by {ts(deadline_iso, 'f')}" if deadline_iso else ""
    ups = f" ({rungs_up} rung{'s' if rungs_up != 1 else ''} up)"
    return send(content=f"⚔️ {challenger} challenged {challenged}{ups}{by}")


def ladder_signup(player: str):
    """A player linked their profile / joined the ladder pool."""
    return send(embed=_embed("🎮 New ladder signup",
                             f"**{player}** signed up for the KOTH ladder.", COLOR))


def team_signup(name: str, tag: str | None, players: list, pending: bool = True,
                ladder: str | None = None, solo: bool = False, rung: int | None = None):
    """A captain registered a team (players, name, tag). On a 1v1 ladder (solo=True)
    the entry is one player, registered straight onto the board at `rung`."""
    title = f"[{tag}] {name}" if tag else name
    roster = ", ".join(players) if players else "—"
    desc = f"**{title}**" + ("" if solo else f"\nRoster: {roster}")
    if ladder:
        desc += f"\nLadder: {ladder}"
    if rung:
        desc += f"\nOn the board at rung {rung}."
    if pending:
        desc += "\n_Awaiting admin approval._"
    return send(embed=_embed("🆕 New ladder signup" if solo else "🆕 New team signup", desc, COLOR))


def challenge_prescheduled(challenger: str, challenged: str, rungs_up: int, when_iso: str, deadline_iso: str | None,
                           challenge_id: int | None = None):
    """Challenge issued WITH an already-agreed time (2026-09-29: players DM each other first).
    One post: the challenge and its scheduled time."""
    # challenger/challenged are LABELS (already bold, with pings). One time only in this
    # post — the play-by deadline next to an agreed time just reads as a second match time.
    rung = f"{rungs_up} rung{'s' if rungs_up != 1 else ''} up"
    return send(content=f"⚔️ {challenger} challenged {challenged} ({rung}) — scheduled **{when(when_iso)}**"
                        + challenge_link(challenge_id, "Match details"))


def match_proposal(proposer: str, other: str, slots_iso: list, *, initial: bool,
                   challenger: str, challenged: str, rungs_up: int | None = None,
                   deadline_iso: str | None = None, mention: str | None = None,
                   challenge_id: int | None = None):
    """One combined message when a team posts times.

    - initial (the challenger's opening proposal): announce the challenge AND list
      the proposed times in a single post — we hold the challenge ping until now.
    - otherwise (a counter-proposal): "new times suggested", nudge the other team.

    Times are Discord timestamps (each reader's own zone), with a link to pick one.
    """
    # Terse on purpose (Peter, 2026-10-02): one header line, then one line per evening.
    # proposer/other/challenger/challenged are team LABELS (name + parens pings); the
    # header pings, later mentions use the bare name.
    times = fmt_slots(slots_iso)
    if initial:
        ups = f" ({rungs_up} rung{'s' if rungs_up != 1 else ''} up)" if rungs_up else ""
        by = f" · play by {ts(deadline_iso, 'f')}" if deadline_iso else ""
        content = (f"⚔️ {challenger} challenged {challenged}{ups}{by}\n"
                   f"Times offered (your local time) — pick one:\n{times}")
    else:
        content = f"🔄 {_name(proposer)} offered new times — {other}, pick one (your local time):\n{times}"
    return send(content=content + challenge_link(challenge_id, "Pick a time"))


def game_scheduled(a_name: str, a_ping: str, b_name: str, b_ping: str,
                   when_iso: str | None, server: str | None = None, mention: str | None = None,
                   challenge_id: int | None = None):
    """Match scheduled (challenger first). Clean two-line: names+time, then pings."""
    meta = when(when_iso) + (f" · {server}" if server else "")
    out = f"✅ Scheduled: **{a_name}** vs **{b_name}** — {meta}"
    if a_ping or b_ping:
        out += f"\n{a_ping or '—'}  vs  {b_ping or '—'}"
    return send(content=out + challenge_link(challenge_id, "Match details / reschedule"))


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


def forfeit_posted(challenged: str, challenger: str | None = None, drop: int = 1,
                   challenged_name: str | None = None, challenged_rung: int | None = None,
                   climber_name: str | None = None, climber_rung: int | None = None):
    """challenged/challenger are LABELS (they ping); the *_name args are plain names for the
    second mention. The challenged side drops `drop` rungs and the climber, normally the
    challenger, takes the vacated rung. 2026-10-29: the message used to say "drops a rung"
    for every forfeit and never named the challenger."""
    if not challenger:
        return send(content=f"⏳ {challenged} didn't play in time and drops a rung.")
    rungs = "a rung" if drop == 1 else f"{drop} rungs"
    who = challenged_name or "They"
    moves = f" {who} drops {rungs}" + (f" to #{challenged_rung}" if challenged_rung else "")
    if climber_name and climber_rung:
        moves += f", {climber_name} moves up to #{climber_rung}"
    return send(content=f"⏳ {challenged} didn't play {challenger} in time: a walkover, and{moves}.")


def challenge_withdrawn(challenger: str, challenged: str, mention: str | None = None):
    """The challenger pulled their (not-yet-scheduled) challenge. Both teams free.
    challenger/challenged are LABELS, challenger first."""
    return send(content=f"↩️ {challenger} withdrew the challenge vs {challenged}.")


def challenge_cancelled(challenger: str, challenged: str):
    """An admin cancelled the challenge: nobody moves, both are free. LABELS, challenger first."""
    return send(content=f"🚫 The challenge {challenger} vs {challenged} was cancelled. No rungs change; "
                        f"both {unit(plural=True)} are free to challenge again.")


def match_reminder(a_name: str, a_ping: str, b_name: str, b_ping: str,
                   when_iso: str | None, server: str | None = None, kind: str = "1h",
                   mention: str | None = None, challenge_id: int | None = None):
    """Upcoming-match reminder (challenger first). Day-of @ping cadence."""
    head = "🔴 Starting in ~10 min" if kind == "10m" else "🔔 Match in ~1 hour"
    meta = (ts(when_iso, "t") if when_iso else "TBD") + (f" · {server}" if server else "")
    out = f"{head} — **{a_name}** vs **{b_name}** · {meta}"
    if a_ping or b_ping:
        out += f"\n{a_ping or '—'}  vs  {b_ping or '—'}"
    return send(content=out + challenge_link(challenge_id, "Match details"))


def match_rescheduled(team_a: str, team_b: str, when_iso: str | None, server: str | None,
                      mention: str | None = None, note: str | None = None, was: str | None = None,
                      challenge_id: int | None = None):
    """A scheduled match moved (admin, or the two sides agreeing a new time — `note`
    says who). team_a/team_b are LABELS, challenger first. `was` = the old time, shown
    so nobody has to guess which of two times is the live one."""
    # One line (Peter, 2026-10-02). `note` is accepted for old callers but no longer printed.
    extra = f" (was {ts(was, 'f')})" if was else ""
    extra += f" · {server}" if server else ""
    return send(content=f"🔁 {team_a} vs {team_b} moved to **{when(when_iso)}**{extra}"
                        + challenge_link(challenge_id, "Match details / reschedule"))


def challenge_overdue(team_a: str, team_b: str, deadline: str | None, mention: str | None = None,
                      challenge_id: int | None = None):
    """A challenge blew past its play-by deadline. team_a/team_b are LABELS."""
    due = ts(deadline, "f") if deadline else "TBD"
    return send(content=f"⏳ Overdue: {team_a} vs {team_b} (due {due}). Admins: forfeit or extend."
                        + challenge_link(challenge_id, "Open the challenge"))


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

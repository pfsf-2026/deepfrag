"""Per-player Game Report for one 4on4 game, built from the mvd-api (no demo on disk).

    ov = fetch_overview(gid, get)                   # get(path) -> parsed JSON or None
    key = resolve_me(ov, [raw_name, display, cid])  # the player's name as the demo spells it
    data = fetch_rest(gid, get, key)
    report = compute(ov, data, key, gid, map_short)

The report is the frame Peter asked for on 2026-10-17: a summary line, 2-minute time
blocks, highlights, lowlights, and 2-3 "rewinds" — moments where a better series of
decisions was on the table — each with the team's MM2 in the 20 s before, the answer,
the MM2 line to send, and a hub.quakeworld.nu deep link (from/to are demo-relative
seconds: match time + demoOffset). Facts and rules: docs/coaching_doctrine.md. Spawn
points and the per-spawn survival tables: spawn_rooms.py (the 60-game 1 s study).
Everything here is 4on4; a duel report would need its own lowlight rules."""
from __future__ import annotations

import bisect
import collections
import math
import re
import urllib.parse

from duel_adv import _eff, _Series
import spawn_rooms as SR

VERSION = 15
# P(killer wins | stack edge at first contact, power-up state): 2,445 Den/LA fours, 1,025,964 enemy frags
# (tools/mvd_features/fight_table_4on4.json, 2026-09-11). Same table the Advanced Stats pages use.
FIGHT_TABLE = {"no powerup": [[-200, 0.06], [-70, 0.201], [0, 0.5], [70, 0.799], [200, 0.94]],
               "has powerup": [[-200, 0.534], [-70, 0.696], [0, 0.889], [70, 0.955], [200, 0.981]],
               "vs powerup": [[-200, 0.019], [-70, 0.045], [0, 0.111], [70, 0.304], [200, 0.466]],
               "both": [[-200, 0.324], [-70, 0.418], [0, 0.5], [70, 0.582], [200, 0.676]]}


def pwin(edge, state="no powerup"):
    pts = FIGHT_TABLE[state]
    if edge <= pts[0][0]:
        return pts[0][1]
    if edge >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= edge <= x1:
            return y0 + (y1 - y0) * (edge - x0) / (x1 - x0)
    return 0.5
HUB = "https://hub.quakeworld.nu/games/?gameId={gid}&from={f}&to={t}&track={uid}"
MAJOR = ("ra", "ya", "ga", "mh", "rl", "lg", "quad", "pent", "ring")
NEAR = 700            # units: "with" a teammate / "into" enemies
CHAIN_MS = 14000      # a life shorter than this after a spawn is chained
EMPTY_DMG = 50        # a life that dealt less than this, no frag, no major item = empty
STREAM = "pos,h,a,at,sp,d,rl,lg,q,rk,cl"


def _clean_mm2(line):
    """A teamsay line as a person reads it: KTX macros that did not expand (%E, %e, %l …) dropped."""
    return re.sub(r"\s*%[A-Za-z]\b", "", line or "").strip()


def item_state(it, t):
    """One item at match time t: ('up', 0, None) | ('in', seconds, None) | ('taken', seconds ago, by)."""
    ph = sorted((q for q in (it.get("phases") or []) if q.get("availableFrom") is not None), key=lambda q: q["availableFrom"])
    cur = next((q for q in ph if q["availableFrom"] <= t and (q.get("takenAt") is None or q["takenAt"] > t)), None)
    if cur:
        return ("up", 0, None)
    nxt = next((q for q in ph if q["availableFrom"] > t), None)
    last = next((q for q in reversed(ph) if q.get("takenAt") is not None and q["takenAt"] <= t), None)
    if nxt:
        left = round((nxt["availableFrom"] - t) / 1000)
        if left <= 0:
            return ("up", 0, None)
        return ("in", left, last.get("takenBy") if last else None)
    if last:
        return ("taken", round((t - last["takenAt"]) / 1000), last.get("takenBy"))
    return ("unknown", 0, None)


def mmss(ms):
    ms = max(0, int(ms))
    return f"{ms // 60000}:{(ms // 1000) % 60:02d}"


# ── fetch ────────────────────────────────────────────────────────────────────
def fetch_overview(gid, get):
    return get(f"/v1/demos/gameId:{gid}/overview")


def resolve_me(ov, candidates):
    """The demo's spelling of this player. Tries exact / case-insensitive / collapsed
    (coaching._resolve_player_key) for each candidate: raw players.player_name first,
    then display name, then canonical id."""
    import coaching as C
    keys = [p["name"] for p in (ov.get("players") or [])]
    for c in candidates:
        if not c:
            continue
        k = C._resolve_player_key(c, keys)
        if k:
            return k
    return None


def fetch_rest(gid, get, me_key):
    base = f"/v1/demos/gameId:{gid}"
    q = urllib.parse.quote(me_key, safe="")
    return {"me": get(f"{base}/stream-slice?from=0&to=99999&fields={STREAM}&players={q}"),
            "buckets": get(f"{base}/buckets?windowMs=1000&fields=pos,h,a,at,rl,lg,rk"),
            "frags": get(f"{base}/frags"), "damage": get(f"{base}/damage"), "items": get(f"{base}/items"),
            "pickups": get(f"{base}/weapon-pickups"), "backpacks": get(f"{base}/backpacks"), "chat": get(f"{base}/chat?types=teamsay"),
            "events": get(f"{base}/events?types=powerup,streak"), "loctable": get(f"{base}/loc-table")}


# ── compute ──────────────────────────────────────────────────────────────────
def compute(ov, data, me, gid, mp):
    """The report dict. `me` is the demo spelling, `mp` the short map name (dm3 …)."""
    if not data or not data.get("me") or not data.get("buckets"):
        return None
    end = int(ov.get("matchEnd") or ov.get("duration") or 0)
    if end < 240000:
        return None
    off = int(((ov.get("timing") or {}).get("demoOffset")) or 0)
    wall0 = int(((ov.get("timing") or {}).get("demoStartUnixMs")) or 0)
    wall = (lambda t: wall0 + off + int(t)) if wall0 else (lambda t: None)
    uids = ov.get("playerUserIDs") or {}
    uid = uids.get(me)
    team_of = {p["name"]: p.get("team") or "" for p in (ov.get("players") or [])}
    if me not in team_of:
        return None
    team = team_of[me]
    mates = [n for n, t in team_of.items() if t == team and n != me]
    foes = [n for n, t in team_of.items() if t != team]
    loctab = (data.get("loctable") or {}).get("locTable") or []
    locname = lambda i: SR.room_name(loctab[i]) if isinstance(i, int) and 0 <= i < len(loctab) and loctab[i] else "?"

    def hub(t0, t1=None):
        if uid is None:
            return None
        f = max(0, int((t0 - 8000 + off) / 1000)); t = int(((t1 if t1 is not None else t0) + 4000 + off) / 1000)
        return HUB.format(gid=gid, f=f, t=t, uid=uid)

    # one-second state for everybody (buckets): x,y,z,h,a,at,rl,alive
    B = {n: v for n, v in ((data["buckets"] or {}).get("players") or {}).items() if n in team_of}
    nsec = max((len(v.get("alive") or []) for v in B.values()), default=0)

    def bval(n, k, s, d=0):
        a = (B.get(n) or {}).get(k)
        return a[s] if a and 0 <= s < len(a) and a[s] is not None else d

    def bxyz(n, s):
        return (bval(n, "x", s), bval(n, "y", s), bval(n, "z", s))

    def margin(s):
        st = {True: 0.0, False: 0.0}; rl = {True: 0, False: 0}
        for n in team_of:
            if not bval(n, "alive", s):
                continue
            k = team_of[n] == team
            st[k] += _eff(bval(n, "h", s, 100), bval(n, "a", s, 0), bval(n, "at", s, "") or "")
            rl[k] += 1 if bval(n, "rl", s) else 0
        return (st[False] - st[True]) + 100 * (rl[False] - rl[True])
    THR = SR.LOCK_THR.get(mp, 350)
    M = [margin(s) for s in range(nsec)]
    locked_at = lambda ms: 0 <= ms // 1000 < nsec and M[ms // 1000] >= THR

    # my full-resolution stream
    P = next((p for p in (data["me"].get("players") or []) if p.get("name") == me), None)
    if not P or not P.get("pos") or not P["pos"].get("t"):
        return None
    pos = P["pos"]; T = pos["t"]
    H, A, AT = _Series(P.get("h"), 100), _Series(P.get("a"), 0), _Series(P.get("at"), "")
    IV = {k: [(x["s"], x["e"]) for x in (P.get(k) or [])] for k in ("rl", "lg", "q")}
    RK = _Series(P.get("rk"), 0)                      # rockets in hand: an RL with none is a shotgun
    has = lambda k, t: any(s <= t <= e for s, e in IV[k])
    sp = sorted(P.get("sp") or []); dd = sorted(P.get("d") or [])

    def at(t):
        i = bisect.bisect_left(T, t); i = min(i, len(T) - 1)
        if i > 0 and abs(T[i - 1] - t) < abs(T[i] - t):
            i -= 1
        return i
    xyz = lambda t: (pos["x"][at(t)], pos["y"][at(t)], pos["z"][at(t)])
    li_at = lambda t: (pos.get("li") or [0])[at(t)] if pos.get("li") else 0
    dist = lambda p, q: math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)

    frags = [f for f in ((data["frags"] or {}).get("frags") or []) if f.get("time", -1) >= 0]
    dmg = [e for e in ((data["damage"] or {}).get("events") or []) if e.get("time", -1) >= 0 and e.get("attacker") in team_of and e.get("victim") in team_of]
    my_dealt = sorted((e["time"], e["damage"]) for e in dmg if e["attacker"] == me and team_of[e["victim"]] != team)
    my_taken = sorted((e["time"], e["damage"]) for e in dmg if e["victim"] == me and team_of[e["attacker"]] != team)
    DT = [t for t, _ in my_dealt]; TT = [t for t, _ in my_taken]
    span = lambda L, K, a, b: sum(v for _, v in L[bisect.bisect_left(K, a):bisect.bisect_right(K, b)])
    items = data["items"] if isinstance(data["items"], list) else ((data["items"] or {}).get("items") or [])
    kind_count = collections.Counter(it.get("kind") for it in items)
    def loc_disp(kind, loc):
        """A room name without the item's own token repeated: 'SNG.MH' for the mega is 'SNG', 'YA.box' is 'box'."""
        parts = [x for x in (loc or "").split(".") if x and x.lower() != (kind or "").lower()]
        return ".".join(parts) if parts else (loc or "")

    def nm(kind, loc=""):
        """'QUAD' when the map has one quad; 'YA at tower' when it has several yellows."""
        k = (kind or "").upper()
        return k if kind_count.get(kind, 0) <= 1 or not loc else f"{k} at {loc_disp(kind, loc)}"
    takes = sorted(((ph["takenAt"], it["kind"], SR.room_name(it.get("loc") or ""), it) for it in items for ph in (it.get("phases") or [])
                    if ph.get("takenBy") == me and ph.get("takenAt") is not None), key=lambda x: x[0])
    pickups = [w for w in (data["pickups"] or []) if w.get("player") == me]
    chat = [m for m in (data["chat"] or []) if m.get("type") == "teamsay" and m.get("team") == team]
    events = (data["events"] or {}).get("events") or []
    kills_of = collections.defaultdict(list)
    for f in frags:
        kills_of[f.get("killer")].append(f)

    # ── lives
    lives = []
    for i, s0 in enumerate(sp):
        if s0 >= end:
            break
        nd = min(next((x for x in dd if x > s0), end), end)
        x, y, z = xyz(s0 + 50)
        lab = SR.spawn_label(mp, x, y, z)
        sec0 = s0 // 1000
        dealt = span(my_dealt, DT, s0, nd); taken = span(my_taken, TT, s0, nd)
        kills = [f for f in kills_of.get(me, []) if s0 <= f["time"] <= nd and team_of.get(f.get("victim")) not in (None, team)]
        my_items = [(t, k, l) for t, k, l, _ in takes if s0 <= t <= nd and k in MAJOR]
        death = next((f for f in frags if f.get("victim") == me and abs(f["time"] - nd) < 1500), None) if nd < end else None
        li0 = li_at(s0 + 50); ent = None
        for t in range(s0 + 300, nd, 100):
            l = li_at(t)
            if l != li0:
                ent = (t, locname(l)); break
        first_gun = next((w for w in pickups if s0 <= w["time"] <= nd and w.get("weapon") in ("rl", "lg")), None)
        se = max(0, min(nsec - 1, (nd - 2000) // 1000))
        here = bxyz(me, se)
        near_e = sum(1 for f in foes if bval(f, "alive", se) and dist(bxyz(f, se), here) < NEAR) if nd < end else 0
        near_m = sum(1 for m in mates if bval(m, "alive", se) and dist(bxyz(m, se), here) < NEAR) if nd < end else 0
        td = nd - 100
        eff_d = _eff(H.at(td), A.at(td), AT.at(td) or "")
        lives.append(dict(i=i, s0=s0, nd=nd, len=round((nd - s0) / 1000, 1), spawn=lab, locked=locked_at(s0), M=round(M[sec0]) if sec0 < nsec else None,
                          dealt=dealt, taken=taken, kills=len(kills), items=my_items, death=death, dest=ent,
                          first_gun_s=round((first_gun["time"] - s0) / 1000, 1) if first_gun else None,
                          near_e=near_e, near_m=near_m, eff_d=eff_d, h_d=H.at(td), a_d=A.at(td), at_d=AT.at(td) or "",
                          gun_d=has("rl", td) or has("lg", td), quad_d=has("q", td), spawn_xyz=(x, y, z),
                          empty=(dealt < EMPTY_DMG and not kills and not my_items), chained=(nd - s0) < CHAIN_MS))

    # ── summary
    my_frags = sum(1 for f in kills_of.get(me, []) if team_of.get(f.get("victim")) not in (None, team))
    my_deaths = sum(1 for f in frags if f.get("victim") == me and team_of.get(f.get("killer")) not in (None, team))
    alive_s = sum(l["len"] for l in lives) or 1
    armed_s = sum(1 for s in range(nsec) if bval(me, "alive", s) and (bval(me, "rl", s) or bval(me, "lg", s)))
    stacked_nogun_s = sum(1 for s in range(nsec) if bval(me, "alive", s) and not (bval(me, "rl", s) or bval(me, "lg", s))
                          and _eff(bval(me, "h", s, 100), bval(me, "a", s, 0), bval(me, "at", s, "") or "") >= 150)
    lk = [l for l in lives if l["locked"]]
    summary = dict(frags=my_frags, deaths=my_deaths, lives=len(lives), alive_s=round(alive_s), armed_pct=round(100 * armed_s / alive_s),
                   stacked_nogun_pct=round(100 * stacked_nogun_s / alive_s), empty_lives=sum(1 for l in lives if l["empty"]),
                   stack_no_gun_deaths=sum(1 for l in lives if l["nd"] < end and l["eff_d"] >= 150 and not l["gun_d"]),
                   quad_deaths=sum(1 for l in lives if l["nd"] < end and l["quad_d"]),
                   locked_spawns=len(lk), chained_locked=sum(1 for l in lk if l["chained"]),
                   item_in_14s_locked_pct=round(100 * sum(1 for l in lk if any(t - l["s0"] <= CHAIN_MS for t, _, _ in l["items"])) / len(lk)) if lk else None,
                   dmg_dealt=sum(v for _, v in my_dealt), dmg_taken=sum(v for _, v in my_taken),
                   first_damage_pct=None)
    # landing the first hit: fights = damage exchanges with one enemy inside 4 s gaps; who hit first
    ex = sorted([(e["time"], e["attacker"] == me, e["victim"] if e["attacker"] == me else e["attacker"]) for e in dmg
                 if (e["attacker"] == me and team_of[e["victim"]] != team) or (e["victim"] == me and team_of[e["attacker"]] != team)])
    first = []; last_t = {}
    for t, mine, other in ex:
        if t - last_t.get(other, -99999) > 4000:
            first.append(mine)
        last_t[other] = t
    if first:
        summary["first_damage_pct"] = round(100 * sum(first) / len(first)); summary["fights"] = len(first)

    # ── time blocks (2 min)
    blocks = []
    for b in range(0, end, 120000):
        e = min(b + 120000, end)
        if e - b < 10000:
            continue
        blocks.append(dict(t0=b, t1=e, label=f"{mmss(b)}-{mmss(e)}",
                           frags=sum(1 for f in kills_of.get(me, []) if b <= f["time"] < e and team_of.get(f.get("victim")) not in (None, team)),
                           deaths=sum(1 for f in frags if f.get("victim") == me and b <= f["time"] < e),
                           dealt=span(my_dealt, DT, b, e - 1), taken=span(my_taken, TT, b, e - 1),
                           items=[k for t, k, l, _ in takes if b <= t < e and k in ("ra", "ya", "mh", "quad", "pent", "ring", "rl", "lg")],
                           locked_s=sum(1 for s in range(b // 1000, min(e // 1000, nsec)) if M[s] >= THR),
                           hub=hub(b, e - 120000 + 110000)))

    # ── highlights
    hi = []
    for ev in events:
        if ev.get("player") != me and not (ev.get("type") == "streak" and (ev.get("detail") or {}).get("team") != team):
            continue
        d = ev.get("detail") or {}; t0 = int(ev["t"] * 1000); t1 = int((d.get("endTime") or ev["t"]) * 1000)
        if ev["type"] == "powerup" and ev.get("player") == me:
            if (d.get("duration") or 0) < 5:                 # took it and died: that is the lowlight, not a run
                continue
            hi.append(dict(t=t0, t1=t1, kind="powerup", text=f"{d.get('powerup')} run: {d.get('frags', 0)} frags in {d.get('duration', 0):.0f} s", hub=hub(t0, t1)))
        elif ev["type"] == "streak" and ev.get("player") == me:
            hi.append(dict(t=t0, t1=t1, kind="streak", text=f"{d.get('length')}-frag streak over {d.get('duration', 0):.0f} s with {d.get('weapon') or 'sg'}", hub=hub(t0, t1)))
        elif ev["type"] == "streak":
            ender = next((f for f in frags if f.get("victim") == ev.get("player") and abs(f["time"] - t1) < 1500), None)
            if ender and ender.get("killer") == me:
                hi.append(dict(t=t1, t1=t1, kind="streak_end", text=f"ended {ev.get('player')}'s {d.get('length')}-frag streak", hub=hub(t1)))
    streak_starts = {h["t"] for h in hi if h["kind"] == "streak"}
    for l in sorted(lives, key=lambda l: -(l["kills"] * 100 + l["dealt"]))[:3]:
        if l["kills"] >= 2 and l["s0"] not in streak_starts:
            hi.append(dict(t=l["s0"], t1=l["nd"], kind="life", text=f"{l['len']:.0f} s life from the {l['spawn']} spawn: took {' '.join(k for _, k, _ in l['items']) or 'nothing'}, then {l['kills']} frags and {l['dealt']} damage with it", hub=hub(l["s0"], l["nd"])))
    for t, k, l, _ in takes:
        if k in ("ra", "mh", "quad", "pent") and locked_at(t):
            hi.append(dict(t=t, t1=t, kind="item_locked", text=f"took the {nm(k, l)} while your team was locked: the stack race that breaks locks", hub=hub(t)))
    hi.sort(key=lambda h: h["t"])

    # ── lowlights
    lo = []
    for l in lives:
        if l["nd"] >= end:
            continue
        k = l["death"] or {}
        tk = team_of.get(k.get("killer")) == team and k.get("killer") != me
        if l["quad_d"]:
            lo.append(dict(t=l["nd"], kind="quad_death", text=f"quad died with you after {l['dealt']} damage: spent in one fight", hub=hub(l["nd"])))
        elif l["eff_d"] >= 150 and not l["gun_d"]:
            lo.append(dict(t=l["nd"], kind="stack_no_gun", cost=l["dealt"], text=f"{l['h_d']}/{l['a_d']}{l['at_d']} and no gun when {k.get('killer') or 'they'} found you, {l['len']:.0f} s into the life" + (" (teamkill)" if tk else ""), hub=hub(l["nd"])))
        elif l["near_e"] >= 2 and l["near_m"] == 0 and l["kills"] == 0 and not tk:
            lo.append(dict(t=l["nd"], kind="alone_into_2", cost=l["dealt"], text=f"into {l['near_e']} enemies alone, {l['dealt']} damage: fight, or wait for a second gun?", hub=hub(l["nd"])))
    E = sorted(l["s0"] for l in lives if l["empty"] and l["nd"] < end)
    j = 0
    while j < len(E):
        k = j
        while k + 1 < len(E) and E[k + 1] - E[j] <= 90000:
            k += 1
        if k - j + 1 >= 3:
            lo.append(dict(t=E[j], kind="empty_cluster", text=f"{k - j + 1} lives in {(E[k] - E[j]) / 1000:.0f} s with nothing: no damage, no item. Off those spawns, take something first", hub=hub(E[j], E[k])))
        j = k + 1
    # a player who fights all game trips "alone into two" every minute: keep the five costliest per kind
    per_kind = collections.defaultdict(list)
    for h in lo:
        per_kind[h["kind"]].append(h)
    keep = []
    for kind, L in per_kind.items():
        if kind in ("alone_into_2", "stack_no_gun") and len(L) > 5:
            L = sorted(L, key=lambda h: h.get("cost", 0))[:5]
        keep += L
    lo = sorted(keep, key=lambda h: h["t"])

    packs = [b for b in (data.get("backpacks") or []) if isinstance(b, dict) and b.get("weapon") in ("rl", "lg") and b.get("origin")]

    def packs_at(xyz, t, window_ms=45000, reach_s=10):
        """Dropped RL/LG packs from the last 45 s within reach: rockets on the floor are an item too
        (Peter, 2026-10-21: on schloss rockets are scarce and the packs matter)."""
        out = []
        for b in packs:
            if not (t - window_ms <= b["time"] <= t):
                continue
            o = b["origin"]; tt = dist(xyz, (o[0], o[1], o[2])) / 320 + 0.5
            if tt <= reach_s:
                out.append(dict(kind=f"{b['weapon']} backpack", loc=SR.room_name(b.get("loc") or ""), label=f"{b['weapon'].upper()} backpack at {SR.room_name(b.get('loc') or '')}",
                                state="dropped", s=round((t - b["time"]) / 1000), by=b.get("player"), away=round(tt, 1), by_enemy=(b.get("player") in foes)))
        out.sort(key=lambda o: o["away"])
        return out[:3]

    AMMO_WORD = {"rockets": "rockets", "cells": "cells", "nails": "nails", "shells": "shells"}

    def ammo_at(xyz, t, kind, n=2):
        """Nearest ammo boxes of one kind (rockets / cells / nails) that are up or about to be."""
        out = []
        for it in items:
            if it.get("kind") != kind:
                continue
            st, n_s, by = item_state(it, t)
            tt = dist(xyz, (it["x"], it["y"], it["z"])) / 320 + 0.5
            if st == "up" or (st == "in" and n_s <= tt + 2):
                loc_ = SR.room_name(it.get("loc") or "")
                out.append(dict(kind=kind, loc=loc_, label=f"{AMMO_WORD.get(kind, kind)} at {loc_}", state=st, s=n_s, by=None, away=round(tt, 1), by_enemy=False))
        out.sort(key=lambda o: o["away"])
        return out[:n]

    def near_at(xyz, t, n=5):
        """The nearest key items to a position at time t, with their clock."""
        out = []
        for it in items:
            if it.get("kind") not in ("rl", "lg", "ra", "ya", "mh", "quad"):
                continue
            st, n_s, by = item_state(it, t)
            tt = dist(xyz, (it["x"], it["y"], it["z"])) / 320 + 0.5
            loc_ = SR.room_name(it.get("loc") or "")
            out.append(dict(kind=it["kind"], loc=loc_, label=nm(it["kind"], loc_), state=st, s=n_s, by=(by if it["kind"] == "quad" else None), away=round(tt, 1), by_enemy=(by in foes)))
        out.sort(key=lambda o: o["away"])
        return out[:n]

    def mates_at(s, target=None):
        """Each live teammate at second s: stack, gun, rockets, and seconds from `target` (or from me)."""
        out = []
        ref = target if target is not None else bxyz(me, s)
        for m in mates:
            if not bval(m, "alive", s):
                continue
            out.append(dict(name=m, eff=round(_eff(bval(m, "h", s, 100), bval(m, "a", s, 0), bval(m, "at", s, "") or "")),
                            rl=bool(bval(m, "rl", s)), rockets=int(bval(m, "rk", s, 0) or 0), away=round(dist(bxyz(m, s), ref) / 320, 1)))
        return sorted(out, key=lambda x: x["away"])

    def on_path(from_xyz, to_xyz, t):
        """Armors/megas that cost under 1.5 s of detour between two points and are up (or up by arrival)."""
        base_d = dist(from_xyz, to_xyz)
        res = []
        for it in items:
            if it.get("kind") not in ("ra", "ya", "ga", "mh"):
                continue
            ixyz = (it["x"], it["y"], it["z"])
            detour = (dist(from_xyz, ixyz) + dist(ixyz, to_xyz) - base_d) / 320
            if detour > 1.5:
                continue
            st, n_s, by = item_state(it, t)
            arrive = dist(from_xyz, ixyz) / 320
            if st == "up" or (st == "in" and n_s <= arrive + 1):
                res.append(dict(kind=it["kind"], loc=SR.room_name(it.get("loc") or ""), detour_s=round(detour, 1), state=st, s=n_s))
        return res

    # ── rewinds
    surv_sp = SR.CHAINED_LOCKED.get(mp) or {}; surv_room = SR.ROOM_SURVIVAL.get(mp) or {}
    cand = []
    for l in lives:
        if not l["locked"] or not l["chained"] or l["nd"] >= end or l["spawn"] == "other" or l["len"] < 3.0:
            continue                                        # under 3 s there was no decision to make
        k = l["death"] or {}
        if team_of.get(k.get("killer")) == team:          # a teamkill is not a decision
            continue
        room = l["dest"][1] if l["dest"] else "stayed"
        mine = (surv_room.get(l["spawn"]) or {}).get(room)
        best = max(((r, v) for r, v in (surv_room.get(l["spawn"]) or {}).items()), key=lambda kv: kv[1][0], default=None)
        opts = []
        for it in items:
            if it.get("kind") not in ("ra", "ya", "ga", "mh", "rl", "lg", "quad"):
                continue
            for ph in it.get("phases") or []:
                av, tk2, by = ph.get("availableFrom"), ph.get("takenAt"), ph.get("takenBy")
                if av is None or av > l["s0"] + 12000 or (tk2 is not None and tk2 < l["s0"]) or by in mates:
                    continue
                tt = dist(l["spawn_xyz"], (it["x"], it["y"], it["z"])) / 320 + 0.5
                arrive = l["s0"] + tt * 1000
                if tt <= 12 and arrive >= av - 1500 and (tk2 is None or arrive <= tk2 + 1000):
                    opts.append(dict(kind=it["kind"], loc=SR.room_name(it.get("loc") or ""), s=round(tt, 1), up_at=av, taken_at=tk2, taken_by=by))
        opts.sort(key=lambda o: ({"ra": 0, "quad": 0, "mh": 1, "ya": 1, "rl": 2, "lg": 2, "ga": 3}[o["kind"]], o["s"]))
        comms = [m for m in chat if l["s0"] - 20000 <= m.get("time", -1) <= l["nd"]]
        mine_say = [m for m in comms if m.get("player") == me]
        others = []
        for m in comms:
            if m.get("player") == me:
                continue
            line = _clean_mm2(m.get("messageClean") or m.get("message") or "")
            if not line or (others and others[-1]["text"] == line):
                continue
            others.append(dict(t=m["time"], text=line))
        others = others[-10:]
        # what was up, coming, or just gone at the second you spawned (nearest key items first)
        near_items = []
        for it in items:
            if it.get("kind") not in ("rl", "lg", "ra", "ya", "mh", "quad"):
                continue
            st, n_s, by = item_state(it, l["s0"])
            tt = dist(l["spawn_xyz"], (it["x"], it["y"], it["z"])) / 320 + 0.5
            loc_ = SR.room_name(it.get("loc") or "")
            near_items.append(dict(kind=it["kind"], loc=loc_, label=nm(it["kind"], loc_), state=st, s=n_s, by=(by if it["kind"] == "quad" else None), away=round(tt, 1), by_enemy=(by in foes)))
        near_items.sort(key=lambda o: o["away"])
        near_items = near_items[:6] + packs_at(l["spawn_xyz"], l["s0"])
        score = (1 - (mine[0] if mine else 0.2)) + (0.5 if opts else 0) + (0.3 if best and (not mine or best[1][0] - mine[0] > 0.15) else 0) + (0.2 if l["near_e"] >= 2 else 0)
        cand.append((score, l, room, mine, best, opts[:3], others, mine_say, near_items))
    cand.sort(key=lambda c: -c[0])
    rewinds = []
    for score, l, room, mine, best, opts, others, mine_say, near_items in sorted(cand[:3], key=lambda c: c[1]["s0"]):
        k = l["death"] or {}
        did = f"You went {('to ' + room) if room != 'stayed' else 'nowhere (killed in the spawn area)'}"
        did += f"; you dealt {l['dealt']} damage"
        did += f" and died {l['len']:.1f} s in to {k.get('killer')} ({k.get('weapon')})" if k else f" and died {l['len']:.1f} s in"
        did += f", {l['near_e']} enemies within {NEAR} units, {l['near_m']} teammates." if l["near_e"] else ", no enemy within 700 units two seconds before the death."
        # The reveal, short (Peter, 2026-10-21: "keep the coaching more precise"): the clock of the nearest
        # weapons and armors, the MM2 read, the line, what happened. Numbers stay in the data fields.
        def clk(o):
            if o["state"] == "up" or (o["state"] == "in" and o["s"] <= 0):
                return f"{nm(o['kind'], o['loc'])} up ({o['away']:.0f} s away)"
            if o["state"] == "in":
                return f"{nm(o['kind'], o['loc'])} in {o['s']} s ({o['away']:.0f} s away)"
            return f"{nm(o['kind'], o['loc'])} gone {o['s']} s ago" + (f" to {o['by']}" if o.get("by") and o["kind"] == "quad" else "")
        ans = ["Clock: " + "; ".join(clk(o) for o in near_items[:3]) + "." if near_items else "Clock: nothing near."]
        lost = [re.sub(r"^\S+:?\s*lost\s+", "", c["text"]).split(" ")[0] for c in others if re.search(r"\blost\b", c["text"].lower())]
        seen = [c["text"] for c in others if "enemy" in c["text"].lower()]
        if lost or seen:
            ans.append("MM2: " + (f"lost {', '.join(dict.fromkeys(lost[-3:]))}, so they come from there" if lost else "") + ("; " if lost and seen else "") + (seen[-1] if seen else "") + ".")
        else:
            ans.append("MM2: nothing for 20 s. Assume they hold the big items; play for the small ones.")
        home = next((o for o in near_items if o["kind"] in ("rl", "lg") and o["away"] <= 4), None)
        lost_l = [x.lower() for x in lost]
        hot = [o for o in opts if any(o["loc"].lower().startswith(x.split(".")[0]) for x in lost_l if x)]
        line = sorted([o for o in opts if o not in hot], key=lambda o: o["s"]) if opts else []
        if home and home["state"] == "up":
            ans.append(f"Line: stay. The {home['kind'].upper()} is up here. Take it, then the nearest armor; fight from this doorway.")
        elif home and home["state"] == "in" and home["s"] <= 8:
            ans.append(f"Line: stay for the {home['kind'].upper()} ({home['s']} s). Back to the wall that covers the entrance, shotgun whoever comes, be standing on it when it spawns.")
        elif line:
            steps = [f"{o['kind'].upper()} ({o['s']:.0f} s" + ("" if o["up_at"] <= l["s0"] else f", up {mmss(o['up_at'])}") + ")" for o in line]
            ans.append("Line: " + (f"the {home['kind'].upper()} is {home['s']} s out, nothing to wait for. " if home else "") + "go " + " → ".join(steps) + ". Shotgun anyone you pass, no stopping; fight only after the last one.")
        elif best:
            ans.append(f"Line: go to {best[0]} now; take what you pass.")
        else:
            ans.append("Line: nothing on the clock. Trade: shotgun damage before you die, and say where he is.")
        if hot:
            ans.append("Not " + " or ".join(f"the {nm(o['kind'], o['loc'])}" for o in hot[:2]) + ": that room was just called lost. With a shotgun it is a fight, not a pickup.")
        if l["near_e"] >= 2:
            ans.append(f"{l['near_e']} of them, no teammate near: one shot from cover, then leave.")
        took = [o for o in line if o["taken_by"] in foes]
        ans.append("Happened: " + ("; ".join(f"{o['taken_by']} took the {nm(o['kind'], o['loc'])} at {mmss(o['taken_at'])}" for o in took) + "; " if took else "")
                   + f"you died {l['len']:.0f} s in" + (f" to {k.get('killer')} ({k.get('weapon')})" if k else "") + f", {l['dealt']} damage.")
        mm2 = []
        if l["near_e"] >= 2:
            mm2.append(f"lost {room if room != 'stayed' else l['spawn']} {l['near_e']}>")
        if opts and opts[0]["taken_by"] in foes:
            mm2.append(f"enemy took {nm(opts[0]['kind'], opts[0]['loc']).lower()}")
        mm2.append(f"need armor weapon @ {locname(li_at(l['s0'] + 50))}")
        rewinds.append(dict(idx=len(rewinds), kind="spawn", t=l["s0"], t_end=l["nd"], hub=hub(l["s0"], l["nd"]), spawn=l["spawn"], margin=l["M"], items_at=near_items,
                            mates_at=mates_at(max(0, min(nsec - 1, l["s0"] // 1000))),
                            question=f"{mmss(l['s0'])} — you spawned at {l['spawn']} with your team locked (margin {l['M']}). No voice: only what the MM2 below told you. What should you have thought, and where do you go?",
                            did=did, comms=others, you_sent=[_clean_mm2(m.get("messageClean") or m.get("message")) for m in mine_say],
                            answer=" ".join(ans), mm2=mm2, options=opts, best_room=best[0] if best else None, your_room=room,
                            your_room_survival=mine[0] if mine else None, best_room_survival=best[1][0] if best else None, score=score))

    # ── quad rewinds: quad about to spawn, you alive and within reach, an enemy took it (or you took it naked and died)
    for it in items:
        if it.get("kind") != "quad":
            continue
        for ph in it.get("phases") or []:
            av, by = ph.get("availableFrom"), ph.get("takenBy")
            if av is None or av < 12000 or av > end:
                continue
            s10 = max(0, min(nsec - 1, (av - 10000) // 1000))
            if not bval(me, "alive", s10):
                continue
            qxyz = (it["x"], it["y"], it["z"])
            here = bxyz(me, s10); away = dist(here, qxyz) / 320
            eff10 = _eff(bval(me, "h", s10, 100), bval(me, "a", s10, 0), bval(me, "at", s10, "") or ""); rl10 = bool(bval(me, "rl", s10))
            rk10 = int(RK.at(av - 10000) or 0)
            armed = rl10 and rk10 > 0
            took_me = by == me; took_enemy = by in foes
            died_soon = took_me and any(av <= x <= av + 10000 for x in dd)
            if took_enemy and away <= 12:
                mates10 = mates_at(s10, qxyz)
                path = on_path(here, qxyz, av - 10000)
                # who on your team is actually placed to take it: a gun with rockets and stack, inside reach
                better = [m for m in mates10 if m["away"] <= 10 and m["rl"] and m["rockets"] > 0 and (m["eff"] >= eff10 + 40 or not armed)]
                gun_txt = (f"the RL with {rk10} rockets" if armed else ("the RL but no rockets, so a shotgun until you find rockets" if rl10 else "no RL"))
                q = f"{mmss(av - 10000)} — quad spawns in 10 s. You are {away:.0f} s away with {eff10:.0f} effective stack and {gun_txt}. What do you do?"
                did = f"You were {away:.0f} s from the quad room at {mmss(av - 10000)} and {by} took it at {mmss(av)}" + (f"; you reached the room {'with' if armed else 'without'} rockets." if away <= 6 else ".")
                near_q = near_at(here, av - 10000, 4)
                packs_q = packs_at(here, av - 10000)
                ammo_chips = ammo_at(here, av - 10000, "rockets") if (rl10 and rk10 <= 0) else []
                parts = [f"Quad in 10, you are {int(away)} s out. Clock: " + "; ".join(
                    (f"{nm(o['kind'], o['loc'])} up" if o["state"] == "up" or (o["state"] == "in" and o["s"] <= 0) else f"{nm(o['kind'], o['loc'])} in {o['s']} s" if o["state"] == "in" else f"{nm(o['kind'], o['loc'])} gone {o['s']} s")
                    + f" ({o['away']:.0f} s)" for o in near_q if o["kind"] != "quad") + "."]
                if better:
                    b0 = better[0]
                    parts.append(f"{b0['name']} is {b0['away']:.0f} s out with {b0['eff']} and {b0['rockets']} rockets: he takes it. You: cover the other entrance, call what you see. Not the quad" + (" with no rockets" if not armed else "") + ".")
                elif armed and away <= 10:
                    parts.append("Go now" + (f", {nm(path[0]['kind'], path[0]['loc'])} on the way ({path[0]['detour_s']:.0f} s)" if path else "") + ". In the room with 3 s to spare; hold the entrance, fire as he comes, then take it.")
                elif away <= 10:
                    ammo_q = ammo_at(here, av - 10000, "rockets")
                    parts.append("No rockets: taking the quad is a lost trade. Take " + (f"the {packs_q[0]['label']} ({packs_q[0]['away']:.0f} s, dropped {packs_q[0]['s']} s ago)" if packs_q else (f"the rockets at {ammo_q[0]['loc']} ({ammo_q[0]['away']:.0f} s)" if ammo_q else (f"the {nm(path[0]['kind'], path[0]['loc'])}" if path else "rockets or the yellow"))) + "; let a teammate with rockets take it, or one shot from the doorway and leave.")
                else:
                    parts.append("Too far. Say so; get yellow or rockets and own the next one.")
                if mates10 and not better:
                    near_m = mates10[0]
                    parts.append(f"Nearest teammate {near_m['name']}: {near_m['away']:.0f} s out, {near_m['eff']} stack, " + (f"{near_m['rockets']} rockets" if near_m['rl'] else "no RL") + ".")
                parts.append(f"{by} took it.")
                a = " ".join(parts)
                mm2 = [f"quad in 10 @ {SR.room_name(it.get('loc') or 'quad')}", ("taking quad" if armed and not better else ("covering quad" if better else "need rockets @ quad"))]
                comms = [m for m in chat if av - 25000 <= m.get("time", -1) <= av]
                others = []
                for m in comms:
                    if m.get("player") == me:
                        continue
                    line = _clean_mm2(m.get("messageClean") or m.get("message") or "")
                    if line and not (others and others[-1]["text"] == line):
                        others.append(dict(t=m["time"], text=line))
                rewinds.append(dict(idx=0, kind="quad", t=av - 10000, t_end=av + 5000, hub=hub(av - 10000, av + 5000), spawn=None, margin=round(M[s10]) if s10 < nsec else None,
                                    stack=round(eff10), has_rl=rl10, rockets=rk10, mates_at=mates10, on_path=path,
                                    items_at=[dict(kind="quad", loc=SR.room_name(it.get("loc") or ""), label=nm("quad", SR.room_name(it.get("loc") or "")), state="in", s=10, by=None, away=round(away, 1), by_enemy=False)] + [o for o in near_q if o["kind"] != "quad"] + ammo_chips + packs_q,
                                    question=q, did=did, comms=others[-10:], you_sent=[_clean_mm2(m.get("messageClean") or m.get("message")) for m in comms if m.get("player") == me],
                                    answer=a, mm2=mm2, options=[], best_room=None, your_room=None, your_room_survival=None, best_room_survival=None, score=0.6 + (0.3 if away <= 6 else 0)))
            elif took_me and died_soon and eff10 < 100:
                q = f"{mmss(av - 10000)} — quad spawns in 10 s and you are going for it with {eff10:.0f} effective stack. What do you do?"
                rewinds.append(dict(idx=0, kind="quad", t=av - 10000, t_end=av + 10000, hub=hub(av - 10000, av + 10000), spawn=None, margin=round(M[s10]) if s10 < nsec else None,
                                    items_at=[dict(kind="quad", loc=SR.room_name(it.get("loc") or ""), label=nm("quad", SR.room_name(it.get("loc") or "")), state="in", s=10, by=None, away=round(away, 1), by_enemy=False)],
                                    question=q, did=f"You took the quad at {mmss(av)} with about {eff10:.0f} stack and died inside 10 s: the run was over before it started.",
                                    comms=[], you_sent=[], answer="A quad on a spawn stack is a quad for them to farm. Spend the ten seconds on the yellow or mega beside the room, take it with a body, open the run on the nearest enemy gun.",
                                    mm2=["quad in 10, need armor", "taking quad"], options=[], best_room=None, your_room=None, your_room_survival=None, best_room_survival=None, score=0.5))
    # one quad moment per report (the costliest), up to three spawn moments: the same quad lesson three
    # times is noise (Peter, 2026-10-21)
    quads = sorted([w for w in rewinds if w["kind"] == "quad"], key=lambda w: -w.get("score", 0))[:1]
    spawns_ = sorted([w for w in rewinds if w["kind"] == "spawn"], key=lambda w: -w.get("score", 0))[:3]
    rewinds = sorted(quads + spawns_, key=lambda w: w["t"])
    for i, w in enumerate(rewinds):
        w["idx"] = i; w["wall_ms"] = wall(w["t"])
    for h in hi + lo:
        h["wall_ms"] = wall(h["t"])
    for b in blocks:
        b["wall_ms"] = wall(b["t0"])

    # ── everyone in this game on the Advanced Stats numbers (Peter, 2026-10-21: sort by the per-game
    # impact score, show game score, quads, pents, MM2; not the basic damage columns). The Game Impact
    # Score here is the same recipe as docs/advanced_metrics.md (30% adjusted kills, 15% damage, 15%
    # stacked DDR, 15% survival, 20% items, 5% multi-kills; the eight average 1.00) computed from the
    # 1 s state, so stacks at first contact are to the second rather than the frame. No +/- here: that
    # needs the win-probability model, which is not in the API.
    all_chat = [m for m in (data.get("chat") or []) if m.get("type") == "teamsay"]
    chat_by = collections.Counter(m.get("player") for m in all_chat)
    pw_iv = collections.defaultdict(list)
    for ev in events:
        if ev.get("type") == "powerup" and ev.get("player") in team_of:
            dd_ = ev.get("detail") or {}
            pw_iv[ev["player"]].append((int(ev["t"] * 1000), int((dd_.get("endTime") or ev["t"]) * 1000)))
    def has_pw(n, t):
        return any(s_ <= t <= e_ for s_, e_ in pw_iv.get(n, []))
    def eff_at(n, t):
        s_ = max(0, min(nsec - 1, t // 1000))
        return _eff(bval(n, "h", s_, 100), bval(n, "a", s_, 0), bval(n, "at", s_, "") or "")
    def pw_state(k, v, t):
        a_, b_ = has_pw(k, t), has_pw(v, t)
        return "both" if a_ and b_ else ("has powerup" if a_ else ("vs powerup" if b_ else "no powerup"))
    enemy_dmg = [e for e in dmg if team_of[e["attacker"]] != team_of[e["victim"]]]
    dmg_by_pair = collections.defaultdict(list)
    for e in enemy_dmg:
        dmg_by_pair[frozenset((e["attacker"], e["victim"]))].append(e)
    dmg_by_victim = collections.defaultdict(list)
    for e in enemy_dmg:
        dmg_by_victim[e["victim"]].append(e)
    R = {n: collections.Counter() for n in team_of}
    for e in enemy_dmg:
        a_, v_, t_ = e["attacker"], e["victim"], e["time"]
        R[a_]["dmg"] += e["damage"]; R[v_]["taken"] += e["damage"]
        if eff_at(a_, t_ - 30) >= 150:
            R[a_]["stk_given"] += e["damage"]
        if eff_at(v_, t_ - 30) >= 150:
            R[v_]["stk_taken"] += e["damage"]
    efrags = [f for f in frags if f.get("killer") in team_of and f.get("victim") in team_of and team_of[f["killer"]] != team_of[f["victim"]]]
    for f in efrags:
        k_, v_, t_ = f["killer"], f["victim"], f["time"]
        R[k_]["kills"] += 1
        chain = [e for e in dmg_by_pair.get(frozenset((k_, v_)), []) if e["time"] <= t_]
        t0 = t_
        for e in reversed(chain):
            if t0 - e["time"] <= 4000:
                t0 = e["time"]
            else:
                break
        edge = eff_at(k_, t0 - 30) - eff_at(v_, t0 - 30)
        kp = min(3.0, 0.5 / max(0.02, pwin(edge, pw_state(k_, v_, t0 - 30))))
        contrib = collections.Counter()
        for e in dmg_by_victim.get(v_, []):
            if t_ - 10000 <= e["time"] <= t_ and team_of[e["attacker"]] == team_of[k_]:
                contrib[e["attacker"]] += e["damage"]
        tot = sum(contrib.values())
        if tot <= 0:
            R[k_]["adj"] += kp
        else:
            for a_, dm in contrib.items():
                R[a_]["adj"] += kp * (0.15 * (a_ == k_) + 0.85 * dm / tot)
    score_of = {p["name"]: p.get("frags") for p in (ov.get("players") or [])}
    rows_ = []
    for n in team_of:
        deaths_n = sum(1 for f in frags if f.get("victim") == n)      # every death, from the frag log (1 s buckets miss instant respawns)
        ks = sorted(f["time"] for f in efrags if f["killer"] == n)
        multi = sum(1 for i in range(1, len(ks)) if ks[i] - ks[i - 1] <= 8000)
        it_n = collections.Counter(it["kind"] for it in items for ph in (it.get("phases") or []) if ph.get("takenBy") == n)
        items_w = it_n.get("ra", 0) * 1.0 + it_n.get("ya", 0) * 0.6 + it_n.get("mh", 0) * 0.8 + it_n.get("quad", 0) * 2.0 + it_n.get("pent", 0) * 2.0
        r_ = R[n]
        rows_.append(dict(name=n, team=team_of[n], me=(n == me), score=score_of.get(n), kills=r_["kills"], deaths=deaths_n,
                          adj=round(r_["adj"], 1), dmg=r_["dmg"], taken=r_["taken"], dmg_pm=round(r_["dmg"] / max(1, end / 60000)),
                          sddr=round(r_["stk_given"] / max(1, r_["stk_taken"]), 2), multi=multi, items_w=items_w,
                          ra=it_n.get("ra", 0), ya=it_n.get("ya", 0), mh=it_n.get("mh", 0), quads=it_n.get("quad", 0), pents=it_n.get("pent", 0),
                          mm2=chat_by.get(n, 0)))
    def _norm(key, inv=False):
        m_ = (sum(x[key] for x in rows_) / len(rows_)) or 1
        for x in rows_:
            x["n_" + key] = (m_ / max(0.5, x[key])) if inv else (x[key] / m_)
    for k_ in ("adj", "dmg", "multi", "items_w", "sddr"):
        _norm(k_)
    _norm("deaths", inv=True)
    for x in rows_:
        x["impact"] = 0.30 * x["n_adj"] + 0.15 * x["n_dmg"] + 0.15 * x["n_sddr"] + 0.15 * x["n_deaths"] + 0.05 * min(2.0, x["n_multi"]) + 0.20 * x["n_items_w"]
    m_ = (sum(x["impact"] for x in rows_) / len(rows_)) or 1
    for x in rows_:
        x["impact"] = round(x["impact"] / m_, 2)
        for k_ in [k for k in x if k.startswith("n_")]:
            x.pop(k_)
    table = sorted(rows_, key=lambda x: -x["impact"])
    HIGHER = {"impact": True, "score": True, "adj": True, "dmg_pm": True, "sddr": True, "deaths": False, "quads": True, "pents": True, "ra": True, "mm2": True}
    my_rank = {}
    mine_row = next((r for r in table if r["me"]), None)
    if mine_row:
        for col, hi_good in HIGHER.items():
            vals = [r[col] for r in table if r[col] is not None]
            v = mine_row[col]
            if v is None or not vals:
                continue
            my_rank[col] = 1 + sum(1 for x in vals if (x > v if hi_good else x < v))
    def ordn(k):
        return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"
    compare = None
    if mine_row and my_rank:
        compare = (f"Impact {mine_row['impact']:.2f} (1.00 is the average of the eight): {ordn(my_rank.get('impact', 0))} of {len(table)}. "
                   f"Score {ordn(my_rank.get('score', 0))}, adjusted kills {ordn(my_rank.get('adj', 0))}, damage per minute {ordn(my_rank.get('dmg_pm', 0))}, "
                   f"stacked DDR {ordn(my_rank.get('sddr', 0))}, deaths {ordn(my_rank.get('deaths', 0))} (fewest first), MM2 {ordn(my_rank.get('mm2', 0))}.")

    # ── MM2
    def cls(m):
        s = (m.get("messageClean") or m.get("message") or "").lower()
        if "lost" in s: return "lost"
        if "need" in s: return "need"
        if "pack" in s: return "pack"
        if re.search(r"\b(took|take|got)\b", s): return "took"
        if re.search(r"\d+/\d+", s): return "status"
        if re.search(r"\b(quad|pent|ring)\b", s): return "powerup"
        if "enemy" in s or re.search(r"\d+>", s): return "enemy"
        return "other"
    mine_c = collections.Counter(cls(m) for m in chat if m.get("player") == me)
    by_player = collections.Counter(m.get("player") for m in chat)
    mm2 = dict(sent=sum(mine_c.values()), by_kind=dict(mine_c), per_min=round(60 * sum(mine_c.values()) / alive_s, 1),
               team={n: by_player.get(n, 0) for n in [me] + mates}, team_total=sum(by_player.values()))

    return dict(version=VERSION, hub_game_id=gid, map=mp, map_name=ov.get("map"), player=me, team=team, mates=mates, foes=foes,
                teams=ov.get("teams"), scoreboard=ov.get("players"), demo_offset_ms=off, hub_user_id=uid, match_end_ms=end,
                match_start_wall_ms=wall(0),
                lock_threshold=THR, locked_pct=round(100 * sum(1 for m in M if m >= THR) / nsec) if nsec else None,
                hub=HUB.format(gid=gid, f=0, t=int((end + off) / 1000), uid=uid) if uid is not None else None,
                summary=summary, compare=compare, table=table, my_rank=my_rank,
                blocks=blocks, highlights=hi, lowlights=lo, rewinds=rewinds, mm2=mm2,
                lives=[{k: v for k, v in l.items() if k not in ("death", "spawn_xyz", "dest")} | {"killer": (l["death"] or {}).get("killer"), "weapon": (l["death"] or {}).get("weapon"), "first_room": l["dest"][1] if l["dest"] else None} for l in lives])

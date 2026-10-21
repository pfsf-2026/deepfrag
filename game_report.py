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

VERSION = 8
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
        return ("in", round((nxt["availableFrom"] - t) / 1000), last.get("takenBy") if last else None)
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
            "pickups": get(f"{base}/weapon-pickups"), "chat": get(f"{base}/chat?types=teamsay"),
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
            hi.append(dict(t=t, t1=t, kind="item_locked", text=f"took the {k} at {l} while your team was locked: the stack race that breaks locks", hub=hub(t)))
    hi.sort(key=lambda h: h["t"])

    # ── lowlights
    lo = []
    for l in lives:
        if l["nd"] >= end:
            continue
        k = l["death"] or {}
        tk = team_of.get(k.get("killer")) == team and k.get("killer") != me
        if l["quad_d"]:
            lo.append(dict(t=l["nd"], kind="quad_death", text=f"quad died with you after {l['dealt']} damage: the run was spent in one fight instead of on the enemies with guns", hub=hub(l["nd"])))
        elif l["eff_d"] >= 150 and not l["gun_d"]:
            lo.append(dict(t=l["nd"], kind="stack_no_gun", cost=l["dealt"], text=f"you met {k.get('killer') or 'them'} with {l['h_d']}/{l['a_d']}{l['at_d']} and no RL or LG, {l['len']:.0f} s into the life: a stack spent without a weapon to use it" + (" (teamkill)" if tk else ""), hub=hub(l["nd"])))
        elif l["near_e"] >= 2 and l["near_m"] == 0 and l["kills"] == 0 and not tk:
            lo.append(dict(t=l["nd"], kind="alone_into_2", cost=l["dealt"], text=f"you went into {l['near_e']} enemies with no teammate within {NEAR} units and dealt {l['dealt']}: the decision was to fight them rather than wait for a second gun or report them", hub=hub(l["nd"])))
    E = sorted(l["s0"] for l in lives if l["empty"] and l["nd"] < end)
    j = 0
    while j < len(E):
        k = j
        while k + 1 < len(E) and E[k + 1] - E[j] <= 90000:
            k += 1
        if k - j + 1 >= 3:
            lo.append(dict(t=E[j], kind="empty_cluster", text=f"{k - j + 1} lives in {(E[k] - E[j]) / 1000:.0f} s that produced nothing: no damage, no frag, no item. Off those spawns the decision was to run at the fight before taking anything", hub=hub(E[j], E[k])))
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
            near_items.append(dict(kind=it["kind"], loc=SR.room_name(it.get("loc") or ""), state=st, s=n_s, by=by, away=round(tt, 1), by_enemy=(by in foes)))
        near_items.sort(key=lambda o: o["away"])
        near_items = near_items[:6]
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
        # The reveal is coaching of the HOW (Peter, 2026-10-21: "you're pushing stats again… rather than the
        # narrative of how to achieve the stats"): the clock, the read of the MM2, the line to take and how
        # to play it, the call to make, then what actually happened. Numbers stay in the data fields.
        clock = []
        for o in near_items[:4]:
            if o["state"] == "up":
                clock.append(f"the {o['kind'].upper()} at {o['loc']} is up, {o['away']:.0f} s away")
            elif o["state"] == "in" and o["s"] <= 0:
                clock.append(f"the {o['kind'].upper()} at {o['loc']} is up right now, {o['away']:.0f} s away")
            elif o["state"] == "in":
                clock.append(f"the {o['kind'].upper()} at {o['loc']} comes up in {o['s']} s, {o['away']:.0f} s away" + (f" ({o['by']} took the last one)" if o["by"] else ""))
            elif o["state"] == "taken":
                clock.append(f"the {o['kind'].upper()} at {o['loc']} went {o['s']} s ago to {o['by'] or 'someone'}")
        ans = [f"At {mmss(l['s0'])} you spawn at {l['spawn']} with your team locked" + (f": {'; '.join(clock)}." if clock else ".")]
        lost = [re.sub(r"^\S+:?\s*lost\s+", "", c["text"]).split(" ")[0] for c in others if re.search(r"\blost\b", c["text"].lower())]
        seen = [c["text"] for c in others if "enemy" in c["text"].lower()]
        if lost or seen:
            ans.append("The read from the MM2: " + (f"your team has just lost {', '.join(dict.fromkeys(lost[-3:]))}, so that is where they are coming from" if lost else "") + ("; " if lost and seen else "") + (f"{seen[-1]}" if seen else "") + ".")
        else:
            ans.append("The read from the MM2: your team has told you nothing in the last 20 s, so assume the enemy holds the big items and play for the small ones.")
        home = next((o for o in near_items if o["kind"] in ("rl", "lg") and o["away"] <= 4), None)
        # an item in a room your team has just called lost is a fight, not a pickup, when you have no gun
        lost_l = [x.lower() for x in lost]
        hot = [o for o in opts if any(o["loc"].lower().startswith(x.split(".")[0]) for x in lost_l if x)]
        line = sorted([o for o in opts if o not in hot], key=lambda o: o["s"]) if opts else []
        if home and home["state"] == "up":
            ans.append(f"The line: the {home['kind'].upper()} is in this room and up, so this is a spawn to stay on — take it first, then the nearest armor, and fight from the doorway of this room rather than walking out naked.")
        elif home and home["state"] == "in" and home["s"] <= 8:
            ans.append(f"The line: the {home['kind'].upper()} is {home['s']} s out, which is a fight worth having — stay, put your back to the wall that covers the entrance, shotgun whoever comes for it, and be on the pad when it spawns.")
        elif line:
            steps = [f"the {o['kind'].upper()} at {o['loc']} ({o['s']:.0f} s away, {'already up' if o['up_at'] <= l['s0'] else 'up at ' + mmss(o['up_at'])})" for o in line]
            ans.append("The line: " + (f"the {home['kind'].upper()} is gone for {home['s']} s, so there is nothing to wait for here — " if home else "") + "go to " + ", then ".join(steps)
                       + ". Move at spawn speed, shotgun anyone you pass without stopping, and only after the last of those do you look for a fight. Hit first: see the doorway before the enemy sees you, and if someone is standing on the item, fire from the entrance and back off rather than walking onto him.")
        elif best:
            ans.append(f"The line: nothing is on the clock from this spawn, so head for {best[0]} straight away — it is the way out of this spawn that keeps you alive long enough to find the next item — and put shotgun damage on anyone you pass.")
        else:
            ans.append("The line: nothing is on the clock from this spawn. This is a life to trade with: put shotgun damage on the nearest enemy before you die and make sure your team hears where he is.")
        if hot:
            ans.append("Not " + " or ".join(f"the {o['kind'].upper()} at {o['loc']}" for o in hot[:2]) + ": your team has just called that room lost, and with a shotgun that is a fight you walk into, not an item you pick up. Leave it until you have a gun or a teammate with one.")
        if l["near_e"] >= 2:
            ans.append(f"You met {l['near_e']} of them with no teammate near you: that is the moment to fire once from cover and leave, not to commit.")
        took = [o for o in line if o["taken_by"] in foes]
        happened = (f"What happened: " + ("; ".join(f"{o['taken_by']} took the {o['kind'].upper()} at {mmss(o['taken_at'])}" for o in took) + ", and " if took else "")
                    + f"you died {l['len']:.0f} s in" + (f" to {k.get('killer')} ({k.get('weapon')})" if k else "") + f" having dealt {l['dealt']} damage.")
        ans.append(happened)
        mm2 = []
        if l["near_e"] >= 2:
            mm2.append(f"lost {room if room != 'stayed' else l['spawn']} {l['near_e']}>")
        if opts and opts[0]["taken_by"] in foes:
            mm2.append(f"enemy took {opts[0]['kind']} at {opts[0]['loc']}")
        mm2.append(f"need armor weapon @ {locname(li_at(l['s0'] + 50))}")
        rewinds.append(dict(idx=len(rewinds), kind="spawn", t=l["s0"], t_end=l["nd"], hub=hub(l["s0"], l["nd"]), spawn=l["spawn"], margin=l["M"], items_at=near_items,
                            mates_at=mates_at(max(0, min(nsec - 1, l["s0"] // 1000))),
                            question=f"{mmss(l['s0'])} — you spawned at {l['spawn']} with your team locked (margin {l['M']}). No voice: only what the MM2 below told you. What should you have thought, and where do you go?",
                            did=did, comms=others, you_sent=[_clean_mm2(m.get("messageClean") or m.get("message")) for m in mine_say],
                            answer=" ".join(ans), mm2=mm2, options=opts, best_room=best[0] if best else None, your_room=room,
                            your_room_survival=mine[0] if mine else None, best_room_survival=best[1][0] if best else None, score=score))

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
                gun_txt = (f"the RL with {rk10} rockets" if armed else ("the RL but no rockets, so a shotgun until you find a pack" if rl10 else "no RL"))
                q = f"{mmss(av - 10000)} — quad spawns in 10 s. You are {away:.0f} s away with {eff10:.0f} effective stack and {gun_txt}. What do you do?"
                did = f"You were {away:.0f} s from the quad room at {mmss(av - 10000)} and {by} took it at {mmss(av)}" + (f"; you reached the room {'with' if armed else 'without'} rockets." if away <= 6 else ".")
                parts = [f"Quad is {int(away)} s of running away and spawns in 10, so the decision is made now, not at the spawn."]
                if better:
                    b0 = better[0]
                    parts.append(f"{b0['name']} is {b0['away']:.0f} s from the room with {b0['eff']} stack and the RL with {b0['rockets']} rockets: he is the one taking it, and your job is to make his take safe — cover the other entrance so nobody comes through behind him, and call what you see.")
                    parts.append("Do not walk onto the pad yourself" + (" with no rockets" if not armed else "") + ": two naked bodies in the room is a double kill for whoever has the rocket.")
                elif armed and away <= 10:
                    parts.append("Start moving on this call" + (f", take the {path[0]['kind'].upper()} at {path[0]['loc']} on the way (it costs {path[0]['detour_s']:.0f} s)" if path else ", with nothing on your path worth a detour") + ", and be inside the room with three seconds to spare so you are on the pad as it appears. Hold the entrance the enemy will use and fire as he comes through, then step onto the pad.")
                elif away <= 10:
                    parts.append("You have no rockets, so the pad is a trade you lose against a gun. Spend these ten seconds on the next thing instead" + (f": the {path[0]['kind'].upper()} at {path[0]['loc']} is on your way" if path else ": a rocket pack or the yellow") + ", and let the teammate with rockets take it; if nobody can, shoot from the doorway to make him flinch and leave.")
                else:
                    parts.append("You are too far to make this one; the useful decision is to say so and set up for the next: get the yellow or rockets now, so in sixty seconds you are the one in the room with a gun.")
                if mates10 and not better:
                    near_m = mates10[0]
                    parts.append(f"Nearest teammate is {near_m['name']}, {near_m['away']:.0f} s from the room with {near_m['eff']} stack" + (f" and {near_m['rockets']} rockets" if near_m['rl'] else " and no RL") + ".")
                parts.append(f"{by} took it this time.")
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
                                    items_at=[dict(kind="quad", loc=SR.room_name(it.get("loc") or ""), state="in", s=10, by=None, away=round(away, 1), by_enemy=False)] + [dict(kind=o["kind"], loc=o["loc"], state=o["state"], s=o["s"], by=None, away=o["detour_s"], by_enemy=False) for o in path],
                                    question=q, did=did, comms=others[-10:], you_sent=[_clean_mm2(m.get("messageClean") or m.get("message")) for m in comms if m.get("player") == me],
                                    answer=a, mm2=mm2, options=[], best_room=None, your_room=None, your_room_survival=None, best_room_survival=None, score=0.6 + (0.3 if away <= 6 else 0)))
            elif took_me and died_soon and eff10 < 100:
                q = f"{mmss(av - 10000)} — quad spawns in 10 s and you are going for it with {eff10:.0f} effective stack. What do you do?"
                rewinds.append(dict(idx=0, kind="quad", t=av - 10000, t_end=av + 10000, hub=hub(av - 10000, av + 10000), spawn=None, margin=round(M[s10]) if s10 < nsec else None,
                                    items_at=[dict(kind="quad", loc=SR.room_name(it.get("loc") or ""), state="in", s=10, by=None, away=round(away, 1), by_enemy=False)],
                                    question=q, did=f"You took the quad at {mmss(av)} with about {eff10:.0f} stack and died inside 10 s: the run was over before it started.",
                                    comms=[], you_sent=[], answer="A quad on a spawn stack is a quad for the other team to farm. Spend the ten seconds before it on the yellow or the mega beside the room, take the quad with a body to carry it, and open the run on the nearest enemy gun, not on the first spawn you see.",
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
                summary=summary, blocks=blocks, highlights=hi, lowlights=lo, rewinds=rewinds, mm2=mm2,
                lives=[{k: v for k, v in l.items() if k not in ("death", "spawn_xyz", "dest")} | {"killer": (l["death"] or {}).get("killer"), "weapon": (l["death"] or {}).get("weapon"), "first_room": l["dest"][1] if l["dest"] else None} for l in lives])

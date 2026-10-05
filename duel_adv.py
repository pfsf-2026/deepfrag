"""Duel (1on1) advanced metrics for ONE game, computed from the mvd-api.

Same definitions as the demo pipeline in tools/mvd_features (extract.py builds the
per-hit rows with both players' stack attached, duel_corpus.py scores them), but fed by
five small mvd-api calls instead of a locally parsed demo, so the API can refresh a game
by itself after a ladder match and nothing depends on a laptop. docs/advanced_metrics.md
has the definitions; the fight table and the win-probability coefficients below are the
ones fitted there (tools/mvd_features/fight_table_1on1.json, winprob_1on1.json).

Added in VERSION 2: item timing detail for megas and red armors.
  mh_waits / ra_waits   how long each one sat before this player took it (ms). The one
                        on the map at the start is left out: nobody has to time it.
  mh_kept / mh_lost     after this player took a mega, who took the next one. kept /
                        (kept + lost) is "held the mega": he had the timer and was there.
  mh_all / ra_all       megas / red armors taken in the game by both players (share).

    data = fetch(game_id, get)            # get(path) -> parsed JSON or None
    rows = compute(data, map_name)        # two dicts keyed by the in-demo name, or None
"""
from __future__ import annotations

import bisect
import collections
import math

VERSION = 2
MIN_DURATION_MS = 240000          # shorter than four minutes is an aborted game
FIGHT_GAP_MS = 4000               # hits further apart than this are separate fights
EDGE = 60                         # effective-HP gap that makes a fight uneven
STACKED = 150                     # effective HP that counts as stacked
ON_TIMER_MS = 3000
ARMOR_RATIO = {"ra": 0.8, "ya": 0.6, "ga": 0.3, "": 0.0}
STREAM_FIELDS = "h,a,at,sp,d,rl,lg,q,pe"

# P(win the fight | stack edge at first contact, power-up state): 13,417 duels, 609,678 frags.
FIGHT_TABLE = {
    "no powerup": [(-200, 0.123), (-70, 0.302), (0, 0.5), (70, 0.698), (200, 0.877)],
    "has powerup": [(-200, 0.493), (-70, 0.764), (0, 0.821), (70, 0.833), (200, 0.894)],
    "vs powerup": [(-200, 0.106), (-70, 0.167), (0, 0.179), (70, 0.236), (200, 0.507)],
    "both": [(-200, 0.5), (-70, 1.0), (0, 0.5), (70, 0.0), (200, 0.5)],
}
# Duel win probability v1, no intercept. Features: frag_diff, frag_diff*frac_left,
# frag_diff/(frac_left+.05), stack_diff/100, powerup_diff, rl_diff, lg_diff, frac_left.
# One set per map with 300+ duels in the fit; every other map uses "pooled".
WINPROB = {
    "pooled": [-0.07150729940187424, 0.24036175873812307, 0.1345321237169057, 0.31456578813795866, 0.0076123862713363384, 0.21479502591960536, 0.18995313933712435, 2.19701256716837e-16],
    "aerowalk": [-0.09950412577645094, 0.2616773991526553, 0.1351150043823534, 0.29849164903385883, 0.006996491430650675, 0.2442056471288943, 0.19585742655455943, 1.781931316899345e-16],
    "bravado": [-0.10313066705435187, 0.2767558887312466, 0.1417129784402824, 0.3275878624540356, -0.0023362587099718065, 0.13102780202246106, 0.19398032995886968, 7.942922097099093e-17],
    "dm2": [0.22952975507690304, 0.0544641220189742, 0.16147746986760564, 0.34922350679701253, -4.6460149359268266e-05, 0.45590586556767976, 0.0, 1.3285164704483648e-16],
    "dm4": [0.14257357867064466, 0.076003627970947, 0.14456603080968597, 0.4025531006382741, 0.0, 0.1535387855966027, 0.2905914082048924, 3.5942534342485476e-16],
    "dm6": [-0.02662057714306362, 0.24460494454588383, 0.12880073073317735, 0.34007553755944664, 0.0, 0.1523124455436831, 0.3195534113151698, 8.502935134869026e-17],
    "metron": [-0.006636501774216442, 0.19043403191677746, 0.10551277609051486, 0.2963278794795808, 0.0, 0.15594248455598264, 0.09120581758847855, -4.9821919462784535e-17],
    "pocket": [-0.02003358504999928, 0.23279505625345684, 0.12592242201264026, 0.37025818861040144, 1.6236153526083865, 0.1014960518077279, 0.09123854716617129, -1.7666245695864317e-14],
    "skull": [0.005074229570422856, 0.1911882592130607, 0.11305841770166747, 0.282531720984975, 0.0, 0.21857178694225154, 0.12732238518959885, -1.0444404956419135e-16],
    "ztndm3": [-0.07957011323784981, 0.20532615943151225, 0.1399802753092974, 0.3652627618731359, 0.004499088532991367, 0.13946373086468022, 0.23764669178802084, -5.874751134855757e-17],
}


def _eff(h, a, at):
    r = ARMOR_RATIO.get(at, 0)
    if h <= 0:
        return 0
    return h / (1 - r) if (r > 0 and r * h / (1 - r) <= a) else h + a


class _Series:
    """A change series [{t, v}, ...]: the value in force at time t."""
    __slots__ = ("t", "v", "d")

    def __init__(self, series, default=0):
        series = series or []
        self.t = [e["t"] for e in series]
        self.v = [e["v"] for e in series]
        self.d = default

    def at(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        return self.v[i] if i >= 0 else self.d


def _in(ivs, t):
    return any(s <= t <= e for s, e in ivs)


def _feats(fd, frac, sd, pw, rl, lg):
    return [fd, fd * frac, fd / (frac + 0.05), sd / 100, pw, rl, lg, frac]


def _pwin(coef, fd, frac, sd, pw, rl, lg):
    z = sum(c * v for c, v in zip(coef, _feats(fd, frac, sd, pw, rl, lg)))
    return 1 / (1 + math.exp(-z))


def _pfight(edge, state):
    pts = FIGHT_TABLE.get(state, FIGHT_TABLE["no powerup"])
    if edge <= pts[0][0]:
        return pts[0][1]
    if edge >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= edge <= x1:
            return y0 + (y1 - y0) * (edge - x0) / (x1 - x0)


def fetch(game_id, get):
    """The five mvd-api payloads compute() needs. get(path) returns parsed JSON or None."""
    base = f"/v1/demos/gameId:{game_id}"
    ov = get(f"{base}/overview")
    if not ov:
        return None
    return {"overview": ov,
            "streams": get(f"{base}/stream-slice?from=0&to=99999&fields={STREAM_FIELDS}"),
            "damage": get(f"{base}/damage"), "frags": get(f"{base}/frags"), "items": get(f"{base}/items")}


def compute(data, map_name=None):
    """Two rows (one per player, keyed by in-demo name under "name"), or None when the
    game cannot be scored: not exactly two players, no result, or under four minutes."""
    if not data or not data.get("overview") or not data.get("streams"):
        return None
    ov = data["overview"]
    end = ov.get("matchEnd") or ov.get("duration") or 0
    score = {p["name"]: p.get("frags") for p in (ov.get("players") or [])}
    P = {p["name"]: p for p in (data["streams"].get("players") or [])
         if p.get("h") is not None and p["name"] in score}
    if len(P) != 2 or len(score) != 2 or end < MIN_DURATION_MS or any(v is None for v in score.values()):
        return None
    A, B = list(P)
    other = {A: B, B: A}
    H = {n: _Series(P[n].get("h"), 100) for n in P}
    AR = {n: _Series(P[n].get("a"), 0) for n in P}
    AT = {n: _Series(P[n].get("at"), "") for n in P}
    IV = {k: {n: [(iv["s"], iv["e"]) for iv in (P[n].get(k) or [])] for n in P} for k in ("rl", "lg", "q", "pe")}
    SP = {n: P[n].get("sp") or [] for n in P}

    def tss(n, t):                      # time since this player last spawned
        i = bisect.bisect_right(SP[n], t) - 1
        return (t - SP[n][i]) if i >= 0 else t

    def state(n, t):                    # (effective HP, has RL, has LG, has quad/pent)
        h, a, at = H[n].at(t), AR[n].at(t), AT[n].at(t)
        return (round(_eff(h, a, at)), int(_in(IV["rl"][n], t)), int(_in(IV["lg"][n], t)),
                int(_in(IV["q"][n], t) or _in(IV["pe"][n], t)))

    def capped(e):                      # KTX's stats-page damage: health part capped at what was left
        v, t = e["victim"], e["time"]
        h0, a0, r = H[v].at(t - 1), AR[v].at(t - 1), ARMOR_RATIO.get(AT[v].at(t - 1), 0)
        save = min(a0, math.ceil(e["damage"] * r))
        take = math.ceil(e["damage"] - save)
        return save + max(0, min(take, h0))

    frags = sorted((f for f in ((data.get("frags") or {}).get("frags") or [])
                    if f.get("killer") in P and f.get("victim") in P and f["time"] >= 0), key=lambda f: f["time"])
    run = collections.Counter()
    sct, scv = [], []
    for f in frags:                     # running score, so every event knows the frag difference
        if f["killer"] != f["victim"]:
            run[f["killer"]] += 1
        else:
            run[f["victim"]] -= 1
        sct.append(f["time"])
        scv.append(dict(run))

    def diff_at(n, t):
        i = bisect.bisect_right(sct, t) - 1
        s = scv[i] if i >= 0 else {}
        return s.get(n, 0) - s.get(other[n], 0)

    S = {n: collections.Counter() for n in P}
    # one row per hit and per kill between the two players, with both players' state just before it:
    # (t, order, kind, att, vic, att_eff, vic_eff, att_pw, vic_pw, att_rl, att_lg, vic_rl, vic_lg, vic_tss, frag_diff, time_left)
    ev = []
    for e in ((data.get("damage") or {}).get("events") or []):
        a, v, t = e.get("attacker"), e.get("victim"), e.get("time", -1)
        if a not in P or v not in P or t < 0 or a == v:
            continue
        sa, sv, dc = state(a, t - 30), state(v, t - 30), capped(e)
        S[a]["dmg"] += dc
        S[v]["taken"] += dc
        if sa[0] >= STACKED:
            S[a]["stacked_given"] += dc
        if sv[0] >= STACKED:
            S[v]["stacked_taken"] += dc
        ev.append((t, 0, "dmg", a, v, sa[0], sv[0], sa[3], sv[3], sa[1], sa[2], sv[1], sv[2], tss(v, t), diff_at(a, t), end - t))
    for f in frags:
        k, v, t = f["killer"], f["victim"], f["time"]
        if k == v:
            continue
        sk, sv = state(k, t - 30), state(v, t - 30)
        if tss(v, t) <= 2000:
            S[v]["spawnfrags_vs"] += 1          # KTX's spawn-frag stat, from the victim's side
        ev.append((t, 1, "frag", k, v, sk[0], sv[0], sk[3], sv[3], sk[1], sk[2], sv[1], sv[2], tss(v, t), diff_at(k, t), end - t))
    ev.sort(key=lambda r: (r[0], r[1]))

    takes = collections.defaultdict(list)   # name -> [(t, kind, wait_ms, opening)]
    allk = collections.Counter()
    for it in ((data.get("items") or {}).get("items") or []):
        kind, prev = it.get("kind"), None
        for ph in sorted((p for p in (it.get("phases") or []) if p.get("takenAt") is not None and p.get("takenBy") in P),
                         key=lambda p: p["takenAt"]):
            n, avail = ph["takenBy"], ph.get("availableFrom")
            takes[n].append((ph["takenAt"], kind, int(ph["takenAt"] - (avail or ph["takenAt"])), not avail))
            allk[kind] += 1
            if kind == "mh" and prev is not None:
                if prev == n:
                    S[n]["mh_kept"] += 1
                else:
                    S[prev]["mh_lost"] += 1
            prev = n
    for n in takes:
        takes[n].sort()

    coef = WINPROB.get(map_name) or WINPROB["pooled"]
    frag_equiv = _pwin(WINPROB["pooled"], 1, 0.5, 0, 0, 0, 0) - 0.5
    fights, cur = [], []
    for r in ev:
        if cur and r[0] - cur[-1][0] > FIGHT_GAP_MS:
            fights.append(cur)
            cur = []
        cur.append(r)
    if cur:
        fights.append(cur)
    last_death = {}
    ev_t = [r[0] for r in ev]
    for f in fights:
        first = f[0]
        starter, resp, edge = first[3], first[4], first[5] - first[6]
        S[starter]["fights"] += 1
        S[resp]["fights"] += 1
        S[starter]["started"] += 1
        if edge <= -EDGE:
            S[starter]["started_behind"] += 1
        if edge >= EDGE:
            S[starter]["started_ahead"] += 1
        kills = [r for r in f if r[2] == "frag"]
        if kills:
            k, v = kills[0][3], kills[0][4]
            for n, e in ((k, edge if k == starter else -edge), (v, edge if v == starter else -edge)):
                b = "even" if abs(e) < EDGE else ("behind" if e < 0 else "ahead")
                S[n][b + "_n"] += 1
                if n == k:
                    S[n][b + "_w"] += 1
            ke, ve = (first[5], first[6]) if first[3] == k else (first[6], first[5])
            kpw, vpw = (first[7], first[8]) if first[3] == k else (first[8], first[7])
            st = "both" if kpw and vpw else ("has powerup" if kpw else ("vs powerup" if vpw else "no powerup"))
            S[k]["adj"] += min(3.0, 0.5 / max(0.05, _pfight(ke - ve, st)))
        for r in kills:
            t, _, _, k, v, ae, ve, pa, pv, arl, alg, vrl, vlg, vtss, fd, tl = r
            frac = max(0.0, min(1.0, tl / end))
            pre = _pwin(coef, fd - 1, frac, ae - ve, (1 if pa else 0) - (1 if pv else 0), arl - vrl, alg - vlg)
            post = _pwin(coef, fd, frac, ae, (1 if pa else 0), arl, alg)
            S[k]["pm"] += post - pre
            S[v]["pm"] -= post - pre
            S[k]["kills"] += 1
            if vtss is not None and vtss <= 3000:
                S[v]["spawn_deaths"] += 1
            elif v in last_death and t - last_death[v] <= 14000:
                S[v]["chained_real"] += 1
            last_death[v] = t
            # item first: after dying, an armor or the mega before the next exchange of damage
            i = bisect.bisect_right(ev_t, t)
            nxt = ev[i][0] if i < len(ev) else None
            if any(x[0] > t and (nxt is None or x[0] < nxt) and x[1] in ("ra", "ya", "ga", "mh") for x in takes[v]):
                S[v]["item_first"] += 1

    rows = []
    for n in P:
        o, s, tk = other[n], S[n], takes.get(n, [])
        rows.append({
            "name": n, "opp": o, "win": 1 if score[n] > score[o] else 0, "minutes": round(end / 60000, 2),
            "frags": score[n], "kills": s["kills"], "deaths": len(P[n].get("d") or []), "adj_kills": round(s["adj"], 2),
            "dmg": s["dmg"], "taken": s["taken"], "stacked_given": s["stacked_given"], "stacked_taken": s["stacked_taken"],
            "spawn_deaths": s["spawn_deaths"], "spawnfrags_vs": s["spawnfrags_vs"], "chained_real": s["chained_real"],
            "fights": s["fights"], "started": s["started"], "started_behind": s["started_behind"], "started_ahead": s["started_ahead"],
            "even_w": s["even_w"], "even_n": s["even_n"], "behind_w": s["behind_w"], "behind_n": s["behind_n"],
            "ahead_w": s["ahead_w"], "ahead_n": s["ahead_n"], "item_first": s["item_first"],
            "ra": sum(1 for x in tk if x[1] == "ra"), "ra_on_timer": sum(1 for x in tk if x[1] == "ra" and x[2] <= ON_TIMER_MS),
            "ya": sum(1 for x in tk if x[1] == "ya"), "mh": sum(1 for x in tk if x[1] == "mh"),
            "plus_minus": round(s["pm"] / frag_equiv, 2),
            "mh_waits": [x[2] for x in tk if x[1] == "mh" and not x[3]], "mh_kept": s["mh_kept"], "mh_lost": s["mh_lost"],
            "mh_all": allk["mh"], "ra_waits": [x[2] for x in tk if x[1] == "ra" and not x[3]], "ra_all": allk["ra"],
            "model_version": VERSION,
        })
    return rows


def data_from_full(full):
    """compute()'s input from one `qw-analyze -view full` JSON (a locally parsed demo), for
    bulk backfills: same fields the five mvd-api calls return."""
    streams = full.get("streams") or {}
    return {"overview": {"matchEnd": (streams.get("global") or {}).get("matchEnd"),
                         "players": (full.get("match") or {}).get("players") or []},
            "streams": {"players": streams.get("players") or []},
            "damage": full.get("damage") or {}, "frags": full.get("frags") or {}, "items": full.get("items") or {}}


def rows_from_data(game, data):
    """Rows ready for duel_advanced_stats for one game from the todo list
    ({gid, map, date, players: [{cid, name}, {cid, name}]}), or (None, reason).
    Reasons: "no demo" (worth retrying later) | "not a duel" | "players not matched"."""
    import coaching as C                      # demo-name resolver shared with the coach
    if not data or not data.get("streams"):
        return None, "no demo"
    out = compute(data, game.get("map"))
    if not out:
        return None, "not a duel"
    names = [r["name"] for r in out]
    cid = {}
    for pl in game.get("players") or []:
        key = C._resolve_player_key(pl["name"], names) or C._resolve_player_key(pl["cid"], names)
        if key and key not in cid:
            cid[key] = pl["cid"]
    if len(cid) == 1 and len(game.get("players") or []) == 2:
        # one side matched by name: the other demo player is the other listed player
        left = [pl["cid"] for pl in game["players"] if pl["cid"] not in cid.values()]
        rest = [n for n in names if n not in cid]
        if len(left) == 1 and len(rest) == 1:
            cid[rest[0]] = left[0]
    if len(cid) != 2 or len(set(cid.values())) != 2:
        return None, "players not matched"
    rows = []
    for r in out:
        row = {k: v for k, v in r.items() if k not in ("name", "opp")}
        row.update(hub_game_id=game["gid"], canonical_id=cid[r["name"]], opponent_id=cid[r["opp"]],
                   played_at=game.get("date"), map=game.get("map"))
        rows.append(row)
    return rows, None


def rows_for_game(game, get):
    """rows_from_data() for a game fetched from the mvd-api. get(path) -> parsed JSON or None."""
    return rows_from_data(game, fetch(game["gid"], get))

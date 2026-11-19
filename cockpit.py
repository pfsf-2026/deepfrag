"""Live status of our own QW servers, for the cockpit page and the Stream Deck plugin
(Peter, 2026-11-13: a Xeneon Edge "cockpit" at home, Stream Deck keys at the office).

GET /api/players/{id}/kovaaks reads the KovaaK's username from the player's config profile
(the `kovaaks` key) and returns their most-played scenarios from KovaaK's public web backend,
each flagged when it was played at a different cm/360 than the profile's sens_cm360.

GET /api/fleet/live asks every fleet port directly over UDP (the QW "status" query, the
same one server browsers send) and returns map, match status, players and spectators.
Answers are cached for a few seconds so a wall of Stream Deck keys polling it doesn't
turn into a query storm on the boxes. LA is left out until Peter lists it.
"""

import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Response

from name_canon import clean_for_display

router = APIRouter()

FLEET = [
    {"city": "Denver", "host": "70.39.95.254"},
    {"city": "Dallas", "host": "144.202.66.126"},
    {"city": "Atlanta", "host": "155.138.204.79"},
]
PORTS = (28501, 28502, 28503, 28504)
CACHE_SECONDS = 5

_cache = {"at": 0.0, "body": None}
_lock = threading.Lock()


def _parse_status(raw: bytes) -> dict:
    """mvdsv's reply: '\\xff\\xff\\xff\\xffn\\key\\value...\\n' then one line per client:
    'userid frags time ping "name" "skin" top bottom'. Spectators have frags 'S'."""
    text = raw[4:].decode("latin1", "replace")
    lines = text.split("\n")
    head = lines[0][1:] if lines[0].startswith("n") else lines[0]
    parts = head.split("\\")[1:]
    info = dict(zip(parts[0::2], parts[1::2]))
    players, specs = [], []
    for ln in lines[1:]:
        ln = ln.strip("\x00 \r")
        if not ln or '"' not in ln:
            continue
        nums, rest = ln.split('"', 1)
        raw_name = rest.split('"', 1)[0]
        is_spec = raw_name.startswith("\\s\\")
        name = clean_for_display(raw_name[3:] if is_spec else raw_name)
        f = nums.split()
        frags, ping = (f[1] if len(f) > 1 else ""), (f[3] if len(f) > 3 else "")
        if is_spec or frags.upper() == "S":
            specs.append(name)
        else:
            try:
                players.append({"name": name, "frags": int(frags), "ping": int(ping) if ping.lstrip("-").isdigit() else None})
            except ValueError:
                players.append({"name": name, "frags": None, "ping": None})
    return {"map": info.get("map"), "status": info.get("status"), "mode": info.get("mode"),
            "maxclients": int(info["maxclients"]) if info.get("maxclients", "").isdigit() else None,
            "players": players, "spectators": specs}


def _query(host: str, port: int) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    t0 = time.time()
    try:
        s.sendto(b"\xff\xff\xff\xffstatus 23\n", (host, port))
        raw = s.recv(16384)
        out = _parse_status(raw)
        out.update(up=True, rtt_ms=round((time.time() - t0) * 1000))
        return out
    except OSError:
        return {"up": False}
    finally:
        s.close()


def _snapshot() -> dict:
    jobs = [(srv, port) for srv in FLEET for port in PORTS]
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        results = list(ex.map(lambda j: _query(j[0]["host"], j[1]), jobs))
    servers = []
    for (srv, port), r in zip(jobs, results):
        servers.append({"city": srv["city"], "address": f"{srv['host']}:{port}", "port": port,
                        "slot": PORTS.index(port) + 1, **r})
    return {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "servers": servers}


@router.get("/api/fleet/live")
def fleet_live(response: Response):
    """Every port on our servers right now: up/down, map, status, players, spectators."""
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    with _lock:
        if _cache["body"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            _cache["body"], _cache["at"] = _snapshot(), time.time()
        return _cache["body"]


# ── KovaaK's (public web backend, no key; undocumented, so failures degrade to an error field)
KOVAAKS = "https://kovaaks.com/webapp-backend"
_kv_cache: dict = {}
KV_SECONDS = 600


def _kv_get(path: str):
    req = urllib.request.Request(KOVAAKS + path, headers={"User-Agent": "Mozilla/5.0 (DeepFrag)"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _cm(v) -> float | None:
    m = re.search(r"[0-9]+(?:\.[0-9]+)?", str(v or ""))
    return float(m.group(0)) if m else None


@router.get("/api/players/{canonical_id}/kovaaks")
def player_kovaaks(canonical_id: str, response: Response, limit: int = 12):
    """Most-played KovaaK's scenarios for the player whose config names a `kovaaks` user."""
    from api import pg
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT config FROM player_configs WHERE canonical_id = %s", (canonical_id,))
        row = cur.fetchone()
    cfg = (row or {}).get("config") or {}
    user = str(cfg.get("kovaaks") or "").strip()
    if not user:
        raise HTTPException(404, "no kovaaks username in this player's config")
    sens = _cm(cfg.get("sens_cm360"))
    limit = max(1, min(int(limit or 12), 50))
    key = (user.lower(), limit)
    hit = _kv_cache.get(key)
    if not hit or time.time() - hit[0] > KV_SECONDS:
        q = urllib.parse.urlencode({"username": user, "page": 0, "max": limit, "sort_param[]": "count"})
        try:
            d = _kv_get(f"/user/scenario/total-play?{q}")
        except Exception as e:  # noqa: BLE001
            return {"user": user, "error": f"kovaaks unreachable: {type(e).__name__}", "scenarios": []}
        rows = []
        for r in d.get("data") or []:
            a = r.get("attributes") or {}
            cm = a.get("cm360")
            rows.append({"scenario": r.get("scenarioName"), "plays": (r.get("counts") or {}).get("plays"),
                         "best": r.get("score"), "rank": r.get("rank"),
                         "cm360": round(cm, 2) if isinstance(cm, (int, float)) else None,
                         "fov": a.get("fov"), "played_at": a.get("epoch")})
        hit = (time.time(), {"user": user, "total_scenarios": d.get("total"), "scenarios": rows})
        _kv_cache[key] = hit
    body = dict(hit[1], sens_cm360=sens)
    for r in body["scenarios"]:
        r["sens_match"] = None if sens is None or r["cm360"] is None else abs(r["cm360"] - sens) < 0.1
    response.headers["Cache-Control"] = "public, max-age=300"
    return body


# ── Server wall: every live server on the hub, with our ratings on top ────────────────────────
# GET /api/servers/wall is the hub's live list (hubapi.quakeworld.nu, the one hub.quakeworld.nu
# draws) with each player matched to a DeepFrag profile: rating and tier in the server's mode, a
# rating-only win chance for a duel, a badge when the players are the two sides of an open ladder
# challenge. Our own empty ports are appended so they can still be joined from the wall.
# (Peter, 2026-11-19: the full-width Xeneon Edge view.)
HUB_SERVERS = "https://hubapi.quakeworld.nu/v2/servers/mvdsv"
WALL_SECONDS = 5
RATED_MODES = ("1on1", "2on2", "4on4")
_wall = {"at": 0.0, "body": None}
_wall_lock = threading.Lock()
_cutoffs: dict = {}            # mode -> (fetched_at, cutoffs)


def _hub_servers() -> list:
    req = urllib.request.Request(HUB_SERVERS, headers={"User-Agent": "DeepFrag cockpit"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode())


def _wall_lookups(cur, names: list) -> tuple:
    """names -> canonical ids (raw-name map first, then the normalized name as an id), and
    those ids' overall ratings per mode."""
    import name_canon as NC
    norm = {n: NC.normalize(n) for n in names}
    keys = list({*names, *norm.values(), *(n.lower() for n in names)})
    cur.execute("SELECT raw_name, canonical_id FROM player_name_map WHERE raw_name = ANY(%s)", (keys,))
    by_raw = {r["raw_name"]: r["canonical_id"] for r in cur.fetchall()}
    cur.execute("SELECT canonical_id, display_name FROM players_canonical WHERE canonical_id = ANY(%s)"
                " AND NOT COALESCE(hidden, FALSE)", (list({*norm.values(), *by_raw.values()}),))
    known = {r["canonical_id"]: r["display_name"] for r in cur.fetchall()}
    cid = {}
    for n in names:
        c = by_raw.get(n) or by_raw.get(norm[n]) or by_raw.get(n.lower()) or norm[n]
        if c in known:
            cid[n] = c
    cur.execute("SELECT canonical_id, mode, mu, sigma, matches_rated FROM ratings"
                " WHERE canonical_id = ANY(%s) AND map = '' AND mode = ANY(%s)",
                (list(set(cid.values())), list(RATED_MODES)))
    ratings = {(r["canonical_id"], r["mode"]): r for r in cur.fetchall()}
    return cid, ratings


def _wall_cutoffs(cur, mode: str) -> dict:
    from api import _get_tier_cutoffs
    hit = _cutoffs.get(mode)
    if not hit or time.time() - hit[0] > 600:
        hit = _cutoffs[mode] = (time.time(), _get_tier_cutoffs(cur, mode))
    return hit[1]


def _wall_ladder(cur) -> list:
    cur.execute("""SELECT c.id, c.status, l.name AS ladder, l.team_size, a.members AS a, b.members AS b
                   FROM ladder_challenges c JOIN ladders l ON l.id = c.ladder_id
                   JOIN ladder_teams a ON a.id = c.challenger_id JOIN ladder_teams b ON b.id = c.challenged_id
                   WHERE c.status IN ('open', 'scheduled')""")
    return [dict(r) for r in cur.fetchall()]


def _wall_build() -> dict:
    from api import pg
    from tiers import tier_for
    from openskill.models import PlackettLuce
    model = PlackettLuce(mu=1500.0, sigma=500.0, beta=250.0)   # same model as /api/h2h

    hub_error = None
    try:
        hub = _hub_servers()
    except Exception as e:  # noqa: BLE001
        hub, hub_error = [], f"hub unreachable: {type(e).__name__}"
    our_hosts = {s["host"]: s["city"] for s in FLEET}
    names = sorted({p["name"] for s in hub for p in s.get("players") or [] if not p.get("is_bot") and p.get("name")})

    with pg() as conn:
        cur = conn.cursor()
        cid, ratings = _wall_lookups(cur, names) if names else ({}, {})
        cutoffs = {m: _wall_cutoffs(cur, m) for m in RATED_MODES}
        challenges = _wall_ladder(cur) if names else []

    servers = []
    for s in hub:
        mode = s.get("mode") or ""
        rmode = mode if mode in RATED_MODES else "1on1"
        host = s["address"].rsplit(":", 1)[0]
        players = []
        for p in s.get("players") or []:
            c = None if p.get("is_bot") else cid.get(p.get("name"))
            r = ratings.get((c, rmode)) if c else None
            players.append({"name": p.get("name"), "team": p.get("team") or "", "colors": p.get("colors"),
                            "frags": p.get("frags"), "ping": p.get("ping"), "cc": p.get("cc") or "",
                            "is_bot": bool(p.get("is_bot")), "id": c,
                            "mu": round(r["mu"]) if r else None, "sigma": round(r["sigma"], 1) if r else None,
                            "tier": tier_for(r["mu"], cutoffs[rmode]) if r else None})
        humans = [p for p in players if not p["is_bot"]]
        win_a = None
        if mode == "1on1" and len(humans) == 2 and all(p["mu"] is not None for p in humans):
            a, b = (model.rating(mu=p["mu"], sigma=p["sigma"]) for p in humans)
            win_a = round(model.predict_win([[a], [b]])[0], 3)
        here = {p["id"] for p in humans if p["id"]}
        ladder = None
        for c in challenges:
            need = max(1, int(c["team_size"] or 1))
            if all(len(here & set(side or [])) >= min(need, len(side or []) or need) for side in (c["a"], c["b"])):
                ladder = {"challenge_id": c["id"], "ladder": c["ladder"]}
                break
        rated = sorted((p["mu"] for p in humans if p["mu"] is not None), reverse=True)
        q = s.get("qtv_stream") or {}
        geo = s.get("geo") or {}
        st = s.get("status") or {}
        servers.append({
            "address": s["address"], "title": s.get("title"), "mode": mode, "submode": s.get("submode") or "",
            "map": (s.get("settings") or {}).get("map"), "hostname": (s.get("settings") or {}).get("hostname"),
            "status": st.get("name"), "status_text": st.get("description"), "time": s.get("time"),
            "slots": s.get("player_slots"), "players": players,
            "spectators": (s.get("spectator_slots") or {}).get("used", 0) + int(q.get("spectator_count") or 0),
            "qtv": q.get("url") or None, "cc": geo.get("cc") or "", "region": geo.get("region") or "",
            "city": our_hosts.get(host) or geo.get("city") or "", "ours": host in our_hosts,
            "win_a": win_a, "ladder": ladder,
            # the two best-rated players here, for the "big game" highlight
            "top2": rated[1] if len(rated) > 1 else None,
        })

    # our own ports that the hub isn't listing (empty, or the hub hasn't seen them yet)
    seen = {s["address"] for s in servers}
    with _lock:
        if _cache["body"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            _cache["body"], _cache["at"] = _snapshot(), time.time()
        fleet = _cache["body"]
    for f in fleet["servers"]:
        if not f.get("up") or f["address"] in seen:
            continue
        servers.append({"address": f["address"], "title": f"{f['city']} #{f['slot']}", "mode": f.get("mode") or "",
                        "submode": "", "map": f.get("map"), "hostname": None,
                        "status": "Standby" if f.get("players") else "Empty", "status_text": f.get("status"),
                        "time": None, "slots": {"used": len(f.get("players") or []), "total": f.get("maxclients")},
                        "players": [{"name": p["name"], "team": "", "colors": None, "frags": p["frags"], "ping": p["ping"],
                                     "cc": "", "is_bot": False, "id": None, "mu": None, "sigma": None, "tier": None}
                                    for p in f.get("players") or []],
                        "spectators": len(f.get("spectators") or []), "qtv": None, "cc": "US",
                        "region": "North America", "city": f["city"], "ours": True, "win_a": None, "ladder": None,
                        "top2": None})
    return {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hub_error": hub_error,
            "servers": servers}


@router.get("/api/servers/wall")
def servers_wall(response: Response):
    """Every live server (hub list + our own ports) with DeepFrag ratings on the players."""
    response.headers["Cache-Control"] = f"public, max-age={WALL_SECONDS}"
    with _wall_lock:
        if _wall["body"] is None or time.time() - _wall["at"] > WALL_SECONDS:
            _wall["body"], _wall["at"] = _wall_build(), time.time()
        return _wall["body"]

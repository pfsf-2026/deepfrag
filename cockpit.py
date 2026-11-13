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

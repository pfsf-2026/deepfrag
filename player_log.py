"""Server join log: every connect on our own QW servers, by IP and nick (Peter, 2026-11-09).

Peter: "track all players who join our servers ... a full log by IP address and nicknames ...
connect IPs to nicknames, and when people join a server with a nick that doesn't match up
with the IP, that means they are aliasing so connect the IP to the normal nick." Owner-only:
Peter's Discord account (OWNER_DISCORD_IDS) or the admin key, not the other ladder admins.

Source: mvdsv's player logs on each fleet box (/opt/qw/nquakesv/logs/player_<port>_0000.log),
one line per connect / disconnect with the nick, userid, IP and userinfo. The devbox pulls
them with tools/player_log/pull_joins.py and posts them to /ingest; nothing runs on the boxes.

How a join is judged:
  - Each IP has a NORMAL NICK: the one Peter set, or else the nick seen there on the most
    days. Joins through a qwfwd proxy (*qwfwd in userinfo) carry the proxy's IP, which many
    players share, so they never decide or get judged against an IP's normal nick.
  - A join whose nick isn't the IP's normal nick is an ALIAS of it, unless Peter marked that
    nick on that IP as a separate person (a brother on the same connection, a LAN).
  - Peter can confirm an alias, which keeps it flagged but marks it as known.
"""

import os
import re
from datetime import datetime

from fastapi import APIRouter, Body, Header, HTTPException, Query

from name_canon import clean_for_display, normalize

router = APIRouter()

# Peter (Cronus). Override with a comma-separated list on the service if that ever changes.
DEFAULT_OWNERS = "304705182657150987"

# Fleet aliases → the label the page shows
SERVER_LABELS = {
    "qw-dal-1": "Dallas",
    "qw-atl-1": "Atlanta",
    "qw-den-2": "Denver",
    "qw-den-1": "Denver (old AWS)",
}

SESSION_GAP = "3 hours"  # one session = a run of events for the same slot with no gap longer than this
VERDICTS = ("alias", "separate")


def _deps():
    # Lazy import: api.py includes this router at module bottom (same pattern as vote.py).
    from api import pg, _current_user
    return pg, _current_user


def check_owner(authorization: str | None):
    """The admin key, or a signed-in Discord account in OWNER_DISCORD_IDS. Other ladder
    admins get a 403: this page holds players' IP addresses."""
    _, current_user = _deps()
    key = os.environ.get("SYNC_SECRET")
    if key and authorization == f"Bearer {key}":
        return "admin-key"
    owners = {s.strip() for s in os.environ.get("OWNER_DISCORD_IDS", DEFAULT_OWNERS).split(",") if s.strip()}
    u = current_user(authorization, required=False)
    if u and str(u.get("discord_id")) in owners:
        return u.get("username") or str(u.get("discord_id"))
    raise HTTPException(403, "owner only")


def ensure(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS server_joins (
          id         BIGSERIAL PRIMARY KEY,
          ts         TIMESTAMPTZ NOT NULL,
          server     TEXT NOT NULL,
          port       INT NOT NULL,
          event      TEXT NOT NULL,
          name       TEXT NOT NULL,
          name_norm  TEXT NOT NULL,
          userid     INT,
          ip         TEXT NOT NULL,
          realip     TEXT,
          client     TEXT,
          team       TEXT,
          spectator  BOOLEAN NOT NULL DEFAULT FALSE,
          proxy      BOOLEAN NOT NULL DEFAULT FALSE,
          UNIQUE (server, port, ts, event, userid, name)
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS server_joins_ip ON server_joins (ip)")
    cur.execute("CREATE INDEX IF NOT EXISTS server_joins_nick ON server_joins (name_norm)")
    cur.execute("CREATE INDEX IF NOT EXISTS server_joins_ts ON server_joins (ts DESC)")
    # Peter's choice of normal nick for an IP (overrides the most-days guess)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_owner (
          ip         TEXT PRIMARY KEY,
          nick       TEXT NOT NULL,
          nick_norm  TEXT NOT NULL,
          note       TEXT,
          set_by     TEXT,
          set_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    # Per IP and nick: 'alias' (confirmed alias of the normal nick) or 'separate' (another person)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_nick_verdict (
          ip         TEXT NOT NULL,
          name_norm  TEXT NOT NULL,
          verdict    TEXT NOT NULL,
          set_by     TEXT,
          set_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (ip, name_norm)
        )""")


DUP_PREFIX = re.compile(r"^\(\d+\)")  # mvdsv renames a second "cronus" to "(1)cronus"


def display(name: str | None) -> str | None:
    """Readable nick; `bare` also drops the "(1)" prefix (for normal nicks and grouped rows)."""
    if not name:
        return name
    return clean_for_display(name) or name


def bare(name: str | None) -> str | None:
    return display(DUP_PREFIX.sub("", name)) if name else name


def norm(name: str) -> str:
    name = DUP_PREFIX.sub("", name or "")
    return normalize(name) or name.strip().lower()


# The normal nick of every IP: Peter's choice, else the non-proxy nick seen on the most days
# (ties: the one seen first). Columns: ip, owner_norm, owner (display), manual.
OWNER_CTE = """
  auto AS (
    SELECT DISTINCT ON (ip) ip, name_norm AS owner_norm, name AS owner
    FROM (SELECT ip, name_norm, MIN(name) AS name, COUNT(DISTINCT ts::date) AS days, MIN(ts) AS first
          FROM server_joins WHERE NOT proxy GROUP BY ip, name_norm) x
    ORDER BY ip, days DESC, first
  ),
  owners AS (
    SELECT COALESCE(o.ip, a.ip) AS ip,
           COALESCE(o.nick_norm, a.owner_norm) AS owner_norm,
           COALESCE(o.nick, a.owner) AS owner,
           (o.ip IS NOT NULL) AS manual
    FROM auto a FULL JOIN ip_owner o ON o.ip = a.ip
  )"""


def _status_sql(alias="s"):
    """SQL for a join's status against its IP's normal nick: proxy / normal / separate /
    alias (confirmed) / alias? (unconfirmed)."""
    return f"""CASE
        WHEN {alias}.proxy THEN 'proxy'
        WHEN o.owner_norm IS NULL OR {alias}.name_norm = o.owner_norm THEN 'normal'
        WHEN v.verdict = 'separate' THEN 'separate'
        WHEN v.verdict = 'alias' THEN 'alias'
        ELSE 'alias?' END"""


def _filters(q, server, where, params, t="j"):
    if q:
        q = q.strip()
        if re.fullmatch(r"[0-9.:a-fA-F]+", q) and ("." in q or ":" in q):
            where.append(f"{t}.ip LIKE %(ipq)s")
            params["ipq"] = q + "%"
        else:
            where.append(f"({t}.name_norm LIKE %(nq)s OR {t}.name ILIKE %(rq)s)")
            params["nq"] = "%" + norm(q) + "%"
            params["rq"] = "%" + q + "%"
    if server:
        where.append(f"{t}.server = %(server)s")
        params["server"] = server


# ── Ingest (devbox puller, admin key only) ────────────────────────────────────

@router.post("/api/admin/player-log/ingest")
def ingest(rows: list = Body(..., embed=True), authorization: str | None = Header(default=None)):
    """Rows parsed from the player logs by tools/player_log/pull_joins.py. Re-sending a row
    is harmless (unique on server, port, time, event, userid, nick)."""
    key = os.environ.get("SYNC_SECRET")
    if not key or authorization != f"Bearer {key}":
        raise HTTPException(403, "admin key required")
    if len(rows) > 5000:
        raise HTTPException(400, "at most 5000 rows per call")
    vals = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(r["ts"])
            name = str(r["name"])[:64]
            vals.append((ts, str(r["server"])[:32], int(r["port"]), str(r["event"])[:16], name, norm(name)[:64],
                         int(r["userid"]) if r.get("userid") not in (None, "") else None,
                         str(r["ip"])[:64], (r.get("realip") or None), (r.get("client") or None),
                         (r.get("team") or None), bool(r.get("spectator")), bool(r.get("proxy"))))
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(400, f"bad row: {e}")
    pg, _ = _deps()
    import psycopg2.extras
    with pg() as conn:
        cur = conn.cursor()
        ensure(cur)
        res = psycopg2.extras.execute_values(cur, """
            INSERT INTO server_joins (ts, server, port, event, name, name_norm, userid, ip, realip,
                                      client, team, spectator, proxy)
            VALUES %s ON CONFLICT DO NOTHING RETURNING id""", vals, page_size=1000, fetch=True)
        conn.commit()
    return {"received": len(vals), "inserted": len(res)}


# ── Read (owner only) ─────────────────────────────────────────────────────────

@router.get("/api/admin/player-log/joins")
def joins(q: str = Query(default=""), server: str = Query(default=""),
          only: str = Query(default=""), limit: int = Query(default=100, ge=1, le=500),
          offset: int = Query(default=0, ge=0), authorization: str | None = Header(default=None)):
    """The join log, newest first, one row per session (a player's run of connects on one
    server slot; mvdsv logs a connect again on every map). `only=alias` keeps the joins
    whose nick isn't the IP's normal nick (confirmed or not)."""
    check_owner(authorization)
    where, params = [], {"limit": limit, "offset": offset, "gap": SESSION_GAP}
    _filters(q, server, where, params)
    status = _status_sql("s")
    pg, _ = _deps()
    with pg() as conn:
        cur = conn.cursor()
        ensure(cur)
        cur.execute(f"""
            WITH {OWNER_CTE},
            ev AS (
              SELECT j.*, CASE WHEN LAG(j.ts) OVER w IS NULL OR j.ts - LAG(j.ts) OVER w > %(gap)s::interval
                               THEN 1 ELSE 0 END AS brk
              FROM server_joins j {"WHERE " + " AND ".join(where) if where else ""}
              WINDOW w AS (PARTITION BY j.server, j.port, j.userid, j.ip, j.name_norm ORDER BY j.ts)
            ),
            sid AS (
              SELECT ev.*, SUM(brk) OVER (PARTITION BY server, port, userid, ip, name_norm ORDER BY ts) AS sess
              FROM ev
            ),
            s AS (
              SELECT server, port, userid, ip, name_norm, MAX(name) AS name, MIN(ts) AS first_at, MAX(ts) AS last_at,
                     COUNT(*) FILTER (WHERE event = 'connect') AS connects,
                     BOOL_OR(spectator) AS spectator, BOOL_OR(proxy) AS proxy,
                     MAX(client) AS client, MAX(team) AS team, MAX(realip) AS realip
              FROM sid GROUP BY server, port, userid, ip, name_norm, sess
            )
            SELECT s.*, o.owner, o.manual, v.verdict, {status} AS status, COUNT(*) OVER () AS total
            FROM s LEFT JOIN owners o ON o.ip = s.ip
                   LEFT JOIN ip_nick_verdict v ON v.ip = s.ip AND v.name_norm = s.name_norm
            {"WHERE " + status + " IN ('alias', 'alias?')" if only == "alias" else ""}
            ORDER BY s.last_at DESC LIMIT %(limit)s OFFSET %(offset)s""", params)
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT server, COUNT(*) AS n, MAX(ts) AS last FROM server_joins GROUP BY server ORDER BY server")
        servers = [dict(r) for r in cur.fetchall()]
    total = rows[0]["total"] if rows else 0
    for r in rows:
        r.pop("total", None)
        r["name"] = display(r["name"])
        r["owner"] = bare(r["owner"])
        r["server_label"] = SERVER_LABELS.get(r["server"], r["server"])
    for s in servers:
        s["label"] = SERVER_LABELS.get(s["server"], s["server"])
    return {"joins": rows, "total": total, "servers": servers}


@router.get("/api/admin/player-log/ips")
def ips(q: str = Query(default=""), only: str = Query(default=""),
        limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
        authorization: str | None = Header(default=None)):
    """Every IP with its normal nick and each nick seen on it (days, joins, first/last, status).
    `q` matches the IP or any nick used on it; `only=alias` keeps IPs with an alias."""
    check_owner(authorization)
    where, params = [], {"limit": limit, "offset": offset}
    if q:
        sub, sp = [], {}
        _filters(q, "", sub, sp, t="m")
        params.update(sp)
        where.append(f"n.ip IN (SELECT m.ip FROM server_joins m WHERE {' AND '.join(sub)})")
    pg, _ = _deps()
    with pg() as conn:
        cur = conn.cursor()
        ensure(cur)
        cur.execute(f"""
            WITH {OWNER_CTE},
            n AS (
              SELECT ip, name_norm, MAX(name) AS name, COUNT(DISTINCT ts::date) AS days,
                     COUNT(*) FILTER (WHERE event = 'connect') AS connects, MIN(ts) AS first_at, MAX(ts) AS last_at,
                     BOOL_OR(proxy) AS proxy, ARRAY_AGG(DISTINCT server) AS servers
              FROM server_joins GROUP BY ip, name_norm
            ),
            nn AS (
              SELECT n.*, o.owner, o.owner_norm, o.manual, v.verdict, {_status_sql("n")} AS status
              FROM n LEFT JOIN owners o ON o.ip = n.ip
                     LEFT JOIN ip_nick_verdict v ON v.ip = n.ip AND v.name_norm = n.name_norm
              {"WHERE " + " AND ".join(where) if where else ""}
            ),
            per_ip AS (
              SELECT ip, MAX(owner) AS owner, BOOL_OR(manual) AS manual, MIN(first_at) AS first_at,
                     MAX(last_at) AS last_at, BOOL_AND(proxy) AS proxy,
                     COUNT(*) FILTER (WHERE status IN ('alias', 'alias?')) AS aliases,
                     COUNT(*) FILTER (WHERE status = 'alias?') AS unconfirmed,
                     JSON_AGG(JSON_BUILD_OBJECT('name', name, 'name_norm', name_norm, 'days', days,
                              'connects', connects, 'first_at', first_at, 'last_at', last_at,
                              'status', status, 'servers', servers) ORDER BY days DESC, last_at DESC) AS nicks,
                     (SELECT note FROM ip_owner io WHERE io.ip = nn.ip) AS note
              FROM nn GROUP BY ip
            )
            SELECT *, COUNT(*) OVER () AS total FROM per_ip
            {"WHERE aliases > 0" if only == "alias" else ""}
            ORDER BY last_at DESC LIMIT %(limit)s OFFSET %(offset)s""", params)
        rows = [dict(r) for r in cur.fetchall()]
    total = rows[0]["total"] if rows else 0
    for r in rows:
        r.pop("total", None)
        r["owner"] = bare(r["owner"])
        for n in r["nicks"]:
            n["name"] = bare(n["name"])
            n["servers"] = [SERVER_LABELS.get(s, s) for s in (n["servers"] or [])]
    return {"ips": rows, "total": total}


@router.get("/api/admin/player-log/nicks")
def nicks(q: str = Query(default=""), limit: int = Query(default=100, ge=1, le=500),
          offset: int = Query(default=0, ge=0), authorization: str | None = Header(default=None)):
    """Every nick with the IPs it used and, for each IP, that IP's normal nick: a nick that
    shows up on someone else's IP is that person aliasing."""
    check_owner(authorization)
    where, params = [], {"limit": limit, "offset": offset}
    _filters(q, "", where, params)
    pg, _ = _deps()
    with pg() as conn:
        cur = conn.cursor()
        ensure(cur)
        cur.execute(f"""
            WITH {OWNER_CTE},
            n AS (
              SELECT j.name_norm, j.ip, MAX(j.name) AS name, COUNT(DISTINCT j.ts::date) AS days,
                     MIN(j.ts) AS first_at, MAX(j.ts) AS last_at, BOOL_OR(j.proxy) AS proxy
              FROM server_joins j {"WHERE " + " AND ".join(where) if where else ""}
              GROUP BY j.name_norm, j.ip
            ),
            nn AS (
              SELECT n.*, o.owner, {_status_sql("n")} AS status
              FROM n LEFT JOIN owners o ON o.ip = n.ip
                     LEFT JOIN ip_nick_verdict v ON v.ip = n.ip AND v.name_norm = n.name_norm
            )
            SELECT name_norm, MAX(name) AS name, SUM(days) AS days, MIN(first_at) AS first_at, MAX(last_at) AS last_at,
                   COUNT(*) AS ip_count,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT CASE WHEN status IN ('alias', 'alias?') THEN owner END), NULL) AS alias_of,
                   JSON_AGG(JSON_BUILD_OBJECT('ip', ip, 'days', days, 'first_at', first_at, 'last_at', last_at,
                            'owner', owner, 'status', status) ORDER BY last_at DESC) AS ips,
                   COUNT(*) OVER () AS total
            FROM nn GROUP BY name_norm
            ORDER BY MAX(last_at) DESC LIMIT %(limit)s OFFSET %(offset)s""", params)
        rows = [dict(r) for r in cur.fetchall()]
    total = rows[0]["total"] if rows else 0
    for r in rows:
        r.pop("total", None)
        r["name"] = bare(r["name"])
        r["alias_of"] = sorted({bare(a) for a in (r["alias_of"] or [])})
        for i in r["ips"]:
            i["owner"] = bare(i.get("owner"))
    return {"nicks": rows, "total": total}


# ── Edit (owner only) ─────────────────────────────────────────────────────────

@router.post("/api/admin/player-log/ip-owner")
def set_owner(ip: str = Body(...), nick: str | None = Body(default=None), note: str | None = Body(default=None),
              authorization: str | None = Header(default=None)):
    """Set an IP's normal nick (empty nick: back to the most-days guess)."""
    who = check_owner(authorization)
    ip = ip.strip()
    pg, _ = _deps()
    with pg() as conn:
        cur = conn.cursor()
        ensure(cur)
        if not (nick or "").strip():
            cur.execute("DELETE FROM ip_owner WHERE ip=%s", (ip,))
        else:
            nick = nick.strip()[:64]
            cur.execute("""INSERT INTO ip_owner (ip, nick, nick_norm, note, set_by) VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (ip) DO UPDATE SET nick=EXCLUDED.nick, nick_norm=EXCLUDED.nick_norm,
                             note=EXCLUDED.note, set_by=EXCLUDED.set_by, set_at=now()""",
                        (ip, nick, norm(nick), (note or "").strip()[:500] or None, who))
        conn.commit()
    return {"ip": ip, "owner": nick or None}


@router.post("/api/admin/player-log/verdict")
def set_verdict(ip: str = Body(...), nick: str = Body(...), verdict: str | None = Body(default=None),
                authorization: str | None = Header(default=None)):
    """Mark a nick on an IP as a confirmed 'alias' of the IP's normal nick, or a 'separate'
    person; no verdict clears it."""
    who = check_owner(authorization)
    if verdict not in (None, "", *VERDICTS):
        raise HTTPException(400, "verdict must be alias, separate or empty")
    ip, nn = ip.strip(), norm(nick)
    pg, _ = _deps()
    with pg() as conn:
        cur = conn.cursor()
        ensure(cur)
        if not verdict:
            cur.execute("DELETE FROM ip_nick_verdict WHERE ip=%s AND name_norm=%s", (ip, nn))
        else:
            cur.execute("""INSERT INTO ip_nick_verdict (ip, name_norm, verdict, set_by) VALUES (%s, %s, %s, %s)
                           ON CONFLICT (ip, name_norm) DO UPDATE SET verdict=EXCLUDED.verdict,
                             set_by=EXCLUDED.set_by, set_at=now()""", (ip, nn, verdict, who))
        conn.commit()
    return {"ip": ip, "nick": nn, "verdict": verdict or None}

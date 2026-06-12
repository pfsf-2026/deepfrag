#!/usr/bin/env python3
"""DeepFrag API — FastAPI app reading from Postgres.

Endpoints:
  GET /api/health
  GET /api/rankings?mode=1on1&min_matches=20&active=true&limit=500
  GET /api/players/{canonical_id}
  GET /api/players/{canonical_id}/maps
  GET /api/search?q=cron&limit=20

Profile + maps reuse the existing build logic from export.py — we just point
its db handle at Postgres. SQLite-isms in export.py SQL (e.g. strftime) are
patched in db_pg.py via a thin row_factory shim.

Run local:
  uvicorn api:app --reload --port 8000
"""

import base64
import json
import os
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from tiers import tier_for, compute_cutoffs
from export_rankings import (
    decayed_sigma, effective_sigma, diversity_factor,
    DIVERSITY_THRESHOLD_OVERALL, DIVERSITY_THRESHOLD_PER_MAP,
)


def _get_tier_cutoffs(cur, mode: str, map_name: str = "") -> dict:
    """Fetch all conservative ratings for this (mode, map) bucket and compute
    percentile-based tier cutoffs. Cheap (one indexed SELECT + sort) — called
    once per ranking response, once per profile mode/map. See tiers.py for
    the Div 0/1/2/3 percentile breaks."""
    cur.execute(
        "SELECT conservative FROM ratings WHERE mode=%s AND map=%s AND matches_rated >= 10",
        (mode, map_name),
    )
    return compute_cutoffs(r["conservative"] for r in cur.fetchall())
import profile_pg
import stats_pg

PG_URL = os.environ.get("DEEPFRAG_PG_URL", "postgresql:///deepfrag")

app = FastAPI(title="DeepFrag API", version="0.2")

# NOTE: do NOT run DB migrations in a startup event. An ALTER TABLE on boot makes
# every cold-starting instance contend for an ACCESS EXCLUSIVE lock; under any
# parallelism they serialize past the startup probe deadline → no instance
# becomes ready → full outage (2026-06-06). Columns are ensured lazily by the
# endpoints that need them (_ensure_canon_review_schema) and already exist in
# prod. Schema changes go through a one-shot admin endpoint, never on startup.

# Compress rankings (240KB → ~30KB) and any future large payloads.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Wide-open CORS for now — the Cloudflare Pages frontend is the only consumer.
# Admin write endpoints (scheduler pause/resume, rerate) need POST, so we allow
# all standard methods. Auth still gates writes via Bearer SYNC_SECRET.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Bounded Postgres connection pool. WHY: a fresh psycopg2.connect per request,
# combined with Cloud Run concurrency=80 × maxScale and the per-minute sync-live
# job + slow coaching calls, exhausted Cloud SQL's connection slots ("remaining
# connection slots are reserved" → every request fails to connect → site down,
# 2026-05-29). A ThreadedConnectionPool caps total connections per instance so we
# can never blow past the server limit; requests briefly wait for a free slot
# instead of failing. maxconn × maxScale must stay under the Cloud SQL limit:
# 10 × 5 instances = 50, safely under Postgres default 100 (minus reserved).
from psycopg2.pool import ThreadedConnectionPool

_POOL_MAX = int(os.environ.get("PG_POOL_MAX", "10"))
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            1, _POOL_MAX, PG_URL, cursor_factory=psycopg2.extras.RealDictCursor
        )
    return _pool


import threading
import time as _time

_pool_lock = threading.Condition()


@contextmanager
def pg():
    """Per-request Postgres connection drawn from a bounded pool. Returned to the
    pool (not closed) on exit. IMPORTANT: callers that do slow work (demo parse,
    LLM calls) must finish the DB work and let the `with pg()` block CLOSE before
    that slow work, so the connection isn't held idle for tens of seconds.

    ThreadedConnectionPool.getconn() RAISES when exhausted rather than waiting, so
    we wrap it in a short wait-and-retry (FastAPI runs sync endpoints in a ~40-
    thread pool, which can momentarily exceed the connection cap). Cloud Run
    concurrency is also capped low so this rarely triggers."""
    pool = _get_pool()
    conn = None
    deadline = _time.monotonic() + 10.0
    while conn is None:
        try:
            with _pool_lock:
                conn = pool.getconn()
        except psycopg2.pool.PoolError:
            if _time.monotonic() > deadline:
                raise HTTPException(503, "database busy, retry shortly")
            _time.sleep(0.05)
    try:
        yield conn
        conn.rollback()  # clean any open/aborted txn so the pooled conn is reusable
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        with _pool_lock:
            pool.putconn(conn)


# ── Auth (Discord OAuth → JWT) ───────────────────────────────────────────────
# Token-based: callback mints a JWT, frontend stores it + sends Bearer. The /api
# proxy forwards Authorization verbatim and never caches authed requests.

def _current_user(authorization: str | None, required: bool = True):
    import auth as A
    tok = (authorization or "")
    tok = tok[7:].strip() if tok.lower().startswith("bearer ") else tok.strip()
    payload = A.jwt_decode(tok) if tok else None
    if not payload:
        if required:
            raise HTTPException(401, "not authenticated")
        return None
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("""SELECT discord_id, username, global_name, avatar, canonical_id, is_admin, verified,
                              region, country, city, state, favorite_server, timezone, availability
                       FROM users WHERE discord_id=%s""", (payload.get("sub"),))
        u = cur.fetchone()
    if not u and required:
        raise HTTPException(401, "unknown user")
    return u


@app.get("/api/auth/discord/login")
def auth_login():
    """Kick off Discord OAuth. State is a short-lived signed token (CSRF)."""
    import auth as A
    if not os.environ.get("DISCORD_CLIENT_ID"):
        raise HTTPException(503, "Discord OAuth not configured")
    return RedirectResponse(A.login_url(A.jwt_encode({"k": "state"}, ttl=600)))


@app.get("/api/auth/discord/callback")
def auth_callback(code: str = Query(...), state: str = Query(default="")):
    """Discord redirects here with a code; exchange it, upsert the user, mint a
    session JWT, and bounce to the frontend with the token."""
    import auth as A
    if not A.jwt_decode(state):
        raise HTTPException(400, "invalid or expired state")
    try:
        du = A.exchange_code(code)
    except Exception as e:
        raise HTTPException(400, f"Discord auth failed: {e}")
    if not du or not du.get("id"):
        raise HTTPException(400, "Discord authentication failed (no user id)")
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        u = A.upsert_user(cur, du)
        conn.commit()
    token = A.jwt_encode({"sub": u["discord_id"], "name": u.get("global_name") or u.get("username")})
    print(f"[auth.callback] user={u['discord_id']} token_len={len(token)} -> HTML token handoff", flush=True)
    return _token_handoff_html(token)


def _token_handoff_html(token: str) -> HTMLResponse:
    """Deliver the session token to the SPA via an HTML BODY, not a redirect.

    Every redirect-based attempt (?token= query, #token= fragment) lost the token
    because the CF Pages /api proxy's fetch() normalizes the Location header and
    drops the query/fragment on the same-zone hop back to /auth. An HTML body
    can't be normalized — the proxy passes 200 bodies through verbatim — so we
    embed the token in a tiny page that stores it (same-origin localStorage) and
    navigates to the ladder. Bulletproof against the proxy + path canonicalizer.
    """
    payload = json.dumps(token)  # safe JS string literal (token is JWT-charset anyway)
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Signing in… · DeepFrag</title>"
        "<meta name='robots' content='noindex'>"
        "<style>body{background:#0a0d12;color:#94a3b8;font-family:system-ui,sans-serif;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
        ".s{width:28px;height:28px;border:3px solid #2b3445;border-top-color:#14e6c0;"
        "border-radius:50%;animation:spin .8s linear infinite;margin-right:12px}"
        "@keyframes spin{to{transform:rotate(360deg)}}</style></head>"
        "<body><div class='s'></div><span>Signing you in…</span>"
        "<script>try{localStorage.setItem('df_token'," + payload + ");}catch(e){}"
        "location.replace('/ladder');</script></body></html>"
    )
    resp = HTMLResponse(content=html)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None), response: Response = None):
    """Current logged-in user (from the Bearer JWT), plus linked-profile display
    and any pending claim — the frontend uses these to decide whether to show
    the 'claim your profile' flow."""
    if response is not None:
        response.headers["Cache-Control"] = "no-store"
    u = dict(_current_user(authorization, required=True))
    with pg() as conn:
        cur = conn.cursor()
        if u.get("canonical_id"):
            cur.execute("SELECT display_name FROM players_canonical WHERE canonical_id=%s", (u["canonical_id"],))
            row = cur.fetchone()
            u["profile_display"] = row["display_name"] if row else None
        cur.execute("""SELECT canonical_id, status, created_at FROM user_claims
                       WHERE discord_id=%s AND status='pending' ORDER BY created_at DESC LIMIT 1""",
                    (u["discord_id"],))
        c = cur.fetchone()
        if c:
            cur.execute("SELECT display_name FROM players_canonical WHERE canonical_id=%s", (c["canonical_id"],))
            pr = cur.fetchone()
            u["pending_claim"] = {"canonical_id": c["canonical_id"],
                                  "display": pr["display_name"] if pr else c["canonical_id"]}
        # The user's ladder team (membership via linked canonical_id, or created
        # by them) — lets the topbar/board show "Team Settings" for captains.
        u["team"] = None
        try:
            import ladder as _ladder
            _ladder.ensure_schema(cur)
            params, where = [], []
            if u.get("canonical_id"):
                where.append("members @> %s::jsonb"); params.append(json.dumps([u["canonical_id"]]))
            where.append("created_by=%s"); params.append(u["discord_id"])
            cur.execute(f"""SELECT id, ladder_id, name, tag, status, rung
                            FROM ladder_teams
                            WHERE status IN ('pending','active') AND ({' OR '.join(where)})
                            ORDER BY (status='active') DESC, id LIMIT 1""", params)
            tm = cur.fetchone()
            if tm:
                u["team"] = dict(tm)
        except Exception:
            pass
    return u


@app.post("/api/auth/location")
def auth_set_location(authorization: str | None = Header(default=None),
                      state: str | None = Body(default=None, embed=True),
                      city: str | None = Body(default=None, embed=True),
                      country: str | None = Body(default=None, embed=True),
                      favorite_server: str | None = Body(default=None, embed=True),
                      timezone: str | None = Body(default=None, embed=True)):
    """Save the user's location/timezone (all optional). state = US state / CA
    province / 'INTL'; timezone = IANA name (overrides location-derived tz).
    region derived (NA for US/CA states, else null)."""
    import auth as A
    u = _current_user(authorization, required=True)
    st = (state or "").strip().upper() or None
    region = ("NA" if st != "INTL" else None) if st else None
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("""UPDATE users SET state=%s, city=%s, country=%s, favorite_server=%s,
                              region=%s, timezone=%s WHERE discord_id=%s""",
                    (st, (city or "").strip()[:60] or None,
                     (country or "").strip().upper()[:2] or None,
                     (favorite_server or "").strip()[:120] or None, region,
                     (timezone or "").strip()[:64] or None, u["discord_id"]))
        conn.commit()
    return {"state": st, "city": city, "country": country, "favorite_server": favorite_server,
            "region": region, "timezone": timezone}


_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _clean_availability(payload):
    """Validate/normalize an availability blob -> {"tz": str|None, "slots": {day:[hours]}}.
    Hours kept in 0..26 (26 = 2am next day). Empty days dropped. Returns None if
    nothing is set (so we can store SQL NULL)."""
    if not isinstance(payload, dict):
        return None
    tz = payload.get("tz")
    tz = (tz or "").strip()[:64] or None
    raw = payload.get("slots") or {}
    slots = {}
    if isinstance(raw, dict):
        for d in _DAY_KEYS:
            hrs = raw.get(d)
            if not isinstance(hrs, list):
                continue
            clean = sorted({int(h) for h in hrs if isinstance(h, (int, float)) and 0 <= int(h) <= 26})
            if clean:
                slots[d] = clean
    if not slots:
        return None
    return {"tz": tz, "slots": slots}


@app.post("/api/auth/availability")
def auth_set_availability(authorization: str | None = Header(default=None),
                          tz: str | None = Body(default=None, embed=True),
                          slots: dict | None = Body(default=None, embed=True)):
    """Save the current user's general weekly availability for the ladder
    scheduler. Stored in the player's own tz; days mon..sun, hours 0..26."""
    import auth as A
    u = _current_user(authorization, required=True)
    blob = _clean_availability({"tz": tz, "slots": slots})
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("UPDATE users SET availability=%s WHERE discord_id=%s",
                    (json.dumps(blob) if blob else None, u["discord_id"]))
        conn.commit()
    return {"availability": blob}


@app.get("/api/auth/claim/suggestions")
def auth_claim_suggestions(authorization: str | None = Header(default=None)):
    """Fuzzy-match the user's Discord name(s) against player nicks → candidate
    profiles to pick from (option C). Falls back to the Player Search box if none
    look right (option B)."""
    u = _current_user(authorization, required=True)
    names = [n for n in {u.get("global_name"), u.get("username")} if n]
    seen, out = set(), []
    with pg() as conn:
        cur = conn.cursor()
        for n in names:
            cur.execute("""
                SELECT pc.canonical_id, pc.display_name AS display,
                       (SELECT COUNT(*) FROM players p WHERE p.canonical_id = pc.canonical_id) AS matches
                FROM players_canonical pc
                WHERE LOWER(pc.display_name) LIKE %s
                ORDER BY matches DESC LIMIT 8
            """, (f"%{n.lower()}%",))
            for r in cur.fetchall():
                if r["canonical_id"] not in seen:
                    seen.add(r["canonical_id"])
                    out.append(r)
    return {"names_tried": names, "suggestions": out[:8]}


@app.post("/api/auth/claim")
def auth_claim(authorization: str | None = Header(default=None),
               canonical_id: str = Body(..., embed=True)):
    """User picks their profile → linked IMMEDIATELY (no approval gate) so they
    can register a team in the same session. Marked verified=false for an admin's
    later background check. Records the pick in user_claims (status='self') for
    the audit trail."""
    import auth as A
    u = _current_user(authorization, required=True)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("SELECT 1 FROM players_canonical WHERE canonical_id=%s", (canonical_id,))
        if not cur.fetchone():
            raise HTTPException(404, "no such player")
        cur.execute("UPDATE users SET canonical_id=%s, verified=FALSE WHERE discord_id=%s",
                    (canonical_id, u["discord_id"]))
        cur.execute("DELETE FROM user_claims WHERE discord_id=%s AND status IN ('pending','self')",
                    (u["discord_id"],))
        cur.execute("""INSERT INTO user_claims (discord_id, canonical_id, status, resolved_at, resolved_by)
                       VALUES (%s,%s,'self', now(), 'self') RETURNING id""",
                    (u["discord_id"], canonical_id))
        cid = cur.fetchone()["id"]
        cur.execute("SELECT display_name FROM players_canonical WHERE canonical_id=%s", (canonical_id,))
        pr = cur.fetchone()
        conn.commit()
    try:
        import notify
        notify.ladder_signup(pr["display_name"] if pr and pr["display_name"] else canonical_id)
    except Exception:
        pass
    return {"claim_id": cid, "canonical_id": canonical_id, "status": "linked", "verified": False}


@app.get("/api/admin/claims")
def admin_claims(authorization: str | None = Header(default=None),
                 status: str = Query("pending")):
    """List account→profile claims for admin review (admin token)."""
    import auth as A
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("""
            SELECT c.id, c.discord_id, c.canonical_id, c.status, c.created_at,
                   u.username, u.global_name, u.avatar,
                   pc.display_name AS profile_display,
                   (SELECT COUNT(*) FROM players p WHERE p.canonical_id = c.canonical_id) AS profile_matches
            FROM user_claims c
            JOIN users u ON u.discord_id = c.discord_id
            LEFT JOIN players_canonical pc ON pc.canonical_id = c.canonical_id
            WHERE c.status = %s
            ORDER BY c.created_at DESC
        """, (status,))
        return {"claims": [dict(r, created_at=r["created_at"].isoformat() if r["created_at"] else None)
                           for r in cur.fetchall()]}


@app.post("/api/admin/claims/{claim_id}/resolve")
def admin_resolve_claim(claim_id: int, authorization: str | None = Header(default=None),
                        approve: bool = Body(..., embed=True)):
    """Approve (link the Discord account to the player) or reject a claim."""
    import auth as A
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("SELECT * FROM user_claims WHERE id=%s", (claim_id,))
        c = cur.fetchone()
        if not c:
            raise HTTPException(404, "claim not found")
        if c["status"] != "pending":
            raise HTTPException(409, "claim already resolved")
        new_status = "approved" if approve else "rejected"
        if approve:
            cur.execute("UPDATE users SET canonical_id=%s WHERE discord_id=%s",
                        (c["canonical_id"], c["discord_id"]))
        cur.execute("""UPDATE user_claims SET status=%s, resolved_at=now(), resolved_by='token'
                       WHERE id=%s""", (new_status, claim_id))
        conn.commit()
    return {"claim_id": claim_id, "status": new_status,
            "linked": c["canonical_id"] if approve else None}


@app.get("/api/health")
def health():
    with pg() as conn:
        v = conn.cursor()
        v.execute("SELECT count(*) AS n FROM matches")
        matches = v.fetchone()["n"]
    return {"ok": True, "matches": matches, "now": datetime.now(timezone.utc).isoformat()}


@app.get("/api/debug/ingest")
def debug_ingest(response: Response):
    """Read-only ingest health: is the sync pulling matches, and is canonicalize
    linking them? Disambiguates 'stuck profiles' (ingestion vs canonicalization).
    Aggregate counts only — safe to expose."""
    response.headers["Cache-Control"] = "no-store"
    # match_date is stored as ISO-8601 TEXT, so compare lexically against a string
    # cutoff (works for same-format ISO timestamps; avoids a text→ts cast that
    # would blow up on any odd row).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT max(match_date) AS max_date, count(*) AS total FROM matches")
        a = cur.fetchone()
        cur.execute("SELECT count(*) AS n FROM matches WHERE match_date > %s", (cutoff,))
        recent = cur.fetchone()["n"]
        cur.execute("""SELECT count(*) AS n FROM players p JOIN matches m ON m.match_id=p.match_id
                       WHERE p.canonical_id IS NULL AND m.match_date > %s""", (cutoff,))
        recent_unassigned = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM players WHERE canonical_id IS NULL")
        unassigned = cur.fetchone()["n"]
    return {
        "max_match_date": a["max_date"],
        "total_matches": a["total"],
        "matches_last_4d": recent,                 # >0 → ingestion is working
        "recent_player_rows_unassigned": recent_unassigned,  # >0 → canonicalize is behind
        "total_player_rows_unassigned": unassigned,
        "now": datetime.now(timezone.utc).isoformat(),
    }


# ── Support tickets ──────────────────────────────────────────────────────────
def _ensure_support_schema(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
        id           BIGSERIAL PRIMARY KEY,
        title        TEXT NOT NULL,
        area         TEXT,
        description  TEXT NOT NULL,
        email        TEXT,
        discord_id   TEXT,
        username     TEXT,
        canonical_id TEXT,
        page_url     TEXT,
        status       TEXT NOT NULL DEFAULT 'open',   -- open | in_progress | resolved
        resolution   TEXT,
        created_at   TIMESTAMPTZ DEFAULT now(),
        resolved_at  TIMESTAMPTZ
    )""")
    # Two-tier resolution: plain-English summary (shown to user + emailed) and a
    # detailed technical writeup (admin only). Plus email-delivery tracking.
    cur.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS resolution_summary TEXT")
    cur.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS resolution_detail TEXT")
    cur.execute("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS email_status TEXT")  # null|pending|sent|failed
    # Optional screenshots attached to a ticket (client-side resized to ≤2000px).
    cur.execute("""CREATE TABLE IF NOT EXISTS support_attachments (
        id          BIGSERIAL PRIMARY KEY,
        ticket_id   BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
        data        BYTEA NOT NULL,
        mime        TEXT,
        created_at  TIMESTAMPTZ DEFAULT now()
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_support_att_ticket ON support_attachments(ticket_id)")


def _parse_image_data_uri(s: str, cap: int = 2_600_000):
    """Decode a 'data:image/...;base64,...' string to (bytes, mime), size-capped.
    Returns (None, None) for empty. Raises 400/413 on bad input."""
    if not s:
        return None, None
    if not s.startswith("data:") or "," not in s:
        raise HTTPException(400, "image must be a data URI")
    head, b64 = s.split(",", 1)
    mime = head[5:].split(";")[0] or "image/png"
    if mime not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        raise HTTPException(400, "image must be PNG/JPEG/WebP/GIF")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "invalid image encoding")
    if len(raw) > cap:
        raise HTTPException(413, "image too large — resize first")
    return raw, mime


def _send_resolution_email(to: str, num: int, summary: str) -> str:
    """Email the user their plain-English resolution. Uses Resend if configured
    (RESEND_API_KEY + EMAIL_FROM). Returns 'sent' | 'pending' (no provider) |
    'failed'. Never raises."""
    if not to:
        return None
    key = os.environ.get("RESEND_API_KEY")
    sender = os.environ.get("EMAIL_FROM")
    if not key or not sender:
        return "pending"   # provider not configured yet — queued for later
    body = (f"Hi,\n\nYour DeepFrag support ticket #{num} has been resolved.\n\n"
            f"{summary}\n\nThanks for the report — it helped.\n\n— DeepFrag")
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps({"from": sender, "to": [to],
                             "subject": f"Your DeepFrag ticket #{num} is resolved", "text": body}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return "sent" if 200 <= r.status < 300 else "failed"
    except Exception:
        return "failed"


@app.post("/api/support/ticket")
def support_create(authorization: str | None = Header(default=None),
                   title: str = Body(..., embed=True),
                   area: str | None = Body(default=None, embed=True),
                   description: str = Body(..., embed=True),
                   email: str | None = Body(default=None, embed=True),
                   page_url: str | None = Body(default=None, embed=True),
                   images: list | None = Body(default=None, embed=True)):
    """Submit a support ticket. No sign-in required; if signed in, the user's
    Discord/profile is attached. Optional `images` = up to 3 data-URI screenshots
    (resized client-side). Returns the sequential ticket number."""
    if not title.strip() or not description.strip():
        raise HTTPException(400, "title and description are required")
    u = _current_user(authorization, required=False)  # optional
    shots = [s for s in (images or []) if s][:3]      # cap at 3
    with pg() as conn:
        cur = conn.cursor()
        _ensure_support_schema(cur)
        cur.execute("""INSERT INTO support_tickets
                       (title, area, description, email, discord_id, username, canonical_id, page_url)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (title.strip()[:200], (area or "").strip()[:60] or None, description.strip()[:5000],
                     (email or "").strip()[:120] or None,
                     u.get("discord_id") if u else None,
                     (u.get("global_name") or u.get("username")) if u else None,
                     u.get("canonical_id") if u else None,
                     (page_url or "").strip()[:300] or None))
        num = cur.fetchone()["id"]
        for s in shots:
            raw, mime = _parse_image_data_uri(s)
            if raw:
                cur.execute("INSERT INTO support_attachments (ticket_id, data, mime) VALUES (%s,%s,%s)",
                            (num, psycopg2.Binary(raw), mime))
        conn.commit()
    try:
        import notify
        who = (u.get("global_name") or u.get("username")) if u else (email or "anonymous")
        notify.support_ticket(num, area, title.strip(), who)
    except Exception:
        pass
    return {"ticket": num, "status": "open"}


def _attach_map(cur, ticket_ids):
    """{ticket_id: [attachment_id, ...]} for the given tickets (ordered)."""
    out = {}
    if not ticket_ids:
        return out
    cur.execute("""SELECT id, ticket_id FROM support_attachments
                   WHERE ticket_id = ANY(%s) ORDER BY id""", (list(ticket_ids),))
    for r in cur.fetchall():
        out.setdefault(r["ticket_id"], []).append(r["id"])
    return out


@app.get("/api/admin/support/attachment/{att_id}")
def support_attachment(att_id: int, authorization: str | None = Header(default=None)):
    """Serve a ticket screenshot. Visible to god admins (SYNC_SECRET) and ladder
    admins (is_admin) — same gate as the read-only ladder support view."""
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ensure_support_schema(cur)
        cur.execute("SELECT data, mime FROM support_attachments WHERE id=%s", (att_id,))
        row = cur.fetchone()
    if not row or not row["data"]:
        raise HTTPException(404, "not found")
    return Response(content=bytes(row["data"]), media_type=row["mime"] or "image/png",
                    headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/admin/support/tickets")
def admin_support_list(authorization: str | None = Header(default=None),
                       status: str = Query("all")):
    """All support tickets (admin)."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ensure_support_schema(cur)
        if status and status != "all":
            cur.execute("SELECT * FROM support_tickets WHERE status=%s ORDER BY created_at DESC", (status,))
        else:
            cur.execute("SELECT * FROM support_tickets ORDER BY (status='resolved'), created_at DESC")
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            for k in ("created_at", "resolved_at"):
                if d.get(k) and hasattr(d[k], "isoformat"):
                    d[k] = d[k].isoformat()
            rows.append(d)
        att = _attach_map(cur, [r["id"] for r in rows])
        for d in rows:
            d["attachments"] = att.get(d["id"], [])
    return {"tickets": rows}


@app.get("/api/admin/ladder/support")
def ladder_admin_support(authorization: str | None = Header(default=None)):
    """Ladder-area support tickets, read-only, for ladder admins (Nin/Bance/Cronus)
    to monitor. They can't resolve here — that's the god panel — but they get the
    history."""
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ensure_support_schema(cur)
        cur.execute("""SELECT id, title, area, description, username, email, status,
                              resolution_summary, created_at, resolved_at
                       FROM support_tickets WHERE area ILIKE '%ladder%'
                       ORDER BY (status='resolved'), created_at DESC""")
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            for k in ("created_at", "resolved_at"):
                if d.get(k) and hasattr(d[k], "isoformat"):
                    d[k] = d[k].isoformat()
            rows.append(d)
        att = _attach_map(cur, [r["id"] for r in rows])
        for d in rows:
            d["attachments"] = att.get(d["id"], [])
    return {"tickets": rows}


@app.post("/api/admin/support/tickets/{ticket_id}/status")
def admin_support_status(ticket_id: int, authorization: str | None = Header(default=None),
                         status: str = Body(..., embed=True),
                         resolution_summary: str | None = Body(default=None, embed=True),
                         resolution_detail: str | None = Body(default=None, embed=True)):
    """Update a ticket (admin). On 'resolved', store the plain-English summary
    (user-facing/email) + the detailed technical writeup (admin), and — if the
    reporter left an email — send/queue the summary to them."""
    _check_admin_auth(authorization)
    if status not in ("open", "in_progress", "resolved"):
        raise HTTPException(400, "bad status")
    with pg() as conn:
        cur = conn.cursor()
        _ensure_support_schema(cur)
        cur.execute("""UPDATE support_tickets
                       SET status=%s,
                           resolution_summary=COALESCE(%s, resolution_summary),
                           resolution_detail=COALESCE(%s, resolution_detail),
                           resolved_at = CASE WHEN %s='resolved' THEN now() ELSE resolved_at END
                       WHERE id=%s RETURNING id, status, email, resolution_summary""",
                    (status, resolution_summary, resolution_detail, status, ticket_id))
        row = cur.fetchone()
        if not row:
            conn.commit()
            raise HTTPException(404, "ticket not found")
        email_status = None
        if status == "resolved" and row["email"] and row["resolution_summary"]:
            email_status = _send_resolution_email(row["email"], row["id"], row["resolution_summary"])
            cur.execute("UPDATE support_tickets SET email_status=%s WHERE id=%s", (email_status, ticket_id))
        conn.commit()
    return {"id": row["id"], "status": row["status"], "email_status": email_status}


# ── Ladder cron tick: reminders + forfeit clock ──────────────────────────────
def _ladder_tick(cur):
    """Fire upcoming-match reminders (24h out, starting soon) and flag overdue
    challenges. Idempotent via per-challenge fired-once flags. Returns counts."""
    import ladder as _ladder
    import notify
    _ladder.ensure_schema(cur)
    now = datetime.now(timezone.utc)
    counts = {"reminded_1h": 0, "reminded_10m": 0, "overdue": 0, "bo3_normalized": 0}

    # Self-heal: enforce Bo3-only. A match's maps = the DECISIVE set up to the
    # clinching 2nd win; games after that are "for fun" and don't count. Trim
    # them, recompute score/winner/hub_game_ids, and set played_at to the last
    # DECISIVE game's end (drives the loss cooldown). Idempotent.
    cur.execute("SELECT id, maps, team_a_id, team_b_id, score_a, score_b, winner_id, hub_game_ids FROM ladder_matches")
    for r in cur.fetchall():
        maps = list(r["maps"] or [])
        if not maps:
            continue
        aw = bw = 0
        cut = len(maps)
        for i, mp in enumerate(maps):
            a, b = mp.get("a_frags"), mp.get("b_frags")
            if a is None or b is None:
                continue
            if a > b:
                aw += 1
            elif b > a:
                bw += 1
            if aw == 2 or bw == 2:
                cut = i + 1
                break
        decisive = maps[:cut]
        na = sum(1 for mp in decisive if (mp.get("a_frags") or 0) > (mp.get("b_frags") or 0))
        nb = sum(1 for mp in decisive if (mp.get("b_frags") or 0) > (mp.get("a_frags") or 0))
        winner = r["team_a_id"] if na > nb else r["team_b_id"] if nb > na else r["winner_id"]
        hub_ids = [mp.get("hub_game_id") for mp in decisive if mp.get("hub_game_id")]
        pa = None
        if hub_ids:
            cur.execute("SELECT max(match_date) AS m FROM matches WHERE hub_game_id = ANY(%s)",
                        ([int(x) for x in hub_ids],))
            mm = cur.fetchone()
            pa = mm["m"] if mm and mm["m"] else None
        # Only write if something actually changed (trim or score or played_at).
        cur.execute("""UPDATE ladder_matches
                       SET maps=%s, score_a=%s, score_b=%s, winner_id=%s, hub_game_ids=%s,
                           played_at=COALESCE(%s::timestamptz, played_at)
                       WHERE id=%s AND (
                         jsonb_array_length(maps) <> %s OR score_a IS DISTINCT FROM %s
                         OR score_b IS DISTINCT FROM %s
                         OR (%s::timestamptz IS NOT NULL AND played_at IS DISTINCT FROM %s::timestamptz))""",
                    (json.dumps(decisive), na, nb, winner, json.dumps(hub_ids), pa,
                     r["id"], len(decisive), na, nb, pa, pa))
        counts["bo3_normalized"] += cur.rowcount

    # Scheduled matches → reminders. Two tiers: ~1 hour out and ~10 minutes out.
    # Windows are sized so the */5 cron always lands at least one tick inside them
    # before kickoff; per-challenge fired-once flags prevent repeats.
    cur.execute("""SELECT c.id, c.challenger_id, c.challenged_id, c.agreed_at, c.server,
                          c.reminded_soon, c.reminded_10m, ca.name AS a, cd.name AS b
                   FROM ladder_challenges c
                   JOIN ladder_teams ca ON ca.id=c.challenger_id
                   JOIN ladder_teams cd ON cd.id=c.challenged_id
                   WHERE c.status='scheduled' AND c.agreed_at IS NOT NULL
                     AND c.agreed_at > now() - interval '1 hour'""")
    for r in cur.fetchall():
        d = r["agreed_at"] - now
        if not r["reminded_soon"] and timedelta(minutes=12) < d <= timedelta(minutes=70):
            notify.match_reminder(r["a"], r["b"], r["agreed_at"].isoformat(), r["server"], kind="1h",
                                  mention=_mentions(cur, r["challenger_id"], r["challenged_id"]))
            cur.execute("UPDATE ladder_challenges SET reminded_soon=TRUE WHERE id=%s", (r["id"],))
            counts["reminded_1h"] += 1
        if not r["reminded_10m"] and timedelta(0) < d <= timedelta(minutes=12):
            notify.match_reminder(r["a"], r["b"], r["agreed_at"].isoformat(), r["server"], kind="10m",
                                  mention=_mentions(cur, r["challenger_id"], r["challenged_id"]))
            cur.execute("UPDATE ladder_challenges SET reminded_10m=TRUE WHERE id=%s", (r["id"],))
            counts["reminded_10m"] += 1

    # Open challenges past their play-by deadline → flag once for admins.
    cur.execute("""SELECT c.id, c.challenger_id, c.challenged_id, c.deadline, ca.name AS a, cd.name AS b
                   FROM ladder_challenges c
                   JOIN ladder_teams ca ON ca.id=c.challenger_id
                   JOIN ladder_teams cd ON cd.id=c.challenged_id
                   WHERE c.status='open' AND c.deadline < now() AND NOT c.overdue_flagged""")
    for r in cur.fetchall():
        notify.challenge_overdue(r["a"], r["b"], r["deadline"].isoformat() if r["deadline"] else None,
                                 mention=_mentions(cur, r["challenger_id"], r["challenged_id"]))
        cur.execute("UPDATE ladder_challenges SET overdue_flagged=TRUE WHERE id=%s", (r["id"],))
        counts["overdue"] += 1
    return counts


@app.post("/api/cron/ladder-tick")
def cron_ladder_tick(authorization: str | None = Header(default=None)):
    """Cloud Scheduler hits this (every ~30 min). Auth: SYNC_SECRET or CRON_SECRET."""
    expected = {os.environ.get("SYNC_SECRET"), os.environ.get("CRON_SECRET")} - {None, ""}
    if not expected or (authorization or "").removeprefix("Bearer ") not in expected:
        raise HTTPException(401, "bad cron token")
    with pg() as conn:
        cur = conn.cursor()
        counts = _ladder_tick(cur)
        conn.commit()
    return {"ok": True, **counts}


def _evaluate_freshness(conn):
    """Data-freshness watchdog core: flag stale ingestion / behind canonicalize,
    alert to Discord (throttled 3h via monitor_state). Returns a verdict dict.
    Called by the cron endpoint AND at the end of every 2h sync."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=4)).isoformat()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS monitor_state (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("SELECT max(match_date) AS m FROM matches")
    maxd = cur.fetchone()["m"]
    cur.execute("""SELECT count(*) AS n FROM players p JOIN matches m ON m.match_id=p.match_id
                   WHERE p.canonical_id IS NULL AND m.match_date > %s""", (cutoff,))
    unassigned = cur.fetchone()["n"]
    stale_hours = None
    if maxd:
        try:
            dt = datetime.fromisoformat(str(maxd).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            stale_hours = round((now - dt).total_seconds() / 3600, 1)
        except Exception:
            pass
    problems = []
    if stale_hours is None or stale_hours > 4:
        problems.append(f"newest match is {stale_hours if stale_hours is not None else '?'}h old — ingestion may be stalled")
    if unassigned > 200:
        problems.append(f"{unassigned} recent player rows have no profile link — canonicalize may be stalled")
    alerted = False
    if problems:  # throttle: alert at most once every 3h while unhealthy
        cur.execute("SELECT value FROM monitor_state WHERE key='last_health_alert'")
        row = cur.fetchone()
        last = None
        if row and row["value"]:
            try:
                last = datetime.fromisoformat(row["value"])
            except Exception:
                pass
        if last is None or (now - last).total_seconds() > 3 * 3600:
            try:
                import notify
                if notify.data_health_alert(problems, maxd):
                    alerted = True
                    cur.execute("""INSERT INTO monitor_state (key, value) VALUES ('last_health_alert', %s)
                                   ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""", (now.isoformat(),))
            except Exception:
                pass
    conn.commit()
    return {"healthy": not problems, "stale_hours": stale_hours,
            "recent_unassigned": unassigned, "problems": problems, "alerted": alerted}


@app.post("/api/cron/freshness-check")
def cron_freshness_check(authorization: str | None = Header(default=None)):
    """Data-freshness watchdog — the alarm the 2026-06 silent stall lacked.
    Auth: SYNC_SECRET or CRON_SECRET. (Also runs automatically after each 2h sync.)"""
    expected = {os.environ.get("SYNC_SECRET"), os.environ.get("CRON_SECRET")} - {None, ""}
    if not expected or (authorization or "").removeprefix("Bearer ") not in expected:
        raise HTTPException(401, "bad cron token")
    with pg() as conn:
        return _evaluate_freshness(conn)


# ── Rankings ───────────────────────────────────────────────────────────────────

@app.get("/api/rankings")
def rankings(
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    min_matches: int = Query(10, ge=1, le=10_000),
    active: bool = Query(False, description="Only show players with a match in the last 90d"),
    region: str = Query("", description="EU/NA/SA/OC/AS/AF or empty for global"),
    limit: int = Query(500, ge=1, le=2000),
):
    # Hard floor: never show players with <5 rated matches regardless of the
    # client filter — 5 is the minimum to establish even a provisional rating.
    min_matches = max(min_matches, 5)
    # Rankings data only changes after rate.py runs (≈ daily). Cache aggressively at
    # the CDN — first request hits Cloud Run + Cloud SQL, subsequent ones served
    # from Cloudflare's edge in <50ms. stale-while-revalidate keeps it instant
    # while a background refresh fetches the new data.
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=86400"
    now = datetime.now(timezone.utc)
    recent_cutoff = (now - timedelta(days=90)).isoformat()

    with pg() as conn:
        cur = conn.cursor()
        # Pre-aggregate last_match + recent_matches ONCE for the whole mode,
        # then LEFT JOIN to ratings. The old correlated-subquery shape ran
        # 2× per row (~1900 sub-queries for 942 players) and took ~4s on Cloud
        # SQL micro; this CTE version is ~150ms.
        cur.execute("""
            WITH last_match_by_cid AS (
                SELECT p.canonical_id, MAX(m.match_date) AS last_match
                FROM players p JOIN matches m ON m.match_id = p.match_id
                WHERE m.match_mode = %(mode)s AND p.canonical_id IS NOT NULL
                GROUP BY p.canonical_id
            ),
            recent_by_cid AS (
                SELECT p.canonical_id, COUNT(*) AS recent_matches
                FROM players p JOIN matches m ON m.match_id = p.match_id
                WHERE m.match_mode = %(mode)s
                  AND m.match_date >= %(recent)s
                  AND p.canonical_id IS NOT NULL
                GROUP BY p.canonical_id
            )
            -- avg_ddr / avg_frag_diff are precomputed on the ratings row by
            -- rate.py — no per-request aggregation needed. Was a 3s CTE before.
            SELECT r.canonical_id,
                   COALESCE(pc.display_name, r.canonical_id) AS display,
                   pc.region, pc.region_confidence,
                   r.mu, r.sigma, r.conservative,
                   COALESCE(r.unique_opponents, 0) AS unique_opponents,
                   r.matches_rated, r.wins, r.losses, r.draws,
                   lm.last_match,
                   COALESCE(re.recent_matches, 0) AS recent_matches,
                   r.avg_ddr, r.avg_frag_diff
            FROM ratings r
            LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
            LEFT JOIN last_match_by_cid lm ON lm.canonical_id = r.canonical_id
            LEFT JOIN recent_by_cid re ON re.canonical_id = r.canonical_id
            WHERE r.mode = %(mode)s AND r.map = '' AND r.matches_rated >= %(min)s
              AND NOT COALESCE(pc.hidden, FALSE)
        """, {"mode": mode, "min": min_matches, "recent": recent_cutoff})
        rows = cur.fetchall()
        cutoffs = _get_tier_cutoffs(cur, mode)

    out = []
    for r in rows:
        recent = r["recent_matches"] or 0
        if active and recent == 0:
            continue
        if region and (r["region"] or "") != region:
            continue
        sigma_eff = effective_sigma(r["sigma"], r["last_match"], now, r["unique_opponents"])
        conservative_eff = r["mu"] - 3 * sigma_eff
        out.append({
            "canonical_id": r["canonical_id"],
            "display": r["display"],
            "region": r["region"],
            "region_confidence": r["region_confidence"],
            "mu": round(r["mu"], 1),
            "sigma": round(r["sigma"], 1),
            "sigma_effective": round(sigma_eff, 1),
            "conservative": round(conservative_eff, 1),
            "conservative_raw": round(r["conservative"], 1),
            "matches": r["matches_rated"],
            "unique_opponents": r["unique_opponents"],
            "provisional": r["unique_opponents"] < DIVERSITY_THRESHOLD_OVERALL,
            "wins": r["wins"],
            "losses": r["losses"],
            "draws": r["draws"],
            "win_rate": round(r["wins"] / r["matches_rated"], 3) if r["matches_rated"] else None,
            "last_match": r["last_match"],
            "recent_matches_90d": recent,
            "active_90d": recent > 0,
            "avg_ddr": round(r["avg_ddr"], 2) if r["avg_ddr"] is not None else None,
            "avg_frag_diff": round(r["avg_frag_diff"], 1) if r["avg_frag_diff"] is not None else None,
            "tier": tier_for(conservative_eff, cutoffs),
        })

    out.sort(key=lambda x: -x["conservative"])
    for i, p in enumerate(out[:limit]):
        p["rank"] = i + 1
    return {"mode": mode, "count": len(out), "players": out[:limit]}


# ── Player profile (lightweight version — only the fields the UI actually shows on first load) ─

# NOTE: /api/players/map MUST be registered before /api/players/{canonical_id}
# or FastAPI captures 'map' as a canonical_id and the map 404s.
@app.get("/api/players/map")
def players_map(response: Response):
    """All players with geo data, for the player map. Precise lat/lon where
    known (from the config sheet) plus nationality for country-level placement.
    Public, cacheable."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT pc.canonical_id, pc.nick, pc.nationality, pc.lat, pc.lon,
                   COALESCE(can.display_name, pc.nick) AS display
            FROM player_configs pc
            LEFT JOIN players_canonical can ON can.canonical_id = pc.canonical_id
            WHERE pc.nationality IS NOT NULL OR pc.lat IS NOT NULL
            ORDER BY pc.nick
        """)
        return {"players": cur.fetchall()}


@app.get("/api/players/{canonical_id}")
def player_profile(canonical_id: str):
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT canonical_id, display_name, login, created_at, updated_at,
                   region, region_confidence, region_distribution
            FROM players_canonical WHERE canonical_id = %s
        """, (canonical_id,))
        canon = cur.fetchone()
        if not canon:
            raise HTTPException(404, "player not found")

        # Career: lifetime totals across all matches the player appears in.
        cur.execute("""
            SELECT COUNT(DISTINCT m.match_id) AS matches,
                   MIN(m.match_date) AS first_match,
                   MAX(m.match_date) AS last_match
            FROM players p JOIN matches m ON m.match_id = p.match_id
            WHERE p.canonical_id = %s
        """, (canonical_id,))
        career = cur.fetchone() or {}

        # Per-mode ratings (overall + tier).
        cur.execute("""
            SELECT mode, mu, sigma, conservative, matches_rated, wins, losses, draws,
                   updated_at
            FROM ratings WHERE canonical_id = %s AND map = ''
        """, (canonical_id,))
        ratings = {"1on1": None, "2on2": None, "4on4": None}
        mode_rows = cur.fetchall()
        # Compute cutoffs lazily — one trip per mode the player is rated in.
        cutoffs_by_mode = {r["mode"]: _get_tier_cutoffs(cur, r["mode"]) for r in mode_rows}
        for r in mode_rows:
            ratings[r["mode"]] = {
                "mu": round(r["mu"], 1),
                "sigma": round(r["sigma"], 1),
                "conservative": round(r["conservative"], 1),
                "matches": r["matches_rated"],
                "wins": r["wins"],
                "losses": r["losses"],
                "draws": r["draws"],
                "tier": tier_for(r["conservative"], cutoffs_by_mode.get(r["mode"])),
                "updated_at": r["updated_at"],
            }

    return {
        "canonical_id": canon["canonical_id"],
        "display": canon["display_name"],
        "login": canon["login"],
        "career": dict(career),
        "ratings": ratings,
    }


# ── Stats leaderboards (mechanical-skill: accuracy, damage, items, etc.) ──────

def _stats_window_since(window: str) -> str:
    """ISO cutoff for a stats time window, or '' for all-time."""
    days = {"30d": 30, "90d": 90, "6mo": 182, "1yr": 365}.get(window)
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days else ""


@app.get("/api/stats/leaderboards")
def stats_leaderboards(
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    map: str = Query("all", description="Map name or 'all'"),
    region: str = Query("all", description="EU/NA/SA/OC/AS/AF or 'all'"),
    min_matches: int = Query(25, ge=5, le=10_000),
    window: str = Query("all", description="30d/90d/6mo/1yr/all"),
    top: int = Query(10, ge=1, le=100),
):
    """Aggregate per-player stats once, slice into one top-N leaderboard per
    stat. 1on1 only for now — 2on2/4on4 wait on team rating methodology."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    if mode != "1on1":
        return {"mode": mode, "leaderboards": {}, "note": "Only 1on1 leaderboards are available right now."}

    sql, params = stats_pg.stats_query(mode=mode, map_name=map, region=region,
                                       min_matches=min_matches, since=_stats_window_since(window))
    with pg() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

    return {
        "mode": mode,
        "map": map,
        "region": region,
        "min_matches": min_matches,
        "player_count": len(rows),
        "leaderboards": stats_pg.build_leaderboards(rows, top_n=top),
    }


@app.get("/api/stats/table")
def stats_table(
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    map: str = Query("all"),
    region: str = Query("all"),
    min_matches: int = Query(100, ge=5, le=10_000),
    window: str = Query("all", description="30d/90d/6mo/1yr/all"),
):
    """Every qualifying player with ALL stat columns — powers the sortable,
    paginated full-table view on /stats. 1on1 only for now."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    if mode != "1on1":
        return {"mode": mode, "columns": [], "players": [], "note": "Only 1on1 stats are available right now."}
    sql, params = stats_pg.stats_query(mode=mode, map_name=map, region=region,
                                       min_matches=min_matches, since=_stats_window_since(window))
    with pg() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return {"mode": mode, "columns": stats_pg.table_columns(), "players": stats_pg.build_table(rows)}


@app.get("/api/stats/maps")
def stats_maps(mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"), min_games: int = Query(20, ge=1)):
    """List maps with enough activity to leaderboard against. Populates the map dropdown."""
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT match_map AS map, COUNT(*) AS games
            FROM matches WHERE match_mode = %s AND match_map IS NOT NULL
            GROUP BY match_map HAVING COUNT(*) >= %s
            ORDER BY games DESC
        """, (mode, min_games))
        return {"mode": mode, "maps": [dict(r) for r in cur.fetchall()]}


# ── Servers list + per-server detail ──────────────────────────────────────────

@app.get("/api/servers")
def servers_list(response: Response, region: str = Query("", description="EU/NA/SA/OC/AS/AF or empty for all"),
                 active: bool = Query(True, description="Only servers seen live or active in last 90d"),
                 limit: int = Query(500, ge=1, le=2000)):
    """List every server with summary stats. Aggregates by HOST (port-stripped)
    so 'ny.quake.world:28501', ':28502', ':28503' show as one row, not three.
    Default: active=true filters to servers currently live in hub OR with a
    match in the last 90 days."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    where_clauses, params = [], []
    if region:
        where_clauses.append("host_root_geo.region = %s")
        params.append(region)
    if active:
        where_clauses.append("(host_root_geo.is_live OR agg.last_match::timestamptz >= NOW() - INTERVAL '90 days')")
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    with pg() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            WITH host_root_geo AS (
                -- Prefer LIVE rows (from hub) over historical DNS-only ones, then
                -- pick one row per host_root. Carries is_live so the API can filter.
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root,
                       country, region, city, lat, lon, is_live
                FROM servers
                ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST, country NULLS LAST
            ),
            match_agg AS (
                -- Count matches WITHOUT joining players (otherwise SUM gets multiplied by player count).
                SELECT split_part(server_hostname, ':', 1) AS host_root,
                       COUNT(*) AS games,
                       MAX(match_date) AS last_match,
                       MIN(match_date) AS first_match,
                       SUM(CASE WHEN match_mode='1on1' THEN 1 ELSE 0 END) AS g_1on1,
                       SUM(CASE WHEN match_mode='2on2' THEN 1 ELSE 0 END) AS g_2on2,
                       SUM(CASE WHEN match_mode='4on4' THEN 1 ELSE 0 END) AS g_4on4,
                       COUNT(DISTINCT server_hostname) AS port_count,
                       string_agg(DISTINCT server_hostname, ', ' ORDER BY server_hostname) AS ports
                FROM matches WHERE server_hostname IS NOT NULL
                GROUP BY split_part(server_hostname, ':', 1)
            ),
            player_agg AS (
                -- Separate join for unique-player count, so it doesn't multiply rows above.
                SELECT split_part(m.server_hostname, ':', 1) AS host_root,
                       COUNT(DISTINCT p.canonical_id) AS players
                FROM matches m JOIN players p ON p.match_id = m.match_id
                WHERE m.server_hostname IS NOT NULL AND p.canonical_id IS NOT NULL
                GROUP BY split_part(m.server_hostname, ':', 1)
            ),
            agg AS (
                SELECT m.host_root, m.games, m.last_match, m.first_match,
                       COALESCE(pl.players, 0) AS players,
                       m.g_1on1, m.g_2on2, m.g_4on4, m.port_count, m.ports
                FROM match_agg m LEFT JOIN player_agg pl ON pl.host_root = m.host_root
            )
            SELECT agg.host_root AS hostname,
                   host_root_geo.country, host_root_geo.region, host_root_geo.city,
                   host_root_geo.lat, host_root_geo.lon,
                   COALESCE(host_root_geo.is_live, FALSE) AS is_live,
                   agg.games, agg.last_match, agg.first_match, agg.players,
                   agg.g_1on1, agg.g_2on2, agg.g_4on4, agg.port_count, agg.ports
            FROM agg
            LEFT JOIN host_root_geo ON host_root_geo.host_root = agg.host_root
            {where}
            ORDER BY agg.games DESC
            LIMIT {limit}
        """, params)
        return {"count": cur.rowcount, "servers": [dict(r) for r in cur.fetchall()]}


@app.get("/api/servers/{host_root:path}/detail")
def server_detail(response: Response, host_root: str):
    """Per-server deep-dive: stats + activity heatmap + top players by matches + by rating.
    host_root is the hostname WITHOUT port (we aggregate across all ports)."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()

        # Pick any server row for this host_root for metadata (they all share country/region)
        cur.execute("""
            SELECT * FROM servers
            WHERE split_part(hostname, ':', 1) = %s AND country IS NOT NULL
            LIMIT 1
        """, (host_root,))
        meta = cur.fetchone()
        if not meta:
            # Fall back to any row even without geo
            cur.execute("SELECT * FROM servers WHERE split_part(hostname, ':', 1) = %s LIMIT 1", (host_root,))
            meta = cur.fetchone()
            if not meta:
                raise HTTPException(404, "server not found")

        # Aggregate stats across all ports + average-games-per-week for 3mo / 12mo windows
        cur.execute("""
            WITH base AS (
                SELECT m.match_id, m.match_date, m.match_mode, p.canonical_id, p.player_ping,
                       m.server_hostname
                FROM matches m
                LEFT JOIN players p ON p.match_id = m.match_id AND p.canonical_id IS NOT NULL
                WHERE split_part(m.server_hostname, ':', 1) = %s
            )
            SELECT COUNT(DISTINCT match_id) AS games,
                   COUNT(DISTINCT canonical_id) AS players,
                   MIN(match_date) AS first_match,
                   MAX(match_date) AS last_match,
                   COUNT(DISTINCT CASE WHEN match_mode='1on1' THEN match_id END) AS g_1on1,
                   COUNT(DISTINCT CASE WHEN match_mode='2on2' THEN match_id END) AS g_2on2,
                   COUNT(DISTINCT CASE WHEN match_mode='4on4' THEN match_id END) AS g_4on4,
                   AVG(player_ping) AS avg_ping,
                   COUNT(DISTINCT server_hostname) AS port_count,
                   string_agg(DISTINCT server_hostname, ', ' ORDER BY server_hostname) AS ports,
                   COUNT(DISTINCT CASE WHEN match_date::timestamptz >= NOW() - INTERVAL '90 days' THEN match_id END) / 13.0 AS avg_games_per_week_3mo,
                   COUNT(DISTINCT CASE WHEN match_date::timestamptz >= NOW() - INTERVAL '365 days' THEN match_id END) / 52.0 AS avg_games_per_week_12mo
            FROM base
        """, (host_root,))
        stats = dict(cur.fetchone() or {})

        # Most-played map on this server (across ports)
        cur.execute("""
            SELECT match_map, COUNT(*) AS games FROM matches
            WHERE split_part(server_hostname, ':', 1) = %s AND match_map IS NOT NULL
            GROUP BY match_map ORDER BY games DESC LIMIT 5
        """, (host_root,))
        top_maps = [dict(r) for r in cur.fetchall()]

        # Top players by match count
        cur.execute("""
            SELECT p.canonical_id, COALESCE(pc.display_name, p.canonical_id) AS display,
                   COUNT(DISTINCT p.match_id) AS games
            FROM players p
            JOIN matches m ON m.match_id = p.match_id
            LEFT JOIN players_canonical pc ON pc.canonical_id = p.canonical_id
            WHERE split_part(m.server_hostname, ':', 1) = %s AND p.canonical_id IS NOT NULL
            GROUP BY p.canonical_id, pc.display_name
            ORDER BY games DESC LIMIT 8
        """, (host_root,))
        top_by_matches = [dict(r) for r in cur.fetchall()]

        # Top players by 1on1 rating who've played here ≥10 times (across ports)
        cur.execute("""
            WITH played_here AS (
                SELECT p.canonical_id, COUNT(DISTINCT p.match_id) AS games_here
                FROM players p JOIN matches m ON m.match_id = p.match_id
                WHERE split_part(m.server_hostname, ':', 1) = %s AND p.canonical_id IS NOT NULL
                GROUP BY p.canonical_id HAVING COUNT(DISTINCT p.match_id) >= 10
            )
            SELECT r.canonical_id, COALESCE(pc.display_name, r.canonical_id) AS display,
                   r.mu, r.sigma, r.conservative, COALESCE(r.unique_opponents, 0) AS unique_opponents,
                   r.matches_rated, ph.games_here
            FROM ratings r
            JOIN played_here ph ON ph.canonical_id = r.canonical_id
            LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
            WHERE r.mode = '1on1' AND r.map = '' AND r.matches_rated >= 10
            ORDER BY r.conservative DESC LIMIT 8
        """, (host_root,))
        top_by_rating = []
        top_rows = cur.fetchall()
        cutoffs_1on1 = _get_tier_cutoffs(cur, "1on1") if top_rows else {}
        for r in top_rows:
            factor = diversity_factor(r["unique_opponents"], threshold=DIVERSITY_THRESHOLD_OVERALL)
            cons_eff = r["mu"] - 3 * r["sigma"] * factor
            top_by_rating.append({
                "canonical_id": r["canonical_id"],
                "display": r["display"],
                "conservative": round(cons_eff, 1),
                "games_here": r["games_here"],
                "tier": tier_for(cons_eff, cutoffs_1on1),
            })

        # Weekly activity for the FULL history of this server (no 53-week cap).
        # Pad with zero-game weeks from first-seen-match to today so the heatmap
        # shows continuous coverage, no gaps.
        cur.execute("""
            SELECT to_char(match_date::timestamptz, 'IYYY-IW') AS week,
                   MIN(match_date::timestamptz) AS week_start, COUNT(*) AS games
            FROM matches
            WHERE split_part(server_hostname, ':', 1) = %s
            GROUP BY week ORDER BY week
        """, (host_root,))
        raw = {r["week"]: dict(r) for r in cur.fetchall()}

        # Determine the first-week to start the skeleton from. Use the earliest match
        # we have, but cap at 3 years back so we don't render absurdly wide for ancient
        # servers with thousands of empty weeks.
        from datetime import timedelta
        today = datetime.now(timezone.utc)
        first_match_iso = stats.get("first_match")
        if first_match_iso:
            try:
                first_dt = datetime.fromisoformat(first_match_iso.replace("Z", "+00:00"))
            except ValueError:
                first_dt = today - timedelta(weeks=53)
        else:
            first_dt = today - timedelta(weeks=53)
        cap = today - timedelta(weeks=52 * 3)  # 3 year cap
        start_dt = max(first_dt, cap)
        weeks_span = max(53, int((today - start_dt).days / 7) + 1)

        weekly = []
        for n in range(weeks_span - 1, -1, -1):
            dt = today - timedelta(weeks=n)
            iso_year, iso_week, _ = dt.isocalendar()
            wk_key = f"{iso_year}-{iso_week:02d}"
            existing = raw.get(wk_key)
            if existing:
                weekly.append({
                    "week": existing["week"],
                    "week_start": existing["week_start"].isoformat() if hasattr(existing["week_start"], "isoformat") else existing["week_start"],
                    "games": existing["games"],
                })
            else:
                weekly.append({"week": wk_key, "week_start": dt.isoformat(), "games": 0})

    # Per-port live state — one row per (host:port) variant. Hub data updated
    # every 2h by the periodic sync. Used by the expanded /servers view so
    # each port shows its own map/mode/players list separately, not aggregated.
    with pg() as conn2:
        pcur = conn2.cursor()
        pcur.execute("""
            SELECT hostname, live_address,
                   COALESCE(NULLIF(split_part(live_address, ':', 2), ''),
                            NULLIF(split_part(hostname, ':', 2), ''),
                            '?') AS port,
                   is_live, current_map, current_mode, current_players,
                   current_specs, max_clients, fraglimit, timelimit, teamplay, deathmatch,
                   qtv_stream_url, qtv_viewer_count, mvdsv_version,
                   current_players_json, last_seen_live
            FROM servers
            WHERE split_part(hostname, ':', 1) = %s
              AND (is_live = TRUE OR current_players_json IS NOT NULL)
            ORDER BY port, hostname
        """, (host_root,))
        ports = []
        seen_ports = set()  # dedup the trailing-junk hostname variants ("28502" vs "28502�")
        for r in pcur.fetchall():
            port = r["port"]
            if port in seen_ports:
                continue
            seen_ports.add(port)
            players = None
            if r["current_players_json"]:
                try:
                    players = json.loads(r["current_players_json"])
                except Exception:
                    players = None
            ports.append({
                "port": port,
                "hostname": r["hostname"],
                "live_address": r["live_address"],
                "is_live": r["is_live"],
                "current_map": r["current_map"],
                "current_mode": r["current_mode"],
                "current_players": r["current_players"],
                "current_specs": r["current_specs"],
                "max_clients": r["max_clients"],
                "fraglimit": r["fraglimit"],
                "timelimit": r["timelimit"],
                "qtv_stream_url": r["qtv_stream_url"],
                "qtv_viewer_count": r["qtv_viewer_count"],
                "players": players or [],
            })
        pcur.close()

    return {
        "hostname": host_root,
        "meta": dict(meta),
        "stats": stats,
        "top_maps": top_maps,
        "top_by_matches": top_by_matches,
        "top_by_rating": top_by_rating,
        "weekly_activity": weekly,
        "ports": ports,
    }


# ── Map rankings: rankings filtered to a specific map ─────────────────────────

@app.get("/api/rankings/maps/{map_name}")
def map_rankings(
    response: Response,
    map_name: str,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    min_matches: int = Query(5, ge=1, le=10_000),
    limit: int = Query(500, ge=1, le=2000),
):
    # Per-map already requires 5 by default; enforce as hard floor too.
    min_matches = max(min_matches, 5)
    """Per-map OpenSkill leaderboard. Used by the Maps deep-dive's rank pill
    link and the dedicated /rankings/maps page."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT r.canonical_id,
                   COALESCE(pc.display_name, r.canonical_id) AS display,
                   r.mu, r.sigma, r.conservative,
                   COALESCE(r.unique_opponents, 0) AS unique_opponents,
                   r.matches_rated, r.wins, r.losses, r.draws
            FROM ratings r
            LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
            WHERE r.mode = %s AND r.map = %s AND r.matches_rated >= %s
        """, (mode, map_name, min_matches))
        rows = cur.fetchall()
        cutoffs = _get_tier_cutoffs(cur, mode, map_name)

    # Diversity factor is a no-op now (OpenSkill handles it natively) — sigma_eff
    # equals stored sigma. Kept for API-shape stability with the prior version.
    out = []
    for r in rows:
        factor = diversity_factor(r["unique_opponents"], threshold=DIVERSITY_THRESHOLD_PER_MAP)
        sigma_eff = r["sigma"] * factor
        conservative_eff = r["mu"] - 3 * sigma_eff
        out.append({
            "canonical_id": r["canonical_id"],
            "display": r["display"],
            "mu": round(r["mu"], 1),
            "sigma": round(r["sigma"], 1),
            "sigma_effective": round(sigma_eff, 1),
            "conservative": round(conservative_eff, 1),
            "conservative_raw": round(r["conservative"], 1),
            "matches": r["matches_rated"],
            "unique_opponents": r["unique_opponents"],
            "provisional": r["unique_opponents"] < DIVERSITY_THRESHOLD_PER_MAP,
            "wins": r["wins"],
            "losses": r["losses"],
            "draws": r["draws"],
            "win_rate": round(r["wins"] / r["matches_rated"], 3) if r["matches_rated"] else None,
            "tier": tier_for(conservative_eff, cutoffs),
        })
    out.sort(key=lambda x: -x["conservative"])
    for i, p in enumerate(out[:limit]):
        p["rank"] = i + 1
    return {"mode": mode, "map": map_name, "count": len(out), "players": out[:limit]}


# ── Head-to-head: two players, overall + per-map breakdown + predictions ──

@app.get("/api/h2h")
def head_to_head(
    response: Response,
    p1: str = Query(..., min_length=1, description="canonical_id of player A"),
    p2: str = Query(..., min_length=1, description="canonical_id of player B"),
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    recent_limit: int = Query(20, ge=1, le=100),
    since_days: int | None = Query(None, ge=1, le=10_000,
                                   description="restrict H2H rows to last N days; null = all time"),
):
    """Compare two players: head-to-head record + per-map breakdown + per-map
    prediction (OpenSkill predict_win on per-map ratings). Powers the /h2h page.

    p1 and p2 must be canonical_ids — use /api/search to resolve names first.
    """
    if p1 == p2:
        raise HTTPException(400, "p1 and p2 must be different players")
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"

    # Local import to avoid circular pollution at module load; openskill is only
    # needed in this one endpoint for predict_win.
    from openskill.models import PlackettLuce
    model = PlackettLuce(mu=1500.0, sigma=500.0, beta=250.0)

    with pg() as conn:
        cur = conn.cursor()

        # 1. Both players' canonical metadata + overall rating
        cur.execute("""
            SELECT pc.canonical_id, pc.display_name, pc.region, pc.region_confidence,
                   r.mu, r.sigma, r.conservative, r.matches_rated, r.wins, r.losses
            FROM players_canonical pc
            LEFT JOIN ratings r ON r.canonical_id = pc.canonical_id
                                AND r.mode = %s AND r.map = ''
            WHERE pc.canonical_id = ANY(%s)
        """, (mode, [p1, p2]))
        found = {r["canonical_id"]: dict(r) for r in cur.fetchall()}
        if p1 not in found or p2 not in found:
            raise HTTPException(404, f"player not found: {set([p1, p2]) - set(found)}")

        overall_cutoffs = _get_tier_cutoffs(cur, mode)

        def shape_player(cid):
            r = found[cid]
            cons = r.get("conservative")
            return {
                "canonical_id": cid,
                "display": r["display_name"],
                "region": r["region"],
                "mu": round(r["mu"], 1) if r.get("mu") is not None else None,
                "sigma": round(r["sigma"], 1) if r.get("sigma") is not None else None,
                "conservative": round(cons, 1) if cons is not None else None,
                "matches": r.get("matches_rated"),
                "wins": r.get("wins"),
                "losses": r.get("losses"),
                "tier": tier_for(cons, overall_cutoffs) if cons else None,
            }

        player_a = shape_player(p1)
        player_b = shape_player(p2)

        # Skill-profile shape per player — 5 axes matching the profile sidebar's
        # Skill Profile radar (LG / RL / DDR / ±frag / Net dmg). Both players
        # drawn on the same pentagon so the skill-mismatch is visible.
        cur.execute("""
            SELECT canonical_id,
                   AVG(player_lg_hits::float / NULLIF(player_lg_attacks, 0)) AS lg_accuracy,
                   AVG(player_rl_virtual::float / NULLIF(player_rl_attacks, 0)) AS rl_accuracy,
                   SUM(player_damage_given)::float / NULLIF(SUM(player_damage_taken), 0) AS avg_ddr,
                   AVG(player_frags - player_deaths)::float AS avg_frag_diff,
                   AVG(player_damage_given - player_damage_taken)::float AS avg_net_dmg
            FROM players p JOIN matches m ON m.match_id = p.match_id
            WHERE p.canonical_id = ANY(%s) AND m.match_mode = %s
            GROUP BY canonical_id
        """, ([p1, p2], mode))
        weapon_shape = {r["canonical_id"]: {
            "lg_accuracy": r["lg_accuracy"],
            "rl_accuracy": r["rl_accuracy"],
            "avg_ddr": r["avg_ddr"],
            "avg_frag_diff": r["avg_frag_diff"],
            "avg_net_dmg": r["avg_net_dmg"],
        } for r in cur.fetchall()}
        player_a["weapon_shape"] = weapon_shape.get(p1, {})
        player_b["weapon_shape"] = weapon_shape.get(p2, {})

        # Population min/max per axis (rated 1on1 players, last 365d).
        # Same algorithm as /api/divisions/avg-stats — drives radar normalization
        # so Div 4 ±frag/Net dmg negative values render proportionally instead
        # of collapsing to center.
        cur.execute("""
            WITH per_player AS (
                SELECT p.canonical_id,
                       AVG(p.player_lg_hits::float / NULLIF(p.player_lg_attacks, 0)) AS lg,
                       AVG(p.player_rl_virtual::float / NULLIF(p.player_rl_attacks, 0)) AS rl,
                       SUM(p.player_damage_given)::float / NULLIF(SUM(p.player_damage_taken), 0) AS ddr,
                       AVG(p.player_frags - p.player_deaths)::float AS frag_diff,
                       AVG(p.player_damage_given - p.player_damage_taken)::float AS net_dmg
                FROM players p
                JOIN matches m ON m.match_id = p.match_id
                JOIN ratings r ON r.canonical_id = p.canonical_id
                    AND r.mode = %(mode)s AND r.map = '' AND r.matches_rated >= 10
                WHERE m.match_mode = %(mode)s
                  AND m.match_date >= (NOW() - INTERVAL '365 days')::text
                GROUP BY p.canonical_id
                HAVING COUNT(*) >= 5
            )
            SELECT MIN(lg) AS lg_min, MAX(lg) AS lg_max,
                   MIN(rl) AS rl_min, MAX(rl) AS rl_max,
                   MIN(ddr) AS ddr_min, MAX(ddr) AS ddr_max,
                   MIN(frag_diff) AS fd_min, MAX(frag_diff) AS fd_max,
                   MIN(net_dmg) AS nd_min, MAX(net_dmg) AS nd_max
            FROM per_player
        """, {"mode": mode})
        rng = cur.fetchone() or {}
        skill_profile_ranges = {
            "lg_accuracy":   {"min": rng.get("lg_min"),  "max": rng.get("lg_max")},
            "rl_accuracy":   {"min": rng.get("rl_min"),  "max": rng.get("rl_max")},
            "avg_ddr":       {"min": rng.get("ddr_min"), "max": rng.get("ddr_max")},
            "avg_frag_diff": {"min": rng.get("fd_min"),  "max": rng.get("fd_max")},
            "avg_net_dmg":   {"min": rng.get("nd_min"),  "max": rng.get("nd_max")},
        }

        # 2. H2H summary across matches in this mode (optionally within a recent time window)
        date_clause = ""
        date_param = []
        if since_days:
            since_iso = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
            date_clause = " AND m.match_date >= %s"
            date_param = [since_iso]
        cur.execute(f"""
            SELECT m.match_id, m.match_date, m.match_map,
                   p1.player_frags AS f1, p1.player_damage_given AS dg1, p1.player_damage_taken AS dt1,
                   p2.player_frags AS f2, p2.player_damage_given AS dg2, p2.player_damage_taken AS dt2
            FROM matches m
            JOIN players p1 ON p1.match_id = m.match_id AND p1.canonical_id = %s
            JOIN players p2 ON p2.match_id = m.match_id AND p2.canonical_id = %s
            WHERE m.match_mode = %s{date_clause}
            ORDER BY m.match_date DESC
        """, [p1, p2, mode, *date_param])
        h2h_rows = cur.fetchall()

        total = len(h2h_rows)
        a_wins = sum(1 for r in h2h_rows if (r["f1"] or 0) > (r["f2"] or 0))
        b_wins = sum(1 for r in h2h_rows if (r["f2"] or 0) > (r["f1"] or 0))
        draws = total - a_wins - b_wins
        # Aggregate damage given/taken across H2H
        a_dg = sum(r["dg1"] or 0 for r in h2h_rows)
        a_dt = sum(r["dt1"] or 0 for r in h2h_rows)
        b_dg = sum(r["dg2"] or 0 for r in h2h_rows)
        b_dt = sum(r["dt2"] or 0 for r in h2h_rows)
        h2h_summary = {
            "matches": total,
            "wins_a": a_wins,
            "wins_b": b_wins,
            "draws": draws,
            "last_match": h2h_rows[0]["match_date"] if h2h_rows else None,
            "ddr_a": round(a_dg / a_dt, 2) if a_dt > 0 else None,
            "ddr_b": round(b_dg / b_dt, 2) if b_dt > 0 else None,
        }

        # 3. Per-map breakdown: where they've played each other + per-map ratings
        # for prediction. Aggregate H2H by map.
        per_map_h2h = {}
        for r in h2h_rows:
            m_name = r["match_map"]
            if m_name not in per_map_h2h:
                per_map_h2h[m_name] = {"matches": 0, "wins_a": 0, "wins_b": 0,
                                       "a_dg": 0, "a_dt": 0, "b_dg": 0, "b_dt": 0}
            agg = per_map_h2h[m_name]
            agg["matches"] += 1
            if (r["f1"] or 0) > (r["f2"] or 0):
                agg["wins_a"] += 1
            elif (r["f2"] or 0) > (r["f1"] or 0):
                agg["wins_b"] += 1
            agg["a_dg"] += r["dg1"] or 0
            agg["a_dt"] += r["dt1"] or 0
            agg["b_dg"] += r["dg2"] or 0
            agg["b_dt"] += r["dt2"] or 0

        # Both players' per-map ratings (one query)
        cur.execute("""
            SELECT canonical_id, map, mu, sigma, conservative, matches_rated, wins, losses
            FROM ratings
            WHERE canonical_id = ANY(%s) AND mode = %s AND map != ''
        """, ([p1, p2], mode))
        per_map_rating = {}  # {(cid, map): rating dict}
        for r in cur.fetchall():
            per_map_rating[(r["canonical_id"], r["map"])] = dict(r)

        # Top-N most-played maps in this mode — the "real" map pool.
        # Excludes one-off custom/weird maps so the H2H table stays focused
        # on the maps people actually compete on.
        cur.execute("""
            SELECT match_map FROM matches
            WHERE match_mode = %s AND match_map IS NOT NULL
            GROUP BY match_map ORDER BY count(*) DESC LIMIT 20
        """, (mode,))
        top_maps = {r["match_map"] for r in cur.fetchall()}

        # Filter rule (per user 2026-05-26):
        #   - at least 1 H2H match between these two players on this map
        #   - AND the map is in the top-20 most-played maps overall
        # No "rated only" filter — H2H presence is the signal we want.
        all_maps = {m for m in per_map_h2h.keys()
                    if per_map_h2h[m]["matches"] >= 1 and m in top_maps}

        maps_out = []
        for m_name in all_maps:
            ra = per_map_rating.get((p1, m_name))
            rb = per_map_rating.get((p2, m_name))
            h2h = per_map_h2h.get(m_name, {"matches": 0, "wins_a": 0, "wins_b": 0,
                                           "a_dg": 0, "a_dt": 0, "b_dg": 0, "b_dt": 0})

            # Prediction: only if both players have a per-map rating
            pred_a = pred_b = None
            if ra and rb:
                ra_obj = model.rating(mu=ra["mu"], sigma=ra["sigma"], name=p1)
                rb_obj = model.rating(mu=rb["mu"], sigma=rb["sigma"], name=p2)
                probs = model.predict_win([[ra_obj], [rb_obj]])
                pred_a = round(probs[0], 3)
                pred_b = round(probs[1], 3)

            maps_out.append({
                "map": m_name,
                "h2h_matches": h2h["matches"],
                "h2h_wins_a": h2h["wins_a"],
                "h2h_wins_b": h2h["wins_b"],
                "h2h_ddr_a": round(h2h["a_dg"] / h2h["a_dt"], 2) if h2h["a_dt"] > 0 else None,
                "h2h_ddr_b": round(h2h["b_dg"] / h2h["b_dt"], 2) if h2h["b_dt"] > 0 else None,
                "rating_a": {"cons": round(ra["conservative"], 1), "matches": ra["matches_rated"],
                             "wins": ra["wins"], "losses": ra["losses"]} if ra else None,
                "rating_b": {"cons": round(rb["conservative"], 1), "matches": rb["matches_rated"],
                             "wins": rb["wins"], "losses": rb["losses"]} if rb else None,
                "predict_win_a": pred_a,
                "predict_win_b": pred_b,
            })
        # Sort by total H2H matches (heaviest map first), then by combined per-map exposure.
        maps_out.sort(
            key=lambda x: (
                -x["h2h_matches"],
                -((x["rating_a"]["matches"] if x["rating_a"] else 0) +
                  (x["rating_b"]["matches"] if x["rating_b"] else 0)),
            )
        )

        # 4. Recent H2H matches (capped, for the timeline)
        recent = []
        for r in h2h_rows[:recent_limit]:
            recent.append({
                "match_id": r["match_id"],
                "date": r["match_date"],
                "map": r["match_map"],
                "frags_a": r["f1"], "frags_b": r["f2"],
                "ddr_a": round((r["dg1"] or 0) / (r["dt1"] or 1), 2) if r["dt1"] else None,
                "ddr_b": round((r["dg2"] or 0) / (r["dt2"] or 1), 2) if r["dt2"] else None,
            })

        # 5. Overall prediction (using overall ratings) — single number for the headline
        overall_pred_a = overall_pred_b = None
        if player_a["mu"] is not None and player_b["mu"] is not None:
            oa = model.rating(mu=player_a["mu"], sigma=player_a["sigma"], name=p1)
            ob = model.rating(mu=player_b["mu"], sigma=player_b["sigma"], name=p2)
            probs = model.predict_win([[oa], [ob]])
            overall_pred_a = round(probs[0], 3)
            overall_pred_b = round(probs[1], 3)

    return {
        "mode": mode,
        "player_a": player_a,
        "player_b": player_b,
        "h2h": h2h_summary,
        "overall_predict_win_a": overall_pred_a,
        "overall_predict_win_b": overall_pred_b,
        "maps": maps_out,
        "recent_matches": recent,
        "skill_profile_ranges": skill_profile_ranges,
    }


@app.get("/api/maps")
def list_maps(mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"), min_players: int = Query(5, ge=1, le=1000)):
    """List every map that has OpenSkill ratings in this mode, sorted by how many
    players are rated on it. Powers the map dropdown on /rankings/maps."""
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT map, COUNT(*) AS players
            FROM ratings
            WHERE mode = %s AND map != ''
            GROUP BY map HAVING COUNT(*) >= %s
            ORDER BY players DESC
        """, (mode, min_players))
        return {"mode": mode, "maps": [{"map": r["map"], "players": r["players"]} for r in cur.fetchall()]}


# ── Rating history (chronological mu/sigma over time) ─────────────────────────

@app.get("/api/players/{canonical_id}/rating-history")
def rating_history(
    response: Response,
    canonical_id: str,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    map: str = Query("", description="Empty = overall mode rating; else map name"),
    limit: int = Query(20000, ge=1, le=50000),
):
    """Per-match OpenSkill trajectory for a player. Each row is one rated match
    with mu_after, sigma_after, conservative-after, delta, opponent. Used to draw
    the rating history chart on the profile page. High default limit so even players
    with multi-thousand-match histories (Cronus = 5144) get full coverage."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"

    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT match_date, opponent_cid, outcome,
                   mu_after, sigma_after, delta,
                   (mu_after - 3 * sigma_after) AS conservative_after
            FROM rating_history
            WHERE canonical_id = %s AND mode = %s AND map = %s
            ORDER BY match_date ASC
            LIMIT %s
        """, (canonical_id, mode, map, limit))
        out = []
        for r in cur.fetchall():
            out.append({
                "match_date": r["match_date"],
                "opponent_cid": r["opponent_cid"],
                "outcome": r["outcome"],
                "mu": round(r["mu_after"], 1),
                "sigma": round(r["sigma_after"], 1),
                "conservative": round(r["conservative_after"], 1),
                "delta": round(r["delta"], 2) if r["delta"] is not None else 0,
            })
    return {"canonical_id": canonical_id, "mode": mode, "map": map, "count": len(out), "points": out}


# ── Per-division weapon-stat averages (for profile donut reference rings) ────

@app.get("/api/divisions/avg-stats")
def divisions_avg_stats(
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    since_days: int = Query(90, ge=1, le=10_000),
):
    """For each division, return the average weapon-accuracy + item-pickup stats
    across all players currently in that division, computed over matches in the
    last `since_days`. Used by profile donuts to render a 'where you sit vs your
    division' reference marker."""
    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=3600"
    since_iso = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

    with pg() as conn:
        cur = conn.cursor()
        cutoffs = _get_tier_cutoffs(cur, mode)
        if not cutoffs:
            return {"mode": mode, "since_days": since_days, "divisions": {}}

        # Map each rated player to their current division (based on cons cutoffs),
        # then aggregate match-level stats from the players table within the window.
        # CASE chain mirrors the order of TIER_SPECS so higher cutoffs win first.
        cur.execute("""
            WITH player_div AS (
                SELECT canonical_id,
                       CASE
                           WHEN conservative >= %(c0)s THEN 'div0'
                           WHEN conservative >= %(c1)s THEN 'div1'
                           WHEN conservative >= %(c2)s THEN 'div2'
                           WHEN conservative >= %(c3)s THEN 'div3'
                           ELSE 'div4'
                       END AS div
                FROM ratings
                WHERE mode = %(mode)s AND map = '' AND matches_rated >= 10
            )
            SELECT pd.div,
                   AVG(p.player_lg_hits::float / NULLIF(p.player_lg_attacks, 0)) AS lg_accuracy,
                   AVG(p.player_rl_virtual::float / NULLIF(p.player_rl_attacks, 0)) AS rl_accuracy,
                   AVG(p.player_ssg_hits::float / NULLIF(p.player_ssg_attacks, 0)) AS ssg_accuracy,
                   AVG(p.player_sg_hits::float / NULLIF(p.player_sg_attacks, 0)) AS sg_accuracy,
                   AVG(p.player_gl_directs::float / NULLIF(p.player_gl_attacks, 0)) AS gl_accuracy,
                   AVG(p.player_ra_taken)::float AS avg_ra,
                   AVG(p.player_ya_taken)::float AS avg_ya,
                   AVG(p.player_ga_taken)::float AS avg_ga,
                   AVG(p.player_health100_taken)::float AS avg_mh,
                   -- Composite metrics used by the new 1on1-focused radar
                   SUM(p.player_damage_given)::float / NULLIF(SUM(p.player_damage_taken), 0) AS avg_ddr,
                   AVG(p.player_frags - p.player_deaths)::float AS avg_frag_diff,
                   AVG(p.player_damage_given - p.player_damage_taken)::float AS avg_net_dmg,
                   COUNT(DISTINCT pd.canonical_id) AS player_count,
                   COUNT(*) AS match_player_rows
            FROM player_div pd
            JOIN players p ON p.canonical_id = pd.canonical_id
            JOIN matches m ON m.match_id = p.match_id
            WHERE m.match_mode = %(mode)s AND m.match_date >= %(since)s
            GROUP BY pd.div
        """, {
            "mode": mode, "since": since_iso,
            "c0": cutoffs.get("div0", float("inf")),
            "c1": cutoffs.get("div1", float("inf")),
            "c2": cutoffs.get("div2", float("inf")),
            "c3": cutoffs.get("div3", float("inf")),
        })
        out = {}
        for r in cur.fetchall():
            out[r["div"]] = {
                "lg_accuracy": r["lg_accuracy"],
                "rl_accuracy": r["rl_accuracy"],
                "ssg_accuracy": r["ssg_accuracy"],
                "sg_accuracy": r["sg_accuracy"],
                "gl_accuracy": r["gl_accuracy"],
                "avg_ra": r["avg_ra"],
                "avg_ya": r["avg_ya"],
                "avg_ga": r["avg_ga"],
                "avg_mh": r["avg_mh"],
                # New Skill Profile metrics (2026-05-27) — needed by the radar overlay
                "avg_ddr": r["avg_ddr"],
                "avg_frag_diff": r["avg_frag_diff"],
                "avg_net_dmg": r["avg_net_dmg"],
                "player_count": r["player_count"],
                "match_player_rows": r["match_player_rows"],
            }
        # Population min/max per axis — drives the radar's scale so the inner
        # pentagon = worst rated player, outer pentagon = best rated player.
        # Hardcoded caps used to collapse Div 3/4 polygons toward center because
        # negative ±frag / Net dmg / sub-1.0 DDR clamped at 0. With real ranges
        # everyone's polygon sits proportionally on the same scale.
        cur.execute("""
            WITH per_player AS (
                SELECT p.canonical_id,
                       AVG(p.player_lg_hits::float / NULLIF(p.player_lg_attacks, 0)) AS lg,
                       AVG(p.player_rl_virtual::float / NULLIF(p.player_rl_attacks, 0)) AS rl,
                       SUM(p.player_damage_given)::float / NULLIF(SUM(p.player_damage_taken), 0) AS ddr,
                       AVG(p.player_frags - p.player_deaths)::float AS frag_diff,
                       AVG(p.player_damage_given - p.player_damage_taken)::float AS net_dmg
                FROM players p
                JOIN matches m ON m.match_id = p.match_id
                JOIN ratings r ON r.canonical_id = p.canonical_id
                    AND r.mode = %(mode)s AND r.map = '' AND r.matches_rated >= 10
                WHERE m.match_mode = %(mode)s AND m.match_date >= %(since)s
                GROUP BY p.canonical_id
                HAVING COUNT(*) >= 5
            )
            SELECT MIN(lg) AS lg_min, MAX(lg) AS lg_max,
                   MIN(rl) AS rl_min, MAX(rl) AS rl_max,
                   MIN(ddr) AS ddr_min, MAX(ddr) AS ddr_max,
                   MIN(frag_diff) AS fd_min, MAX(frag_diff) AS fd_max,
                   MIN(net_dmg) AS nd_min, MAX(net_dmg) AS nd_max
            FROM per_player
        """, {"mode": mode, "since": since_iso})
        rng = cur.fetchone() or {}
        ranges = {
            "lg_accuracy":   {"min": rng.get("lg_min"), "max": rng.get("lg_max")},
            "rl_accuracy":   {"min": rng.get("rl_min"), "max": rng.get("rl_max")},
            "avg_ddr":       {"min": rng.get("ddr_min"), "max": rng.get("ddr_max")},
            "avg_frag_diff": {"min": rng.get("fd_min"), "max": rng.get("fd_max")},
            "avg_net_dmg":   {"min": rng.get("nd_min"), "max": rng.get("nd_max")},
        }
    return {"mode": mode, "since_days": since_days, "divisions": out, "ranges": ranges}


# ── Full profile (drop-in replacement for the static profile JSON shape) ───────

@app.get("/api/players/{canonical_id}/full")
def player_profile_full(
    response: Response,
    canonical_id: str,
    window: str = Query("90", description="'7' | '30' | '90' | '365' | 'all'"),
):
    """Returns the same JSON shape as /profiles/{id}.json so the frontend can
    swap fetch URLs without changing render logic. Single-window for now —
    other windows are fetched lazily as the user clicks the window pill."""
    # Profile data only changes when rate.py runs (≈ daily), so cache HARD at the
    # CDN edge (5min fresh) + serve-stale-while-revalidating for a day. Long TTL
    # is what keeps origin/DB load low — the db-f1-micro can't take a per-request
    # origin hit per profile view (2026-06-03 pool-exhaustion incident).
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=86400"

    # 'all' = no date filter (None). Otherwise it's a day count.
    window_key = window
    if window == "all":
        days = None
    else:
        try:
            days = int(window)
        except ValueError:
            raise HTTPException(400, "window must be int or 'all'")
        if days < 1 or days > 3650:
            raise HTTPException(400, "window out of range")

    with pg() as conn:
        cur = conn.cursor()
        # Player resolution
        cur.execute("""
            SELECT canonical_id, display_name, login,
                   region, region_confidence, region_distribution
            FROM players_canonical WHERE canonical_id = %s
        """, (canonical_id,))
        canon = cur.fetchone()
        if not canon:
            raise HTTPException(404, "player not found")

        # Career
        career = profile_pg.career(cur, canonical_id)

        # Per-mode ratings (overall) + tier + diversity-adjusted conservative
        cur.execute("""
            SELECT mode, mu, sigma, conservative, matches_rated, wins, losses, draws, updated_at,
                   COALESCE(unique_opponents, 0) AS unique_opponents,
                   (SELECT COUNT(*) + 1 FROM ratings r2
                    WHERE r2.mode = r.mode AND r2.map = '' AND r2.conservative > r.conservative) AS rank,
                   (SELECT COUNT(*) FROM ratings r3 WHERE r3.mode = r.mode AND r3.map = '') AS total_rated
            FROM ratings r WHERE canonical_id = %s AND map = ''
        """, (canonical_id,))
        ratings = {"1on1": None, "2on2": None, "4on4": None}
        mode_rows = cur.fetchall()
        cutoffs_by_mode = {r["mode"]: _get_tier_cutoffs(cur, r["mode"]) for r in mode_rows}
        for r in mode_rows:
            factor = diversity_factor(r["unique_opponents"], threshold=DIVERSITY_THRESHOLD_OVERALL)
            sigma_eff = r["sigma"] * factor
            conservative_eff = r["mu"] - 3 * sigma_eff
            ratings[r["mode"]] = {
                "mu": round(r["mu"], 1),
                "sigma": round(r["sigma"], 1),
                "sigma_effective": round(sigma_eff, 1),
                "conservative": round(conservative_eff, 1),
                "conservative_raw": round(r["conservative"], 1),
                "matches": r["matches_rated"],
                "unique_opponents": r["unique_opponents"],
                "provisional": r["unique_opponents"] < DIVERSITY_THRESHOLD_OVERALL,
                "wins": r["wins"],
                "losses": r["losses"],
                "draws": r["draws"],
                "rank": r["rank"],
                "total_rated": r["total_rated"],
                "tier": tier_for(conservative_eff, cutoffs_by_mode.get(r["mode"])),
                "updated_at": r["updated_at"],
            }

        # Per-map OpenSkill (1on1 only for now) — tier cutoffs computed per-map.
        cur.execute("""
            SELECT map, mu, sigma, conservative, matches_rated, wins, losses, draws,
                   COALESCE(unique_opponents, 0) AS unique_opponents,
                   (SELECT COUNT(*) + 1 FROM ratings r2
                    WHERE r2.mode = r.mode AND r2.map = r.map AND r2.conservative > r.conservative) AS rank,
                   (SELECT COUNT(*) FROM ratings r3 WHERE r3.mode = r.mode AND r3.map = r.map) AS total_rated
            FROM ratings r WHERE canonical_id = %s AND mode = '1on1' AND map != ''
        """, (canonical_id,))
        map_ratings_1on1 = {}
        for r in cur.fetchall():
            factor = diversity_factor(r["unique_opponents"], threshold=DIVERSITY_THRESHOLD_PER_MAP)
            sigma_eff = r["sigma"] * factor
            conservative_eff = r["mu"] - 3 * sigma_eff
            map_ratings_1on1[r["map"]] = {
                "mu": round(r["mu"], 1),
                "sigma": round(r["sigma"], 1),
                "sigma_effective": round(sigma_eff, 1),
                "conservative": round(conservative_eff, 1),
                "conservative_raw": round(r["conservative"], 1),
                "matches": r["matches_rated"],
                "unique_opponents": r["unique_opponents"],
                "provisional": r["unique_opponents"] < DIVERSITY_THRESHOLD_PER_MAP,
                "wins": r["wins"],
                "losses": r["losses"],
                "draws": r["draws"],
                "rank": r["rank"],
                "total_rated": r["total_rated"],
            }

        # The window payload (single window — call again with ?window=30 etc to swap)
        win_payload = profile_pg.build_window(cur, canonical_id, days=days)
        # Enrich by_map_1on1 with per-map ELO for the Maps card
        for row in win_payload["by_map_1on1"]:
            mr = map_ratings_1on1.get(row["bucket"])
            if mr:
                row["rating"] = mr["conservative"]
                row["mu"] = mr["mu"]
                row["sigma"] = mr["sigma"]
                row["rated_matches"] = mr["matches"]
                row["rank"] = mr["rank"]
                row["total_rated"] = mr["total_rated"]
        # No prior period for the 'all' window (there's nothing before "all time").
        win_payload["prior"] = profile_pg.build_prior(cur, canonical_id, days=days) if days else None
        win_payload["year_ago"] = None  # skip year_ago for now — rarely used, expensive

        # Recent matches list for the Recent tab + Overview's last-10 strip.
        # Shape mirrors the legacy static /profiles/*.json: match_mode/match_map
        # (not mode/map), player_frags + opponent_frags + outcome (W/L/D) for the
        # 1on1 row, accuracy fields. Profile.html's recentTable column defs
        # depend on these exact key names.
        cur.execute("""
            WITH me AS (
                SELECT m.match_id, m.match_date, m.match_mode, m.match_map,
                       m.match_dmm, m.server_hostname,
                       p.player_frags, p.player_deaths,
                       (p.player_lg_hits::float / NULLIF(p.player_lg_attacks, 0)) AS lg_acc,
                       (p.player_rl_virtual::float / NULLIF(p.player_rl_attacks, 0)) AS rl_acc
                FROM matches m JOIN players p ON p.match_id = m.match_id
                WHERE p.canonical_id = %(cid)s
                ORDER BY m.match_date DESC
                LIMIT 50
            ),
            opp AS (
                -- For 1on1 only: the other player in the match is the opponent.
                -- For 2on2/4on4 leave opponent_name = null (the recentTable shows '—').
                -- Prefer the canonical display_name (clean) over raw player_name
                -- (which has color/escape codes like cr\5onus). Fall back to
                -- canonical_id if display_name is null, then raw name as last resort.
                SELECT me.match_id,
                       MAX(COALESCE(pc.display_name, p2.canonical_id, p2.player_name))
                           FILTER (WHERE p2.canonical_id IS DISTINCT FROM %(cid)s) AS opponent_name,
                       MAX(p2.player_frags)
                           FILTER (WHERE p2.canonical_id IS DISTINCT FROM %(cid)s) AS opponent_frags
                FROM me
                JOIN players p2 ON p2.match_id = me.match_id
                LEFT JOIN players_canonical pc ON pc.canonical_id = p2.canonical_id
                WHERE me.match_mode = '1on1'
                GROUP BY me.match_id
            )
            SELECT me.match_id, me.match_date, me.match_mode, me.match_map, me.match_dmm,
                   me.server_hostname, me.player_frags, me.player_deaths,
                   me.lg_acc, me.rl_acc,
                   opp.opponent_name, opp.opponent_frags,
                   CASE
                       WHEN me.match_mode = '1on1' AND opp.opponent_frags IS NOT NULL THEN
                           CASE
                               WHEN me.player_frags > opp.opponent_frags THEN 'win'
                               WHEN me.player_frags < opp.opponent_frags THEN 'loss'
                               ELSE 'draw'
                           END
                       ELSE NULL  -- 2on2/4on4 outcome needs team join, skip for now
                   END AS outcome
            FROM me LEFT JOIN opp ON opp.match_id = me.match_id
            ORDER BY me.match_date DESC
        """, {"cid": canonical_id})
        recent_matches = [dict(r) for r in cur.fetchall()]

    return {
        "player": canon["display_name"],
        "canonical_id": canon["canonical_id"],
        "aliases": canonical_id,
        "career": career,
        "ratings": ratings,
        "map_ratings_1on1": map_ratings_1on1,
        "windows_available": ["7", "30", "90", "365", "all"],
        "default_window": window_key,
        "windows": {window_key: win_payload},
        "recent_matches": recent_matches,
    }


# ── Per-map breakdown ──────────────────────────────────────────────────────────

@app.get("/api/players/{canonical_id}/maps/{map_name}/opponents")
def player_opponents_on_map(canonical_id: str, map_name: str, limit: int = Query(8, ge=1, le=50)):
    """Top 1on1 opponents the player has faced ON a specific map. Used by the
    Maps deep-dive's expand panel so 'Top opponents' actually reflects the map
    you clicked on, not the player's global 1on1 H2H list."""
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            WITH my_matches AS (
                SELECT m.match_id, p.player_name, p.player_frags
                FROM players p JOIN matches m ON m.match_id = p.match_id
                WHERE p.canonical_id = %(cid)s
                  AND m.match_mode = '1on1' AND m.match_map = %(map)s
            ),
            h2h AS (
                SELECT
                    COALESCE(opp.canonical_id, opp.player_name) AS opponent_key,
                    MAX(COALESCE(pc.display_name, opp.canonical_id, opp.player_name)) AS opponent,
                    COUNT(*) AS matches,
                    SUM(CASE WHEN my.player_frags > opp.player_frags THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN my.player_frags < opp.player_frags THEN 1 ELSE 0 END) AS losses,
                    AVG(my.player_frags - opp.player_frags) AS avg_frag_diff,
                    MAX(opp.player_name) AS sample_name
                FROM my_matches my
                JOIN players opp ON opp.match_id = my.match_id AND opp.player_name <> my.player_name
                LEFT JOIN players_canonical pc ON pc.canonical_id = opp.canonical_id
                GROUP BY COALESCE(opp.canonical_id, opp.player_name)
                ORDER BY matches DESC
                LIMIT %(limit)s
            )
            SELECT * FROM h2h
        """, {"cid": canonical_id, "map": map_name, "limit": limit})
        out = []
        for r in cur.fetchall():
            out.append({
                "opponent_canonical_id": r["opponent_key"],
                "opponent": r["opponent"],
                "matches": r["matches"],
                "wins": r["wins"],
                "losses": r["losses"],
                "win_rate": round(r["wins"] / r["matches"], 3) if r["matches"] else None,
                "avg_frag_diff": round(float(r["avg_frag_diff"]), 2) if r["avg_frag_diff"] is not None else None,
            })
    return {"canonical_id": canonical_id, "map": map_name, "opponents": out}


@app.get("/api/players/{canonical_id}/maps")
def player_maps(canonical_id: str, min_matches: int = Query(5, ge=1, le=100)):
    with pg() as conn:
        cur = conn.cursor()
        # Lifetime per-map stats for this player in 1on1, joined with per-map OpenSkill.
        cur.execute("""
            WITH pm AS (
                SELECT m.match_map AS bucket,
                       COUNT(*) AS matches,
                       SUM(CASE WHEN p.player_frags > opp.player_frags THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN p.player_frags < opp.player_frags THEN 1 ELSE 0 END) AS losses,
                       AVG(p.player_frags - opp.player_frags) AS avg_frag_diff,
                       AVG(p.player_frags::float) AS avg_frags,
                       AVG(p.player_lg_hits::float / NULLIF(p.player_lg_attacks,0)) AS lg_accuracy,
                       AVG(p.player_rl_virtual::float / NULLIF(p.player_rl_attacks,0)) AS rl_accuracy,
                       MAX(m.match_date) AS last_played
                FROM players p
                JOIN matches m ON m.match_id = p.match_id AND m.match_mode = '1on1'
                JOIN players opp ON opp.match_id = p.match_id AND opp.canonical_id != p.canonical_id
                WHERE p.canonical_id = %(cid)s
                GROUP BY m.match_map
            )
            SELECT pm.*,
                   r.mu, r.sigma, r.conservative,
                   (SELECT COUNT(*) + 1 FROM ratings r2
                    WHERE r2.mode = '1on1' AND r2.map = pm.bucket
                      AND r2.conservative > r.conservative) AS rank,
                   (SELECT COUNT(*) FROM ratings r3
                    WHERE r3.mode = '1on1' AND r3.map = pm.bucket) AS total_rated
            FROM pm
            LEFT JOIN ratings r ON r.canonical_id = %(cid)s AND r.mode = '1on1' AND r.map = pm.bucket
            WHERE pm.matches >= %(min)s
            ORDER BY r.conservative DESC NULLS LAST, pm.matches DESC
        """, {"cid": canonical_id, "min": min_matches})

        out = []
        for r in cur.fetchall():
            out.append({
                "bucket": r["bucket"],
                "matches": r["matches"],
                "wins": r["wins"],
                "losses": r["losses"],
                "win_rate": round(r["wins"] / r["matches"], 3) if r["matches"] else None,
                "avg_frag_diff": round(r["avg_frag_diff"], 2) if r["avg_frag_diff"] is not None else None,
                "avg_frags": round(r["avg_frags"], 2) if r["avg_frags"] is not None else None,
                "lg_accuracy": round(r["lg_accuracy"], 3) if r["lg_accuracy"] is not None else None,
                "rl_accuracy": round(r["rl_accuracy"], 3) if r["rl_accuracy"] is not None else None,
                "last_played": r["last_played"],
                "rating": round(r["conservative"], 1) if r["conservative"] is not None else None,
                "mu": round(r["mu"], 1) if r["mu"] is not None else None,
                "sigma": round(r["sigma"], 1) if r["sigma"] is not None else None,
                "rank": r["rank"],
                "total_rated": r["total_rated"],
            })
    return {"canonical_id": canonical_id, "mode": "1on1", "maps": out}


# ── Players index ──────────────────────────────────────────────────────────────

@app.get("/api/players")
def players_index(
    threshold: int = Query(10, ge=1, le=10000),
    recent_min: int = Query(5, ge=1, le=10000),
    recent_window_days: int = Query(90, ge=1, le=3650),
):
    """Full player index — the live replacement for /profiles/index.json.
    Includes every canonical player meeting EITHER lifetime threshold OR
    recent-activity threshold (so active newcomers show up before they
    cross the lifetime bar)."""
    # match_date is stored as text; cast to timestamptz for window comparison.
    # Pass days as int and build the interval Postgres-side to avoid a string
    # concat in SQL.
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            WITH stats AS (
                SELECT p.canonical_id,
                       pc.display_name,
                       COUNT(DISTINCT p.match_id) AS matches,
                       SUM(CASE WHEN m.match_date::timestamptz >= NOW() - (%(days)s || ' days')::interval
                                THEN 1 ELSE 0 END) AS recent_matches,
                       MIN(m.match_date) AS first_seen,
                       MAX(m.match_date) AS last_seen
                FROM players p
                JOIN matches m ON m.match_id = p.match_id
                LEFT JOIN players_canonical pc ON pc.canonical_id = p.canonical_id
                WHERE p.canonical_id IS NOT NULL
                GROUP BY p.canonical_id, pc.display_name
            )
            SELECT canonical_id, display_name, matches, first_seen, last_seen
            FROM stats
            WHERE matches >= %(threshold)s OR recent_matches >= %(recent_min)s
            ORDER BY matches DESC
        """, {"days": recent_window_days, "threshold": threshold, "recent_min": recent_min})
        rows = cur.fetchall()
    players = [
        {
            "canonical_id": r["canonical_id"],
            "display": r["display_name"] or r["canonical_id"],
            "matches": r["matches"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
        }
        for r in rows
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(players),
        "players": players,
    }


def _items_by_map(cur, maps: set) -> dict:
    """Load BSP item locations [{kind,x,y,z}] per map from map_annotations.
    Powers first-item-intent (armor-first vs weapon-first). Returns {map: items};
    maps without entity data are simply absent (intent skipped for them)."""
    maps = [m for m in maps if m]
    if not maps:
        return {}
    cur.execute(
        "SELECT map, entities->'items' AS items FROM map_annotations "
        "WHERE map = ANY(%s) AND entities ? 'items'",
        (maps,),
    )
    return {r["map"]: r["items"] for r in cur.fetchall()}


def _spawns_by_map(cur, maps: set) -> dict:
    """BSP spawn entities per map (for FSO first-spawn extraction + deep-analyze)."""
    maps = [m for m in maps if m]
    if not maps:
        return {}
    cur.execute(
        "SELECT map, entities->'spawns' AS spawns FROM map_annotations "
        "WHERE map = ANY(%s) AND entities ? 'spawns'",
        (maps,),
    )
    return {r["map"]: r["spawns"] for r in cur.fetchall()}


_COACHING_DDL = """
CREATE TABLE IF NOT EXISTS coaching_runs (
  id BIGSERIAL PRIMARY KEY, canonical_id TEXT NOT NULL, mode TEXT NOT NULL,
  run_date DATE NOT NULL, matches_analyzed INT, wins INT, losses INT,
  metrics JSONB, levers JSONB, narration TEXT, narration_source TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), UNIQUE (canonical_id, mode, run_date));
CREATE TABLE IF NOT EXISTS match_analysis (
  id BIGSERIAL PRIMARY KEY, game_id BIGINT NOT NULL, canonical_id TEXT NOT NULL,
  map TEXT, result TEXT, timeline JSONB, analysis TEXT, source TEXT, model TEXT,
  created_at TIMESTAMPTZ DEFAULT now(), UNIQUE (game_id, canonical_id));
"""


def _ensure_coaching_tables(cur):
    """Idempotent: create coaching_runs + match_analysis if missing. Cheap; lets
    the feature self-provision in prod without a separate migration step."""
    cur.execute(_COACHING_DDL)
    # report column added 2026-06-03 for durable cross-session restore of the
    # last full coaching report (not just the metrics snapshot).
    cur.execute("ALTER TABLE coaching_runs ADD COLUMN IF NOT EXISTS report JSONB")


# ── Coaching (AI coach metric layer) ─────────────────────────────────────────
# Deterministic coaching primitives over a player's recent matches: item
# control, stack-at-engagement, restack efficiency, accuracy, death weapons —
# split win vs loss. The weakness engine + LLM narration sit on top of this.
# See docs/ai_coaching_platform.md. Heavy (parses N demos via mvd-api), so
# cache hard and cap N.

@app.get("/api/players/{canonical_id}/coaching/metrics")
def coaching_metrics(
    canonical_id: str,
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    limit: int = Query(15, ge=1, le=40),
):
    """Compute coaching primitives over the player's most recent `limit` matches
    in `mode` that have parseable demos (positive match_id = hub gameId). Returns
    per-match rows + a win/loss aggregate. Cached 1h (demos are immutable)."""
    import coaching as coaching_mod
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT display_name FROM players_canonical WHERE canonical_id = %s", (canonical_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "player not found")
        display = row["display_name"]
        # Recent matches with a resolvable hub gameId + the W/L outcome.
        # hub_game_id is the demo-addressing key for BOTH epochs (new rows where
        # match_id IS the gameId, and old migrated rows where it's a negative
        # hash but hub_game_id was backfilled from the demo filename).
        cur.execute("""
            SELECT m.hub_game_id AS game_id, m.match_map AS map,
                   p.player_frags AS mf, opp.player_frags AS of
            FROM players p
            JOIN matches m ON m.match_id = p.match_id AND m.match_mode = %(mode)s
            JOIN players opp ON opp.match_id = p.match_id AND opp.canonical_id <> p.canonical_id
            WHERE p.canonical_id = %(cid)s AND m.hub_game_id IS NOT NULL
            ORDER BY m.match_date DESC
            LIMIT %(limit)s
        """, {"cid": canonical_id, "mode": mode, "limit": limit})
        matches = cur.fetchall()
        items_by_map = _items_by_map(cur, {mr["map"] for mr in matches})

    per_match, results = [], []
    for mrow in matches:
        m = coaching_mod.match_metrics(mrow["game_id"], display,
                                       item_locs=items_by_map.get(mrow["map"]))
        per_match.append(m)
        results.append("W" if (mrow["mf"] or 0) > (mrow["of"] or 0) else "L")
    parsed = [m for m in per_match if m]
    agg = coaching_mod.aggregate(per_match, results)
    return {
        "canonical_id": canonical_id,
        "display": display,
        "mode": mode,
        "requested": len(matches),
        "parsed": len(parsed),
        "aggregate": agg,
        "matches": [
            {**m, "result": r}
            for m, r in zip(per_match, results) if m
        ],
    }


@app.get("/api/players/{canonical_id}/coaching/report")
def coaching_report(
    canonical_id: str,
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    limit: int = Query(15, ge=1, le=40),
):
    """Full coaching read: metrics -> ranked weakness levers -> narration.
    The narration is LLM (Claude) when ANTHROPIC_API_KEY is configured, else a
    deterministic template. Cached 1h. This is the Coach tab's data source."""
    import coaching as coaching_mod
    import coaching_weakness
    import coaching_narrate
    import coaching_fso
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT display_name FROM players_canonical WHERE canonical_id = %s", (canonical_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "player not found")
        display = row["display_name"]
        # hub_game_id is the demo-addressing key for both data epochs (see the
        # metrics endpoint above). Backfilled for ~99% of old migrated matches.
        cur.execute("""
            SELECT m.hub_game_id AS game_id, m.match_map AS map,
                   p.player_frags AS mf, opp.player_frags AS of,
                   opp.player_name AS opp_name, m.match_date AS date
            FROM players p
            JOIN matches m ON m.match_id = p.match_id AND m.match_mode = %(mode)s
            JOIN players opp ON opp.match_id = p.match_id AND opp.canonical_id <> p.canonical_id
            WHERE p.canonical_id = %(cid)s AND m.hub_game_id IS NOT NULL
            ORDER BY m.match_date DESC LIMIT %(limit)s
        """, {"cid": canonical_id, "mode": mode, "limit": limit})
        matches = cur.fetchall()
        maps = {mr["map"] for mr in matches}
        items_by_map = _items_by_map(cur, maps)
        spawn_locs_by_map = _spawns_by_map(cur, maps)
        fso_benchmark = coaching_fso.load_benchmark(cur, maps)

    per_match, results = [], []
    for mrow in matches:
        per_match.append(coaching_mod.match_metrics(
            mrow["game_id"], display, item_locs=items_by_map.get(mrow["map"])))
        results.append("W" if (mrow["mf"] or 0) > (mrow["of"] or 0) else "L")
    agg = coaching_mod.aggregate(per_match, results)
    weakness = coaching_weakness.detect(agg, mode)

    # First Spawn Optimization — extra lever (time-to-Mega vs the elite spawn_runs
    # reference). Inject into the ranked levers so the narration covers it too.
    fso = coaching_fso.player_fso(matches, display, fso_benchmark, spawn_locs_by_map)
    if fso.get("fso") is not None:
        you, elite = fso["fso"], fso["elite_fso"]
        gap = max(elite - you, 0) / (elite or 1)
        weakness.setdefault("levers", []).append({
            "key": "first_spawn_opt", "label": "First-spawn optimization", "fmt": "pct",
            "win": None, "loss": None, "you": f"{round(you * 100)}%",
            "elite": f"{round(elite * 100)}%", "self_gap": None,
            "below_benchmark": you < elite, "priority": round(gap, 3),
        })
        weakness["levers"].sort(key=lambda x: x["priority"], reverse=True)

    narration = coaching_narrate.narrate(display, mode, weakness)

    # Persist a daily snapshot so the training journal + since-first-report trends
    # accrue automatically. Upsert per (player, mode, day). Best-effort.
    recent_matches = [{
        "game_id": mr["game_id"], "map": mr["map"],
        "result": "W" if (mr["mf"] or 0) > (mr["of"] or 0) else "L",
        "my_frags": mr["mf"], "opp_frags": mr["of"], "opponent": mr["opp_name"],
        # match_date is stored as a string in this DB; isoformat() only on datetimes.
        "date": (mr["date"].isoformat() if hasattr(mr["date"], "isoformat") else mr["date"]),
    } for mr in matches]

    result_payload = {
        "canonical_id": canonical_id,
        "display": display,
        "mode": mode,
        "parsed": len([m for m in per_match if m]),
        "aggregate": agg,
        "weakness": weakness,
        "narration": narration,
        "fso": fso,
        "recent_matches": recent_matches,
    }

    # Persist a daily snapshot (journal/trends) AND the full report JSON, so the
    # Coach tab can durably restore the last analysis on open — across sessions,
    # not just the session-scoped client cache. Best-effort.
    try:
        ic = agg.get("item_control", {})
        wins, losses = agg.get("wins", 0), agg.get("losses", 0)
        snap = {
            "ra_control": ic.get("ra", {}).get("all"),
            "stack_at_kill": agg.get("stack_at_kill", {}).get("all"),
            "pct_stacked": agg.get("pct_stacked", {}).get("all"),
            "armor_first": agg.get("armor_first_rate", {}).get("all"),
            "fso": fso.get("fso"),
            "win_rate": round(wins / (wins + losses), 3) if (wins + losses) else None,
        }
        with pg() as conn:
            cur = conn.cursor()
            _ensure_coaching_tables(cur)
            cur.execute("""
                INSERT INTO coaching_runs (canonical_id, mode, run_date, matches_analyzed,
                    wins, losses, metrics, levers, narration, narration_source, report)
                VALUES (%s,%s,CURRENT_DATE,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (canonical_id, mode, run_date) DO UPDATE SET
                    matches_analyzed=EXCLUDED.matches_analyzed, wins=EXCLUDED.wins,
                    losses=EXCLUDED.losses, metrics=EXCLUDED.metrics, levers=EXCLUDED.levers,
                    narration=EXCLUDED.narration, narration_source=EXCLUDED.narration_source,
                    report=EXCLUDED.report, created_at=now()
            """, (canonical_id, mode, agg.get("matches_analyzed", 0), wins, losses,
                  json.dumps(snap), json.dumps(weakness.get("levers", [])),
                  narration.get("text"), narration.get("source"), json.dumps(result_payload)))
            conn.commit()
    except Exception:
        pass  # journal persistence is best-effort; never break the live report

    return result_payload


@app.get("/api/players/{canonical_id}/coaching/history")
def coaching_history(
    canonical_id: str,
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
):
    """Training-journal history: the persisted daily coaching snapshots for this
    player (oldest→newest), plus since-first-report deltas. Powers the journal +
    progress table. Snapshots are written by the report endpoint."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        _ensure_coaching_tables(cur)
        cur.execute("""
            SELECT run_date, matches_analyzed, wins, losses, metrics, narration_source
            FROM coaching_runs WHERE canonical_id=%s AND mode=%s ORDER BY run_date ASC
        """, (canonical_id, mode))
        rows = cur.fetchall()
        # The most recent FULL report, for durable cross-session restore on open.
        cur.execute("""
            SELECT report FROM coaching_runs
            WHERE canonical_id=%s AND mode=%s AND report IS NOT NULL
            ORDER BY run_date DESC LIMIT 1
        """, (canonical_id, mode))
        lr = cur.fetchone()
    if not rows:
        return {"canonical_id": canonical_id, "mode": mode, "runs": [], "since_first": None, "latest_report": None}
    first, last = rows[0]["metrics"] or {}, rows[-1]["metrics"] or {}
    keys = ["ra_control", "stack_at_kill", "pct_stacked", "armor_first", "fso", "win_rate"]
    since_first = {k: {"from": first.get(k), "to": last.get(k)} for k in keys
                   if first.get(k) is not None or last.get(k) is not None}
    return {
        "canonical_id": canonical_id, "mode": mode,
        "runs": [dict(r, run_date=r["run_date"].isoformat()) for r in reversed(rows)],
        "first_report": rows[0]["run_date"].isoformat(),
        "since_first": since_first,
        "latest_report": lr["report"] if lr else None,
    }


@app.get("/api/players/{canonical_id}/matches/{game_id}/deep-analyze")
def deep_analyze_match(
    canonical_id: str,
    game_id: int,
    response: Response,
    refresh: bool = Query(False, description="recompute even if cached"),
):
    """Deep single-match review (LLM, grounded in a structured timeline). Cached
    in match_analysis — one Claude call per (game, player), since demos are
    immutable. Slow on first run (~parse + LLM); instant when cached."""
    import deep_analyze
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    with pg() as conn:
        cur = conn.cursor()
        _ensure_coaching_tables(cur)
        if not refresh:
            cur.execute("""SELECT game_id, map, result, timeline, analysis, source, model, created_at
                           FROM match_analysis WHERE game_id=%s AND canonical_id=%s""",
                        (game_id, canonical_id))
            cached = cur.fetchone()
            if cached:
                return {"cached": True, **cached, "created_at": cached["created_at"].isoformat()}
        cur.execute("SELECT display_name FROM players_canonical WHERE canonical_id=%s", (canonical_id,))
        prow = cur.fetchone()
        if not prow:
            raise HTTPException(404, "player not found")
        display = prow["display_name"]
        cur.execute("""
            SELECT m.match_map AS map, p.player_frags AS mf, opp.player_frags AS of
            FROM players p
            JOIN matches m ON m.match_id = p.match_id
            JOIN players opp ON opp.match_id = p.match_id AND opp.canonical_id <> p.canonical_id
            WHERE p.canonical_id=%s AND m.hub_game_id=%s LIMIT 1
        """, (canonical_id, game_id))
        mrow = cur.fetchone()
        if not mrow:
            raise HTTPException(404, "match not found for player")
        map_name = mrow["map"]
        result = "W" if (mrow["mf"] or 0) > (mrow["of"] or 0) else "L"
        item_locs = _items_by_map(cur, {map_name}).get(map_name)
        spawn_locs = _spawns_by_map(cur, {map_name}).get(map_name)

    # LLM/parse is slow — run it OUTSIDE the pooled connection (see pg() docstring).
    out = deep_analyze.analyze(game_id, display, map_name, result, spawn_locs, item_locs)
    if not out:
        raise HTTPException(422, "match demo not analyzable")

    try:
        with pg() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO match_analysis (game_id, canonical_id, map, result, timeline, analysis, source, model)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (game_id, canonical_id) DO UPDATE SET
                    timeline=EXCLUDED.timeline, analysis=EXCLUDED.analysis,
                    source=EXCLUDED.source, model=EXCLUDED.model, created_at=now()
            """, (game_id, canonical_id, map_name, result, json.dumps(out["timeline"]),
                  out["analysis"]["text"], out["analysis"].get("source"),
                  out["analysis"].get("model")))
            conn.commit()
    except Exception:
        pass

    return {"cached": False, "game_id": game_id, "map": map_name, "result": result,
            "timeline": out["timeline"], "analysis": out["analysis"]["text"],
            "source": out["analysis"].get("source"), "model": out["analysis"].get("model")}


# ── Player configs + map ─────────────────────────────────────────────────────
# Hardware/config profiles (sens, mouse, binds, geo) seeded from the community
# sheet, per-user editable (admin-gated for now). Powers the profile "Config
# Profile" card and the player map.

@app.get("/api/players/{canonical_id}/config")
def get_player_config(canonical_id: str, response: Response):
    """A player's config profile (sens/mouse/binds/geo). Public read."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT canonical_id, nick, nationality, lat, lon, config, source, updated_at
            FROM player_configs WHERE canonical_id = %s
        """, (canonical_id,))
        row = cur.fetchone()
    if not row:
        return {"canonical_id": canonical_id, "config": None}
    return row


@app.put("/api/players/{canonical_id}/config")
def put_player_config(
    canonical_id: str,
    config: dict = Body(..., embed=True),
    nationality: str | None = Body(default=None, embed=True),
    lat: float | None = Body(default=None, embed=True),
    lon: float | None = Body(default=None, embed=True),
):
    """Edit a player's config profile. OPEN for now — anyone can edit any
    player's config (community-sourced, low-stakes; per-user auth comes with
    federated login). Marks source='user' so the sheet re-seed won't clobber
    a hand-edited row."""
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO player_configs
                (canonical_id, nick, nationality, lat, lon, config, source, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'user', 'public', now())
            ON CONFLICT (canonical_id) WHERE canonical_id IS NOT NULL
            DO UPDATE SET
                nationality = COALESCE(EXCLUDED.nationality, player_configs.nationality),
                lat = COALESCE(EXCLUDED.lat, player_configs.lat),
                lon = COALESCE(EXCLUDED.lon, player_configs.lon),
                config = EXCLUDED.config,
                source = 'user', updated_by = 'public', updated_at = now()
        """, (canonical_id, canonical_id, nationality, lat, lon, json.dumps(config)))
        conn.commit()
    return {"canonical_id": canonical_id, "saved": True}


@app.post("/api/admin/configs/seed-from-sheet")
def admin_seed_configs(authorization: str | None = Header(default=None)):
    """One-shot (re-runnable) config setup: CREATE TABLE player_configs IF NOT
    EXISTS, then import the community config sheet. Runs inside Cloud Run (needs
    the Cloud SQL socket + outbound net to fetch the sheet). Idempotent; never
    clobbers user/admin-edited rows."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_configs (
                canonical_id  TEXT,
                nick          TEXT NOT NULL,
                nationality   TEXT,
                lat           DOUBLE PRECISION,
                lon           DOUBLE PRECISION,
                config        JSONB NOT NULL DEFAULT '{}'::jsonb,
                source        TEXT,
                updated_by    TEXT,
                updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_player_configs_cid
                       ON player_configs(canonical_id) WHERE canonical_id IS NOT NULL""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_player_configs_nick
                       ON player_configs(LOWER(nick))""")
        conn.commit()
    return {
        "step": "seed_player_configs",
        **_run_script("seed_player_configs.py", timeout=120),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/admin/backfill-hub-game-id")
def admin_backfill_hub_game_id(authorization: str | None = Header(default=None)):
    """One-shot (re-runnable) fix for the two-epoch match_id problem: add the
    hub_game_id column, set it = match_id for live-synced (positive) rows, then
    run backfill_hub_game_id.py to correlate the ~141k old migrated rows
    (negative match_id, no sha) to their real hub gameId via demo filename.
    hub_game_id is the demo-addressing key the coaching layer uses. Idempotent.
    Heavy: pages all ~167k hub games, ~3-5 min."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS hub_game_id BIGINT")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_matches_hub_game_id
                       ON matches(hub_game_id) WHERE hub_game_id IS NOT NULL""")
        cur.execute("UPDATE matches SET hub_game_id = match_id WHERE match_id > 0 AND hub_game_id IS NULL")
        conn.commit()
    return {
        "step": "backfill_hub_game_id",
        **_run_script("backfill_hub_game_id.py", timeout=900),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/admin/maps/seed-entities")
def admin_seed_map_entities(authorization: str | None = Header(default=None)):
    """Idempotent: add map_annotations.entities column + load the BSP map-entity
    corpus (spawns + items + paired teleporters) from the mvd_analyzer read-dmg
    branch. Powers first-item-intent coaching + the upgraded annotator. ~110
    maps with data, pulls from GitHub raw, ~1-2 min."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("ALTER TABLE map_annotations ADD COLUMN IF NOT EXISTS entities JSONB")
        conn.commit()
    return {
        "step": "seed_map_entities",
        **_run_script("seed_map_entities.py", timeout=300),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/admin/maps/{map_name}/extract-spawn-runs")
def admin_extract_spawn_runs(map_name: str, authorization: str | None = Header(default=None)):
    """Idempotent: build/refresh the first-spawn training runs for ONE map (top-5
    players, coverage-driven). Per-map so it fits Cloud Run's 60-min cap — the
    full 9-map build is run map-by-map (or locally). Pulls windowed 13ms buckets
    + frags from mvd-api, snaps spawns, classifies outcome, stores paths in
    spawn_runs. ~5-12 min/map depending on coverage."""
    _check_admin_auth(authorization)
    return {
        "step": "extract_spawn_runs",
        "map": map_name,
        **_run_script("extract_spawn_runs.py", "--map", map_name, timeout=3000),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Map annotations (spawn points + teleports) ──────────────────────────────────
# Backs the spawn/tele annotator. Geometry (loc triangle meshes) is cached in
# map_annotations.geometry by seed_map_geometry.py; spawns/teles are authored
# via the annotator UI. `locked` gates writes once a map's data is confirmed
# complete — when locked, the map serves read-only (the path to public,
# community-sourced annotation once locking is trusted).


@app.get("/api/maps/annotations")
def list_map_annotations(response: Response):
    """Index of every map that has cached geometry, with spawn/tele counts +
    lock status. Powers the annotator's map picker. Public, cacheable."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT map,
                   jsonb_array_length(spawns) AS spawn_count,
                   jsonb_array_length(teles)  AS tele_count,
                   (geometry IS NOT NULL)     AS has_geometry,
                   COALESCE(jsonb_array_length(geometry->'locs'), 0) AS loc_count,
                   locked, updated_by, updated_at
            FROM map_annotations
            ORDER BY map
        """)
        return {"maps": cur.fetchall()}


@app.get("/api/maps/{map_name}/annotations")
def get_map_annotations(map_name: str, response: Response):
    """Full annotation payload for one map: cached geometry + spawns + teles +
    lock status. The annotator loads this to render and edit. Public read."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT map, spawns, teles, geometry, entities, locked, updated_by, updated_at
            FROM map_annotations WHERE map = %s
        """, (map_name,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"no annotations for map '{map_name}'")
    return row


@app.put("/api/maps/{map_name}/annotations")
def put_map_annotations(
    map_name: str,
    authorization: str | None = Header(default=None),
    spawns: list = Body(..., embed=True),
    teles: list = Body(default=[], embed=True),
):
    """Admin write: replace a map's spawns + teles. Blocked (409) if the map is
    locked. Geometry is never written here (it's seeded separately). Creates
    the row if the map doesn't exist yet (geometry stays null until seeded)."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT locked FROM map_annotations WHERE map = %s", (map_name,))
        row = cur.fetchone()
        if row and row["locked"]:
            raise HTTPException(409, f"map '{map_name}' is locked; unlock before editing")
        cur.execute("""
            INSERT INTO map_annotations (map, spawns, teles, updated_by, updated_at)
            VALUES (%s, %s::jsonb, %s::jsonb, 'annotator', now())
            ON CONFLICT (map) DO UPDATE SET
                spawns = EXCLUDED.spawns,
                teles = EXCLUDED.teles,
                updated_by = 'annotator',
                updated_at = now()
        """, (map_name, json.dumps(spawns), json.dumps(teles)))
        conn.commit()
    return {"map": map_name, "spawns": len(spawns), "teles": len(teles), "saved": True}


@app.post("/api/admin/maps/{map_name}/lock")
def set_map_lock(
    map_name: str,
    locked: bool = Query(...),
    authorization: str | None = Header(default=None),
):
    """Admin: set/clear the locked flag on a map. Locked maps serve read-only
    via PUT (409). This is the gate we flip once a map's spawn+tele data is
    confirmed complete, and eventually the basis for public community editing
    of only the still-unlocked maps."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE map_annotations SET locked = %s, updated_at = now() WHERE map = %s",
                    (locked, map_name))
        if cur.rowcount == 0:
            raise HTTPException(404, f"no annotations for map '{map_name}'")
        conn.commit()
    return {"map": map_name, "locked": locked}


# ── First-spawn runs (training data for the spawn-optimization dashboard) ────────
# spawn_runs holds, per (map, top-5 player, game), the opening-life path off their
# first spawn plus a 2-dim outcome label (items secured × opening result). Built
# by extract_spawn_runs.py. The dashboard picks a player + map and replays 3-4
# example runs per spawn point, filterable by the enemy's spawn. Where the chosen
# player lacks ≥3 examples for a spawn, we PAD from the other top-5 players on that
# map (attributed via `player`/`padded`) so every spawn has enough material.

SPAWN_TARGET_PER_SPAWN = 3


def _spawn_labels(spawns_json) -> list:
    """Spawn loc labels for a map, with index fallbacks (S1..Sn) for unlabeled
    spawns — matches extract_spawn_runs.label_spawns so frontend pills line up
    with stored own_spawn values even on un-annotated maps (e.g. metron)."""
    out = []
    for i, s in enumerate(spawns_json or []):
        out.append(s.get("loc") or f"S{i + 1}")
    return out


@app.get("/api/maps/{map_name}/spawn-runs")
def list_map_spawn_run_players(map_name: str, response: Response):
    """Which players have first-spawn training data on this map, with run counts.
    Powers the dashboard's player picker. Public, cacheable."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT sr.player,
                   COALESCE(pc.display_name, sr.player) AS display,
                   MIN(sr.rank_on_map) AS rank_on_map,
                   COUNT(*) AS runs,
                   COUNT(DISTINCT sr.own_spawn) AS spawns_covered
            FROM spawn_runs sr
            LEFT JOIN players_canonical pc ON pc.canonical_id = sr.player
            WHERE sr.map = %s
            GROUP BY sr.player, pc.display_name
            ORDER BY rank_on_map NULLS LAST, runs DESC
        """, (map_name,))
        players = cur.fetchall()
        cur.execute("SELECT entities->'spawns' AS s FROM map_annotations WHERE map = %s", (map_name,))
        row = cur.fetchone()
    if not players:
        raise HTTPException(404, f"no spawn runs for map '{map_name}'")
    spawns = _spawn_labels(row["s"] if row else None)
    return {"map": map_name, "spawns": spawns, "players": players}


@app.get("/api/maps/{map_name}/spawn-runs/{player}")
def get_player_spawn_runs(
    map_name: str, player: str, response: Response,
    per_spawn: int = Query(4, ge=1, le=12, description="max examples returned per spawn point"),
):
    """The selected player's first-spawn runs on this map, grouped by own spawn.
    Each spawn returns up to `per_spawn` example runs (the player's own first,
    then PADDED from other top-5 players on the map when the player has <target),
    newest first. Run rows are light (no path arrays) — fetch a path on demand via
    the /path endpoint. Client filters by enemy_spawn. Public, cacheable."""
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    cols = ("game_id, own_spawn, enemy_spawn, items_outcome, opening_result, "
            "first_kill_ms, first_death_ms, duration_s, player, rank_on_map, match_date, "
            "(enemy_path IS NOT NULL) AS has_enemy_path")
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT entities->'spawns' AS s FROM map_annotations WHERE map = %s", (map_name,))
        row = cur.fetchone()
        spawns = _spawn_labels(row["s"] if row else None)
        # The player's own runs.
        cur.execute(f"""SELECT {cols} FROM spawn_runs
                        WHERE map=%s AND player=%s ORDER BY own_spawn, match_date DESC NULLS LAST""",
                    (map_name, player))
        own = cur.fetchall()
        # Pool from the other top-5 players, for padding sparse spawns.
        cur.execute(f"""SELECT {cols} FROM spawn_runs
                        WHERE map=%s AND player<>%s ORDER BY own_spawn, rank_on_map, match_date DESC NULLS LAST""",
                    (map_name, player))
        pool = cur.fetchall()
    if not own and not pool:
        raise HTTPException(404, f"no spawn runs for '{player}' on '{map_name}'")

    own_by_spawn: dict = {}
    for r in own:
        r["padded"] = False
        own_by_spawn.setdefault(r["own_spawn"], []).append(r)
    pool_by_spawn: dict = {}
    for r in pool:
        r["padded"] = True
        pool_by_spawn.setdefault(r["own_spawn"], []).append(r)

    spawn_keys = spawns or sorted(set(own_by_spawn) | set(pool_by_spawn))
    groups = []
    for sp in spawn_keys:
        runs = list(own_by_spawn.get(sp, []))
        own_n = len(runs)
        if own_n < SPAWN_TARGET_PER_SPAWN:
            runs += pool_by_spawn.get(sp, [])[: per_spawn - own_n]
        runs = runs[:per_spawn]
        if not runs:
            continue
        groups.append({
            "spawn": sp,
            "own_count": own_n,
            "padded_count": sum(1 for r in runs if r["padded"]),
            "runs": runs,
        })
    return {"map": map_name, "player": player, "spawns": spawn_keys, "groups": groups}


@app.get("/api/maps/{map_name}/spawn-runs/{player}/{game_id}/path")
def get_spawn_run_path(map_name: str, player: str, game_id: int, response: Response):
    """Full replay payload for one run: the player's path (and enemy path, when
    captured) as [[x,y,z],...] per 13ms bucket, plus spawn + outcome metadata.
    The `player` here is the run's actual player (which may be a padding player),
    so padded runs resolve correctly. Public, cacheable (immutable training row)."""
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT map, player, rank_on_map, game_id, own_spawn, enemy_spawn,
                              items_outcome, opening_result, first_kill_ms, first_death_ms,
                              duration_s, path, enemy_path
                       FROM spawn_runs WHERE map=%s AND player=%s AND game_id=%s""",
                    (map_name, player, game_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"no spawn run {game_id} for '{player}' on '{map_name}'")
    return row


# ── Speakeasy 2v2 ladder ─────────────────────────────────────────────────────
# Standings + movement engine in ladder.py. Reads are public; writes (create
# ladder, seed teams) are admin for now — captain self-serve challenge/report
# (Discord-auth gated) lands next.

def _enrich_members(cur, teams):
    """Replace member canonical_ids with {id, display} for the UI."""
    ids = sorted({m for t in teams for m in (t.get("members") or [])})
    names = {}
    if ids:
        cur.execute("SELECT canonical_id, display_name FROM players_canonical WHERE canonical_id = ANY(%s)", (ids,))
        names = {r["canonical_id"]: r["display_name"] for r in cur.fetchall()}
    for t in teams:
        t["members"] = [{"id": m, "display": names.get(m, m)} for m in (t.get("members") or [])]
    return teams


@app.get("/api/ladder")
def ladder_list():
    """Active ladders (summary). Public."""
    import ladder as _ladder
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT id, name, season, team_size, map_pool, rules, status FROM ladders WHERE status='active' ORDER BY id")
        return {"ladders": cur.fetchall()}


@app.get("/api/ladder/{ladder_id}")
def ladder_detail(ladder_id: int, response: Response):
    """Full ladder: ranked teams, King of the Hill (+ weeks held), open challenges.
    Short cache — it moves on writes but reads should stay snappy."""
    import ladder as _ladder
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=300"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT id, name, season, team_size, map_pool, rules, status FROM ladders WHERE id=%s", (ladder_id,))
        lad = cur.fetchone()
        if not lad:
            raise HTTPException(404, "ladder not found")
        teams = _enrich_members(cur, _ladder.standings(cur, ladder_id))
        # Loss cooldown: a team that lost in the last `loss_cooldown_days` can't
        # issue challenges until cooldown_until. Attach it so the board can show a
        # countdown + disable that team's challenge buttons. A win since that loss
        # clears it (winning a defense lifts cooldown) — so only count it when the
        # team's latest decisive result is a loss.
        cd_days = (lad.get("rules") or {}).get("loss_cooldown_days", 7)
        cur.execute("""SELECT t.id,
                              max(m.played_at) FILTER (WHERE m.winner_id IS NOT NULL AND m.winner_id <> t.id) AS last_loss,
                              max(m.played_at) FILTER (WHERE m.winner_id = t.id) AS last_win
                       FROM ladder_teams t
                       LEFT JOIN ladder_matches m ON (m.team_a_id=t.id OR m.team_b_id=t.id) AND m.ladder_id=%s
                       WHERE t.ladder_id=%s GROUP BY t.id""", (ladder_id, ladder_id))
        cd = {}
        for r in cur.fetchall():
            if r["last_loss"] and not (r["last_win"] and r["last_win"] > r["last_loss"]):
                until = r["last_loss"] + timedelta(days=cd_days)
                if until > datetime.now(timezone.utc):
                    cd[r["id"]] = until.isoformat()
        for t in teams:
            t["cooldown_until"] = cd.get(t["id"])
        # Match record (W-L) + game/map record (W-L) per team, from reported matches.
        cur.execute("SELECT team_a_id, team_b_id, winner_id, maps FROM ladder_matches WHERE ladder_id=%s", (ladder_id,))
        rec = {}
        for r in cur.fetchall():
            a, b = r["team_a_id"], r["team_b_id"]
            for tid in (a, b):
                rec.setdefault(tid, {"mw": 0, "ml": 0, "gw": 0, "gl": 0})
            if r["winner_id"]:
                rec[r["winner_id"]]["mw"] += 1
                rec[b if r["winner_id"] == a else a]["ml"] += 1
            for mp in (r["maps"] or []):
                af, bf = mp.get("a_frags"), mp.get("b_frags")
                if af is None or bf is None:
                    continue
                if af > bf:
                    rec[a]["gw"] += 1; rec[b]["gl"] += 1
                elif bf > af:
                    rec[b]["gw"] += 1; rec[a]["gl"] += 1
        for t in teams:
            r = rec.get(t["id"], {"mw": 0, "ml": 0, "gw": 0, "gl": 0})
            t["match_w"], t["match_l"] = r["mw"], r["ml"]
            t["game_w"], t["game_l"] = r["gw"], r["gl"]
        # King of the Hill: current rung-1 team + how long they've held it.
        koth = None
        top = next((t for t in teams if t.get("rung") == 1), None)
        if top:
            cur.execute("""SELECT at FROM ladder_movements WHERE ladder_id=%s AND team_id=%s AND to_rung=1
                           ORDER BY at DESC LIMIT 1""", (ladder_id, top["id"]))
            mv = cur.fetchone()
            since = mv["at"] if mv else None
            weeks = None
            if since:
                weeks = max(0, int((datetime.now(timezone.utc) - since).days // 7))
            koth = {"team_id": top["id"], "name": top["name"],
                    "since": since.isoformat() if since else None, "weeks": weeks}
        cur.execute("""
            SELECT c.id, c.challenger_id, c.challenged_id, c.rungs_up, c.status, c.deadline, c.created_at,
                   c.proposed, c.proposed_by, c.agreed_at, c.server,
                   ca.name AS challenger, cd.name AS challenged
            FROM ladder_challenges c
            JOIN ladder_teams ca ON ca.id=c.challenger_id
            JOIN ladder_teams cd ON cd.id=c.challenged_id
            WHERE c.ladder_id=%s AND c.status IN ('open','scheduled')
            ORDER BY c.created_at DESC
        """, (ladder_id,))
        challenges = [dict(r,
                           deadline=r["deadline"].isoformat() if r["deadline"] else None,
                           created_at=r["created_at"].isoformat() if r["created_at"] else None,
                           agreed_at=r["agreed_at"].isoformat() if r["agreed_at"] else None,
                           proposed=r["proposed"] or [])
                      for r in cur.fetchall()]
    return {"ladder": lad, "teams": teams, "koth": koth, "challenges": challenges}


@app.post("/api/admin/ladder/create")
def admin_ladder_create(authorization: str | None = Header(default=None),
                        name: str = Body(..., embed=True),
                        map_pool: list = Body(default=[], embed=True),
                        rules: dict = Body(default={}, embed=True),
                        team_size: int = Body(default=2, embed=True),
                        season: str | None = Body(default=None, embed=True)):
    """Create a ladder (ladder-admin). Idempotent on name."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""INSERT INTO ladders (name, season, team_size, map_pool, rules)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING RETURNING id""",
                    (name, season, team_size, json.dumps(map_pool), json.dumps(rules)))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT id FROM ladders WHERE name=%s", (name,))
            row = cur.fetchone()
        conn.commit()
    return {"ladder_id": row["id"], "name": name}


@app.post("/api/admin/ladder/{ladder_id}/open")
def admin_ladder_open(ladder_id: int, authorization: str | None = Header(default=None),
                      open: bool = Body(..., embed=True)):
    """Open/close the ladder for player challenging (ladder-admin). Stored in
    rules.open. Closed = pre-launch: players can't challenge, board shows a
    'not open yet' banner; admins can still arrange challenges for testing."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("UPDATE ladders SET rules = COALESCE(rules,'{}'::jsonb) || %s::jsonb WHERE id=%s RETURNING rules",
                    (json.dumps({"open": bool(open)}), ladder_id))
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "ladder not found")
    return {"ladder_id": ladder_id, "open": bool(open)}


@app.post("/api/admin/ladder/{ladder_id}/teams")
def admin_ladder_add_team(ladder_id: int, authorization: str | None = Header(default=None),
                         name: str = Body(..., embed=True),
                         members: list = Body(default=[], embed=True),
                         rung: int | None = Body(default=None, embed=True)):
    """Add/seed a team (ladder-admin). rung=N seeds at that rung; omit → bottom."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""INSERT INTO ladder_teams (ladder_id, name, members, rung)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (ladder_id, name) DO UPDATE SET members=EXCLUDED.members
                       RETURNING id""", (ladder_id, name, json.dumps(members), rung))
        tid = cur.fetchone()["id"]
        if rung is not None:
            cur.execute("""INSERT INTO ladder_movements (ladder_id, team_id, to_rung, reason)
                           VALUES (%s,%s,%s,'seed')""", (ladder_id, tid, rung))
        else:
            _ladder.place_new_team(cur, ladder_id, tid)
        conn.commit()
    return {"team_id": tid, "name": name}


def _norm_tag(tag: str | None) -> str | None:
    """QW clan tag: trimmed, max 6 chars (Peter said 2–4, allow a little slack).
    Empty → None."""
    if not tag:
        return None
    t = tag.strip()[:6]
    return t or None


@app.post("/api/ladder/{ladder_id}/team/signup")
def ladder_team_signup(ladder_id: int, authorization: str | None = Header(default=None),
                       name: str = Body(..., embed=True),
                       tag: str | None = Body(default=None, embed=True),
                       teammate_canonical_id: str | None = Body(default=None, embed=True),
                       logo: str | None = Body(default=None, embed=True)):
    """A captain registers a team: themselves + a teammate (by canonical_id),
    a team name, and an optional logo (data URI). Lands as PENDING for admin
    approval — never auto-placed. Requires a linked player profile."""
    import ladder as _ladder
    user = _current_user(authorization, required=True)
    cid = user.get("canonical_id")
    if not cid:
        raise HTTPException(403, "link your player profile first")
    members = [cid]
    if teammate_canonical_id and teammate_canonical_id != cid:
        members.append(teammate_canonical_id)
    logo_bytes, logo_type = _parse_logo_data_uri(logo)
    tag = _norm_tag(tag)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT 1 FROM ladders WHERE id=%s AND status='active'", (ladder_id,))
        if not cur.fetchone():
            raise HTTPException(404, "ladder not found")
        # validate teammate exists
        if teammate_canonical_id:
            cur.execute("SELECT 1 FROM players_canonical WHERE canonical_id=%s", (teammate_canonical_id,))
            if not cur.fetchone():
                raise HTTPException(404, "teammate player not found")
        try:
            cur.execute("""INSERT INTO ladder_teams
                           (ladder_id, name, tag, members, rung, active, status, created_by, logo, logo_type)
                           VALUES (%s,%s,%s,%s,NULL,FALSE,'pending',%s,%s,%s) RETURNING id""",
                        (ladder_id, name, tag, json.dumps(members), user["discord_id"],
                         psycopg2.Binary(logo_bytes) if logo_bytes else None, logo_type))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(409, "that team name is already taken")
        tid = cur.fetchone()["id"]
        # resolve member display names for the notification
        names = []
        if members:
            cur.execute("SELECT canonical_id, display_name FROM players_canonical WHERE canonical_id = ANY(%s)", (members,))
            dn = {r["canonical_id"]: r["display_name"] for r in cur.fetchall()}
            names = [dn.get(m, m) for m in members]
        conn.commit()
    try:
        import notify
        notify.team_signup(name, tag, names, pending=True)
    except Exception:
        pass
    return {"team_id": tid, "name": name, "status": "pending"}


@app.post("/api/ladder/team/{team_id}/edit")
def ladder_team_edit(team_id: int, authorization: str | None = Header(default=None),
                     name: str | None = Body(default=None, embed=True),
                     tag: str | None = Body(default=None, embed=True),
                     teammate_canonical_id: str | None = Body(default=None, embed=True),
                     members: list | None = Body(default=None, embed=True),
                     logo: str | None = Body(default=None, embed=True),
                     remove_logo: bool = Body(default=False, embed=True)):
    """Edit a team's name/tag/roster/logo. Allowed for a roster member of the
    team (captain self-serve) OR any ladder admin (SYNC_SECRET or is_admin).
    Admins may pass `members` to set the full roster (assign player profiles
    after registration); captains use `teammate_canonical_id`. Only provided
    fields change."""
    import ladder as _ladder
    # Admins authenticate via SYNC_SECRET (god panel) or Discord is_admin;
    # captains via their Discord JWT (must be on the roster).
    expected = os.environ.get("SYNC_SECRET")
    is_admin, user = False, None
    if expected and authorization == f"Bearer {expected}":
        is_admin = True
    else:
        user = _current_user(authorization, required=True)
        is_admin = bool(user.get("is_admin"))
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT id, ladder_id, members, created_by FROM ladder_teams WHERE id=%s", (team_id,))
        t = cur.fetchone()
        if not t:
            raise HTTPException(404, "team not found")
        existing = list(t["members"] or [])
        if not is_admin:
            cid = user.get("canonical_id")
            if not (user["discord_id"] == t["created_by"] or (cid and cid in existing)):
                raise HTTPException(403, "you can only edit your own team")
        sets, vals = [], []
        if name is not None and name.strip():
            sets.append("name=%s"); vals.append(name.strip())
        if tag is not None:
            sets.append("tag=%s"); vals.append(_norm_tag(tag))
        # Admin path: set the whole roster verbatim. Captain path: replace the
        # teammate slot, keeping the captain (first member).
        new_members = None
        if members is not None and is_admin:
            new_members = []
            for m in members:
                m = (m or "").strip()
                if not m or m in new_members:
                    continue
                cur.execute("SELECT 1 FROM players_canonical WHERE canonical_id=%s", (m,))
                if not cur.fetchone():
                    raise HTTPException(404, f"player not found: {m}")
                new_members.append(m)
        elif teammate_canonical_id is not None:
            cap = existing[0] if existing else (user.get("canonical_id") if user else None)
            new_members = [cap] if cap else []
            if teammate_canonical_id and teammate_canonical_id != cap:
                cur.execute("SELECT 1 FROM players_canonical WHERE canonical_id=%s", (teammate_canonical_id,))
                if not cur.fetchone():
                    raise HTTPException(404, "teammate player not found")
                new_members.append(teammate_canonical_id)
        if new_members is not None:
            sets.append("members=%s"); vals.append(json.dumps(new_members))
        if remove_logo:
            sets.append("logo=NULL"); sets.append("logo_type=NULL")
        elif logo:
            lb, lt = _parse_logo_data_uri(logo)
            sets.append("logo=%s"); vals.append(psycopg2.Binary(lb))
            sets.append("logo_type=%s"); vals.append(lt)
        if not sets:
            raise HTTPException(400, "nothing to update")
        vals.append(team_id)
        try:
            cur.execute(f"UPDATE ladder_teams SET {', '.join(sets)} WHERE id=%s", vals)
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(409, "that team name is already taken")
        conn.commit()
    return {"team_id": team_id, "updated": True}


@app.get("/api/admin/ladder/{ladder_id}/teams/pending")
def admin_ladder_pending(ladder_id: int, authorization: str | None = Header(default=None)):
    """Pending team signups awaiting approval (ladder-admin)."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT id, name, tag, members, created_by, created_at,
                              (logo IS NOT NULL) AS has_logo
                       FROM ladder_teams
                       WHERE ladder_id=%s AND status='pending'
                       ORDER BY created_at""", (ladder_id,))
        teams = [dict(r, created_at=r["created_at"].isoformat() if r["created_at"] else None)
                 for r in cur.fetchall()]
        teams = _enrich_members(cur, teams)
    return {"pending": teams}


@app.post("/api/admin/ladder/{ladder_id}/reorder")
def admin_ladder_reorder(ladder_id: int, authorization: str | None = Header(default=None),
                         order: list = Body(..., embed=True)):
    """Set the rung order directly (admin drag-and-drop). `order` is the list of
    team_ids top-to-bottom → rungs 1..N. Ladder-admin."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        # validate the ids belong to this ladder + are active
        cur.execute("SELECT id, rung FROM ladder_teams WHERE ladder_id=%s AND active", (ladder_id,))
        valid = {r["id"]: r["rung"] for r in cur.fetchall()}
        ids = [int(t) for t in order if int(t) in valid]
        if set(ids) != set(valid):
            raise HTTPException(400, "order must include exactly the active teams")
        for i, tid in enumerate(ids, 1):
            if valid[tid] != i:
                cur.execute("UPDATE ladder_teams SET rung=%s WHERE id=%s", (i, tid))
                cur.execute("""INSERT INTO ladder_movements (ladder_id, team_id, from_rung, to_rung, reason)
                               VALUES (%s,%s,%s,%s,'admin')""", (ladder_id, tid, valid[tid], i))
        conn.commit()
    return {"ladder_id": ladder_id, "order": ids}


@app.post("/api/admin/ladder/team/{team_id}/approve")
def admin_ladder_team_approve(team_id: int, authorization: str | None = Header(default=None)):
    """Approve a pending team → activate it + place at the bottom rung (ladder-admin)."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT id, ladder_id, name, status FROM ladder_teams WHERE id=%s", (team_id,))
        t = cur.fetchone()
        if not t:
            raise HTTPException(404, "team not found")
        if t["status"] != "pending":
            raise HTTPException(409, "team is not pending")
        cur.execute("UPDATE ladder_teams SET status='active', active=TRUE WHERE id=%s", (team_id,))
        rung = _ladder.place_new_team(cur, t["ladder_id"], team_id)
        conn.commit()
    try:
        import notify
        notify.send(embed={"title": "✅ Team approved",
                           "description": f"**{t['name']}** joins the ladder at rung {rung}.",
                           "color": 0x22C55E})
    except Exception:
        pass
    return {"team_id": team_id, "status": "active", "rung": rung}


@app.post("/api/admin/ladder/team/{team_id}/reject")
def admin_ladder_team_reject(team_id: int, authorization: str | None = Header(default=None)):
    """Reject a pending team signup (ladder-admin)."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("UPDATE ladder_teams SET status='rejected', active=FALSE WHERE id=%s AND status='pending' RETURNING name",
                    (team_id,))
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "no pending team with that id")
    return {"team_id": team_id, "status": "rejected"}


@app.get("/api/ladder/team/{team_id}")
def ladder_team_get(team_id: int):
    """Single team (enriched members + tag + has_logo + status). Public — used to
    open Team Settings (works for pending teams not yet on the board)."""
    import ladder as _ladder
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT id, ladder_id, name, tag, members, rung, status,
                              (logo IS NOT NULL) AS has_logo
                       FROM ladder_teams WHERE id=%s""", (team_id,))
        t = cur.fetchone()
        if not t:
            raise HTTPException(404, "team not found")
        t = _enrich_members(cur, [dict(t)])[0]
    return t


@app.get("/api/ladder/team/{team_id}/logo")
def ladder_team_logo(team_id: int):
    """Serve a team's logo image (public). Long browser cache — logos rarely change."""
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("SELECT logo, logo_type FROM ladder_teams WHERE id=%s", (team_id,))
        row = cur.fetchone()
    if not row or not row["logo"]:
        raise HTTPException(404, "no logo")
    data = bytes(row["logo"])
    return Response(content=data, media_type=row["logo_type"] or "image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


def _team_row(cur, ladder_id, team_id):
    cur.execute("SELECT id, name, members, rung, active FROM ladder_teams WHERE id=%s AND ladder_id=%s",
                (team_id, ladder_id))
    return cur.fetchone()


# ── Ladder stats (team stats, map stats, match deep-dive) ────────────────────
# All derive from ladder_matches (maps:[{map,a_frags,b_frags,hub_game_id}]) and
# the per-player KTX stats already ingested into players/matches.

@app.get("/api/ladder/{ladder_id}/matches")
def ladder_matches_list(ladder_id: int, response: Response, limit: int = Query(50, le=200)):
    """Reported matches for a ladder (newest first) — powers the reports list and
    links into the match deep-dive."""
    import ladder as _ladder
    response.headers["Cache-Control"] = "public, max-age=60"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT m.id, m.team_a_id, m.team_b_id, m.score_a, m.score_b, m.winner_id,
                              m.maps, m.played_at, ta.name AS a_name, tb.name AS b_name,
                              (ta.logo IS NOT NULL) AS a_logo, (tb.logo IS NOT NULL) AS b_logo
                       FROM ladder_matches m
                       JOIN ladder_teams ta ON ta.id=m.team_a_id
                       JOIN ladder_teams tb ON tb.id=m.team_b_id
                       WHERE m.ladder_id=%s ORDER BY m.played_at DESC NULLS LAST, m.id DESC LIMIT %s""",
                    (ladder_id, limit))
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["played_at"] = d["played_at"].isoformat() if d.get("played_at") else None
            out.append(d)
    return {"matches": out}


def _pct(num, den):
    return round(100.0 * num / den, 1) if den else 0.0


@app.get("/api/ladder/match/{match_id}")
def ladder_match_detail(match_id: int, response: Response):
    """Single-match deep-dive: per-map scorelines + per-player KTX stats for each
    map (joined via the map's hub_game_id)."""
    import ladder as _ladder
    response.headers["Cache-Control"] = "public, max-age=20"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT m.*, ta.name AS a_name, tb.name AS b_name,
                              (ta.logo IS NOT NULL) AS a_logo, (tb.logo IS NOT NULL) AS b_logo
                       FROM ladder_matches m
                       JOIN ladder_teams ta ON ta.id=m.team_a_id
                       JOIN ladder_teams tb ON tb.id=m.team_b_id WHERE m.id=%s""", (match_id,))
        m = cur.fetchone()
        if not m:
            raise HTTPException(404, "match not found")
        maps = list(m["maps"] or [])
        out_maps = []
        for mp in maps:
            hid = mp.get("hub_game_id")
            players = []
            if hid:
                cur.execute("""SELECT p.canonical_id, p.player_name,
                                      p.player_frags AS frags, p.player_deaths AS deaths,
                                      p.player_damage_given AS dmg, p.player_ra_taken AS ra,
                                      p.player_ya_taken AS ya, p.player_quad_taken AS quad,
                                      p.player_rl_attacks AS rl_a, p.player_rl_directs AS rl_h,
                                      p.player_lg_attacks AS lg_a, p.player_lg_hits AS lg_h,
                                      COALESCE(pc.display_name, p.player_name) AS display
                               FROM players p
                               JOIN matches mt ON mt.match_id = p.match_id
                               LEFT JOIN players_canonical pc ON pc.canonical_id = p.canonical_id
                               WHERE mt.hub_game_id = %s
                               ORDER BY p.player_frags DESC NULLS LAST""", (hid,))
                for r in cur.fetchall():
                    players.append({
                        "name": r["display"] or r["player_name"], "canonical_id": r["canonical_id"],
                        "frags": r["frags"], "deaths": r["deaths"],
                        "eff": _pct(r["frags"] or 0, (r["frags"] or 0) + (r["deaths"] or 0)),
                        "rl": _pct(r["rl_h"] or 0, r["rl_a"] or 0), "lg": _pct(r["lg_h"] or 0, r["lg_a"] or 0),
                        "ra": r["ra"], "ya": r["ya"], "quad": r["quad"], "dmg": r["dmg"],
                    })
            out_maps.append({"map": mp.get("map"), "a_frags": mp.get("a_frags"),
                             "b_frags": mp.get("b_frags"), "hub_game_id": hid, "players": players})
    return {
        "id": m["id"], "a_name": m["a_name"], "b_name": m["b_name"],
        "a_id": m["team_a_id"], "b_id": m["team_b_id"], "a_logo": m["a_logo"], "b_logo": m["b_logo"],
        "score_a": m["score_a"], "score_b": m["score_b"], "winner_id": m["winner_id"],
        "played_at": m["played_at"].isoformat() if m.get("played_at") else None,
        "maps": out_maps,
    }


@app.get("/api/ladder/{ladder_id}/map-stats")
def ladder_map_stats(ladder_id: int, response: Response):
    """Map analytics over reported maps: most played, first pick, decider, closest,
    blowouts, high scoring."""
    import ladder as _ladder
    response.headers["Cache-Control"] = "public, max-age=20"
    from collections import Counter
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT m.maps, ta.name AS a, tb.name AS b
                       FROM ladder_matches m
                       JOIN ladder_teams ta ON ta.id=m.team_a_id
                       JOIN ladder_teams tb ON tb.id=m.team_b_id WHERE m.ladder_id=%s""", (ladder_id,))
        rows = cur.fetchall()
    played, firstpick, decider = Counter(), Counter(), Counter()
    totals, counts = Counter(), Counter()    # for avg combined frags
    games = []                               # for closest/blowouts
    total_maps = 0
    for r in rows:
        maps = list(r["maps"] or [])
        aw = bw = 0
        clinched = False   # decider = the CLINCHING map (a team's 2nd win), not the
                           # last one played — dead-rubber games after the clinch
                           # still count for played/scoring but aren't the decider.
        for i, mp in enumerate(maps):
            name = mp.get("map")
            if not name:
                continue
            a, b = mp.get("a_frags"), mp.get("b_frags")
            played[name] += 1; total_maps += 1
            if i == 0:
                firstpick[name] += 1
            if a is not None and b is not None:
                totals[name] += (a + b); counts[name] += 1
                games.append({"map": name, "a": a, "b": b, "diff": abs(a - b),
                              "total": a + b, "label": f"{r['a']} vs {r['b']}"})
                if not clinched:
                    if a > b:
                        aw += 1
                    elif b > a:
                        bw += 1
                    if aw == 2 or bw == 2:
                        decider[name] += 1; clinched = True
    def top(counter, n=6):
        return [{"map": k, "count": v, "pct": _pct(v, total_maps)} for k, v in counter.most_common(n)]
    high = sorted(((k, round(totals[k] / counts[k], 1)) for k in counts), key=lambda x: -x[1])
    return {
        "total_maps": total_maps,
        "most_played": top(played),
        "first_pick": [{"map": k, "count": v, "pct": _pct(v, sum(firstpick.values()))} for k, v in firstpick.most_common(6)],
        "decider": [{"map": k, "count": v, "pct": _pct(v, sum(decider.values()))} for k, v in decider.most_common(6)],
        "closest": sorted(games, key=lambda g: g["diff"])[:5],
        "blowouts": sorted(games, key=lambda g: -g["diff"])[:5],
        "high_scoring": [{"map": k, "avg": v} for k, v in high[:6]],
    }


@app.get("/api/ladder/{ladder_id}/team-stats")
def ladder_team_stats(ladder_id: int, response: Response):
    """Per-team, per-map averages from the rostered players' KTX stats across the
    team's reported matches. Mirrors thebig4's Team Statistics table."""
    import ladder as _ladder
    response.headers["Cache-Control"] = "public, max-age=20"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        # active teams + rosters
        cur.execute("""SELECT id, name, tag, members, (logo IS NOT NULL) AS has_logo
                       FROM ladder_teams WHERE ladder_id=%s AND status='active'""", (ladder_id,))
        teams = cur.fetchall()
        # hub_game_ids per team from their matches
        cur.execute("""SELECT team_a_id, team_b_id, hub_game_ids FROM ladder_matches WHERE ladder_id=%s""", (ladder_id,))
        team_games = {}
        for r in cur.fetchall():
            for tid in (r["team_a_id"], r["team_b_id"]):
                team_games.setdefault(tid, set()).update(int(g) for g in (r["hub_game_ids"] or []) if g is not None)

        out = []
        for t in teams:
            roster = list(t["members"] or [])
            hub_ids = list(team_games.get(t["id"], set()))
            row = {"team_id": t["id"], "name": t["name"], "tag": t["tag"], "has_logo": t["has_logo"], "maps": 0}
            if roster and hub_ids:
                # one row per (player, map-game); we average team totals across map-games
                cur.execute("""SELECT mt.hub_game_id AS g,
                                      SUM(p.player_frags) AS f, SUM(p.player_deaths) AS d,
                                      SUM(p.player_suicides) AS sui, SUM(p.player_teamkills) AS tk,
                                      SUM(p.player_damage_given) AS gvn, SUM(p.player_damage_taken) AS tkn,
                                      SUM(p.player_ya_taken) AS ya, SUM(p.player_ra_taken) AS ra,
                                      SUM(p.player_health100_taken) AS mh,
                                      SUM(p.player_sg_hits) AS sgh, SUM(p.player_sg_attacks) AS sga,
                                      SUM(p.player_lg_hits) AS lgh, SUM(p.player_lg_attacks) AS lga,
                                      SUM(p.player_rl_directs) AS rlh, SUM(p.player_rl_attacks) AS rla,
                                      SUM(p.player_quad_taken) AS q
                               FROM players p
                               JOIN matches mt ON mt.match_id = p.match_id
                               WHERE mt.hub_game_id = ANY(%s) AND p.canonical_id = ANY(%s)
                               GROUP BY mt.hub_game_id""", (hub_ids, roster))
                g = cur.fetchall()
                n = len(g)
                row["maps"] = n
                if n:
                    def avg(k): return round(sum((x[k] or 0) for x in g) / n, 1)
                    sf, sd = sum(x["f"] or 0 for x in g), sum(x["d"] or 0 for x in g)
                    row.update({
                        "eff": _pct(sf, sf + sd), "frags": avg("f"), "deaths": avg("d"),
                        "suicides": avg("sui"), "tk": avg("tk"),
                        "dmg_given": avg("gvn"), "dmg_taken": avg("tkn"),
                        "ya": avg("ya"), "ra": avg("ra"), "mh": avg("mh"),
                        "sg": _pct(sum(x["sgh"] or 0 for x in g), sum(x["sga"] or 0 for x in g)),
                        "lg": _pct(sum(x["lgh"] or 0 for x in g), sum(x["lga"] or 0 for x in g)),
                        "rl": _pct(sum(x["rlh"] or 0 for x in g), sum(x["rla"] or 0 for x in g)),
                        "quad": avg("q"),
                    })
            out.append(row)
    out.sort(key=lambda x: -(x.get("eff") or 0))
    return {"teams": out}


@app.get("/api/ladder/{ladder_id}/player-stats")
def ladder_player_stats(ladder_id: int, response: Response):
    """Per-player, per-map averages from KTX stats across the ladder's reported
    matches (decisive maps only). Same columns as Team Stats, ranked by efficiency."""
    import ladder as _ladder
    response.headers["Cache-Control"] = "public, max-age=20"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT hub_game_ids FROM ladder_matches WHERE ladder_id=%s", (ladder_id,))
        game_ids = set()
        for r in cur.fetchall():
            game_ids.update(int(g) for g in (r["hub_game_ids"] or []) if g is not None)
        # canonical_id -> (team name, tag) from active rosters
        cur.execute("SELECT name, tag, members FROM ladder_teams WHERE ladder_id=%s AND status='active'", (ladder_id,))
        cid_team = {}
        for t in cur.fetchall():
            for m in (t["members"] or []):
                cid_team[m] = (t["name"], t["tag"])
        if not game_ids:
            return {"players": []}
        cur.execute("""SELECT p.canonical_id AS cid, mt.hub_game_id AS g,
                              p.player_frags AS f, p.player_deaths AS d, p.player_suicides AS sui,
                              p.player_teamkills AS tk, p.player_damage_given AS gvn, p.player_damage_taken AS tkn,
                              p.player_ya_taken AS ya, p.player_ra_taken AS ra, p.player_health100_taken AS mh,
                              p.player_sg_hits AS sgh, p.player_sg_attacks AS sga,
                              p.player_lg_hits AS lgh, p.player_lg_attacks AS lga,
                              p.player_rl_directs AS rlh, p.player_rl_attacks AS rla, p.player_quad_taken AS q,
                              COALESCE(pc.display_name, p.player_name) AS display
                       FROM players p
                       JOIN matches mt ON mt.match_id = p.match_id
                       LEFT JOIN players_canonical pc ON pc.canonical_id = p.canonical_id
                       WHERE mt.hub_game_id = ANY(%s) AND p.canonical_id IS NOT NULL""",
                    (list(game_ids),))
        from collections import defaultdict
        byp = defaultdict(list)
        disp = {}
        for r in cur.fetchall():
            byp[r["cid"]].append(r)
            disp[r["cid"]] = r["display"]
        out = []
        for cid, g in byp.items():
            n = len(g)
            def avg(k): return round(sum((x[k] or 0) for x in g) / n, 1)
            sf = sum(x["f"] or 0 for x in g)
            sd = sum(x["d"] or 0 for x in g)
            team = cid_team.get(cid)
            out.append({
                "canonical_id": cid, "name": disp.get(cid, cid),
                "team": team[0] if team else None, "tag": team[1] if team else None, "maps": n,
                "eff": _pct(sf, sf + sd), "frags": avg("f"), "deaths": avg("d"),
                "suicides": avg("sui"), "tk": avg("tk"), "dmg_given": avg("gvn"), "dmg_taken": avg("tkn"),
                "ya": avg("ya"), "ra": avg("ra"), "mh": avg("mh"),
                "sg": _pct(sum(x["sgh"] or 0 for x in g), sum(x["sga"] or 0 for x in g)),
                "lg": _pct(sum(x["lgh"] or 0 for x in g), sum(x["lga"] or 0 for x in g)),
                "rl": _pct(sum(x["rlh"] or 0 for x in g), sum(x["rla"] or 0 for x in g)),
                "quad": avg("q"),
            })
    out.sort(key=lambda x: -(x.get("eff") or 0))
    return {"players": out}


@app.post("/api/ladder/{ladder_id}/challenge")
def ladder_challenge(ladder_id: int, authorization: str | None = Header(default=None),
                     challenger_id: int = Body(..., embed=True),
                     challenged_id: int = Body(..., embed=True)):
    """A captain (or admin) issues a challenge 1–2 rungs up. Sets a play-by
    deadline from the ladder's forfeit window. Captains must be a member of the
    challenger team (matched by their linked canonical_id)."""
    import ladder as _ladder
    user = _current_user(authorization, required=True)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT rules FROM ladders WHERE id=%s AND status='active'", (ladder_id,))
        lad = cur.fetchone()
        if not lad:
            raise HTTPException(404, "ladder not found")
        chr_t = _team_row(cur, ladder_id, challenger_id)
        chd_t = _team_row(cur, ladder_id, challenged_id)
        if not chr_t or not chd_t:
            raise HTTPException(404, "team not found")
        # Pre-launch gate: challenging is off for players until the ladder is
        # opened (rules.open). Admins can still challenge (for testing).
        if not (lad.get("rules") or {}).get("open") and not user.get("is_admin"):
            raise HTTPException(403, "the ladder isn't open yet")
        # Authorize: admin, or a member of the challenging team.
        members = chr_t.get("members") or []
        cid = user.get("canonical_id")
        if not user.get("is_admin") and (not cid or cid not in members):
            raise HTTPException(403, "you must be a member of the challenging team")
        cr, hr = chr_t["rung"], chd_t["rung"]
        if cr is None or hr is None:
            raise HTTPException(409, "both teams must be placed on the ladder")
        gap = cr - hr  # challenger is below (larger rung) by this many
        if gap not in (1, 2):
            raise HTTPException(409, "you can only challenge 1 or 2 rungs up")
        # One open challenge per team at a time (either side).
        cur.execute("""SELECT 1 FROM ladder_challenges
                       WHERE ladder_id=%s AND status IN ('open','scheduled')
                         AND (challenger_id IN (%s,%s) OR challenged_id IN (%s,%s))
                       LIMIT 1""",
                    (ladder_id, challenger_id, challenged_id, challenger_id, challenged_id))
        if cur.fetchone():
            raise HTTPException(409, "one of these teams already has an open challenge")
        # Loss cooldown: after losing ANY match, a team can't ISSUE challenges for
        # a week (it can still BE challenged). The sting of a loss. Winners stay
        # free to challenge until they lose or get tied up in a challenge.
        # BUT a win clears it early: a team in cooldown can only play as the
        # CHALLENGED side, so if they then WIN that defense their most recent
        # decisive match is a win → cooldown lifts immediately. So cooldown is
        # active only when the team's latest decisive result is a loss.
        cooldown_days = (lad.get("rules") or {}).get("loss_cooldown_days", 7)
        cur.execute("""SELECT max(played_at) FILTER (WHERE winner_id <> %s) AS last_loss,
                              max(played_at) FILTER (WHERE winner_id = %s)  AS last_win
                       FROM ladder_matches
                       WHERE ladder_id=%s AND winner_id IS NOT NULL
                         AND (team_a_id=%s OR team_b_id=%s)""",
                    (challenger_id, challenger_id, ladder_id, challenger_id, challenger_id))
        lr = cur.fetchone()
        if lr and lr["last_loss"] and not (lr["last_win"] and lr["last_win"] > lr["last_loss"]):
            until = lr["last_loss"] + timedelta(days=cooldown_days)
            now = datetime.now(timezone.utc)
            if until > now:
                rem = until - now
                raise HTTPException(409, f"your team lost recently — you can't issue challenges for "
                                         f"{rem.days}d {rem.seconds // 3600}h. (You can still be challenged, "
                                         f"and winning a defense lifts the cooldown.)")
        forfeit_days = (lad.get("rules") or {}).get("forfeit_days", 7)
        deadline = datetime.now(timezone.utc) + timedelta(days=forfeit_days)
        cur.execute("""INSERT INTO ladder_challenges (ladder_id, challenger_id, challenged_id, rungs_up, deadline)
                       VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                    (ladder_id, challenger_id, challenged_id, gap, deadline))
        chid = cur.fetchone()["id"]
        conn.commit()
    # No Discord ping yet — we hold the announcement until the challenger posts
    # their proposed times, then send ONE combined message (challenge + times).
    return {"challenge_id": chid, "deadline": deadline.isoformat(), "rungs_up": gap}


@app.get("/api/ladder/challenge/{challenge_id}/server-suggestion")
def ladder_server_suggestion(challenge_id: int, response: Response):
    """Recommend the fairest NA server for a challenge, from both teams' players'
    real ping history (fallback: self-reported state distance). Public."""
    import ladder as _ladder
    import ping_suggest as PS
    import auth as A
    response.headers["Cache-Control"] = "public, max-age=20"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT ca.members AS a, cd.members AS b
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id
                       WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        team_a, team_b = list(ch["a"] or []), list(ch["b"] or [])
        player_ids = list({*team_a, *team_b})
        # self-reported location for the fallback + Brazil-vs-Brazil detection
        states, locs = {}, {}
        if player_ids:
            A.ensure_users(cur)
            cur.execute("SELECT canonical_id, state, country FROM users WHERE canonical_id = ANY(%s)", (player_ids,))
            for r in cur.fetchall():
                if r["state"]:
                    states[r["canonical_id"]] = r["state"]
                locs[r["canonical_id"]] = (r["state"], r["country"])
        # A team is "Brazilian" if it has located players and ALL of them are BR
        # (country=BR or state=INTL). BR-vs-BR matches may use a BR server.
        def _team_is_br(ids):
            located = [locs[i] for i in ids if i in locs and (locs[i][0] or locs[i][1])]
            return bool(located) and all((st == "INTL" or co == "BR") for st, co in located)
        allow_sa = _team_is_br(team_a) and _team_is_br(team_b)
        suggestions = PS.suggest_servers(cur, player_ids, states=states, top=3, allow_sa=allow_sa)
        # display names for the ping matrix
        names = {}
        if player_ids:
            cur.execute("SELECT canonical_id, display_name FROM players_canonical WHERE canonical_id = ANY(%s)", (player_ids,))
            names = {r["canonical_id"]: r["display_name"] for r in cur.fetchall()}
    for s in suggestions:
        for p in s["pings"]:
            p["name"] = names.get(p["player"], p["player"])
    return {"suggestions": suggestions}


@app.get("/api/ladder/challenge/{challenge_id}/availability")
def ladder_challenge_availability(challenge_id: int, response: Response):
    """Both teams' players' general weekly availability, for overlaying 'who's
    usually free' onto the scheduler's slots. The client converts each slot into
    each player's tz and checks their free hours. Public (low-sensitivity)."""
    import ladder as _ladder
    import auth as A
    response.headers["Cache-Control"] = "no-store"
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT ca.id AS a_id, ca.name AS a_name, ca.members AS a,
                              cd.id AS b_id, cd.name AS b_name, cd.members AS b
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id
                       WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        team_a, team_b = list(ch["a"] or []), list(ch["b"] or [])
        player_ids = list({*team_a, *team_b})
        avail, names = {}, {}
        if player_ids:
            A.ensure_users(cur)
            cur.execute("""SELECT canonical_id, availability, timezone
                           FROM users WHERE canonical_id = ANY(%s) AND availability IS NOT NULL""",
                        (player_ids,))
            for r in cur.fetchall():
                avail[r["canonical_id"]] = {"av": r["availability"], "tz": r["timezone"]}
            cur.execute("SELECT canonical_id, display_name FROM players_canonical WHERE canonical_id = ANY(%s)", (player_ids,))
            names = {r["canonical_id"]: r["display_name"] for r in cur.fetchall()}

    def _players(ids):
        out = []
        for cid in ids:
            a = avail.get(cid)
            if not a or not a["av"]:
                continue
            blob = a["av"]
            out.append({"id": cid, "name": names.get(cid, cid),
                        "tz": (blob.get("tz") or a["tz"]),
                        "slots": blob.get("slots") or {}})
        return out

    total_players = len(player_ids)
    listed = _players(team_a) + _players(team_b)
    return {
        "teams": [
            {"id": ch["a_id"], "name": ch["a_name"], "players": _players(team_a)},
            {"id": ch["b_id"], "name": ch["b_name"], "players": _players(team_b)},
        ],
        "players": listed,
        "total_players": total_players,
        "with_availability": len(listed),
    }


def _user_on_team(cur, user, team_id):
    """True if the user (or admin) is on the given team's roster."""
    if user.get("is_admin"):
        return True
    cid = user.get("canonical_id")
    if not cid:
        return False
    cur.execute("SELECT members FROM ladder_teams WHERE id=%s", (team_id,))
    row = cur.fetchone()
    return bool(row and cid in (row["members"] or []))


def _mentions(cur, *team_ids):
    """Build a Discord @-mention string for the linked players on the given
    team(s). Members are canonical_ids → users.discord_id. Empty if none linked."""
    ids = [t for t in team_ids if t]
    if not ids:
        return ""
    cur.execute("SELECT members FROM ladder_teams WHERE id = ANY(%s)", (ids,))
    cids = []
    for r in cur.fetchall():
        cids.extend(r["members"] or [])
    if not cids:
        return ""
    cur.execute("SELECT discord_id FROM users WHERE canonical_id = ANY(%s) AND discord_id IS NOT NULL",
                (list(set(cids)),))
    return " ".join(f"<@{r['discord_id']}>" for r in cur.fetchall())


def _turn_team(ch):
    """Whose turn it is to act. No slots on the table → the challenger proposes
    first. Otherwise the team that did NOT post the current slots picks (or
    counter-proposes)."""
    if not (ch.get("proposed") or []):
        return ch["challenger_id"]
    pb = ch.get("proposed_by")
    return ch["challenged_id"] if pb == ch["challenger_id"] else ch["challenger_id"]


@app.post("/api/ladder/challenge/{challenge_id}/availability")
def ladder_challenge_availability(challenge_id: int, authorization: str | None = Header(default=None),
                                  slots: list = Body(..., embed=True)):
    """Propose (or counter-propose) availability slots. Whoever's turn it is may
    post slots; this records them under that team and flips the turn to the other
    team to pick or counter. Member of the turn team (or admin) only."""
    import ladder as _ladder
    user = _current_user(authorization, required=True)
    clean = [str(s) for s in (slots or []) if s][:200]
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT c.challenger_id, c.challenged_id, c.proposed, c.proposed_by, c.status,
                              c.rungs_up, c.deadline,
                              ca.name AS challenger, cd.name AS challenged
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        if ch["status"] not in ("open",):
            raise HTTPException(409, "challenge is already scheduled or resolved")
        # First time anyone posts slots = the challenger's opening proposal. That's
        # when we fire the (held) challenge announcement, bundled with the times.
        is_initial = not (ch.get("proposed") or [])
        turn = _turn_team(ch)
        if not _user_on_team(cur, user, turn):
            raise HTTPException(403, "it's not your team's turn to suggest times")
        clean = sorted(clean)   # chronological in the Discord message + pick list
        cur.execute("UPDATE ladder_challenges SET proposed=%s, proposed_by=%s WHERE id=%s",
                    (json.dumps(clean), turn, challenge_id))
        mention = _mentions(cur, ch["challenger_id"], ch["challenged_id"])
        conn.commit()
    proposer = ch["challenger"] if turn == ch["challenger_id"] else ch["challenged"]
    other = ch["challenged"] if turn == ch["challenger_id"] else ch["challenger"]
    try:
        import notify
        if clean:
            notify.match_proposal(
                proposer, other, clean, initial=is_initial,
                challenger=ch["challenger"], challenged=ch["challenged"],
                rungs_up=ch.get("rungs_up"),
                deadline_iso=(ch["deadline"].isoformat() if ch.get("deadline") else None),
                mention=mention)
    except Exception:
        pass
    return {"challenge_id": challenge_id, "slots": clean, "proposed_by": turn}


@app.post("/api/ladder/challenge/{challenge_id}/schedule")
def ladder_challenge_schedule(challenge_id: int, authorization: str | None = Header(default=None),
                              slot: str = Body(..., embed=True),
                              server: str | None = Body(default=None, embed=True)):
    """Pick one of the proposed slots (+ server) → match scheduled. Only the team
    whose turn it is (i.e. NOT the team that posted the current slots) may pick."""
    import ladder as _ladder
    user = _current_user(authorization, required=True)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT c.challenger_id, c.challenged_id, c.proposed, c.proposed_by, c.status,
                              ca.name AS challenger, cd.name AS challenged
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id
                       WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        if ch["status"] not in ("open",):
            raise HTTPException(409, "challenge is already scheduled or resolved")
        if not (ch["proposed"] or []):
            raise HTTPException(400, "no times have been proposed yet")
        turn = _turn_team(ch)
        if not _user_on_team(cur, user, turn):
            raise HTTPException(403, "it's not your team's turn to pick")
        if slot not in (ch["proposed"] or []):
            raise HTTPException(400, "pick one of the proposed slots")
        cur.execute("""UPDATE ladder_challenges
                       SET agreed_at=%s, server=%s, status='scheduled' WHERE id=%s""",
                    (slot, (server or "").strip() or None, challenge_id))
        mention = _mentions(cur, ch["challenger_id"], ch["challenged_id"])
        conn.commit()
    try:
        import notify
        notify.game_scheduled(ch["challenger"], ch["challenged"], slot, (server or "").strip() or None, mention=mention)
    except Exception:
        pass
    return {"challenge_id": challenge_id, "agreed_at": slot, "server": server, "status": "scheduled"}


@app.post("/api/ladder/challenge/{challenge_id}/withdraw")
def ladder_challenge_withdraw(challenge_id: int, authorization: str | None = Header(default=None)):
    """The CHALLENGER may withdraw their own challenge while it's still `open`
    (no time agreed yet). Frees both teams. The challenged team cannot withdraw —
    only the side that issued it. Once `scheduled`, it's locked (ask an admin to
    cancel). Admins may withdraw on a team's behalf."""
    import ladder as _ladder
    user = _current_user(authorization, required=True)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT c.challenger_id, c.challenged_id, c.status,
                              ca.name AS challenger, cd.name AS challenged
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id
                       WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        if ch["status"] != "open":
            raise HTTPException(409, "this challenge is already scheduled or resolved — "
                                     "ask an admin to cancel it")
        # Only the challenger's roster (or an admin) may withdraw. The challenged
        # team is never allowed to — they can only play it or let it expire.
        if not _user_on_team(cur, user, ch["challenger_id"]):
            if _user_on_team(cur, user, ch["challenged_id"]):
                raise HTTPException(403, "only the challenging team can withdraw a challenge")
            raise HTTPException(403, "you must be on the challenging team to withdraw this")
        cur.execute("""UPDATE ladder_challenges SET status='cancelled', resolved_at=now()
                       WHERE id=%s AND status='open' RETURNING id""", (challenge_id,))
        row = cur.fetchone()
        mention = _mentions(cur, ch["challenger_id"], ch["challenged_id"])
        conn.commit()
    if not row:
        raise HTTPException(409, "challenge is no longer open")
    try:
        import notify
        notify.challenge_withdrawn(ch["challenger"], ch["challenged"], mention=mention)
    except Exception:
        pass
    return {"challenge_id": challenge_id, "status": "cancelled"}


@app.get("/api/admin/ladder/challenge/{challenge_id}/candidate-games")
def admin_ladder_candidate_games(challenge_id: int, authorization: str | None = Header(default=None)):
    """Ingested 2on2 hub games involving BOTH teams' rostered players, around the
    scheduled time — candidates for the admin to mark as the official Bo3 maps.
    There may be MORE than 3 (warmups, re-dos); the admin picks the decisive set
    and only those count toward results + stats."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT c.challenger_id, c.challenged_id, c.agreed_at,
                              ca.name AS a_name, cd.name AS b_name,
                              ca.members AS a_members, cd.members AS b_members
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        a_roster = list(ch["a_members"] or [])
        b_roster = list(ch["b_members"] or [])
        if not a_roster or not b_roster:
            return {"challenge_id": challenge_id, "candidates": [], "note": "rosters not fully linked yet"}
        # Time window: ±~18h around the agreed time if set, else last 3 days. (Plays
        # often drift from the scheduled slot.) match_date is ISO text → lexical compare.
        if ch.get("agreed_at"):
            lo = (ch["agreed_at"] - timedelta(hours=18)).isoformat()
            hi = (ch["agreed_at"] + timedelta(hours=30)).isoformat()
        else:
            lo = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            hi = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        cur.execute("""SELECT mt.hub_game_id, mt.match_map, mt.match_date,
                              SUM(CASE WHEN p.canonical_id = ANY(%(a)s) THEN p.player_frags ELSE 0 END) AS a_frags,
                              SUM(CASE WHEN p.canonical_id = ANY(%(b)s) THEN p.player_frags ELSE 0 END) AS b_frags,
                              COUNT(*) FILTER (WHERE p.canonical_id = ANY(%(a)s)) AS a_n,
                              COUNT(*) FILTER (WHERE p.canonical_id = ANY(%(b)s)) AS b_n
                       FROM matches mt JOIN players p ON p.match_id = mt.match_id
                       WHERE mt.match_mode='2on2' AND mt.hub_game_id IS NOT NULL
                         AND mt.match_date > %(lo)s AND mt.match_date < %(hi)s
                       GROUP BY mt.hub_game_id, mt.match_map, mt.match_date
                       HAVING COUNT(*) FILTER (WHERE p.canonical_id = ANY(%(a)s)) >= 1
                          AND COUNT(*) FILTER (WHERE p.canonical_id = ANY(%(b)s)) >= 1
                       ORDER BY mt.match_date""",
                    {"a": a_roster, "b": b_roster, "lo": lo, "hi": hi})
        cands = []
        for r in cur.fetchall():
            a, b = r["a_frags"] or 0, r["b_frags"] or 0
            cands.append({"hub_game_id": r["hub_game_id"], "map": r["match_map"],
                          "played_at": str(r["match_date"]), "a_frags": a, "b_frags": b,
                          "winner": "a" if a > b else "b" if b > a else "tie"})
    # Auto-detect the decisive Bo3 set: walk games in time order, counting map
    # wins, until one team reaches 2. Those are `suggested` (pre-ticked in the UI);
    # extra games (warm-ups, post-decider) are left off. Same logic the future
    # fully-auto resolver will use.
    aw = bw = 0
    done = False
    for c in cands:
        if done or c["winner"] == "tie":
            c["suggested"] = False
            continue
        c["suggested"] = True
        if c["winner"] == "a":
            aw += 1
        else:
            bw += 1
        if aw == 2 or bw == 2:
            done = True
    return {"challenge_id": challenge_id, "a_name": ch["a_name"], "b_name": ch["b_name"],
            "challenger_id": ch["challenger_id"], "challenged_id": ch["challenged_id"],
            "candidates": cands,
            "suggested_score": {"a": aw, "b": bw},
            "suggested_complete": (aw == 2 or bw == 2)}


@app.post("/api/admin/ladder/challenge/{challenge_id}/result")
def admin_ladder_result(challenge_id: int, authorization: str | None = Header(default=None),
                        winner_id: int = Body(..., embed=True),
                        maps: list = Body(default=[], embed=True),
                        score_a: int = Body(default=None, embed=True),
                        score_b: int = Body(default=None, embed=True)):
    """Admin records a played challenge: writes the match, applies ladder
    movement (challenger win → climb; challenged win → no movement), and
    resolves the challenge. hub_game_ids are pulled from the maps payload."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT * FROM ladder_challenges WHERE id=%s", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        if ch["status"] in ("played", "forfeited"):
            raise HTTPException(409, "challenge already resolved")
        if winner_id not in (ch["challenger_id"], ch["challenged_id"]):
            raise HTTPException(400, "winner must be one of the two teams")
        hub_ids = [m.get("hub_game_id") for m in maps if m.get("hub_game_id")]
        # played_at = when the LAST counted game actually ended (drives the loss
        # cooldown), not when the admin got around to reporting it. Falls back to
        # now() if no hub games are linked.
        played_at = None
        if hub_ids:
            cur.execute("SELECT max(match_date) AS m FROM matches WHERE hub_game_id = ANY(%s)", (hub_ids,))
            mr = cur.fetchone()
            played_at = mr["m"] if mr and mr["m"] else None
        cur.execute("""INSERT INTO ladder_matches
                       (ladder_id, challenge_id, team_a_id, team_b_id, maps, score_a, score_b, winner_id, hub_game_ids, played_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, COALESCE(%s::timestamptz, now())) RETURNING id""",
                    (ch["ladder_id"], challenge_id, ch["challenger_id"], ch["challenged_id"],
                     json.dumps(maps), score_a, score_b, winner_id, json.dumps(hub_ids), played_at))
        match_id = cur.fetchone()["id"]
        moves = {}
        if winner_id == ch["challenger_id"]:
            moves = _ladder.apply_win(cur, ch["ladder_id"], ch["challenger_id"], ch["challenged_id"], match_id)
        # challenged win → ranks unchanged (challenger simply failed to climb)
        cur.execute("UPDATE ladder_challenges SET status='played', resolved_at=now() WHERE id=%s", (challenge_id,))
        # Names for every team touched (winner/loser + any shifted by a 2-rung jump).
        loser_id = ch["challenged_id"] if winner_id == ch["challenger_id"] else ch["challenger_id"]
        all_ids = list({winner_id, loser_id, *moves.keys()})
        cur.execute("SELECT id, name FROM ladder_teams WHERE id = ANY(%s)", (all_ids,))
        names = {r["id"]: r["name"] for r in cur.fetchall()}
        # KotH change = a team newly at rung 1 (only the climbing challenger can be).
        new_koth = next((tid for tid, r in moves.items() if r == 1), None)
        koth_name = names.get(new_koth)
        # Per-map scoreline + human movement summary for the notification.
        def _ms(m):
            mp, a, b = m.get("map", "?"), m.get("a_frags"), m.get("b_frags")
            return f"{mp} {a}-{b}" if a is not None and b is not None else mp
        maps_line = " · ".join(_ms(m) for m in maps) if maps else None
        movement = None
        if moves:
            wr = moves.get(winner_id)
            parts = []
            if wr is not None:
                parts.append(f"📈 **{names.get(winner_id, winner_id)}** moved up to #{wr} on the KOTH ladder")
            for tid, rk in moves.items():
                if tid == winner_id:
                    continue
                arrow = "⬇️" if tid == loser_id else "↘️"
                parts.append(f"{arrow} **{names.get(tid, tid)}** → #{rk}")
            movement = "\n".join(parts)
        mention = _mentions(cur, winner_id, loser_id)
        conn.commit()
    try:
        import notify
        score = f"{score_a}-{score_b}" if score_a is not None and score_b is not None else None
        notify.result_posted(names.get(winner_id, f"#{winner_id}"), names.get(loser_id, f"#{loser_id}"),
                             maps_line=maps_line, movement=movement, score=score, mention=mention)
        if koth_name:
            notify.koth_changed(koth_name)
    except Exception:
        pass
    return {"match_id": match_id, "winner_id": winner_id, "moves": moves}


@app.post("/api/admin/ladder/challenge/{challenge_id}/cancel")
def admin_ladder_cancel(challenge_id: int, authorization: str | None = Header(default=None)):
    """Cancel a challenge (ladder-admin) — no ladder movement, just clears it so
    the teams are free again. For mistakes / restarting a matchup."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("UPDATE ladder_challenges SET status='cancelled', resolved_at=now() "
                    "WHERE id=%s AND status IN ('open','scheduled') RETURNING id", (challenge_id,))
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "no open challenge with that id")
    return {"challenge_id": challenge_id, "status": "cancelled"}


@app.post("/api/admin/ladder/challenge/{challenge_id}/reschedule")
def admin_ladder_reschedule(challenge_id: int, authorization: str | None = Header(default=None),
                            slot: str = Body(..., embed=True),
                            server: str | None = Body(default=None, embed=True)):
    """Move an already-scheduled match to a new time (and optionally change the
    server). Resets the reminder flags so the 1h/10m pings re-fire for the new
    time, and posts an updated message to Discord."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    try:
        dt = datetime.fromisoformat(slot.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        raise HTTPException(400, "bad time — expected an ISO-8601 instant")
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("""SELECT c.status, c.server, c.challenger_id, c.challenged_id,
                              ca.name AS a, cd.name AS b
                       FROM ladder_challenges c
                       JOIN ladder_teams ca ON ca.id=c.challenger_id
                       JOIN ladder_teams cd ON cd.id=c.challenged_id WHERE c.id=%s""", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        if ch["status"] != "scheduled":
            raise HTTPException(409, "only a scheduled match can be rescheduled")
        new_server = (server or "").strip() or ch["server"]
        cur.execute("""UPDATE ladder_challenges
                       SET agreed_at=%s, server=%s,
                           reminded_soon=FALSE, reminded_10m=FALSE, reminded_24h=FALSE
                       WHERE id=%s""", (dt, new_server, challenge_id))
        mention = _mentions(cur, ch["challenger_id"], ch["challenged_id"])
        conn.commit()
    try:
        import notify
        notify.match_rescheduled(ch["a"], ch["b"], dt.isoformat(), new_server, mention=mention)
    except Exception:
        pass
    return {"challenge_id": challenge_id, "agreed_at": dt.isoformat(), "server": new_server}


@app.post("/api/admin/ladder/challenge/{challenge_id}/forfeit")
def admin_ladder_forfeit(challenge_id: int, authorization: str | None = Header(default=None)):
    """Admin marks a challenge as forfeited (challenged team didn't play in
    time): the challenged team drops one rung."""
    import ladder as _ladder
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ladder.ensure_schema(cur)
        cur.execute("SELECT * FROM ladder_challenges WHERE id=%s", (challenge_id,))
        ch = cur.fetchone()
        if not ch:
            raise HTTPException(404, "challenge not found")
        if ch["status"] in ("played", "forfeited"):
            raise HTTPException(409, "challenge already resolved")
        moves = _ladder.apply_forfeit(cur, ch["ladder_id"], ch["challenged_id"])
        cur.execute("UPDATE ladder_challenges SET status='forfeited', resolved_at=now() WHERE id=%s", (challenge_id,))
        cur.execute("SELECT name FROM ladder_teams WHERE id=%s", (ch["challenged_id"],))
        row = cur.fetchone()
        chd_name = row["name"] if row else f"#{ch['challenged_id']}"
        # A forfeit can promote the team below into rung 1.
        new_koth = next((tid for tid, r in moves.items() if r == 1 and tid != ch["challenged_id"]), None)
        koth_name = None
        if new_koth:
            cur.execute("SELECT name FROM ladder_teams WHERE id=%s", (new_koth,))
            r = cur.fetchone()
            koth_name = r["name"] if r else None
        conn.commit()
    try:
        import notify
        notify.forfeit_posted(chd_name)
        if koth_name:
            notify.koth_changed(koth_name)
    except Exception:
        pass
    return {"forfeited": True, "moves": moves}


@app.get("/api/admin/oauth/status")
def admin_oauth_status(authorization: str | None = Header(default=None)):
    """OAuth/federation config snapshot for the admin panel (admin token).
    Secrets are reported only as configured-or-not + a masked tail, never raw."""
    _check_admin_auth(authorization)

    def _mask(v):
        if not v:
            return None
        return f"…{v[-4:]}" if len(v) > 4 else "set"

    cid = os.environ.get("DISCORD_CLIENT_ID")
    counts = {}
    with pg() as conn:
        cur = conn.cursor()
        import auth as A
        A.ensure_users(cur)
        cur.execute("SELECT COUNT(*) n FROM users")
        counts["users"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM users WHERE canonical_id IS NOT NULL")
        counts["linked"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM users WHERE is_admin")
        counts["admins"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM user_claims WHERE status='pending'")
        counts["pending_claims"] = cur.fetchone()["n"]
    return {
        "discord": {
            "provider": "Discord",
            "configured": bool(cid and os.environ.get("DISCORD_CLIENT_SECRET")),
            "client_id": cid,
            "client_secret": _mask(os.environ.get("DISCORD_CLIENT_SECRET")),
            "redirect_uri": os.environ.get("DISCORD_REDIRECT_URI"),
            "frontend_url": os.environ.get("FRONTEND_URL"),
            "scopes": ["identify"],
            "jwt_secret": "set" if os.environ.get("JWT_SECRET") else "fallback(SYNC_SECRET)",
            "webhook_configured": bool(os.environ.get("DISCORD_WEBHOOK_URL")),
        },
        "counts": counts,
    }


@app.get("/api/admin/users")
def admin_users(authorization: str | None = Header(default=None)):
    """List Discord-authed users (admin token). Used to grant admin + link players."""
    import auth as A
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("""SELECT u.discord_id, u.username, u.global_name, u.avatar,
                              u.canonical_id, u.is_admin, u.verified, u.created_at, u.last_login,
                              pc.display_name AS profile_display
                       FROM users u
                       LEFT JOIN players_canonical pc ON pc.canonical_id = u.canonical_id
                       ORDER BY u.verified ASC, u.created_at DESC""")
        return {"users": [dict(r,
                               created_at=r["created_at"].isoformat() if r["created_at"] else None,
                               last_login=r["last_login"].isoformat() if r["last_login"] else None)
                          for r in cur.fetchall()]}


@app.post("/api/admin/users/{discord_id}/admin")
def admin_set_admin(discord_id: str, authorization: str | None = Header(default=None),
                    is_admin: bool = Body(True, embed=True)):
    """Grant/revoke admin on a user (admin token)."""
    import auth as A
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("UPDATE users SET is_admin=%s WHERE discord_id=%s RETURNING discord_id, username, is_admin",
                    (is_admin, discord_id))
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "user not found")
    return row


@app.post("/api/admin/users/{discord_id}/link")
def admin_link_player(discord_id: str, authorization: str | None = Header(default=None),
                      canonical_id: str = Body(..., embed=True)):
    """Link a Discord user to a canonical player (admin token). This is what lets
    a captain act on behalf of a team they're a roster member of."""
    import auth as A
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("UPDATE users SET canonical_id=%s WHERE discord_id=%s RETURNING discord_id, canonical_id",
                    (canonical_id, discord_id))
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "user not found")
    return row


@app.post("/api/admin/users/{discord_id}/verify")
def admin_verify_user(discord_id: str, authorization: str | None = Header(default=None),
                      verified: bool = Body(True, embed=True)):
    """Mark a self-linked account as verified (admin's background check). Linking
    is immediate at claim time; this just records that you've confirmed it."""
    import auth as A
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        A.ensure_users(cur)
        cur.execute("UPDATE users SET verified=%s WHERE discord_id=%s RETURNING discord_id, verified",
                    (verified, discord_id))
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "user not found")
    return row


# ── Search ─────────────────────────────────────────────────────────────────────

@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=64), limit: int = Query(20, ge=1, le=100)):
    pattern = f"%{q.lower()}%"
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT pc.canonical_id, pc.display_name AS display,
                   (SELECT COUNT(*) FROM players p WHERE p.canonical_id = pc.canonical_id) AS matches
            FROM players_canonical pc
            WHERE (LOWER(pc.display_name) LIKE %s OR pc.canonical_id LIKE %s)
              AND NOT COALESCE(pc.hidden, FALSE)
            ORDER BY matches DESC
            LIMIT %s
        """, (pattern, pattern, limit))
        return {"q": q, "results": cur.fetchall()}


# ── Periodic sync (triggered by Cloud Scheduler every 2h) ─────────────────
# The endpoint is invoked over HTTP with a bearer token matching SYNC_SECRET
# env var. Runs the full sync pipeline inline; Cloud Run hard cap is 60min
# which is plenty (typical run = 30s sync + 30s rate.py + ~60s misc).

import subprocess


def _run_script(script: str, *args: str, timeout: int = 600) -> dict:
    """Run a python script inside the container, capturing return code + tail
    of stdout. Subprocess (not in-process import) because each existing script
    has its own DB connection + commit pattern; isolating them keeps the
    endpoint's request connection clean."""
    cmd = ["python", script, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "script": script,
            "args": list(args),
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"script": script, "args": list(args), "returncode": -1, "error": "timeout"}


def _check_admin_auth(authorization: str | None):
    """Bearer auth shared by every /api/admin/* endpoint. Returns 503 if no
    SYNC_SECRET configured, 401 if the token doesn't match."""
    expected = os.environ.get("SYNC_SECRET")
    if not expected:
        raise HTTPException(503, "SYNC_SECRET not configured on the server")
    if authorization != f"Bearer {expected}":
        raise HTTPException(401, "missing or invalid bearer token")


def _check_ladder_admin(authorization: str | None):
    """Ladder management auth: EITHER Peter's SYNC_SECRET (god key, used by the
    /admin panel) OR any Discord-authed user with is_admin (Nin/Bance/Cronus via
    plain login on /ladder/admin). Lets co-admins run the ladder without the god
    key, while the rest of /admin stays SYNC_SECRET-only."""
    expected = os.environ.get("SYNC_SECRET")
    if expected and authorization == f"Bearer {expected}":
        return {"via": "sync_secret", "is_admin": True, "discord_id": None}
    u = _current_user(authorization, required=False)
    if u and u.get("is_admin"):
        return u
    raise HTTPException(403, "ladder admin access required")


def _parse_logo_data_uri(s: str):
    """Decode a 'data:image/...;base64,...' string to (bytes, mime). Capped so a
    team logo can't bloat the DB. Returns (None, None) for empty input."""
    if not s:
        return None, None
    if not s.startswith("data:") or "," not in s:
        raise HTTPException(400, "logo must be a data URI")
    head, b64 = s.split(",", 1)
    mime = head[5:].split(";")[0] or "image/png"
    if mime not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        raise HTTPException(400, "logo must be PNG/JPEG/WebP/GIF")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "invalid logo encoding")
    if len(raw) > 600_000:
        raise HTTPException(413, "logo too large (max ~500KB — resize first)")
    return raw, mime


# ── Player Rating Cards — Phase 1 (Decision & Skill Framework) ───────────────
# The EASY tier: single-number skills already stored per match (no reparse), each
# a direct frogbot cvar so a player rating transmutes straight into a bot dial.
# Scored 0-99 as a sample-shrunk percentile vs the established population.
# Phase 2/3 add movement, situational aim (yaw/pitch, under-fire), reaction.
# (key, label, pillar, higher_is_better) → bot dial:
#   lg_acc/sg_acc → accuracy · rl_acc → prediction_error · ra/mh_ctrl → item-desire
#   weights · aggression → engage threshold. Weapon Preference (style) → lg/rl_pref.
_CARD_ATTRS = [
    ("lg_acc",     "LG Accuracy", "Aim",         True),
    ("rl_acc",     "RL Accuracy", "Aim",         True),   # DIRECT hits / attacks
    ("sg_acc",     "SG Accuracy", "Aim",         True),
    ("ra_ctrl",    "RA Control",  "Game Sense",  True),   # RA share vs opponent (map-independent)
    ("mh_ctrl",    "MH Control",  "Game Sense",  True),   # Mega share vs opponent
    ("aggression", "Aggression",  "Temperament", True),   # damage given / match
]


@app.get("/api/admin/player-cards")
def admin_player_cards(authorization: str | None = Header(default=None),
                       mode: str = "1on1"):
    """R1 Player Rating Cards: top-20 overall + top-10 of Div 1/2/3, each scored
    on the 8 Tier-A attributes as a 0-99 percentile within the rated population."""
    import bisect
    _check_admin_auth(authorization)
    MIN_ANCHOR_MATCHES = 50
    SHRINK_K = 150  # ~150 games to fully "earn" a rating
    try:
        with pg() as conn:
            cur = conn.cursor()
            # A) Ranked players + tier cutoffs (fast, indexed on the ratings table).
            cutoffs = _get_tier_cutoffs(cur, mode)
            cur.execute("""SELECT r.canonical_id, COALESCE(pc.display_name, r.canonical_id) AS display,
                                  pc.region, r.conservative, r.matches_rated
                           FROM ratings r LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
                           WHERE r.mode=%s AND r.map='' AND r.matches_rated >= 10
                             AND NOT COALESCE(pc.hidden, FALSE)
                           ORDER BY r.conservative DESC""", (mode,))
            ranked = cur.fetchall()
            rated_cids = [r["canonical_id"] for r in ranked]

            # B) Aggregate Phase-1 columns ONLY for rated players — index-bounded by
            #    canonical_id, not a full-history scan (that timed out the uncached
            #    admin call). Self-join to the opponent gives map-independent RA/MH
            #    share; HAVING>=50 = the established floor we card/anchor on.
            sig = {}
            if rated_cids:
                cur.execute("""
                    SELECT p.canonical_id, COUNT(*) AS n,
                           SUM(p.player_lg_hits) AS lg_h, SUM(p.player_lg_attacks) AS lg_a,
                           SUM(p.player_rl_directs) AS rl_d, SUM(p.player_rl_attacks) AS rl_a,
                           SUM(p.player_sg_hits) AS sg_h, SUM(p.player_sg_attacks) AS sg_a,
                           SUM(p.player_damage_given) AS dmg_g,
                           SUM(p.player_lg_damage_enemy) AS lg_dmg, SUM(p.player_rl_damage_enemy) AS rl_dmg,
                           SUM(p.player_ra_taken) AS ra_mine, SUM(p.player_health100_taken) AS mh_mine,
                           SUM(COALESCE(opp.player_ra_taken,0)) AS ra_opp,
                           SUM(COALESCE(opp.player_health100_taken,0)) AS mh_opp
                    FROM players p
                    JOIN matches m ON m.match_id = p.match_id
                    JOIN players opp ON opp.match_id = p.match_id AND opp.player_name <> p.player_name
                    WHERE m.match_mode = %s AND p.canonical_id = ANY(%s)
                    GROUP BY p.canonical_id
                    HAVING COUNT(*) >= 50
                """, (mode, rated_cids))

                def _ratio(a, b):
                    return (a / b) if (a is not None and b) else None

                for r in cur.fetchall():
                    n = r["n"] or 0
                    ra_m, ra_o = r["ra_mine"] or 0, r["ra_opp"] or 0
                    mh_m, mh_o = r["mh_mine"] or 0, r["mh_opp"] or 0
                    lg_dmg, rl_dmg = r["lg_dmg"] or 0, r["rl_dmg"] or 0
                    sig[r["canonical_id"]] = {
                        "matches": n,
                        "lg_acc":     _ratio(r["lg_h"], r["lg_a"]),
                        "rl_acc":     _ratio(r["rl_d"], r["rl_a"]),
                        "sg_acc":     _ratio(r["sg_h"], r["sg_a"]),
                        "ra_ctrl":    _ratio(ra_m, ra_m + ra_o),
                        "mh_ctrl":    _ratio(mh_m, mh_m + mh_o),
                        "aggression": _ratio(r["dmg_g"], n),
                        "weapon_pref": _ratio(lg_dmg, lg_dmg + rl_dmg),  # LG share (style)
                    }
    except Exception as e:
        raise HTTPException(500, f"player-cards aggregation failed: {type(e).__name__}: {e}")

    # Percentile anchor = the aggregated established players; shrink each stat toward
    # the population mean by sample size before percentile-ranking.
    pop, mean = {}, {}
    for k, *_ in _CARD_ATTRS:
        vals = sorted(v[k] for v in sig.values() if v.get(k) is not None)
        pop[k] = vals
        mean[k] = (sum(vals) / len(vals)) if vals else None

    def rate(cid, key, higher):
        raw = sig[cid].get(key)
        vals = pop[key]
        mu = mean[key]
        n = sig[cid].get("matches") or 0
        if raw is None or mu is None or len(vals) < 2:
            return None
        shrunk = (n * raw + SHRINK_K * mu) / (n + SHRINK_K)
        pct = bisect.bisect_left(vals, shrunk) / (len(vals) - 1)
        if not higher:
            pct = 1 - pct
        return max(0, min(99, round(pct * 99)))

    def card_for(cid):
        n = sig[cid].get("matches") or 0
        attrs = [{"key": k, "label": lbl, "pillar": pil, "value": rate(cid, k, hb),
                  "raw": sig[cid].get(k)} for k, lbl, pil, hb in _CARD_ATTRS]
        vals = [a["value"] for a in attrs if a["value"] is not None]
        conf = "established" if n >= MIN_ANCHOR_MATCHES else ("provisional" if n >= 15 else "low")
        return {"ovr": round(sum(vals) / len(vals)) if vals else None, "attrs": attrs,
                "stat_matches": n, "confidence": conf, "weapon_pref": sig[cid].get("weapon_pref")}

    enriched = []
    for i, r in enumerate(ranked):
        p = {"canonical_id": r["canonical_id"], "display": r["display"], "region": r["region"],
             "rank": i + 1, "conservative": round(r["conservative"], 1),
             "matches": r["matches_rated"], "tier": tier_for(r["conservative"], cutoffs)}
        c = (card_for(r["canonical_id"]) if r["canonical_id"] in sig
             else {"ovr": None, "attrs": None, "stat_matches": 0, "confidence": "none"})
        p.update(c)
        enriched.append(p)

    # Only card ESTABLISHED players (>= 50 games) — the same floor as the percentile
    # anchor, so every carded player has a stable, sample-backed rating.
    MIN_CARD_MATCHES = 50

    def take(pred, n):
        out = []
        for p in enriched:
            if (p.get("stat_matches") or 0) >= MIN_CARD_MATCHES and pred(p):
                out.append(p)
                if len(out) >= n:
                    break
        return out

    def in_div(slug):
        return lambda p: bool(p["tier"]) and p["tier"]["slug"] == slug

    sections = [
        {"key": "overall", "label": "Top 20 — Overall", "players": take(lambda p: True, 20)},
        {"key": "div1", "label": "Top 10 — Div 1 (50+ games)", "players": take(in_div("div1"), 10)},
        {"key": "div2", "label": "Top 10 — Div 2 (50+ games)", "players": take(in_div("div2"), 10)},
        {"key": "div3", "label": "Top 10 — Div 3 (50+ games)", "players": take(in_div("div3"), 10)},
    ]
    return {"mode": mode, "population": len(sig),
            "attributes": [{"key": k, "label": lbl, "pillar": pil} for k, lbl, pil, *_ in _CARD_ATTRS],
            "sections": sections}


@app.get("/api/admin/status")
def admin_status(authorization: str | None = Header(default=None)):
    """One-stop admin dashboard payload: scheduler state, last sync time,
    DB row counts. Cheap (a handful of COUNT queries + one gcloud subprocess
    for the scheduler state)."""
    _check_admin_auth(authorization)

    # Scheduler state via Google Cloud Scheduler client. Cloud Run's default
    # service account needs roles/cloudscheduler.viewer (admin for pause/resume).
    sched_state = "unknown"
    sched_next = None
    try:
        from google.cloud import scheduler_v1
        client = scheduler_v1.CloudSchedulerClient()
        name = "projects/deepfrag-prod/locations/us-central1/jobs/deepfrag-periodic-sync"
        job = client.get_job(name=name)
        sched_state = scheduler_v1.Job.State(job.state).name.lower()  # ENABLED / PAUSED / DISABLED
        if job.schedule_time:
            sched_next = job.schedule_time.isoformat()
    except Exception as e:
        sched_state = f"unknown ({type(e).__name__}: {str(e)[:80]})"

    with pg() as conn:
        cur = conn.cursor()
        stats = {}
        cur.execute("SELECT COUNT(*) AS n FROM matches")
        stats["matches"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM ratings WHERE mode='1on1' AND map=''")
        stats["rated_1on1"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM servers")
        stats["servers"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM servers WHERE is_live = TRUE")
        stats["servers_live"] = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM players_canonical")
        stats["canonical_players"] = cur.fetchone()["n"]
        cur.execute("SELECT MAX(match_date) AS last FROM matches")
        stats["last_match_date"] = cur.fetchone()["last"]

    return {
        "scheduler": {"state": sched_state, "next_run": sched_next},
        "stats": stats,
        "api_revision": os.environ.get("K_REVISION", "unknown"),
        "now": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/admin/players/{canonical_id}")
def admin_player_detail(canonical_id: str,
                        authorization: str | None = Header(default=None)):
    """Admin-only deep profile. Returns ratings row + career + aliases + recent
    activity for a single canonical_id. Populates the Players-tab inspector."""
    _check_admin_auth(authorization)
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT canonical_id, display_name, login, created_at, updated_at,
                   region, region_confidence, region_distribution
            FROM players_canonical WHERE canonical_id = %s
        """, (canonical_id,))
        canon = cur.fetchone()
        if not canon:
            raise HTTPException(404, "player not found")

        cur.execute("""
            SELECT COUNT(DISTINCT m.match_id) AS matches,
                   MIN(m.match_date) AS first_match,
                   MAX(m.match_date) AS last_match,
                   COUNT(DISTINCT CASE WHEN m.match_mode='1on1' THEN m.match_id END) AS matches_1on1,
                   COUNT(DISTINCT CASE WHEN m.match_mode='2on2' THEN m.match_id END) AS matches_2on2,
                   COUNT(DISTINCT CASE WHEN m.match_mode='4on4' THEN m.match_id END) AS matches_4on4,
                   COUNT(DISTINCT CASE WHEN m.match_date::timestamptz >= NOW() - INTERVAL '90 days' THEN m.match_id END) AS matches_90d
            FROM matches m JOIN players p ON p.match_id = m.match_id
            WHERE p.canonical_id = %s
        """, (canonical_id,))
        career = dict(cur.fetchone() or {})

        cur.execute("""
            SELECT player_name, COUNT(*) AS uses
            FROM players WHERE canonical_id = %s
            GROUP BY player_name ORDER BY uses DESC LIMIT 200
        """, (canonical_id,))
        aliases = [{"name": r["player_name"], "uses": r["uses"]} for r in cur.fetchall()]

        cur.execute("""
            SELECT mode, mu, sigma, conservative, matches_rated, wins, losses, draws,
                   unique_opponents, avg_ddr, avg_frag_diff, updated_at
            FROM ratings WHERE canonical_id = %s AND map = ''
        """, (canonical_id,))
        ratings = {r["mode"]: dict(r) for r in cur.fetchall()}

        cutoffs = _get_tier_cutoffs(cur, "1on1")
        if "1on1" in ratings:
            ratings["1on1"]["tier"] = tier_for(ratings["1on1"]["conservative"], cutoffs)

    return {
        "canonical_id": canon["canonical_id"],
        "display": canon["display_name"],
        "login": canon["login"],
        "created_at": canon["created_at"],
        "updated_at": canon["updated_at"],
        "region": canon["region"],
        "region_confidence": canon["region_confidence"],
        "region_distribution": canon["region_distribution"],
        "career": career,
        "aliases": aliases,
        "ratings": ratings,
    }


def _fetch_cloudflare_pages_deploys(limit: int = 30):
    """Pull recent Cloudflare Pages deploys for the deepfrag project. Returns
    [] silently if the CF env vars aren't set so the Cloud Run feed still
    works even without Cloudflare credentials configured."""
    import requests
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    project = os.environ.get("CLOUDFLARE_PAGES_PROJECT", "deepfrag")
    if not (token and account):
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/pages/projects/{project}/deployments"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     params={"per_page": min(limit, 25)}, timeout=15)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        return []
    out = []
    for d in body.get("result", []):
        stage = (d.get("latest_stage") or {})
        out.append({
            "source": "pages",
            "name": d.get("short_id") or d.get("id", "")[:8],
            "create_time": d.get("created_on"),
            "image": None,
            "image_sha": (d.get("deployment_trigger") or {}).get("metadata", {}).get("commit_hash", "")[:7] or None,
            "status": stage.get("status") or "unknown",  # success / failure / active / etc
            "traffic_percent": 100 if (d.get("aliases") or [None])[0] == f"https://{project}.pages.dev" else 0,
            "active": d.get("environment") == "production" and stage.get("status") == "success" and (d.get("aliases") or [None])[0] == f"https://{project}.pages.dev",
            "url": d.get("url"),
            "environment": d.get("environment"),
        })
    return out


@app.get("/api/admin/deploys")
def admin_deploys(authorization: str | None = Header(default=None),
                  limit: int = Query(30, ge=1, le=100)):
    """Recent deploys for the Deploy log tab + dashboard latest-deploys card.
    Merges Cloud Run revisions (backend API) and Cloudflare Pages deployments
    (frontend) into one chronological list with a 'source' badge per row.
    Requires roles/run.viewer on the Cloud Run SA; CF Pages requires
    CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID env vars."""
    _check_admin_auth(authorization)
    try:
        import google.auth, google.auth.transport.requests
        import requests
        creds, _ = google.auth.default()
        creds.refresh(google.auth.transport.requests.Request())
        # Fetch revisions + active service traffic config in parallel-ish.
        svc_base = "https://run.googleapis.com/v2/projects/deepfrag-prod/locations/us-central1/services/deepfrag-api"
        headers = {"Authorization": f"Bearer {creds.token}"}
        revs_r = requests.get(f"{svc_base}/revisions?pageSize={limit}", headers=headers, timeout=15)
        svc_r = requests.get(svc_base, headers=headers, timeout=15)
        revs_r.raise_for_status()
        svc_r.raise_for_status()

        # Build a {revision_name: traffic_percent} map from the Service's
        # current traffic split — usually a single revision at 100%.
        traffic_map = {}
        for t in (svc_r.json().get("trafficStatuses") or svc_r.json().get("traffic") or []):
            rev = (t.get("revision") or "").split("/")[-1]
            if rev:
                traffic_map[rev] = t.get("percent", 0)

        out = []
        for rev in (revs_r.json().get("revisions") or []):
            name = (rev.get("name") or "").split("/")[-1]
            # Conditions[0] is usually "Ready" — surface its status + reason.
            ready_status = "unknown"
            for c in (rev.get("conditions") or []):
                if c.get("type") == "Ready":
                    ready_status = c.get("state", "unknown")
                    break
            image = ""
            containers = rev.get("containers") or []
            if containers:
                image = containers[0].get("image", "")
            out.append({
                "source": "api",
                "name": name,
                "create_time": rev.get("createTime"),
                "image": image,
                "image_sha": image.split("@sha256:")[1][:12] if "@sha256:" in image else None,
                "status": ready_status,
                "traffic_percent": traffic_map.get(name, 0),
                "active": traffic_map.get(name, 0) > 0,
            })
        # Merge in Cloudflare Pages deploys (frontend). Fails silently if env
        # vars missing — backend feed still works.
        try:
            out.extend(_fetch_cloudflare_pages_deploys(limit=limit))
        except Exception:
            pass
        # Newest first across both sources
        out.sort(key=lambda r: r["create_time"] or "", reverse=True)
        return {
            "deploys": out[:limit],
            "active_revision": next((r["name"] for r in out if r["source"] == "api" and r["active"]), None),
            "active_pages": next((r["name"] for r in out if r["source"] == "pages" and r["active"]), None),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Cloud Run API error: {type(e).__name__}: {str(e)[:200]}")


@app.get("/api/admin/activity")
def admin_activity(authorization: str | None = Header(default=None),
                   limit: int = Query(40, ge=1, le=200)):
    """Live activity feed for the admin dashboard. Returns recent system events
    composed from: matches added in last 24h, last scheduler run summary,
    invariant check status. Each event has {ts, level, tag, msg}."""
    _check_admin_auth(authorization)
    events = []
    with pg() as conn:
        cur = conn.cursor()
        # Recent matches — one event per match added (most recent first)
        cur.execute("""
            SELECT m.match_id, m.match_date, m.match_mode, m.match_map,
                   m.server_hostname,
                   string_agg(DISTINCT p.canonical_id, ', ' ORDER BY p.canonical_id) AS players
            FROM matches m
            LEFT JOIN players p ON p.match_id = m.match_id AND p.canonical_id IS NOT NULL
            WHERE m.match_date::timestamptz > NOW() - INTERVAL '24 hours'
            GROUP BY m.match_id, m.match_date, m.match_mode, m.match_map, m.server_hostname
            ORDER BY m.match_date DESC
            LIMIT %s
        """, (limit,))
        for r in cur.fetchall():
            host = (r["server_hostname"] or "").split(":")[0]
            events.append({
                "ts": r["match_date"],
                "level": "ok",
                "tag": r["match_mode"].upper(),
                "msg": f"{r['match_map']} · {r['players'] or '?'} @ {host}",
                "match_id": r["match_id"],
            })
        # Latest re-rate marker (max updated_at on ratings table)
        cur.execute("SELECT MAX(updated_at) AS last FROM ratings WHERE mode='1on1' AND map=''")
        last_rate = cur.fetchone()["last"]
        if last_rate:
            events.append({
                "ts": last_rate,
                "level": "info",
                "tag": "RATE",
                "msg": "last 1on1 rating-run completed",
            })
        # Latest server sync — max last_seen_live on servers
        cur.execute("SELECT MAX(last_seen_live) AS last, COUNT(*) FILTER (WHERE is_live) AS live FROM servers")
        srv = cur.fetchone()
        if srv["last"]:
            events.append({
                "ts": srv["last"],
                "level": "info",
                "tag": "SRV",
                "msg": f"hub sync · {srv['live']} live servers",
            })
    events.sort(key=lambda e: e["ts"] or "", reverse=True)
    return {"events": events[:limit]}


@app.post("/api/admin/scheduler/{action}")
def admin_scheduler(action: str, authorization: str | None = Header(default=None)):
    """Pause or resume the deepfrag-periodic-sync Cloud Scheduler job.
    `action` must be 'pause' or 'resume'."""
    _check_admin_auth(authorization)
    if action not in ("pause", "resume"):
        raise HTTPException(400, "action must be 'pause' or 'resume'")
    try:
        from google.cloud import scheduler_v1
        client = scheduler_v1.CloudSchedulerClient()
        name = "projects/deepfrag-prod/locations/us-central1/jobs/deepfrag-periodic-sync"
        if action == "pause":
            job = client.pause_job(name=name)
        else:
            job = client.resume_job(name=name)
        return {
            "action": action,
            "state": scheduler_v1.Job.State(job.state).name.lower(),
        }
    except Exception as e:
        raise HTTPException(500, f"scheduler {action} failed: {type(e).__name__}: {e}")


@app.post("/api/admin/rerate")
def admin_rerate(authorization: str | None = Header(default=None),
                 confirm: str = Query(...,
                     description="must equal 'I-understand-this-wipes-ratings'")):
    """Full re-rate of every 1on1 rating row. Wipes the ratings table for
    mode=1on1 (across all map buckets) and rebuilds from scratch. Takes ~3-8
    minutes; the request blocks until done.

    Use cases: algorithm change (tier breakpoints, perf weights), bug fix in
    rate.py, schema change. NOT for daily ops — that's what /api/admin/sync
    + the every-2h scheduler is for.

    Requires confirm param to prevent accidental clicks."""
    _check_admin_auth(authorization)
    if confirm != "I-understand-this-wipes-ratings":
        raise HTTPException(400, "missing confirm token")
    result = _run_script("rate.py", "--mode", "1on1", timeout=1200)
    # Also run invariants right after — re-rate is exactly the moment to verify.
    invariants = _run_script("tests/test_invariants.py", timeout=60)
    return {"rerate": result, "invariants": invariants}


# Postgres TZ names for the per-region heatmap. Picked to match where most
# players in each region actually live — heatmap reads naturally that way.
REGION_TIMEZONES = {
    "EU":    {"tz": "Europe/Berlin",      "label": "CET/CEST"},
    "NA":    {"tz": "America/New_York",   "label": "ET"},
    "SA":    {"tz": "America/Sao_Paulo",  "label": "BRT"},
    "OC":    {"tz": "Australia/Sydney",   "label": "AEST"},
    "AS-AF": {"tz": "Asia/Tokyo",         "label": "JST"},
    "OTHER": {"tz": "UTC",                "label": "UTC"},
    "all":   {"tz": "UTC",                "label": "UTC"},
}
REGION_LABELS = {
    "EU":    {"flag": "🇪🇺", "name": "Europe"},
    "NA":    {"flag": "🇺🇸", "name": "N. America"},
    "SA":    {"flag": "🇧🇷", "name": "S. America"},
    "OC":    {"flag": "🇦🇺", "name": "Oceania"},
    "AS-AF": {"flag": "🇯🇵", "name": "Asia/Africa"},
    "OTHER": {"flag": "🌐", "name": "Other"},
    "all":   {"flag": "🌐", "name": "All regions"},
}

@app.get("/api/admin/matches/by-region")
def admin_matches_by_region(
    authorization: str | None = Header(default=None),
    region: str = Query("all", description="all|EU|NA|SA|OC|AS-AF|OTHER"),
    window: str = Query("30", description="7|30|90|365|all"),
    mode: str = Query("all", description="all|1on1|2on2|4on4"),
):
    """Powers the admin Matches tab (Region Switcher design). Returns:
      - region_totals: per-region match count for the tab row + live indicator
      - region_summary: matches/players/servers/peak-hour for the selected region
      - top_maps / top_servers / top_players: ranked lists scoped to region+mode+window
      - heatmap: 7d × 24h grid in the region's local timezone (so the activity
        pattern reads correctly — EU evenings are EU evenings, not UTC times)
      - mode_breakdown: counts per mode for the sub-tab pills
    """
    _check_admin_auth(authorization)

    # Window → date filter (None means 'all time')
    days = None if window == "all" else int(window)
    date_filter = "" if days is None else "AND m.match_date::timestamptz >= NOW() - INTERVAL %(days)s"
    date_params = {} if days is None else {"days": f"{days} days"}
    mode_filter = "" if mode == "all" else "AND m.match_mode = %(mode)s"
    mode_params = {} if mode == "all" else {"mode": mode}
    region_filter = "" if region == "all" else "AND s.region = %(region)s"
    region_params = {} if region == "all" else {"region": region}

    tz_info = REGION_TIMEZONES.get(region, REGION_TIMEZONES["all"])
    base_params = {**date_params, **mode_params, **region_params}

    with pg() as conn:
        cur = conn.cursor()

        # Region totals — ALWAYS spans all regions so the tabs work regardless
        # of which region is currently selected. Window+mode filters DO apply
        # so the tab numbers match the window/mode picker.
        cur.execute(f"""
            SELECT COALESCE(s.region, 'OTHER') AS region,
                   COUNT(*) AS matches,
                   COUNT(*) FILTER (WHERE s.is_live) AS matches_on_live_servers,
                   COUNT(DISTINCT split_part(m.server_hostname, ':', 1)) AS servers,
                   COUNT(DISTINCT split_part(m.server_hostname, ':', 1)) FILTER (WHERE s.is_live) AS servers_live
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region, is_live
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL {date_filter} {mode_filter}
            GROUP BY COALESCE(s.region, 'OTHER')
        """, {**date_params, **mode_params})
        region_totals = []
        total_all_regions = 0
        for r in cur.fetchall():
            region_totals.append({
                "region": r["region"],
                "flag": REGION_LABELS.get(r["region"], {}).get("flag", "🌐"),
                "name": REGION_LABELS.get(r["region"], {}).get("name", r["region"]),
                "matches": r["matches"],
                "servers": r["servers"],
                "servers_live": r["servers_live"],
            })
            total_all_regions += r["matches"]
        # Synthetic "all" row
        cur.execute(f"""
            SELECT COUNT(DISTINCT split_part(m.server_hostname, ':', 1)) FILTER (WHERE s.is_live) AS live
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, is_live
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL {date_filter} {mode_filter}
        """, {**date_params, **mode_params})
        all_live = cur.fetchone()["live"] or 0
        region_totals.insert(0, {
            "region": "all", "flag": "🌐", "name": "All regions",
            "matches": total_all_regions, "servers": None, "servers_live": all_live,
        })

        # Mode breakdown for sub-tabs (always region-scoped, never mode-filtered)
        cur.execute(f"""
            SELECT m.match_mode AS mode, COUNT(*) AS n
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL {date_filter} {region_filter}
            GROUP BY m.match_mode
        """, {**date_params, **region_params})
        mode_breakdown = {r["mode"]: r["n"] for r in cur.fetchall()}
        mode_breakdown["all"] = sum(mode_breakdown.values())

        # Region summary (selected region only, all filters applied)
        cur.execute(f"""
            SELECT COUNT(*) AS matches,
                   COUNT(DISTINCT split_part(m.server_hostname, ':', 1)) AS servers,
                   COUNT(DISTINCT split_part(m.server_hostname, ':', 1))
                     FILTER (WHERE s.is_live) AS servers_live,
                   COUNT(DISTINCT p.canonical_id) AS unique_players
            FROM matches m
            LEFT JOIN players p ON p.match_id = m.match_id
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region, is_live
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL {date_filter} {mode_filter} {region_filter}
        """, base_params)
        summary_row = dict(cur.fetchone())

        # Peak hour — hour-of-day with the most matches, in the region's local TZ.
        cur.execute(f"""
            SELECT EXTRACT(HOUR FROM m.match_date::timestamptz AT TIME ZONE %(tz)s)::int AS hour,
                   COUNT(*) AS n
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL {date_filter} {mode_filter} {region_filter}
            GROUP BY hour ORDER BY n DESC LIMIT 1
        """, {**base_params, "tz": tz_info["tz"]})
        peak = cur.fetchone()
        summary = {
            **summary_row,
            "peak_hour": peak["hour"] if peak else None,
            "peak_hour_matches": peak["n"] if peak else 0,
            "timezone_label": tz_info["label"],
        }

        # Top maps in this scope
        cur.execute(f"""
            SELECT m.match_map AS map, COUNT(*) AS n
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL AND m.match_map IS NOT NULL
              {date_filter} {mode_filter} {region_filter}
            GROUP BY m.match_map ORDER BY n DESC LIMIT 12
        """, base_params)
        top_maps = [dict(r) for r in cur.fetchall()]

        # Top servers in this scope
        cur.execute(f"""
            SELECT split_part(m.server_hostname, ':', 1) AS host_root,
                   COUNT(*) AS n,
                   MAX(s.country) AS country,
                   BOOL_OR(s.is_live) AS is_live
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region, country, is_live
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL
              {date_filter} {mode_filter} {region_filter}
            GROUP BY split_part(m.server_hostname, ':', 1)
            ORDER BY n DESC LIMIT 12
        """, base_params)
        top_servers = [dict(r) for r in cur.fetchall()]

        # Top players in this scope
        cur.execute(f"""
            SELECT p.canonical_id, COUNT(DISTINCT m.match_id) AS n
            FROM matches m
            JOIN players p ON p.match_id = m.match_id
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL AND p.canonical_id IS NOT NULL
              {date_filter} {mode_filter} {region_filter}
            GROUP BY p.canonical_id ORDER BY n DESC LIMIT 12
        """, base_params)
        top_players = [dict(r) for r in cur.fetchall()]

        # Hourly heatmap — 7 days × 24 hours, in region TZ. Day 0 = today,
        # day 6 = 6 days ago. Hour 0-23 in local time. NULL filled = 0.
        cur.execute(f"""
            SELECT EXTRACT(DOW FROM m.match_date::timestamptz AT TIME ZONE %(tz)s)::int AS dow,
                   EXTRACT(HOUR FROM m.match_date::timestamptz AT TIME ZONE %(tz)s)::int AS hour,
                   COUNT(*) AS n
            FROM matches m
            LEFT JOIN (
                SELECT DISTINCT ON (split_part(hostname, ':', 1))
                       split_part(hostname, ':', 1) AS host_root, region
                FROM servers ORDER BY split_part(hostname, ':', 1), is_live DESC NULLS LAST
            ) s ON s.host_root = split_part(m.server_hostname, ':', 1)
            WHERE m.server_hostname IS NOT NULL
              AND m.match_date::timestamptz >= NOW() - INTERVAL '7 days'
              {mode_filter} {region_filter}
            GROUP BY dow, hour
        """, {**mode_params, **region_params, "tz": tz_info["tz"]})
        heat_raw = {(r["dow"], r["hour"]): r["n"] for r in cur.fetchall()}
        # Build 7×24 grid: dow 1=Mon ... 0=Sun. We render Mon-Sun.
        dow_order = [1, 2, 3, 4, 5, 6, 0]  # Mon, Tue, Wed, Thu, Fri, Sat, Sun
        dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        heatmap_max = max(heat_raw.values()) if heat_raw else 1
        heatmap = []
        for i, dow in enumerate(dow_order):
            row = {"day": dow_labels[i], "hours": []}
            for h in range(24):
                n = heat_raw.get((dow, h), 0)
                row["hours"].append({"hour": h, "n": n, "level": min(5, int(5 * n / heatmap_max)) if heatmap_max else 0})
            heatmap.append(row)

    return {
        "region": region,
        "window": window,
        "mode": mode,
        "timezone_label": tz_info["label"],
        "timezone": tz_info["tz"],
        "region_totals": region_totals,
        "summary": summary,
        "mode_breakdown": mode_breakdown,
        "top_maps": top_maps,
        "top_servers": top_servers,
        "top_players": top_players,
        "heatmap": heatmap,
        "heatmap_max": heatmap_max,
    }


@app.post("/api/admin/sync-live")
def admin_sync_live(authorization: str | None = Header(default=None)):
    """Lightweight live-server snapshot refresh. Only runs sync_live_servers.py
    (~5-10s) — no match pull, no canonicalize, no rate. Designed to be hit
    every 60s by a dedicated Cloud Scheduler so the 'live' indicators on the
    Servers page + admin Matches tab stay fresh without piling up the heavy
    /api/admin/sync pipeline (which still runs every 2h)."""
    expected = os.environ.get("SYNC_SECRET")
    if not expected:
        raise HTTPException(503, "SYNC_SECRET not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(401, "missing or invalid bearer token")
    return {
        "step": "sync_live_servers",
        **_run_script("sync_live_servers.py", timeout=60),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/admin/sync")
def admin_sync(authorization: str | None = Header(default=None),
               skip_servers: bool = False,
               skip_rate: bool = False):
    """Periodic full-pull sync. Pipeline:
      1. sync_all_recent — pull every new hub match since the latest match_date
      2. canonicalize.py — assign canonical_ids for any new player names
      3. assign_player_regions.py — update player → primary region mapping
      4. sync_live_servers.py — refresh current live server snapshot (skip via ?skip_servers=true)
      5. rate.py --incremental --mode 1on1 — rate the new matches (skip via ?skip_rate=true)

    Auth: Bearer token must match SYNC_SECRET env var.
    """
    expected = os.environ.get("SYNC_SECRET")
    if not expected:
        raise HTTPException(503, "SYNC_SECRET not configured on the server")
    if authorization != f"Bearer {expected}":
        raise HTTPException(401, "missing or invalid bearer token")

    # Import here so cold-start of the public-facing endpoints doesn't pay for
    # the requests/bs4/yaml imports that only the sync path uses.
    import sync as sync_mod

    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "steps": []}

    # Step 1 — fetch new matches from hub
    with pg() as conn:
        try:
            step = sync_mod.sync_all_recent(conn, workers=8)
            summary["steps"].append({"step": "sync_all_recent", **step})
        except Exception as e:
            summary["steps"].append({"step": "sync_all_recent", "error": str(e)})
            summary["ended_at"] = datetime.now(timezone.utc).isoformat()
            return summary

    # Step 2 — INCREMENTAL canonicalize (resolve only NEW names + link all NULL
    # rows). Replaces the old full-pass canonicalize.py, which re-resolved and
    # re-upserted every distinct name each run (16k+ round trips) and silently
    # timed out as the DB grew — the root of the 2026-06 stall.
    try:
        with pg() as conn:
            summary["steps"].append({"step": "canonicalize", **_canonicalize_incremental(conn)})
    except Exception as e:
        summary["steps"].append({"step": "canonicalize", "error": str(e)})

    # Step 3 — re-assign player regions (idempotent, fast)
    summary["steps"].append({"step": "assign_regions", **_run_script("assign_player_regions.py", timeout=300)})

    # Step 4 — refresh live servers snapshot (network-bound, ~10s)
    if not skip_servers:
        summary["steps"].append({"step": "sync_live_servers", **_run_script("sync_live_servers.py", timeout=120)})

    # Step 5 — incremental rate (only new matches)
    if not skip_rate:
        summary["steps"].append({"step": "rate", **_run_script("rate.py", "--mode", "1on1", "--incremental", timeout=600)})

    # Step 5b — trigger the CF Pages rebuild so the prerendered homepage re-bakes
    # with the fresh standings (proactive global cache refresh after recompute).
    # Hook URL is a Cloud Run env secret (CF_DEPLOY_HOOK), never committed.
    if not skip_rate:
        import urllib.request as _u
        hook = os.environ.get("CF_DEPLOY_HOOK")
        if hook:
            try:
                with _u.urlopen(_u.Request(hook, method="POST", data=b"{}",
                                           headers={"content-type": "application/json"}), timeout=20) as r:
                    summary["steps"].append({"step": "cf_rebuild", "status": r.status})
            except Exception as e:
                summary["steps"].append({"step": "cf_rebuild", "error": str(e)[:200]})
        else:
            summary["steps"].append({"step": "cf_rebuild", "skipped": "CF_DEPLOY_HOOK not set"})

    # Step 6 — DB invariants. Catches regressions like the matches_rated
    # inflation bug (2026-05-27) before users see them. Non-blocking: a
    # failure here doesn't roll back the sync, just surfaces in the response
    # so admin/observability tools can alert on it.
    summary["steps"].append({"step": "invariants", **_run_script("tests/test_invariants.py", timeout=60)})

    # Step 7 — freshness watchdog: right after a sync, if the pipeline is STILL
    # stale/behind, that's a real problem → alert (throttled). This is the alarm
    # the 2026-06 silent stall lacked.
    try:
        with pg() as conn:
            summary["steps"].append({"step": "freshness", **_evaluate_freshness(conn)})
    except Exception as e:
        summary["steps"].append({"step": "freshness", "error": str(e)})

    summary["ended_at"] = datetime.now(timezone.utc).isoformat()
    return summary


def _ensure_canon_review_schema(cur):
    """Soft-delete + review flags on profiles, and a persistent merge table that
    canonicalize.py honors so manual links survive re-runs."""
    cur.execute("ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS hidden BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS reviewed BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("""CREATE TABLE IF NOT EXISTS canon_merges (
        source_canonical_id TEXT PRIMARY KEY,
        target_canonical_id TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )""")


@app.get("/api/admin/canon/review")
def admin_canon_review(authorization: str | None = Header(default=None),
                       min_matches: int = Query(20, ge=0),
                       max_matches: int = Query(100, ge=1),
                       only_isolated: bool = Query(True)):
    """Profiles in the [min,max] match range for cleanup review (ladder-admin).
    `only_isolated` = just those with a single name-variant (don't connect to any
    other profile) — the alts/junk most likely to need delete/link."""
    _check_ladder_admin(authorization)
    with pg() as conn:
        cur = conn.cursor()
        _ensure_canon_review_schema(cur)
        cur.execute("""
            WITH mc AS (
                SELECT canonical_id, COUNT(*) AS matches
                FROM players GROUP BY canonical_id
            ),
            vc AS (
                SELECT canonical_id, COUNT(*) AS variants
                FROM player_name_map GROUP BY canonical_id
            )
            SELECT pc.canonical_id, pc.display_name AS display, pc.region,
                   mc.matches, COALESCE(vc.variants, 0) AS variants,
                   (SELECT MAX(m.match_date) FROM players p JOIN matches m ON m.id = p.match_id
                      WHERE p.canonical_id = pc.canonical_id) AS last_seen
            FROM players_canonical pc
            JOIN mc ON mc.canonical_id = pc.canonical_id
            LEFT JOIN vc ON vc.canonical_id = pc.canonical_id
            WHERE NOT pc.hidden AND NOT pc.reviewed
              AND mc.matches BETWEEN %s AND %s
              AND (%s = FALSE OR COALESCE(vc.variants,0) <= 1)
            ORDER BY mc.matches DESC, pc.display_name
        """, (min_matches, max_matches, only_isolated))
        rows = cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        ls = d.get("last_seen")
        d["last_seen"] = ls.isoformat() if hasattr(ls, "isoformat") else ls
        out.append(d)
    return {"profiles": out, "count": len(out)}


@app.post("/api/admin/canon/{canonical_id}/review")
def admin_canon_review_action(canonical_id: str, authorization: str | None = Header(default=None),
                             action: str = Body(..., embed=True),
                             target: str | None = Body(default=None, embed=True)):
    """Resolve one profile from the cleanup queue (ladder-admin):
      action='keep'   → mark reviewed, leave as-is
      action='delete' → hide everywhere (soft; match data untouched, reversible)
      action='merge'  → re-point this profile's matches+names into `target`,
                        hide the source, and record it so canonicalize keeps it."""
    _check_ladder_admin(authorization)
    if action not in ("keep", "delete", "merge"):
        raise HTTPException(400, "action must be keep|delete|merge")
    with pg() as conn:
        cur = conn.cursor()
        _ensure_canon_review_schema(cur)
        cur.execute("SELECT 1 FROM players_canonical WHERE canonical_id=%s", (canonical_id,))
        if not cur.fetchone():
            raise HTTPException(404, "profile not found")
        if action == "keep":
            cur.execute("UPDATE players_canonical SET reviewed=TRUE WHERE canonical_id=%s", (canonical_id,))
        elif action == "delete":
            cur.execute("UPDATE players_canonical SET hidden=TRUE, reviewed=TRUE WHERE canonical_id=%s", (canonical_id,))
        else:  # merge
            if not target or target == canonical_id:
                raise HTTPException(400, "merge needs a different target profile")
            cur.execute("SELECT 1 FROM players_canonical WHERE canonical_id=%s", (target,))
            if not cur.fetchone():
                raise HTTPException(404, "target profile not found")
            cur.execute("UPDATE players SET canonical_id=%s WHERE canonical_id=%s", (target, canonical_id))
            cur.execute("UPDATE player_name_map SET canonical_id=%s WHERE canonical_id=%s", (target, canonical_id))
            cur.execute("""INSERT INTO canon_merges (source_canonical_id, target_canonical_id)
                           VALUES (%s,%s) ON CONFLICT (source_canonical_id)
                           DO UPDATE SET target_canonical_id=EXCLUDED.target_canonical_id""",
                        (canonical_id, target))
            cur.execute("UPDATE players_canonical SET hidden=TRUE, reviewed=TRUE WHERE canonical_id=%s", (canonical_id,))
        conn.commit()
    return {"canonical_id": canonical_id, "action": action, "target": target}


def _assign_canonical_from_map(conn):
    """Link every player row that has no canonical_id to the canonical it maps to
    in player_name_map. O(rows), no fuzzy."""
    cur = conn.cursor()
    cur.execute("""UPDATE players p SET canonical_id = nm.canonical_id
                   FROM player_name_map nm
                   WHERE p.canonical_id IS NULL AND p.player_name = nm.raw_name""")
    assigned = cur.rowcount
    conn.commit()
    return assigned


def _canonicalize_incremental(conn):
    """INCREMENTAL canonicalize — replaces the O(n) full pass that re-resolved and
    re-upserted EVERY distinct name (16k+ per-row round trips) on every run and
    timed out as the DB grew.

    Only NEW names (not yet in player_name_map) are resolved + batch-upserted,
    then every NULL-canonical row is linked from the (now-complete) map. Cost is
    O(new names), not O(all names). Returns a small summary."""
    import name_canon
    c = name_canon.Canonicalizer.load()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    # Distinct player names with no map entry yet — most common first so each new
    # canonical gets its busiest variant as the display name.
    cur.execute("""SELECT p.player_name, COALESCE(NULLIF(p.player_login,''),NULL) AS login, count(*) AS n
                   FROM players p
                   LEFT JOIN player_name_map nm ON nm.raw_name = p.player_name
                   WHERE nm.raw_name IS NULL AND p.player_name IS NOT NULL
                   GROUP BY p.player_name, p.player_login
                   ORDER BY n DESC""")
    rows = cur.fetchall()
    canon_by_cid = {}      # cid -> (cid, display, login, now, now)  (dedup per batch)
    map_rows = []          # (raw_name, cid, source, confidence, now)
    for r in rows:
        name, login = r["player_name"], r["login"]
        cid, decision = c.resolve(name, login)
        if cid not in canon_by_cid:
            display = name_canon.clean_for_display(name) or name
            canon_by_cid[cid] = (cid, display, login or "", now, now)
        map_rows.append((name, cid, decision, 1.0, now))
    if map_rows:
        psycopg2.extras.execute_values(cur,
            "INSERT INTO players_canonical (canonical_id, display_name, login, created_at, updated_at) "
            "VALUES %s ON CONFLICT (canonical_id) DO UPDATE SET updated_at=EXCLUDED.updated_at",
            list(canon_by_cid.values()), page_size=1000)
        psycopg2.extras.execute_values(cur,
            "INSERT INTO player_name_map (raw_name, canonical_id, source, confidence, created_at) "
            "VALUES %s ON CONFLICT (raw_name) DO UPDATE SET canonical_id=EXCLUDED.canonical_id, source=EXCLUDED.source",
            map_rows, page_size=1000)
        conn.commit()
    assigned = _assign_canonical_from_map(conn)
    cur.execute("SELECT count(*) AS n FROM players WHERE canonical_id IS NULL")
    still = cur.fetchone()["n"]
    return {"new_names_resolved": len(rows), "rows_assigned": assigned, "still_unassigned": still}


@app.post("/api/admin/canon/backfill-unassigned")
def admin_canon_backfill(authorization: str | None = Header(default=None)):
    """One-click fix for orphaned (canonical_id NULL) rows: resolve any brand-new
    names (incremental, batched) then link everything from player_name_map.
    Ladder-admin or god key."""
    _check_ladder_admin(authorization)
    with pg() as conn:
        res = _canonicalize_incremental(conn)
    return res


@app.post("/api/admin/apply-aliases")
def admin_apply_aliases(authorization: str | None = Header(default=None)):
    """FAST path: apply ONLY the explicit aliases.yaml entries (display name +
    re-point each variant/login to its canonical) — no fuzzy matching, so it
    finishes in seconds even at 159k matches (the full canonicalize.py O(n²)
    fuzzy pass times out at 600s). Use this to apply manual name fixes/merges.
    Ladder-admin."""
    _check_ladder_admin(authorization)
    import name_canon as NC
    import yaml as _yaml
    aliases = _yaml.safe_load(open(NC.ALIASES_PATH)) or {}
    var2cid, login2cid, displays = {}, {}, {}
    for cid, payload in aliases.items():
        payload = payload or {}
        displays[cid] = (payload.get("display") or cid, payload.get("login") or "")
        var2cid[cid.lower()] = cid
        for v in payload.get("variants", []):
            var2cid[str(v).lower()] = cid
        if payload.get("login"):
            login2cid[payload["login"]] = cid
    now = datetime.now(timezone.utc).isoformat()
    with pg() as conn:
        cur = conn.cursor()
        _ensure_canon_review_schema(cur)
        # 1. upsert display/login for each aliased canonical
        for cid, (disp, login) in displays.items():
            cur.execute("""INSERT INTO players_canonical (canonical_id, display_name, login, created_at, updated_at)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT(canonical_id) DO UPDATE SET
                             display_name=EXCLUDED.display_name,
                             login=COALESCE(NULLIF(EXCLUDED.login,''), players_canonical.login),
                             updated_at=EXCLUDED.updated_at""",
                        (cid, disp, login, now, now))
        # 2. find raw names that map to an aliased canonical (login first, else normalized variant)
        cur.execute("SELECT DISTINCT player_name, COALESCE(NULLIF(player_login,''),NULL) AS login FROM players")
        repoint = []
        for r in cur.fetchall():
            raw, login = r["player_name"], r["login"]
            target = login2cid.get(login) if login else None
            if not target:
                target = var2cid.get(NC.normalize(raw))
            if target:
                repoint.append((target, raw))
        # 3. re-point players + name_map (bulk)
        if repoint:
            psycopg2.extras.execute_values(
                cur, "UPDATE players SET canonical_id=data.cid FROM (VALUES %s) AS data(cid, raw) "
                     "WHERE players.player_name = data.raw", repoint, page_size=2000)
            psycopg2.extras.execute_values(
                cur, "UPDATE player_name_map SET canonical_id=data.cid FROM (VALUES %s) AS data(cid, raw) "
                     "WHERE player_name_map.raw_name = data.raw", repoint, page_size=2000)
        # 4. hide canonicals orphaned by merges (0 player rows now)
        cur.execute("""UPDATE players_canonical SET hidden=TRUE
                       WHERE canonical_id NOT IN (SELECT DISTINCT canonical_id FROM players WHERE canonical_id IS NOT NULL)""")
        orphaned = cur.rowcount
        conn.commit()
    return {"aliased_canonicals": len(displays), "rows_repointed": len(repoint), "orphans_hidden": orphaned}


@app.post("/api/admin/recanonicalize")
def admin_recanonicalize(authorization: str | None = Header(default=None)):
    """Run ONLY the name-canonicalization pass (apply aliases.yaml + name fixes)
    without the heavy match-pull/rating. Fast way to apply display/merge fixes.
    Returns canonicalize.py's full output so errors are visible. Ladder-admin."""
    _check_ladder_admin(authorization)
    r = _run_script("canonicalize.py", timeout=1500)
    # Also log to Cloud Run stdout so the error is greppable server-side.
    print(f"[recanon] rc={r.get('returncode')}\nSTDOUT_TAIL:\n{r.get('stdout_tail','')}\n"
          f"STDERR_TAIL:\n{r.get('stderr_tail','')}", flush=True)
    return r


@app.post("/api/admin/maps/seed-geometry")
def admin_seed_map_geometry(authorization: str | None = Header(default=None)):
    """One-shot (re-runnable) setup for the map annotator:
      1. CREATE TABLE map_annotations IF NOT EXISTS (idempotent migration).
      2. Run seed_map_geometry.py to fetch + cache loc/triangle geometry for
         all known maps into map_annotations.geometry.
    Runs inside Cloud Run, which is the only place with both the Cloud SQL
    socket and outbound internet to reach the geometry source. Safe to re-run:
    geometry is refreshed, user-authored spawns/teles are preserved."""
    _check_admin_auth(authorization)
    # 1. Idempotent table create (mirrors schema.sql).
    with pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS map_annotations (
                map         TEXT PRIMARY KEY,
                spawns      JSONB NOT NULL DEFAULT '[]'::jsonb,
                teles       JSONB NOT NULL DEFAULT '[]'::jsonb,
                geometry    JSONB,
                locked      BOOLEAN NOT NULL DEFAULT FALSE,
                updated_by  TEXT,
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.commit()
    # 2. Seed geometry (subprocess; passes prod PG_URL through the env). The
    #    legacy-spawns import is a no-op in prod (the sandbox file isn't there).
    return {
        "step": "seed_map_geometry",
        **_run_script("seed_map_geometry.py", timeout=600),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

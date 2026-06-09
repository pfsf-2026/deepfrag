#!/usr/bin/env python3
"""Discord OAuth + lightweight JWT sessions for DeepFrag (ladder captains).

Token-based: the /api CF Pages proxy forwards Authorization verbatim (and never
caches authed requests), so the SPA stores a signed JWT in localStorage and sends
it as `Authorization: Bearer <jwt>`. HS256 JWT is implemented with stdlib (hmac +
base64) — no PyJWT dependency, matching the slim-container approach elsewhere.

Flow: /api/auth/discord/login → Discord consent → /api/auth/discord/callback
(exchange code, fetch the Discord user, upsert `users`, mint JWT) → redirect to
the frontend with the token. Env: DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
DISCORD_REDIRECT_URI, FRONTEND_URL, JWT_SECRET (falls back to SYNC_SECRET).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

AUTHORIZE = "https://discord.com/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_URL = "https://discord.com/api/users/@me"
JWT_TTL = 30 * 24 * 3600  # 30 days
# Discord's API (behind Cloudflare) blocks the default Python-urllib UA with a
# 403 "error code: 1010". Their docs require a descriptive User-Agent on every
# request — send one or the token exchange never gets through.
USER_AGENT = "DeepFrag (https://deepfrag.pages.dev, 1.0)"


def _secret() -> str:
    return os.environ.get("JWT_SECRET") or os.environ.get("SYNC_SECRET") or "dev-insecure-secret"


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jwt_encode(payload: dict, ttl: int = JWT_TTL) -> str:
    head = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64e(json.dumps({**payload, "exp": int(time.time()) + ttl}).encode())
    seg = f"{head}.{body}"
    sig = _b64e(hmac.new(_secret().encode(), seg.encode(), hashlib.sha256).digest())
    return f"{seg}.{sig}"


def jwt_decode(token: str) -> dict | None:
    try:
        head, body, sig = token.split(".")
        seg = f"{head}.{body}"
        expect = _b64e(hmac.new(_secret().encode(), seg.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_b64d(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def login_url(state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": os.environ.get("DISCORD_CLIENT_ID", ""),
        "redirect_uri": os.environ.get("DISCORD_REDIRECT_URI", ""),
        "response_type": "code",
        "scope": "identify",
        "state": state,
    })
    return f"{AUTHORIZE}?{q}"


def exchange_code(code: str) -> dict | None:
    """Exchange the OAuth code for a Discord user profile {id, username, ...}.
    Raises RuntimeError with Discord's actual error body so the caller can
    surface *why* it failed (mismatch vs bad secret vs expired code)."""
    data = urllib.parse.urlencode({
        "client_id": os.environ.get("DISCORD_CLIENT_ID", ""),
        "client_secret": os.environ.get("DISCORD_CLIENT_SECRET", ""),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.environ.get("DISCORD_REDIRECT_URI", ""),
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": USER_AGENT,
        "accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.loads(r.read()).get("access_token")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"token endpoint {e.code}: {body}")
    if not tok:
        raise RuntimeError("no access_token in Discord response")
    ureq = urllib.request.Request(USER_URL, headers={
        "authorization": f"Bearer {tok}",
        "user-agent": USER_AGENT,
        "accept": "application/json",
    })
    with urllib.request.urlopen(ureq, timeout=15) as r:
        return json.loads(r.read())


USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
  discord_id   TEXT PRIMARY KEY,
  username     TEXT,
  global_name  TEXT,
  avatar       TEXT,
  canonical_id TEXT,                 -- linked QW player (set later by the user/admin)
  is_admin     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ DEFAULT now(),
  last_login   TIMESTAMPTZ DEFAULT now()
);
"""


CLAIMS_DDL = """
CREATE TABLE IF NOT EXISTS user_claims (
  id           BIGSERIAL PRIMARY KEY,
  discord_id   TEXT NOT NULL REFERENCES users(discord_id),
  canonical_id TEXT NOT NULL,                 -- the QW player they say is them
  status       TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
  created_at   TIMESTAMPTZ DEFAULT now(),
  resolved_at  TIMESTAMPTZ,
  resolved_by  TEXT                            -- admin discord_id (or 'token')
);
-- One live (pending) claim per user; re-claiming replaces it.
CREATE UNIQUE INDEX IF NOT EXISTS user_claims_one_pending
  ON user_claims (discord_id) WHERE status = 'pending';
"""


def ensure_users(cur):
    cur.execute(USERS_DDL)
    cur.execute(CLAIMS_DDL)
    # Self-claims link a profile IMMEDIATELY (no approval gate); `verified` is an
    # admin's later background check, not a precondition for anything.
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE")
    # Self-reported approximate location for match-server suggestion. region =
    # continent code (EU/NA/SA/OC/AS/AF); country = ISO2; city = free label.
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS region TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS country TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS city TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS state TEXT")  # US state / CA province / INTL
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_server TEXT")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT")  # IANA, optional override
    # General weekly availability for the ladder scheduler. JSONB:
    #   {"tz": "America/New_York", "slots": {"mon":[19,20,21], ...}}
    # Day keys mon..sun; hour ints in the player's tz, 0-23 plus 24=midnight,
    # 25=1am, 26=2am of the following day (covers the ladder's late ET slots).
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS availability JSONB")


def upsert_user(cur, du: dict) -> dict:
    """Upsert a Discord user; return the stored row."""
    cur.execute("""
        INSERT INTO users (discord_id, username, global_name, avatar, last_login)
        VALUES (%s,%s,%s,%s, now())
        ON CONFLICT (discord_id) DO UPDATE SET
            username=EXCLUDED.username, global_name=EXCLUDED.global_name,
            avatar=EXCLUDED.avatar, last_login=now()
        RETURNING discord_id, username, global_name, avatar, canonical_id, is_admin
    """, (str(du.get("id")), du.get("username"), du.get("global_name"), du.get("avatar")))
    return cur.fetchone()

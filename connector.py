"""Sage SEO data connector — read-only, key-authenticated aggregates.

Implements Sage's Customer Data Connector provider protocol so Sage can pull
DeepFrag numbers for content strategy and ground generated articles in real
data. Contract reference: sage-frontend/docs/integrations/fedspend-api-request.md
(FedSpend was the first provider; the envelope literal "fedspend-connector" is
Sage's generic wire-format-v1 marker — its syncer validates that exact string
for every provider, so we emit it despite the name).

Auth: `Authorization: Bearer <key>` against env CONNECTOR_API_KEYS
(comma-separated so keys rotate without code changes), timing-safe compare.
Completely separate from the admin SYNC_SECRET path. Read-only aggregates —
no raw per-match records leave the API. Responses stay well under 1 MB.
"""

import hmac
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

router = APIRouter()

# Hostname junk that must not appear in live-server data (proxies, relays,
# bot lobbies) — same filter family as /api/balancer/servers.
_JUNK_HOST = ("qwfwd", "qtv", "[bots]", "[ bots ]")


def _pg():
    # Lazy import: api.py includes this router at the bottom of its module,
    # so importing back into api at call time is safe (module fully loaded).
    from api import pg
    return pg()


def _auth(authorization: str = Header("")):
    keys = [k.strip() for k in os.environ.get("CONNECTOR_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        raise HTTPException(503, "Connector not configured on this deployment")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token or not any(hmac.compare_digest(token, k) for k in keys):
        raise HTTPException(401, "Invalid connector key")


def _envelope(response: Response, params: dict, data):
    response.headers["Cache-Control"] = "private, max-age=3600"
    return {
        "format": "fedspend-connector",
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": params,
        "data": data,
    }


def _rankings(mode: str, top: int):
    with _pg() as conn:
        cur = conn.cursor()
        # Established players only (rating floor + sigma cap) — mirrors the
        # public rankings' non-provisional population.
        cur.execute("""
            SELECT r.canonical_id,
                   COALESCE(pc.display_name, r.canonical_id) AS display,
                   pc.region,
                   r.mu, r.sigma, r.matches_rated AS matches,
                   r.wins, r.losses, r.avg_ddr, r.avg_frag_diff
            FROM ratings r
            LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
            WHERE r.mode = %(mode)s AND r.map = ''
              AND r.matches_rated >= 10 AND r.sigma <= 150
            ORDER BY r.mu DESC
            LIMIT %(top)s
        """, {"mode": mode, "top": top})
        rows = []
        for i, r in enumerate(cur.fetchall()):
            d = dict(r)
            for k, v in d.items():
                if isinstance(v, float):
                    d[k] = round(v, 2)
            d["rank"] = i + 1
            rows.append(d)
        return rows


@router.get("/api/v1/connector/meta")
def connector_meta(response: Response, _=Depends(_auth)):
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) AS matches, MAX(match_date) AS data_through
            FROM matches WHERE COALESCE(has_bots, 0) = 0
        """)
        tot = dict(cur.fetchone())
        cur.execute("""
            SELECT mode, COUNT(*) AS n FROM ratings
            WHERE map = '' AND matches_rated >= 10 AND sigma <= 150
            GROUP BY mode
        """)
        rated = {r["mode"]: r["n"] for r in cur.fetchall()}
        cur.execute("""
            SELECT COUNT(*) AS n FROM servers
            WHERE is_live AND COALESCE(current_players, 0) > 0
        """)
        live_now = cur.fetchone()["n"]

    now = datetime.now(timezone.utc).isoformat()
    return _envelope(response, {}, {
        "scope": "quakeworld-competitive",
        "data_through": tot["data_through"],
        "totals": {"matches": tot["matches"], "rated_players": rated},
        "datasets": [
            {"key": "rankings-1on1", "rows": rated.get("1on1", 0), "updated_at": now},
            {"key": "rankings-4on4", "rows": rated.get("4on4", 0), "updated_at": now},
            {"key": "map-activity", "rows": None, "updated_at": now},
            {"key": "activity-trends", "rows": None, "updated_at": now},
            {"key": "live-servers", "rows": live_now, "updated_at": now},
        ],
        "docs_url": "https://raw.githubusercontent.com/pfsf-2026/deepfrag/main/docs/api_connector.md",
    })


@router.get("/api/v1/connector/rankings-1on1")
def connector_rankings_1on1(response: Response, top: int = Query(50, ge=1, le=200), _=Depends(_auth)):
    return _envelope(response, {"top": top}, _rankings("1on1", top))


@router.get("/api/v1/connector/rankings-4on4")
def connector_rankings_4on4(response: Response, top: int = Query(50, ge=1, le=200), _=Depends(_auth)):
    return _envelope(response, {"top": top}, _rankings("4on4", top))


@router.get("/api/v1/connector/map-activity")
def connector_map_activity(response: Response, min_games: int = Query(25, ge=1), _=Depends(_auth)):
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT match_mode AS mode, match_map AS map, COUNT(*) AS games
            FROM matches
            WHERE COALESCE(has_bots, 0) = 0 AND match_mode IN ('1on1', '2on2', '4on4')
              AND match_map IS NOT NULL
            GROUP BY 1, 2
            HAVING COUNT(*) >= %(min)s
            ORDER BY 1, games DESC
        """, {"min": min_games})
        data = [dict(r) for r in cur.fetchall()]
    return _envelope(response, {"min_games": min_games}, data)


@router.get("/api/v1/connector/activity-trends")
def connector_activity_trends(response: Response, weeks: int = Query(26, ge=4, le=104), _=Depends(_auth)):
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT to_char(date_trunc('week', m.match_date::timestamptz), 'YYYY-MM-DD') AS week_start,
                   m.match_mode AS mode,
                   COUNT(DISTINCT m.match_id) AS games,
                   COUNT(DISTINCT p.canonical_id) AS players
            FROM matches m
            JOIN players p ON p.match_id = m.match_id
            WHERE COALESCE(m.has_bots, 0) = 0
              AND m.match_mode IN ('1on1', '2on2', '4on4')
              AND m.match_date::timestamptz >= now() - (%(weeks)s || ' weeks')::interval
            GROUP BY 1, 2
            ORDER BY 1, 2
        """, {"weeks": weeks})
        data = [dict(r) for r in cur.fetchall()]
    return _envelope(response, {"weeks": weeks}, data)


@router.get("/api/v1/connector/live-servers")
def connector_live_servers(response: Response, _=Depends(_auth)):
    with _pg() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT hostname, city, region,
                   current_map AS map, current_mode AS mode,
                   current_players AS players
            FROM servers
            WHERE is_live AND COALESCE(current_players, 0) > 0
            ORDER BY current_players DESC
        """)
        data = [dict(r) for r in cur.fetchall()
                if not any(j in (r["hostname"] or "").lower() for j in _JUNK_HOST)]
    return _envelope(response, {}, data)

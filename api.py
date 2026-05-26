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

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query, Response
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

app = FastAPI(title="DeepFrag API", version="0.1")

# Compress rankings (240KB → ~30KB) and any future large payloads.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Wide-open CORS for now — only static JSON is served and the only consumer
# is the Cloudflare Pages frontend. Tighten when we add write endpoints.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@contextmanager
def pg():
    """Per-request Postgres connection. Cloud SQL connection pooling will come
    later; for now a fresh connection per request is fine (~10ms overhead)."""
    conn = psycopg2.connect(PG_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/api/health")
def health():
    with pg() as conn:
        v = conn.cursor()
        v.execute("SELECT count(*) AS n FROM matches")
        matches = v.fetchone()["n"]
    return {"ok": True, "matches": matches, "now": datetime.now(timezone.utc).isoformat()}


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
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
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
            SELECT r.canonical_id,
                   COALESCE(pc.display_name, r.canonical_id) AS display,
                   pc.region, pc.region_confidence,
                   r.mu, r.sigma, r.conservative,
                   COALESCE(r.unique_opponents, 0) AS unique_opponents,
                   r.matches_rated, r.wins, r.losses, r.draws,
                   lm.last_match,
                   COALESCE(re.recent_matches, 0) AS recent_matches
            FROM ratings r
            LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
            LEFT JOIN last_match_by_cid lm ON lm.canonical_id = r.canonical_id
            LEFT JOIN recent_by_cid re ON re.canonical_id = r.canonical_id
            WHERE r.mode = %(mode)s AND r.map = '' AND r.matches_rated >= %(min)s
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
            "tier": tier_for(conservative_eff, cutoffs),
        })

    out.sort(key=lambda x: -x["conservative"])
    for i, p in enumerate(out[:limit]):
        p["rank"] = i + 1
    return {"mode": mode, "count": len(out), "players": out[:limit]}


# ── Player profile (lightweight version — only the fields the UI actually shows on first load) ─

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

@app.get("/api/stats/leaderboards")
def stats_leaderboards(
    response: Response,
    mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"),
    map: str = Query("all", description="Map name or 'all'"),
    region: str = Query("all", description="EU/NA/SA/OC/AS/AF or 'all'"),
    min_matches: int = Query(25, ge=5, le=10_000),
    top: int = Query(10, ge=1, le=100),
):
    """Aggregate per-player stats once, slice into one top-N leaderboard per
    stat. 1on1 only for now — 2on2/4on4 wait on team rating methodology."""
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"
    if mode != "1on1":
        return {"mode": mode, "leaderboards": {}, "note": "Only 1on1 leaderboards are available right now."}

    sql, params = stats_pg.stats_query(mode=mode, map_name=map, region=region, min_matches=min_matches)
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

    return {
        "hostname": host_root,
        "meta": dict(meta),
        "stats": stats,
        "top_maps": top_maps,
        "top_by_matches": top_by_matches,
        "top_by_rating": top_by_rating,
        "weekly_activity": weekly,
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
    """Per-map TrueSkill leaderboard. Used by the Maps deep-dive's rank pill
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


@app.get("/api/maps")
def list_maps(mode: str = Query("1on1", pattern="^(1on1|2on2|4on4)$"), min_players: int = Query(5, ge=1, le=1000)):
    """List every map that has TrueSkill ratings in this mode, sorted by how many
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
    """Per-match TrueSkill trajectory for a player. Each row is one rated match
    with mu_after, sigma_after, conservative-after, delta, opponent. Used to draw
    the ELO history chart on the profile page. High default limit so even players
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
    # Profile data only changes when rate.py runs (≈ daily). Cache for 30min at the
    # CDN edge + serve-stale-while-revalidating for a day so window-pill clicks are
    # instant even on cold cache misses.
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=3600"

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
        # Lifetime per-map stats for this player in 1on1, joined with per-map TrueSkill.
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
            WHERE LOWER(pc.display_name) LIKE %s OR pc.canonical_id LIKE %s
            ORDER BY matches DESC
            LIMIT %s
        """, (pattern, pattern, limit))
        return {"q": q, "results": cur.fetchall()}

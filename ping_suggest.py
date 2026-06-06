#!/usr/bin/env python3
"""Best-server suggestion for a KOTH 2v2 match, from real ping history.

For the two teams' rostered players, pull each player's MEDIAN ping to each NA
server they've played, then recommend the NA server that minimizes the worst
player's ping (fairest), tie-broken by average. Players with no ping history to a
server fall back to a distance estimate from their self-reported state centroid
(marked estimated). Geolocation is only the fallback — real pings drive it.
"""
from __future__ import annotations

import math

# Rough centroids for the location fallback (lat, lon). US states + DC, a few CA
# provinces. Only used when a player has no ping history to a candidate server.
STATE_CENTROIDS = {
    "AL": (32.8, -86.8), "AK": (64.2, -149.5), "AZ": (34.3, -111.7), "AR": (34.9, -92.4),
    "CA": (37.2, -119.3), "CO": (39.0, -105.5), "CT": (41.6, -72.7), "DE": (39.0, -75.5),
    "DC": (38.9, -77.0), "FL": (28.6, -82.4), "GA": (32.6, -83.4), "HI": (20.3, -156.4),
    "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3), "IA": (42.0, -93.5),
    "KS": (38.5, -98.4), "KY": (37.5, -85.3), "LA": (31.0, -92.0), "ME": (45.4, -69.2),
    "MD": (39.0, -76.8), "MA": (42.3, -71.8), "MI": (44.3, -85.4), "MN": (46.3, -94.3),
    "MS": (32.7, -89.7), "MO": (38.4, -92.5), "MT": (47.0, -109.6), "NE": (41.5, -99.8),
    "NV": (39.3, -116.6), "NH": (43.7, -71.6), "NJ": (40.2, -74.7), "NM": (34.4, -106.1),
    "NY": (42.9, -75.5), "NC": (35.6, -79.4), "ND": (47.4, -100.5), "OH": (40.3, -82.8),
    "OK": (35.6, -97.5), "OR": (44.0, -120.5), "PA": (40.9, -77.8), "RI": (41.7, -71.6),
    "SC": (33.9, -80.9), "SD": (44.4, -100.2), "TN": (35.9, -86.4), "TX": (31.5, -99.3),
    "UT": (39.3, -111.7), "VT": (44.1, -72.7), "VA": (37.5, -78.9), "WA": (47.4, -120.5),
    "WV": (38.6, -80.6), "WI": (44.6, -89.9), "WY": (43.0, -107.5),
    "AB": (53.9, -116.6), "BC": (53.7, -127.6), "MB": (53.8, -98.8), "ON": (51.3, -85.3),
    "QC": (52.9, -73.5),
}


def _haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _est_ping_from_distance(km: float) -> int:
    """Very rough ms estimate from distance: light in fiber + routing overhead."""
    return int(round(20 + km * 0.025))


def suggest_servers(cur, player_ids: list[str], states: dict | None = None, top: int = 3,
                    allow_sa: bool = False):
    """player_ids: canonical_ids of all rostered players. states: {canonical_id:
    state_code} for the distance fallback. allow_sa=True (Brazil-vs-Brazil match)
    also considers SA/BR servers. Returns ranked server suggestions:
      [{host, country, city, max_ping, avg_ping, n_real, pings:[{player,ping,est}]}]
    """
    states = states or {}
    if not player_ids:
        return []

    region_where = ("region IN ('NA','SA') OR country IN ('US','CA','BR')" if allow_sa
                    else "region='NA' OR country IN ('US','CA')")
    # Median ping per (player, candidate host) from match history.
    cur.execute(f"""
        WITH na AS (
            SELECT DISTINCT ON (split_part(hostname,':',1)) split_part(hostname,':',1) AS host,
                   country, city, lat, lon
            FROM servers
            WHERE {region_where}
            ORDER BY split_part(hostname,':',1), is_live DESC NULLS LAST
        )
        SELECT p.canonical_id, split_part(m.server_hostname,':',1) AS host,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY p.player_ping) AS med, COUNT(*) AS n,
               na.country, na.city, na.lat, na.lon
        FROM players p
        JOIN matches m ON m.id = p.match_id
        JOIN na ON na.host = split_part(m.server_hostname,':',1)
        WHERE p.canonical_id = ANY(%s) AND p.player_ping BETWEEN 5 AND 400
        GROUP BY p.canonical_id, host, na.country, na.city, na.lat, na.lon
        HAVING COUNT(*) >= 2
    """, (player_ids,))
    rows = cur.fetchall()

    servers = {}   # host -> {country, city, lat, lon}
    real = {}      # (player, host) -> med ping
    for r in rows:
        servers[r["host"]] = {"country": r["country"], "city": r["city"], "lat": r["lat"], "lon": r["lon"]}
        real[(r["canonical_id"], r["host"])] = float(r["med"])

    if not servers:
        return []

    out = []
    for host, meta in servers.items():
        pings = []
        for pid in player_ids:
            if (pid, host) in real:
                pings.append({"player": pid, "ping": round(real[(pid, host)]), "est": False})
            elif states.get(pid) in STATE_CENTROIDS and meta["lat"] is not None:
                km = _haversine_km(STATE_CENTROIDS[states[pid]], (meta["lat"], meta["lon"]))
                pings.append({"player": pid, "ping": _est_ping_from_distance(km), "est": True})
            else:
                pings.append({"player": pid, "ping": None, "est": False})
        known = [p["ping"] for p in pings if p["ping"] is not None]
        if not known:
            continue
        out.append({
            "host": host, "country": meta["country"], "city": meta["city"],
            "max_ping": max(known), "avg_ping": round(sum(known) / len(known)),
            "n_real": sum(1 for p in pings if not p["est"] and p["ping"] is not None),
            "covered": len(known), "players": len(player_ids), "pings": pings,
        })

    # Fairest first: most players covered, then lowest worst-ping, then avg.
    out.sort(key=lambda s: (-s["covered"], s["max_ping"], s["avg_ping"]))
    return out[:top]

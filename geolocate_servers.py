#!/usr/bin/env python3
"""Resolve every distinct server_hostname → IP → country/region, cache in `servers`,
then backfill matches.server_country / matches.server_region.

Uses ip-api.com batch endpoint (free, no auth, 100 IPs/request, 45 req/min).

Re-runs are cheap: only hostnames not in `servers` (or with `resolve_error`) get
re-queried. Run after sync.py to enrich new servers as they appear.
"""

from __future__ import annotations  # so `str | None` works on Python 3.9

import argparse
import re
import socket
import time
from datetime import datetime, timezone

import requests

import db as dbmod

# Country → coarse region. Buckets the regions in line with how QW players
# actually cluster competitively. Anything unmapped falls back to "OTHER".
REGION = {
    # North America
    "US": "NA", "CA": "NA", "MX": "NA",
    # Europe
    "GB": "EU", "IE": "EU", "FR": "EU", "DE": "EU", "NL": "EU", "BE": "EU",
    "LU": "EU", "CH": "EU", "AT": "EU", "IT": "EU", "ES": "EU", "PT": "EU",
    "SE": "EU", "NO": "EU", "DK": "EU", "FI": "EU", "IS": "EU",
    "PL": "EU", "CZ": "EU", "SK": "EU", "HU": "EU", "RO": "EU", "BG": "EU",
    "EE": "EU", "LV": "EU", "LT": "EU",
    "RU": "EU", "UA": "EU", "BY": "EU", "MD": "EU",
    "GR": "EU", "TR": "EU", "HR": "EU", "SI": "EU", "BA": "EU", "RS": "EU", "MK": "EU",
    "AL": "EU", "CY": "EU", "MT": "EU",
    # Oceania
    "AU": "OC", "NZ": "OC",
    # South America
    "BR": "SA", "AR": "SA", "CL": "SA", "PE": "SA", "CO": "SA", "VE": "SA",
    "UY": "SA", "PY": "SA", "EC": "SA", "BO": "SA",
    # Asia
    "JP": "AS", "KR": "AS", "CN": "AS", "TW": "AS", "HK": "AS", "SG": "AS",
    "TH": "AS", "MY": "AS", "ID": "AS", "PH": "AS", "VN": "AS", "IN": "AS",
    "IL": "AS", "AE": "AS", "SA": "AS",
    # Africa
    "ZA": "AF", "EG": "AF", "MA": "AF", "NG": "AF", "KE": "AF",
}


def clean_hostname(raw: str) -> str:
    """Extract a DNS-resolvable hostname from the hub's friendly name field.
    'ny.quake.world:28501 NAQW'        → 'ny.quake.world'
    'KTX #1 @ qw.servequake.com'       → 'qw.servequake.com'
    'The-Den'                          → 'the-den' (will fail DNS, name-hint takes over)
    """
    if not raw:
        return ""
    s = raw.strip()
    # @-separated: 'KTX #1 @ qw.servequake.com' — take the part after @
    if "@" in s:
        s = s.split("@")[-1].strip()
    # Strip 'host:port garbage' → 'host'
    s = re.split(r"[\s:]", s, maxsplit=1)[0]
    return s.strip().lower()


# Hostname-name pattern → (country, region). Catches servers where DNS fails or
# the hostname is a friendly name with no DNS at all (e.g. "Spider MSK Antilag",
# "Thickshaker Vic Antilag", "QUAKE.SE KTX", "Brasil"). Patterns are matched
# case-insensitively against the FULL raw hostname.
NAME_HINTS = [
    # Country/city tokens (most specific first). Order matters — earlier rules
    # win; specific server names should be near the top so they don't get
    # captured by broader regexes below.
    (r"\bmsk\b|moscow|moscw", "RU", "EU"),
    (r"\bvic\b|melbourne|sydney|brisbane", "AU", "OC"),
    (r"\bauckland\b|\bwellington\b|\.nz\b", "NZ", "OC"),
    (r"brasil|brazil|\.br\b|sao\.paulo|saopaulo|rio|\bilha\b|\bring\b @ ilha", "BR", "SA"),
    (r"\bargentin", "AR", "SA"),
    # The-Den is Cronus's box in Denver, CO. Pin BEFORE the generic
    # German "den/the-den" hint below (which originally matched it to DE).
    (r"the.?den|cronus", "US", "NA"),
    (r"pentagon|\bbavaria\b|\bbayern\b|hamburg|munich|berlin|cologne", "DE", "EU"),
    (r"thickshaker|antilag", "AU", "OC"),  # known Aussie comp servers
    (r"zasadzka|warsaw|\.pl\b", "PL", "EU"),
    (r"quake\.se|\.se\b|stockholm|sweden|qhlan", "SE", "EU"),
    (r"\.no\b|oslo|norway", "NO", "EU"),
    (r"\.fi\b|helsinki|finland", "FI", "EU"),
    (r"\.dk\b|copenhagen|denmark", "DK", "EU"),
    (r"\.de\b|berlin|frankfurt|munich|germany", "DE", "EU"),
    (r"\.nl\b|amsterdam|rotterdam|netherlands|hollnd|qlash", "NL", "EU"),
    (r"\.uk\b|\.co\.uk|london|britain|england", "GB", "EU"),
    (r"\.ie\b|dublin|ireland", "IE", "EU"),
    (r"\.fr\b|paris|france", "FR", "EU"),
    (r"\.es\b|madrid|barcelona|spain", "ES", "EU"),
    (r"\.it\b|rome|milan|italy", "IT", "EU"),
    (r"\.pt\b|lisbon|portugal", "PT", "EU"),
    # NA — region/city tokens
    (r"\bny\b|new.?york|nj\.|newark", "US", "NA"),
    (r"chicago|chi\.|illinois", "US", "NA"),
    (r"dallas|texas|tx\.", "US", "NA"),
    (r"miami|florida|fl\.", "US", "NA"),
    (r"denver|colorado|\bco\.", "US", "NA"),  # Denver and CO state servers
    (r"\.ca\b|toronto|ontario|montreal|canada|vancouver", "CA", "NA"),
    (r"naqw|us\.|usa", "US", "NA"),
    # Generic EU/NA fallback tokens
    (r"\beu\b|europe", "DE", "EU"),
    (r"\bna\b|america", "US", "NA"),
]

# Manual location overrides for servers whose IP geolocation is wrong (cloud
# hosts often report data-center city, not where the operator actually is).
# Maps canonical hostname → {city, lat, lon}. Applied after IP geo so it wins.
MANUAL_LOCATIONS = {
    "The-Den":         {"city": "Denver", "lat": 39.7392, "lon": -104.9903, "country": "US", "region": "NA"},
    "Cronus-The-Den":  {"city": "Denver", "lat": 39.7392, "lon": -104.9903, "country": "US", "region": "NA"},
}


def hint_region_from_name(raw_name: str):
    """Fallback: try to guess country/region from substrings in the raw hostname.
    Returns (country, region) or (None, None)."""
    if not raw_name:
        return None, None
    n = raw_name.lower()
    for pattern, country, region in NAME_HINTS:
        if re.search(pattern, n):
            return country, region
    return None, None


def resolve_dns(hostname: str) -> str | None:
    """DNS A-record lookup. Returns IP or None on failure."""
    try:
        return socket.gethostbyname(hostname)
    except (socket.gaierror, socket.herror, UnicodeError):
        return None


def batch_geolocate(ips: list) -> dict:
    """POST a batch (up to 100) of IPs to ip-api.com. Returns {ip: row_dict}."""
    if not ips:
        return {}
    # ip-api.com batch: POST with a list of {query, fields} entries
    body = [{"query": ip, "fields": "status,country,countryCode,city,lat,lon,isp,query"} for ip in ips]
    r = requests.post("http://ip-api.com/batch", json=body, timeout=30,
                      headers={"User-Agent": "DeepFrag/0.1"})
    r.raise_for_status()
    return {row["query"]: row for row in r.json()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Re-resolve every hostname, even ones already in the servers table.")
    ap.add_argument("--limit", type=int, help="Only process this many new hostnames (testing).")
    args = ap.parse_args()

    db = dbmod.connect()
    cur = db.cursor()

    # 1. Collect candidates: distinct hostnames in matches not already resolved
    if args.refresh:
        cur.execute("""
            SELECT DISTINCT server_hostname FROM matches
            WHERE server_hostname IS NOT NULL AND server_hostname <> ''
        """)
    else:
        cur.execute("""
            SELECT DISTINCT m.server_hostname FROM matches m
            LEFT JOIN servers s ON s.hostname = m.server_hostname
            WHERE m.server_hostname IS NOT NULL
              AND m.server_hostname <> ''
              AND (s.hostname IS NULL OR s.resolve_error IS NOT NULL)
        """)
    raw_names = [r["server_hostname"] for r in cur.fetchall()]
    if args.limit:
        raw_names = raw_names[: args.limit]
    print(f"Hostnames to (re)resolve: {len(raw_names)}")
    if not raw_names:
        print("Nothing to do. (Already resolved everything; re-run with --refresh to redo.)")
        return

    # 2. DNS resolve in Python (cheap, parallelizable, but serial is fine for <1k)
    print("\nResolving DNS…")
    hostname_to_ip = {}
    for i, raw in enumerate(raw_names, 1):
        clean = clean_hostname(raw)
        if not clean:
            continue
        ip = resolve_dns(clean)
        hostname_to_ip[raw] = ip
        if i % 25 == 0 or i == len(raw_names):
            print(f"  {i}/{len(raw_names)} — last: {clean[:40]:40s} → {ip or 'FAIL'}")

    resolved = {h: ip for h, ip in hostname_to_ip.items() if ip}
    failed_dns = [h for h, ip in hostname_to_ip.items() if not ip]
    print(f"\nDNS: {len(resolved)} resolved, {len(failed_dns)} failed.")

    # 3. Batch-geolocate the IPs via ip-api.com (45 reqs/min, 100 IPs per req)
    print("\nGeolocating IPs via ip-api.com…")
    now = datetime.now(timezone.utc).isoformat()
    rows_to_upsert = []
    ips = list(set(resolved.values()))
    for batch_start in range(0, len(ips), 100):
        batch = ips[batch_start : batch_start + 100]
        try:
            results = batch_geolocate(batch)
        except requests.RequestException as e:
            print(f"  Batch {batch_start}: API error: {e}")
            continue
        for ip in batch:
            r = results.get(ip, {})
            if r.get("status") == "success":
                cc = r.get("countryCode", "")
                rows_to_upsert.append({
                    "ip": ip,
                    "country": cc,
                    "region": REGION.get(cc, "OTHER"),
                    "city": r.get("city"),
                    "lat": r.get("lat"),
                    "lon": r.get("lon"),
                    "isp": r.get("isp"),
                    "error": None,
                })
            else:
                rows_to_upsert.append({"ip": ip, "country": None, "region": None,
                                        "city": None, "lat": None, "lon": None, "isp": None,
                                        "error": r.get("message", "lookup_failed")})
        print(f"  {min(batch_start + 100, len(ips))}/{len(ips)} IPs done")
        time.sleep(1.5)  # rate limit cushion

    geo_by_ip = {r["ip"]: r for r in rows_to_upsert}

    # 4. Upsert into `servers` table
    print(f"\nUpserting {len(resolved)} resolved + {len(failed_dns)} failed-DNS into servers…")
    name_hint_count = 0
    for hostname, ip in resolved.items():
        g = geo_by_ip.get(ip, {})
        country = g.get("country")
        region = g.get("region")
        # Use name hint as fallback if IP geo didn't return anything useful.
        if not country:
            hint_country, hint_region = hint_region_from_name(hostname)
            if hint_country:
                country, region = hint_country, hint_region
                name_hint_count += 1
        cur.execute("""
            INSERT INTO servers (hostname, ip, country, region, city, lat, lon, isp, resolved_at, resolve_error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hostname) DO UPDATE SET
                ip=EXCLUDED.ip, country=EXCLUDED.country, region=EXCLUDED.region,
                city=EXCLUDED.city, lat=EXCLUDED.lat, lon=EXCLUDED.lon, isp=EXCLUDED.isp,
                resolved_at=EXCLUDED.resolved_at, resolve_error=EXCLUDED.resolve_error
        """, (hostname, ip, country, region, g.get("city"),
              g.get("lat"), g.get("lon"), g.get("isp"), now, g.get("error")))
    # For failed-DNS hostnames, try the name hint — many friendly server names have
    # region/country tokens baked in (MSK, Vic, Brasil, .SE, etc.).
    for hostname in failed_dns:
        hint_country, hint_region = hint_region_from_name(hostname)
        if hint_country:
            name_hint_count += 1
            cur.execute("""
                INSERT INTO servers (hostname, country, region, resolved_at, resolve_error)
                VALUES (%s, %s, %s, %s, 'dns_failed_name_hint')
                ON CONFLICT (hostname) DO UPDATE SET
                  country=EXCLUDED.country, region=EXCLUDED.region,
                  resolved_at=EXCLUDED.resolved_at, resolve_error=EXCLUDED.resolve_error
            """, (hostname, hint_country, hint_region, now))
        else:
            cur.execute("""
                INSERT INTO servers (hostname, resolved_at, resolve_error)
                VALUES (%s, %s, 'dns_failed')
                ON CONFLICT (hostname) DO UPDATE SET resolved_at=EXCLUDED.resolved_at, resolve_error='dns_failed'
            """, (hostname, now))
    print(f"  Name-hint fallback rescued {name_hint_count} additional servers")
    db.commit()

    # 5. Backfill matches.server_country / server_region from servers
    print("\nBackfilling matches.server_country / server_region…")
    cur.execute("""
        UPDATE matches m SET server_country = s.country, server_region = s.region
        FROM servers s
        WHERE s.hostname = m.server_hostname
          AND s.country IS NOT NULL
          AND (m.server_country IS DISTINCT FROM s.country OR m.server_region IS DISTINCT FROM s.region)
    """)
    print(f"  Updated {cur.rowcount:,} match rows")
    db.commit()

    # 6. Report
    print("\nRegion distribution across servers:")
    cur.execute("SELECT region, COUNT(*) AS n FROM servers WHERE region IS NOT NULL GROUP BY region ORDER BY n DESC")
    for r in cur.fetchall():
        print(f"  {r['region']:6} {r['n']:4} servers")
    cur.execute("SELECT country, COUNT(*) AS n FROM servers WHERE country IS NOT NULL GROUP BY country ORDER BY n DESC LIMIT 15")
    print("\nTop 15 countries by server count:")
    for r in cur.fetchall():
        print(f"  {r['country']:4} {r['n']:4} servers")
    cur.execute("SELECT server_region, COUNT(*) AS n FROM matches WHERE server_region IS NOT NULL GROUP BY server_region ORDER BY n DESC")
    print("\nMatches per region:")
    for r in cur.fetchall():
        print(f"  {r['server_region']:6} {r['n']:8,} matches")

    cur.close()


if __name__ == "__main__":
    main()

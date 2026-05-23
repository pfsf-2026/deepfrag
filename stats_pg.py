"""1on1 stat leaderboards — aggregates per-player mechanical stats in ONE query,
slices the result into 11 mini-leaderboards. Adding modes later (2on2/4on4) will
extend this; keeping 1on1-only for now per the rating-methodology-first plan.
"""

from __future__ import annotations


# Each entry: (stat_id, display name, sort direction ['desc' or 'asc'], format string)
# Column names match the AS aliases in the SQL below.
STATS_1ON1 = [
    ("lg_pct",          "LG accuracy",            "desc", "{:.1%}"),
    ("rl_pct",          "RL accuracy",            "desc", "{:.1%}"),
    ("frag_diff",       "±frag avg",              "desc", "{:+.1f}"),
    ("ddr",             "Damage diff ratio",      "desc", "{:.2f}"),
    ("net_dmg",         "Net damage / match",     "desc", "{:+,.0f}"),
    ("dmg_given",       "Total damage given",     "desc", "{:,.0f}"),
    ("dmg_taken",       "Total damage taken",     "asc",  "{:,.0f}"),  # lower better
    ("ra_per_match",    "RA / match",             "desc", "{:.2f}"),
    ("mh_per_match",    "Mega / match",           "desc", "{:.2f}"),
    ("ya_per_match",    "YA / match",             "desc", "{:.2f}"),
    ("avg_frags",       "Avg frags / match",      "desc", "{:.1f}"),
    ("avg_speed",       "Avg speed",              "desc", "{:.0f}"),
    ("spawnfrags_taken","Spawnfrags taken / match","asc", "{:.2f}"),   # lower better
]


def stats_query(mode: str = "1on1", map_name: str = "", region: str = "",
                min_matches: int = 25) -> tuple[str, dict]:
    """Build the SQL + params dict for the 1on1 stats aggregation.

    `spawnfrags_taken` = opponent's `player_spawnfrags` in each 1on1 match
    (i.e., how many times the opponent killed THIS player on spawn). Joining
    p2 = the other player in the match makes this trivial.
    """
    where_extra = ""
    params = {"mode": mode, "min_matches": min_matches}
    if map_name and map_name != "all":
        where_extra += " AND m.match_map = %(map)s"
        params["map"] = map_name
    region_clause = ""
    if region and region != "all":
        region_clause = "AND pc.region = %(region)s"
        params["region"] = region

    sql = f"""
        WITH player_stats AS (
            SELECT p.canonical_id,
                   COALESCE(pc.display_name, p.canonical_id) AS display,
                   pc.region,
                   COUNT(*) AS matches,
                   AVG(p.player_lg_hits::float / NULLIF(p.player_lg_attacks, 0)) AS lg_pct,
                   AVG(p.player_rl_virtual::float / NULLIF(p.player_rl_attacks, 0)) AS rl_pct,
                   AVG(p.player_frags - p.player_deaths) AS frag_diff,
                   AVG(p.player_damage_given) AS dmg_given,
                   AVG(p.player_damage_taken) AS dmg_taken,
                   AVG(p.player_damage_given - p.player_damage_taken) AS net_dmg,
                   SUM(p.player_damage_given)::float / NULLIF(SUM(p.player_damage_taken), 0) AS ddr,
                   AVG(p.player_ra_taken) AS ra_per_match,
                   AVG(p.player_health100_taken) AS mh_per_match,
                   AVG(p.player_ya_taken) AS ya_per_match,
                   AVG(p.player_frags) AS avg_frags,
                   AVG(p.player_speed_avg) AS avg_speed,
                   AVG((SELECT p2.player_spawnfrags FROM players p2
                        WHERE p2.match_id = p.match_id AND p2.player_name <> p.player_name
                        LIMIT 1)) AS spawnfrags_taken
            FROM players p
            JOIN matches m ON m.match_id = p.match_id
            LEFT JOIN players_canonical pc ON pc.canonical_id = p.canonical_id
            WHERE m.match_mode = %(mode)s
              AND p.canonical_id IS NOT NULL
              {where_extra}
              {region_clause}
            GROUP BY p.canonical_id, pc.display_name, pc.region
            HAVING COUNT(*) >= %(min_matches)s
        )
        SELECT * FROM player_stats
    """
    return sql, params


def build_leaderboards(rows: list, top_n: int = 5) -> dict:
    """Slice per-player stats into one top-N leaderboard per stat. Honors
    sort direction (asc for 'lower-is-better' stats)."""
    out = {}
    for stat_id, display, direction, fmt in STATS_1ON1:
        # Filter out players with no value for this stat (e.g., never shot LG)
        valid = [r for r in rows if r.get(stat_id) is not None]
        reverse = (direction == "desc")
        valid.sort(key=lambda r: r[stat_id], reverse=reverse)
        leaderboard = []
        for i, r in enumerate(valid[:top_n], start=1):
            v = r[stat_id]
            # Convert decimal (for accuracy stats) so JSON serializes correctly
            try:
                v = float(v)
            except (TypeError, ValueError):
                pass
            leaderboard.append({
                "rank": i,
                "canonical_id": r["canonical_id"],
                "display": r["display"],
                "region": r.get("region"),
                "value": v,
                "formatted": fmt.format(v) if v is not None else "—",
                "matches": r["matches"],
            })
        out[stat_id] = {
            "display": display,
            "direction": direction,
            "top": leaderboard,
        }
    return out

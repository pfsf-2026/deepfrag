#!/usr/bin/env python3
"""Generate a profile.json describing one player's stats across all synced matches.

The JSON is meant to be consumed by a static UI (public/index.html). One file per
player, regenerated after each sync. Schema is intentionally denormalized so the
client doesn't need to do joins.

Player identity is messy in QW: the same person uses different color-code variants
and capitalizations across matches. Pass `--alias` repeatedly to fold variants into
one canonical identity, e.g.:

    export.py cronus --alias cronus --alias 'cr\\5onus' --alias Cronus
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tiers import tier_for

# Time windows (in days) we pre-compute aggregates for. `None` means "all time".
# Adding a window inflates profile.json roughly linearly — keep this list short.
DEFAULT_WINDOWS = [("7", 7), ("30", 30), ("90", 90), ("365", 365), ("all", None)]


def _connect(db_path):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return db


def _round(v, digits=3):
    return None if v is None else round(v, digits)


# ─── Identity plumbing ─────────────────────────────────────────────────────
# All aggregation queries are scoped to a single canonical_id. The players table
# has canonical_id pre-populated by canonicalize.py, so we just filter on that.
# The old `--alias`-style multi-name matching is no longer needed.

def _alias_placeholders(aliases):
    """Legacy helper, kept for any old call sites that pass an alias list."""
    return ",".join(f":alias{i}" for i in range(len(aliases)))


def _scope_kwargs(aliases):
    """Legacy helper. New code uses _canonical_kwargs."""
    return {f"alias{i}": a.lower() for i, a in enumerate(aliases)}


def _canonical_kwargs(canonical_id):
    return {"canonical_id": canonical_id}


def _scope_kwargs(scope):
    """Polymorphic kwargs builder: string scope → canonical_id; list → alias list."""
    if isinstance(scope, str):
        return _canonical_kwargs(scope)
    return _alias_kwargs(scope)


def _date_filter(days, offset_days=0):
    """Return (sql_fragment, params) that restricts matches to a date window.

    Window is `days` long, ending `offset_days` ago. So:
      _date_filter(90)         → last 90 days (today-90 ... today)
      _date_filter(90, 90)     → prior 90 days (today-180 ... today-90)
      _date_filter(None)       → no filter (all-time)
    """
    if days is None:
        return "", {}
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=offset_days)
    start = end - timedelta(days=days)
    if offset_days > 0:
        return "AND match_date >= :since_date AND match_date < :until_date", {
            "since_date": start.isoformat(),
            "until_date": end.isoformat(),
        }
    return "AND match_date >= :since_date", {"since_date": start.isoformat()}


def _win_cte(aliases_or_cid):
    """Build the WITH-clause that scopes player_match to our player and computes outcomes.

    Accepts either:
      - a string canonical_id (preferred, post-canonicalization)
      - a list of name aliases (legacy fallback for un-canonicalized DBs)

    All downstream aggregation queries prepend this CTE then SELECT from match_outcomes.
    Excludes match_mode='3on3' globally — too rare to bucket meaningfully.
    """
    if isinstance(aliases_or_cid, str):
        # New path: filter by canonical_id directly (fast, indexed).
        scope_clause = "p.canonical_id = :canonical_id"
    else:
        # Legacy: alias list. Kept so older invocations don't break.
        scope_clause = f"lower(p.player_name) IN ({_alias_placeholders(aliases_or_cid)})"
    # PERF: team_frags pre-filters to player_match's match_ids. Without this
    # restriction it scans the entire (now 534k-row) players table on every call.
    return f"""
WITH player_match AS (
    SELECT p.*, m.match_mode, m.match_map, m.server_hostname, m.match_date, m.match_dmm, m.has_bots
    FROM players p JOIN matches m ON m.match_id = p.match_id
    WHERE {scope_clause}
      AND m.match_mode != '3on3'
),
team_frags AS (
    SELECT match_id, player_team, sum(player_frags) AS team_total
    FROM players
    WHERE match_id IN (SELECT match_id FROM player_match)
    GROUP BY match_id, player_team
),
match_outcomes AS (
    SELECT
        pm.*,
        -- For 1on1: compare to opponent's frags directly.
        -- For team modes: compare own team's frags vs the other team's frags.
        CASE
            WHEN pm.match_mode = '1on1' THEN (
                SELECT CASE
                    WHEN pm.player_frags > p2.player_frags THEN 'win'
                    WHEN pm.player_frags < p2.player_frags THEN 'loss'
                    ELSE 'draw' END
                FROM players p2
                WHERE p2.match_id = pm.match_id AND p2.player_name <> pm.player_name
                LIMIT 1
            )
            ELSE (
                SELECT CASE
                    WHEN tf_self.team_total > max(tf_other.team_total) THEN 'win'
                    WHEN tf_self.team_total < max(tf_other.team_total) THEN 'loss'
                    ELSE 'draw' END
                FROM team_frags tf_self
                JOIN team_frags tf_other
                  ON tf_other.match_id = tf_self.match_id AND tf_other.player_team <> tf_self.player_team
                WHERE tf_self.match_id = pm.match_id AND tf_self.player_team = pm.player_team
            )
        END AS outcome,
        CASE WHEN pm.match_mode = '1on1' THEN (
            -- Resolve opponent through identity layer: canonical_id → display_name.
            -- Falls back to raw player_name if canonical_id wasn't set on the row.
            SELECT COALESCE(pc.display_name, p2.canonical_id, p2.player_name)
            FROM players p2
            LEFT JOIN players_canonical pc ON pc.canonical_id = p2.canonical_id
            WHERE p2.match_id = pm.match_id AND p2.player_name <> pm.player_name LIMIT 1
        ) END AS opponent_name,
        CASE WHEN pm.match_mode = '1on1' THEN (
            SELECT p2.canonical_id FROM players p2
            WHERE p2.match_id = pm.match_id AND p2.player_name <> pm.player_name LIMIT 1
        ) END AS opponent_canonical_id,
        CASE WHEN pm.match_mode = '1on1' THEN (
            SELECT p2.player_frags FROM players p2
            WHERE p2.match_id = pm.match_id AND p2.player_name <> pm.player_name LIMIT 1
        ) END AS opponent_frags
    FROM player_match pm
)
"""


# ─── Top-level sections ───────────────────────────────────────────────────

def career(db, player, aliases):
    # career_totals is keyed by the lookup name (canonical_id-equivalent) used at scrape time.
    # If aliases is a string canonical_id, look that up directly; if it's a legacy alias list,
    # try the first element (used to be the canonical player name passed on CLI).
    lookup = aliases if isinstance(aliases, str) else (player or aliases[0])
    row = db.execute(
        "SELECT * FROM career_totals WHERE lower(player_name) = lower(?)",
        (lookup,),
    ).fetchone()
    lifetime = None
    if row:
        lifetime = {
            "matches": row["total_matches"],
            "by_mode": {
                "1on1": row["total_1on1"],
                "2on2": row["total_2on2"],
                "4on4": row["total_4on4"],
            },
            "frags": row["total_frags"],
            "time_mins": row["total_time_mins"],
            "fpm": row["fpm"],
            "scraped_at": row["scraped_at"],
        }
    if isinstance(aliases, str):
        where_clause = "p.canonical_id = :canonical_id"
    else:
        where_clause = f"lower(p.player_name) IN ({_alias_placeholders(aliases)})"
    hub_row = db.execute(
        f"""
        SELECT count(DISTINCT m.match_id) AS n,
               min(m.match_date) AS first_date,
               max(m.match_date) AS last_date
        FROM matches m JOIN players p ON p.match_id = m.match_id
        WHERE {where_clause}
        """,
        _scope_kwargs(aliases),
    ).fetchone()
    return {
        "lifetime": lifetime,
        "hub": {
            "matches": hub_row["n"],
            "first_match": hub_row["first_date"],
            "last_match": hub_row["last_date"],
        },
    }


def _aggregate(db, aliases, where_extra="", extra_params=None, days=None, offset_days=0):
    """Compute every per-match average / accuracy we care about for a given slice.

    This is the load-bearing aggregation — used by mode/dmm/window breakdowns and
    consumed by the UI (and eventually by AI analysis). New stats added here
    propagate everywhere automatically, so be thorough.
    """
    date_sql, date_params = _date_filter(days, offset_days)
    params = {**_scope_kwargs(aliases), **(extra_params or {}), **date_params}
    sql = _win_cte(aliases) + f"""
        SELECT
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            sum(CASE WHEN outcome='draw' THEN 1 ELSE 0 END) AS draws,

            -- Frags / kills
            avg(player_frags) AS avg_frags,
            avg(player_deaths) AS avg_deaths,
            avg(player_frags - player_deaths) AS avg_frag_diff,
            avg(player_teamkills) AS avg_teamkills,
            avg(player_spawnfrags) AS avg_spawnfrags,
            avg(player_suicides) AS avg_suicides,

            -- Damage breakdown
            avg(player_damage_given) AS avg_dmg_given,
            avg(player_damage_taken) AS avg_dmg_taken,
            avg(player_damage_enemy_weapons) AS avg_dmg_enemy_weapons,
            avg(player_damage_team) AS avg_dmg_team,
            avg(player_damage_team_weapons) AS avg_dmg_team_weapons,
            avg(player_damage_self) AS avg_dmg_self,
            avg(player_damage_to_die) AS avg_dmg_to_die,

            -- Per-weapon accuracy
            avg(CAST(player_rl_virtual AS REAL) / nullif(player_rl_attacks, 0)) AS rl_accuracy,
            avg(CAST(player_lg_hits AS REAL) / nullif(player_lg_attacks, 0)) AS lg_accuracy,
            avg(CAST(player_sg_hits AS REAL) / nullif(player_sg_attacks, 0)) AS sg_accuracy,
            avg(CAST(player_ssg_hits AS REAL) / nullif(player_ssg_attacks, 0)) AS ssg_accuracy,
            avg(CAST(player_gl_virtual AS REAL) / nullif(player_gl_attacks, 0)) AS gl_accuracy,

            -- Per-weapon volume (attacks per match — useful for "did they use this weapon at all?")
            avg(player_rl_attacks) AS avg_rl_attacks,
            avg(player_lg_attacks) AS avg_lg_attacks,
            avg(player_sg_attacks) AS avg_sg_attacks,
            avg(player_ssg_attacks) AS avg_ssg_attacks,
            avg(player_gl_attacks) AS avg_gl_attacks,

            -- Per-weapon damage to enemies
            avg(player_rl_damage_enemy) AS avg_rl_dmg,
            avg(player_lg_damage_enemy) AS avg_lg_dmg,
            avg(player_sg_damage_enemy) AS avg_sg_dmg,
            avg(player_ssg_damage_enemy) AS avg_ssg_dmg,
            avg(player_rl_directs) AS avg_rl_directs,

            -- Per-weapon kills (only RL/LG track this)
            avg(player_rl_kills_enemy) AS avg_rl_kills,
            avg(player_lg_kills_enemy) AS avg_lg_kills,

            -- RL/LG control (drops vs transfers — being killed and weapon goes to who)
            avg(player_rl_dropped) AS avg_rl_dropped,
            avg(player_rl_taken)   AS avg_rl_taken,
            avg(player_rl_transfer) AS avg_rl_transfer,
            avg(player_lg_dropped) AS avg_lg_dropped,
            avg(player_lg_taken)   AS avg_lg_taken,
            avg(player_lg_transfer) AS avg_lg_transfer,

            -- Item pickups (all tiers)
            avg(player_ra_taken) AS avg_ra,
            avg(player_ya_taken) AS avg_ya,
            avg(player_ga_taken) AS avg_ga,
            avg(player_health15_taken) AS avg_h15,
            avg(player_health25_taken) AS avg_h25,
            avg(player_health100_taken) AS avg_mh,
            avg(player_quad_taken) AS avg_quads,
            avg(player_quad_time)  AS avg_quad_time_secs,
            avg(player_pent_taken) AS avg_pents,
            avg(player_ring_taken) AS avg_rings,
            avg(player_ring_time)  AS avg_ring_time_secs,

            -- Sprees, speed, ping
            avg(player_spree_frag) AS avg_spree_frag,
            avg(player_spree_quad) AS avg_spree_quad,
            avg(player_speed_max)  AS avg_speed_max,
            avg(player_speed_avg)  AS avg_speed_avg,
            avg(player_ping)       AS avg_ping
        FROM match_outcomes
        WHERE 1=1 {where_extra} {date_sql}
    """
    row = db.execute(sql, params).fetchone()
    if not row or not row["matches"]:
        return None
    d = dict(row)
    d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
    # Round all float columns
    for k in list(d.keys()):
        if k in ("matches", "wins", "losses", "draws"):
            continue
        d[k] = _round(d[k])
    return d


def by_mode(db, aliases, days=None, offset_days=0):
    date_sql, date_params = _date_filter(days, offset_days)
    sql = _win_cte(aliases) + f"SELECT DISTINCT match_mode FROM match_outcomes WHERE 1=1 {date_sql}"
    modes = [r[0] for r in db.execute(sql, {**_scope_kwargs(aliases), **date_params}).fetchall()]
    return {mode: _aggregate(db, aliases, "AND match_mode = :mode", {"mode": mode}, days=days, offset_days=offset_days) for mode in modes}


def by_dmm(db, aliases, days=None, offset_days=0):
    date_sql, date_params = _date_filter(days, offset_days)
    sql = _win_cte(aliases) + f"SELECT DISTINCT match_dmm FROM match_outcomes WHERE match_dmm IS NOT NULL {date_sql}"
    dmms = [r[0] for r in db.execute(sql, {**_scope_kwargs(aliases), **date_params}).fetchall()]
    return {str(dmm): _aggregate(db, aliases, "AND match_dmm = :dmm", {"dmm": dmm}, days=days, offset_days=offset_days) for dmm in dmms}


def _per_group(db, aliases, group_col, mode_filter=None, days=None, offset_days=0):
    date_sql, date_params = _date_filter(days, offset_days)
    params = {**_scope_kwargs(aliases), **date_params}
    where_extra = ""
    if mode_filter:
        where_extra = "AND match_mode = :mode"
        params["mode"] = mode_filter
    sql = _win_cte(aliases) + f"""
        SELECT
            {group_col} AS bucket,
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            avg(player_frags) AS avg_frags,
            avg(player_frags - player_deaths) AS avg_frag_diff,
            avg(CAST(player_lg_hits AS REAL) / nullif(player_lg_attacks, 0)) AS lg_accuracy,
            avg(CAST(player_rl_virtual AS REAL) / nullif(player_rl_attacks, 0)) AS rl_accuracy
        FROM match_outcomes
        WHERE {group_col} IS NOT NULL {where_extra} {date_sql}
        GROUP BY bucket
        ORDER BY matches DESC
    """
    out = []
    for row in db.execute(sql, params):
        d = dict(row)
        d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
        for k in ("avg_frags", "avg_frag_diff", "lg_accuracy", "rl_accuracy"):
            d[k] = _round(d[k])
        out.append(d)
    return out


def head_to_head(db, aliases, days=None, offset_days=0):
    """1on1 only: per-opponent record. Groups by canonical_id (so all of the same
    person's name variants merge), labels with display_name from players_canonical."""
    date_sql, date_params = _date_filter(days, offset_days)
    sql = _win_cte(aliases) + f"""
        SELECT
            COALESCE(opponent_canonical_id, opponent_name) AS opponent_canonical_id,
            COALESCE(MAX(opponent_name), opponent_canonical_id) AS opponent,
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            avg(player_frags - opponent_frags) AS avg_frag_diff,
            max(match_date) AS last_played
        FROM match_outcomes
        WHERE match_mode = '1on1' AND opponent_name IS NOT NULL {date_sql}
        GROUP BY opponent_canonical_id
        ORDER BY matches DESC
    """
    out = []
    for row in db.execute(sql, {**_scope_kwargs(aliases), **date_params}):
        d = dict(row)
        d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
        d["avg_frag_diff"] = _round(d["avg_frag_diff"])
        out.append(d)
    return out


def trend_weekly(db, aliases, days=None, offset_days=0, mode_filter=None):
    """Weekly buckets with the same metrics _aggregate exposes, so the UI can plot any.

    Note: weeks with zero matches don't appear (no row to bucket by). The client
    handles gaps in plot data with spanGaps.
    """
    date_sql, date_params = _date_filter(days, offset_days)
    params = {**_scope_kwargs(aliases), **date_params}
    mode_clause = ""
    if mode_filter:
        mode_clause = "AND match_mode = :trend_mode"
        params["trend_mode"] = mode_filter
    sql = _win_cte(aliases) + f"""
        SELECT
            strftime('%Y-%W', match_date) AS week,
            min(match_date) AS week_start,
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            avg(player_frags) AS avg_frags,
            avg(player_deaths) AS avg_deaths,
            avg(player_frags - player_deaths) AS avg_frag_diff,
            avg(player_damage_given) AS avg_dmg_given,
            avg(player_damage_taken) AS avg_dmg_taken,
            avg(player_damage_enemy_weapons) AS avg_dmg_enemy_weapons,
            avg(player_damage_team) AS avg_dmg_team,
            avg(CAST(player_lg_hits AS REAL) / nullif(player_lg_attacks, 0)) AS lg_accuracy,
            avg(CAST(player_rl_virtual AS REAL) / nullif(player_rl_attacks, 0)) AS rl_accuracy,
            avg(CAST(player_sg_hits AS REAL) / nullif(player_sg_attacks, 0)) AS sg_accuracy,
            avg(CAST(player_ssg_hits AS REAL) / nullif(player_ssg_attacks, 0)) AS ssg_accuracy,
            avg(player_rl_damage_enemy) AS avg_rl_dmg,
            avg(player_lg_damage_enemy) AS avg_lg_dmg,
            avg(player_rl_kills_enemy) AS avg_rl_kills,
            avg(player_lg_kills_enemy) AS avg_lg_kills,
            avg(player_ra_taken) AS avg_ra,
            avg(player_ya_taken) AS avg_ya,
            avg(player_ga_taken) AS avg_ga,
            avg(player_health100_taken) AS avg_mh,
            avg(player_quad_taken) AS avg_quads,
            avg(player_pent_taken) AS avg_pents,
            avg(player_rl_taken) AS avg_rl_taken,
            avg(player_lg_taken) AS avg_lg_taken,
            avg(player_rl_dropped) AS avg_rl_dropped,
            avg(player_lg_dropped) AS avg_lg_dropped,
            avg(player_rl_transfer) AS avg_rl_transfer,
            avg(player_lg_transfer) AS avg_lg_transfer,
            avg(player_spawnfrags) AS avg_spawnfrags,
            avg(player_teamkills) AS avg_teamkills,
            avg(player_ping) AS avg_ping
        FROM match_outcomes
        WHERE 1=1 {date_sql} {mode_clause}
        GROUP BY week
        ORDER BY week
    """
    out = []
    for row in db.execute(sql, params):
        d = dict(row)
        d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
        for k in list(d.keys()):
            if k in ("week", "week_start", "matches", "wins", "losses"):
                continue
            d[k] = _round(d[k])
        out.append(d)
    return out


def recent_matches(db, aliases, limit=50, days=None, offset_days=0):
    date_sql, date_params = _date_filter(days, offset_days)
    sql = _win_cte(aliases) + f"""
        SELECT match_id, match_date, match_mode, match_map, match_dmm, server_hostname,
               outcome, opponent_name, opponent_frags, player_frags, player_deaths,
               CAST(player_lg_hits AS REAL) / nullif(player_lg_attacks, 0) AS lg_acc,
               CAST(player_rl_virtual AS REAL) / nullif(player_rl_attacks, 0) AS rl_acc
        FROM match_outcomes
        WHERE 1=1 {date_sql}
        ORDER BY match_date DESC
        LIMIT :limit
    """
    out = []
    for row in db.execute(sql, {**_scope_kwargs(aliases), **date_params, "limit": limit}):
        d = dict(row)
        d["lg_acc"] = _round(d["lg_acc"])
        d["rl_acc"] = _round(d["rl_acc"])
        out.append(d)
    return out


def build_profile_with_ratings(db, player, aliases, canonical_id, windows=DEFAULT_WINDOWS):
    """Build profile and tack on per-mode TrueSkill ratings."""
    profile = build_profile(db, player, aliases, windows)
    profile["ratings"] = ratings_for_player(db, canonical_id)
    return profile


def _window_payload(db, aliases, days, offset_days=0):
    """Build the full slice of aggregations for a single time window.

    offset_days != 0 means "shift the window back by that many days" — used
    to compute the 'prior period' or 'year ago' payloads for compare views.

    trend_weekly is computed both globally (all modes — used for activity view)
    and per-mode (used for mode-specific trend lines on the Trends tab).
    """
    return {
        "by_mode": by_mode(db, aliases, days=days, offset_days=offset_days),
        "by_dmm": by_dmm(db, aliases, days=days, offset_days=offset_days),
        "by_map_1on1": _per_group(db, aliases, "match_map", mode_filter="1on1", days=days, offset_days=offset_days),
        "by_map_4on4": _per_group(db, aliases, "match_map", mode_filter="4on4", days=days, offset_days=offset_days),
        "by_map_2on2": _per_group(db, aliases, "match_map", mode_filter="2on2", days=days, offset_days=offset_days),
        "by_server_all": _per_group(db, aliases, "server_hostname", days=days, offset_days=offset_days),
        "by_server_1on1": _per_group(db, aliases, "server_hostname", mode_filter="1on1", days=days, offset_days=offset_days),
        "head_to_head_1on1": head_to_head(db, aliases, days=days, offset_days=offset_days),
        "trend_weekly": trend_weekly(db, aliases, days=days, offset_days=offset_days),
        "trend_weekly_by_mode": {
            "1on1": trend_weekly(db, aliases, days=days, offset_days=offset_days, mode_filter="1on1"),
            "4on4": trend_weekly(db, aliases, days=days, offset_days=offset_days, mode_filter="4on4"),
            "2on2": trend_weekly(db, aliases, days=days, offset_days=offset_days, mode_filter="2on2"),
        },
        "recent_matches": recent_matches(db, aliases, limit=50, days=days, offset_days=offset_days),
    }


def ratings_for_player(db, canonical_id):
    """Return per-mode TrueSkill ratings if rate.py has been run for this player.

    Returns {'1on1': {...}, '2on2': null, '4on4': null} — null modes are not yet rated.
    """
    out = {'1on1': None, '2on2': None, '4on4': None}
    if not isinstance(canonical_id, str):
        return out
    rows = db.execute(
        """
        SELECT mode, mu, sigma, conservative, matches_rated, wins, losses, draws,
               updated_at,
               (SELECT count(*) + 1 FROM ratings r2
                WHERE r2.mode = r.mode AND r2.map = '' AND r2.conservative > r.conservative) AS rank,
               (SELECT count(*) FROM ratings r3 WHERE r3.mode = r.mode AND r3.map = '') AS total_rated
        FROM ratings r
        WHERE canonical_id = ? AND map = ''
        """,
        (canonical_id,),
    ).fetchall()
    for r in rows:
        out[r["mode"]] = {
            "mu": _round(r["mu"], 1),
            "sigma": _round(r["sigma"], 1),
            "conservative": _round(r["conservative"], 1),
            "matches": r["matches_rated"],
            "wins": r["wins"],
            "losses": r["losses"],
            "draws": r["draws"],
            "rank": r["rank"],
            "total_rated": r["total_rated"],
            "tier": tier_for(r["conservative"]),
            "updated_at": r["updated_at"],
        }
    return out


def per_map_ratings_for_player(db, canonical_id, mode="1on1"):
    """Return per-map TrueSkill for a player in a given mode.

    {map_name: {mu, sigma, conservative, matches, wins, losses, rank, total_rated}}
    Map name is the bucket key from rate.py (lowercase, as stored in matches.match_map).
    """
    out = {}
    if not isinstance(canonical_id, str):
        return out
    rows = db.execute(
        """
        SELECT map, mu, sigma, conservative, matches_rated, wins, losses, draws,
               (SELECT count(*) + 1 FROM ratings r2
                WHERE r2.mode = r.mode AND r2.map = r.map AND r2.conservative > r.conservative) AS rank,
               (SELECT count(*) FROM ratings r3
                WHERE r3.mode = r.mode AND r3.map = r.map) AS total_rated
        FROM ratings r
        WHERE canonical_id = ? AND mode = ? AND map != ''
        """,
        (canonical_id, mode),
    ).fetchall()
    for r in rows:
        out[r["map"]] = {
            "mu": _round(r["mu"], 1),
            "sigma": _round(r["sigma"], 1),
            "conservative": _round(r["conservative"], 1),
            "matches": r["matches_rated"],
            "wins": r["wins"],
            "losses": r["losses"],
            "draws": r["draws"],
            "rank": r["rank"],
            "total_rated": r["total_rated"],
        }
    return out


def build_profile(db, player, aliases, windows=DEFAULT_WINDOWS):
    # Per-map ratings (1on1 only for now). Used to enrich the Maps card so
    # each map row shows that player's per-map TrueSkill alongside W/L stats.
    canon = aliases if isinstance(aliases, str) else None
    map_ratings_1on1 = per_map_ratings_for_player(db, canon, "1on1") if canon else {}

    def _attach_map_ratings(payload):
        for row in payload.get("by_map_1on1", []) or []:
            mr = map_ratings_1on1.get(row.get("bucket"))
            if mr:
                row["rating"] = mr["conservative"]
                row["mu"] = mr["mu"]
                row["sigma"] = mr["sigma"]
                row["rated_matches"] = mr["matches"]
                row["rank"] = mr["rank"]
                row["total_rated"] = mr["total_rated"]
        return payload

    out_windows = {}
    for label, days in windows:
        payload = _attach_map_ratings(_window_payload(db, aliases, days))
        if days:
            # Bounded windows get two comparison payloads:
            #   prior     → same length, immediately preceding (offset = days)
            #   year_ago  → same length, 365 days earlier (offset = 365)
            payload["prior"] = _attach_map_ratings(_window_payload(db, aliases, days, offset_days=days))
            payload["year_ago"] = _attach_map_ratings(_window_payload(db, aliases, days, offset_days=365))
        else:
            payload["prior"] = None
            payload["year_ago"] = None
        out_windows[label] = payload
    return {
        "player": player,
        "aliases": aliases,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "windows_available": [w[0] for w in windows],
        "default_window": "90",
        "career": career(db, player, aliases),
        "map_ratings_1on1": map_ratings_1on1,
        "windows": out_windows,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export per-player profile JSON, scoped by canonical_id from the identity layer.",
    )
    parser.add_argument("canonical_id",
                        help="canonical player id (e.g. 'cronus') — see players_canonical table or aliases.yaml")
    parser.add_argument("--alias", action="append", default=[],
                        help="(legacy) fall back to alias-list matching if canonicalization hasn't been run yet")
    parser.add_argument("--db", default=str(Path(__file__).parent / "data" / "qw-stats.db"))
    parser.add_argument("--out", default=str(Path(__file__).parent / "public" / "profile.json"))
    args = parser.parse_args()

    db = _connect(args.db)
    try:
        # Default: scope by canonical_id (fast, accurate). If --alias args were provided,
        # use the legacy alias-list path instead (for un-canonicalized DBs).
        if args.alias:
            scope = list(set([args.canonical_id.lower(), *(a.lower() for a in args.alias)]))
            display_name = args.canonical_id
        else:
            scope = args.canonical_id
            row = db.execute(
                "SELECT display_name FROM players_canonical WHERE canonical_id = ?",
                (args.canonical_id,),
            ).fetchone()
            display_name = row["display_name"] if row else args.canonical_id
        profile = build_profile(db, display_name, scope)
        profile["canonical_id"] = args.canonical_id
        # Per-mode TrueSkill ratings (Phase A: 1on1 only; 2on2/4on4 null until Phase B)
        profile["ratings"] = ratings_for_player(db, args.canonical_id)
    finally:
        db.close()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(profile, indent=2))
    size = Path(args.out).stat().st_size
    print(f"Wrote {args.out} ({size:,} bytes)")
    print(f"  scope: {scope!r}")
    print(f"  display: {display_name}")
    print(f"  career.hub.matches: {profile['career']['hub']['matches']}")
    print(f"  windows:")
    for label in profile["windows_available"]:
        win = profile["windows"][label]
        n = sum((m or {}).get("matches", 0) for m in win["by_mode"].values())
        print(f"    {label:>4}d: {n:,} matches across {list(win['by_mode'].keys())}")


if __name__ == "__main__":
    main()

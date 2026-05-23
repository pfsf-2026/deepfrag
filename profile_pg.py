"""Postgres-backed profile builder — mirrors the shape of export.build_profile()
but queries Cloud SQL directly. Used by api.py's /api/players/{id}/full endpoint.

SQL is mostly portable from export.py with three substitutions:
  :name  →  %(name)s   (psycopg2 named params)
  CAST(x AS REAL)  →  x::float
  strftime('%Y-%W', d)  →  to_char(d::timestamptz, 'IYYY-IW')
"""

from datetime import datetime, timedelta, timezone


def _round(v, digits=3):
    return None if v is None else round(float(v), digits)


def _date_filter(days, offset_days=0):
    """Build a WHERE clause + params dict for a [start, end) window."""
    if days is None:
        return "", {}
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=offset_days)
    start = end - timedelta(days=days)
    if offset_days:
        return ("AND match_date >= %(since_date)s AND match_date < %(until_date)s",
                {"since_date": start.isoformat(), "until_date": end.isoformat()})
    return "AND match_date >= %(since_date)s", {"since_date": start.isoformat()}


def _win_cte():
    """CTE that scopes player_match to a canonical_id and computes per-match outcome.
    Bind %(canonical_id)s when executing."""
    return """
WITH player_match AS (
    SELECT p.*, m.match_mode, m.match_map, m.server_hostname, m.match_date,
           m.match_dmm, m.has_bots
    FROM players p JOIN matches m ON m.match_id = p.match_id
    WHERE p.canonical_id = %(canonical_id)s
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
                    WHEN tf_self.team_total > MAX(tf_other.team_total) THEN 'win'
                    WHEN tf_self.team_total < MAX(tf_other.team_total) THEN 'loss'
                    ELSE 'draw' END
                FROM team_frags tf_self
                JOIN team_frags tf_other
                  ON tf_other.match_id = tf_self.match_id AND tf_other.player_team <> tf_self.player_team
                WHERE tf_self.match_id = pm.match_id AND tf_self.player_team = pm.player_team
                GROUP BY tf_self.team_total
            )
        END AS outcome,
        CASE WHEN pm.match_mode = '1on1' THEN (
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


def career(cur, canonical_id):
    """Hub career: lifetime distinct-match count + first/last seen."""
    cur.execute("""
        SELECT COUNT(DISTINCT m.match_id) AS n,
               MIN(m.match_date) AS first_date,
               MAX(m.match_date) AS last_date
        FROM matches m JOIN players p ON p.match_id = m.match_id
        WHERE p.canonical_id = %s
    """, (canonical_id,))
    row = cur.fetchone()
    return {
        "lifetime": None,
        "hub": {
            "matches": row["n"] if row else 0,
            "first_match": row["first_date"] if row else None,
            "last_match": row["last_date"] if row else None,
        }
    }


def _aggregate(cur, canonical_id, where_extra="", extra_params=None, days=None, offset_days=0):
    """Per-slice averages — the same set the static export emits."""
    date_sql, date_params = _date_filter(days, offset_days)
    params = {"canonical_id": canonical_id, **(extra_params or {}), **date_params}
    sql = _win_cte() + f"""
        SELECT
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            sum(CASE WHEN outcome='draw' THEN 1 ELSE 0 END) AS draws,

            avg(player_frags) AS avg_frags,
            avg(player_deaths) AS avg_deaths,
            avg(player_frags - player_deaths) AS avg_frag_diff,
            avg(player_teamkills) AS avg_teamkills,
            avg(player_spawnfrags) AS avg_spawnfrags,
            avg(player_suicides) AS avg_suicides,

            avg(player_damage_given) AS avg_dmg_given,
            avg(player_damage_taken) AS avg_dmg_taken,
            avg(player_damage_enemy_weapons) AS avg_dmg_enemy_weapons,
            avg(player_damage_team) AS avg_dmg_team,

            avg(player_rl_virtual::float / nullif(player_rl_attacks, 0)) AS rl_accuracy,
            avg(player_lg_hits::float / nullif(player_lg_attacks, 0)) AS lg_accuracy,
            avg(player_sg_hits::float / nullif(player_sg_attacks, 0)) AS sg_accuracy,
            avg(player_ssg_hits::float / nullif(player_ssg_attacks, 0)) AS ssg_accuracy,

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
            avg(player_ping) AS avg_ping
        FROM match_outcomes
        WHERE 1=1 {where_extra} {date_sql}
    """
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row or not row["matches"]:
        return None
    d = dict(row)
    d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
    for k in list(d.keys()):
        if k in ("matches", "wins", "losses", "draws"):
            continue
        d[k] = _round(d[k])
    return d


def by_mode(cur, canonical_id, days=None, offset_days=0):
    """Per-match-mode breakdown — keyed by '1on1' / '2on2' / '4on4'."""
    date_sql, date_params = _date_filter(days, offset_days)
    cur.execute(_win_cte() + f"SELECT DISTINCT match_mode FROM match_outcomes WHERE 1=1 {date_sql}",
                {"canonical_id": canonical_id, **date_params})
    modes = [r["match_mode"] for r in cur.fetchall()]
    out = {}
    for m in modes:
        out[m] = _aggregate(cur, canonical_id, "AND match_mode = %(mode)s",
                            {"mode": m}, days=days, offset_days=offset_days)
    return out


def per_map(cur, canonical_id, mode, days=None, offset_days=0):
    """Per-map breakdown for one mode (the by_map_1on1 / by_map_4on4 / etc. lists)."""
    date_sql, date_params = _date_filter(days, offset_days)
    params = {"canonical_id": canonical_id, "mode": mode, **date_params}
    sql = _win_cte() + f"""
        SELECT
            match_map AS bucket,
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            avg(player_frags) AS avg_frags,
            avg(player_frags - player_deaths) AS avg_frag_diff,
            avg(player_lg_hits::float / nullif(player_lg_attacks, 0)) AS lg_accuracy,
            avg(player_rl_virtual::float / nullif(player_rl_attacks, 0)) AS rl_accuracy,
            MAX(match_date) AS last_played
        FROM match_outcomes
        WHERE match_map IS NOT NULL AND match_mode = %(mode)s {date_sql}
        GROUP BY match_map
        ORDER BY matches DESC
    """
    cur.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
        for k in ("avg_frags", "avg_frag_diff", "lg_accuracy", "rl_accuracy"):
            d[k] = _round(d[k])
        out.append(d)
    return out


def head_to_head_1on1(cur, canonical_id, days=None, offset_days=0):
    """Per-opponent record, 1on1 only. Grouped by opponent canonical_id.

    Postgres requires every non-aggregate SELECT column to be in GROUP BY. We
    put the same COALESCE in both SELECT and GROUP BY to give it a single
    unambiguous grouping key — opponent_name is otherwise wrapped in MAX().
    """
    date_sql, date_params = _date_filter(days, offset_days)
    params = {"canonical_id": canonical_id, **date_params}
    sql = _win_cte() + f"""
        SELECT
            COALESCE(opponent_canonical_id, opponent_name) AS opponent_canonical_id,
            MAX(opponent_name) AS opponent,
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            avg(player_frags - opponent_frags) AS avg_frag_diff,
            max(match_date) AS last_played
        FROM match_outcomes
        WHERE match_mode = '1on1' AND opponent_name IS NOT NULL {date_sql}
        GROUP BY COALESCE(opponent_canonical_id, opponent_name)
        ORDER BY matches DESC
    """
    cur.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
        d["avg_frag_diff"] = _round(d["avg_frag_diff"])
        out.append(d)
    return out


def trend_weekly_by_mode(cur, canonical_id, mode, days=None, offset_days=0):
    """Per-week buckets for one mode — used for sparkline trends on the Metrics view."""
    date_sql, date_params = _date_filter(days, offset_days)
    params = {"canonical_id": canonical_id, "trend_mode": mode, **date_params}
    sql = _win_cte() + f"""
        SELECT
            to_char(match_date::timestamptz, 'IYYY-IW') AS week,
            min(match_date) AS week_start,
            count(*) AS matches,
            sum(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            sum(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) AS losses,
            avg(player_frags) AS avg_frags,
            avg(player_deaths) AS avg_deaths,
            avg(player_frags - player_deaths) AS avg_frag_diff,
            avg(player_damage_given) AS avg_dmg_given,
            avg(player_damage_taken) AS avg_dmg_taken,
            avg(player_lg_hits::float / nullif(player_lg_attacks, 0)) AS lg_accuracy,
            avg(player_rl_virtual::float / nullif(player_rl_attacks, 0)) AS rl_accuracy,
            avg(player_rl_damage_enemy) AS avg_rl_dmg,
            avg(player_lg_damage_enemy) AS avg_lg_dmg,
            avg(player_ra_taken) AS avg_ra,
            avg(player_ya_taken) AS avg_ya,
            avg(player_ga_taken) AS avg_ga,
            avg(player_health100_taken) AS avg_mh,
            avg(player_ping) AS avg_ping
        FROM match_outcomes
        WHERE match_mode = %(trend_mode)s {date_sql}
        GROUP BY week
        ORDER BY week
    """
    cur.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["win_rate"] = _round(d["wins"] / d["matches"]) if d["matches"] else None
        for k in list(d.keys()):
            if k in ("week", "week_start", "matches", "wins", "losses"):
                continue
            d[k] = _round(d[k])
        out.append(d)
    return out


def _fetch_match_outcomes(cur, canonical_id, days=None, offset_days=0):
    """ONE query to fetch every match_outcome row for the player + window.
    All downstream aggregations work off the in-memory list — much faster than
    running _win_cte 15 times. Returns list of dicts (~7K rows for an active player)."""
    date_sql, date_params = _date_filter(days, offset_days)
    params = {"canonical_id": canonical_id, **date_params}
    sql = _win_cte() + f"""
        SELECT
            match_id, match_date, match_mode, match_map, match_dmm,
            outcome, opponent_canonical_id, opponent_name, opponent_frags,
            player_frags, player_deaths, player_teamkills, player_spawnfrags, player_suicides,
            player_damage_given, player_damage_taken, player_damage_enemy_weapons, player_damage_team,
            player_rl_attacks, player_rl_virtual, player_rl_damage_enemy, player_rl_kills_enemy,
            player_rl_dropped, player_rl_taken, player_rl_transfer,
            player_lg_attacks, player_lg_hits, player_lg_damage_enemy, player_lg_kills_enemy,
            player_lg_dropped, player_lg_taken, player_lg_transfer,
            player_sg_attacks, player_sg_hits,
            player_ssg_attacks, player_ssg_hits,
            player_ra_taken, player_ya_taken, player_ga_taken,
            player_health100_taken, player_quad_taken, player_pent_taken,
            player_ping
        FROM match_outcomes WHERE 1=1 {date_sql}
    """
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def _avg(rows, key):
    """Numeric mean over non-null values."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def _avg_ratio(rows, num_key, den_key):
    """Mean of num/den, only over rows where den > 0 (matches the SQLite nullif behavior)."""
    ratios = []
    for r in rows:
        n, d = r.get(num_key), r.get(den_key)
        if n is not None and d:
            ratios.append(n / d)
    return sum(ratios) / len(ratios) if ratios else None


def _agg_metrics(rows):
    """Compute every per-slice aggregate from a list of match_outcome rows."""
    if not rows:
        return None
    n = len(rows)
    wins = sum(1 for r in rows if r.get("outcome") == "win")
    losses = sum(1 for r in rows if r.get("outcome") == "loss")
    draws = sum(1 for r in rows if r.get("outcome") == "draw")
    d = {
        "matches": n, "wins": wins, "losses": losses, "draws": draws,
        "win_rate": _round(wins / n) if n else None,
        "avg_frags": _round(_avg(rows, "player_frags")),
        "avg_deaths": _round(_avg(rows, "player_deaths")),
        "avg_frag_diff": _round(_avg([{"v": (r["player_frags"] or 0) - (r["player_deaths"] or 0)} for r in rows], "v")),
        "avg_teamkills": _round(_avg(rows, "player_teamkills")),
        "avg_spawnfrags": _round(_avg(rows, "player_spawnfrags")),
        "avg_dmg_given": _round(_avg(rows, "player_damage_given")),
        "avg_dmg_taken": _round(_avg(rows, "player_damage_taken")),
        "avg_dmg_enemy_weapons": _round(_avg(rows, "player_damage_enemy_weapons")),
        "avg_dmg_team": _round(_avg(rows, "player_damage_team")),
        "rl_accuracy": _round(_avg_ratio(rows, "player_rl_virtual", "player_rl_attacks")),
        "lg_accuracy": _round(_avg_ratio(rows, "player_lg_hits", "player_lg_attacks")),
        "sg_accuracy": _round(_avg_ratio(rows, "player_sg_hits", "player_sg_attacks")),
        "ssg_accuracy": _round(_avg_ratio(rows, "player_ssg_hits", "player_ssg_attacks")),
        "avg_rl_dmg": _round(_avg(rows, "player_rl_damage_enemy")),
        "avg_lg_dmg": _round(_avg(rows, "player_lg_damage_enemy")),
        "avg_rl_kills": _round(_avg(rows, "player_rl_kills_enemy")),
        "avg_lg_kills": _round(_avg(rows, "player_lg_kills_enemy")),
        "avg_ra": _round(_avg(rows, "player_ra_taken")),
        "avg_ya": _round(_avg(rows, "player_ya_taken")),
        "avg_ga": _round(_avg(rows, "player_ga_taken")),
        "avg_mh": _round(_avg(rows, "player_health100_taken")),
        "avg_quads": _round(_avg(rows, "player_quad_taken")),
        "avg_pents": _round(_avg(rows, "player_pent_taken")),
        "avg_rl_taken": _round(_avg(rows, "player_rl_taken")),
        "avg_lg_taken": _round(_avg(rows, "player_lg_taken")),
        "avg_rl_dropped": _round(_avg(rows, "player_rl_dropped")),
        "avg_lg_dropped": _round(_avg(rows, "player_lg_dropped")),
        "avg_rl_transfer": _round(_avg(rows, "player_rl_transfer")),
        "avg_lg_transfer": _round(_avg(rows, "player_lg_transfer")),
        "avg_ping": _round(_avg(rows, "player_ping")),
    }
    return d


def _by_mode_python(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["match_mode"], []).append(r)
    return {mode: _agg_metrics(rs) for mode, rs in groups.items()}


def _per_map_python(rows, mode):
    """Per-map breakdown for one mode — slimmer aggregate than full _agg_metrics."""
    groups = {}
    for r in rows:
        if r["match_mode"] != mode or not r["match_map"]:
            continue
        groups.setdefault(r["match_map"], []).append(r)
    out = []
    for bucket, rs in groups.items():
        n = len(rs)
        wins = sum(1 for r in rs if r["outcome"] == "win")
        losses = sum(1 for r in rs if r["outcome"] == "loss")
        out.append({
            "bucket": bucket,
            "matches": n, "wins": wins, "losses": losses,
            "win_rate": _round(wins / n) if n else None,
            "avg_frags": _round(_avg(rs, "player_frags")),
            "avg_frag_diff": _round(_avg([{"v": (r["player_frags"] or 0) - (r["player_deaths"] or 0)} for r in rs], "v")),
            "lg_accuracy": _round(_avg_ratio(rs, "player_lg_hits", "player_lg_attacks")),
            "rl_accuracy": _round(_avg_ratio(rs, "player_rl_virtual", "player_rl_attacks")),
            "last_played": max(r["match_date"] for r in rs if r["match_date"]),
        })
    out.sort(key=lambda r: -r["matches"])
    return out


def _h2h_python(rows):
    """1on1 head-to-head from rows, grouped by opponent_canonical_id (falls back to opponent_name)."""
    groups = {}
    for r in rows:
        if r["match_mode"] != "1on1" or not r.get("opponent_name"):
            continue
        key = r.get("opponent_canonical_id") or r["opponent_name"]
        groups.setdefault(key, []).append(r)
    out = []
    for key, rs in groups.items():
        n = len(rs)
        wins = sum(1 for r in rs if r["outcome"] == "win")
        losses = sum(1 for r in rs if r["outcome"] == "loss")
        out.append({
            "opponent_canonical_id": key,
            "opponent": max(r["opponent_name"] for r in rs if r["opponent_name"]),
            "matches": n, "wins": wins, "losses": losses,
            "win_rate": _round(wins / n) if n else None,
            "avg_frag_diff": _round(_avg(
                [{"v": (r["player_frags"] or 0) - (r["opponent_frags"] or 0)} for r in rs if r.get("opponent_frags") is not None],
                "v"
            )),
            "last_played": max(r["match_date"] for r in rs if r["match_date"]),
        })
    out.sort(key=lambda r: -r["matches"])
    return out


def _trend_weekly_python(rows, mode):
    """Per-week buckets for one mode — keyed by ISO year-week."""
    from datetime import datetime
    groups = {}
    for r in rows:
        if r["match_mode"] != mode or not r["match_date"]:
            continue
        try:
            dt = datetime.fromisoformat(r["match_date"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        wk = f"{dt.isocalendar()[0]}-{dt.isocalendar()[1]:02d}"
        groups.setdefault(wk, []).append(r)
    out = []
    for wk in sorted(groups.keys()):
        rs = groups[wk]
        out.append({
            "week": wk,
            "week_start": min(r["match_date"] for r in rs),
            "matches": len(rs),
            "wins": sum(1 for r in rs if r["outcome"] == "win"),
            "losses": sum(1 for r in rs if r["outcome"] == "loss"),
            "avg_frags": _round(_avg(rs, "player_frags")),
            "avg_deaths": _round(_avg(rs, "player_deaths")),
            "avg_frag_diff": _round(_avg([{"v": (r["player_frags"] or 0) - (r["player_deaths"] or 0)} for r in rs], "v")),
            "avg_dmg_given": _round(_avg(rs, "player_damage_given")),
            "avg_dmg_taken": _round(_avg(rs, "player_damage_taken")),
            "lg_accuracy": _round(_avg_ratio(rs, "player_lg_hits", "player_lg_attacks")),
            "rl_accuracy": _round(_avg_ratio(rs, "player_rl_virtual", "player_rl_attacks")),
            "avg_rl_dmg": _round(_avg(rs, "player_rl_damage_enemy")),
            "avg_lg_dmg": _round(_avg(rs, "player_lg_damage_enemy")),
            "avg_ra": _round(_avg(rs, "player_ra_taken")),
            "avg_ya": _round(_avg(rs, "player_ya_taken")),
            "avg_ga": _round(_avg(rs, "player_ga_taken")),
            "avg_mh": _round(_avg(rs, "player_health100_taken")),
            "avg_ping": _round(_avg(rs, "player_ping")),
        })
        out[-1]["win_rate"] = _round(out[-1]["wins"] / out[-1]["matches"]) if out[-1]["matches"] else None
    return out


def build_window(cur, canonical_id, days):
    """One-query window build: pull match_outcomes once, aggregate in Python.
    Was 15+ separate SQL queries — now 1 + memory ops. 4s → <500ms."""
    rows = _fetch_match_outcomes(cur, canonical_id, days=days)
    return {
        "by_mode": _by_mode_python(rows),
        "by_map_1on1": _per_map_python(rows, "1on1"),
        "by_map_2on2": _per_map_python(rows, "2on2"),
        "by_map_4on4": _per_map_python(rows, "4on4"),
        "head_to_head_1on1": _h2h_python(rows),
        "trend_weekly_by_mode": {
            "1on1": _trend_weekly_python(rows, "1on1"),
            "2on2": _trend_weekly_python(rows, "2on2"),
            "4on4": _trend_weekly_python(rows, "4on4"),
        },
    }


def build_prior(cur, canonical_id, days):
    """Compact prior-period payload — only by_mode + h2h are used by deltas."""
    rows = _fetch_match_outcomes(cur, canonical_id, days=days, offset_days=days)
    return {
        "by_mode": _by_mode_python(rows),
        "head_to_head_1on1": _h2h_python(rows),
    }

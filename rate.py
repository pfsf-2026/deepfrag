#!/usr/bin/env python3
"""Compute DeepFrag ratings — margin-calibrated OpenSkill + shrunk per-map deviations.

ENGINE v3 (deployed 2026-08-17). Two structural changes vs the 2026-05-26 engine,
both validated by walk-forward backtest on 79,928 duels (docs/1on1_methodology.md
§1b has the full evidence table; scratchpad harness: backtest.py/permap3.py):

  1. CONTINUOUS-MARGIN OUTCOMES (overall rating).
     The old engine rated binary W/L and multiplied the update by a perf weight
     clamped to [0.2, 1.6] — so a loss could never raise μ, and its linear
     expected-margin curve (0.020×gap, capped ±20) destroyed ~85% of the frag
     signal in mismatches (real curve: 70·tanh(gap/2575), reaching -44 at big
     gaps). v3 scores each match as a continuous outcome s ∈ [0,1] blending
     the binary result with margin + DDR surprise, then interpolates between
     the win-case and loss-case OpenSkill posteriors by s. A 13-15 loss to a
     +950 opponent now nudges μ UP. Held-out log-loss: 0.4684 → 0.4115 (-12.2%,
     z=21.7); the gain concentrates in mismatches (gap>800: -74%).

  2. PER-MAP AS SHRUNK DEVIATIONS (replaces the per-map ELO walk).
     The old per-map path gave each (player, map) a free-floating ELO seeded at
     final global μ (temporal leakage) wandering at K=32 on 5-20 games — pure
     variance: it predicted WORSE than ignoring maps entirely (0.6614 vs 0.4016
     log-loss). Map skill is real (split-half reliability r=0.50, shuffled
     control -0.08) but must be estimated as a regularised DEVIATION:

         map_mu = global_mu + MAP_GAIN · (n/(n+K)) · mean(residual)

     where residual = actual outcome − P(win) predicted by the global rating at
     match time (no leakage). Backtest: 0.3875 log-loss / 82.4% acc — per-map
     finally ADDS signal over global (0.4016 / 81.4%).

  Also new: Glicko-style idle-day σ inflation (TAU_PER_DAY) and a σ floor so
  high-game-count veterans' μ stays responsive.

Single chronological pass rates the overall bucket AND accumulates per-map
residuals together (the old code ran 1 + n_maps separate passes). Persists to
`ratings` + `rating_history` exactly as before; per-map accumulator state lives
in the new `map_residuals` table so --incremental runs stay exact.

Inter-regional weighting: unchanged (away player's update dampened ×0.6).

Usage:
  python rate.py                 # full rebuild for 1on1
  python rate.py --mode 1on1
  python rate.py --incremental
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras
from openskill.models import PlackettLuce

import db as dbmod

DEFAULT_DB = Path(__file__).parent / "data" / "qw-stats.db"

ENGINE_VERSION = "v3-margin-2026-08-17"

# OpenSkill model — same display scale as always (μ=1500, σ=500) so downstream
# consumers (tiers, conservative-rating, predict_win) need no re-scaling.
BETA = 250.0
MODEL = PlackettLuce(mu=1500.0, sigma=500.0, beta=BETA, tau=0.5, kappa=0.0001)

# Cross-region match: rating update for the away player is multiplied by this.
# 0.6 = "this match is 60% as informative for the away player as a fair-ping
# match". Home player unaffected. Chosen by reasoning, not data (2026-05-26).
CROSS_REGION_WEIGHT = 0.6

# ── v3 engine constants ──────────────────────────────────────────────────────
# All values from the 2026-08-16 coordinate-descent sweep against held-out
# log-loss (37,352 scored matches, 2025-01-01+, both players ≥20 prior games).
# Change these ONLY with a fresh backtest; update the bible in the same commit.
EXP_MARGIN_AMP = 70.0     # expected frag diff = AMP · tanh(gap / SCALE) —
EXP_MARGIN_SCALE = 2575.0  # fitted on 8,776 real duel observations
MARGIN_NORM = 10.0        # frag surprise that saturates the margin score
W_RESULT = 0.65           # outcome score: 65% binary W/L, 35% margin/DDR
DDR_WEIGHT = 0.35         # share of the margin component carried by DDR
TAU_PER_DAY = 1.0         # Glicko-style σ inflation per idle day (σ-units)
SIGMA_FLOOR = 80.0        # σ never contracts below this (μ stays responsive
                          # for veterans; old engine let it reach ~41)

# ── per-map shrinkage constants ──────────────────────────────────────────────
MAP_SHRINK_K = 10.0       # games at which the map effect reaches half weight
MAP_GAIN = 900.0          # converts mean win-prob residual → μ offset
MAP_MIN_CORPUS = 50       # a map needs ≥ this many matches to get rating rows
                          # (accumulators still tracked below the threshold)


def predict_win(mu_a: float, sig_a: float, mu_b: float, sig_b: float) -> float:
    """P(a beats b) — identical form to api.py's predict_win."""
    denom = math.sqrt(2 * BETA**2 + sig_a**2 + sig_b**2)
    return 0.5 * (1.0 + math.erf((mu_a - mu_b) / (denom * math.sqrt(2.0))))


def expected_margin(mu_a: float, mu_b: float) -> float:
    """Predicted (a_frags − b_frags). Empirical fit — see module docstring."""
    return EXP_MARGIN_AMP * math.tanh((mu_a - mu_b) / EXP_MARGIN_SCALE)


def outcome_score(mu_a: float, mu_b: float, frags_a: int, frags_b: int,
                  dmg_given_a, dmg_taken_a) -> float:
    """Continuous outcome s ∈ [0,1] for player A. 0.5 = performed exactly to
    rating; >0.5 = performed like a win. Blends the binary result (W_RESULT)
    with a margin-surprise sigmoid, itself blended with a DDR sigmoid when
    damage stats exist (pre-KTX matches fall back to margin only)."""
    surprise = ((frags_a or 0) - (frags_b or 0)) - expected_margin(mu_a, mu_b)
    margin_s = 1.0 / (1.0 + math.exp(-surprise / MARGIN_NORM))
    if dmg_given_a is not None and dmg_taken_a is not None and dmg_taken_a > 0:
        ddr = dmg_given_a / max(1.0, dmg_taken_a)
        ddr_s = 1.0 / (1.0 + math.exp(-(ddr - 1.0) * 2.0))
        margin_s = (1 - DDR_WEIGHT) * margin_s + DDR_WEIGHT * ddr_s
    if frags_a == frags_b:
        binary = 0.5
    else:
        binary = 1.0 if frags_a > frags_b else 0.0
    return W_RESULT * binary + (1 - W_RESULT) * margin_s


def aged_sigma(sigma: float, idle_days: float) -> float:
    """Glicko-style: belief widens while a player is away, capped at the prior."""
    if idle_days <= 0 or TAU_PER_DAY <= 0:
        return sigma
    return min(500.0, math.sqrt(sigma**2 + (TAU_PER_DAY * idle_days) ** 2))


def v3_update(mu_a: float, sig_a: float, mu_b: float, sig_b: float,
              s_a: float, w_a: float = 1.0, w_b: float = 1.0):
    """One match update. Computes BOTH hypothetical OpenSkill posteriors
    (A wins / B wins) and interpolates by the continuous score s_a — this is
    what lets a strong loss raise μ, which the old multiplicative perf weight
    (clamped ≥0.2) structurally could not. Cross-region dampening then blends
    the result back toward the prior per player (w ∈ {1.0, CROSS_REGION_WEIGHT}).

    NOTE: openskill's rate() mutates its input Rating objects in place
    (verified 2026-05-26), so each call gets freshly constructed objects.

    Returns (new_mu_a, new_sig_a, new_mu_b, new_sig_b).
    """
    [[aw_a], [aw_b]] = MODEL.rate(
        [[MODEL.rating(mu=mu_a, sigma=sig_a)], [MODEL.rating(mu=mu_b, sigma=sig_b)]],
        ranks=[0, 1])
    [[bw_a], [bw_b]] = MODEL.rate(
        [[MODEL.rating(mu=mu_a, sigma=sig_a)], [MODEL.rating(mu=mu_b, sigma=sig_b)]],
        ranks=[1, 0])

    v2_mu_a = s_a * aw_a.mu + (1 - s_a) * bw_a.mu
    v2_sig_a = s_a * aw_a.sigma + (1 - s_a) * bw_a.sigma
    v2_mu_b = s_a * aw_b.mu + (1 - s_a) * bw_b.mu
    v2_sig_b = s_a * aw_b.sigma + (1 - s_a) * bw_b.sigma

    new_mu_a = mu_a + w_a * (v2_mu_a - mu_a)
    new_sig_a = max(SIGMA_FLOOR, sig_a + w_a * (v2_sig_a - sig_a))
    new_mu_b = mu_b + w_b * (v2_mu_b - mu_b)
    new_sig_b = max(SIGMA_FLOOR, sig_b + w_b * (v2_sig_b - sig_b))
    return new_mu_a, new_sig_a, new_mu_b, new_sig_b


def map_delta(resid_sum: float, n: int) -> float:
    """Shrunk map-effect in μ units. 0 games → 0 (pure global)."""
    if n <= 0:
        return 0.0
    return MAP_GAIN * (n / (n + MAP_SHRINK_K)) * (resid_sum / n)


def map_sigma(global_sigma: float, n: int) -> float:
    """σ for a per-map row: global belief + standard error of the shrunk
    deviation (per-game residual sd ≈ 0.5 in win-prob units)."""
    if n <= 0:
        return global_sigma
    se = MAP_GAIN * 0.5 * math.sqrt(n) / (n + MAP_SHRINK_K)
    return math.sqrt(global_sigma**2 + se**2)


# ── team-mode (4on4) engine constants ────────────────────────────────────────
# From the 2026-08-23 coordinate-descent sweep against held-out log-loss on the
# walk-forward 4on4 backtest (9,946 scored matches, 2024-08-23+, all 8 players
# ≥10 priors; scratchpad t4sweep.py). Final: logloss 0.5894 vs 0.6931 coin /
# 0.6105 pure OpenSkill; acc 68.1%; calibration within ~1-2pts per bucket.
# NOTE the differences from 1on1: margin gets MORE weight (W_RESULT 0.35 vs
# 0.65) because team margins are high-information (median |margin| 65 frags);
# beta lower (200); NO DDR term, NO idle aging, NO cross-region weighting —
# none were part of the validated backtest. Change only with a fresh backtest;
# update docs/4on4_methodology.md in the same commit.
TEAM_SIZE = {"4on4": 4}          # 2on2 needs its own sweep before enabling
TEAM_BETA = 200.0
TEAM_MODEL = PlackettLuce(mu=1500.0, sigma=500.0, beta=TEAM_BETA, tau=0.5, kappa=0.0001)
TEAM_EXP_AMP = 110.0             # expected TEAM frag diff = AMP·tanh(mean_gap/SCALE)
TEAM_EXP_SCALE = 700.0
TEAM_MARGIN_NORM = 40.0
TEAM_W_RESULT = 0.35
TEAM_SIGMA_FLOOR = 80.0
# Map layer + contribution weighting (2026-08-23/24 sweeps, walk-forward
# logloss): engine 0.5894 → +map 0.5694 (K=60, G=1900) → +contrib 0.5560
# (CW=1.1, μ-CONDITIONAL expected share), accuracy 68.1% → 71.5%.
# Contribution: personal outcome = team score + CW·(damage_share −
# expected_share), expected_share = own_mu / Σ team_mu. NOT flat 0.25 — that
# drained players on stronger teams and boosted players on weaker ones (the
# ntr/roster-context complaint, 2026-08-24). Higher CW keeps improving logloss
# slowly (0.5516 @ 3.0) but drifts toward pure performance rating with
# role-bias risk — raise only alongside role modeling.
TEAM_MAP_K = 60.0
TEAM_MAP_G = 1900.0
TEAM_CONTRIB_W = 1.1


def team_map_delta(resid_sum: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return TEAM_MAP_G * (n / (n + TEAM_MAP_K)) * (resid_sum / n)


def predict_team(ra: list, rb: list) -> float:
    """P(team A wins). ra/rb = [(mu, sigma), ...] per player."""
    dmu = sum(m for m, _ in ra) - sum(m for m, _ in rb)
    var = (len(ra) + len(rb)) * TEAM_BETA ** 2 + sum(s ** 2 for _, s in ra + rb)
    return 0.5 * (1.0 + math.erf(dmu / (math.sqrt(2 * var))))


def team_outcome_score(mean_mu_a: float, mean_mu_b: float, fa: int, fb: int) -> float:
    """Continuous outcome for team A — the validated t4/T2 form (no DDR term)."""
    expected = TEAM_EXP_AMP * math.tanh((mean_mu_a - mean_mu_b) / TEAM_EXP_SCALE)
    surprise = (fa - fb) - expected
    margin_s = 1.0 / (1.0 + math.exp(-surprise / TEAM_MARGIN_NORM))
    binary = 0.5 if fa == fb else (1.0 if fa > fb else 0.0)
    return TEAM_W_RESULT * binary + (1 - TEAM_W_RESULT) * margin_s


def team_update(ra: list, rb: list, s: float):
    """One team-match update, interpolating win-case/loss-case posteriors by s.
    ra/rb = [(mu, sigma), ...]; returns (new_ra, new_rb) same shape."""
    def fresh():
        RA = [TEAM_MODEL.rating(mu=m, sigma=g) for m, g in ra]
        RB = [TEAM_MODEL.rating(mu=m, sigma=g) for m, g in rb]
        return RA, RB
    RA, RB = fresh()
    [wa, wb] = TEAM_MODEL.rate([RA, RB], ranks=[0, 1])
    RA2, RB2 = fresh()
    [la, lb] = TEAM_MODEL.rate([RA2, RB2], ranks=[1, 0])
    new_a = [(s * w.mu + (1 - s) * l.mu,
              max(TEAM_SIGMA_FLOOR, s * w.sigma + (1 - s) * l.sigma))
             for w, l in zip(wa, la)]
    new_b = [(s * w.mu + (1 - s) * l.mu,
              max(TEAM_SIGMA_FLOOR, s * w.sigma + (1 - s) * l.sigma))
             for w, l in zip(wb, lb)]
    return new_a, new_b


def _bulk_insert_history(cur, rows):
    """Single round-trip insert via execute_values. ~100× faster than executemany.
    Dedupes by PK (canonical_id, mode, map, match_id) first — rare but real when a
    player has multiple `players` rows in one match (joined/disconnected/rejoined)."""
    by_pk = {}
    for r in rows:
        by_pk[(r[0], r[1], r[2], r[3])] = r
    deduped = list(by_pk.values())
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO rating_history
           (canonical_id, mode, map, match_id, match_date, opponent_cid, outcome,
            mu_before, mu_after, sigma_before, sigma_after, delta)
           VALUES %s
           ON CONFLICT (canonical_id, mode, map, match_id) DO UPDATE
           SET match_date=EXCLUDED.match_date, opponent_cid=EXCLUDED.opponent_cid,
               outcome=EXCLUDED.outcome, mu_before=EXCLUDED.mu_before,
               mu_after=EXCLUDED.mu_after, sigma_before=EXCLUDED.sigma_before,
               sigma_after=EXCLUDED.sigma_after, delta=EXCLUDED.delta""",
        deduped,
        page_size=2000,
    )


def _bulk_insert_ratings(cur, rows):
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO ratings
           (canonical_id, mode, map, mu, sigma, conservative,
            matches_rated, wins, losses, draws,
            last_match_id, last_match_date, updated_at, unique_opponents,
            avg_ddr, avg_frag_diff)
           VALUES %s
           ON CONFLICT (canonical_id, mode, map) DO UPDATE SET
             mu=EXCLUDED.mu, sigma=EXCLUDED.sigma, conservative=EXCLUDED.conservative,
             matches_rated=EXCLUDED.matches_rated, wins=EXCLUDED.wins,
             losses=EXCLUDED.losses, draws=EXCLUDED.draws,
             last_match_id=EXCLUDED.last_match_id, last_match_date=EXCLUDED.last_match_date,
             updated_at=EXCLUDED.updated_at, unique_opponents=EXCLUDED.unique_opponents,
             -- Don't blow away perf precompute for players who had no NEW matches
             -- in this incremental run (their EXCLUDED.avg_ddr would be NULL).
             avg_ddr=COALESCE(EXCLUDED.avg_ddr, ratings.avg_ddr),
             avg_frag_diff=COALESCE(EXCLUDED.avg_frag_diff, ratings.avg_frag_diff)""",
        rows,
        page_size=2000,
    )


def ensure_schema(conn):
    """Idempotent DDL: perf columns on ratings + the map_residuals accumulator
    table (v3). map_residuals persists per-(player, map) residual state so
    --incremental runs continue exactly where the last run stopped — including
    cells still below per_map_min that have no ratings row yet."""
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE ratings
        ADD COLUMN IF NOT EXISTS avg_ddr REAL,
        ADD COLUMN IF NOT EXISTS avg_frag_diff REAL
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS map_residuals (
            canonical_id TEXT NOT NULL,
            mode         TEXT NOT NULL,
            map          TEXT NOT NULL,
            resid_sum    DOUBLE PRECISION NOT NULL DEFAULT 0,
            n            INTEGER NOT NULL DEFAULT 0,
            wins         INTEGER NOT NULL DEFAULT 0,
            losses       INTEGER NOT NULL DEFAULT 0,
            draws        INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (canonical_id, mode, map)
        )
    """)
    conn.commit()
    cur.close()


# Backwards-compat alias (admin tooling referenced the old name).
ensure_perf_columns = ensure_schema


def load_existing_ratings(conn, mode):
    """Return (cache, stats) for incremental runs — overall bucket only.
    cache: {cid: [mu, sigma]}."""
    cache = {}
    stats = {}
    cur = conn.cursor()
    cur.execute(
        "SELECT canonical_id, mu, sigma, matches_rated, wins, losses, draws "
        "FROM ratings WHERE mode=%s AND map=''",
        (mode,),
    )
    for r in cur.fetchall():
        cid = r["canonical_id"]
        cache[cid] = [r["mu"], r["sigma"]]
        stats[cid] = {"matches": r["matches_rated"] or 0, "wins": r["wins"] or 0,
                      "losses": r["losses"] or 0, "draws": r["draws"] or 0}
    cur.close()
    return cache, stats


def load_map_residuals(conn, mode):
    """{(cid, map): {"rs": resid_sum, "n": n, "wins": w, "losses": l, "draws": d}}"""
    cells = {}
    cur = conn.cursor()
    cur.execute("SELECT canonical_id, map, resid_sum, n, wins, losses, draws "
                "FROM map_residuals WHERE mode=%s", (mode,))
    for r in cur.fetchall():
        cells[(r["canonical_id"], r["map"])] = {
            "rs": r["resid_sum"], "n": r["n"],
            "wins": r["wins"], "losses": r["losses"], "draws": r["draws"]}
    cur.close()
    return cells


def load_last_dates(conn, mode):
    """{cid: last rated match_date} — seeds idle-day σ aging on incremental runs."""
    cur = conn.cursor()
    cur.execute("SELECT canonical_id, MAX(match_date) AS last FROM rating_history "
                "WHERE mode=%s AND map='' GROUP BY canonical_id", (mode,))
    out = {r["canonical_id"]: r["last"] for r in cur.fetchall()}
    cur.close()
    return out


def load_player_regions(conn):
    """{canonical_id: region}. Players without an assigned region get None."""
    cur = conn.cursor()
    cur.execute("SELECT canonical_id, region FROM players_canonical WHERE region IS NOT NULL")
    out = {r["canonical_id"]: r["region"] for r in cur.fetchall()}
    cur.close()
    return out


def list_maps_for_mode(conn, mode, min_matches=10):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT match_map FROM matches
        WHERE match_mode = %s AND match_map IS NOT NULL
        GROUP BY match_map
        HAVING count(*) >= %s
        ORDER BY count(*) DESC
        """,
        (mode, min_matches),
    )
    out = [r["match_map"] for r in cur.fetchall()]
    cur.close()
    return out


def fetch_matches(conn, mode, since_date=None):
    """Yield per-match tuples with all data needed for the v3 engine.

    Columns: match_id, match_date, match_map, cid_a, frags_a, dmg_given_a,
             dmg_taken_a, cid_b, frags_b, dmg_given_b, dmg_taken_b, server_region.

    server_region lookup: matches.server_hostname → strip port → servers.hostname.
    None when geo unknown. Damage columns may be NULL on older pre-KTX matches —
    the outcome score falls back to margin-only in that case.
    """
    where_extra = ""
    params = {"mode": mode}
    if since_date:
        where_extra += " AND m.match_date > %(since)s"
        params["since"] = since_date
    cur = conn.cursor()
    # CRITICAL: aggregate per (match_id, canonical_id) BEFORE the self-join.
    # Without this, a player who appears with multiple name variants in the same
    # match (e.g. reconnects with different color codes) creates a cartesian-
    # product blowup on the pairwise join — verified 2026-05-27, cronus
    # matches_rated was 3× inflated. Frags/damage are SUMmed across variants
    # since rejoining within a match should count as continuing play.
    cur.execute(
        f"""
        WITH match_players AS (
            SELECT m.match_id, m.match_date, m.match_map, m.server_hostname,
                   p.canonical_id,
                   SUM(p.player_frags) AS frags,
                   SUM(p.player_damage_given) AS dmg_given,
                   SUM(p.player_damage_taken) AS dmg_taken
            FROM matches m
            JOIN players p ON p.match_id = m.match_id
            WHERE m.match_mode = %(mode)s
              AND p.canonical_id IS NOT NULL
              {where_extra}
            GROUP BY m.match_id, m.match_date, m.match_map, m.server_hostname, p.canonical_id
        )
        SELECT mp1.match_id, mp1.match_date, mp1.match_map,
               mp1.canonical_id AS cid_a, mp1.frags AS f_a, mp1.dmg_given AS dg_a, mp1.dmg_taken AS dt_a,
               mp2.canonical_id AS cid_b, mp2.frags AS f_b, mp2.dmg_given AS dg_b, mp2.dmg_taken AS dt_b,
               s.region AS server_region
        FROM match_players mp1
        JOIN match_players mp2 ON mp1.match_id = mp2.match_id
                              AND mp1.canonical_id < mp2.canonical_id
        LEFT JOIN servers s ON s.hostname = split_part(mp1.server_hostname, ':', 1)
        ORDER BY mp1.match_date
        """,
        params,
    )
    for r in cur.fetchall():
        yield (r["match_id"], r["match_date"], r["match_map"],
               r["cid_a"], r["f_a"], r["dg_a"], r["dt_a"],
               r["cid_b"], r["f_b"], r["dg_b"], r["dt_b"],
               r["server_region"])
    cur.close()


def _weights_for_match(player_a_region, player_b_region, server_region):
    """Return (weight_a, weight_b) reflecting cross-region disadvantage.

    A player is "away" when the server is in a different region than their home.
    Away players' updates are dampened to CROSS_REGION_WEIGHT. Home players unaffected.
    When any region is unknown, treat as fair-weight (1.0) — no penalty for missing data.
    """
    if not server_region:
        return 1.0, 1.0
    w_a = CROSS_REGION_WEIGHT if (player_a_region and player_a_region != server_region) else 1.0
    w_b = CROSS_REGION_WEIGHT if (player_b_region and player_b_region != server_region) else 1.0
    return w_a, w_b


def _idle_days(last, current) -> float:
    if last is None or current is None:
        return 0.0
    try:
        return max(0.0, (current - last).total_seconds() / 86400.0)
    except TypeError:
        return 0.0  # mixed naive/aware or string leakage — no aging over bad data


def rate_all(db, mode, now, full_rebuild=True, per_map_min=5, player_regions=None):
    """ONE chronological pass over every match in `mode`:
      - v3 overall rating update per match (continuous-margin OpenSkill)
      - per-map residual accumulation vs the pre-match GLOBAL prediction
        (this is what kills the old engine's temporal leakage: the residual is
        always measured against the belief AT THAT MATCH, never the final one)
      - history rows for the '' bucket and (when the map qualifies) the map bucket

    Returns (n_matches, n_overall_rows, n_map_rows).
    """
    if player_regions is None:
        player_regions = {}
    cur = db.cursor()

    maps_ok = set(list_maps_for_mode(db, mode, min_matches=MAP_MIN_CORPUS))

    if full_rebuild:
        cur.execute("DELETE FROM ratings WHERE mode=%s", (mode,))
        cur.execute("DELETE FROM rating_history WHERE mode=%s", (mode,))
        cur.execute("DELETE FROM map_residuals WHERE mode=%s", (mode,))
        db.commit()
        cache, stats = {}, {}
        cells = {}
        last_date = {}
        since_date = None
    else:
        cache, stats = load_existing_ratings(db, mode)
        cells = load_map_residuals(db, mode)
        last_date = load_last_dates(db, mode)
        cur.execute(
            "SELECT MAX(match_date) AS last FROM rating_history WHERE mode=%s AND map=''",
            (mode,),
        )
        row = cur.fetchone()
        since_date = row["last"] if row else None

    matches = list(fetch_matches(db, mode, since_date=since_date))
    if not matches:
        return 0, 0, 0

    # Per-player perf accumulators, keyed by (cid, map_bucket) with '' = overall.
    # Precomputed here so /api/rankings doesn't aggregate millions of rows.
    perf = {}

    def _accum_perf(cid, bucket, dg, dt, frag_diff):
        if dg is None or dt is None:
            return
        p = perf.setdefault((cid, bucket), {"dg": 0, "dt": 0, "fd_sum": 0.0, "n": 0})
        p["dg"] += dg
        p["dt"] += dt
        p["fd_sum"] += frag_diff
        p["n"] += 1

    history_rows = []
    n_skipped = 0
    touched_cells = set()
    played_this_run = set()

    for (match_id, match_date, match_map,
         cid_a, f_a, dg_a, dt_a,
         cid_b, f_b, dg_b, dt_b,
         server_region) in matches:
        if cid_a == cid_b or f_a is None or f_b is None:
            n_skipped += 1
            continue

        ra = cache.setdefault(cid_a, [1500.0, 500.0])
        rb = cache.setdefault(cid_b, [1500.0, 500.0])
        sa = stats.setdefault(cid_a, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        sb = stats.setdefault(cid_b, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        mu_a_pre, sig_a_pre = ra
        mu_b_pre, sig_b_pre = rb

        mp = (match_map or "").lower() if match_map else None
        rated_map = mp if (mp and mp in maps_ok) else None

        # ── per-map bookkeeping happens against the PRE-update global belief
        if rated_map:
            cell_a = cells.setdefault((cid_a, rated_map),
                                      {"rs": 0.0, "n": 0, "wins": 0, "losses": 0, "draws": 0})
            cell_b = cells.setdefault((cid_b, rated_map),
                                      {"rs": 0.0, "n": 0, "wins": 0, "losses": 0, "draws": 0})
            map_mu_a_pre = mu_a_pre + map_delta(cell_a["rs"], cell_a["n"])
            map_mu_b_pre = mu_b_pre + map_delta(cell_b["rs"], cell_b["n"])
            map_sig_a_pre = map_sigma(sig_a_pre, cell_a["n"])
            map_sig_b_pre = map_sigma(sig_b_pre, cell_b["n"])
            p_global = predict_win(mu_a_pre, sig_a_pre, mu_b_pre, sig_b_pre)

        _accum_perf(cid_a, "", dg_a, dt_a, (f_a or 0) - (f_b or 0))
        _accum_perf(cid_b, "", dg_b, dt_b, (f_b or 0) - (f_a or 0))
        if rated_map:
            _accum_perf(cid_a, rated_map, dg_a, dt_a, (f_a or 0) - (f_b or 0))
            _accum_perf(cid_b, rated_map, dg_b, dt_b, (f_b or 0) - (f_a or 0))

        # ── idle-day σ aging (applies at the moment a player returns to play)
        aged_a = aged_sigma(sig_a_pre, _idle_days(last_date.get(cid_a), match_date))
        aged_b = aged_sigma(sig_b_pre, _idle_days(last_date.get(cid_b), match_date))
        last_date[cid_a] = match_date
        last_date[cid_b] = match_date

        # ── outcome + W/L/D bookkeeping
        if f_a > f_b:
            out_a, out_b = "win", "loss"
            sa["wins"] += 1
            sb["losses"] += 1
            y_eff = 1.0
        elif f_b > f_a:
            out_a, out_b = "loss", "win"
            sb["wins"] += 1
            sa["losses"] += 1
            y_eff = 0.0
        else:
            out_a = out_b = "draw"
            sa["draws"] += 1
            sb["draws"] += 1
            y_eff = 0.5
        sa["matches"] += 1
        sb["matches"] += 1
        played_this_run.add(cid_a)
        played_this_run.add(cid_b)

        # ── v3 global update
        wa_cr, wb_cr = _weights_for_match(
            player_regions.get(cid_a), player_regions.get(cid_b), server_region
        )
        s_a = outcome_score(mu_a_pre, mu_b_pre, f_a, f_b, dg_a, dt_a)
        new_mu_a, new_sig_a, new_mu_b, new_sig_b = v3_update(
            mu_a_pre, aged_a, mu_b_pre, aged_b, s_a, wa_cr, wb_cr)
        ra[0], ra[1] = new_mu_a, new_sig_a
        rb[0], rb[1] = new_mu_b, new_sig_b

        history_rows.append((cid_a, mode, "", match_id, match_date, cid_b, out_a,
                             mu_a_pre, new_mu_a, sig_a_pre, new_sig_a, new_mu_a - mu_a_pre))
        history_rows.append((cid_b, mode, "", match_id, match_date, cid_a, out_b,
                             mu_b_pre, new_mu_b, sig_b_pre, new_sig_b, new_mu_b - mu_b_pre))

        # ── per-map residual update + history
        if rated_map:
            cell_a["rs"] += y_eff - p_global
            cell_b["rs"] += (1.0 - y_eff) - (1.0 - p_global)
            cell_a["n"] += 1
            cell_b["n"] += 1
            key_wld = {"win": "wins", "loss": "losses", "draw": "draws"}
            cell_a[key_wld[out_a]] += 1
            cell_b[key_wld[out_b]] += 1
            touched_cells.add((cid_a, rated_map))
            touched_cells.add((cid_b, rated_map))

            map_mu_a_post = new_mu_a + map_delta(cell_a["rs"], cell_a["n"])
            map_mu_b_post = new_mu_b + map_delta(cell_b["rs"], cell_b["n"])
            history_rows.append((cid_a, mode, rated_map, match_id, match_date, cid_b, out_a,
                                 map_mu_a_pre, map_mu_a_post,
                                 map_sig_a_pre, map_sigma(new_sig_a, cell_a["n"]),
                                 map_mu_a_post - map_mu_a_pre))
            history_rows.append((cid_b, mode, rated_map, match_id, match_date, cid_a, out_b,
                                 map_mu_b_pre, map_mu_b_post,
                                 map_sig_b_pre, map_sigma(new_sig_b, cell_b["n"]),
                                 map_mu_b_post - map_mu_b_pre))

        if len(history_rows) >= 5000:
            _bulk_insert_history(cur, history_rows)
            history_rows = []
            db.commit()

    if history_rows:
        _bulk_insert_history(cur, history_rows)

    # ── persist per-map accumulator state (touched cells only on incremental —
    # untouched cells are already stored; full rebuild writes everything)
    if touched_cells or full_rebuild:
        write_cells = cells.items() if full_rebuild else \
            [((cid, mp), cells[(cid, mp)]) for (cid, mp) in touched_cells]
        resid_rows = [(cid, mode, mp, c["rs"], c["n"], c["wins"], c["losses"], c["draws"])
                      for (cid, mp), c in write_cells]
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO map_residuals
               (canonical_id, mode, map, resid_sum, n, wins, losses, draws)
               VALUES %s
               ON CONFLICT (canonical_id, mode, map) DO UPDATE SET
                 resid_sum=EXCLUDED.resid_sum, n=EXCLUDED.n, wins=EXCLUDED.wins,
                 losses=EXCLUDED.losses, draws=EXCLUDED.draws""",
            resid_rows, page_size=2000)

    # Unique-opponent counts for every bucket in one query — surfaced as the
    # UI "Provisional" hint (no math adjustment since the OpenSkill migration).
    cur.execute("""
        SELECT canonical_id, map, COUNT(DISTINCT opponent_cid) AS n
        FROM rating_history WHERE mode = %s AND opponent_cid IS NOT NULL
        GROUP BY canonical_id, map
    """, (mode,))
    uniq = {(r["canonical_id"], r["map"]): r["n"] for r in cur.fetchall()}

    # Players flagged `unrated` get NO published rating (their games still count
    # toward OPPONENTS' ratings — we just never write a rating row for them).
    cur.execute("ALTER TABLE players_canonical ADD COLUMN IF NOT EXISTS unrated BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("SELECT canonical_id FROM players_canonical WHERE unrated")
    _unrated = {row["canonical_id"] for row in cur.fetchall()}

    # ── overall rating rows
    rating_rows = []
    for cid, (mu, sigma) in cache.items():
        if cid in _unrated:
            continue
        s = stats.get(cid, {})
        pf = perf.get((cid, ""))
        avg_ddr = (pf["dg"] / pf["dt"]) if (pf and pf["dt"] > 0) else None
        avg_frag_diff = (pf["fd_sum"] / pf["n"]) if (pf and pf["n"] > 0) else None
        rating_rows.append((cid, mode, "", mu, sigma, mu - 3 * sigma,
                            s.get("matches", 0), s.get("wins", 0),
                            s.get("losses", 0), s.get("draws", 0),
                            None, None, now, uniq.get((cid, ""), 0),
                            avg_ddr, avg_frag_diff))
    n_overall = len(rating_rows)

    # ── per-map rating rows, derived from final global rating + shrunk deviation.
    # A cell needs rewriting when its accumulator moved OR the global μ under it
    # moved — i.e. whenever the PLAYER appeared this run. Full rebuild: everyone.
    n_map = 0
    for (cid, mp), c in cells.items():
        if cid in _unrated or c["n"] < per_map_min or mp not in maps_ok:
            continue
        if not full_rebuild and cid not in played_this_run:
            continue
        g = cache.get(cid)
        if not g:
            continue
        mu = g[0] + map_delta(c["rs"], c["n"])
        sigma = map_sigma(g[1], c["n"])
        pf = perf.get((cid, mp))
        avg_ddr = (pf["dg"] / pf["dt"]) if (pf and pf["dt"] > 0) else None
        avg_frag_diff = (pf["fd_sum"] / pf["n"]) if (pf and pf["n"] > 0) else None
        rating_rows.append((cid, mode, mp, mu, sigma, mu - 3 * sigma,
                            c["n"], c["wins"], c["losses"], c["draws"],
                            None, None, now, uniq.get((cid, mp), 0),
                            avg_ddr, avg_frag_diff))
        n_map += 1

    if rating_rows:
        _bulk_insert_ratings(cur, rating_rows)
    db.commit()
    cur.close()
    return len(matches), n_overall, n_map


def fetch_team_matches(conn, mode, since_date=None):
    """Yield (match_id, match_date, match_map, teamA, teamB) where each team is a list of
    (cid, frags, deaths, dmg_given, dmg_taken), STRICTLY chronological. Only
    matches with exactly two teams of TEAM_SIZE[mode] players survive — mixed
    joins/leavers and odd formats are skipped (same rule as the backtest)."""
    size = TEAM_SIZE[mode]
    where = ""
    params = {"mode": mode}
    if since_date:
        where = " AND m.match_date > %(since)s"
        params["since"] = since_date
    cur = conn.cursor()
    cur.execute(f"""
        SELECT m.match_id, m.match_date, m.match_map,
               p.canonical_id AS cid, MIN(p.player_team) AS team,
               SUM(p.player_frags) AS frags, SUM(p.player_deaths) AS deaths,
               SUM(p.player_damage_given) AS dg, SUM(p.player_damage_taken) AS dt
        FROM matches m JOIN players p ON p.match_id = m.match_id
        WHERE m.match_mode = %(mode)s AND p.canonical_id IS NOT NULL
          AND COALESCE(m.has_bots, 0) = 0
          {where}
        GROUP BY m.match_id, m.match_date, m.match_map, p.canonical_id
        ORDER BY m.match_date, m.match_id
    """, params)
    cur_mid, cur_date, cur_map, bucket = None, None, None, {}
    def emit():
        if cur_mid is None:
            return None
        teams = {}
        for cid, (team, fr, de, dg, dt) in bucket.items():
            teams.setdefault((team or "").lower(), []).append((cid, fr, de, dg, dt))
        if len(teams) != 2:
            return None
        (ta, pa), (tb, pb) = sorted(teams.items())
        if len(pa) != size or len(pb) != size:
            return None
        if any(r[1] is None for r in pa + pb):
            return None
        return (cur_mid, cur_date, cur_map, pa, pb)
    for r in cur.fetchall():
        if r["match_id"] != cur_mid:
            m = emit()
            if m:
                yield m
            cur_mid, cur_date, cur_map, bucket = r["match_id"], r["match_date"], (r["match_map"] or "").lower(), {}
        bucket[r["cid"]] = (r["team"], r["frags"], r["deaths"], r["dg"], r["dt"])
    m = emit()
    if m:
        yield m
    cur.close()


def rate_team_mode(db, mode, now, full_rebuild=True, per_map_min=5):
    """Single chronological pass for a team mode (4on4). Per player:
    - global mu/sigma from the continuous team-margin outcome, with each
      player's personal score shifted by their DAMAGE SHARE within the team
      (TEAM_CONTRIB_W; expected share = own μ / team μ sum) — individual improvement moves
      individual ratings;
    - per-(player,map) shrunk deviations learned from residuals vs the
      MAP-ADJUSTED prediction (state persisted in map_residuals).
    No cross-region, no idle aging — not part of the validated backtest."""
    cur = db.cursor()
    if full_rebuild:
        cur.execute("DELETE FROM ratings WHERE mode=%s", (mode,))
        cur.execute("DELETE FROM rating_history WHERE mode=%s", (mode,))
        cur.execute("DELETE FROM map_residuals WHERE mode=%s", (mode,))
        db.commit()
        cache, stats, cells = {}, {}, {}
        since_date = None
    else:
        cache_raw, stats = load_existing_ratings(db, mode)
        cache = {k: (v[0], v[1]) if not isinstance(v, tuple) else v
                 for k, v in cache_raw.items()}
        cells = load_map_residuals(db, mode)
        cur.execute("SELECT MAX(match_date) AS last FROM rating_history "
                    "WHERE mode=%s AND map=''", (mode,))
        row = cur.fetchone()
        since_date = row["last"] if row else None

    perf = {}
    history_rows = []
    n_matches = 0
    for (mid, mdate, mp, TA, TB) in fetch_team_matches(db, mode, since_date=since_date):
        A = [r[0] for r in TA]
        B = [r[0] for r in TB]
        fa = sum(r[1] for r in TA)
        fb = sum(r[1] for r in TB)
        for cid in A + B:
            cache.setdefault(cid, (1500.0, 500.0))
            stats.setdefault(cid, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        ra = [cache[c] for c in A]
        rb = [cache[c] for c in B]

        # map-adjusted prediction — used ONLY to learn map residuals (this is
        # the exact form the backtest validated; the global update below uses
        # unadjusted mus for its outcome score).
        if mp:
            def _eff(c):
                m, g = cache[c]
                cell = cells.get((c, mp))
                if cell and cell["n"]:
                    m += team_map_delta(cell["rs"], cell["n"])
                return m, g
            ea = [_eff(c) for c in A]
            eb = [_eff(c) for c in B]
            p_map = predict_team(ea, eb)
            if fa != fb:
                y = 1.0 if fa > fb else 0.0
                for c in A:
                    cell = cells.setdefault((c, mp), {"rs": 0.0, "n": 0, "wins": 0, "losses": 0, "draws": 0})
                    cell["rs"] += y - p_map
                    cell["n"] += 1
                    cell["wins" if y == 1.0 else "losses"] += 1
                for c in B:
                    cell = cells.setdefault((c, mp), {"rs": 0.0, "n": 0, "wins": 0, "losses": 0, "draws": 0})
                    cell["rs"] += (1 - y) - (1 - p_map)
                    cell["n"] += 1
                    cell["wins" if y == 0.0 else "losses"] += 1
            else:
                for c in A + B:
                    cell = cells.setdefault((c, mp), {"rs": 0.0, "n": 0, "wins": 0, "losses": 0, "draws": 0})
                    cell["n"] += 1
                    cell["draws"] += 1

        # team outcome + contribution-weighted per-player interpolation
        s_team = team_outcome_score(sum(m for m, _ in ra) / len(ra),
                                    sum(m for m, _ in rb) / len(rb), fa, fb)
        tdg_a = sum((r[3] or 0) for r in TA)
        tdg_b = sum((r[3] or 0) for r in TB)

        mu_sum_a = sum(m for m, _ in ra)
        mu_sum_b = sum(m for m, _ in rb)

        def _si(row, tdg, s, own_mu, mu_team):
            if TEAM_CONTRIB_W <= 0 or not tdg or row[3] is None:
                return s
            share = (row[3] or 0) / tdg
            expected = own_mu / mu_team if mu_team > 0 else 0.25
            return min(1.0, max(0.0, s + TEAM_CONTRIB_W * (share - expected)))

        RA = [TEAM_MODEL.rating(mu=m, sigma=g) for m, g in ra]
        RB = [TEAM_MODEL.rating(mu=m, sigma=g) for m, g in rb]
        [wa, wb] = TEAM_MODEL.rate([RA, RB], ranks=[0, 1])
        RA2 = [TEAM_MODEL.rating(mu=m, sigma=g) for m, g in ra]
        RB2 = [TEAM_MODEL.rating(mu=m, sigma=g) for m, g in rb]
        [la, lb] = TEAM_MODEL.rate([RA2, RB2], ranks=[1, 0])

        if fa > fb:
            out_a, out_b = "win", "loss"
        elif fb > fa:
            out_a, out_b = "loss", "win"
        else:
            out_a = out_b = "draw"
        opp_a = ",".join(sorted(B))
        opp_b = ",".join(sorted(A))

        for row, (om, og), w, l in zip(TA, ra, wa, la):
            cid = row[0]
            si = _si(row, tdg_a, s_team, om, mu_sum_a)
            nm = si * w.mu + (1 - si) * l.mu
            ns = max(TEAM_SIGMA_FLOOR, si * w.sigma + (1 - si) * l.sigma)
            history_rows.append((cid, mode, "", mid, mdate, opp_a, out_a,
                                 om, nm, og, ns, nm - om))
            cache[cid] = (nm, ns)
            st = stats[cid]
            st["matches"] += 1
            st["wins" if out_a == "win" else "losses" if out_a == "loss" else "draws"] += 1
        for row, (om, og), w, l in zip(TB, rb, wb, lb):
            cid = row[0]
            si = _si(row, tdg_b, 1.0 - s_team, om, mu_sum_b)
            nm = si * l.mu + (1 - si) * w.mu
            ns = max(TEAM_SIGMA_FLOOR, si * l.sigma + (1 - si) * w.sigma)
            history_rows.append((cid, mode, "", mid, mdate, opp_b, out_b,
                                 om, nm, og, ns, nm - om))
            cache[cid] = (nm, ns)
            st = stats[cid]
            st["matches"] += 1
            st["wins" if out_b == "win" else "losses" if out_b == "loss" else "draws"] += 1

        for (cid, fr, de, dg, dt) in TA + TB:
            if dg is not None and dt is not None:
                pf = perf.setdefault(cid, {"dg": 0, "dt": 0, "fd": 0.0, "n": 0})
                pf["dg"] += dg
                pf["dt"] += dt
                pf["fd"] += (fr or 0) - (de or 0)
                pf["n"] += 1
        n_matches += 1
        if len(history_rows) >= 5000:
            _bulk_insert_history(cur, history_rows)
            history_rows = []
            db.commit()
    if history_rows:
        _bulk_insert_history(cur, history_rows)

    # persist map cells
    resid_rows = [(cid, mode, mp_, c["rs"], c["n"], c["wins"], c["losses"], c["draws"])
                  for (cid, mp_), c in cells.items()]
    if resid_rows:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO map_residuals
               (canonical_id, mode, map, resid_sum, n, wins, losses, draws)
               VALUES %s
               ON CONFLICT (canonical_id, mode, map) DO UPDATE SET
                 resid_sum=EXCLUDED.resid_sum, n=EXCLUDED.n, wins=EXCLUDED.wins,
                 losses=EXCLUDED.losses, draws=EXCLUDED.draws""",
            resid_rows, page_size=2000)

    cur.execute("""SELECT canonical_id, COUNT(DISTINCT opponent_cid) AS n
                   FROM rating_history WHERE mode=%s AND opponent_cid IS NOT NULL
                   GROUP BY canonical_id""", (mode,))
    uniq = {r["canonical_id"]: r["n"] for r in cur.fetchall()}
    cur.execute("SELECT canonical_id FROM players_canonical WHERE unrated")
    _unrated = {r["canonical_id"] for r in cur.fetchall()}
    # Anti-alias gate (Peter, 2026-08-24): no duel rating → no PUBLISHED team
    # rating. Throwaway alias accounts live in team modes and rarely duel; a
    # 1on1 ratings row is the cheap identity bar. Their matches still count
    # toward opponents' ratings — publishing is all that's gated (reversible
    # by rerate after a merge lands them under their real identity).
    cur.execute("SELECT canonical_id FROM ratings WHERE mode='1on1' AND map=''")
    duel_rated = {r["canonical_id"] for r in cur.fetchall()}

    rating_rows = []
    n_gated = 0
    for cid, (mu, sig) in cache.items():
        if cid in _unrated:
            continue
        if cid not in duel_rated:
            n_gated += 1
            continue
        st = stats.get(cid, {})
        if not st.get("matches"):
            continue
        pf = perf.get(cid)
        avg_ddr = (pf["dg"] / pf["dt"]) if (pf and pf["dt"] > 0) else None
        avg_fd = (pf["fd"] / pf["n"]) if (pf and pf["n"] > 0) else None
        rating_rows.append((cid, mode, "", mu, sig, mu - 3 * sig,
                            st["matches"], st["wins"], st["losses"], st["draws"],
                            None, None, now, uniq.get(cid, 0), avg_ddr, avg_fd))
    # per-map rows: mu = global + shrunk map delta (recomputed every run so they
    # never drift from the current global rating)
    n_map_rows = 0
    for (cid, mp_), c in cells.items():
        if cid in _unrated or cid not in duel_rated or c["n"] < per_map_min:
            continue
        base = cache.get(cid)
        if not base:
            continue
        mu_m = base[0] + team_map_delta(c["rs"], c["n"])
        rating_rows.append((cid, mode, mp_, mu_m, base[1], mu_m - 3 * base[1],
                            c["n"], c["wins"], c["losses"], c["draws"],
                            None, None, now, 0, None, None))
        n_map_rows += 1
    if rating_rows:
        _bulk_insert_ratings(cur, rating_rows)
    db.commit()
    cur.close()
    print(f"  duel-rating gate: {n_gated:,} team-only identities NOT published")
    return n_matches, len(rating_rows) - n_map_rows


def run(db_path: Path, mode: str = "1on1", incremental: bool = False, per_map_min: int = 5):
    db = dbmod.connect()
    now = datetime.now(timezone.utc).isoformat()
    full_rebuild = not incremental
    ensure_schema(db)
    if mode in TEAM_SIZE:
        print(f"Engine {ENGINE_VERSION} — TEAM mode {mode} "
              f"(beta={TEAM_BETA:.0f}, w_result={TEAM_W_RESULT}, amp={TEAM_EXP_AMP:.0f}, "
              f"{'FULL REBUILD' if full_rebuild else 'incremental'})…")
        start = datetime.now()
        n_matches, n_rows = rate_team_mode(db, mode, now, full_rebuild=full_rebuild)
        elapsed = (datetime.now() - start).total_seconds()
        print(f"  {n_matches:,} team matches → {n_rows:,} player rating rows in {elapsed:.1f}s")
        _sanity_top10(db, mode)
        return
    if mode == "2on2":
        print("2on2 is NOT enabled: constants are unvalidated (needs its own backtest sweep).")
        return
    player_regions = load_player_regions(db)
    print(f"Engine {ENGINE_VERSION} — loaded regions for {len(player_regions):,} players.")

    print(f"Rating {mode} (continuous-margin OpenSkill, cross-region weight={CROSS_REGION_WEIGHT}, "
          f"per-map shrinkage K={MAP_SHRINK_K:.0f} G={MAP_GAIN:.0f}, "
          f"{'FULL REBUILD' if full_rebuild else 'incremental'})…")
    start = datetime.now()
    n_matches, n_overall, n_map = rate_all(db, mode, now, full_rebuild=full_rebuild,
                                           per_map_min=per_map_min,
                                           player_regions=player_regions)
    elapsed = (datetime.now() - start).total_seconds()
    print(f"  {n_matches:,} matches → {n_overall:,} overall + {n_map:,} per-map "
          f"rating rows in {elapsed:.1f}s")

    _sanity_top10(db, mode)


def _sanity_top10(db, mode):
    print(f"\nTop 10 {mode} OVERALL (by conservative rating):")
    sanity_cur = db.cursor()
    sanity_cur.execute(
        """
        SELECT r.canonical_id, pc.display_name, pc.region, r.mu, r.sigma, r.conservative,
               r.matches_rated, r.wins, r.losses
        FROM ratings r
        LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
        WHERE r.mode = %s AND r.map = '' AND r.matches_rated >= 50
        ORDER BY r.conservative DESC LIMIT 10
        """,
        (mode,),
    )
    top = sanity_cur.fetchall()
    for t in top:
        name = t["display_name"] or t["canonical_id"]
        reg = (t["region"] or "??")[:2]
        print(f"  μ={t['mu']:7.1f} σ={t['sigma']:5.1f} cons={t['conservative']:7.1f}  "
              f"{t['wins']:5}W-{t['losses']:5}L  [{reg}]  {name}")
    sanity_cur.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--mode", default="1on1", choices=["1on1", "2on2", "4on4"])
    p.add_argument("--incremental", action="store_true",
                   help="Only rate matches after the latest match_date in rating_history")
    args = p.parse_args()
    run(Path(args.db), args.mode, args.incremental)

#!/usr/bin/env python3
"""Compute OpenSkill (Weng-Lin Plackett-Luce) ratings — 1on1, W/L-based.

Replaces TrueSkill (deprecated 2026-05-26). OpenSkill advantages:
  - Per-player σ updates reflect information content of each match (not a global tau).
  - Drops the need for a separate diversity-penalty σ multiplier.
  - MIT-licensed, actively maintained (openskill.py).
  - Native team support — same engine will power 2on2/4on4 when those land.

Walks every 1on1 match in chronological order, updates both players' ratings,
persists current state in `ratings` and per-match deltas in `rating_history`.

Inter-regional weighting:
  When a player plays on a server outside their home region (cross-region match),
  their rating update is dampened (CROSS_REGION_WEIGHT). The home-region player's
  update is unaffected. Rationale: high ping disadvantages the visitor; the result
  is informative but less so than a fair-ping match.

Outcomes:
  - Higher player_frags wins → openskill.rate([winner, loser], ranks=[0, 1])
  - Equal frags → ranks=[0, 0] (drawn)

Defaults: full rebuild each run. Use --incremental to only rate new matches.

Usage:
  python rate.py                 # full rebuild for 1on1
  python rate.py --mode 1on1
  python rate.py --incremental
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras
from openskill.models import PlackettLuce

import db as dbmod

DEFAULT_DB = Path(__file__).parent / "data" / "qw-stats.db"

# OpenSkill model — same display scale as the prior TrueSkill setup (μ=1500, σ=500)
# so downstream consumers (tiers, conservative-rating) don't need to be re-scaled.
# β = skill noise per match (≈σ/2 by convention). τ = additive σ growth per match;
# keeps σ from over-narrowing in the high-game-count regime. Tuned tight (0.5)
# because per-player σ updates already do most of the work.
MODEL = PlackettLuce(mu=1500.0, sigma=500.0, beta=250.0, tau=0.5, kappa=0.0001)

# Cross-region match: rating update for the away player is multiplied by this.
# 0.6 = "this match is 60% as informative for the away player as a fair-ping match".
# Home player unaffected. Chosen by reasoning, not data — revisit after a quarter
# of cross-region match data accumulates.
CROSS_REGION_WEIGHT = 0.6

# Performance-weighting tunables (introduced 2026-05-26 alongside OpenSkill).
# A composite perf score blends two signals: frag-diff vs rating-expected gap, and
# DDR (damage given / taken ratio). The result amplifies (>1) or dampens (<1)
# the rating update beyond what W/L alone would say.
#
# Example: Cronus (1500) loses 21-15 to chr1s (2500) with DDR 1.1.
#   - Expected frag-diff for Cronus: -20 (capped). Actual: -6 → overperformed by +14.
#   - DDR 1.1 → mild positive (he was trading well).
#   - perf_delta_cronus ≈ +0.34 → loser-weight = 1.0 - 0.34 = 0.66 → 34% smaller loss.
#   - perf_delta_chr1s ≈ -0.34 → winner-weight = 1.0 - 0.34 = 0.66 → 34% smaller gain.
#
# Tunables in [0, 1]; larger = more aggressive perf-weighting. Calibrated low
# initially so the W/L signal stays dominant — perf is a refinement, not a
# replacement.
PERF_FRAG_WEIGHT = 0.6     # weight of the frag-diff-vs-expected signal
PERF_DDR_WEIGHT  = 0.4     # weight of the DDR signal
PERF_MAX_DELTA   = 0.4     # cap |perf_delta| — keeps the per-match update bounded
EXPECTED_FRAG_PER_RATING = 0.020  # 200pt rating gap → 4 frag expected diff (calibrate later)
EXPECTED_FRAG_CAP = 20.0   # rating gaps > 1000pt saturate the expected diff
FRAG_DIFF_NORMALIZER = 25.0  # 25-frag overperformance ≈ full signal saturation


def _expected_frag_diff(mu_a: float, mu_b: float) -> float:
    """Predicted (player_a frags - player_b frags). Positive = a should win.
    Naive linear from rating gap, saturated at ±EXPECTED_FRAG_CAP."""
    raw = EXPECTED_FRAG_PER_RATING * (mu_a - mu_b)
    return max(-EXPECTED_FRAG_CAP, min(EXPECTED_FRAG_CAP, raw))


def _perf_delta(mu_a: float, mu_b: float, frags_a: int, frags_b: int,
                dmg_given_a, dmg_taken_a) -> float:
    """Return the performance delta P_a ∈ [-PERF_MAX_DELTA, +PERF_MAX_DELTA] for
    player A. Positive = A overperformed their rating-expected outcome.

    Combine frag-diff signal (how much did the actual gap beat the predicted gap?)
    with DDR signal (damage given / taken — was A generating pressure?).
    Returns 0.0 when damage stats are missing (older matches without KTX data)."""
    expected = _expected_frag_diff(mu_a, mu_b)
    actual = (frags_a or 0) - (frags_b or 0)
    frag_signal = max(-1.0, min(1.0, (actual - expected) / FRAG_DIFF_NORMALIZER))

    if dmg_given_a is None or dmg_taken_a is None or dmg_taken_a <= 0:
        ddr_signal = 0.0
    else:
        ddr = dmg_given_a / max(1.0, dmg_taken_a)
        ddr_signal = max(-1.0, min(1.0, ddr - 1.0))

    delta = PERF_FRAG_WEIGHT * frag_signal + PERF_DDR_WEIGHT * ddr_signal
    return max(-PERF_MAX_DELTA, min(PERF_MAX_DELTA, delta))


def _perf_weight(perf_delta: float, won: bool) -> float:
    """Convert a player's perf delta to a rating-update multiplier.

    Winner: overperformed (delta > 0) → bigger gain. Underperformed → smaller gain.
    Loser:  overperformed (delta > 0) → smaller loss. Underperformed → bigger loss.
    """
    if won:
        return 1.0 + perf_delta
    else:
        return 1.0 - perf_delta


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
            last_match_id, last_match_date, updated_at, unique_opponents)
           VALUES %s
           ON CONFLICT (canonical_id, mode, map) DO UPDATE SET
             mu=EXCLUDED.mu, sigma=EXCLUDED.sigma, conservative=EXCLUDED.conservative,
             matches_rated=EXCLUDED.matches_rated, wins=EXCLUDED.wins,
             losses=EXCLUDED.losses, draws=EXCLUDED.draws,
             last_match_id=EXCLUDED.last_match_id, last_match_date=EXCLUDED.last_match_date,
             updated_at=EXCLUDED.updated_at, unique_opponents=EXCLUDED.unique_opponents""",
        rows,
        page_size=2000,
    )


def load_existing_ratings(conn, mode, map_bucket=''):
    """Return (cache, stats) for incremental runs within a single (mode, map) bucket."""
    cache = {}
    stats = {}
    cur = conn.cursor()
    cur.execute(
        "SELECT canonical_id, mu, sigma, matches_rated, wins, losses, draws "
        "FROM ratings WHERE mode=%s AND map=%s",
        (mode, map_bucket),
    )
    for r in cur.fetchall():
        cid = r["canonical_id"]
        cache[cid] = MODEL.rating(mu=r["mu"], sigma=r["sigma"], name=cid)
        stats[cid] = {"matches": r["matches_rated"] or 0, "wins": r["wins"] or 0,
                      "losses": r["losses"] or 0, "draws": r["draws"] or 0}
    cur.close()
    return cache, stats


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


def fetch_matches(conn, mode, since_date=None, map_filter=None):
    """Yield per-match tuples with all data needed for OpenSkill + perf-weighting.

    Columns: match_id, match_date, cid_a, frags_a, dmg_given_a, dmg_taken_a,
             cid_b, frags_b, dmg_given_b, dmg_taken_b, server_region.

    server_region lookup: matches.server_hostname → strip port → servers.hostname.
    None when geo unknown. Damage columns may be NULL on older pre-KTX matches —
    perf weighting falls back to W/L-only in that case.
    """
    where_extra = ""
    params = {"mode": mode}
    if since_date:
        where_extra += " AND m.match_date > %(since)s"
        params["since"] = since_date
    if map_filter:
        where_extra += " AND m.match_map = %(map)s"
        params["map"] = map_filter
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT m.match_id, m.match_date,
               p1.canonical_id AS cid_a, p1.player_frags AS f_a,
               p1.player_damage_given AS dg_a, p1.player_damage_taken AS dt_a,
               p2.canonical_id AS cid_b, p2.player_frags AS f_b,
               p2.player_damage_given AS dg_b, p2.player_damage_taken AS dt_b,
               s.region AS server_region
        FROM matches m
        JOIN players p1 ON p1.match_id = m.match_id
        JOIN players p2 ON p2.match_id = m.match_id
        LEFT JOIN servers s ON s.hostname = split_part(m.server_hostname, ':', 1)
        WHERE m.match_mode = %(mode)s
          AND p1.canonical_id IS NOT NULL
          AND p2.canonical_id IS NOT NULL
          AND p1.canonical_id < p2.canonical_id
          {where_extra}
        ORDER BY m.match_date
        """,
        params,
    )
    for r in cur.fetchall():
        yield (r["match_id"], r["match_date"],
               r["cid_a"], r["f_a"], r["dg_a"], r["dt_a"],
               r["cid_b"], r["f_b"], r["dg_b"], r["dt_b"],
               r["server_region"])
    cur.close()


def _update_with_weights(model, r_winner, r_loser, weight_winner, weight_loser, drawn=False):
    """Rate a 1v1 match with per-player update weights.

    OpenSkill's `rate()` produces the full update assuming weight=1.0 for both.
    For weight<1.0 (cross-region away player), we blend: new = old + weight * (full - old).
    Implemented manually rather than using openskill's `weights=` because that param
    is for team-internal contribution weighting, which doesn't apply to 1v1.
    """
    if drawn:
        [[new_a], [new_b]] = model.rate([[r_winner], [r_loser]], ranks=[0, 0])
    else:
        [[new_a], [new_b]] = model.rate([[r_winner], [r_loser]], ranks=[0, 1])

    blended_winner = model.rating(
        mu=r_winner.mu + weight_winner * (new_a.mu - r_winner.mu),
        sigma=r_winner.sigma + weight_winner * (new_a.sigma - r_winner.sigma),
        name=r_winner.name,
    )
    blended_loser = model.rating(
        mu=r_loser.mu + weight_loser * (new_b.mu - r_loser.mu),
        sigma=r_loser.sigma + weight_loser * (new_b.sigma - r_loser.sigma),
        name=r_loser.name,
    )
    return blended_winner, blended_loser


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


def rate_bucket(db, mode, map_bucket, now, full_rebuild=True, per_map_min=5,
                player_regions=None):
    """Run OpenSkill over all matches in (mode, map_bucket).
       map_bucket='' = overall (all maps in the mode).
       For per-map buckets only emit ratings for players with >= per_map_min matches.

    Returns (n_rated, n_players_written).
    """
    if player_regions is None:
        player_regions = {}
    cur = db.cursor()
    if full_rebuild:
        cur.execute("DELETE FROM ratings WHERE mode=%s AND map=%s", (mode, map_bucket))
        cur.execute("DELETE FROM rating_history WHERE mode=%s AND map=%s", (mode, map_bucket))
        db.commit()
        cache, stats = {}, {}
    else:
        cache, stats = load_existing_ratings(db, mode, map_bucket)

    map_filter = map_bucket if map_bucket else None
    matches = list(fetch_matches(db, mode, map_filter=map_filter))
    if not matches:
        return 0, 0

    history_rows = []
    n_skipped = 0
    for (match_id, match_date,
         cid_a, f_a, dg_a, dt_a,
         cid_b, f_b, dg_b, dt_b,
         server_region) in matches:
        if cid_a == cid_b or f_a is None or f_b is None:
            n_skipped += 1
            continue

        ra = cache.setdefault(cid_a, MODEL.rating(name=cid_a))
        rb = cache.setdefault(cid_b, MODEL.rating(name=cid_b))
        sa = stats.setdefault(cid_a, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        sb = stats.setdefault(cid_b, {"matches": 0, "wins": 0, "losses": 0, "draws": 0})
        mu_a_b, sig_a_b = ra.mu, ra.sigma
        mu_b_b, sig_b_b = rb.mu, rb.sigma

        # Cross-region dampening (orthogonal to performance)
        wa_cr, wb_cr = _weights_for_match(
            player_regions.get(cid_a), player_regions.get(cid_b), server_region
        )

        # Perf delta per player — measured against the rating-implied expectation.
        # Drawn matches skip perf (won=neither), keeping the W/L-only update.
        if f_a > f_b:
            won_a, won_b = True, False
        elif f_b > f_a:
            won_a, won_b = False, True
        else:
            won_a, won_b = None, None  # draw

        if won_a is None:
            wa_perf = wb_perf = 1.0
        else:
            pa = _perf_delta(ra.mu, rb.mu, f_a, f_b, dg_a, dt_a)
            pb = _perf_delta(rb.mu, ra.mu, f_b, f_a, dg_b, dt_b)
            wa_perf = _perf_weight(pa, won_a)
            wb_perf = _perf_weight(pb, won_b)

        # Combine cross-region × perf, clamped to a sane range.
        wa = max(0.2, min(1.6, wa_cr * wa_perf))
        wb = max(0.2, min(1.6, wb_cr * wb_perf))

        if f_a > f_b:
            ra_new, rb_new = _update_with_weights(MODEL, ra, rb, wa, wb, drawn=False)
            out_a, out_b = "win", "loss"
            sa["wins"] += 1; sb["losses"] += 1
        elif f_b > f_a:
            rb_new, ra_new = _update_with_weights(MODEL, rb, ra, wb, wa, drawn=False)
            out_a, out_b = "loss", "win"
            sb["wins"] += 1; sa["losses"] += 1
        else:
            ra_new, rb_new = _update_with_weights(MODEL, ra, rb, wa, wb, drawn=True)
            out_a = out_b = "draw"
            sa["draws"] += 1; sb["draws"] += 1

        cache[cid_a] = ra_new; cache[cid_b] = rb_new
        sa["matches"] += 1; sb["matches"] += 1

        history_rows.append((cid_a, mode, map_bucket, match_id, match_date, cid_b, out_a,
                             mu_a_b, ra_new.mu, sig_a_b, ra_new.sigma, ra_new.mu - mu_a_b))
        history_rows.append((cid_b, mode, map_bucket, match_id, match_date, cid_a, out_b,
                             mu_b_b, rb_new.mu, sig_b_b, rb_new.sigma, rb_new.mu - mu_b_b))

        if len(history_rows) >= 5000:
            _bulk_insert_history(cur, history_rows)
            history_rows = []
            db.commit()

    if history_rows:
        _bulk_insert_history(cur, history_rows)

    # Unique-opponent count is still useful as a UI "Provisional" hint — even though
    # OpenSkill's σ updates handle diversity natively in the math, we surface the
    # count so users see when a rating is built from a thin opponent pool.
    cur.execute("""
        SELECT canonical_id, COUNT(DISTINCT opponent_cid) AS n
        FROM rating_history WHERE mode = %s AND map = %s AND opponent_cid IS NOT NULL
        GROUP BY canonical_id
    """, (mode, map_bucket))
    uniq_counts = {r["canonical_id"]: r["n"] for r in cur.fetchall()}

    rating_rows = []
    for cid, r in cache.items():
        s = stats.get(cid, {})
        if map_bucket and s["matches"] < per_map_min:
            continue
        rating_rows.append((cid, mode, map_bucket, r.mu, r.sigma, r.mu - 3 * r.sigma,
                            s["matches"], s["wins"], s["losses"], s["draws"],
                            None, None, now, uniq_counts.get(cid, 0)))
    if rating_rows:
        _bulk_insert_ratings(cur, rating_rows)
    db.commit()
    cur.close()
    return len(matches), len(rating_rows)


def run(db_path: Path, mode: str = "1on1", incremental: bool = False, per_map_min: int = 5):
    db = dbmod.connect()
    now = datetime.now(timezone.utc).isoformat()
    full_rebuild = not incremental
    player_regions = load_player_regions(db)
    print(f"Loaded regions for {len(player_regions):,} players.")

    print(f"Rating {mode} overall (OpenSkill PlackettLuce, cross-region weight={CROSS_REGION_WEIGHT})…")
    start = datetime.now()
    n_matches, n_players = rate_bucket(db, mode, '', now, full_rebuild=full_rebuild,
                                        per_map_min=0, player_regions=player_regions)
    elapsed = (datetime.now() - start).total_seconds()
    print(f"  {n_matches:,} matches → {n_players:,} players rated in {elapsed:.1f}s")

    maps = list_maps_for_mode(db, mode, min_matches=50)
    print(f"\nRating {mode} per-map across {len(maps)} maps "
          f"(min {per_map_min} matches per player to be stored)…")
    start = datetime.now()
    total_matches = 0
    total_players = 0
    for m in maps:
        n_matches, n_players = rate_bucket(db, mode, m, now, full_rebuild=full_rebuild,
                                            per_map_min=per_map_min,
                                            player_regions=player_regions)
        total_matches += n_matches
        total_players += n_players
    elapsed = (datetime.now() - start).total_seconds()
    print(f"  {total_matches:,} match-events → {total_players:,} per-map ratings written in {elapsed:.1f}s")

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

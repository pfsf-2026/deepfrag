#!/usr/bin/env python3
"""Export per-mode rankings (leaderboards) as a single static JSON.

Output: nuxt/public/rankings.json
Structure: { generated_at, modes: { '1on1': [...], '2on2': [...], '4on4': [...] } }

Each player entry contains canonical_id, display, mu, sigma, conservative, matches, w/l/d.
Sorted by conservative rating (mu - 3σ) descending, capped at 500 per mode.
"""

import argparse
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tiers import tier_for

DEFAULT_DB = Path(__file__).parent / "data" / "qw-stats.db"
DEFAULT_OUT = Path(__file__).parent / "nuxt" / "public" / "rankings.json"

# Glicko-style inactivity decay. σ² grows linearly with days inactive past the
# grace period, so an inactive player's "conservative" leaderboard rating slides
# down even though their μ is frozen. Calibrated so 90d off ≈ -20pts, 1yr ≈ -330pts.
DECAY_GRACE_DAYS = 30
DECAY_PER_DAY = 0.5

# Opponent-diversity penalty thresholds — below these, σ gets multiplied by a
# diversity factor that pulls the conservative rating down (and flags as Provisional).
DIVERSITY_THRESHOLD_OVERALL = 10
DIVERSITY_THRESHOLD_PER_MAP = 3


def decayed_sigma(stored_sigma, last_match_iso, now):
    """Inflate σ based on days since last_match, after a 30d grace period."""
    if not last_match_iso:
        return stored_sigma
    try:
        last = datetime.fromisoformat(last_match_iso.replace("Z", "+00:00"))
    except ValueError:
        return stored_sigma
    days = max(0, (now - last).days - DECAY_GRACE_DAYS)
    if days <= 0:
        return stored_sigma
    return math.sqrt(stored_sigma * stored_sigma + (DECAY_PER_DAY * days) ** 2)


def diversity_factor(unique_opponents, threshold=DIVERSITY_THRESHOLD_OVERALL):
    """Return σ multiplier that grows when unique opponents is below threshold.

    Examples (threshold=10):
      25 opps → factor 1.0 (no penalty, capped)
      10 opps → factor 1.0
       5 opps → factor sqrt(10/5)  ≈ 1.41   (σ × 1.41)
       2 opps → factor sqrt(10/2)  ≈ 2.24   (σ × 2.24)
       1 opp  → factor sqrt(10/1)  ≈ 3.16

    Stops the '50-2 vs 4 friends' rating inflation by widening uncertainty
    until the player has faced a representative pool.
    """
    if unique_opponents is None or unique_opponents <= 0:
        return float(threshold) ** 0.5
    if unique_opponents >= threshold:
        return 1.0
    return math.sqrt(threshold / unique_opponents)


def effective_sigma(stored_sigma, last_match_iso, now, unique_opponents, threshold=DIVERSITY_THRESHOLD_OVERALL):
    """Combine inactivity decay AND diversity penalty into one effective σ.

    The two multiplicatively compound, but in practice rarely overlap — inactive
    players also tend to have low diversity. Either alone is enough to widen σ.
    """
    decayed = decayed_sigma(stored_sigma, last_match_iso, now)
    return decayed * diversity_factor(unique_opponents, threshold)


def fetch_rankings(db, mode, now, limit=500, min_matches=10):
    rows = db.execute(
        """
        SELECT r.canonical_id,
               pc.display_name AS display,
               r.mu, r.sigma, r.conservative,
               COALESCE(r.unique_opponents, 0) AS unique_opponents,
               r.matches_rated, r.wins, r.losses, r.draws,
               (SELECT MAX(m.match_date)
                FROM matches m JOIN players p ON p.match_id = m.match_id
                WHERE p.canonical_id = r.canonical_id) AS last_match,
               (SELECT COUNT(*) FROM matches m
                JOIN players p ON p.match_id = m.match_id
                WHERE p.canonical_id = r.canonical_id
                  AND m.match_date >= :recent_cutoff
                  AND m.match_mode = :mode) AS recent_matches
        FROM ratings r
        LEFT JOIN players_canonical pc ON pc.canonical_id = r.canonical_id
        WHERE r.mode = :mode AND r.map = '' AND r.matches_rated >= :min_matches
        """,
        {
            "mode": mode,
            "min_matches": min_matches,
            "recent_cutoff": (now - timedelta(days=90)).isoformat(),
        },
    ).fetchall()

    out = []
    for r in rows:
        sigma_eff = effective_sigma(r["sigma"], r["last_match"], now, r["unique_opponents"])
        conservative_eff = r["mu"] - 3 * sigma_eff
        out.append({
            "canonical_id": r["canonical_id"],
            "display": r["display"] or r["canonical_id"],
            "mu": round(r["mu"], 1),
            "sigma": round(r["sigma"], 1),
            "sigma_effective": round(sigma_eff, 1),
            "conservative": round(conservative_eff, 1),
            "conservative_raw": round(r["conservative"], 1),
            "matches": r["matches_rated"],
            "unique_opponents": r["unique_opponents"],
            "provisional": (r["unique_opponents"] or 0) < DIVERSITY_THRESHOLD_OVERALL,
            "wins": r["wins"],
            "losses": r["losses"],
            "draws": r["draws"],
            "win_rate": round(r["wins"] / r["matches_rated"], 3) if r["matches_rated"] else None,
            "last_match": r["last_match"],
            "recent_matches_90d": r["recent_matches"] or 0,
            "active_90d": (r["recent_matches"] or 0) > 0,
            "tier": tier_for(conservative_eff),
        })

    # Sort by the (decayed) conservative — inactive players drift down naturally.
    out.sort(key=lambda x: -x["conservative"])
    for i, p in enumerate(out[:limit]):
        p["rank"] = i + 1
    return out[:limit]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--limit", type=int, default=2000,
                   help="Cap entries per mode. With ~4k rated players, single request stays <1MB gzipped.")
    args = p.parse_args()

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)
    out = {
        "generated_at": now.isoformat(),
        "modes": {},
    }
    for mode in ["1on1", "2on2", "4on4"]:
        rows = fetch_rankings(db, mode, now, limit=args.limit)
        out["modes"][mode] = rows
        active = sum(1 for r in rows if r["active_90d"])
        print(f"  {mode}: {len(rows)} players ({active} active in last 90d)")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")))
    print(f"Wrote {args.out} ({Path(args.out).stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

"""Tier classifier — maps conservative OpenSkill rating → DeepFrag division.

Tiers (high → low):
  Div 0   top 15%   — elite, the genuine top tier across all regions
  Div 1   next 30%  — strong, multi-region competitive
  Div 2   next 35%  — solid, regular competitors
  Div 3   bottom 20% — climbing / casual / new players

Boundaries are **percentile-based**, recomputed on demand from the current rated
population (overall 1on1, matches_rated ≥ 10). Cutoffs are absolute rating values
once computed, so a single player's rating maps to a tier deterministically —
the percentile math only runs when computing cutoffs.

EU naturally dominates Div 0 because EU has more deeply-rated players; that's
intended. The system measures rating, not regional fairness — see the 1on1
methodology bible for the cross-region weighting that lives in rate.py.
"""

from __future__ import annotations

# Tier definitions: (slug, display name, percentile_floor, color)
# percentile_floor is the LOWER bound of this tier within the population —
# i.e. Div 0 starts at 85th percentile (top 15%).
TIER_SPECS = [
    ("div0", "Div 0", 0.85, "#fbbf24"),  # gold
    ("div1", "Div 1", 0.55, "#a855f7"),  # violet
    ("div2", "Div 2", 0.20, "#14e6c0"),  # teal
    ("div3", "Div 3", 0.00, "#64748b"),  # gray
]


def compute_cutoffs(ratings):
    """Given an iterable of conservative ratings (floats), return
    {slug: min_rating_for_this_tier}. Pass at least the full rated-overall
    1on1 population for stable thresholds. Returns {} when n < 10.
    """
    vals = sorted([r for r in ratings if r is not None])
    n = len(vals)
    if n < 10:
        return {}
    cutoffs = {}
    for slug, _name, floor_pct, _color in TIER_SPECS:
        if floor_pct <= 0:
            cutoffs[slug] = float("-inf")
        else:
            idx = int(floor_pct * n)
            cutoffs[slug] = vals[idx]
    return cutoffs


def tier_for(conservative, cutoffs=None):
    """Return {slug, name, color, min} for a conservative rating given the
    population-derived cutoffs. Returns None when conservative is None or
    cutoffs is empty/None."""
    if conservative is None or not cutoffs:
        return None
    for slug, name, _floor_pct, color in TIER_SPECS:
        if conservative >= cutoffs.get(slug, float("-inf")):
            return {"slug": slug, "name": name, "color": color,
                    "min": cutoffs.get(slug)}
    return None


def tier_distribution(ratings):
    """Diagnostic: {slug: count} per tier + the cutoffs derived. Sanity-check
    that Div 0 actually ends up close to 15% of the population."""
    cutoffs = compute_cutoffs(ratings)
    counts = {slug: 0 for slug, *_ in TIER_SPECS}
    for r in ratings:
        t = tier_for(r, cutoffs)
        if t:
            counts[t["slug"]] += 1
    return counts, cutoffs

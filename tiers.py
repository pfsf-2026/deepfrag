"""Tier classifier — maps conservative TrueSkill rating → DeepFrag tier.

Tiers are ordered low → high. Breakpoints calibrated against the 1on1 rating
distribution (942 rated players, 2026-05): top 0.1% = GOAT, ~50% Marauder or
above, bottom ~15% Pubstar.

Hex colors are used by both the Nuxt UI and any other downstream renderer; they
intentionally span the spectrum (gray → gold) so a badge alone tells the story.
"""

TIERS = [
    # (min_rating_inclusive, slug, display_name, color)
    (2300, "goat",       "GOAT",       "#fbbf24"),  # gold
    (2100, "mythical",   "Mythical",   "#ec4899"),  # pink
    (1900, "legend",     "Legend",     "#a855f7"),  # violet
    (1700, "champion",   "Champion",   "#ef4444"),  # red
    (1500, "master",     "Master",     "#f97316"),  # orange
    (1300, "highlander", "Highlander", "#14e6c0"),  # teal (accent)
    (1100, "marauder",   "Marauder",   "#22c55e"),  # green
    (900,  "gladiator",  "Gladiator",  "#06b6d4"),  # cyan
    (700,  "fragger",    "Fragger",    "#3b82f6"),  # blue
    (-99999, "pubstar",  "Pubstar",    "#64748b"),  # gray
]


def tier_for(conservative):
    """Return {slug, name, color, min} for a conservative rating, or None if rating is None."""
    if conservative is None:
        return None
    for floor, slug, name, color in TIERS:
        if conservative >= floor:
            return {"slug": slug, "name": name, "color": color, "min": floor}
    return None

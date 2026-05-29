# DeepFrag Methodology Bibles

Living design documents for the rating and stats systems. Each "bible" captures both the **shipped state** and the **open design questions** for one game mode. Update in the same commit as any change to rating constants, formulas, or thresholds in code.

| Mode | Status | Doc |
|---|---|---|
| 1on1 | ✅ Shipped, in production | [1on1_methodology.md](./1on1_methodology.md) |
| 2on2 | 🔜 Designed, not yet built | [2on2_methodology.md](./2on2_methodology.md) |
| 4on4 | 🔜 Designed, not yet built | [4on4_methodology.md](./4on4_methodology.md) |

## How these documents relate

- **1on1** is the foundation — the OpenSkill engine, decay, tier ladder, and stats leaderboards all originated here (TrueSkill + diversity-penalty was deprecated 2026-05-26). Read it first.
- **2on2** explains the team-rating problem (carry, partner quality) and proposes the three-layer architecture we'll inherit for 4on4.
- **4on4** focuses on what's UNIQUE to 4on4 — role differentiation, the stacked-vs-naked damage diff problem, and the Corsi-derived performance metrics. The Corsi narrative lives in §2 of the 4on4 doc and informs the DDR and Net Damage stats already shipped for 1on1.

## When to update

- A constant changes in [rate.py](../rate.py), [export_rankings.py](../export_rankings.py), [tiers.py](../tiers.py), or [stats_pg.py](../stats_pg.py) → update the corresponding bible's "Constants" section in the same commit.
- A new stat ships → add to the bible's stats table.
- A design decision is reversed → strike-through the old approach (don't delete) and add the new direction with a "decided YYYY-MM-DD" note.

## Out of scope

- Code documentation — these aren't API docs. Reading the bible should give you the WHY; reading the code gives you the HOW.
- Marketing/community-facing copy — these are internal/dev-facing. The public-facing methodology explanation on deepfrag.pages.dev should be a separate, much shorter document.

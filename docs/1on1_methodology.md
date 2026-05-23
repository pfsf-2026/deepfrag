# 1on1 Rating Methodology — DeepFrag

> Status: **shipped, in production.** This document captures the current state of the 1on1 rating system as of 2026-05-22. Treat it as a living bible — any change to constants, formulas, or thresholds in code should be reflected here in the same commit.

---

## 1. Core engine: TrueSkill

We use Microsoft's TrueSkill (via the `trueskill` Python package), a Bayesian skill-rating model designed for head-to-head and team games. Each player has a Gaussian belief over their true skill — a mean `μ` and standard deviation `σ`. The "conservative" rating shown publicly is `μ − 3σ`, i.e. the lower bound of a 99.7% confidence interval.

### Constants

| Param | Value | Why |
|---|---|---|
| `mu` (starting) | 1500.0 | Arbitrary midpoint; lets new players climb in either direction. |
| `sigma` (starting) | 500.0 | Very wide — new players take 5-10 matches to stabilize. |
| `beta` | 250.0 | The "skill noise" per match. ~σ/2 is conventional. |
| `tau` | 5.0 | Dynamics — how much μ can drift between matches. Originally 25 (too volatile), dialed to 5 to settle. |
| `draw_probability` | 0.01 | Tiny but nonzero so rare equal-frag duels don't break the math. |

These live in [rate.py:36](../rate.py#L36).

### What gets rated

- Every 1on1 match in the `matches` table where `match_mode = '1on1'` and `match_id` resolves to exactly two distinct `canonical_id`s in `players`.
- Players who join/leave mid-match (multiple `players` rows per match per player) are deduplicated — we use their *aggregate* frag totals to determine winner.
- Draws are detected (equal frags) and use TrueSkill's draw machinery.

### Per-bucket ratings

We compute TWO sets of ratings per mode:

1. **Overall** (`map = ''`) — every 1on1 match contributes regardless of map. This is what powers the main rankings page.
2. **Per-map** (`map = 'dm2'`, `map = 'aerowalk'`, etc.) — separate rating per `(player, map)` pair. Only stored when the player has played ≥ `per_map_min` matches on that map (default **5**).

Per-map ratings let the profile page show "you're rated 1800 overall but 2100 on AEROWALK." See [rate.py:204](../rate.py#L204).

---

## 2. Opponent-diversity penalty (Phase 5)

Pure TrueSkill is gameable: rack up 50 wins against the same low-rated friend and your μ climbs without σ shrinking enough to penalize the lack of breadth. We patched this with a Bayesian-style diversity multiplier on σ at *display time* (not stored — applied in [api.py](../api.py) and [export_rankings.py:49](../export_rankings.py#L49)).

### Formula

```
factor = sqrt(threshold / unique_opponents)   when unique_opponents < threshold
factor = 1.0                                  otherwise
effective_σ = stored_σ × factor
```

| Threshold | Value | Used for |
|---|---|---|
| `DIVERSITY_THRESHOLD_OVERALL` | 10 | Main rankings, profile overall rating. |
| `DIVERSITY_THRESHOLD_PER_MAP` | 3 | Per-map rankings (lower bar — many maps are obscure). |

### Effect on ranking

| Unique opps | Factor | Effect on conservative |
|---|---|---|
| ≥ 10 | 1.0× | none — settled |
| 5 | 1.41× | σ wider → cons lower by ~3σ × 0.41 = ~620pts |
| 2 | 2.24× | σ wider → ~1860pts off cons |
| 1 | 3.16× | hard cap — barely ranked |

Players with `unique_opponents < threshold` are flagged `provisional: true` in API responses; the UI shows them with a "Provisional" badge and de-emphasizes their cons rating.

### Real-world example

`grawer` (2026-05): 33 matches, 1291 raw cons → diversity adjusted to 703. Only one unique opponent. The system correctly treats this as "we don't actually know how good grawer is."

---

## 3. Inactivity decay (Glicko-style σ inflation)

If a player hasn't played in 30+ days, their σ inflates as if they were unrated — old skill is less informative the longer they've been gone. From [export_rankings.py:35](../export_rankings.py#L35):

```
days_inactive = max(0, (now - last_match).days - GRACE)
inflated_σ = sqrt(stored_σ² + (PER_DAY × days_inactive)²)
```

| Constant | Value |
|---|---|
| `DECAY_GRACE_DAYS` | 30 |
| `DECAY_PER_DAY` | 0.5 σ-units/day |

Calibrated so:
- 90 days off → cons drops ~20pts
- 1 year off → cons drops ~330pts

The μ doesn't change — a player who comes back can climb back up quickly with a few wins. Decay only widens the uncertainty band.

Diversity penalty and decay **multiply** when both apply (rare but possible — inactive AND played few opponents).

---

## 4. Tier ladder

The conservative rating maps to one of 10 tiers ([tiers.py](../tiers.py)). Breakpoints calibrated against the actual 1on1 distribution (~942 rated players, 2026-05).

| Tier | Cons floor | Color | Approx % of pop |
|---|---|---|---|
| GOAT | 2300 | gold | top 0.1% |
| Mythical | 2100 | pink | top 1% |
| Legend | 1900 | violet | top 5% |
| Champion | 1700 | red | top 15% |
| Master | 1500 | orange | ~25% |
| Highlander | 1300 | teal | ~40% |
| Marauder | 1100 | green | ~55% |
| Gladiator | 900 | cyan | ~70% |
| Fragger | 700 | blue | ~85% |
| Pubstar | < 700 | gray | bottom 15% |

**Open question:** the tier names mix fantasy/RPG (Mythical, GOAT) with combat lore (Marauder, Highlander). User considered a Quake-native "Div 0 / Div 1 / ... / Div 4" scheme but landed on keeping the colorful ladder. Revisit if community feedback prefers convention.

---

## 5. Identity / canonicalization

Ratings are keyed on `canonical_id`, not raw player name. The pipeline:

1. **`canonicalize.py`** applies [`aliases.yaml`](../aliases.yaml) — explicit mappings like `chris ← chr1s, eatmyass` and `war ← whodat, george, notgeorge`.
2. **Fuzzy candidates** (RapidFuzz score ≥ 0.78) go to `.review_queue.yaml` for human review. Edit `decision: accept|reject` then run `python name_canon.py apply-reviews && python canonicalize.py`.
3. **Name spam** (color codes, brackets, clan tags) gets normalized — `(1)Carmolio` → considered for `carmolio`.

Without canonicalization, every clan tag change creates a new "player" and ratings fragment. Aliases are append-only — once two identities are merged, all their matches share one rating arc.

---

## 6. Regional weighting (Phase 2–3, current)

Each player is assigned a primary region (NA / EU / SA / OC / AS-AF) based on the servers they play on most ([assign_player_regions.py](../assign_player_regions.py)). LAN events (QHLAN 2018/2020/2022/2024/2026/2028) are excluded from this calculation — playing AT a LAN doesn't reveal where you LIVE.

Region is currently a **filter only**, not a rating input. The rankings page lets users filter by region; ratings themselves are global.

**Phase 4 (pending)** will introduce mode-specific cross-region weighting. The insight: a NA player who has played 80% NA games and 20% EU games against weaker EU competition will have an inflated rating relative to a NA-only player. We'd discount cross-region wins below a threshold of regional cross-pollination. Per-mode because 1on1 has more cross-region play than 2on2/4on4 (which are clan-bound).

---

## 7. Stats leaderboards (mechanical-skill, separate from rating)

In addition to TrueSkill (who you BEAT), we expose mechanical leaderboards (how you PLAY) at `/stats`. From [stats_pg.py](../stats_pg.py):

| Stat | Direction | Notes |
|---|---|---|
| LG accuracy | desc | `lg_hits / lg_attacks` averaged per match |
| RL accuracy | desc | `rl_virtual / rl_attacks` (virtual = hits if no armor) |
| ±frag avg | desc | per-match frags − deaths |
| **DDR (Damage diff ratio)** | desc | Σ given / Σ taken — Corsi-equivalent rate stat |
| **Net damage / match** | desc | avg(given − taken) — raw margin |
| Total damage given | desc | per-match average |
| Total damage taken | asc | lower is better |
| RA / match | desc | red armors taken |
| Mega / match | desc | mega healths taken (100h) |
| YA / match | desc | yellow armors taken |
| Avg frags / match | desc | scoreboard frags |
| Avg speed | desc | from MVD `speed_avg` |
| Spawnfrags taken / match | asc | opponent's `player_spawnfrags` — how often you die on spawn |

Default filter: `min_matches >= 100`. Region and map filters available.

**The DDR/Net-damage story** is the QW-equivalent of hockey's Corsi: damage is the "shot attempts" underlying frags. A high DDR with low TrueSkill suggests "actually better, getting unlucky"; the inverse suggests "fragile, due to regress." See [4on4_methodology.md](./4on4_methodology.md#corsi-narrative) for the full theoretical framing — it informs team-mode design more than 1on1.

---

## 8. Known issues / open improvements

### Decided, pending
- **Phase 4: cross-region weighting** (per-mode thresholds) — see Section 6.
- **Mix vs divisional split** — EU has formal divs (Div 1/2/3/4 league play); NA/AU/BR are pickup-only. A rating earned in structured div play arguably carries different weight than mix-game wins. Optional per-region split.

### Open questions
- **Weng-Lin vs TrueSkill** — Weng-Lin (used by openskill.js) is a simpler, faster Bayesian rating system with better-documented math. TrueSkill works but is patent-encumbered historically and the Python lib is unmaintained. Worth a side-by-side eval before any major rewrite.
- **Frag-differential weighting** — currently a 21-19 win and a 21-3 win count identically for TrueSkill. Margin-of-victory is information we're discarding. Could either feed into `beta` per match or post-hoc adjust μ delta.
- **Score decay** — should a 5-year-old win count the same as last week's? TrueSkill σ-decay handles this for INACTIVE players, but an active player's old wins still anchor their μ. Time-weighted re-rating would let skill genuinely improve faster.
- **Tier renaming** — see Section 4.

### Limitations
- Only stores ratings for `per_map_min ≥ 5` matches per map — obscure maps with 1-2 games show no per-map rating.
- TrueSkill's tau=5 is a global compromise. Players whose skill is genuinely volatile (returning veterans, rapid improvers) get penalized.
- No "team you played FOR/AGAINST" awareness — irrelevant for 1on1 but relevant downstream when we use 1on1 as a prior for team modes.

---

## 9. Pipeline + storage

```
sync.py (hub.quakeworld.nu)   →  matches, players tables (PG)
canonicalize.py (aliases)     →  canonical_id assignments
rate.py                       →  ratings, rating_history (PG)
assign_player_regions.py      →  players_canonical.region
api.py                        →  /api/rankings, /api/players/{id}, /api/stats/*
```

Cloud SQL Postgres 16 (`deepfrag-db`, db-f1-micro, us-central1) is the source of truth. The Nuxt frontend hits the FastAPI service on Cloud Run, which queries PG live (no JSON export step anymore).

`rate.py --incremental` only rates matches newer than the latest in `rating_history` — full rebuild only when alias merges happen.

---

## 10. References

- TrueSkill paper: Herbrich, Minka, Graepel (2007) — MS Research
- Glicko-2: Glickman (2012) — basis for σ inflation
- Bayesian opponent diversity: our own — no canonical reference
- Corsi statistic: [Wikipedia](https://en.wikipedia.org/wiki/Corsi_(statistic)) — informs DDR and team-mode design

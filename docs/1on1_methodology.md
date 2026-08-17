# 1on1 Rating Methodology — DeepFrag

> Status: **shipped, in production.** Last major change: 2026-08-17 (engine v3: continuous-margin outcomes + shrunk per-map deviations — see §1b). Prior major change: 2026-05-26 (TrueSkill → OpenSkill migration + Div 0-3 tiers). Treat as a living bible — any change to constants, formulas, or thresholds in code should be reflected here in the same commit.

---

## 1. Core engine: OpenSkill (Weng-Lin, Plackett-Luce)

We use **OpenSkill** (Weng-Lin model via the `openskill.py` package), a Bayesian skill-rating system in the TrueSkill family but with simpler closed-form math and active maintenance. Each player has a Gaussian belief over their true skill — a mean `μ` and standard deviation `σ`. The "conservative" rating shown publicly is `μ − 3σ`, i.e. the lower bound of a 99.7% confidence interval.

**Why OpenSkill over TrueSkill** (migration completed 2026-05-26):
- Per-player σ updates reflect the **information content** of each match, not a global τ knob. 50 matches vs the same opponent narrow σ less than 50 matches vs 50 different opponents — handled in the math, no diversity-penalty band-aid needed.
- MIT-licensed, no patent overhang, actively maintained.
- Native N-vs-N team support so 2on2 / 4on4 use the same engine when those land.
- ParadokS's independent QW research arrived at OpenSkill too — external validation.

### Constants

| Param | Value | Why |
|---|---|---|
| `mu` (starting) | 1500.0 | Arbitrary midpoint; lets new players climb in either direction. Same scale as the prior TrueSkill setup to avoid downstream re-scaling. |
| `sigma` (starting) | 500.0 | Very wide — new players take 5-10 matches to stabilize. |
| `beta` | 250.0 | Skill noise per match. ~σ/2 conventional. |
| `tau` | 0.5 | Additive σ growth per match. Kept tight; OpenSkill's per-match σ updates already do most of the work — τ guards against over-narrowing in high-game-count regimes. |
| `kappa` | 0.0001 | Minimum σ floor (numerical safety). |

These live in [rate.py:42](../rate.py#L42).

**Empirical verification of diversity behavior** (spot test, 2026-05-26):

| Scenario | Resulting cons (μ − 3σ) | Δ from start |
|---|---|---|
| 50 wins vs SAME opponent | 1598 | +98 |
| 50 wins vs 5 cycling opponents | 2081 | +581 |
| 50 wins vs 50 DIFFERENT opponents | 2324 | +824 |

OpenSkill produces a ~700pt gap between low- and high-diversity rating arcs *without any post-hoc penalty* — significantly more aggressive than the prior TrueSkill + sqrt-multiplier band-aid achieved.

### 1b. Engine v3 — continuous-margin outcomes (2026-08-17)

Motivated by the 2026-08-15 Cronus/Yeti 9-map bet post-mortem: the W/L-only
engine forecast the series at ~2% when the observed frag margins implied ~45%.
Root causes, each verified by walk-forward backtest on 79,928 duels (scored on
37,352 held-out matches from 2025-01-01 where both players had ≥20 prior games):

1. **Expected-margin curve was wrong.** The old perf-weighting predicted
   `0.020 × μ-gap` capped at ±20 frags. Empirical fit on 8,776 duel
   observations: `70 · tanh(gap / 2575)` — real margins reach −44 at extreme
   gaps, so the ±20 cap destroyed most of the signal exactly where mismatches
   live.
2. **A loss could never raise μ.** Perf weighting multiplied the update by a
   factor clamped to [0.2, 1.6] — magnitude only, never direction. A 13-15
   loss to a +950 opponent is *evidence the gap shrank*, but it still moved
   the loser down.
3. **σ over-contracted for veterans** (Cronus: 5,711 games, σ 41) so μ became
   nearly immovable, and idle players' σ never widened in-engine.

**The v3 update.** Each match gets a continuous outcome score
`s ∈ [0,1]` for player A:

```
surprise = (frags_a − frags_b) − 70·tanh((μa − μb)/2575)
margin_s = σ(surprise / 10)                   # logistic
margin_s = 0.65·margin_s + 0.35·σ((DDR−1)·2)  # DDR blend when damage data exists
s        = 0.65·binary(W/L/draw) + 0.35·margin_s
```

Both hypothetical OpenSkill posteriors are computed (A wins / B wins) and the
new rating is the s-interpolation between them. Cross-region dampening then
blends toward the prior exactly as before (×0.6 for the away player). σ gets
Glicko-style inflation of `1.0 σ-units/idle-day` at update time and never
contracts below `80`.

| Constant | Value | Where |
|---|---|---|
| `EXP_MARGIN_AMP` / `EXP_MARGIN_SCALE` | 70 / 2575 | [rate.py](../rate.py) |
| `MARGIN_NORM` | 10 | |
| `W_RESULT` / `DDR_WEIGHT` | 0.65 / 0.35 | |
| `TAU_PER_DAY` / `SIGMA_FLOOR` | 1.0 / 80 | |

**Evidence** (held-out log-loss; paired z = 21.7):

| Engine | log-loss | Brier | acc |
|---|---|---|---|
| v2 production (W/L + perf weight) | 0.4684 | 0.1388 | 80.9% |
| **v3 (continuous margin)** | **0.4115** | **0.1327** | 80.8% |

The gain is calibration, concentrated in mismatches: gap>800 improves 74%,
gap 400-800 improves 52%. Accuracy is flat — picking winners was never the
problem; probability quality was.

**Tested and rejected** (2026-08-16, keep for the record): trend-adaptive
volatility (Glicko-2-style σ inflation for players on a surprise streak) and a
dual career+form rating — both ≤0.1% gains, indistinguishable from noise. The
margin signal already tracks genuine improvement; a recency knob only adds
variance. Don't re-add without a backtest that beats 0.4115.

**Known property, deliberate: efficient wins vs weak opponents bleed μ.**
Surfaced 2026-08-17 by the sane/bogojoker case: sane went 406W-3L vs
1300-1700 opponents for **net −370 μ** (he wins by ~15-20 where the curve
expects more from his level), while bogojoker's blowout-farming of the same
tier paid +433 — that difference, not their elite results, is the whole gap
between them (vs 2100+ opponents the engine credits sane MORE: +201 vs +62).
Two candidate "fixes" were backtested and REJECTED:
- *Competitiveness-gated margin* (margin weight × 4p(1−p), so farm games score
  ~binary): log-loss 0.4115 → 0.4369-0.4726. The mismatch margin signal IS
  the calibration gain; gating it re-inflates the top like v2.
- *Win-bleed floor* (a win scores no less than `P(win) − slack`): slack 0.05
  → 0.4172 (−1.4%); slack 0.10 ≈ neutral (0.4118) but only narrows the
  sane-bogo gap 136→120 while adding a knob. Not worth it.
μ is a *level* estimate, not a win-the-game trophy: it settles where your
aggregate performance sits, and how hard you beat weak opponents is genuine
evidence of level. The face-validity cost for non-transitive pairs is handled
in the PREDICTOR instead (h2h blending, below) — not by distorting ratings.

**H2H-blended prediction** (api.py `/api/h2h`, added 2026-08-17): one global
rating cannot encode non-transitive style matchups (sane leads bogojoker
23-21 lifetime; rating-only predicted 35%). For pairs with **≥10 decisive
meetings**, the headline win probability shrinks toward the observed pair
record with **8 pseudo-games** of rating prior:
`p' = (n·h2h_rate + 8·p_rating)/(n + 8)`.
Backtested on pair-history games: 0.4115 → **0.4086**. Ratings themselves are
untouched — this is a prediction-layer overlay only.

### What gets rated

- Every 1on1 match in the `matches` table where `match_mode = '1on1'` and `match_id` resolves to exactly two distinct `canonical_id`s in `players`.
- Players who join/leave mid-match (multiple `players` rows per match per player) are deduplicated — we use their *aggregate* frag totals to determine winner.
- Draws are detected (equal frags) and use OpenSkill's draw machinery.

### Per-bucket ratings

We compute TWO sets of ratings per mode:

1. **Overall** (`map = ''`) — every 1on1 match contributes regardless of map. This is what powers the main rankings page.
2. **Per-map** (`map = 'dm2'`, `map = 'aerowalk'`, etc.) — a **shrunk deviation from the global rating** (v3, 2026-08-17), stored when the player has ≥ `per_map_min` matches on that map (default **5**) and the map has ≥ 50 matches corpus-wide.

```
map_μ = global_μ + 900 · (n/(n+10)) · mean(residual)
residual = actual outcome − P(win) predicted by the global rating at match time
```

`MAP_GAIN=900`, `MAP_SHRINK_K=10`. Accumulator state lives in the `map_residuals` table so incremental runs are exact. Map σ = global σ plus the standard error of the shrunk deviation.

~~Per-map as an independent ELO walk (K=32, seeded at final global μ)~~ **(deprecated 2026-08-17)** — backtested at 0.6614 log-loss / 69.0% accuracy, i.e. *worse than ignoring maps entirely* (global-only: 0.4016 / 81.4%). Two defects: (a) a free-floating rating on 5-20 games is a random walk — variance swamps the real map effect; (b) it was seeded/expected against the *final* global μ, leaking the future into historical matches. Map skill itself is real — split-half reliability of the per-map residual is **r = 0.50** (shuffled-label control: −0.08) — it just has to be estimated as a regularised deviation. The shrinkage model scores **0.3875 / 82.4%**, finally beating global-only. Prediction tools should use `global_μ + shrunk deviation`, never a standalone per-map rating.

Per-map ratings let the profile page show "you're rated 1800 overall but 2100 on AEROWALK." See `map_delta()` in [rate.py](../rate.py).

---

## 2. Opponent diversity — handled natively (no penalty)

**Deprecated 2026-05-26 with the OpenSkill migration.** Previously we ran TrueSkill plus a `sqrt(threshold/unique_opps)` σ multiplier ("diversity penalty") to stop "50-2 vs the same friend" rating inflation. OpenSkill's per-match σ updates handle this from first principles — see the empirical table in §1.

The `diversity_factor()` helper in [export_rankings.py](../export_rankings.py) now returns `1.0` always; it's preserved as a no-op shim so legacy callsites keep working without a sweep.

**What we still expose:**
- `unique_opponents` count per player remains stored and surfaced in API responses.
- The `provisional: true` flag stays for players with `unique_opponents < 10` (overall) or `< 3` (per-map) — purely a UX hint that the rating is built from a thin opponent pool. No math adjustment.

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

Decay still applies — diversity penalty is dead so there's no compounding factor anymore.

---

## 4. Tier ladder — Div 0 / 1 / 2 / 3 (percentile-based)

The conservative rating maps to one of four divisions ([tiers.py](../tiers.py)). **Percentile-based** boundaries: cutoffs are recomputed at request-time from the current rated population (matches_rated ≥ 10), so divisions auto-rebalance as the population evolves.

| Tier | Percentile | Color | Notes |
|---|---|---|---|
| **Div 0** | top 15% | gold (#fbbf24) | Elite. The genuine top tier across all regions. |
| **Div 1** | next 30% (55-85th) | violet (#a855f7) | Strong, multi-region competitive. |
| **Div 2** | next 35% (20-55th) | teal (#14e6c0) | Solid, regular competitors. |
| **Div 3** | bottom 20% (<20th) | gray (#64748b) | Climbing / casual / new. |

Cutoffs are computed by `_get_tier_cutoffs()` in [api.py](../api.py) using `tiers.compute_cutoffs()`. EU naturally dominates Div 0 due to depth — that's intended. The system measures rating, not regional fairness; cross-region fairness lives in the per-match weighting (§6).

**Replaced:** 10-tier GOAT/Mythical/Legend/Champion/Master/Highlander/Marauder/Gladiator/Fragger/Pubstar ladder (deprecated 2026-05-26). The new scheme uses Quake-native division convention and gives clearer signal at the top (15% Div 0 ≫ the prior 0.1% GOAT cliff).

---

## 5. Identity / canonicalization

Ratings are keyed on `canonical_id`, not raw player name. The pipeline:

1. **`canonicalize.py`** applies [`aliases.yaml`](../aliases.yaml) — explicit mappings like `chris ← chr1s, eatmyass` and `war ← whodat, george, notgeorge`.
2. **Fuzzy candidates** (RapidFuzz score ≥ 0.78) go to `.review_queue.yaml` for human review. Edit `decision: accept|reject` then run `python name_canon.py apply-reviews && python canonicalize.py`.
3. **Name spam** (color codes, brackets, clan tags) gets normalized — `(1)Carmolio` → considered for `carmolio`.

Without canonicalization, every clan tag change creates a new "player" and ratings fragment. Aliases are append-only — once two identities are merged, all their matches share one rating arc.

---

## 6. Regional weighting — inter-regional match dampening (live)

Each player has a primary region (NA / EU / SA / OC / AS-AF) assigned by [assign_player_regions.py](../assign_player_regions.py). LAN events are excluded from the assignment calculation.

**Cross-region rating update logic** (introduced 2026-05-26, in [rate.py](../rate.py)):

When a match is played on a server whose region differs from a player's home region, that player is "away" and their rating update is **dampened to `CROSS_REGION_WEIGHT = 0.6`**. The home-region player's update is unaffected (full weight = 1.0).

| Match scenario | Away player's update | Home player's update |
|---|---|---|
| EU server, both EU players | 1.0× (n/a) | 1.0× |
| EU server, EU vs NA | NA player: 0.6× | EU player: 1.0× |
| LAN / unknown-region server | 1.0× (no data, no penalty) | 1.0× |

**Rationale:** the visiting player's ping handicap makes the result less reliable as a measure of their skill, but the result is still informative for the home player who's on fair-ping conditions. Dampening (vs. excluding) the away update keeps cross-region matches contributing — just with discounted confidence.

Implemented via a manual μ/σ blend: `new = old + weight * (openskill_full - old)`. Done in Python rather than openskill's `weights=` param because that parameter is for team-internal contribution weighting (4on4 carry signal), not 1v1 match-confidence dampening.

The `0.6` factor was chosen by reasoning, not data. Revisit after a quarter of cross-region match data accumulates — particularly to see if Cronus/sane/blaze-on-EU matches and BPS/Carapace-on-NA matches calibrate to a reasonable cross-region "exchange rate."

---

## 7. Stats leaderboards (mechanical-skill, separate from rating)

In addition to OpenSkill (who you BEAT), we expose mechanical leaderboards (how you PLAY) at `/stats`. From [stats_pg.py](../stats_pg.py):

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

**The DDR/Net-damage story** is the QW-equivalent of hockey's Corsi: damage is the "shot attempts" underlying frags. A high DDR with low OpenSkill rating suggests "actually better, getting unlucky"; the inverse suggests "fragile, due to regress." See [4on4_methodology.md](./4on4_methodology.md#corsi-narrative) for the full theoretical framing — it informs team-mode design more than 1on1.

---

## 8. Known issues / open improvements

### Decided, pending
- **Phase 4: cross-region weighting** (per-mode thresholds) — see Section 6.
- **Mix vs divisional split** — EU has formal divs (Div 1/2/3/4 league play); NA/AU/BR are pickup-only. A rating earned in structured div play arguably carries different weight than mix-game wins. Optional per-region split.

### Open questions
- ~~**Frag-differential weighting** — currently a 21-19 win and a 21-3 win count identically.~~ **Shipped 2026-08-17** as the v3 continuous-margin outcome (§1b). (A weaker multiplicative perf-weight version had shipped 2026-05-26; §1b explains why it wasn't enough.)
- ~~**Score decay** — time-weighted re-rating would let skill genuinely improve faster.~~ **Resolved 2026-08-17, mostly by rejection**: idle-day σ inflation (`TAU_PER_DAY=1.0`) shipped in-engine, but explicit recency weighting was backtested two ways (trend volatility, career+form dual rating) and both failed to beat the margin signal — see §1b "Tested and rejected".
- **Tier renaming** — see Section 4.

### Limitations
- Only stores ratings for `per_map_min ≥ 5` matches per map — obscure maps with 1-2 games show no per-map rating (accumulators are tracked from game 1 in `map_residuals`, so nothing is lost before the threshold).
- OpenSkill's `tau` is a global compromise. Partially mitigated 2026-08-17 by `TAU_PER_DAY` idle inflation + `SIGMA_FLOOR=80`, but a genuinely volatile ACTIVE player still shares the global dynamics (an explicit fix was tested and rejected — §1b).
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

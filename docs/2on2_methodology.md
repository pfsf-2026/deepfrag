# 2on2 Rating Methodology — DeepFrag

> Status: **NOT YET BUILT.** This document is the design bible we'll use when we tackle 2on2. The 1on1 system ([1on1_methodology.md](./1on1_methodology.md)) ships as v1.0; this is the working spec for what 2on2 needs to look like before we write code.

---

## 1. Why 2on2 isn't just "1on1 with two players"

The temptation is to drop the existing 1on1 OpenSkill pipeline onto 2on2 matches and call it done. OpenSkill (and the Weng-Lin family) supports team play out of the box — pass `[player_a, player_b]` vs `[player_c, player_d]` and it'll redistribute the rating delta. We could ship that in an afternoon.

But it would be **wrong**, and silently wrong, in ways that 1on1 isn't. The fundamental difference: in 1on1 the player IS the team — every kill, every armor, every drop is one person's doing. In 2on2 there are two players whose contributions are not separable from the result. A great player carrying a weak partner generates the same scoreboard W as two equal players grinding it out. The rating update treats both partners identically, which means:

- **Carry players get under-rated.** They win games they "shouldn't" by raw team-skill math, so the model thinks the team is overperforming and adjusts modestly.
- **Carried players get over-rated.** They ride teammate skill to wins and get equal credit.
- **The "who you played WITH" signal is discarded.** Two wins with a 2300-rated partner shouldn't move you the same as two wins with a 1400 partner. Vanilla team-rating ignores this.

2on2 is the *least bad* team mode for the naive approach — only one partner to confound things — but the bias still compounds over hundreds of matches.

---

## 2. What 2on2 has that 1on1 doesn't

Before we design, list what's actually different about 2on2 data:

- **Two players per side** — duos that recur frequently (clan pairs), and pickup partners.
- **Maps are mostly the same** (dm2, dm4, dm6, e1m2, povdmm4) — slightly different meta (more frag farming, less item dance) but per-map ratings will work.
- **Match length is shorter** on average — 10-minute timers common.
- **Per-player stats still exist** — MVDs record damage given/taken, accuracy, item pickups per player. So mechanical leaderboards (LG%, RL%, DDR) work essentially unchanged from 1on1.
- **Match volume is lower** — 2on2 is fewer total matches than 1on1 or 4on4. Diversity penalty thresholds will need recalibration; 10 unique opps may be unrealistic.

---

## 3. Proposed rating architecture

### Layer 1: Team OpenSkill (baseline)

Run OpenSkill with `[a, b]` vs `[c, d]` as the team composition. Store the per-player μ/σ deltas. This gives us a working leaderboard immediately and is the floor we improve from.

Tune:
- `tau` may need to be higher than 1on1's value because 2on2 partner variance adds noise.
- `beta` likely lower (~150-200) since team play is less spiky than 1on1.
- Draw handling stays minimal — 2on2 draws are rare.

### Layer 2: Partner-weighted adjustment

After Layer 1 produces base ratings, post-process to account for partner quality:

```
expected_team_rating = (μ_a + μ_b) / 2
actual_outcome = win/loss vs opponent_team_rating
partner_contribution = corr(your_match_stats, team_outcome | partner_rating)
```

The intuition: if you consistently outperform your team's expected rating when paired with weaker partners, you have a positive *carry coefficient*. We bonus your individual μ for that.

This is what Halo/Dota use ("MMR adjustment by performance"). Implementation TBD — needs offline experimentation against known carry players.

### Layer 3: Performance-derived priors (use stats as evidence)

DDR and frag-differential at the individual level are signals INDEPENDENT of team outcome. A player who racks up a 2.0 DDR in a losing 2on2 effort tells us something the raw W/L rating doesn't see (the loss says they're worse, the DDR says they were the best player on the server).

Use as soft Bayesian prior — small adjustment toward the stat-implied skill. Don't let it dominate; outcomes are still the ground truth.

---

## 4. Stats leaderboards for 2on2

Most 1on1 stats transfer directly. The 11-stat ([stats_pg.py](../stats_pg.py)) plus DDR/Net Damage all work — per-player records exist in MVDs regardless of team size.

**New 2on2-specific stats to consider:**

- **Partner uplift** — your team's win rate / (avg of your individual ratings). >1 = you elevate partners; <1 = you drag them down. Requires Layer 2 work.
- **Frag share %** — what % of your team's frags did you generate? High share + wins = carry; low share + wins = supported.
- **Damage share %** — same idea for damage. Less scoreboard-distorted than frag share (some maps reward different roles).

Hold these until Layer 1 ships — leaderboards are easy once the rating table exists.

---

## 5. Identity / region / decay

All inherited from 1on1 without change:
- `canonical_id` is the same person across all modes.
- Regional assignment is mode-agnostic (a player's primary region is the same whether they 1on1 or 2on2).
- Inactivity σ-decay applies per-mode (you can be active in 1on1 but inactive in 2on2).

Diversity thresholds: **recalibrate**. Suggest starting at `THRESHOLD_OVERALL = 8` (vs 10 in 1on1) given lower match volume. Per-map threshold = 3 unchanged.

---

## 6. Cross-mode rating relationships

Open question: should 1on1 skill inform 2on2 starting μ?

**Arguments for** (use 1on1 rating as 2on2 prior):
- 1on1 skill correlates strongly with 2on2 individual play in QW (movement, aim, item control all transfer).
- A new 2on2 player who's a 1900 1on1 player shouldn't start at 1500 — we know they're better.

**Arguments against:**
- 2on2 demands team awareness, comms, role-discipline that 1on1 doesn't test. Many top 1on1 players are mediocre 2on2 players.
- Cross-contamination — a 2on2 loss would unfairly drag a 1on1 rating if we tied them.

**Recommended approach:** loose Bayesian prior at first-match — set starting μ to 0.7 × 1on1_rating + 0.3 × 1500, with full σ (500). After 10 2on2 matches, σ has narrowed enough that the prior doesn't dominate. This is standard "informative prior" handling.

---

## 7. What we don't need to solve (yet)

- **Carry rating as a separate displayed metric** — interesting but premature. Bake into Layer 2 first; surface as a UI element only if signal is strong.
- **Sub-team rating** (e.g., rating "Cronus + Reload" as a duo) — fun but niche. Build only if community asks.
- **Role classification** (who's the "frag guy" vs "support") — too 4on4-ish; 2on2 doesn't really have defined roles.

---

## 8. Tier ladder for 2on2

Re-calibrate from the 1on1 tier breakpoints. Don't reuse the 1on1 distribution. 2on2 has fewer rated players and the distribution will be tighter (team play averages out individual spikes). Calibrate AFTER Layer 1 ships and we have actual rating distribution.

Likely we drop or merge tiers — 8 instead of 10 — since the rating spread will be narrower.

---

## 9. Build order

1. Schema additions: nothing major — `ratings` table already has `mode` column; just start writing `mode='2on2'` rows.
2. Modify [rate.py](../rate.py) `rate_bucket` to handle team mode: detect `match_mode='2on2'`, group by team_id (or by `team_score_red`/`team_score_blue` columns — confirm schema), call OpenSkill with team lists.
3. Per-map per_map_min stays 5; recalibrate after first run.
4. New rankings page tab/dropdown for 2on2 (frontend trivial — `/api/rankings?mode=2on2` already accepts the param).
5. Layer 2 + Layer 3 = separate later iterations.

**Estimated session time for Layer 1: 1-2 sessions.** Layers 2 and 3 are research projects, not sprints.

---

## 10. References

- OpenSkill team mode: [openskill.py docs](https://openskill.me/en/stable/) (Weng-Lin model)
- TrueSkill team mode (historical reference): [Microsoft Research docs](https://www.microsoft.com/en-us/research/project/trueskill-ranking-system/)
- Partner uplift / carry coefficient: Dota 2's MMR research, various Riot LoR/LoL post-mortems
- Bayesian prior across game modes: openskill.py docs (Weng-Lin model handles this naturally)
- See [4on4_methodology.md](./4on4_methodology.md) for related carry/stacked-damage thinking that compounds 2on2 issues

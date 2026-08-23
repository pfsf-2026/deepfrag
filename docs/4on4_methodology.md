# 4on4 Rating Methodology — DeepFrag

> Status: **Layer 1 SHIPPED 2026-08-23** (individual ratings + margin engine + team balancer — see §0). Layers 2-4 (roles, stacked-DDR, roster context) remain design. Read [1on1_methodology.md](./1on1_methodology.md) first for the rating engine basics, and [2on2_methodology.md](./2on2_methodology.md) for the team-rating fundamentals — this document focuses on what's UNIQUE about 4on4.

---

## 0. Layer 1 as shipped (2026-08-23)

Individual per-player 4on4 ratings via team OpenSkill (PlackettLuce 4v4) with the
**continuous-margin outcome** validated for 1on1 in the v3 engine — ported to team
level and re-tuned on 4on4 data. `rate_team_mode()` in [rate.py](../rate.py).

### Constants (coordinate-descent sweep, walk-forward log-loss, 2026-08-23)

| Param | Value | Note |
|---|---|---|
| `TEAM_BETA` | 200 | vs 250 in 1on1 — bible §3's "lower beta" guess confirmed by sweep |
| `TEAM_W_RESULT` | 0.35 | margin carries 65% of the outcome — MORE than 1on1 (35%): team margins (median 65 frags) are high-information, single W/L is noisy |
| `TEAM_EXP_AMP / SCALE` | 110 / 700 | expected team frag diff = 110·tanh(mean_mu_gap/700) |
| `TEAM_MARGIN_NORM` | 40 | |
| `TEAM_SIGMA_FLOOR` | 80 | same convention as 1on1 v3 |
| tau | 0.5 | sweep axis was flat (no measurable effect); kept at model default |

**Added 2026-08-23 (same-day, separately validated):**
- **Per-map shrunk deviations** — split-half reliability of 4on4 map skill r=+0.28
  (control −0.10; Spearman-Brown 0.44 — real, weaker than duels' 0.67). Layer:
  mu_map = mu + 1900·(n/(n+60))·mean_resid vs the map-adjusted prediction.
  Logloss 0.5894 → 0.5694. State in `map_residuals`; per-map rating rows emitted
  at ≥5 games; `/api/balance?map=` uses them.
- **Contribution weighting (Layer-2-lite, revised 2026-08-24)** — each player's
  personal outcome = team score + 1.1·(damage_share − expected_share), clamped
  [0,1], with **expected_share = own μ / Σ team μ**. Logloss → **0.5560**,
  accuracy → **71.5%**. The first version used a flat 0.25 baseline, which
  systematically drained players on stronger teams and boosted players on
  weaker ones (Peter's ntr/roster-context observation) — μ-conditional fixes
  the bias AND predicts better. CW beyond 1.1 keeps improving logloss slowly
  (0.5516 @ 3.0) but drifts toward pure performance rating with role bias
  (damage share is not role-neutral: RA-defenders under-share by design) —
  do not raise without role modeling. This is what makes INDIVIDUAL improvement
  move an individual's rating instead of being smeared across the team.

**Anti-alias gate (2026-08-24, Peter):** a player with NO 1on1 rating row gets no
PUBLISHED 4on4 rating (matches still count toward opponents). Throwaway alias
accounts live in team modes and rarely duel — the duel rating is the identity bar.

**Deliberately absent** (not part of the validated backtest — add only with fresh evidence):
DDR term in the outcome score, idle-day sigma aging, cross-region weighting.
Matches that are not exactly 4v4 with two teams are skipped entirely.

### Validation (scratchpad t4.py/balance.py, 19,877 matches 2022-01..2026-05)

Walk-forward, scored on 9,946 matches (2024-08-23+, all 8 players ≥10 priors):

| Engine | logloss | acc |
|---|---|---|
| coin flip | 0.693 | 50% |
| per-player Elo (K=16) baseline | 0.618 | 65.7% |
| pure team OpenSkill | 0.611 | 67.5% |
| **shipped margin engine** | **0.589** | **68.1%** |

Calibration: favorite-probability buckets land within ~1-2pts of their centers
(50-60%→56.0, 60-70%→65.3, 70-80%→74.9, 80-90%→86.0, 90-100%→95.0) and actual
frag margins rise monotonically with confidence (65→156).

### Team balancer (`GET /api/balance`)

For 8 players, enumerates all 35 4/4 splits and returns the most even by
predicted win probability. Historic validation: actual pickup splits averaged
|P−0.5| = 0.174 (a ~67/33 game); the optimal split of the same 8 players
averages 0.016 (~52/48); a <55/45 split existed in 94.5% of matches but actual
teams achieved one only 16.4% of the time. External check: predicted evenness
of ACTUAL splits tracks realized closeness (the calibration table above), so
minimizing predicted imbalance minimizes real imbalance. Known bias: skill is
treated as additive — practiced fixed rosters outperform their rating sum
(that's Layer 4's job).

---

## 1. Why 4on4 is the hardest

If 1on1 is "the player IS the team" and 2on2 has "one teammate to confound things," 4on4 is **three teammates of variable skill plus role differentiation plus item-control dynamics that don't exist anywhere else**. The naive failure modes from 2on2 ([§1](./2on2_methodology.md#1-why-2on2-isnt-just-1on1-with-two-players)) all amplify:

- A 2400-rated player can win games carrying THREE weaker partners with vanilla team-rating assuming the whole team contributed equally to the outcome.
- "Who you played WITH" is now a 3-dimensional question — your partners' skills, your partners' role-compatibility, AND the opponent-team composition.
- Match outcomes have higher variance — one 4-stack of pugs can beat a stacked clan on the right map with the right rolls. Sample size needed to converge is larger than 1on1 or 2on2.

Additionally, 4on4 has **role differentiation** that 2on2 barely hints at:

- The **MH (Mega Health) guy** — controls timing on mega, generates damage from a stacked position.
- The **RA (Red Armor) guy** — opposite item, similar role.
- The **YA/runner** — picks up loose armors, joins fights with partial stack, often the frag leader.
- The **defender** — sits on items the team needs to deny, doesn't farm frags.

These aren't fixed positions like hockey forwards/defensemen — they emerge from the match. But they DO mean two players with identical scoreboard stats might have wildly different roles and team values.

---

## 2. The Corsi narrative — what we want to capture

(This is the conceptual framing the user requested be preserved. The DDR + Net Damage stats already shipped for 1on1 ([1on1 §7](./1on1_methodology.md#7-stats-leaderboards-mechanical-skill-separate-from-rating)) come from this thinking, but the *real* payoff is in 4on4.)

### What Corsi measures (hockey)

In hockey, goals are rare and noisy — you can dominate a game and lose 1-0 because the goalie stood on his head. **Corsi** solves this by counting *shot attempts* for and against while you're on the ice. The intuition: a team that's constantly attacking will eventually score, even if tonight they didn't. So Corsi is a *territorial/pressure* stat — it captures who was controlling play, decoupled from puck luck. A player with great Corsi but bad goal differential is usually unlucky; one with bad Corsi but great goals is riding hot shooting and will regress.

### The QW parallel

Frags in QW are the goals — discrete, scoreboard-defining, but noisy on any given match. You can outplay someone for 8 minutes and lose 21-19 because they got the lucky RA rock at 4:30 and snowballed. What we want is the QW version of "shot attempts" — the thing happening continuously that *causes* frags, where you can't get lucky for 10 minutes straight.

That thing is **damage**. Every LG beam, every RL splash, every SG pellet is a "shot attempt" in the Corsi sense — it's the underlying pressure that converts to frags over time. So:

- **Damage Differential Ratio (DDR)** = Σ dmg_given / Σ dmg_taken. This is the cleanest Corsi analog. A 1.5 DDR means "for every 100 HP they take off me, I take 150 off them" — sustained territorial dominance. It's a *rate*, so it's map-length and pace-neutral, which is exactly why hockey people prefer Corsi% to raw Corsi.
- **Net damage per match** is the Corsi *raw* version — the absolute margin. Less neutral (long maps inflate it) but more visceral. "Sane averaged +3,400 HP swing per match" tells a story that "1.69 ratio" doesn't.
- **Item Control Index** (RA + Mega per minute alive) is the deeper layer — the QW version of *zone entries* in hockey analytics. Damage is what happens; item control is *why* it happens. The guy who's first to every RA is the guy generating the damage diff. It's a leading indicator.

### Where it gets interesting in team modes — STACKED vs NAKED

This is the insight the user contributed that changes how the metric is computed in 4on4. In hockey, "on the ice" is a clean state — you're either out there or you're on the bench. In team QW, naive damage-diff has a problem: **respawn is instant, but state is not**.

> "Players are pretty much always alive, but 0/100 with no stack on respawn and must acquire weapons and armors to become 'stacked' and impact the balance of the game in their team's favor."

A 4on4 player respawning naked at mid isn't really "on the ice" in the Corsi sense — their LG chip into a stacked enemy isn't pressure, it's noise. The damage that *matters* is the damage you do while you have the stack to back it up, because that's what threatens to flip control of the map.

So the team-mode Corsi equivalent isn't just "damage diff while alive" — it's **damage diff while stacked**. That's the stat that would actually separate the players who repeatedly *acquire* stack and use it from the players who farm naked-LG damage on the way to the next RA they're going to lose anyway.

This is harder to compute (need to track armor/weapon state per second from MVD frames), but it's the metric that would correspond to what coaches actually look at — and it dovetails directly with the team rating work, because the **carry signal** is essentially:

> "this player generates positive stacked-damage-diff regardless of teammates"

### Why it matters for ratings

OpenSkill only sees W/L. Corsi-likes give us a *match-quality* signal underneath the result. Two players with the same OpenSkill rating might have wildly different DDRs — the high-DDR one is "actually better, getting unlucky," the low-DDR one is "fragile, due to regress." Over time we could use this to either:

1. **Accelerate rating adjustments** — high-DDR underrated players get bigger gains per win (Bayesian "expected goals" treatment).
2. **Surface as a separate "form" indicator** on profiles — the QW equivalent of expected goals shown alongside actual goals.

The second is cheaper to ship and informationally rich. The first is the deeper integration but requires careful validation against actual rating-prediction accuracy.

---

## 3. Proposed 4on4 rating architecture

Inherits 2on2's three layers ([2on2 §3](./2on2_methodology.md#3-proposed-rating-architecture)) with 4on4-specific tweaks:

### Layer 1: Team OpenSkill (baseline)

`[a, b, c, d]` vs `[e, f, g, h]`. OpenSkill (Weng-Lin) handles N-vs-N natively. Tuning:
- ~~`tau` higher than 2on2 (~15-20) due to 4-player variance.~~ (decided 2026-08-23: sweep showed tau flat — kept 0.5)
- ~~`beta` lower (~100-150) — outcomes are less spiky.~~ (decided 2026-08-23: sweep landed on 200, direction right, magnitude wrong)
- draws handled by the continuous outcome score (binary component = 0.5) — no draw_probability tuning needed.

### Layer 2: Partner-weighted adjustment with role awareness

The 2on2 carry coefficient extends to 4on4 but with role-classification:
- Compute each player's "frag share" and "damage share" within the match.
- Cluster players into rough roles (high item-control + low frags = "MH/RA"; low item + high frags = "runner"; etc.).
- Carry coefficient compares your in-role performance against partner-baseline-of-role.

This is significantly harder than 2on2 — needs offline clustering work plus per-role rating arcs.

### Layer 3: Stacked-DDR as primary performance prior

THIS is where the Corsi work pays off. Instead of using raw DDR as the performance signal, use **stacked-DDR** — damage diff weighted by your armor+weapon state. Mechanics:

1. For each second of match time, classify player as STACKED (RA/YA + RL/LG) or NAKED.
2. Sum damage given/taken in STACKED windows only.
3. Stacked-DDR = Σ stacked_given / Σ stacked_taken.

A player who frags 30 times while never holding stack has lower stacked-DDR than one who frags 20 times all from stacked positions, even though the scoreboard says the first did more "work." The second is the player who controlled the map.

Use stacked-DDR as the prior, not raw DDR. Raw DDR still ships for the leaderboard but the rating system reaches for stacked-DDR.

### Layer 4: Roster context

4on4 in QW is dominated by **fixed clans + pickup teams**. The same 4 players win 80% of their matches together because they have comms, set plays, item-rotation discipline. Their individual ratings should NOT inflate equally from those wins — the *roster* is rated, not just the players.

Track:
- Fixed-roster win rate (% of matches with exactly the same 4 players)
- Mix/pickup win rate
- Carry rating = (your mix W%) − (your fixed W%)

A player with positive carry in mix games is the one who's actually individually elite. A fixed-roster star who can't carry pickup teams is rated more conservatively.

This is the EU-formal-divisions context where DivX rosters matter. NA/AU/BR are pickup-only and Layer 4 collapses to nothing — fine.

---

## 4. Team-mode stats — what to build, in priority order

| Stat | Difficulty | Value | When |
|---|---|---|---|
| Per-player frag/damage stats (LG%, RL%, etc.) | Trivial (reuse stats_pg) | Medium | Same day as Layer 1 |
| Per-player DDR + Net Damage | Trivial | Medium | Same day as Layer 1 |
| Frag share % | Easy (group by team within match) | High | After Layer 1 |
| Damage share % | Easy | High | After Layer 1 |
| **Stacked-DDR** | HARD (per-frame MVD parsing) | **Very high — defines carry** | Major project |
| On-field item-control index | Medium (just sum RA+MH per minute alive) | High | After Layer 1 |
| Carry rating (mix vs fixed) | Medium (requires roster tracking) | High in EU | After Layer 1 |
| Spawn timing | N/A | Zero — rejected | Never (per user: respawn is instant) |

The "rejected" entry is important to preserve: in hockey analytics, "shifts per game" and "time on ice" are first-class stats. They don't translate to QW because QW has no spawn discipline — everyone respawns immediately. Don't invent equivalents; the right move is stacked-DDR.

---

## 5. MVD data requirements for stacked-DDR

Stacked-DDR is the killer stat but requires data we may not currently extract. Audit needed:

- Does our MVD pipeline (or the hub.quakeworld.nu source) expose **per-frame armor/weapon state**? Or only end-of-match aggregates?
- If only aggregates: we either re-parse MVDs ourselves (huge undertaking) or partner with whoever runs ezQuake's MVD analyzer.
- Alternative: approximate stacked-DDR via **pickup proximity** — count damage in the 30s window after picking up RA/MH/YA. Cruder but uses data we already have.

**Recommend: ship the approximation first**, validate it correlates with subjective "who carried" rankings from community polls, then invest in true per-frame parsing if the approximation drifts.

---

## 6. Cross-mode rating priors

Same trade-off as 2on2 ([§6](./2on2_methodology.md#6-cross-mode-rating-relationships)). 1on1 skill correlates LESS with 4on4 than with 2on2 — 4on4 demands team coordination that 1on1 doesn't test at all.

Recommended:
- Starting prior: 0.5 × 1on1_rating + 0.5 × 1500, full σ. Weaker prior than 2on2's 0.7.
- After 15 matches, prior is dominated by 4on4 outcomes.

---

## 7. Tier ladder for 4on4

Probably needs different breakpoints than 1on1/2on2 — 4on4 rating distribution is tightest of all three modes (team play averages out). Calibrate AFTER Layer 1 ships.

The role-differentiation problem means a single tier ladder is less informative — a Mythical-tier MH player and a Mythical-tier runner play completely differently. Worth considering **role-tagged tiers** (Mythical Runner, Champion Anchor) once Layer 2's role clustering is in place.

---

## 8. Build order

1. **Layer 1 + basic stats** — 1-2 sessions. Schema is in place; just turn on 4on4 in [rate.py](../rate.py).
2. **Frag/damage share stats** — 1 session after Layer 1.
3. **Approximated stacked-DDR** (post-pickup window) — 1-2 sessions, includes validation.
4. **Layer 4 roster context** (mix vs fixed carry) — 1 session, gated on having enough match data per roster.
5. **Layer 2 role clustering + role-aware ratings** — research project, 2-4 sessions plus offline analysis.
6. **True per-frame stacked-DDR** — only if approximation proves insufficient. Major engineering effort.

---

## 9. What we explicitly defer

- **Live coaching tips** — far future; the rating + stat plumbing has to be rock-solid first.
- **Match prediction model** — interesting but it's "rating evaluation" not rating itself. Build after Layers 1-3.
- **AI commentary** — UI-level, not rating-system. Separate workstream.

---

## 10. Attribution: phylter's qw-4on4-ratings

DeepFrag's ingestion lineage: our sync.py's hub-fetch pattern **was lifted from
[phylter-qw/qw-4on4-ratings](https://github.com/phylter-qw/qw-4on4-ratings)**
(it says so in its docstring) and our matches/players schema matches his
column-for-column. This bible failed to credit that before 2026-08-24 — fixed.

His rating method differs from ours: community-survey-derived weights over
per-stat standard scores → per-player match score → TrueSkill. That is a
*performance rating* (stats drive rating regardless of team result); ours is
*outcome-anchored* (team W/L + margin) with a bounded contribution nudge. His
weights.txt is a genuine community prior over what matters in 4on4 — a future
experiment: replace damage-share in our contribution term with a phylter-style
weighted standard-score composite, backtest against 0.5560.

## 10. References

- Corsi statistic: [Wikipedia](https://en.wikipedia.org/wiki/Corsi_(statistic))
- Expected Goals (xG) in soccer: closest analog to what stacked-DDR would be — outcome-decoupled performance metric
- OpenSkill (Weng-Lin) N-vs-N: [openskill.py docs](https://openskill.me/en/stable/)
- TrueSkill N-vs-N (historical reference): [Microsoft Research](https://www.microsoft.com/en-us/research/project/trueskill-ranking-system/)
- Dota 2 MMR / "personal performance": [Valve blog post on MMR](https://web.archive.org/web/2020/https://blog.dota2.com/) — basis for Layer 2 carry coefficient
- ezQuake MVD format spec: [QuakeWorld wiki](https://wiki.quakeworld.nu/MVD) — required reading before per-frame parsing

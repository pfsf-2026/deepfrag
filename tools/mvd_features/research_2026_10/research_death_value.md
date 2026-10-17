# Death value — which deaths are meaningless, how the top NA players avoid them, and what their deaths buy

4on4 on dm3 / dm2 / e1m2 / schloss, 8 players, since 2025-01-01: **1,415 games, 649,183 deaths** (every player), of which the
24 rostered players account for 534,876 (TOP 229,913 in 4,371 player-games; FIELD 304,963 in 4,889). The roster is 82% of all
player-games in the pool, so FIELD is the pool's average, not a weak tail. Scripts and raw tables sit next to this file:
`death_value_build.py` (one row per death → `deaths.csv`), `death_value_analyze.py` (→ `death_value_out.md`, every table quoted
here plus the per-player-per-map table), `stacked_hazard.py` (→ `stacked_hazard_out.md`).

## The five findings

1. **The field dies 8.9 more times per game than the top (57.7 vs 48.8 enemy kills), and more than all of that gap is empty deaths.**
   Lives that dealt under 50 damage, killed nobody and took no armor/weapon/powerup: 26.7 per game for the field vs 19.3 for the
   top. Deaths that bought something (an item, a frag, 100+ damage, a long life) are *equal or more frequent* for the top
   (spawn_item 1.73 vs 1.67, spawn_trade 4.72 vs 4.52, productive 7.95 vs 7.28, died holding quad 1.29 vs 0.73 per game).
   The headline MEANINGLESS class (spawn death inside 14 s, under 50 damage, nothing taken, team not locked, no enemy powerup up)
   is 7.9 per game for the top vs 11.1 for the field (1.40×; 1.48× when the two are teammates in the same game).
2. **In the same state the two groups die at the same rate; the top spends less time in the bad states.** Per 10 s sample: a
   fresh, unarmed, unstacked player dies in the next 10 s 49.8% (top) vs 49.5% (field); a 150+ player with no RL/LG 23.4% vs 24.7%.
   Armed and stacked: 9.4% vs 11.5%. The difference is exposure: the field spends 36% of its stacked time without a gun (top 24%),
   is armed 32% of its alive time (top 48%) and stacked 24% of it (top 33%). This is a route/decision gap, not an aim gap.
3. **What a death buys: a top life returns 178 damage, 1.11 frags and 0.69 items; a field life 103 damage, 0.60 frags, 0.42 items**
   (same team, same game: 215 vs 113 damage, 0.85 vs 0.47 items). The median life is the same length (8.6 vs 9.1 s) and both chain
   two-thirds of deaths inside 14 s; the top's extra value sits in the long tail (7.3% of its lives last 60 s+, field 4.8%) and in
   what short lives do (a 6–14 s top life deals 68 damage, a field one 54).
4. **Wasted stack is mostly "armor without a gun", and it is the second most expensive death after dying with quad.** A life that
   lasted 14 s+ and entered its last fight with 150+ but dealt under 100 in it costs −5.2 pp of win probability (−4.1 net of what
   it dealt); the field does it 1.85 times a game vs 1.44 (0.41 vs 0.22 per stacked minute). 62% (top) and 69% (field) of those
   players had no RL or LG; the killer was smaller than the victim 78% of the time; the fight lasted 2.8 s. The survivors' version
   of the same state (150+, RL in hand) dies at a third of the rate on every map.
5. **Under a lock everybody dies the same: 74% chained, 44–45% killed inside 6 s, survival to 14 s identical per map. The top's locked
   lives simply buy more:** an item inside 14 s 18.5% vs 13.8%, 50+ damage inside 14 s 33% vs 24%, 113 vs 65 damage per locked life.
   On schloss the top's locked survivors take an item inside 14 s 57% of the time, the field's 38%; on dm3 48% vs 33%.

---

## 1. Method

**A life.** For every `frag` event with t ≥ 1 s (match-start telefrags dropped) the life is `[t − vic_tss, t]`. `vic_tss` was
consistent with the previous death 99.9% of the time. Per life: damage dealt (KTX-capped, enemy only), damage to enemies who were
150+ when hit, frags, "stacked frags" (victim had entered his final fight with 150+), items taken from `item_takes`
(RA/YA/GA/MH/RL/LG/quad/pent/ring/GL/SNG), and the same inside the first 14 s.

**The last fight.** Walking back from the death through the player's enemy damage events (dealt or taken) with gaps ≤ 4 s gives the
fight start; `eff_fight` is his effective HP at the first event of that chain (or at death for a one-shot). `dmg_fight`,
`frags_fight` are what he did inside it. **Alone** = no teammate dealt damage to, or took damage from, any of the enemies he was
exchanging with in the final 5 s. `n_enemies` = distinct enemies who hit him or were hit by him in those 5 s, plus the killer.

**Killer:** eff, RL/LG, powerup, time since spawn and weapon from the frag row. **Lock:** the lock_spawn.py margin
(enemy stack − own) + 100·(enemy RLs − own) + 100·(enemy RAs − own) at the 10 s sample, thresholds at the 85th percentile per map
(dm3 511, dm2 487, schloss 433, e1m2 238), evaluated at spawn and at death. **Quad:** `enemy_quad`/`enemy_pent` = an enemy
powerup run (`powerup_runs`) covered the death; `held` = the victim held one; `quad_fight` = died in a quad room (`quad_rooms.json`)
between 10 s before and 5 s after a quad spawn.

**Win-probability cost** (winprob_4on4.json, per-map model, victim's team, state10s sample containing the death):
- `dp_frag` = the frag alone;
- `dp_cost` = the frag plus losing what he carried into the last fight: (eff_fight − 100) of stack (he respawns with 100), his RL, LG
  and powerup;
- `dp_net` = dp_cost plus credit for the damage and frags he made in that fight. It does not credit item denial, position or time,
  so it understates `spawn_item` lives.
All costs below are for live games only (0.10 ≤ p(win) ≤ 0.90 before the death).

**Classes** (enemy kills; team kills and suicides counted separately: 3.8 vs 4.7 per game). First match wins:

| class | definition |
|---|---|
| held_quad | died holding quad or pent |
| quad_victim | killed by a quad/pent holder |
| quad_fight | died in a quad room within −10/+5 s of a quad spawn |
| spawn_nothing | life < 14 s, dealt < 50, no frag, no RA/YA/MH/RL/LG/powerup |
| spawn_scratch | life < 14 s, dealt 50–99, no frag, no item |
| spawn_item | life < 14 s, took RA/YA/MH/RL/LG/quad/pent/ring |
| spawn_trade | life < 14 s, a frag or 100+ damage |
| productive | life ≥ 14 s and (200+ damage, or 2+ frags, or an item plus 100+ damage) — judged on the whole life |
| stack_wasted | life ≥ 14 s, not productive, entered the last fight with 150+ and dealt < 100 in it, no frag in it |
| stack_traded | same but dealt 100+ or fragged in it (almost always already "productive", so tiny) |
| alone_2plus | life ≥ 14 s, not productive, under 150, alone vs 2+ in the final 5 s |
| mid_empty | life ≥ 14 s, dealt < 50, no frag, no item |
| mid_other | life ≥ 14 s, some output (50–199 damage or one frag), none of the above |

Two flags cut across classes: **MEANINGLESS** = spawn_nothing and not locked at spawn and no enemy quad/pent run up and not holding
a powerup. **STACK LOST** = any life ≥ 14 s that entered its last fight with 150+, dealt < 100 in it, no frag in it, not a
powerup death (this catches the long productive life that ends by throwing its stack away; 49% of the top's stack losses and 38% of
the field's end otherwise-productive lives).

---

## 2. Deaths per game and the class mix

### 2a. Pooled (enemy kills per player-game)

| class | TOP share | TOP /game | FIELD share | FIELD /game | FIELD/TOP | same-team FIELD/TOP |
|---|---|---|---|---|---|---|
| spawn_nothing | 29.0% | 14.17 | 32.6% | 18.81 | 1.33 | 1.40 |
| spawn_scratch | 10.5% | 5.10 | 9.5% | 5.46 | 1.07 | |
| spawn_item | 3.5% | 1.73 | 2.9% | 1.67 | 0.96 | 0.98 |
| spawn_trade | 9.7% | 4.72 | 7.8% | 4.52 | 0.96 | 0.99 |
| productive | 16.3% | 7.95 | 12.6% | 7.28 | 0.92 | 0.92 |
| stack_wasted | 1.3% | 0.65 | 1.8% | 1.03 | 1.58 | 1.63 |
| alone_2plus | 1.0% | 0.47 | 1.5% | 0.84 | 1.78 | 1.85 |
| mid_empty | 1.5% | 0.72 | 3.6% | 2.10 | 2.93 | 3.13 |
| mid_other | 5.7% | 2.78 | 8.4% | 4.83 | 1.73 | 1.83 |
| quad_fight | 4.3% | 2.10 | 4.5% | 2.58 | 1.23 | |
| quad_victim | 14.5% | 7.09 | 13.5% | 7.78 | 1.10 | 1.10 |
| held_quad | 2.6% | 1.29 | 1.3% | 0.73 | 0.56 | |
| **all enemy deaths** | | **48.82** | | **57.71** | **1.18** | **1.22** |
| MEANINGLESS | 16.2% | 7.93 | 19.2% | 11.08 | 1.40 | 1.48 |
| spawn_nothing while locked | 9.5% | 4.66 | 9.7% | 5.62 | 1.21 | |
| spawn_nothing, not locked, enemy powerup up | 3.2% | 1.58 | 3.7% | 2.11 | 1.34 | |
| empty life, any length | 39.6% | 19.32 | 46.3% | 26.72 | 1.38 | 1.45 |
| STACK LOST (flag) | 2.9% | 1.44 | 3.2% | 1.85 | 1.28 | 1.30 |
| … killer smaller than him | 2.3% | 1.13 | 2.5% | 1.44 | 1.28 | |
| … he had no RL/LG | 1.8% | 0.89 | 2.2% | 1.27 | 1.43 | |

"Same-team" = 2,367 team-games in which a top and a field player were teammates; the ratios survive, so this is not a
team-quality artefact.

Where the field's 8.9 extra deaths come from: spawn_nothing +4.6, mid_other +2.0, mid_empty +1.4, quad_victim +0.7,
quad_fight +0.5, stack_wasted +0.4, alone_2plus +0.4, spawn_scratch +0.4; the top has *more* productive (+0.7), held_quad (+0.6),
spawn_trade and spawn_item deaths. Empty-output classes add up to 9.2 — the whole gap and a bit more.

Non-rostered players (2,044 player-games): 51.7 deaths/game, 17.3% meaningless, 132 damage per life — between the two groups,
as expected for a roster ranked by wins above replacement.

### 2b. Per map

| map | grp | games | deaths/game | chained | MEANINGLESS /game | spawn_item | spawn_trade | productive | stack_wasted | STACK LOST /game | quad_victim | quad_fight |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dm3 | TOP | 1326 | 41.0 | 61% | 6.33 | 3.3% | 8.8% | 18.5% | 1.2% | 1.18 | 15.9% | 2.2% |
| dm3 | FIELD | 1500 | 49.6 | 59% | 8.69 | 2.7% | 6.9% | 13.7% | 1.6% | 1.50 | 15.0% | 2.1% |
| dm2 | TOP | 1239 | 50.8 | 69% | 8.58 | 4.9% | 8.1% | 15.6% | 2.2% | 2.16 | 15.5% | 4.2% |
| dm2 | FIELD | 1411 | 59.3 | 69% | 11.93 | 4.3% | 6.9% | 13.0% | 3.0% | 2.97 | 14.3% | 4.2% |
| e1m2 | TOP | 886 | 53.6 | 66% | 8.74 | 1.2% | 12.5% | 15.1% | 0.4% | 0.64 | 12.7% | 5.1% |
| e1m2 | FIELD | 1016 | 63.8 | 66% | 12.48 | 0.9% | 10.3% | 10.7% | 0.5% | 0.69 | 11.7% | 6.0% |
| schloss | TOP | 920 | 52.7 | 68% | 8.58 | 4.4% | 9.9% | 15.8% | 1.2% | 1.61 | 13.5% | 6.0% |
| schloss | FIELD | 962 | 61.6 | 68% | 12.07 | 3.3% | 7.7% | 12.9% | 1.6% | 1.96 | 12.4% | 6.1% |

dm3 is the slow map (41–50 deaths, 60% chained); dm2 is where stack is lost (two reds, 2.2–3.0 stack losses per game, 22% of top
deaths and 19% of field deaths began the last fight with 150+); e1m2 has no red and almost no stacked deaths (0.6–0.7 per game),
so there the whole gap is empty spawn lives (8.7 vs 12.5 per game) and short trades (12.5% vs 10.3%).

### 2c. Per player (all maps; per map in `death_value_out.md` §5i)

| player | grp | games | deaths/game | chained | MEANINGLESS /game | STACK LOST /game | mid_empty | productive | dmg/life | items/life |
|---|---|---|---|---|---|---|---|---|---|---|
| bogojoker | TOP | 262 | 42.6 | 64% | 5.79 | 1.13 | 1.1% | 19.4% | 259 | 0.61 |
| zorak | TOP | 100 | 39.1 | 59% | 5.17 | 1.37 | 1.5% | 20.8% | 220 | 0.66 |
| sane | TOP | 219 | 50.2 | 67% | 7.45 | 1.26 | 1.2% | 16.6% | 193 | 0.51 |
| chris | TOP | 214 | 47.2 | 65% | 6.65 | 1.02 | 1.2% | 18.4% | 190 | 0.54 |
| blaze | TOP | 336 | 42.7 | 62% | 6.51 | 1.46 | 1.5% | 18.4% | 199 | 0.59 |
| yeti | TOP | 630 | 49.8 | 67% | 8.12 | 1.39 | 1.2% | 15.9% | 185 | 0.55 |
| blood_dog_d_p | TOP | 1261 | 51.3 | 67% | 8.28 | 1.59 | 1.5% | 15.7% | 172 | 0.56 |
| war | TOP | 671 | 46.4 | 66% | 8.34 | 1.51 | 1.8% | 16.1% | 162 | 0.53 |
| dusty | TOP | 365 | 51.9 | 67% | 8.51 | 1.36 | 1.7% | 15.3% | 147 | 0.45 |
| coj | TOP | 313 | 53.5 | 68% | 10.00 | 1.56 | 1.6% | 14.2% | 150 | 0.50 |
| viag | FIELD | 206 | 44.7 | 60% | 6.80 | 1.59 | 2.4% | 18.0% | 159 | 0.56 |
| nico | FIELD | 509 | 53.1 | 67% | 9.26 | 1.67 | 2.1% | 15.8% | 146 | 0.47 |
| gflip | FIELD | 185 | 55.0 | 64% | 10.16 | 1.56 | 3.1% | 13.6% | 117 | 0.35 |
| omicron | FIELD | 148 | 49.4 | 64% | 9.62 | 1.86 | 3.4% | 13.7% | 119 | 0.43 |
| namtsui | FIELD | 835 | 53.2 | 65% | 9.31 | 1.64 | 2.3% | 14.5% | 123 | 0.38 |
| cronus | FIELD | 810 | 54.8 | 65% | 10.34 | 2.02 | 2.8% | 14.2% | 112 | 0.45 |
| pharm | FIELD | 121 | 54.2 | 63% | 9.56 | 2.07 | 2.1% | 15.2% | 122 | 0.47 |
| pred | FIELD | 381 | 56.2 | 62% | 10.39 | 2.02 | 4.1% | 12.6% | 92 | 0.38 |
| foobhar | FIELD | 230 | 60.8 | 66% | 11.99 | 1.59 | 3.1% | 12.1% | 97 | 0.36 |
| phylter | FIELD | 181 | 61.1 | 66% | 11.45 | 2.19 | 2.6% | 13.0% | 102 | 0.43 |
| stedanko | FIELD | 89 | 55.8 | 65% | 11.19 | 1.98 | 4.0% | 11.5% | 93 | 0.37 |
| ledge | FIELD | 473 | 65.0 | 68% | 12.84 | 1.54 | 3.1% | 11.7% | 89 | 0.28 |
| schotty | FIELD | 582 | 72.2 | 68% | 16.43 | 2.34 | 6.8% | 6.7% | 49 | 0.20 |
| evalcat | FIELD | 139 | 64.1 | 61% | 14.46 | 1.71 | 9.7% | 7.5% | 55 | 0.21 |

Chained share is 59–68% for everyone and separates nobody (doctrine §7, 2026-10-16). Meaningless deaths per game and damage per
life do: bogojoker/zorak/chris at 5–7 per game and 190–260 damage per life; coj at 10 per game is at field level; viag (6.8, 159)
is the field's top-shaped player; schotty and evalcat die empty 14–16 times a game and return 49–55 damage per life.

---

## 3. What a death buys

| per enemy-kill death (= per life) | TOP | FIELD | TOP per map dm3/dm2/e1m2/schloss | FIELD per map |
|---|---|---|---|---|
| mean life (s) | 20.3 | 17.2 | 24.1 / 18.9 / 19.0 / 18.9 | 20.3 / 16.2 / 15.8 / 16.1 |
| median life (s) | 8.6 | 9.1 | 9.9 / 7.5 / 9.1 / 8.2 | 10.8 / 7.8 / 9.2 / 8.6 |
| damage dealt | 178 | 103 | 173 / 191 / 163 / 181 | 99 / 111 / 96 / 103 |
| damage to 150+ enemies | 47 | 25 | 44 / 68 / 18 / 50 | 23 / 37 / 10 / 26 |
| frags | 1.11 | 0.60 | 1.12 / 1.07 / 1.17 / 1.11 | 0.61 / 0.58 / 0.62 / 0.60 |
| stacked frags (victim entered with 150+) | 0.15 | 0.07 | 0.14 / 0.22 / 0.07 / 0.17 | 0.06 / 0.10 / 0.03 / 0.07 |
| lives with any frag | 32% | 27% | | |
| lives that took RA/YA/MH/RL/LG/powerup | 28.5% | 22.7% | 31 / 32 / 18 / 30 | 25 / 29 / 12 / 24 |
| lives that took RA/MH/quad/pent/ring | 16.3% | 11.1% | 19 / 19 / 9 / 17 | 13 / 14 / 5 / 12 |
| items per life | 0.69 | 0.42 | 0.79 / 0.81 / 0.37 / 0.75 | 0.46 / 0.54 / 0.18 / 0.45 |
| empty lives (<50 dmg, no frag, no item) | 39.6% | 46.3% | 38 / 43 / 37 / 39 | 45 / 48 / 45 / 47 |
| died with RL in hand | 18.0% | 12.8% | | |
| entered the last fight with 150+ | 15.4% | 11.8% | 15 / 22 / 7 / 17 | 11 / 19 / 4 / 12 |
| alone in the final 5 s | 41.6% | 44.0% | | |
| faced 2+ in the final 5 s | 56.9% | 50.8% | | |
| killer had RL or LG | 67.8% | 64.6% | | |
| killer was a fresh spawn (<14 s) | 24.3% | 26.4% | | |
| killed inside 6 s of spawning | 36.6% | 34.6% | | |

Life-length distribution and what each bucket bought:

| life | TOP share | FIELD share | TOP dmg | FIELD dmg | TOP items | FIELD items | TOP frags | FIELD frags |
|---|---|---|---|---|---|---|---|---|
| 0–6 s | 36.6% | 34.6% | 32 | 26 | 0.02 | 0.02 | 0.05 | 0.04 |
| 6–14 s | 29.5% | 30.8% | 68 | 54 | 0.15 | 0.12 | 0.26 | 0.21 |
| 14–30 s | 17.9% | 20.5% | 131 | 95 | 0.60 | 0.42 | 0.74 | 0.53 |
| 30–60 s | 8.8% | 9.3% | 320 | 211 | 1.72 | 1.22 | 2.04 | 1.41 |
| 60–120 s | 4.7% | 3.6% | 804 | 552 | 3.58 | 2.81 | 5.70 | 3.99 |
| 120 s+ | 2.6% | 1.2% | 2,205 | 1,461 | 8.21 | 6.16 | 17.0 | 11.4 |

The top is spawn-killed slightly *more* (36.6% of deaths inside 6 s) — it is on the winning side more often, so the enemy is
stacked and camping spawns more often. Its lives are not longer at the median; they do more at every length and are far more likely
to become the 60 s+ lives that decide maps.

---

## 4. Win-probability cost per death, by class (live games, percentage points)

| class | TOP n | dp_frag | dp_cost | dp_net | FIELD n | dp_frag | dp_cost | dp_net | TOP cost /game | FIELD cost /game |
|---|---|---|---|---|---|---|---|---|---|---|
| spawn_nothing | 36,813 | −0.87 | −0.86 | −0.36 | 55,785 | −0.85 | −0.82 | −0.38 | −7.3 | −9.4 |
| spawn_scratch | 14,064 | −0.87 | −0.86 | +0.96 | 17,045 | −0.86 | −0.83 | +1.01 | −2.8 | −2.9 |
| spawn_item | 4,691 | −0.84 | −3.35 | −1.48 | 4,993 | −0.81 | −3.37 | −1.91 | −3.6 | −3.5 |
| spawn_trade | 13,154 | −0.88 | −0.91 | +2.23 | 14,339 | −0.87 | −0.86 | +2.07 | −2.8 | −2.5 |
| productive | 22,236 | −0.90 | −4.52 | −0.12 | 22,923 | −0.88 | −3.89 | −0.38 | −23.2 | −18.3 |
| stack_wasted | 1,689 | −0.83 | −4.49 | −3.55 | 3,116 | −0.83 | −4.32 | −3.48 | −1.8 | −2.8 |
| alone_2plus | 1,331 | −0.96 | −1.06 | +1.15 | 2,715 | −0.93 | −0.94 | +0.90 | −0.3 | −0.5 |
| mid_empty | 1,899 | −0.96 | −0.79 | −0.35 | 6,298 | −0.92 | −0.65 | −0.27 | −0.4 | −0.8 |
| mid_other | 7,757 | −0.94 | −0.84 | +0.89 | 15,458 | −0.91 | −0.77 | +0.71 | −1.5 | −2.4 |
| quad_fight | 5,558 | −0.89 | −2.39 | +0.13 | 7,918 | −0.87 | −1.73 | +0.02 | −3.1 | −2.8 |
| quad_victim | 18,870 | −0.87 | −2.13 | −0.75 | 23,311 | −0.86 | −1.79 | −0.83 | −9.3 | −8.6 |
| held_quad | 3,648 | −0.89 | −6.29 | −0.72 | 2,402 | −0.89 | −5.54 | −1.36 | −5.3 | −2.7 |
| STACK LOST (flag) | | | −5.15 | −4.08 | | | −4.81 | −3.86 | | |
| all | 131,859 | −0.88 | −2.02 | +0.04 | 176,563 | −0.87 | −1.59 | −0.08 | −61.5 | −57.5 |

Reading it:
- A frag alone is worth about −0.87 pp in a live game, the same for everyone. What makes a death expensive is what went with it:
  the stack, the RL, the quad. The model's exchange rates (pooled coefficients): 100 eff of team stack = 0.118 logit; an RL = 0.174
  (≈ 150 eff); an LG = 0.128 (≈ 110 eff); a frag = 30 eff with 15 min left, 49 eff at 5 min, 84 at 2 min, 119 at 1 min.
  Early in a map, stack and guns matter more than the frag; in the last two minutes the frag is everything.
- The two classes that are pure loss: **stack lost** (−5.2 cost, −4.1 net) and **held_quad** (−6.3). Spawn deaths cost the frag and
  nothing else. `spawn_trade` is net positive (+2.2) and `spawn_scratch` nearly so (+1.0): a shotgun spawn that lands two or three
  hits before dying has paid for itself in the model's terms.
- The top loses *more* win probability per game to its deaths in total (−61.5 vs −57.5) because it carries more into fights
  (productive deaths −4.5 pp each, 8 a game). Netted against what those fights dealt, both groups land near zero per death; the
  difference between them is the 8.9 extra empty deaths, each −0.8 pp.
- Which classes the top avoids most, by per-game ratio (field/top): mid_empty 2.9×, alone_2plus 1.8×, mid_other 1.7×, stack_wasted
  1.6×, meaningless 1.4×, quad_fight 1.2×, quad_victim 1.1×. It does *not* avoid spawn_item, spawn_trade or productive deaths (≤1.0×),
  and dies holding quad 1.8× more often (volume: it holds quad more; its quad lives are also longer, 45 s vs 34 s median, 5.7 vs 3.5
  frags).

---

## 5. Locked vs not locked

| state | grp | share of deaths | chained | killed <6 s | item in first 14 s | 50+ dmg in first 14 s | RL in first 14 s | YA/RA/MH in first 14 s | dmg/life | frags/life | dp_cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LOCKED | TOP | 26.3% | 73.8% | 45.5% | 18.5% | 33.3% | 5.1% | 13.2% | 113 | 0.58 | −1.72 |
| LOCKED | FIELD | 23.9% | 73.7% | 43.9% | 13.8% | 24.1% | 3.2% | 10.3% | 65 | 0.31 | −1.39 |
| not locked | TOP | 73.7% | 63.3% | 33.4% | 22.3% | 42.9% | 6.3% | 16.1% | 201 | 1.30 | −2.10 |
| not locked | FIELD | 76.1% | 62.8% | 31.7% | 16.9% | 34.1% | 4.4% | 12.4% | 114 | 0.69 | −1.63 |

Under a lock the two groups are indistinguishable on survival — chained 73.8% vs 73.7%, and per map the share of locked lives
that reach 14 s is dm3 31.8 vs 33.4%, dm2 22.9 vs 22.6%, e1m2 27.0 vs 25.7%, schloss 24.2 vs 23.9%. What differs is what the life
does before it ends. Locked survivors (lives that reached 14 s) who took an item inside those 14 s: dm3 48% vs 33%, dm2 65% vs
54%, e1m2 25% vs 14%, schloss 57% vs 38%; who dealt 50+ inside 14 s: dm3 34% vs 23%, dm2 39% vs 28%, e1m2 47% vs 34%, schloss
50% vs 34%. The first item under a lock is still "nothing" for 75–85% of everyone (schloss top 75%, field 82%; e1m2 80% vs 85%);
the top's edge is a few points of YA (schloss 8.3% vs 5.2%), RL (5.9% vs 3.8%) and RA on dm2 (5.3% vs 3.8%).

Where locked spawns survive (area at +10 s, share reaching 14 s, both groups): dm3 water.LG 69%, SNG/SNG.MH 62–67%, water.rox
70–76% — Ring 15–18%, SNG.tele 15–17%; dm2 secret 47–50%, floating 52%, GL 60–68% — NG 12–13%, water 8–9%; e1m2 GA 52–56%,
water.GA 50%, water.RL 55%, YA.tele 57–59% — Quad 13%, GL.Quad 10–11%; schloss RA 49–51%, cemetary.Ring 46–52%, RA.window 40% —
Quad.low 17%, cathedral.SSG 15–16%, cemetary.tele 17%. The map decides this, not the player: the top and the field have the same
area table. (The doctrine's flood caveat applies: a team may be sending spawns into Ring/NG/Quad on purpose.)

---

## 6. Same state, same death rate: the hazard view

For every 10 s sample where a rostered player was alive, did he die inside the next 10 s? (`stacked_hazard.py`)

| state | TOP samples | TOP P(die in 10 s) | FIELD samples | FIELD P(die) | share of the group's time in this state TOP / FIELD |
|---|---|---|---|---|---|
| all | 507,411 | 30.7% | 559,002 | 37.5% | |
| unstacked, no RL/LG | 221,861 | 49.8% | 332,435 | 49.5% | 44% / 59% of alive time |
| unstacked, RL or LG | 116,566 | 20.5% | 93,634 | 25.1% | 23% / 17% |
| 150+, no RL/LG | 40,045 | 23.4% | 48,246 | 24.7% | 8% / 9% (24% / 36% of stacked time) |
| 150+, RL or LG | 128,939 | 9.4% | 84,687 | 11.5% | 25% / 15% (76% / 64% of stacked time) |
| 150+, alone in the area | 140,134 | 12.8% | 109,968 | 16.6% | 83% / 83% of stacked time |
| 150+, teammate in the area | 28,850 | 12.4% | 22,965 | 14.9% | 17% / 17% |
| 150+, enemy powerup up | 24,561 | 20.4% | 20,431 | 25.8% | 15% / 15% |
| 150+, locked | 9,662 | 29.8% | 7,758 | 34.1% | 6% / 6% |

Per map, 150+ without a gun dies at dm3 18 vs 20%, dm2 27 vs 28%, e1m2 18 vs 20%, schloss 25 vs 26%; with a gun at 8 vs 10%,
10 vs 12%, 8 vs 10%, 11 vs 13%. The state explains the death rate; the group barely does. The group explains the *time spent* in
each state: the field is a shotgun spawn 59% of its alive time (top 44%), and when it does hold 150+ it holds it without a gun
36% of the time (top 24%). A teammate in the same area at the sample does not lower the hazard for stacked players (12.4 vs 12.8%
for the top) — the 10 s area sample is too coarse to say more than that.

---

## 7. Coachable statements, and the alternative for each meaningless class

Each statement compares a player with survivors in the same state on the same map, as the doctrine asks. Tags: P = perception,
D = decision, E = execution.

1. **[D] Get the gun before you carry the armor.** 62% of the top's and 69% of the field's stack-lost deaths were a 150+ player
   with no RL or LG; the fight took 2.8 s and he dealt 46 (top) / 42 (field). A 150+ player with a gun dies in the next 10 s at
   9–12%; without one at 23–25% — on every map, for both groups. The field holds its stack unarmed 36% of the time, the top 24%.
   Cost of each of these deaths: −5.2 pp (−4.1 after what he dealt), 1.85 a game for the field, 1.44 for the top, and dm2 is where
   it happens (3.0 vs 2.2 a game; low.RL, NG, big, high.RL).
2. **[D] The spawn that buys nothing is the whole gap.** Meaningless deaths (not locked, no enemy quad up, under 14 s, under 50
   damage, nothing taken): 11.1 a game for the field vs 7.9 for the top, −0.85 pp each in a live game. Survivors of the same
   spawn state (not locked, no powerup, lived 14 s+) took an item inside 14 s 44.6% (top) vs 32.9% (field), YA/RA/MH 34% vs 26%,
   RL 12.6% vs 8.3%, and dealt 50+ inside 14 s 48% vs 36%. Per map the survivors' item rate is dm3 43% vs 29%, dm2 61% vs 51%,
   e1m2 22% vs 13%, schloss 52% vs 40%. The alternative is a route, not a fight.
3. **[D/P] Where to be 10 s after a free spawn** (share of not-locked lives reaching 14 s, by area at +10 s; same for both groups):
   dm3 water.tunnel 80–82%, water.rox 73–81%, SNG 74–81% vs RA.tunnel 31–36%, SNG.tele 29–32%, RA.rox 27–36%;
   dm2 GL 77–83%, floating 59–67%, high.RL 59–61% vs water 20–21%, low.button 23–24%, Quad.button 24%, NG 25%;
   e1m2 GL.SNG 62–69%, MH.rox 60–66%, MH.SNG 59% vs Quad 27%, GL.Quad 27–29%, Quad.box 16–20%, Quad.stairs 30%;
   schloss RA 68–70%, cemetary.Ring 56–63%, cathedral.YA 49–54% vs cathedral.SSG 27–28%, yard.Pent 25–26%, yard.roof 19–26%.
   These are where survivors *are*, which is partly where the enemy is not; read them with the flood doctrine in mind.
4. **[D] The 18-second walk that ends with nothing** (mid_empty: 14 s+ alive, under 50 damage, nothing taken): 2.1 a game for the
   field vs 0.7 for the top (2.9×, 3.1× as teammates). Median 17–19 s, 80% took nothing at all (not even GA/SNG/GL), 45% alone,
   killer had RL/LG 67–74%, mean eff into the last fight 85 (already chipped before it). The same 14–30 s in a surviving top life
   buys 0.6 items and 131 damage. The decision is at second 5: commit to an item route or to a teammate; drifting is the third
   option and it is the one that dies empty. Pred (2.5–3.0 a game on dm3/e1m2), schotty (6.3 on dm3) and evalcat (7–8 on dm3/e1m2)
   are the extreme cases.
5. **[E] Stacked and alone against one enemy is where the field's aim shows.** Of lives that entered the last fight with 150+ and
   died, "alone vs 1" is 20% (top) / 24% (field) of them; the top dealt 100+ in 52% of those fights, the field in 42%
   (mean 129 vs 103 damage); with a teammate vs 1: 45% vs 32%. Fight length is the same (2.8 s median), so this is the first exchange.
   The killer was smaller than the victim in 78% of all stack losses, for both groups.
6. **[D] Do not coach spawn deaths down; coach them to buy something.** spawn_item (1.73 vs 1.67 a game; YA 40%, RL 34%, MH 18%,
   RA 7%) and spawn_trade (4.7 vs 4.5; a frag in 66–69% of them, +2.2 pp net each) are the same for both groups, and 36.6% of the
   top's deaths are inside 6 s of spawning vs 34.6% of the field's. A fresh unarmed spawn dies inside 10 s at 49.8% vs 49.5% —
   there is no skill in surviving it, only in what the 6–14 s buy (top 68 damage, field 54; item 15% vs 12%).
7. **[P] Enemy quad is a cost of doing business, equal for both.** Killed by the powerup holder: 7.1 vs 7.8 a game (14.5% vs
   13.5% of deaths), 70% of those lives under 14 s, −2.1 pp each (−0.8 net). Where the top differs is the stacked player's
   behaviour while the enemy has it: hazard 20.4% vs 25.8% per 10 s, and the top's quad-victim lives had dealt 131 damage before
   dying vs 74 — they were spending the stack, not hiding it.
8. **[D] Under a lock, the 14 seconds are the unit, not survival.** Everyone chains 74% and reaches 14 s at the same rate per map.
   The top's locked lives take an item inside 14 s 18.5% vs 13.8%, deal 50+ inside 14 s 33% vs 24%, and return 113 vs 65 damage
   per life. On schloss the first item under a lock is YA for 8.3% of top lives vs 5.2%, RL 5.9% vs 3.8%; on e1m2 GA 5.3% vs 3.7%
   and SNG/GL 7.0% vs 6.3% — small numbers, but they are the only lever the data shows under a lock besides the area table in §5.
9. **[D] Alone into two is not what separates the groups; output is.** Deaths alone vs 2+ (any length) are 7.1 vs 7.8 a game
   (14.5% vs 13.5% of deaths); the top dealt 90 in those fights, the field 70, and fragged in 28% vs 23.5%. The model nets these at
   +0.5 / +0.3 pp — a 1v2 that lands damage on two stacked enemies is not a bad death. The low-output version (alone_2plus class,
   0.47 vs 0.84 a game) is.
10. **[D] Dying with quad is the most expensive single death (−6.3 pp) and the top does it more** (1.29 vs 0.73 a game) because it
   holds quad more; its quad lives last 45 s vs 34 s and make 5.7 vs 3.5 frags. For a quad holder the coaching number is the
   30-second clock, not the death.

---

## 8. Caveats

- **10 s resolution.** Lock state, the team stacks behind the win-probability model, the area at +10 s and "teammate in the same
  area" are all read from 10 s samples; a player can move rooms inside that. Deaths are at ms resolution.
- **Team quality.** Top players sit on better teams. The share of their deaths that come from locked spawns is nevertheless a
  little higher (26.3% vs 23.9%) because they die less in free play, so lock exposure alone does not explain the gap. Three
  controls: the same-team pairing (§2a last column, 2,367 team-games), the lock split (§5) and p(win) buckets
  (`death_value_out.md` §6b: the field's meaningless share is 2.6–3.6 points above the top's in every bucket from 0.0–0.1 to
  0.9–1.0). The gaps survive all three.
- **Definition sensitivity.** The meaningless share moves with the thresholds — 10–11% of deaths (under 25 damage), 16–19% (under
  50, used here), 23–26% (under 100); the per-game field/top ratio stays 1.28–1.55 across 14 s / 10 s / 20 s and 25 / 50 / 100.
  "Productive" (200 damage or 2 frags or item + 100) and "stacked" (150 eff) are judgement calls; stack_traded nearly vanishes under
  the chosen precedence because a stacked life that trades 100+ is almost always "productive" already.
- **"Alone"** is read from damage events: a teammate who was in the room but never fired counts as absent. **"Killer bigger"** uses
  the killer's eff at the kill, after the victim's damage, so it understates how often the killer started bigger.
- **Win probability** is the frag/stack/weapon/powerup model fitted on 10 s team states; it has no position, timing or denial term,
  so `dp_net` understates item-taking lives (a stolen YA is a 20 s denial the model cannot see) and the per-game sums are sums of
  marginal values, not a true decomposition of the map result.
- **Roster weight.** blood_dog_d_p is 29% of top player-games and yeti + war another 30%; bogojoker, zorak and chris, the players
  with the cleanest death profiles, are 13%. The "top" averages are closer to BD than to bogojoker. Per-player rows are in §2c
  and per map in `death_value_out.md` §5i.
- Match-start telefrags (t < 1 s) are dropped; team kills and suicides (3.8 vs 4.7 a game) are reported but not classified.

## Files

- `research_death_value.md` — this report.
- `death_value_build.py` → `deaths.csv` (649,183 rows, one per death, 60 columns; 41 s runtime).
- `death_value_analyze.py` → `death_value_out.md` (all tables, including per-player-per-map §5i and the robustness checks §6).
- `stacked_hazard.py` → `stacked_hazard_out.md` (sample hazards, pooled and per map).

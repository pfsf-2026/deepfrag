# Fight entry: how the best NA 4on4 players start fights, and what the 30 s before look like

DeepFrag research note — TB4 4on4 (dm3, dm2, e1m2, schloss), 8-player games since 2025-01-01. 1,415 games, 957,094 pairwise fights.
TOP = bogojoker, zorak, sane, chris, blaze, yeti, blood_dog_d_p, war, dusty, coj (10 players, 4,378 player-games).
FIELD = viag, nico, gflip, omicron, namtsui, cronus, pharm, pred, foobhar, phylter, stedanko, ledge, schotty, evalcat (14 players, 4,889 player-games).
Scripts: `fight_entry_extract.py` (builds `fight_entry.sqlite`, one row per fight) and `fight_entry_report.py` (all tables; full output in `fight_entry_tables.md`), next to this file.

## The five things that matter

1. **TOP players start more fights and win the ones they start: 98 starts per game vs 73, 54% of their fights started vs 46%, and a kill/death split of 44%/29% on their starts vs 35%/37%.** They are alive the same number of minutes (19.2 vs 18.9), so the rate is real: 5.1 starts per alive minute vs 3.9. [decision]
2. **The gap is their own state, not their target choice.** At the first hit TOP players hold RL 43% of the time (FIELD 27%), have 150+ eff 34% (24%), are 60 s+ into a life 24% (13%), and are inside 10 s of a spawn 39% (48%). Every cue about the *enemy* — fresh spawn, just took an armor, just killed, has RL, 200+ eff — is identical to the point (30/28, 35/34, 38/38, 35/35, 19/19). The same holds inside neutral games, so it is not a "better team" artefact. [decision]
3. **The RL gap is economy, not selectivity.** TOP players carry RL for 44% of their alive time and start 43% of their fights with it — ratio 1.0. The FIELD carries it 29% and starts 27% — also ~1.0 (namtsui 0.81, ledge 0.77: they start *less* when armed). Nobody waits for the RL before engaging; the TOP simply spend more of their lives holding it, because they die less (53 vs 63 deaths per game) and pick it up more. [decision/execution]
4. **In spawn-fights TOP and FIELD are the same player.** When the starter is <6 s off a spawn against a built enemy both groups go 20% kill / 55% die. The TOP edge is entirely in built lives (46/25 vs 37/35 when neither is fresh) and in finishing fresh spawns (66/11 vs 55/18). The 30 s before a TOP start more often contains an armor or mega (54% vs 41%) and a kill (49% vs 37%). [decision]
5. **When hit first, TOP players answer harder, they do not disengage more.** 59% put damage back inside 5 s (FIELD 51%), averaging 62 damage (40), killing the starter 28% (19%) and dying 47% (58%). The share that takes no damage back and survives is the same (16% vs 15%). Even when 60+ eff behind they hit back 42% of the time vs 34% and die 79% vs 84%. [execution]

Everything below is the evidence, then ten coachable statements, then the caveats.

## 0. Definitions

- **Fight**: damage/frag events between one pair of enemies with no gap over 4 s (the `player_fights` rule); the cluster also closes at a frag between the pair or when either player respawned in between. The **starter** is whoever landed the first hit; the other player **accepted**. Stacks (`eff` = health + armour-weighted) are taken from the first event, before the hit. **Edge** = starter eff − target eff; ahead ≥ +60, behind ≤ −60, else even.
- **Outcome for the starter**: *kill* = fragged that enemy inside the fight; *die* = the starter died to anyone between the first hit and 1.5 s after the last exchange. 15.6% of "fights" are a single hit and 23.7% exchange under 50 damage; the 50+ damage subset is reported alongside the full set.
- **Lock state**: `state10s` margin = (enemy stack − ours) + 100 × (enemy RLs − ours) + 100 × (enemy RAs − ours) at the 10 s sample containing the first hit. *Locked* = margin in the worst quarter for that map (dm3 ≥ 344, dm2 ≥ 317, e1m2 ≥ 155, schloss ≥ 285), *dominant* = the mirror, else *neutral*. The 85th-percentile thresholds from `lock_spawn.py` give the same ordering (section 1c).
- **Pre-window**: the starter's item takes in the 30 s before the hit (`item_takes`), eff at the 10 s samples ~30 s and ~10 s before (same life only), whether a teammate had damaged the same enemy in the previous 10 s (*joining*) or not (*opening*), the enemy's takes in the last 20 s, kills by either player in the last 10 s, and the starter's area at the 10 s sample before the hit.

## 1. Starts, share of fights started, edge buckets and outcomes

### 1a. Pooled and per map (all fights; "kill / die" = starter's outcome)

| map | group | player-games | starts/game | accepted/game | share started | ahead / even / behind | all starts | ahead | even | behind | accepted (kill / die) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pooled | TOP | 4,378 | 98.1 | 83.7 | 54% | 32 / 45 / 23 | 44% / 29% | 72% / 5% | 40% / 31% | 12% / 59% | 28% / 47% |
| pooled | FIELD | 4,889 | 73.2 | 87.0 | 46% | 25 / 50 / 26 | 35% / 37% | 67% / 8% | 33% / 37% | 8% / 65% | 19% / 58% |
| dm3 | TOP | 1,326 | 83.4 | 71.7 | 54% | 34 / 43 / 24 | 44% / 28% | 71% / 5% | 40% / 29% | 12% / 57% | 27% / 45% |
| dm3 | FIELD | 1,501 | 62.3 | 75.1 | 45% | 25 / 48 / 27 | 35% / 35% | 67% / 7% | 34% / 34% | 8% / 63% | 19% / 56% |
| dm2 | TOP | 1,239 | 102.6 | 86.3 | 54% | 35 / 39 / 26 | 44% / 29% | 71% / 6% | 40% / 30% | 14% / 58% | 28% / 46% |
| dm2 | FIELD | 1,411 | 75.2 | 90.4 | 45% | 30 / 42 / 29 | 35% / 36% | 65% / 9% | 33% / 36% | 9% / 65% | 19% / 57% |
| e1m2 | TOP | 888 | 101.2 | 88.0 | 53% | 25 / 58 / 17 | 46% / 32% | 78% / 6% | 42% / 34% | 12% / 66% | 31% / 49% |
| e1m2 | FIELD | 1,016 | 78.7 | 90.5 | 47% | 18 / 64 / 19 | 36% / 41% | 73% / 9% | 34% / 41% | 8% / 71% | 20% / 62% |
| schloss | TOP | 920 | 110.5 | 94.0 | 54% | 33 / 44 / 24 | 42% / 29% | 70% / 5% | 38% / 30% | 11% / 58% | 27% / 47% |
| schloss | FIELD | 961 | 81.3 | 97.0 | 46% | 25 / 48 / 26 | 34% / 36% | 67% / 7% | 31% / 36% | 7% / 64% | 18% / 58% |

Restricting to fights with 50+ damage exchanged: TOP 77 starts/game, 54% started, 49% / 33%; FIELD 54 starts/game, 45% started, 39% / 44%. Ahead starts go 77/6 vs 73/9, even 48/35 vs 40/44, behind 14/65 vs 9/74. The picture does not move.

Reading it: the map changes the stack economy (e1m2 has no RA, so only 21% of starts are ahead-by-60 and 58-64% are even) but not the TOP–FIELD gap, which is +8 to +10 points on share started and +9 to +11 on kill rate on every map. The TOP win more from *every* edge bucket, including behind (12% vs 8%, with 59% vs 65% deaths), so the advantage is not only in choosing when to start.

### 1b. By lock state of the starter's team (75th-percentile thresholds)

| group | team state | starts | share started | RL at hit | ahead 60+ | kill | die |
|---|---|---|---|---|---|---|---|
| TOP | dominant | 110,449 | 53% | 68% | 52% | 62% | 13% |
| TOP | neutral | 212,421 | 54% | 41% | 30% | 43% | 29% |
| TOP | locked | 106,158 | 55% | 20% | 15% | 26% | 47% |
| FIELD | dominant | 87,410 | 46% | 48% | 41% | 50% | 22% |
| FIELD | neutral | 178,817 | 46% | 25% | 23% | 35% | 37% |
| FIELD | locked | 91,255 | 45% | 12% | 12% | 21% | 52% |

Two things. First, TOP and FIELD teams spend the same share of game time locked and dominant (TOP 24.7% / 25.4%, FIELD 25.1% / 24.9%; mean margin −5 vs +2), so in this sample the "top players are on better teams" effect is small: the roster is ranked by wins-above-replacement, not by team wins (blood_dog's teams win 40%, namtsui's 59%). Second, the TOP keep starting 54-55% of their fights under a lock — they do not go passive — and they still start with RL 20% of the time against 12%.

### 1c. Per player

| grp | player | games | starts/g | share started | ahead | behind | kill | die | RL at hit | 200+ eff | own spawn <10 s | enemy spawn <6 s | accepted: hit back | accepted: died |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TOP | bogojoker | 263 | 125 | 61% | 36% | 20% | 48% | 23% | 50% | 28% | 34% | 34% | 66% | 40% |
| TOP | zorak | 100 | 97 | 55% | 36% | 21% | 48% | 24% | 43% | 29% | 34% | 32% | 63% | 41% |
| TOP | chris | 214 | 96 | 53% | 32% | 22% | 47% | 28% | 42% | 25% | 38% | 31% | 61% | 44% |
| TOP | sane | 220 | 105 | 55% | 31% | 23% | 47% | 29% | 43% | 24% | 40% | 30% | 60% | 46% |
| TOP | blaze | 338 | 89 | 53% | 33% | 22% | 44% | 27% | 42% | 26% | 36% | 30% | 63% | 44% |
| TOP | coj | 313 | 87 | 49% | 32% | 23% | 44% | 31% | 44% | 24% | 41% | 30% | 58% | 51% |
| TOP | yeti | 630 | 104 | 55% | 32% | 23% | 44% | 29% | 44% | 25% | 40% | 29% | 60% | 46% |
| TOP | blood_dog_d_p | 1,263 | 99 | 53% | 31% | 24% | 43% | 30% | 42% | 25% | 41% | 28% | 58% | 48% |
| TOP | dusty | 366 | 92 | 53% | 29% | 24% | 42% | 32% | 39% | 22% | 42% | 31% | 57% | 51% |
| TOP | war | 671 | 93 | 54% | 32% | 22% | 41% | 30% | 40% | 26% | 40% | 29% | 56% | 47% |
| FIELD | viag | 206 | 78 | 50% | 31% | 22% | 44% | 28% | 39% | 23% | 37% | 30% | 58% | 49% |
| FIELD | nico | 509 | 87 | 51% | 30% | 23% | 42% | 35% | 35% | 23% | 43% | 28% | 55% | 51% |
| FIELD | gflip | 185 | 76 | 47% | 25% | 24% | 39% | 35% | 30% | 18% | 45% | 30% | 53% | 55% |
| FIELD | cronus | 810 | 69 | 43% | 28% | 25% | 38% | 34% | 34% | 20% | 45% | 28% | 52% | 55% |
| FIELD | omicron | 148 | 67 | 44% | 29% | 24% | 38% | 33% | 33% | 21% | 40% | 30% | 53% | 53% |
| FIELD | pharm | 121 | 80 | 50% | 26% | 26% | 35% | 36% | 32% | 18% | 46% | 27% | 57% | 57% |
| FIELD | foobhar | 230 | 76 | 46% | 23% | 27% | 34% | 39% | 25% | 15% | 50% | 28% | 49% | 59% |
| FIELD | namtsui | 835 | 83 | 51% | 24% | 26% | 34% | 35% | 26% | 17% | 48% | 29% | 56% | 54% |
| FIELD | phylter | 182 | 79 | 48% | 24% | 26% | 33% | 40% | 27% | 18% | 50% | 28% | 53% | 58% |
| FIELD | pred | 381 | 67 | 43% | 24% | 26% | 33% | 36% | 27% | 16% | 45% | 28% | 49% | 59% |
| FIELD | stedanko | 89 | 68 | 45% | 24% | 24% | 33% | 39% | 25% | 17% | 48% | 28% | 47% | 59% |
| FIELD | ledge | 473 | 81 | 48% | 21% | 27% | 31% | 42% | 19% | 13% | 55% | 29% | 51% | 62% |
| FIELD | schotty | 581 | 50 | 34% | 17% | 29% | 26% | 49% | 9% | 9% | 59% | 27% | 42% | 72% |
| FIELD | evalcat | 139 | 52 | 35% | 16% | 29% | 24% | 42% | 12% | 8% | 52% | 24% | 39% | 65% |

Standouts: **bogojoker** starts 61% of his fights and 125 per game, half of them with RL, and still dies in only 23% of them — the most aggressive and the safest starter in the data. **zorak** matches the kill/death line (48/24) on fewer starts. **viag** is the FIELD player who already looks like a TOP starter (44/28, RL 39%). At the other end, **schotty** and **evalcat** hold RL at the hit 9-12% of the time, start only a third of their fights, and die in 42-49% of the ones they start; 52-59% of their starts come inside 10 s of a spawn.

## 2. The 30 s before a start: TOP vs FIELD

### 2a. Pre-fight profile (pooled; TOP n = 429,263 starts, FIELD n = 357,704)

| condition at the first hit | bucket | TOP | FIELD | gap | everyone |
|---|---|---|---|---|---|
| RL in hand | decision | 43% | 27% | +16 | 35% |
| LG in hand (dm3 only has one: 25% vs 13% there) | decision | 6% | 3% | +3 | 5% |
| first hit is a rocket | execution | 34% | 24% | +11 | 29% |
| first hit is a shotgun | execution | 53% | 64% | −11 | 58% |
| 200+ eff | decision | 25% | 17% | +8 | 21% |
| 150+ eff | decision | 34% | 24% | +10 | 29% |
| under 100 eff | decision | 22% | 25% | −3 | 24% |
| ahead by 60+ | decision | 32% | 25% | +7 | 28% |
| behind by 60+ | decision | 23% | 26% | −3 | 24% |
| took RA/YA/MH ≤ 10 s before | decision | 38% | 35% | +2 | 37% |
| took RA/YA/MH ≤ 30 s before | decision | 54% | 41% | +14 | 47% |
| picked up RL/LG ≤ 30 s before | decision | 21% | 17% | +4 | 19% |
| took a health pack ≤ 10 s before | decision | 24% | 19% | +5 | 21% |
| quad or pent on | decision | 9% | 3% | +5 | 6% |
| own spawn < 10 s ago | decision | 39% | 48% | −8 | 43% |
| own spawn < 6 s ago | decision | 30% | 35% | −6 | 32% |
| alive 60 s+ (a built life) | decision | 24% | 13% | +10 | 19% |
| had just killed someone (10 s) | decision | 49% | 37% | +12 | 43% |
| joining: a teammate hit this enemy in the previous 10 s | perception | 61% | 63% | −2 | 62% |
| the enemy hit a teammate in the previous 10 s | perception | 74% | 75% | −1 | 74% |
| clean opening (nobody on either side had touched the other, and I was not under fire) | perception | 8% | 8% | +1 | 8% |
| I was under fire in the previous 10 s | perception | 68% | 69% | −1 | 68% |
| enemy is a fresh spawn (< 6 s) | perception | 30% | 28% | +1 | 29% |
| enemy took RA/YA/MH in the last 20 s | perception | 35% | 34% | +1 | 35% |
| enemy just killed someone (10 s) | perception | 38% | 38% | 0 | 38% |
| enemy has RL | perception | 35% | 35% | +1 | 35% |
| enemy has 200+ eff | perception | 19% | 19% | 0 | 19% |
| enemy under 100 eff | perception | 30% | 32% | −1 | 31% |
| first hit from 600+ units | execution | 10% | 8% | +2 | 10% |
| first hit from under 200 units | execution | 28% | 33% | −5 | 30% |

The split is stark: every row that describes the **starter's own state** separates the groups by 5-16 points; every row that describes the **enemy's state** is within 2 points. Restricting to neutral-lock samples only (TOP n = 212k, FIELD 179k) reproduces every gap to the point (RL 41/25, 150+ eff 32/22, built life 21/11, own spawn <10 s 40/49, just killed 49/37, armor ≤30 s 54/40, enemy cues all ±1). The 50+ damage subset likewise (RL 50/34, built life 28/17). Per map the RL gap is +15 to +16 on every map (dm3 37/21 plus LG 25/13; dm2 51/36; e1m2 35/19; schloss 46/30), the "spawn <10 s" gap is −8 to −9 everywhere, and the armor-in-30-s gap is +11 to +15 everywhere.

Note the "≤ 10 s after an armor" row: it is the one item-timing condition where TOP and FIELD are nearly equal (38% vs 35%). The TOP's surplus is in the **10-30 s** band: 34% of TOP starts come 10-30 s after an armor/mega against 26% of FIELD starts, and 46% of TOP starts have no armor/mega in the previous 30 s against 59% of FIELD starts. They are not fighting *off* the item, they are fighting *with* it.

### 2b. Stack trajectory (starts on lives 30 s+ old, same life)

| group | starts | eff 30 s before | eff 10 s before | eff at the hit | gained 50+ | lost 50+ | 200+ at hit | armor/MH in the 30 s |
|---|---|---|---|---|---|---|---|---|
| TOP | 166,583 | 168 | 185 | 184 | 39% | 28% | 45% | 72% |
| FIELD | 95,511 | 155 | 174 | 169 | 36% | 28% | 40% | 62% |

For everyone on a built life: a start preceded by a 50+ gain goes 66% kill / 7% die (mean 241 eff at the hit), flat 62/14, a 50+ loss 60/16. The trajectory gap between the groups is modest (+3 on "gained 50+"); the bigger difference is simply how many of their starts happen on a built life at all (section 2a: 24% vs 13% at 60 s+).

### 2c. What was picked up in the 30 s before (all starts)

| group | armor/MH only | armor/MH + RL/LG | RL/LG only | health pack only | nothing |
|---|---|---|---|---|---|
| TOP | 42% | 12% | 9% | 8% | 28% |
| FIELD | 32% | 8% | 9% | 9% | 42% |

Outcome by last armor/mega take (everyone): 0-5 s before → 52% kill / 16% die (mean 229 eff, RL 52%); 5-10 s → 52 / 19; 10-20 s → 49 / 25; 20-30 s → 43 / 30; nothing in 30 s → 32 / 41 (mean 96 eff, RL 21%). Of the armor takes that precede a start, 45% are YA, 30% RA, 25% MH in both groups; mean 14 s from the take to the hit in both. On lives already 30 s old, a TOP start with nothing picked up in the window still goes 64/12; the FIELD's goes 52/22.

### 2d. Where

The start-area distribution is the same for both groups on every map (dm3 RL 9% vs 11%, Ring 7/8, Quad 7/6, RA 7/6; dm2 low.RL 12/12, tele 9/11, NG 9/9; e1m2 YA 12/12, Quad 10/12, GL 11/10; schloss tower.RL 15/17, cathedral 10/10). The TOP win more in the same rooms: dm3 Ring 42/26 vs 31/34 and SNG.tele 41/29 vs 29/40; dm2 NG 52/22 vs 39/31; e1m2 Quad 53/25 vs 39/35; schloss tower.RL 44/24 vs 38/31. Position is not where the difference lives (at 10 s resolution).

### 2e. Is the RL gap a choice or a bank balance?

| | RL held while alive | RL at the first hit of own starts | ratio | 150+ eff while alive | 150+ eff at own starts |
|---|---|---|---|---|---|
| TOP (10 players) | 42-50% | 39-50% | 0.92-1.01 | 30-38% | 29-40% |
| FIELD (14 players) | 10-38% | 9-39% | 0.77-1.09 | 11-31% | 12-32% |

Group means: RL while alive 44.3% vs 28.7%, LG 8.4% vs 4.8%, mean eff while alive 136 vs 120, 200+ eff while alive 23.8% vs 16.8%. The ratio is ~1 for every TOP player: they start fights with RL exactly as often as they hold it. Three FIELD players (ledge 0.77, namtsui 0.81, stedanko 0.81) start *less* often when armed than their RL time would predict — i.e. a larger share of their starts are naked spawn-fights. Clean openings (8% of starts) are the one place everyone is selective: TOP open 59% of them with RL (vs 44% held), FIELD 40% (vs 29%) — the same ×1.35 selectivity, different base.

## 3. What separates kills from deaths, and which of it the TOP do more

### 3a. Univariate lift (all 957k starts by everyone)

| condition | bucket | share of starts | kill if yes / no | die if yes / no | TOP | FIELD |
|---|---|---|---|---|---|---|
| behind by 60+ | decision | 24% | 10% / 49% | 62% / 23% | 23% | 26% |
| ahead by 60+ | decision | 28% | 70% / 28% | 6% / 43% | 32% | 25% |
| RL in hand | decision | 35% | 65% / 26% | 10% / 45% | 43% | 27% |
| first hit is a rocket | execution | 29% | 67% / 29% | 10% / 42% | 34% | 24% |
| 150+ eff | decision | 29% | 61% / 31% | 10% / 42% | 34% | 24% |
| alive 60 s+ | decision | 19% | 68% / 33% | 8% / 38% | 24% | 13% |
| quad or pent on | decision | 6% | 82% / 37% | 6% / 34% | 9% | 3% |
| enemy has RL | perception | 35% | 20% / 51% | 52% / 22% | 35% | 35% |
| own spawn < 10 s | decision | 43% | 24% / 52% | 48% / 21% | 39% | 48% |
| enemy has 200+ eff | perception | 19% | 13% / 46% | 55% / 28% | 19% | 19% |
| 2+ enemies in the fight | perception | 15% | 34% / 41% | 50% / 30% | 15% | 15% |
| had just killed someone | decision | 43% | 60% / 25% | 21% / 41% | 49% | 37% |
| enemy is a fresh spawn | perception | 29% | 54% / 34% | 19% / 38% | 30% | 28% |
| under fire in the previous 10 s | perception | 68% | 35% / 50% | 38% / 20% | 68% | 69% |
| took RA/YA/MH ≤ 30 s | decision | 47% | 48% / 32% | 24% / 41% | 54% | 41% |
| enemy took RA/YA/MH ≤ 20 s | perception | 35% | 27% / 47% | 42% / 27% | 35% | 34% |
| enemy just killed someone | perception | 38% | 32% / 44% | 41% / 27% | 38% | 38% |
| joining a teammate's fight | perception | 62% | 45% / 31% | 28% / 41% | 61% | 63% |
| first hit from 600+ units | execution | 10% | 25% / 41% | 22% / 34% | 10% | 8% |
| took RA/YA/MH ≤ 10 s | decision | 37% | 52% / 46% | 18% / 27% | 38% | 35% |
| clean opening | perception | 8% | 43% / 40% | 27% / 33% | 8% | 8% |

The conditions with the largest lift that the TOP satisfy more often: RL in hand (+16 points), armor/mega inside 30 s (+14), a kill in the last 10 s (+12), a rocket as the opener (+11), 150+ eff (+10), a built life (+10), not starting inside 10 s of a spawn (+8 the right way), ahead by 60+ (+7). The conditions with large lift that they do **not** satisfy more: every enemy-state cue (enemy RL, enemy 200+, enemy fresh, enemy just took armor, enemy just killed) and joining vs opening.

### 3b. Multivariate (logistic regression on binary pre-fight conditions, 957k starts; odds ratios vs an even-stack, shotgun, no-cue, neutral-lock, dm3, non-roster start)

P(kill): quad/pent ×4.2, RL in hand ×3.8, ahead 60+ ×3.7, LG ×1.9, joining ×1.3; behind 60+ ×0.24, enemy has RL ×0.37, enemy took armor/MH ×0.79, own spawn <10 s ×0.83. TOP-player dummy ×1.03, FIELD ×0.93.
P(die): ahead ×0.22, RL ×0.23, quad ×0.31, LG ×0.63, joining ×0.82, enemy fresh ×0.85; behind ×2.5, enemy has RL ×2.3, under fire in the last 10 s ×1.3, enemy just killed ×1.14, team locked ×1.09. FIELD dummy ×1.14, TOP ×0.98.
(The "own 200+ eff" term comes out ×0.53 for kills once edge and RL are in the model — an artefact of the bucketing: an even fight at 200+ means the enemy is also stacked. Read eff through the edge rows.)

Once weapon, edge and the cues are controlled, being a TOP player adds almost nothing to the odds of a kill (×1.03) and the FIELD costs ×0.93 / ×1.14 on death. That is the central result of this study: **the TOP's start outcomes are explained by the state they arrive in, not by something unmeasured they do once the fight begins.** The residual FIELD penalty on dying (×1.14) is the only hint of an in-fight (execution) gap, and it is small next to RL (×0.23) or being ahead (×0.22).

### 3c. Spawn-fights vs built-life fights (TOP vs FIELD)

| starter | enemy | TOP n | TOP kill / die | FIELD n | FIELD kill / die |
|---|---|---|---|---|---|
| fresh (<6 s) | built | 99,196 | 20% / 55% | 96,339 | 19% / 56% |
| fresh | fresh | 27,935 | 34% / 31% | 29,429 | 32% / 33% |
| built | fresh | 99,488 | 66% / 11% | 72,121 | 55% / 18% |
| built | built | 202,644 | 46% / 25% | 159,815 | 37% / 35% |

Spawn-fighting is a coin everyone flips the same way. The TOP make their money by (a) being on the "built" side of the table more often (section 2a) and (b) converting built-vs-built and built-vs-fresh at +9 to +11 points. "Throwing a built life" — starting 60+ behind without an RL against an RL carrier on a life already 15 s old — is 5.8% of the FIELD's built-life starts (died 72%, killed 3%) and 3.2% of the TOP's (died 67%, killed 6%).

## 4. Accepted fights: when the enemy strikes first

| | TOP | FIELD |
|---|---|---|
| accepted fights | 366,625 | 425,458 |
| put damage back inside 5 s | 59% | 51% |
| mean damage back in 5 s | 62 | 40 |
| 60+ damage back in 5 s | 38% | 26% |
| killed the starter | 28% | 19% |
| died | 47% | 58% |
| no damage back and survived ("disengaged") | 16% | 15% |
| had RL when hit | 44% | 28% |
| ahead 60+ / behind 60+ when hit | 29% / 26% | 21% / 31% |
| was < 6 s off a spawn when hit | 26% | 32% |

Excluding own fresh spawns: hit back 63% vs 54%, 76 vs 49 damage, killed the starter 35% vs 24%, died 38% vs 52%. On 50+ damage fights: 71% vs 62% hit back, 79 vs 52 damage, 36% vs 24% kills.

By edge from the acceptor's side: ahead 60+ → TOP hit back 72% / 91 dmg / kill 53% / die 14%, FIELD 65% / 67 / 45% / 21%; even → 61% / 60 / 26% / 49% vs 56% / 41 / 18% / 57%; **behind 60+ → 42% / 34 / 5% / 79% vs 34% / 21 / 2% / 84%**. Holding RL when hit: TOP 69% hit back, 102 damage, 47% kill, 25% die; FIELD 63%, 82, 39%, 33%. Without RL: 51% / 30 / 14% / 64% vs 47% / 25 / 11% / 67%.

So the answer to "fight back or disengage" is: TOP players fight back more, harder, and sooner, in every edge bucket and on every map (hit-back inside 5 s: dm3 57/49, dm2 59/51, e1m2 64/56, schloss 57/48). The share that successfully walks away is identical. Per player, when hit first while 60+ behind, bogojoker (47%), zorak (44%) and blaze (44%) answer most; schotty (27%) and evalcat (26%) least, and they die 89% / 83% of those. Caution: among everyone hit first while behind, those who hit back die 78% vs 84% for those who do not — but "no damage back" includes being one-shot, so this is not proof that firing back saves you; it is proof that the TOP are not choosing retreat.

## 5. Coachable statements

1. **[decision] Stop fighting off the spawn: 48% of a FIELD player's starts come inside 10 s of his spawn (TOP 39%), and those go 24% kill / 48% death for everyone.** Fresh starter vs built enemy is 20/55 for TOP and FIELD alike — nobody is good at it. The first 10 s of a life are for a weapon and a pack, not a shotgun poke.
2. **[decision] Arrive with the stack, not just off the item.** 54% of TOP starts (41% FIELD) have an armor/mega inside the previous 30 s; starts inside 10 s of the take go 52/16-19, 10-20 s 49/25, nothing in 30 s 32/41. The surplus TOP starts are in the 10-30 s band — take it, keep it, then hunt.
3. **[decision] The RL is the single biggest lever (×3.8 kill odds, ×0.23 death odds) and it is a bank balance, not a decision.** TOP hold RL 44% of their alive time and start 43% of their fights with it; FIELD 29% and 27%. The fix is upstream: survive the spawn (53 vs 63 deaths/game), touch the RL spawn on the way, and do not give it away in a behind-start (statement 6).
4. **[decision] Chain the kill into the next start: 49% of TOP starts come inside 10 s of a kill they made (FIELD 37%), and those starts go 60/21 vs 25/41.** After a frag the nearest enemy is usually fresh or already hurt; press it with the stack you just kept.
5. **[perception] Target cues do not separate the top from the field — yet.** Enemy fresh (30/28), enemy just took armor (35/34), enemy just killed (38/38), enemy has RL (35/35) are identical across groups, while each of them moves outcomes by 15-30 points (enemy took armor: 27/42 vs 47/27; enemy fresh: 54/19 vs 34/38). This is unclaimed ground for the coach: the audible pickups (armor, mega, RL) and the kill feed tell you which fights to skip, and nobody in NA is using them better than anyone else.
6. **[decision] Do not throw a built life: 5.8% of FIELD built-life starts are 60+ behind, without RL, against an RL carrier (TOP 3.2%); 72% die, 3% kill.** A 15 s-old life with YA and a shotgun is worth more walking to the RL than poking a stacked rocket.
7. **[execution] When hit first, answer inside 5 s.** TOP put 62 damage back in the first 5 s (FIELD 40), hit back 59% vs 51%, and kill the starter 28% vs 19%; the "walk away clean" rate is 16% for both. With RL in hand the TOP return 102 damage vs 82.
8. **[execution] Open with the rocket, not the shotgun: 34% of TOP starts open with a rocket (FIELD 24%), 53% with a shotgun (64%).** Rocket openers go 67/10, shotgun openers 24/46. If the RL is in hand, the first shot should be it.
9. **[decision] dm3 only: pick up the LG and use it. chris opens 39% of his dm3 starts with LG, blaze 30%, zorak 29%; FIELD players 7-23%.** LG starts go 62-72% kill / 9-16% die for the TOP.
10. **[decision] Keep starting under a lock.** TOP start 55% of their fights while locked (FIELD 45%) and still arrive with RL 20% of the time (12%). The lock is broken by kills (lock_spawn.py: 52-73% of breaks follow 3+ frags in 30 s), and kills come from starts.

## 6. Caveats

- **Definition sensitivity.** A "fight" is any damage exchange; 15.6% are a single hit and 23.7% exchange under 50 damage. The 50+ damage subset shifts all rates (kill up, death up) but not one of the TOP–FIELD gaps. Changing the 4 s cluster gap to 2 s or 8 s: the headline numbers barely move. Share started TOP/FIELD: 53.8/45.8 (2 s), 53.9/45.7 (4 s), 54.0/45.7 (8 s); RL at the hit 42.5/26.9, 42.6/27.0, 42.4/26.9; kill/die on starts 41.6/26.7 vs 33.5/33.8 (2 s), 43.9/29.1 vs 35.2/37.0 (4 s), 44.8/30.3 vs 35.9/38.3 (8 s); accepted hit-back 58.8/50.9, 59.2/51.1, 59.3/51.2. A longer gap merges pokes into fights (931k vs 1,024k fights) and raises both the kill and the death rate for everyone; the gaps between the groups are the same to within a point.
- **Who struck first is a proxy for who chose to fight.** The first hit can be a stray pellet; the "starter" of a fight a teammate is already in (62% of all starts) is often the second man into someone else's fight. Clean openings — 8% of starts — are the only ones where "decision to start" is unambiguous, and the TOP–FIELD RL/edge gaps are larger there (RL 59 vs 40, ahead 38 vs 29).
- **Selection.** TOP players' teams are *not* stronger on average in this sample (same lock-state time share, mean margin −5 vs +2), so team-quality confounding is weaker than expected, but it is not zero: better teammates make joins easier and spawns safer. The within-neutral-lock tables reproduce every gap.
- **What the 10 s state cannot see.** Area, eff 30 s before, and lock margin are 10 s snapshots; the starter's position at the hit can be a room away, and the lock margin can swing inside the sample. Fights on lives under 10 s have no area (10.7% of rows). Health packs and ammo are not in the eff trajectory. Who could *hear* what is inferred from the pickup/kill record, not from audibility — a mega take in the opposite corner of dm3 is counted as a cue the same as one through a wall.
- **Outcome attribution.** "Died" counts deaths to anyone within 1.5 s of the last exchange, so a third enemy's rocket is charged to the fight; "kill" requires the frag inside the pair's cluster. Both are symmetric across groups.
- **Roster effects.** blood_dog_d_p contributes 29% of TOP starts (124,606 of 429,263) and namtsui/cronus 35% of FIELD starts; the per-player table shows the conclusions hold for every individual, but group means are weighted toward them.
- **The regression is descriptive**, binary features, no interactions beyond the edge buckets; it ranks levers, it does not prove a causal effect of, say, waiting for RL.

## Files

- `/private/tmp/claude-501/-Users-peteryeargin/a7f17fb4-de1b-4afb-8c33-8756bc0a6385/scratchpad/fight_entry_extract.py` — builds `fight_entry.sqlite` (957,094 rows, ~55 s). `python3 fight_entry_extract.py [gap_ms] [out.sqlite]`.
- `/private/tmp/claude-501/-Users-peteryeargin/a7f17fb4-de1b-4afb-8c33-8756bc0a6385/scratchpad/fight_entry_report.py` — all tables (~65 s) → `fight_entry_tables.md`.
- `/private/tmp/claude-501/-Users-peteryeargin/a7f17fb4-de1b-4afb-8c33-8756bc0a6385/scratchpad/fight_entry.sqlite` — the fight table (gap 4 s); `fight_entry_gap2.sqlite`, `fight_entry_gap8.sqlite` — sensitivity runs.

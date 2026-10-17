# PERCEPTION study — do the best NA 4on4 players act on what they can hear and see more than the field?

DeepFrag research note, 2026-10-16. Read-only study of `data/mvd_features.sqlite`; scripts and all raw tables are next to this file (`perception_study.py`, `perception_agg.py`, `perception_tables.md`). Nothing in the repo or the database was changed; nothing was added to `docs/coaching_doctrine.md` §7 (the owner should add any correction from this note himself).

Framework tag on every finding: **P** = perception (what he could know), **D** = decision, **X** = execution.

## 0. Bottom line

1. **Cue awareness is NOT what separates TOP from FIELD.** Of the fights a player starts while 60+ eff behind, 86% (TOP) vs 85% (FIELD) had an audible cue (the enemy's armor/mega pickup in the last 20 s, or a trade with him). The enemy's stack was *knowable* in 77% vs 78% of those starts. Same share of bad reads. [P: no gap]
2. **The hypothesis "top players attack the fresh red-taker less" is wrong.** After an enemy takes RA, TOP attack him within 15 s **36%** of the time vs **29%** (FIELD); after a mega, 35% vs 28%. They die doing it less (RA: 57% vs 68%; MH: 53% vs 65%) and kill him more (24% vs 16%; 30% vs 21%). They also take an armor/mega themselves in those 15 s more often (31% vs 24% after a red; 31% vs 22% after a mega) and are almost never idle (5% vs 8–9% "nothing"). No sign of "waiting for the mega to decay": the timing curve has the same shape, just more attacks. [D/X]
3. **The one perception number that separates the groups everywhere is first damage landed: 61% vs 50%** of fights (both sides alive ≥3 s), and it holds with no RL/LG (61% vs 50%), at ≤120 eff with no launcher (62% vs 51%), when behind (58% vs 45%), on every map, and with the FIELD player on the same team in the same game (61% vs 49%). Landing first turns a 51–63% death into a 39–49% one. [P→X]
4. **Top players convert information into items faster.** After an enemy death, TOP take a RA/YA/MH/RL/LG within 15 s **37%** of the time vs **27%**, whoever made the frag (e1m2 24% vs 14%, schloss 41% vs 30%). They take 16% of the red and mega respawns they are alive for vs 11%. When they ARE the taker, both groups take the red on the timer equally (≤3 s: 59% vs 58%); the gap is being there, plus the yellow (≤3 s: 56% vs 47%). [P→D]
5. **Quad: same attendance, different last 10 seconds.** Both groups are near the quad before 75%/72% of spawns and enter ≥5 s early 75%/76% of the time. On dm3 (per-second tracks) TOP are in the room at the spawn 27% vs 17%; of players who were in the room in the last 10 s, 43% (TOP) vs 54% (FIELD) walk out before it spawns; in the room at 0 with the RL 60% vs 43%; a player in the room at 0 takes it 64% vs 40% (with RL 75% vs 55%). [P→D]

What this means for the coach: the field hears the same sounds and reads the same timers; it **starts the same bad fights without the RL** (RL in hand in cued behind-starts: 30% TOP vs 17% FIELD; without the RL everybody dies 76–78% of the time), **gets found first**, and **does not turn a frag or a pickup sound into the next item**. Train the link sound → number → next item, not "listen more".

## 1. What was measured

**Games.** 1,415 4on4 games on dm3 (441), dm2 (404), e1m2 (292), schloss (278) since 2025-01-01 with 8 players. Names folded through `name_canon`.

**Groups.** TOP = bogojoker, zorak, sane, chris, blaze, yeti, blood_dog_d_p, war, dusty, coj (4,375 player-games; blood_dog_d_p is 29% of them, so per-player medians are reported next to every pooled number). FIELD = viag, nico, gflip, omicron, namtsui, cronus, pharm, pred, foobhar, phylter, stedanko, ledge, schotty, evalcat (4,886 player-games). OTHER = everyone else (shown as a reference line in the raw tables).

**Rows.** 896,127 fights; 515,326 enemy RA/MH pickups seen while alive; 244,883 RA/YA/MH takes of a respawned item; 994,177 (RA/MH respawn × alive player); 1,525,092 teammate deaths; 2,237,997 enemy deaths; 213,458 quad approaches; 66,341 dm3 per-second quad tracks.

**Definitions (ms from match start; all stacks are `eff` = min(h/(1−soak), h+a): spawn 100, +RA 300, +YA 250, +GA 142, +MH 200).**
- *Fight*: one player's damage events with enemies, clustered with a 4 s gap (the rule in `fours_player_read.py`). *Started* = he landed the first damage. *Foe* = the other party of that first event. *Behind* = foe eff − own eff ≥ 60 at that event (pre-damage values stored on the event). *Died* = he died inside the fight window +1.5 s; *killed him* = he fragged the foe in that window.
- *Cue*: in the 20 s before the fight the foe took RA/YA/MH (treated as audible), or the player traded damage with him. Also tabulated: the foe fragged someone (kill feed) or took RL/LG.
- *Knowable stack (spec)*: fresh spawn 100, +100 health if a mega was heard, best armor heard (RA 200 / YA 150 / GA 100), within the last 20 s and since the foe's spawn (spawn from `vic_tss`), minus the damage the player himself dealt him in that window; converted to eff with the same formula. *Life variant*: same with the whole life as the window. *Consistent* = |true − knowable| ≤ 60. A behind-start is *knowable* when knowable − own eff ≥ 60.
- *Reaction to an enemy RA/MH take*: the player must be alive at the take (10 s state sample + death events). "Attacked the taker" = landed damage on him within 15 s; "first thing" = earliest of: hit the taker / hit by the taker / hit someone else / took RA-YA-GA-MH-RL-LG-quad / died / nothing. *In the area* = the player's 10 s location sample before the take has the item's own area name. *Teammate also hit him* = a teammate landed damage on the taker inside the window.
- *Item timing*: `wait_ms` = take time − `available_from` (how long the item sat), only for items that had respawned at least once. *Arrival*: for each RA/MH respawn, each alive player: did he take it (and how fast), was he in the item's area at the 10 s sample before/after the spawn.
- *Quad*: `quad_approach` (all maps; distance 10/5/2/0 s before the spawn, stack at spawn, took, "contested", `enter_before_ms`). `quad_tracks` (dm3 only, per-second): room presence uses the doctrine room list (`Quad`, `window.Quad`); *left the room* = in a listed room at some second in [−10, 0] and out of it at a later second before the spawn (a death is not "leaving").
- *Kill feed*: a teammate dies to enemy E in area X (X = the teammate's last 10 s sample); the alive player's location at the next two samples (+10/+20 s), whether he engaged E inside 20 s, who landed first, and the result. *Conversion*: after an enemy dies to the player's team, time to the player's next RA/YA/MH/RL/LG take while alive.
- *First damage*: share of fights in which the player landed the first hit, excluding fights where either side had spawned <3 s earlier.
- Statistics: pooled shares with counts, a two-proportion z-test (ignores clustering by game and player, so treat p as indicative), the per-player median (players with ≥20 rows), and a same-team control (§2.8).

## 2. Results

### 2.1 Fights started 60+ eff behind: did he have a cue? [P]

| | TOP | FIELD | per-player median |
|---|---|---|---|
| started behind ≥60, share of fights he started | 19% (40,562/210,544) | 22% (42,386/190,875) | 19% vs 22% |
| …with a cue (armor/mega heard or traded) | **86%** | **85%** | 86% vs 84% |
| …armor/mega heard | 73% | 71% | |
| …traded with him in the last 20 s | 45% | 45% | |
| …he had fragged (kill feed) in the last 20 s | 60% | 59% | |
| died, behind + cue | 64% | 72% | 65% vs 72% |
| died, behind, no cue | 64% | 74% | |
| killed him, behind + cue | 16% | 10% | 16% vs 9% |
| RL in hand, behind + cue | **30%** | **17%** | 30% vs 19% |
| died, behind + cue, RL in hand | 36% | 43% | |
| died, behind + cue, no RL | **76%** | **78%** | 77% vs 78% |
| a teammate also shot him, behind + cue | 43% | 43% | |
| died, behind + cue, no RL and nobody else shot him | 75% | 78% | |
| fresh spawn (<5 s) at the start, behind + cue | 18% | 20% | |

Per map, died given behind + cue (TOP / FIELD): dm3 64% / 71%, dm2 63% / 71%, e1m2 71% / 79%, schloss 63% / 71%. The exact pattern from last night (armor heard, foe ≥230 eff): died 61% / 70% pooled; schloss 60% / 71%; with no RL and nobody else shooting him: 74% / 75% on schloss.

Reading: the cue is there for both groups 5 times in 6. The death gap (64% vs 72%) is almost entirely the RL mix: 0.30×36 + 0.70×76 = 64 (TOP); 0.17×43 + 0.83×78 = 72 (FIELD). Without the RL, the top players die in these fights as often as everyone else. The doctrine's point stands: many of these starts are floods and spawn fights (18–20% are fresh spawns, 43% have a teammate shooting the same enemy); the lever is not "start fewer", it is "not without the RL".

### 2.2 After an enemy takes RA or MH: what does the player do in 15 s? [D/X with a P trigger]

Enemy takes **RA** (TOP n=104,648; FIELD n=114,074):

| | TOP | FIELD | per-player median |
|---|---|---|---|
| attacked the taker ≤15 s | **36%** | **29%** | 36% vs 29% |
| first thing: attack the taker / attack someone else / take an item / nothing | 10 / 51 / 22 / 5% | 8 / 47 / 19 / 8% | |
| the taker found me first | 6% | 9% | 6% vs 8% |
| took RA/YA/MH myself ≤15 s | **31%** | **24%** | 29% vs 24% |
| died ≤15 s given I attacked him | **57%** | **68%** | 57% vs 68% |
| died to him given I attacked | 36% | 45% | |
| killed him given I attacked | 24% | 16% | 24% vs 16% |
| died ≤15 s given I did NOT attack him | 37% | 46% | |
| attacked given I had ≤120 eff → died | 34% → **69%** | 28% → **76%** | |
| attacked given I had ≥200 eff → died | 41% → 39% | 33% → 49% | |
| attacked given RL in hand / no RL | 39% / 35% | 32% / 28% | |
| attacked from elsewhere (not already in the item's area) | 36% | 29% | |
| a teammate also hit him given I attacked → died | 71% → 56% | 73% → 66% | |
| nobody else hit him given I attacked → died / killed him | 59% / 18% | 73% / 9% | |
| solo, from elsewhere, ≤120 eff (share of all cases) → died | 6% → **70%** | 5% → **80%** | 5% vs 4% → 71% vs 81% |
| first attack on him: ≤15 s / 15–30 / 30–60 / 60–120 s / never before one dies | 26 / 9 / 5 / 1 / 59% | 19 / 6 / 3 / 1 / 71% | |

Per map, attacked ≤15 s → died (TOP / FIELD): dm3 31% → 59% / 25% → 70%; dm2 37% → 55% / 30% → 65%; schloss 42% → 60% / 32% → 71% (e1m2 has no red).

Enemy takes **MH** (TOP n=97,417; FIELD n=105,609): attacked ≤15 s 35% vs 28%; died given attacked 53% vs 65%; killed him 30% vs 21%; took RA/YA/MH myself 31% vs 22%; nothing 5% vs 9%; found first 6% vs 8%; attacked at ≤120 eff → died 63% vs 73%; at ≥200 → 34% vs 43%; solo naked from elsewhere 6% vs 5% of cases → died 66% vs 77%. First attack ≤15 s / 15–30 / 30–60 / never: 24 / 8 / 5 / 61% vs 18 / 5 / 3 / 73% — no "wait 20 s" bump for either group. Per map died given attacked: dm3 49% / 63%, dm2 54% / 65%, e1m2 63% / 74%, schloss 51% / 64%.

**The item he did not take** (share of all cases where the player took it within 15 s, TOP / FIELD):

| after an enemy… | dm3 | dm2 | e1m2 | schloss |
|---|---|---|---|---|
| RA → I took YA | 10.8 / 8.3% | 19.8 / 18.2% | — | 22.2 / 15.3% |
| RA → I took MH | 11.8 / 7.9% | 8.9 / 5.6% | — | 7.6 / 6.1% |
| MH → I took RA | 10.5 / 6.7% | 17.0 / 12.4% | — | 8.9 / 5.4% |
| MH → I took YA | 10.5 / 7.6% | 17.5 / 16.2% | 13.4 / 8.7% | 20.5 / 15.4% |

Reading: the hypothesis was half right. Top players do go for the other item more (and the YA on schloss/dm3 is the clearest case), but they also attack the stacked man more. What they do not do is nothing: idle 5% vs 8–9%, and found-first 6% vs 8–9%. Attacking a fresh red costs a life 1.5× more often than anything else for both groups (57/37 and 68/46), and a solo naked attack from elsewhere is a 70–80% death for everyone.

### 2.3 Item timing and arrivals [P: timer; D: route]

Takes within 3 s of the respawn, by map and item (TOP / FIELD; takes that had respawned at least once):

| map | RA ≤3 s | YA ≤3 s | MH ≤3 s | median RA wait |
|---|---|---|---|---|
| dm3 | 54% / 56% (n 9,762 / 6,797) | **70% / 64%** | 28% / 29% | 2.2 / 2.2 s |
| dm2 | 62% / 58% (17,747 / 14,365) | **32% / 26%** | 33% / 31% | 1.7 / 1.9 s |
| e1m2 | — | **79% / 74%** | **49% / 41%** | |
| schloss | 57% / 59% (7,301 / 4,546) | **63% / 58%** | 31% / 31% | 2.1 / 1.9 s |
| all | 59% / 58% (p=0.004) | 56% / 47% | 33% / 31% | 1.9 / 2.0 s |

Per player, RA ≤3 s runs 55–62% for every TOP player and 52–62% for every FIELD player except evalcat (32%, n=317). YA ≤3 s: TOP 52–64%; FIELD 25–55% (schotty 34%, pred 39%, ledge 42%, evalcat 25%).

Arrivals — every RA respawn the player was alive for (8 players, so ~12.5% is "his share"):

| | TOP | FIELD |
|---|---|---|
| he took it | **16%** (34,012/206,599) | **11%** (24,892/223,580) |
| he took it ≤3 s / ≤10 s | 10% / 14% | 7% / 9% |
| in the item's area at the sample before / after the spawn | 8% / 7% | 7% / 6% |
| his team took it | 51% | 51% |
| took ≤3 s given he had ≤120 eff / ≥200 eff | 11% / 5% | 7% / 3% |

Same for MH: took 16% vs 11%; ≤3 s 5% vs 3%; ≤10 s 11% vs 7%. Per map RA taken (TOP / FIELD): dm3 17 / 11%, dm2 16 / 12%, schloss 17 / 11%; MH: dm3 15 / 11%, dm2 16 / 10%, e1m2 18 / 9%, schloss 15 / 12%.

Reading: the stopwatch is equal — a FIELD player who is at the red takes it on the timer as often as a TOP player. The gap is being at the red (and the mega) when it comes up, 45% more often, including when he needs it (≤120 eff: 11% vs 7%). The YA timer is the one the field is actually late on.

### 2.4 Quad [P: count; D: arrive stacked, stay]

`quad_approach`, all maps, every respawn (first spawn excluded):

| | TOP | FIELD | per-player median |
|---|---|---|---|
| alive at the spawn | 96% | 94% | |
| "contested" flag given alive (see caveat: this is the 650 u radius) | 75% | 72% | 72% vs 74% |
| took, given alive | **20%** | **8%** | 18% vs 9% |
| died near the quad before the spawn | 16% | 19% | |
| entered ≥5 s / ≥10 s early given contested | 75% / 34% | 76% / 36% | |
| ≥150 eff at the spawn given contested | **34%** | **23%** | 34% vs 25% |
| ≥150 eff given took | 61% | 52% | |
| median distance at −10 / −5 / −2 / 0 s (contested) | 810 / 669 / 585 / **546** | 770 / 680 / 644 / **629** | |

Per map, ≥150 eff at spawn given contested (TOP / FIELD): dm3 33 / 22%, dm2 40 / 31%, e1m2 21 / 10%, schloss 34 / 22%. Took given alive is 19–20% vs 8% on all four maps.

dm3 per-second tracks (TOP n=24,836 player-spawns; FIELD n=28,296):

| | TOP | FIELD | per-player median |
|---|---|---|---|
| in a quad room at −10 / −5 / −2 / 0 s | 6 / 15 / 23 / **27%** | 7 / 12 / 15 / **17%** | 24% vs 20% at 0 |
| left the room in the last 10 s, given he was in it | **43%** | **54%** | 45% vs 53% |
| left and was still out at 0 | 33% | 45% | |
| RL at 0, given in the room at 0 | **60%** | **43%** | 65% vs 41% |
| ≥150 eff at 0, given in the room | 53% | 39% | |
| took, given in the room at 0 | **64%** | **40%** | 65% vs 42% |
| took, in the room with RL / without | 75% / 49% | 55% / 29% | |

Reading: attendance and early entry are equal; top players are farther away at −10 s and closer at 0 — they time the last approach instead of camping, they stay once in, and they come with the RL. The field walks out of the room in the last 10 s more than half the time it was in it.

### 2.5 Kill feed and converting frags into items [P→D]

A teammate dies to enemy E in area X (TOP n=622,008; FIELD n=630,986 alive-player cases):

| | TOP | FIELD |
|---|---|---|
| already in X | 6% | 6% |
| entered X within 20 s, given not there | **10%** | **10%** |
| engaged E within 20 s | 55% | 52% |
| I landed first, given engaged | **56%** | **47%** |
| died ≤20 s / died to E | 50% / 20% | 60% / 24% |
| killed E ≤20 s | 20% | 13% |
| attacked E first at ≤120 eff while E had ≥200 (of all) → died / killed him | 5% → 74% / 18% | 4% → 81% / 13% |

Per map, "I landed first given engaged" is 56–57% vs 46–48% on all four maps. With 10 s location samples the "move toward X" measure is coarse, but it shows no difference at all; what differs is who lands first when they meet the killer.

After an enemy dies to the player's team:

| | TOP | FIELD | per-player median |
|---|---|---|---|
| next RA/YA/MH/RL/LG take ≤15 s | **37%** | **27%** | 36% vs 27% |
| ≤30 s | 51% | 37% | |
| ≤15 s given I made the frag / a teammate did | 36% / 37% | 26% / 27% | |
| ≤15 s given I had ≤120 eff | 36% | 26% | |
| that next take is armor/mega | 78% | 73% | |

Per map (TOP / FIELD): dm3 36 / 26%, dm2 44 / 35%, e1m2 24 / 14%, schloss 41 / 30%. Per player: every TOP player 33–40%; FIELD 15–36% (nico 36%, viag 32%, cronus 31%, pharm 31%; schotty 16%, evalcat 15%, ledge 22%, pred 25%).

### 2.6 First damage landed [P→X]

| share of fights where the player landed first | TOP | FIELD | per-player median |
|---|---|---|---|
| all fights | 60% | 50% | 60% vs 51% |
| both sides alive ≥3 s (used below) | **61%** | **50%** | 61% vs 51% |
| I hold RL / LG only / neither | 60% / 57% / 61% | 50% / 46% / 50% | |
| both hold RL | 61% | 48% | 60% vs 45% |
| I am ≥60 ahead / ≥60 behind | 63% / 58% | 54% / 45% | |
| ≤120 eff and no RL/LG | **62%** | **51%** | 63% vs 53% |
| a teammate also in the fight / nobody else hit him | 61% / 60% | 52% / 49% | |
| died, given I landed first / given he did | 39% / 51% | 49% / 63% | |

Per map: 60–62% vs 49–51%. Per player: TOP 54–69% (coj 54%, bogojoker 69%); FIELD 36–57% (schotty 36%, evalcat 38%, cronus 47%, pred 48%, omicron 49%, namtsui 57%, nico 57%).

This is first *damage*, not first shot fired — a missed first rocket is invisible — so it mixes seeing him first, positioning, and aim. The fact that it does not move with weapon, stack, support or map says it is not a stack/weapon artifact.

### 2.7 Stack-read score [P]

| of fights the player started | TOP | FIELD |
|---|---|---|
| true foe eff within 60 of the knowable-20 s estimate | **73%** | **72%** |
| within 60 of the whole-life estimate | 69% | 68% |
| foe stronger than knowable by >60 (hidden stack) | 9% | 9% |
| foe weaker than knowable by >60 (he had lost it) | 18% | 20% |
| behind-starts that were KNOWABLE (estimate − mine ≥60) | **77%** | **78%** |
| …knowable with the whole-life estimate | 92% | 95% |
| died, behind & knowable / behind & unknowable | 63% / 69% | 71% / 77% |
| knowable-behind starts per started fight / unknowable | 15% / 4% | 17% / 5% |

Per map, knowable share of behind-starts (TOP / FIELD): dm3 74 / 74%, dm2 80 / 80%, e1m2 76 / 76%, schloss 81 / 82%. Per player: 76–81% for every player in both groups. What was heard before a knowable bad read (TOP / FIELD): RA 38 / 34%, YA 39 / 40%, mega only 12 / 14%, nothing but a trade 10 / 12% — death rates 60–66% (TOP) vs 69–73% (FIELD) in every row.

Reading: the simple model (fresh spawn + what you heard − what you dealt) describes the enemy's stack within 60 eff three times in four for everyone; 3 of 4 behind-starts are made with the information available, for everyone. The "hidden stack" excuse covers 1 in 11 fights, equally. Top players are not better stack-readers by this score; they survive the same bad read 8 points more often, which §2.1 traces to the RL.

### 2.8 Same-team control

Only rows where the player's team in that game had both a TOP and a FIELD player (4,112 team-games: same opponents, same lock state, same floods):

| | TOP | FIELD |
|---|---|---|
| first damage (both alive ≥3 s) / with RL / with no launcher | 61% / 60% / 62% | 49% / 49% / 50% |
| behind-starts with a cue / died given behind + cue / knowable | 86% / 64% / 77% | 85% / 73% / 78% |
| attacked the RA-or-MH taker ≤15 s → died | 36% → 54% | 28% → 67% |
| took RA/YA/MH ≤15 s after an enemy take / idle / found first | 31% / 5% / 6% | 23% / 9% / 8% |
| item ≤15 s after an enemy death (all / at ≤120 eff) | 37% / 37% | 27% / 26% |
| feed: entered X / engaged / landed first / died ≤20 s | 10% / 55% / 57% / 49% | 10% / 52% / 46% / 61% |
| RA / YA / MH ≤3 s | 58% / 56% / 32% | 58% / 47% / 32% |
| quad: contested / took / ≥150 at spawn | 75% / 20% / 34% | 72% / 8% / 23% |
| dm3 quad: in room at 0 / left in last 10 s / RL at 0 / took given in room | 27% / 42% / 61% / 65% | 16% / 54% / 42% / 39% |

Every gap survives; every non-gap stays a non-gap.

### 2.9 Per-player spread (the coach's shortlist)

| player | group | first damage | item ≤15 s after enemy death | attacked RA/MH taker → died | YA ≤3 s | quad took given alive | landed first on a teammate's killer |
|---|---|---|---|---|---|---|---|
| bogojoker | TOP | 69% | 40% | 42% → 47% | 61% | 21% | 64% |
| sane | TOP | 63% | 35% | 36% → 55% | 58% | 17% | 58% |
| yeti | TOP | 62% | 37% | 37% → 55% | 59% | 22% | 58% |
| zorak | TOP | 62% | 38% | 36% → 55% | 61% | 17% | 58% |
| chris | TOP | 61% | 36% | 35% → 54% | 64% | 15% | 57% |
| blood_dog_d_p | TOP | 60% | 37% | 36% → 55% | 52% | 25% | 56% |
| war | TOP | 60% | 37% | 33% → 56% | 56% | 17% | 56% |
| dusty | TOP | 59% | 33% | 33% → 60% | 53% | 12% | 54% |
| blaze | TOP | 59% | 35% | 34% → 53% | 54% | 18% | 55% |
| coj | TOP | 54% | 35% | 33% → 57% | 55% | 19% | 51% |
| namtsui | FIELD | 57% | 28% | 32% → 65% | 46% | 8% | 54% |
| nico | FIELD | 57% | 36% | 33% → 61% | 54% | 12% | 53% |
| pharm | FIELD | 55% | 31% | 32% → 67% | 50% | 11% | 52% |
| viag | FIELD | 54% | 32% | 28% → 55% | 55% | 13% | 51% |
| ledge | FIELD | 53% | 22% | 31% → 73% | 42% | 5% | 49% |
| gflip | FIELD | 53% | 26% | 28% → 63% | 51% | 9% | 48% |
| phylter | FIELD | 52% | 30% | 29% → 67% | 50% | 14% | 49% |
| foobhar | FIELD | 51% | 27% | 30% → 71% | 49% | 11% | 47% |
| stedanko | FIELD | 50% | 26% | 26% → 67% | 46% | 9% | 44% |
| omicron | FIELD | 49% | 30% | 26% → 61% | 53% | 11% | 46% |
| pred | FIELD | 48% | 25% | 26% → 67% | 39% | 7% | 43% |
| cronus | FIELD | 47% | 31% | 28% → 63% | 53% | 9% | 44% |
| evalcat | FIELD | 38% | 15% | 23% → 78% | 25% | 2% | 35% |
| schotty | FIELD | 36% | 16% | 21% → 81% | 34% | 2% | 33% |

nico and namtsui already land first like top players; the perception work is at the bottom of the table (schotty, evalcat, pred, cronus, ledge) and it is the same three habits each time: landing first, converting a frag into an item, and the yellow timer.

## 3. Coachable statements and drills

Each statement is a measured difference in the same state (same map/weapon/stack where it matters), per the doctrine. Numbers are TOP vs FIELD unless stated.

1. **"Red heard + no RL = not your fight."** [P→D] A fight started 60+ behind with the cue in your ears ends in death 76% (TOP) / 78% (FIELD) of the time without the RL, and 36% / 43% with it. The top players are in those fights with the RL 30% of the time, the field 17%. Drill: in pickups, one rule for a week — after an enemy armor sound, you may start only with the RL in hand or with a teammate already shooting him; otherwise go to the other item. Check with the per-night list (`fights` rows with `started`, `gap ≥ 60`, `cue_armor`, `my_rl = 0`).
2. **"Sound → number, out loud."** [P] The knowable estimate (100 + what you heard − what you dealt) matches the enemy's real stack within 60 three times in four, for everyone; "hidden stack" is 1 fight in 11. Drill: after every RA/YA/MH sound in a demo review, say the enemy's number (300 / 250 / 200) and your own before the fight starts; the coach checks it against the demo. Goal: make the field's 77% "knowable bad read" a number they say before they commit, not after they die.
3. **"The red he took is your yellow."** [P→D] After an enemy red, top players take an armor or mega within 15 s 31% vs 24% (schloss YA 22% vs 15%, dm3 MH 12% vs 8%); after an enemy mega, they take the red 10.5% vs 6.7% on dm3, 17% vs 12% on dm2. Drill: pair the calls per map — "their red → our yellow/mega now", "their mega → red is ours in N s" — and have one player own the call.
4. **"A frag is a green light, not a break."** [P→D] After an enemy dies, top players take a major item within 15 s 37% vs 27% (e1m2 24% vs 14%, schloss 41% vs 30%), whether or not they made the frag. Drill: every time a kill shows in the feed, the nearest player names the item he is going to; review the per-night conversion rate (37% is the bar; schotty 16%, evalcat 15%, ledge 22% are the gaps).
5. **"Land first."** [P→X] Top players land the first damage in 61% of fights vs 50%, with the shotgun as much as with the RL (61% vs 50%), naked (62% vs 51%), behind (58% vs 45%). Landing first turns a 51–63% death into a 39–49% one. Drill: demo review of every fight where the enemy landed first (`started = 0`): what sound or feed line told you he was there, and was the weapon up at the corner? Aim is trained separately; this drill is about knowing where he is before he appears.
6. **"Attacking a fresh red is 1.5× the risk of anything else, even for the best."** [D] Within 15 s of an enemy red, attacking him kills 57% (TOP) / 68% (FIELD) vs 37% / 46% for doing anything else; from ≤120 eff it is 69% / 76%; solo from elsewhere at ≤120 it is 70% / 80%. Drill: the "two conditions" rule — fresh red-taker only with ≥150 eff and RL, or with a teammate on him (death with a teammate also shooting him: 56% TOP / 66% FIELD; alone: 59% / 73%).
7. **"Never stand still after a sound."** [P→D] After an enemy red or mega, the field does nothing in the next 15 s 8–9% vs 5%, and gets found first by the taker 8–9% vs 6%. Drill: after any enemy armor/mega sound, the next 3 s must contain a move — toward a teammate, toward the other item, or into a known angle on his exit.
8. **"Quad: stay in the room."** [P→D] dm3: of players who were in the quad room in the last 10 s, 54% of the field walk out before it spawns vs 43%; a player in the room at 0 takes it 64% vs 40%, 75% vs 55% with the RL. Attendance and early entry are already equal (75% vs 72%; 75% vs 76%). Drill: one teammate counts −15 / −10 / −5 on voice; whoever is in the room at −10 does not leave; the taker arrives at −5 with the RL and ≥150 (TOP ≥150 at spawn 34% vs 23%) — per the doctrine, prepared takes, not attendance.
9. **"The yellow has a timer too."** [P] RA on the timer is equal (≤3 s: 59% vs 58%; every player 52–62% except evalcat); YA is not (56% vs 47%; dm2 32% vs 26%, dm3 70% vs 64%, schloss 63% vs 58%; schotty 34%, pred 39%, ledge 42%). Drill: call the yellow like the red (20 s after the take), one owner per yellow per map.
10. **"Be at the red when it comes up."** [D, with P] Top players take 16% of the reds and megas they are alive for vs 11% (≤3 s: 10% vs 7%), including when they need it (≤120 eff: 11% vs 7%). Drill: in review, list every red/mega respawn where the player was ≤120 eff and not in the room ("arrive" rows with `my_eff ≤ 120`, `in_loc1 = 0`); the question is the route decision at −10 s.

## 4. Caveats and confounds (read before quoting)

- **Audibility is assumed.** Every RA/YA/MH pickup is treated as heard by every enemy; in the game the sound attenuates with distance and a fight can mask it. Trades count as cues. The "knowable" model ignores what teammates say on voice (NA teams talk on mm3); a teammate had hit the foe in the last 20 s in 64% (TOP) vs 66% (FIELD) of behind-starts, so comms-knowable is higher than 77% for both.
- **10 s state resolution.** Locations come from `player_state10s`; "in the item area", "entered X", "in the area before the take" miss players who pass through between samples, and the area is the server's `.loc` name (narrow: only 1–2% of enemy takes had the reacting player inside the item's named area). The feed "move toward X" measure is therefore weak — it shows no difference, which may be resolution rather than truth.
- **"First damage" and "attacked" are landed hits.** Misses are not in the data. A measured "he landed first" can be "I shot first and missed".
- **Fights are per player, clustered with a 4 s gap**; the foe is the other party of the first event; multi-enemy fights are counted once; death is inside the window +1.5 s.
- **Stored quad `contested` flag.** In a 40,000-row sample of `quad_tracks` (dm3) 17,337 of 32,111 "contested" rows (54%) never have a quad-room location in the last 10 s while 16,422 of them were within 650 u, so the flag in `quad_approach`/`quad_tracks` behaves like the old 650 u radius rule, not the doctrine room rule; the §2.4 room numbers (dm3 tracks) are the doctrine-consistent ones, and the distances d10..d0 and `enter_before_ms` are as stored. Quad tracks exist only for dm3 NA games (438).
- **Weapon and stack are confounded with group.** Over all alive samples TOP hold the RL 44% vs 29%, mean eff 136 vs 120, ≥150 eff 33% vs 24%, red 19% vs 12%, quad 7% vs 3%, alive 96.3% vs 94.8%. Every "died" number is partly that. The same-team control (§2.8) removes the team's state, not the player's own stack; the conditional rows (no RL, ≤120 eff, behind) are the fair comparisons.
- **Groups are defined by wins-above-replacement**, i.e. by outcome. Any metric that correlates with winning will separate the groups to some degree by construction; the informative part is which perception metrics do NOT (cue share, knowable share, red stopwatch, quad attendance and early entry, moving toward a dead teammate) versus which do (landing first, conversion, being present at spawns, staying in the quad room, idle/found-first).
- **Pooled tests** ignore clustering by game and player; p-values are indicative. blood_dog_d_p is 29% of TOP rows; per-player medians are given everywhere and agree with the pooled numbers. `mate_hit` etc. were added in the second run; counts are identical to the first.
- **Per map**: e1m2 has no red; dm2 has two; schloss and dm3 one. The MH `available_from` (20 s after the holder is back at 100) is taken from the table as stored.
- Mega-decay "wait" hypothesis: not supported by the timing table (TOP attack the mega-taker both sooner and later, with the same curve shape); the data cannot see a player deliberately waiting unless he attacks later.

## 5. Files and reproduction

- `perception_study.py` — extracts every row above from the database (≈4 min; writes `perception_results.json`, 1.7 GB). `python3 perception_study.py 20` runs a 20-game smoke test.
- `perception_agg.py` — builds all tables (≈2.5 min, 8.6 GB RAM) → `perception_tables.md` (pooled, per map, per player, same-team control, plus the OTHER reference line).
- Per-night use: filter `fights`, `react`, `conv`, `arrive` rows by `gid` to get the timestamps behind each statement above (e.g. every "solo naked attack from elsewhere on a fresh red-taker" for one player in one game).

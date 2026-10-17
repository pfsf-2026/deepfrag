# Floods and coordination at 1-second resolution (NA 4on4, TB4 maps)

Study question: do the best NA teams "flood" (converge on one objective inside a few seconds), who goes first into
enemy-held rooms, how closely players pair, and does coordinated arrival break locks faster than arriving one by one.
Project lead's hypothesis: "when locked, concentrate on one spot (e.g. flood the tele on dm2) — dividing your approach
elongates the lockdown." The 10-s data could not decide it. This pass works from demo positions at 1 s (room entries
at full resolution, spawns at 100 ms).

## Sample and method

- 60 games since 2026-05-30 with >= 2 TOP-roster players: dm3 15, dm2 16, e1m2 14, schloss 15 (every game with
  >= 4 TOP players in the hub since May, plus the most recent 2-3-TOP games to fill each map; the eight cached games
  included). 120 team-games; 106 have >= 2 TOP players (88 with exactly 2, 13 with 3, 5 with 4), 14 have 0-1 TOP.
  Aliases folded (george/whodat/igor/tardface = war, pierre = dusty, venator/vyper = nico, chr1s/chris2pl = chris).
- Lock margin each second: M = (enemy alive stack − own) + 100·(enemy RLs − own) + 100·(enemy reds − own).
  Locked = M >= 500 (dm2/dm3/schloss) or >= 240 (e1m2). A lock *episode* starts at M >= threshold and ends when M stays
  below half the threshold for 3 s; episodes >= 30 s are analysed (326 of them: dm3 77, dm2 82, e1m2 92, schloss 75;
  9 unbroken at the end of the match). Median episode 50 s, p75 80 s, longest 385 s. Teams are locked 10.5-14.4 % of
  their seconds depending on map (median team-game 11.6 %). Mean alive players during a lock is 3.7 — KTX respawns
  are near-instant, so "alive count" is a weak control on these maps.
- Room entry = a change of the analyzer's location (locTable) at full resolution, debounced (a bounce back inside 1 s
  is dropped), spawn placement excluded. **Room flood** = >= 3 alive teammates entering the same room inside 5 s.
  **Item flood** = >= 3 teammates arriving inside 350 u of a major item (RA/YA/mega/quad/RL/LG) that is up or due
  inside 10 s. The brief's 700-u "same item/enemy" rule was tried and dropped: on dm2 three teammates are inside
  700 u of *some* enemy or of big YA most of the time, so it fired 300+ times a game and measured brawling, not
  convergence. Room and item floods inside 5 s are merged into one event (5,798 floods; 48 per team-game, 34 of them
  room floods).
- Validation: definitions were spot-checked on two dm2 games (event lists against the kill feed and item takes);
  no visual demo review was done. Statistics are plain shares, Spearman, a tiny OLS, and two-proportion z-tests.

## 1. Floods: how often, where, what happens next

Rate per team-minute (all floods / room floods only): dm3 2.05 / 1.63, dm2 2.71 / 1.51, e1m2 2.06 / 1.76,
schloss 2.81 / 1.94. TOP-heavy teams 2.43 vs others 2.30 — no difference. Locked teams flood slightly more than free
ones on the two small maps (dm2 3.04 vs 2.70, schloss 3.41 vs 2.78) and not on dm3/e1m2 (2.14 vs 2.06, 1.94 vs 2.11).

Room-flood targets (count over 60 games; "locked" = the flooding team was locked at the time):

| map | all floods | while locked |
|---|---|---|
| dm3 | Ring 276, bridge.low 252, Quad 90, water 89, RA.low 86 | bridge.low 51, water 25, Ring 23, hill 9 |
| dm2 | NG 300, low.RL 190, Quad.low 140, big 95, tele.YA 94 | low.RL 34, NG 21, big 18, tele.high 16, tele.YA 16 |
| e1m2 | cross 214, GL 173, Quad 148, GL.stairs 101 | cross 35, bridge 16, GL 15, Quad 12 |
| schloss | cathedral 253, tower.RL 187, Quad.ledge 178, RA.low 159 | cathedral 45, tower.RL 28, Quad.ledge 17, Quad 15 |

Item floods: dm2 RL 512, YA 510, RA 367, quad 177; schloss YA 508, RL 335, mega 214, RA 213; e1m2 YA 240,
quad 105; dm3 mega 182, YA 111, quad 98, RL 86. The dm2 "flood the tele" call shows up (tele.YA/tele.high 32 locked
floods) but low.RL (34) is the most-flooded room under a dm2 lock.

Outcomes in the 15 s after a flood, against every other 15-s window in the same lock state with no flood in the
previous 15 s (frags for / against the flooding team; dM15 = margin change, negative = the flooding team gained):

| state | windows | frags for | against | net | items taken | dM15 |
|---|---|---|---|---|---|---|
| not locked, flood | 5,031 | 2.83 | 2.72 | +0.11 | 1.64 | +51 |
| not locked, baseline | 61,624 | 3.15 | 2.41 | +0.74 | 1.66 | +30 |
| locked, flood | 767 | 1.30 | 4.78 | −3.48 | 1.44 | −177 |
| locked, baseline | 7,478 | 1.21 | 4.30 | −3.09 | 1.34 | −173 |

Floods are followed by *more* deaths than quiet windows, with or without a lock, at the same number alive
(4 alive, locked: 4.72 against after a flood vs 4.33 baseline) and for TOP-heavy and other teams alike. That is not a
verdict on flooding: a flood is a team moving into contact, and the baseline includes every quiet second. The fair
comparison is the next section (entering the *same* kind of room alone vs in a group). Floods are led by whoever is
in front: of 767 locked floods the first entrant was TOP 402, FIELD 257, other 108, in line with how many of each
were alive. Every roster player joins 71-82 % of the floods he is alive for (TOP 77 %, FIELD 76 %) and leads 20-30 %
(BLooD_DoG 30 %, chris 28 %, war 22 %, blaze 20 %).

## 2. The hypothesis: does concentrating break locks faster?

### 2a. Team bunching over the lock — no relation to lock length (same answer as at 10 s)

For each of the 326 episodes, coordination was measured in the **first 30 s** (so the break itself is not in the
measurement) and compared with how long the lock lasted *after* those 30 s:

| metric, first 30 s | low third | middle | high third | Spearman with remaining lock |
|---|---|---|---|---|
| mean pairwise distance (874 / 1030 / 1212 u) | median 23 s left, 98 % broke | 20 s, 98 % | 19 s, 95 % | −0.01 |
| share of time >= 3 inside 700 u (17 / 35 / 55 %) | 20 s, 98 % | 28 s, 94 % | 17 s, 99 % | 0.00 |
| floods per minute (1 / 3 / 5) | 20 s, 96 % | 22 s, 97 % | 23 s, 98 % | +0.03 |

Controlling for mean alive and lock depth (OLS, standardized): one SD more bunching changes the remaining lock by
−4.6 s (>= 3 inside 700 u), −6.3 s (floods/min), +4.5 s (pairwise distance) — all inside noise; lock depth is what
matters (+16 to +18 s per SD of mean margin). Per map the sign flips (bunched teams stay locked longer on dm3 and
e1m2, shorter on dm2 and schloss). Whole-episode metrics: Spearman +0.02 to +0.04. Per-second hazard inside
episodes, P(lock ends inside 30 s): flood in the last 10 s 43.4 % (n = 9,894 s) vs no flood 45.0 % (12,301);
>= 3 clustered now 44.2 % vs not 44.3 %; by pairwise-distance quartile 43-46 %. **General bunching does nothing
measurable to lock length, at 1 s as at 10 s.**

### 2b. Entering the enemy's room as a group — a small positive signal

The sharper test: entries into a room that holds >= 1 alive enemy, by how many teammates entered inside 5 s
(nobody already inside; inside lock episodes; n = 3,619):

| group entering | n | lock ends <= 30 s | <= 60 s | net frags 15 s | margin at entry |
|---|---|---|---|---|---|
| 1 | 2,498 | 46 % | 73 % | −3.37 | 498 |
| 2 | 896 | 46 % | 73 % | −3.38 | 471 |
| 3+ | 225 | 50 % | 75 % | −3.52 | 491 |

3+ vs 1-2: +4 points, z = 1.2 (not significant). Stratified by lock depth, time since the lock started, alive count,
map and enemies in the room, the pooled difference is +3 to +4 points every time. Using the instantaneous lock
definition instead of episodes: 45-47 % vs 37-38 % (z ≈ 1.8). Per locked second (size of the last contested entry
inside 10 s → lock ends inside 30 s): no entry 31.2 % (n = 3,902 s), solo 47.1 % (12,302), pair 45.6 % (4,764),
3+ 52.0 % (1,227); z = 3.6 but the seconds are autocorrelated, so that is optimistic. Group entries cost *more*
frags (net −3.5) — the lock ends because the enemy bleeds stack, not because the flood wins the fight.

The one strong cell: when **2+ enemies hold the room** and 3+ go in, the lock ends inside 30 s 77 % of the time
(n = 39) vs 47 % for 1-2 entrants (n = 298), z ≈ 3.5. That is a sub-cell found after several cuts; treat it as a
lead for the next 60 games, not a result. Per map (3+ vs 1-2): schloss 57 vs 44 %, e1m2 59 vs 49 %, dm3 43 vs
43 %, dm2 31 vs 48 % (n = 39, the dm2 reversal is also small-sample).

### 2c. Dividing the approach — no measurable cost for pairs

5-s windows in which >= 2 teammates entered enemy-held rooms, locked: 2 players into one room 35 % lock-end
(n = 98) vs 2 players into different rooms 40 % (409); 3 players into one room 69 % (n = 16) vs split 41 % (266),
z ≈ 2.2; 4 players: 2 windows, no reading. Splitting a pair costs nothing; splitting a trio looks costly but rests on
16 events.

### 2d. What actually ends a lock (last 20 s of 317 broken episodes)

The locked team killed a 150+ enemy in only 12 % of breaks (2+ such kills: 2 %) though it scored some frag in 87 %.
It took YA in 62 %, an RL in 50 %, mega 32 %, RA 29 % (dm2 68 %), quad 9 % (schloss 19 %). Its alive stack rose
+82 on average while the enemy's alive stack fell 154; in 62 % of breaks the enemy's loss was the larger part. A 3+
group entry into an enemy-held room happened in the window in 21 % of breaks (schloss 34 %, e1m2 22 %, dm3 14 %,
dm2 13 %). Breaking a lock is a stack race — chip damage plus re-arming — far more often than a decisive kill.

### Verdict on "flood the spot, don't divide"

- As *team bunching* (being close, moving together, flooding rooms): **refuted as a lever** — no relation to lock
  length in 326 episodes at 1 s, with and without controls, on every map.
- As *3+ entering the room the enemy holds*: **weak support** — +4 points of lock-ending inside 30 s overall
  (not significant at the event level), with a large but thin effect when the enemy is bunched too (77 vs 47 %,
  n = 39). Flooding an empty room (the majority of floods) is just travelling together.
- As *dividing elongates the lock*: **not supported** for pairs (split pairs did marginally better); a hint for
  trios (69 vs 41 %, n = 16). The data cannot tell at this sample size.
- The honest instruction the data supports: under a lock, go where the enemy's stack is, go together if three are
  available, and measure the result in stack taken off them and items taken, not in frags (you will still lose the
  frag count in the next 15 s).

## 3. Who goes first into an enemy-held room

35,505 contested entries; 11,625 had a teammate follow inside 5 s; 5,085 of those pairs were one TOP and one
FIELD player. **TOP went first in 51.2 %** (z = 1.7 against 50 %); dm3 50, dm2 54, e1m2 51, schloss 50 %; locked
52 %. Per player, every roster member leads 48-53 % of the pairs he is in. First-in is not a role anyone takes or
avoids — it is whoever is in front.

- Cost of going first: survival 10 s after entry 43 % for the first entrant vs 50 % for the second (z = 12); the
  first also gets slightly more kills (0.63 vs 0.57 inside 10 s).
- Stack decides: first entrants with < 100 stack survive 25 % (RL 20 %), 100-150 39 %, 150-220 68 % (RL 64 %),
  220+ 76 %. In mixed pairs the first entrant has *less* stack than the follower in 59 % of cases; RL/LG share is
  28 % for both. The stacked player is not the one going first.
- TOP vs FIELD at the same stack: < 100 → 28 vs 22 %, 100-150 → 40 vs 37 %, 150+ → 75 vs 65 %. The TOP edge
  (46 vs 37 % overall, z = 8.5) is about one third stack and two thirds execution at equal stack.
- Solo entries (nobody follows, nobody inside; 19,770): TOP 43 %, FIELD 36 %, other 37 % survive 10 s.
- Players: bogojoker leads 53 % of his pairs, enters with 142 stack and RL/LG 43 %, survives 50 %; yeti 127 / 33 %
  / 49 %; blaze 132 / 33 % / 49 %; war and BLooD_DoG 123 / 32 % / 44-46 %; sane 129 / 32 % / 44 %. On the FIELD side
  viag 134 / 31 % / 51 % and nico 119 / 33 % / 44 % enter like TOP players; cronus 118 / 24 % / 36 %, namtsui
  105 / 20 % / 36 %, schotty 98 / 5 % RL / 24 % and pred 94 / 15 % / 32 % go first as boomsticks and die.

## 4. Pairing

Nearest alive teammate, per alive second: TOP median 579 u (25 % inside 350 u, 61 % inside 700, 6 % beyond 1,400);
FIELD 554 u (26 %, 64 %, 5 %); unrostered 585 u. Identical locked or not. The best players do not pair tighter
than the field; per player the paired share (<= 700 u) runs 57 % (blaze) to 66 % (evalcat).

Deaths per minute alive by nearest-teammate distance (all / locked):

| nearest teammate | TOP | FIELD | TOP locked | FIELD locked |
|---|---|---|---|---|
| <= 350 u | 2.74 | 3.17 | 5.24 | 5.65 |
| 350-700 | 2.76 | 3.09 | 5.28 | 5.50 |
| 700-1,400 | 3.28 | 3.93 | 6.44 | 6.79 |
| > 1,400 | 3.61 | 4.17 | 7.21 | 7.07 |

Being inside 700 u of a teammate goes with 20-25 % fewer deaths per minute (part of that is that fights pull
teammates together, so it is a correlation, not a measured cause). A lock doubles everyone's death rate at every
distance. "Alone into 2+" (>= 2 enemies inside 700 u, no teammate inside 700 u): TOP 9.8 % of alive seconds,
FIELD 9.3 %, other 9.6 % — about 6 s of every alive minute for everyone, 10 % under a lock for both roles. Of those
seconds 33 % (TOP) / 37 % (FIELD) end in death inside 3 s, against 26 % / 29 % when a teammate is inside 700 u in the
same 2+ situation. Per player, alone-into-2+ runs 8.7 % (viag) to 10.2 % (BLooD_DoG, pred).

## 5. The first 5 s after a spawn (26,887 spawns that lived >= 2 s)

| | TOP | FIELD |
|---|---|---|
| first movement (median / p75) | 300 / 600 ms | 400 / 600 ms |
| speed over the first 2 s | 360 u/s | 336 u/s |
| left the spawn room inside 5 s | 87 % (median 1.5 s) | 87 % (1.6 s) |
| moved toward a teammate in the first 3 s | 42 % | 41 % |
| moved toward an available major item | 25 % | 23 % |
| an enemy inside 700 u at the spawn | 63 % | 64 % |
| lived >= 14 s (free / locked) | 38 / 28 % | 39 / 31 % |

TOP players start about 100 ms sooner and run 7 % faster off the spawn (sd ≈ 160 u/s, n = 12.7k vs 9.6k, a real but
small gap); direction choices are the same. Under a lock (5,633 spawns, all roles), what went with surviving 14 s:
moved toward a teammate 31 % vs 28 % (z = 2.4); toward an item 32 vs 28 %; still in the spawn room after 5 s 19 %
(n = 852) vs left 31 % (z = 6.6 — partly reverse causation: the camped stay put); first move inside 300 ms 28 % vs
after 600 ms 31 % (no gain from a faster start). Distance to the nearest teammate at the spawn made no difference
(28-30 % at every distance); distance to the nearest enemy did: 23 % survive with an enemy inside 350 u, 27 % at
350-700, 33 % at 700-1,400, 50 % beyond 1,400. First room entered after a locked spawn and survival to 14 s:
dm3 Ring 25 %, lifts.below 24 %, hill 40 %, YA 31 %, window 44 %; dm2 big 38 %, tele.YA 39 %, NG 12 %, low.RL 31 %;
e1m2 GL 16 %, Quad.stairs 21 %, MH.entry 38 %, start.stairs 52 %; schloss cathedral 27 %, tower.RL 31 %,
Quad.ledge 21 %, tower.entry 33 %.

## 6. Coachable statements

1. **[DECISION] Breaking a lock is a stack race, not a kill.** In the 20 s before 317 locks broke, the locked team
   killed a stacked (150+) enemy 12 % of the time but took YA 62 %, an RL 50 %, mega 32 %; the enemy's alive stack
   fell 154 on average. Under a lock the objective is re-arm and chip, and the scoreboard will still read −3 for
   the next 15 s.
2. **[DECISION] Flood the enemy, not the spot.** 3+ entering the room the enemy holds ends the lock inside 30 s
   50 % vs 46 % alone or in twos (+4 points after controls, not yet significant); with 2+ enemies in that room 77 %
   vs 47 % (n = 39). Flooding an empty room is travelling; it moved nothing.
3. **[DECISION] Not engaging keeps you locked.** Locked seconds with no entry into an enemy-held room in the last
   10 s end the lock inside 30 s 31 % of the time; after any entry 46-52 %.
4. **[DECISION] Send the stack first.** First entrants survive 43 % vs 50 % for the follower, and stack decides
   (25 % at < 100, 76 % at 220+); yet in TOP-FIELD pairs the first entrant has less stack than the follower 59 % of
   the time. Nobody owns "first in" (TOP goes first 51 %); make it the stacked player's job.
5. **[EXECUTION] At equal stack, TOP players survive the first entry 3-10 points more** (28/40/75 % vs 22/37/65 %
   at < 100 / 100-150 / 150+). Schotty (98 stack, RL 5 %, survives 24 %) and pred (94, 15 %, 32 %) go first as
   boomsticks; bogojoker (142, 43 %, 50 %) is the model.
6. **[PERCEPTION] Inside 700 u of a teammate the death rate is 20-25 % lower** (TOP 2.76 vs 3.61 per minute;
   FIELD 3.09 vs 4.17) and alone-into-2+ ends in death inside 3 s 33-37 % of the time vs 26-29 % with a mate near.
   Everyone, TOP included, spends ~6 s of every alive minute alone against 2+.
7. **[DECISION] Off a locked spawn, run from the enemy's sound, not toward the teammate.** Survival to 14 s is
   28-30 % at every teammate distance but 23 % with an enemy inside 350 u and 50 % beyond 1,400 u; moving toward a
   teammate adds 3 points. Staying in the spawn room 5 s: 19 % survive.
8. **[DECISION] First room after a locked spawn, per map:** dm2 avoid NG (12 % live) for big/tele.YA (38-39 %);
   e1m2 avoid GL (16 %) for MH.entry (38 %) or start.stairs (52 %); dm3 Ring 25 % vs hill 40 % / window 44 %;
   schloss Quad.ledge 21 % vs tower.entry 33 %.
9. **[EXECUTION] FIELD players leave the spawn 100 ms later and 7 % slower** (336 vs 360 u/s over 2 s); faster
   starts did not raise survival by themselves (28 % vs 31 %), so this is a movement drill, not a survival lever.

## Caveats

- 60 games is modest and TOP-heavy: 106 of 120 team-games have >= 2 TOP players, so "TOP-heavy vs others" rests on
  14 team-games and TOP players mostly have TOP teammates.
- Room boundaries are the analyzer's; a flood into "bridge.low" on dm3 is three players crossing one label inside
  5 s. Most floods are pack movement, not a called play — the demo cannot tell the two apart.
- Lock episodes use hysteresis (end when M < half the threshold for 3 s); respawns are near-instant, so the alive
  count is almost always 3-4 and is a weak control.
- Per-second tests are autocorrelated; their z-values are optimistic. The decisive cells (2+ enemies in the room,
  3 players into one room) hold 16-39 events and were found after several cuts.
- All "survival" and "death rate" numbers are correlations with position, not measured causes.

## Files (scratchpad)

- `fetch_manifest.py` → `fours_since_may.json` (2,704 TB4 4on4 games since May); `select_games.py` → `selected_games.json`
- `parse_all.py` (downloads + analyzer, cached as `full_<gid>.json`, 60 games); `compact.py` → `compact_<gid>.json`
- `floods.py` (definitions, Game class), `run_floods.py` → `floods_rows.json`, `hazard_rows.json`, `baseline_rows.json`, `pairing_rows.json`
- `report.py` → `report_out.txt`; `contested.py` → `contested_out.txt`; `contested2.py` → `contested2_out.txt`;
  `lock_ends.py` → `lock_ends_out.txt`; `extra_out.txt` (per-map lock shares, z-tests)

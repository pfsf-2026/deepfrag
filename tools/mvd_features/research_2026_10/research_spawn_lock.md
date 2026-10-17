# Spawn and lock routines: TOP vs FIELD (NA 4on4, TB4 maps, games since 2025-01-01)

Scope: 1,415 4on4 games (dm3 441, dm2 404, e1m2 292, schloss 278), 637,278 player lives with a known spawn time
(TOP 225,151 lives; FIELD 299,859; everyone else 112,268). Lock margin M and per-map thresholds exactly as in
`lock_spawn.py` (dm3 511, dm2 487, e1m2 238, schloss 433 = 85th percentile of M). "Chained" = died inside 14 s of
spawning. Rosters as given (TOP 10 players, FIELD 14).

Scripts (scratchpad): `sl_build.py` (records, 27 s), `sl_wait_check.py` (respawn-wait validity), `sl_demo_wait.py`
(exact sp/d arrays from the 8 cached demos), `sl_report.py` -> `sl_report_out.txt`, `sl_supp.py` -> `sl_supp_out.txt`.
Nothing in the repo or the database was modified.

## TL;DR

1. **Top players do not survive locked spawns any better than the field.** Chained-death rate under lock: dm3 67% vs 66%,
   dm2 76% vs 76%, e1m2 72% vs 74%, schloss 75% vs 75%; killed inside 6 s 38/36, 51/50, 41/42, 45/43. Same result
   inside mixed teams (TOP and FIELD on the same roster) and as an unweighted mean of per-player rates (72% vs 72%).
   "I can't even spawn" is true at every level; the lock is a map/stack state, not a skill gap.
2. **What differs is what the 14 s produce.** TOP take an item inside 14 s in 34/39/33/40% of locked spawns vs
   28/34/23/29% (dm3/dm2/e1m2/schloss), deal 45/47/55/55 damage per locked spawn vs 33/35/42/38 (+30-45%), frag inside
   14 s 15/11/20/16% vs 11/9/16/12%. "Zero-value" chained spawns (no item, no damage) are 11-18% of TOP's chained
   spawns vs 18-25% of FIELD's. Time-to-first-item is identical (median 7.3-7.7 s); the difference is going for one at all.
3. **Nobody waits to respawn, and waiting does not help.** Exact demo data: median 0.88 s, TOP p95 1.44 s, FIELD p95 2.25 s.
   DB-derived (validated below): under lock TOP wait >=2 s on 3.4% of deaths, FIELD 6.3% (one player, namtsui, 18%).
   Chained rate is flat across wait buckets (71-74%) for both groups and for every habitual waiter.
4. **Streaks and locks are ended by the top players at 1.3-1.4x their roster share, and they also do 52-58% of the
   wear-down damage on the streaker** (lift 1.33-1.42; FIELD 0.65-0.74). The finishing frag comes from a spawn-level
   player (eff <=100: 49-82%), 12-36 s after their own spawn, who had already died to the streaker (80-85%), often with
   the shotgun (FIELD 39-50% of their finishes). Lock-break frags are a shotgun fight: 43-52% SG, attacker eff <=100 in
   61-84% of them, 41-52% fired inside 14 s of the attacker's spawn.
5. **Top players do not prevent locks.** Share of game time locked is the same (TOP 14.4-15.2%, FIELD 15.0-15.3%); in the
   30 s before a lock their share of the team's deaths equals their roster share (37-41% vs 38-41%); they die holding
   the RL *more* (26-44% vs 21-33%) because they carry it more. Locks arrive after the enemy takes RA (dm3 94% of entries vs a 49%
   base rate for any 30 s window; schloss 87% vs 54%; dm2 95% vs 79%) and mega (43-67% vs 34-57%); quad precedes only
   32-38% (base 25%).

## Method notes and caveats (read before quoting)

- State is sampled every 10 s; "area at the first sample" is 0-10 s after the spawn (median ~5 s) - the same quantity the
  pooled study labelled "+10 s". "10-20 s after spawn" is the next sample and is only defined for players still alive.
- Area labels are coarse (e.g. dm3 "RL", "water"); routes inside an area are invisible.
- Team quality: TOP players have on average 1.07 other TOP teammates, FIELD players 1.35 (FIELD players play *with* the
  top players more than the top players do). Every TOP-vs-FIELD comparison was repeated on mixed teams only
  (>=1 TOP and >=1 FIELD on the roster); all directions and magnitudes hold, so the numbers below are the pooled ones
  unless stated.
- Weighting: blood_dog_d_p is 19k of the 59k TOP locked spawns; cronus/schotty/namtsui are 34k of 71k FIELD. The
  per-player table (section 1) shows the within-group spread; group means of per-player rates match the pooled rates.
- Respawn wait = (t_next_death - vic_tss_next) - t_prev_death. Validation: at the first 10 s sample after a derived
  spawn the player is flagged alive 384,875/384,875 times (100%); but inside derived waits >=10 s the player is
  demonstrably alive (dealing/taking damage or taking items) 97-98% of the time, i.e. `vic_tss` is sometimes
  under-measured by 10-40 s. Waits in [1.5, 10) s are contradicted only 1-5% of the time. So derived waits >=10 s
  (1,113 of 637k) and any wait with in-interval activity are dropped. Cross-check with the exact `sp`/`d` arrays of
  the 8 cached demos (3,680 death->spawn pairs, 33 pairing violations): the distributions agree (table in section 2).
- Lock-break attribution uses the 30 s before the first sample with M < THR/2 (as in the pooled study); the window
  contains actions after the real turning point too. "Lift" = share of actions by a group / the group's share of the
  locked team's roster; it does not control for TOP having the better stack or the RL going in, which is part of
  being TOP.
- Streak = one player, >=6 enemy frags without dying (teamkills/env excluded). Where a streak ends is the streaker's
  area at the nearest 10 s sample (+-5 s). Only ~26% of streaks end with the victims locked by the margin definition:
  a streak is a personal state, a lock is a team-stack state; they overlap but are not the same thing.

## 1. Spawn routines per map, locked vs free, TOP vs FIELD

All rows: share of spawns. "item<=14 s" = any of RA/YA/GA/MH/RL/LG/GL/SNG/quad/pent/ring taken inside 14 s;
"RL@first" = RL in hand at the first sample (alive players); "mate" = a live teammate in the same area at the first sample.

| map | state | grp | n | chained | killed<6 s | item<=14 s | item<=8 s | first item (share of spawns) | RL@first | dmg 14 s | dmg>=100 | frag<=14 s | mate same area |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dm3 | locked | TOP | 14,055 | 67% | 38% | 34% | 18% | rl 8, ya 6, lg 6, mh 5 | 4% | 45 | 13% | 15% | 15% |
| dm3 | locked | FIELD | 17,749 | 66% | 36% | 28% | 15% | rl 5, ya 5, mh 5, sng 4 | 3% | 33 | 8% | 11% | 14% |
| dm3 | free | TOP | 42,778 | 59% | 28% | 32% | 17% | ya 7, rl 6, mh 6, lg 5 | 4% | 59 | 20% | 25% | 15% |
| dm3 | free | FIELD | 60,107 | 57% | 25% | 26% | 14% | ya 5, mh 5, rl 4 | 3% | 45 | 14% | 20% | 15% |
| dm2 | locked | TOP | 19,492 | 76% | 51% | 39% | 21% | ya 21, ra 9, rl 6, mh 3 | 4% | 47 | 13% | 11% | 18% |
| dm2 | locked | FIELD | 22,771 | 76% | 50% | 34% | 18% | ya 21, ra 6, rl 3, mh 2 | 3% | 35 | 8% | 9% | 19% |
| dm2 | free | TOP | 48,226 | 64% | 39% | 43% | 23% | ya 21, ra 10, rl 8 | 6% | 60 | 20% | 20% | 19% |
| dm2 | free | FIELD | 67,775 | 65% | 37% | 35% | 19% | ya 20, ra 6, rl 5 | 4% | 46 | 14% | 16% | 18% |
| e1m2 | locked | TOP | 11,885 | 72% | 41% | 33% | 18% | ga 8, sng 7, gl 5, ya 4, rl 4 | 3% | 55 | 18% | 20% | 17% |
| e1m2 | locked | FIELD | 15,042 | 74% | 42% | 23% | 13% | sng 7, ga 6, gl 4, ya 3, rl 2 | 2% | 42 | 12% | 16% | 17% |
| e1m2 | free | TOP | 37,543 | 63% | 31% | 34% | 18% | ga 8, sng 8, gl 5, ya 5 | 3% | 67 | 25% | 29% | 17% |
| e1m2 | free | FIELD | 53,340 | 63% | 30% | 24% | 13% | sng 6, ga 5, gl 5, ya 3 | 2% | 53 | 18% | 23% | 18% |
| schloss | locked | TOP | 13,516 | 75% | 45% | 40% | 22% | ya 13, rl 10, sng 5, mh 5 | 6% | 55 | 17% | 16% | 23% |
| schloss | locked | FIELD | 15,281 | 75% | 43% | 29% | 16% | ya 8, rl 7, mh 4, sng 4 | 4% | 38 | 10% | 12% | 22% |
| schloss | free | TOP | 37,656 | 65% | 35% | 42% | 24% | ya 13, rl 10, sng 5, mh 5 | 7% | 64 | 23% | 25% | 23% |
| schloss | free | FIELD | 47,794 | 64% | 33% | 33% | 19% | ya 9, rl 9, sng 5, mh 5 | 5% | 49 | 16% | 20% | 22% |

Same-team control (mixed rosters only, locked spawns): dm3 TOP 67% chained / item 34% / dmg 45 vs FIELD 66% / 28% / 33;
dm2 76/40%/47 vs 77/33%/34; e1m2 72/33%/56 vs 74/23%/41; schloss 75/40%/55 vs 76/28%/38. Identical to the pooled rows.

Productive vs zero-value locked spawns (sl_supp): "productive" = took an item or dealt >=50 damage; "zero-value" = chained with
no item and no damage.

| map | TOP productive | FIELD productive | TOP zero-value (of chained) | FIELD zero-value (of chained) |
|---|---|---|---|---|
| dm3 | 55% | 45% | 17% | 25% |
| dm2 | 57% | 48% | 18% | 25% |
| e1m2 | 60% | 47% | 11% | 18% |
| schloss | 63% | 48% | 11% | 22% |

The 14 s is a shotgun fight for everyone: 74-83% of the damage dealt in the first 14 s of a locked spawn is SG damage in
both groups; TOP get a little more RL/LG damage in (dm3 rl+lg 18% vs 11%; dm2 rl 13% vs 9%; schloss rl 15% vs 11%).

Per-player locked chained rate, all maps pooled (unweighted; n >= 200 locked spawns):
TOP - zorak 64% (n 1,106), blaze 69%, bogojoker 71%, chris 72%, war 73%, blood_dog_d_p 73% (n 19,219), yeti 73%, dusty 73%,
sane 74%, coj 76%. FIELD - evalcat 68%, viag 69%, pharm 70%, pred 70%, gflip 70%, omicron 71%, cronus 72%, namtsui 73%,
nico 74%, stedanko 74%, schotty 75%, foobhar 75%, phylter 75%, ledge 76%. Group means 72% vs 72%. Note evalcat: best FIELD
survival (68%) with the lowest output of anyone (item 18%, 22 dmg per locked spawn) - surviving by hiding produces nothing;
zorak survives *and* produces (item 45%, 57 dmg).

### Where they go after a locked spawn (area at the first sample, 0-10 s after spawn, alive players)

The destinations are the same for both groups within 1-3 points on every map; TOP survivors and FIELD survivors are in
the same places. The gap in survival-given-alive-at-first-sample is 0-2 points (dm3 47 vs 48, dm2 40 vs 39, e1m2 42 vs 40,
schloss 39 vs 38), so there is no "secret route" to find at this resolution.

- dm3 (TOP n=9,853 / FIELD 12,653): RL 14/13% [survive to 14 s: 61/57%], SNG.tele 8/8% [27/28%], Ring 7/8% [25/29%],
  bridge.low 7/6% [59/62%], hill 6/7% [47/47%], water 6/- [68%], YA.box 5/5% [51/53%]. Survivors at 10-20 s: RL 15%,
  water 10-12%, bridge.low 8-10%, water.LG 5-7%. Largest TOP-FIELD shifts: +1 pt RL, RA, water.LG, bridge.low; -1 pt
  SNG.ledge, RA.tunnel.
- dm2 (11,571 / 13,665): low.RL 14/13% [39/39%], tele 13/14% [31/31%], RA.MH 11/10% [56/52%], NG 8/9% [23/23%],
  big 7/7% [50/50%], big.stairs 6/7% [46/48%], Quad.low 5/6% [25/26%]. Survivors at 10-20 s: low.RL 13-14%,
  RA.MH 11-14%, high.RL 8-9%, secret 5-7%. Shifts: tele -2 pt, NG -1, Quad.low -1, RA.MH +1.
- e1m2 (7,869 / 9,977): YA 10/10% [43/36%], RL 10/10% [57/54%], GL 8/8% [26/27%], MH.low 7/7% [42/40%], Quad 7/9%
  [21/24%], cross 7/8% [34/29%], GL.Quad 6/6% [18/18%]. Survivors at 10-20 s: RL 18-19%, YA 7-8%, GA 6% (TOP), cross 6-7%.
  Shifts: Quad -2 pt, GA +1, bridge +1, cross -1, GL.Quad -1. TOP survive better in the same area at YA (43 vs 36%),
  MH (59 vs 47%), MH.entry (51 vs 42%), cross (34 vs 29%).
- schloss (8,719 / 10,004): tower.RL 17/18% [41/39%], cathedral 12/10% [39/37%], cathedral.YA 8/- [55%], RA.low 8/7%
  [38/43%], Quad 6/9% [30/30%], Quad.low 6/7% [31/33%], tower.entry 6/7% [32/31%]. Survivors at 10-20 s: tower.RL 15-18%,
  cathedral.YA 10-14%, cathedral 9-10%, RA.low 8-9%. Shifts: cathedral.YA +3 pt, cathedral +2, Quad -2. Same-area edge:
  cemetary.tele 36 vs 27%, RA.cellar 40 vs 35%.

First item within 8 s and survival to 14 s given that item (TOP / FIELD, locked, n >= 40 each) - the items that buy time:
- dm3: LG 67/73%, SNG 71/64%, GL 65/70% (the water/SNG side), YA 55/57%, MH 55/51%, RL 52/49%; no item inside 14 s: 24/27%.
- dm2: RA 54/52%, YA 44/43%, MH 48/55%, RL 43/39%; no item: 14/16%.
- e1m2: YA 64/56%, GA 57/63%, MH 50/55%, RL 50/45%, SNG 50/44%, GL 27/25%, quad 28/20%; no item: 20/22%.
- schloss: RA 78/69% (rare: n 94/70), YA 59/61%, MH 48/44%, RL 40/36%, GL 34/37%, SNG 28/35%, quad 21/23%; no item: 16/19%.
(Reverse causality applies - you have to live ~7 s to take anything - but the ordering between items is informative:
on e1m2 and schloss a quad or GL as first item under a lock is the worst outcome of all, because it is the lock zone.)

## 2. The respawn wait

Exact (demo `sp`/`d` arrays, 8 games, 3,680 pairs): overall median 0.88 s. TOP (n=889): p10 0.32, median 0.88, p75 0.93,
p90 1.12, p95 1.44 s; <1 s 86%, >=2 s 4%, >=3 s 2%, >=5 s 1%. FIELD (n=1,461): median 0.90, p75 1.03, p90 1.44, p95 2.25 s;
<1 s 71%, >=2 s 6%, >=3 s 4%, >=5 s 2%. Everyone else: p95 1.23 s, >=3 s 1%.

DB-derived (validated waits only, all maps):

| grp | state | n | median | <0.5 s | >=1 s | >=2 s | >=3 s | >=5 s |
|---|---|---|---|---|---|---|---|---|
| TOP | locked | 58,760 | 0.86 s | 27% | 16% | 3.4% | 2.2% | 1.4% |
| TOP | free | 165,751 | 0.87 s | 21% | 16% | 2.1% | 1.1% | 0.5% |
| FIELD | locked | 70,647 | 0.89 s | 20% | 27% | 6.3% | 4.0% | 2.0% |
| FIELD | free | 228,454 | 0.90 s | 15% | 28% | 5.1% | 2.7% | 1.0% |

- Both groups respawn *faster* when locked (<0.5 s: TOP 27% vs 21% free; FIELD 20% vs 15%) - spamming the key - and
  both show a small rise in the >=2 s tail under lock (+1.3 pt), which is the only trace of deliberate waiting.
- Who waits: namtsui >=2 s on 18.4% of locked deaths (>=3 s 12.2%), stedanko 13.9%, foobhar 12.4%, evalcat 10.2%, gflip 7.3%,
  nico 7.0%; top waiters among TOP are bogojoker 6.0% and war 5.9%; chris 0.9%, blood_dog 2.6%, yeti 2.1%.
- Does it help? No. Chained rate under lock by wait bucket, TOP: <0.5 s 74%, 0.5-1 s 73%, 1-2 s 71%, 2-3 s 73%, 3-5 s 74%,
  5-10 s 71%; FIELD: 73/73/72/71/71/71%. Killed-inside-6 s is flat too (40-49%). Per map the 3-10 s bucket is within
  noise of the <1 s bucket (e1m2 TOP 65% vs 73% on n=278 is the only >5 pt difference). Habitual waiters: namtsui 74% (<1 s)
  vs 70% (>=2 s), foobhar 76 vs 73, stedanko 73 vs 76, evalcat 67 vs 74, bogojoker 72 vs 72, war 73 vs 75.
- Re-killed by the same enemy who killed you last time: 28% of locked spawns for both groups (27% free).

## 3. Enemy frag streaks as locks (>=6 enemy frags without dying)

| map | streaks/game | median frags (p90) | median length | victim-team deaths during it (median) | streaker's share of them | ended by enemy frag / self-env-TK / unbroken | victims margin-locked at the end |
|---|---|---|---|---|---|---|---|
| dm3 | 13.1 | 10 (23) | 129 s | 28 | 36% | 80 / 13 / 7% | 27% |
| dm2 | 20.8 | 9 (21) | 91 s | 26 | 37% | 76 / 20 / 5% | 25% |
| e1m2 | 17.4 | 10 (22) | 90 s | 23 | 43% | 83 / 13 / 4% | 25% |
| schloss | 20.5 | 9 (20) | 87 s | 24 | 39% | 80 / 15 / 4% | 26% |

A streak consumes ~9-10 spawns of the victim team directly and sits inside a stretch where the team loses 23-28 lives in
total. The streaker has the RL at the last frag 87-99% of the time; dm3 streaks are 23% LG.
Streakers are TOP 52-58%, FIELD 28-31% (TOP streaks are one frag longer: median 10-11 vs 8-9).

Who ends it (the finishing frag, n = 4,237-6,357 per map):
- TOP fire 52-57% of the finishing frags against a roster share of 38-42% (lift 1.33-1.38; mixed victim teams only 1.36-1.42);
  FIELD 29-32% against 43% (lift 0.68-0.73; mixed 0.66-0.70).
- TOP also do 52-58% of the damage to the streaker in its last 15 s (lift 1.33-1.42; FIELD 0.65-0.74) - they are not just
  taking the last hit, they are doing the wearing-down too. The streaker is already low when finished (eff median 17-32).
- The ender is a spawn-level player: eff <=100 at the frag - TOP 58/49/71/56% (dm3/dm2/e1m2/schloss), FIELD 69/57/82/64%;
  eff >=150 only 15-39%. Median time since the ender's own spawn: TOP 36/28/20/24 s, FIELD 25/21/12/18 s; fired inside
  14 s of spawning: TOP 26/31/44/37%, FIELD 37/39/53/44%.
- The ender had died to the streaker during the streak 80-85% of the time: it is one of the victims coming back.
- Weapon: TOP rl 39/65/44/59%, sg 27/28/41/32%, lg 29% on dm3; FIELD sg 39/41/50/39%, rl 32/51/32/49%. The ender has the RL
  in hand 44/67/47/62% (TOP) vs 34/52/33/51% (FIELD).
- Where streaks end (streaker's area): dm3 Ring 9%, SNG.tele 9%, RA.low 8%, Quad 8%, RL 7%; dm2 tele 13%, NG 11%, low.RL 11%,
  Quad.low 8%; e1m2 Quad 15%, YA 14%, GL 12%; schloss tower.RL 11%, RA.low 10%, cathedral 9%, Quad 9%, Quad.high 7%.
  The ender's area is the same list (dm3 RA.low 11%, dm2 NG 12%, e1m2 Quad 15%, schloss RA.low 12%). Streaks die where they
  farm: in the spawn-and-lock zones, not somewhere clever.

## 4. Who breaks locks (last 30 s before a >=30 s lock ends)

Per player-episode rates (a locked-team player in the break window), TOP vs FIELD:

| map (episodes) | grp | n | took RA | mega | quad | YA | RL pick | frags>=1 | >=2 | >=3 | RL frag | spawn frag | stacked kill | any trigger* | dmg dealt | died>=1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dm3 (2,196) | TOP | 3,211 | 12% | 21% | 4% | 22% | 17% | 54% | 21% | 7% | 18% | 14% | 2% | 51% | 244 | 74% |
| | FIELD | 3,711 | 6% | 15% | 2% | 16% | 15% | 42% | 13% | 3% | 10% | 10% | 1% | 36% | 156 | 83% |
| dm2 (2,471) | TOP | 3,825 | 35% | 19% | 5% | 40% | 27% | 55% | 22% | 8% | 28% | 18% | 2% | 60% | 287 | 78% |
| | FIELD | 4,284 | 26% | 12% | 2% | 37% | 19% | 39% | 11% | 3% | 14% | 12% | 1% | 43% | 176 | 86% |
| e1m2 (1,727) | TOP | 2,577 | - | 11% | 5% | 14% | 20% | 67% | 31% | 11% | 22% | 19% | 1% | 44% | 248 | 79% |
| | FIELD | 2,988 | - | 6% | 3% | 8% | 13% | 51% | 16% | 4% | 9% | 14% | 0% | 28% | 170 | 86% |
| schloss (1,771) | TOP | 2,882 | 17% | 16% | 7% | 39% | 32% | 62% | 28% | 10% | 31% | 21% | 2% | 55% | 290 | 81% |
| | FIELD | 3,137 | 10% | 13% | 4% | 27% | 21% | 47% | 14% | 4% | 16% | 14% | 0% | 39% | 179 | 87% |

*any trigger = RA, mega or quad take, >=2 frags, or a spawn frag in the window.

Relative to roster share, mixed teams only: RA/mega/quad takes by TOP lift 1.26/1.26/1.38/1.29 (dm3/dm2/e1m2/schloss),
FIELD 0.79/0.82/0.69/0.79; frags TOP 1.21/1.30/1.26/1.27; spawn frags TOP 1.19/1.29/1.24/1.24; stacked kills
(victim eff >=150) TOP 1.79/1.78/2.23/2.02 vs FIELD 0.42/0.51/0.14/0.24 - killing a stacked enemy from a lock is almost
exclusively a top-player act, but it is rare (1-3% of player-episodes).

The break is a fresh-spawn shotgun fight, not a stacked counter-push: of the locked team's frags in the window, the attacker
has eff <=100 in 74/61/84/69% and fired inside 14 s of their own spawn in 41/46/52/50%; weapon SG 43/46/52/45%,
RL 26/45/25/42%, LG 21% on dm3. The victim had the RL in 23-37% of these frags (that is the RL coming back) and was
stacked (eff >=150) in only 0-2%. By group, TOP's break frags are more RL (dm2 52% rl vs 38%; schloss 47 vs 34%; dm3 30 vs
22%) and FIELD's more SG (dm3 48%, dm2 53%, e1m2 58%, schloss 51%).

Sequence (first action of the locked team inside the window, then last action before the break sample):
- dm3: first - frag 36%, YA 15%, mega 14%, RL pick 13%, LG pick 10%; last - frag 35%, YA 13%, mega 13%, RA 12%.
  Common openings: frag>frag 9%, YA>frag 8%, RL>frag 7%, mega>frag 6%. A TOP player takes mega in 28% of break windows
  (FIELD 25%), RA 17% (10%), 2+ frags 35% (27%).
- dm2: first - YA 28%, frag 25%, RA 17%, RL 15%; last - frag 27%, RA 23%, YA 20%. Openings: YA>frag 9%, frag>YA 7%, RL>frag 6%,
  YA>YA 5%, YA>RA 5%. TOP take RA in 48% of windows (FIELD 40%), mega 28% (20%), 2+ frags 37% (24%).
- e1m2: first - frag 64%, RL pick 12%, spawn frag 9%; openings frag>frag 32%, frag>RL 12%, RL>frag 10%. 2+ frags by a TOP
  player in 48% of windows (FIELD 35%); mega 16% (10%).
- schloss: first - frag 35%, YA 24%, RL 17%, mega 8%; last - frag 33%, YA 19%, RA 13%, RL 12%, spawn frag 11%. Openings YA>frag
  10%, frag>YA 10%, frag>frag 9%, RL>frag 7%, YA>RL 6%. TOP: RA 27% (18%), mega 26% (21%), quad 12% (6%), 2+ frags 47% (32%).

## 5. Lock entry: the 30 s before a team becomes locked (entries that became >=30 s locks)

| map (entries) | enemy took in the 30 s before: RA / mega / quad / pent | margin already >= thr/2 10 s earlier | grp | n | deaths (mean) | died >=2 | died with stack | died holding RL | spawn-death | frags>=1 | dmg dealt / taken | had eff>=150 in window | took RA / YA / mega |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dm3 (2,306) | 94 / 66 / 38 / 5% | 61% | TOP | 3,375 | 1.48 | 45% | 3% | 26% | 32% | 58% | 201 / 278 | 43% | 5 / 15 / 19% |
| | | | FIELD | 3,892 | 1.55 | 47% | 3% | 21% | 32% | 48% | 138 / 281 | 34% | 3 / 12 / 14% |
| dm2 (2,585) | 95 / 64 / 34 / 0% | 44% | TOP | 4,007 | 1.91 | 55% | 7% | 40% | 44% | 59% | 299 / 422 | 66% | 22 / 35 / 14% |
| | | | FIELD | 4,483 | 1.96 | 58% | 7% | 31% | 44% | 48% | 195 / 420 | 56% | 17 / 32 / 9% |
| e1m2 (1,794) | - / 43 / 32 / - | 41% | TOP | 2,691 | 1.83 | 56% | 2% | 31% | 39% | 71% | 255 / 327 | 23% | - / 11 / 9% |
| | | | FIELD | 3,097 | 1.94 | 59% | 1% | 22% | 41% | 58% | 182 / 327 | 17% | - / 9 / 5% |
| schloss (1,822) | 87 / 67 / 34 / 10% | 45% | TOP | 2,963 | 1.94 | 58% | 4% | 44% | 42% | 65% | 283 / 391 | 56% | 10 / 32 / 15% |
| | | | FIELD | 3,224 | 1.95 | 60% | 4% | 33% | 42% | 52% | 184 / 365 | 43% | 6 / 23 / 13% |

- Mixed teams: TOP's share of the team's pre-lock deaths is 37/39/38/41% vs roster share 38/40/39/41% - exactly their
  share. Their share of deaths *holding the RL* is 44/47/49/49% and of stack deaths 36/41/44/47%: top players lose the
  RL (and on e1m2/schloss the stack) slightly more than their share, because they are the ones carrying it.
- TOP had eff >=150 at some point in the window 43/66/23/56% vs 34/56/17/43% and still got locked with the team.
- Exposure (share of a player's game time with own team locked): dm3 TOP 14.4% / FIELD 15.3%, dm2 15.2 / 15.0, e1m2 15.0 /
  15.0, schloss 14.7 / 15.3. Per player, every roster member sits between ~12% and ~18%.
- Base rates (share of *all* 30 s windows in which the enemy took the item): RA dm3 49%, dm2 79%, schloss 54%; mega 57/51/34/55%
  (dm3/dm2/e1m2/schloss); quad 25% everywhere. The enemy RA take is strongly over-represented before a lock on dm3 (94 vs 49%)
  and schloss (87 vs 54%), only mildly on dm2 (95 vs 79%, where the RA changes hands constantly); mega and quad are mildly
  over-represented (+9-16 pt and +7-13 pt).
- 43% of lock entries are over inside 30 s (the margin dips above the threshold and comes back); the 57% that last are
  what the sections above analyse.
- Conclusion: top players neither prevent locks nor get locked less; they lose the RL at the entry like everyone else
  (more, in absolute terms). What is different is the exit (sections 3-4).

## 6. Coachable statements and per-map routines

Tags: [P] perception, [D] decision, [E] execution. Numbers are locked spawns unless stated.

1. [D] A locked spawn is a 14 s mission, not a survival problem. Top players die inside 14 s exactly as often as the field
   (67/76/72/75% vs 66/76/74/75% on dm3/dm2/e1m2/schloss) and get killed inside 6 s as often (38-51%). The difference is
   output: item inside 14 s 33-40% vs 23-34%, damage 45-55 vs 33-42 per spawn, zero-value spawns 11-18% vs 18-25% of chained.
2. [E] The first 14 s is a shotgun fight at every level: 74-83% of the damage dealt from a locked spawn is SG. Lock-breaking
   frags are 43-52% SG, fired by a player with eff <=100 (61-84%) inside 14 s of their own spawn (41-52%). Coach the
   shotgun exchange from spawn (close the distance, pre-aim the corner you spawn facing) rather than "get to a weapon first".
3. [D] Do not wait to respawn. Exact demo waits: median 0.88 s, 86% of TOP respawns under 1 s. Chained rate is flat across
   every wait bucket (71-74%) and for every habitual waiter (namtsui, 18% of locked deaths >=2 s, survives 70% vs 74%).
   The only thing waiting changes is how many spawns you get.
4. [P] You will be killed by the same player who just killed you 28% of the time, locked or not. Track the killer's
   weapon sound and position from the kill feed; the spawn routine starts on the death screen.
5. [D] On dm2 under a lock, YA is the first item on 21% of spawns for both groups; the TOP edge is RA (9% vs 6%) and the RL
   (6% vs 3%). Survival to 14 s with RA first 54%, YA 44%, nothing 14-16%. The break sequence is YA -> RA: a TOP player
   takes RA in 48% of break windows (FIELD 40%), and RA precedes 85% of dm2 breaks (pooled study).
6. [D] On dm3 under a lock the items that buy time are on the water side: LG first 67-73% survive, SNG 64-71%, GL 65-70%,
   versus YA 55%, RL ~50%, nothing 24-27%. Ring and SNG.tele are 25-29% survival at the first sample; SNG/water areas
   58-74%. The break runs through mega (58% of breaks; a TOP player takes it in 28% of windows vs 25%).
7. [D] On e1m2 under a lock, GA (8% of TOP spawns vs 6%) and YA (64/56% survival) are the spawn items; GL (27/25%) and
   quad (28/20%) as first item are the worst outcomes because they are the lock zone (Quad 21-24%, GL.Quad 18% survival).
   e1m2 locks break by frags, not items: 2+ frags by one player in 48% of TOP windows (35% FIELD), opening frag>frag 32%.
8. [D] On schloss under a lock, YA first is 13% of TOP spawns vs 8% (59-61% survive), RL first 10% vs 7%; SNG (28-35%),
   GL (34-37%) and quad (21-23%) first are the traps. TOP survivors are at cathedral.YA 14% (FIELD 10%) and Quad less.
   TOP take the RL in 32% of break windows (21%), YA 39% (27%), RA 27% (18%).
9. [E] Streaks are ended by their own victims: the finishing frag comes from a spawn-level player (eff <=100 in 49-82%),
   12-36 s after spawning, who had already died to the streaker (80-85%), in the streaker's farming area (dm3 Ring/SNG.tele/
   RA.low, dm2 tele/NG/low.RL, e1m2 Quad/YA/GL, schloss tower.RL/RA.low/cathedral/Quad). The streaker is low when it dies
   (eff median 17-32): chip, re-spawn, chip, finish. Top players do 52-58% of that chip damage (lift 1.33-1.42).
10. [D] Top players do not prevent locks (same 15% locked time, same pre-lock death share, more RL deaths); the team-level
    lever is the entry trigger: the enemy took RA before 94% of dm3 locks (base rate 49%), 87% of schloss locks (54%), 95% of dm2 locks (79%), and
    mega before 43-67% (base 34-57%). Lock prevention is RA/mega timing discipline, not individual survival.

### "When locked on <map>" - 3-line routines (derived from sections 1, 4 and the pooled study)

dm3
1. Spawn, shotgun out, and move toward the water side: SNG/water areas survive 58-74% vs Ring/SNG.tele 17-29%; first item
   LG, SNG or GL (65-73% survive) beats YA/RL (~50-55%).
2. Mega is the team's break key (58% of breaks); whoever is nearest at the 20 s respawn goes, the others trade SG damage in
   the low areas to keep the stacked RLs busy.
3. The break frag is yours from spawn: 41% of lock-breaking frags are fired inside 14 s of spawning and 74% by a player with
   eff <=100 - fight the nearest streaker on sight rather than running for a weapon; TOP get 24% of their break frags with LG.

dm2
1. YA inside 8 s (12% of locked spawns manage it; 44% survive) and then RA.MH: survivors are at RA.MH 13-15% and low.RL 13-14%;
   avoid NG (23%), Quad.low (25%), water (10-17%) and tele (31%).
2. The break is YA -> RA (RA in 85% of breaks): the RA cycle is the team clock; a TOP player takes it in 48% of break windows -
   plan who is alive at the next RA with the fresh spawn feeding YA first.
3. Expect the shotgun duel at low.RL/NG/tele: 46% of break frags are SG and 45% RL; the RL comes back off the victim 37% of the time.

e1m2
1. GA or YA first (57-64% survive); never route through GL/Quad when locked (GL first 25-27%, quad first 20-28%, GL.Quad area 18%).
2. Breaks are frag bursts (73% of breaks have 3+ frags in 30 s; openings frag>frag 32%): spawn, SG, kill the low streaker -
   52% of break frags are inside 14 s of spawning, 84% with eff <=100.
3. Mega is the only item lever (32% of breaks; TOP take it in 16% of windows vs 10%) - RA does not exist here, so the lock is
   broken by re-spawn pressure, then RL/mega.

schloss
1. cathedral.YA first (13% of TOP spawns, 59-61% survive) or the RL (10%); keep out of Quad/Quad.high/cathedral.SSG (18-20%
   survival) and skip SNG/GL as first items (28-37%).
2. Break needs two of {burst 64%, mega 50%, RA 49%}: a TOP player takes YA in 39% of break windows and the RL in 32%; the
   first RL pick back is the signal to push RA.low/tower.RL, where 21% of streaks end.
3. 50% of break frags are inside 14 s of spawning, 45% SG / 42% RL: fight the streaker from spawn with the SG, finish with the
   first RL - the streaker is at eff ~25 when it dies.

## Caveats (summary)
10 s state resolution and coarse areas; team-quality confound addressed with the mixed-team control (holds everywhere);
lock = 85th-percentile margin, not a human label; roster weights uneven (per-player table given); `vic_tss` artifacts make
derived waits >=10 s unusable (dropped) and the demo cross-check is 8 games; lift numbers do not control for the stack or
weapon TOP players bring into the window; streak locations are +-5 s; the "enemy took RA before entry" rates are compared with the base rate of an enemy RA take in any 30 s window (section 5) -
the excess is large on dm3/schloss and small on dm2, so on dm2 read it as "the enemy had the RA" rather than as a trigger;
all per-item survival figures are conditional on living long enough to take the item.

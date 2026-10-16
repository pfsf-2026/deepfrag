# How the best NA fours players actually play — and what it means for coaching

*DeepFrag research, 2026-10-16. Five parallel studies over 1,415 TB4 4on4 games (dm3 441, dm2 404, e1m2 292,
schloss 278; NA servers, since 2025-01-01, 8 players), plus 60 games re-read from demos at one-second
resolution. TOP = the ten players with ≥80 games ranked by wins above replacement per game (bogojoker, zorak,
sane, chris, blaze, yeti, Blood Dog, war, dusty, coj). FIELD = the other fourteen with ≥80 games. Every
TOP-vs-FIELD gap below was re-checked on mixed teams (TOP and FIELD as teammates in the same game) and holds.
Full reports and scripts: scratchpad `research_fight_entry.md`, `research_death_value.md`,
`research_perception.md`, `research_spawn_lock.md`, `research_floods.md`.*

## The seven findings

**1. The field dies ~9 more times a game, and the whole gap is empty deaths.**
57.7 vs 48.8 deaths to enemies per game. Lives that dealt under 50 damage, made no frag and took no item:
26.7 a game (field) vs 19.3 (top). Deaths that *bought* something are equal or more frequent for the top
(trade off spawn 4.7 vs 4.5; took an item and died 1.7 vs 1.7; died holding quad 1.3 vs 0.7). The strict
"meaningless" class — under 14 s, under 50 damage, nothing taken, team not locked, no enemy powerup up — is
7.9 a game for the top, 11.1 for the field (1.48× inside the same team). The chained-death share (66% vs
65%) and spawn-kills inside 6 s (37% vs 35%) separate nobody. "Don't die" is not advice; "stop having empty
lives" is.

**2. Same state, same death rate. The top just spends less time in the bad states.**
A fresh, unarmed, unstacked player dies inside the next 10 s 49.8% of the time if he is a top player and
49.5% if not. Stacked with a gun: 9.4% vs 11.5%. The difference is exposure: the field is a shotgun spawn
for 59% of its alive time (top 44%), armed 32% (top 48%), and holds 150+ stack *without* a gun 36% of the
time (top 24%). The skill is the route from a spawn to a gun and a stack, not the fight.

**3. The top start MORE fights and win them, and their own state explains all of it.**
98 starts a game vs 73; 54% of their fights are ones they opened vs 46%; on starts they kill 44% / die 29%
vs 35% / 37% (every map, every lock state; 5.1 vs 3.9 starts per alive minute). At the first hit the top
hold the RL 43% vs 27%, have 150+ stack 34% vs 24%, are 60 s+ into a life 24% vs 13%, had an armor or
mega in the last 30 s 54% vs 41%. Every enemy-state cue is identical between groups (enemy just took armor
35/34, enemy has RL 35/35, enemy at 200+ 19/19). In a regression on pre-fight conditions the "top player"
term is ×1.03: the state is the result. RL is the biggest lever of all (×3.8 kill odds, ×0.23 death odds;
rocket openers go 67/10, shotgun openers 24/46). Spawn fights (starter under 6 s off spawn) are identical
for both groups; the entire edge is in built lives. Hit first, the top answer harder rather than retreat
(damage back inside 5 s 59% vs 51%, killed the starter 28% vs 19%, died 47% vs 58%).

**4. Perception: everyone hears the same things. The difference is what they carry and who lands first.**
Of fights started 60+ behind, 86% (top) vs 85% (field) had an audible cue (enemy armor/mega in the last
20 s, or a trade); the enemy's stack was knowable in 77% vs 78%; the "knowable" estimate is within 60 of the
truth 73% vs 72%. The death gap in those fights (64% vs 72%) is the RL mix: without the RL everyone dies
76–78%, with it 36–43%. After an enemy takes red, the top attack him *more* (36% vs 29% within 15 s) and
die less doing it (57% vs 68%) — because they arrive with the rocket; a naked solo attack on a fresh red
dies 70–80% for anyone. The one perception metric that separates everywhere: **landing the first damage**,
61% vs 50% of fights, unchanged without a launcher, behind, alone or paired, on all four maps (schotty 36%,
evalcat 38%, nico and namtsui already 57%). Landing first turns a 51–63% death into 39–49%. The top also
turn information into items faster: an item within 15 s of an enemy death 37% vs 27%; they take 16% of the
red/mega respawns they are alive for vs 11%. The red stopwatch is equal (≤3 s 59% vs 58%); the field is late
on *yellow* (56% vs 47%). Quad: attendance is equal (75% vs 72% near before the spawn), but the field walks
out of the room in the last 10 s 54% of the time vs 43%, is in the room at the spawn 27% vs 17% (dm3), and
in the room with the RL 60% vs 43%.

**5. Under a lock everyone dies the same. The top's locked lives buy more, and locks follow the red.**
Chained-death rate under lock: dm3 67% vs 66%, dm2 76/76, e1m2 72/74, schloss 75/75; destinations after a
locked spawn identical within 1–3 points. "I can't even spawn" is true at every level. What differs: an
item inside 14 s on 34–40% of locked spawns vs 23–34%, 45–55 damage per locked spawn vs 33–42, zero-value
spawns 11–18% vs 18–25%. Time to first item is identical (~7.5 s); the difference is going for one at all.
Nobody waits to respawn (median 0.88 s) and waiting does not help (chained rate flat across every wait
bucket). Breaking a lock is a stack race, not a kill: in the 20 s before 317 locks broke the locked team
killed a stacked enemy 12% of the time but took yellow 62%, an RL 50%, mega 32% (red 68% on dm2); its stack
rose +82 while the enemy's fell 154. The finishing frag comes from a spawn-level player (eff ≤100 in
49–82%), 12–36 s into a life, in the streaker's own farming zone, with a shotgun 43–52% of the time. Locks
*start* with the enemy's red take (dm3 94% of lock entries vs a 49% base rate, schloss 87% vs 54%). The top
end streaks at 1.3–1.4× their roster share and do 52–58% of the wear-down damage; they do not prevent locks
(same locked share of game time, 15%).

**6. Coordination: bunching is refuted; flood the enemy, not the spot; the wrong player goes first.**
At one-second resolution over 326 lock episodes, how tightly the locked team moved in the first 30 s has
zero relation to how long the lock lasted (ρ = −0.01/0.00/+0.03). Three or more teammates entering the room
the enemy actually holds ends the lock inside 30 s 50% vs 46% for solo/pair entries, 77% vs 47% when two or
more enemies are in that room (n = 39: a lead, not a result). Group entries cost frags (net −3.5 in the next
15 s) while winning the stack race. Who goes first into an enemy-held room: the first entrant survives 10 s
43% vs 50% for the follower; stack decides (25% survive under 100, 76% at 220+); yet in 59% of mixed pairs
the first entrant had *less* stack than the one behind him. Bogojoker is the model (leads with ~142 stack
and the RL 43% of the time, survives 50%); boomsticks lead too often. The top do not pair tighter (nearest
teammate median 579 u vs 554 u), but being within 700 u of a teammate goes with 20–25% fewer deaths per
minute for everyone. Off the spawn the top move 100 ms sooner and 7% faster (360 vs 336 u/s) and choose the
same directions; survival under a lock depends on the nearest enemy (23% with one inside 350 u, 50% beyond
1,400 u) and on the first room chosen.

**7. The maps are four different games, and the survival maps are the same for everyone.**
Survival to 14 s by where you are 10 s after a locked spawn (identical for top and field):

| map | spawn there and live | spawn there and die | what breaks the lock (last 20–30 s) |
|---|---|---|---|
| dm3 | water.rox 74%, water.GL 70%, water.LG 67%, SNG 63%, SNG.MH 60%, window 44% | SNG.tele 17%, Ring 18–25%, RA.entry 20% | frag → mega (58%) / YA / RL; red after |
| dm2 | GL 64%, floating 55%, secret 48%, tele.YA 41%, big 38% | water 8–10%, NG 12–13%, Quad.low 15% | YA → **red** (85% of breaks) |
| e1m2 | YA.tele 59%, GA 55%, water.RL 55%, water.GA 54%, start.stairs 52% | GL.Quad 10–16%, Quad 13–14%, YA.spikes 16% | frag → frag (73%); mega; no red lever |
| schloss | RA 53%, cemetary.Ring 48%, cathedral.YA 40%, RA.window 40%, tower 37% | cathedral.SSG 17–18%, Quad 19%, Quad.high 20%, Quad.ledge 21% | YA/RL → red; mega |

## What this means for coaching

Coach states and routes, not deaths. In order of the evidence:

1. **A gun before any fight.** The RL is worth ×3.8 on kill odds and ×0.23 on death odds; the top hold it
   44% of alive time because they die less, not because they wait for it. Every map needs a spawn-to-RL route
   a player can run blind, and the first metric on a player's card should be "share of alive time armed".
2. **Armor without a gun is the most expensive habit in the game** (−5.2 pp a death, second only to dying
   with quad). 1.85 a game in the field vs 1.44, 62–69% without RL/LG, the killer smaller 78% of the time,
   over in 2.8 s, mostly on dm2. The rule writes itself: stack goes to the gun, never the other way.
3. **Land first.** 61% vs 50%, everywhere, under every condition. It is seeing him first, position and aim
   together; it is also the one perception number that moves with skill, so it is the one to track.
4. **Turn sounds into items, not into fights.** Everyone hears the red; the top take an item within 15 s of
   an enemy death 37% vs 27% and are late on yellow far less. "Red heard + no RL = not your fight; the
   yellow he didn't take is."
5. **Quad is the last ten seconds.** Attendance is equal; the field leaves the room in the last 10 s 54% of
   the time. Stay, with the rocket (in-room-with-RL 60% vs 43%).
6. **Locks are an item race.** Under a lock, go for the item on the survival map (yellow first), take the
   damage you can, and know the break sequence for the map (dm2: yellow then red). Flood the room the enemy
   holds with three, not a spot on the map; send the stacked player first, the boomsticks second.
7. **Stop coaching:** chained-death share, "don't die", waiting to respawn, "listen more". None of them
   separates good players from the rest.

## For the player we started with (omicron)
Starts the fewest fights on his team, holds the RL 30–39% of alive time, and his "alone into two" deaths
are the pattern — all three are the state problem in finding 3, not the cue problem. His coaching is 1, 3
and 6 above, in that order; the "two-thirds of deaths inside 14 s" line was the pool's number and is
withdrawn.

## Caveats and data issues
- 10 s state samples and coarse areas for everything except the 60-game one-second study; the decisive
  flood cells hold 16–39 events.
- Roster weighting: Blood Dog is 29% of top player-games (yeti + war another 30%); per-player medians agree
  with the pooled numbers but "top" sits closer to BD than to bogojoker.
- All pickups treated as audible; "first damage" is first hit, not first shot.
- The win-probability model has no position/denial term, so item-taking lives are undervalued.
- **Data fix needed:** the stored `contested` flag in `quad_approach`/`quad_tracks` follows the old 650-unit
  radius rule, not the room rule; the dm3 room numbers above come from per-second tracks instead. The
  corpus-wide quad passes need the room-rule re-run.

## Next
1. Moments: per player per night, the 3–5 lives that cost most (win-prob swing), each with its state and the
   map alternative from the survival table, with the hub timestamp.
2. Replace the coach's "fights started from behind" lever with: share of alive time armed; stack without a
   gun; first damage landed; empty lives per game; locked-spawn item rate.
3. Re-run the quad passes with the room rule; expand the one-second lock study past 60 games.

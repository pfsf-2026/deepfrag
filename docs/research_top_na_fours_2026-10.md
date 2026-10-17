# How the best NA fours players actually play — and what it means for coaching

*DeepFrag research, 2026-10-16. Five parallel studies over 1,415 TB4 4on4 games (dm3 441, dm2 404, e1m2 292,
schloss 278; NA servers, since 2025-01-01, 8 players), plus 60 games re-read from demos at one-second
resolution. TOP = the ten players with ≥80 games ranked by wins above replacement per game (bogojoker, zorak,
sane, chris, blaze, yeti, Blood Dog, war, dusty, coj). FIELD = the other fourteen with ≥80 games. Every
TOP-vs-FIELD gap below was re-checked on mixed teams (TOP and FIELD as teammates in the same game) and holds.
Full reports and scripts: `tools/mvd_features/research_2026_10/` (the five `research_*.md` reports and
every script and output used here).*

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

**7. Which spawn point you get matters, the same for everyone, and the first move from it is coachable.**
*(Corrected 2026-10-17. The first version of this finding tabulated "areas", which were positions at the
first 10 s clock tick after a spawn — and death spots for lives that ended before it — not spawn points.)*
From the 60 one-second games, chained-death rate under a lock by the actual spawn point: dm3 RL 55% vs
tele/mega 75%; dm2 RA/MH and big stairs 64% vs water 89%, NG 85%, low tele 83%; e1m2 start 48% and RL 60% vs
the quad-side spawns 84–86%; schloss flat at 73–81%. Top vs field by spawn point is equal within noise. The
first room a player moves into separates survival 2–4× from the same spawn (among players who got out of the
spawn area at all):

| map | spawn (chained, all → locked) | first room under lock → survival to 14 s (n) |
|---|---|---|
| dm3 | RL 58→55% | water 68% (56), bridge.low 66% (118) |
| dm3 | YA 61→69% | window 41% (85), YA floor 33% (161) |
| dm3 | RA tunnel 61→67% | hill 39% (192), RA.low 25% (44) |
| dm3 | lifts 61→72% | lifts.below 26% (246) |
| dm3 | mega (SNG low) 64→75% | SNG.MH 51% (39), Ring 24% (190) |
| dm3 | tele 66→75% | Ring 26% (192), RA.rox 24% (29) |
| dm2 | RA/MH 56→64% | RA.MH/rox 67% (45), low.button 59% (68), big.stairs 46% (50), low.stairs 46% (37) |
| dm2 | big stairs 61→64% | big 38% (281) |
| dm2 | tele YA side 67→72% | tele.YA 51% (156) |
| dm2 | low button 67→74% | low.RL 29% (258) |
| dm2 | quad button 70→75% | big 44% (75), Quad.button 30% (80), NG 21% (39), Quad.low 14% (74) |
| dm2 | low RL 69→78% | low.stairs 36% (87), low.lift 33% (67) |
| dm2 | tele low 70→83% | tele.YA 33% (143) |
| dm2 | NG 76→85% | path 25% (48), tele.entry 23% (96), Quad.low 16% (37) |
| dm2 | water 78→89% | NG 12% (236) |
| e1m2 | start 51→48% | start.water 54% (80), start.stairs 50% (115) |
| e1m2 | RL 59→60% | water.RL 63% (63), cross.water 37% (109) |
| e1m2 | door 61→65% | bridge 50% (100), cross 17% (95) |
| e1m2 | MH low 60→66% | MH.SNG 49% (55), MH 34% (29), MH.entry 33% (93) |
| e1m2 | spikes 62→71% | SSG.spikes 41% (76), YA.spikes 22% (120) |
| e1m2 | YA 66→78% | YA.water 51% (41), GL.stairs 31% (68) |
| e1m2 | cross 70→78% | MH.entry 38% (53), Quad.stairs 22% (119) |
| e1m2 | GL-quad b 72→84% | GL 18% (180) |
| e1m2 | quad 72→85% | Quad.stairs 24% (46), GL.Quad 19% (95) |
| e1m2 | GL-quad a 73→86% | GL 20% (98), Quad 13% (84) |
| schloss | cemetery tele 69→73% | tower.RL 29% (244), RA.window 21% (39) |
| schloss | tower entry 70→74% | tower.RL 32% (139), Quad.ledge 27% (117) |
| schloss | cathedral SSG 69→75% | cathedral 26% (278) |
| schloss | cemetery low 65→75% | RA.low 29% (235) |
| schloss | quad low 67→76% | tower.entry 35% (136), yard.tunnel 23% (56), Quad.ledge 13% (52) |
| schloss | tower RL 69→80% | tower 38% (120), cemetary.tele 28% (50), tower.entry 20% (25) |
| schloss | quad 71→81% | cathedral 23% (199), Quad.ledge 18% (62) |
| schloss | quad high 71→81% | Quad.ledge 32% (56), cathedral.YA 23% (108), Quad 15% (47) |

Lock here = per-second margin (enemy alive stack − own, +100 per RL) above the map's 85th percentile
(dm3 386, dm2 400, e1m2 234, schloss 375); it has no RA term, so locked shares differ slightly from the 10 s
study. Spawn-point coordinates and the script: `tools/mvd_features/research_2026_10/spawn_points.py`; the timer study is `spawn_item_timing.py` there
(outcomes by the key items' state — up / in 1–8 s / 9–20 s / 20 s+ — at the spawn second, per spawn point). How a locked team gets out,
per map (what it had done in the half-minute before the lock ended; 2026-10-17 rerun by item location): on
dm3, someone took a yellow (two breaks in three) and someone got a rocket launcher (two in three); a red is in
one break in three and a quad in one in eight, so they come after you are out; the mega that is part of a
break is the hill one (one in three), not the Pent-side (one in four) or SNG (one in five) one; killing a
stacked enemy is in one break in eight. On dm2 it is the yellow at big first (three in four), then the
back-room red (two in three); low RL and the secret red in about half. On e1m2 the RL (two in three), the
yellow (four in ten), the mega (one in three); no red on the map. On schloss a yellow (tower six in ten,
cathedral five in ten) and one of the two RLs (each in half), then the red (half). Caveat: a lock is measured
in stack and rockets, so a break always shows as items gained; what this adds is which item, in what order,
and that it is not frags of stacked enemies. An item take is not a flood.

## What to decide, and when

*(Rewritten 2026-10-17 after Peter: "we need more of a story approach … top players do that because they are
just better … make this narrative with data, and not data focused.")* The findings above compare the best ten
with the rest; that is the evidence, not the advice. The advice is the decision in each spot and what players
who make it get next.

**You just spawned and your team is locked.** Everyone dies here the same: two of three locked spawns end
inside 14 s whoever you are, and the first 14 s is a shotgun fight for everyone (74–83% of the damage in them
is shotgun). Waiting to respawn changes nothing. So the decision is not "how do I survive", it is "what does
this life produce before it ends". Players who go for an item straight off the spawn take one inside 14 s on
34–40% of locked spawns and deal 45–55 damage per spawn; players who run at the fight first get an item on
23–34%, deal 33–42, and one locked spawn in four produces nothing. Time to the item is the same for both
(~7.5 s); the difference is the decision to go.

**Which way you go is an item-timer decision, not a fixed room.** (Peter, 2026-10-17: "if you spawn RL and
RL time is soon, stay and fight for it; if RL was just taken, leave for LG or YA now.") The one-second games
agree. dm3 RL spawn, 1,022 spawns: with the RL up at the second you spawn, 75% take it inside 20 s; with it
coming in 1–8 s, 36% take it and 65% die inside 14 s — that is the fight for it, worth having with the stack
to win it; with the RL 9–20 s out, 21% take it; with the RL 20 s+ away nobody gets it from that spawn, and
the players who hang around the room die 76% against 40% for those who leave for the LG (up or coming on
35% of those spawns) or the YA. Same shape everywhere: dm3 YA spawn with the YA up, 53% take it and 51% die;
YA 9–20 s out, 12% and 62%. schloss tower-RL spawn with the RL up, 57% take it; RL 1–8 s out, 74% die in the
fight for it. dm2 RA/MH spawn with the mega up, 51% take it and 48% die; mega 20 s+ away, 59% die. So the
first move: read the timer of the weapon or armor you spawned next to; up or inside 8 s, stay and take it;
gone for 15 s or more, leave now for the next item on the clock. Put shotgun damage on whoever you pass, and
send `need armor weapon @ <loc>`. The Game Report shows this state for every rewind.

**Your team is locked and one of them is farming a room.** Locks break as a stack race, not with a hero frag:
in the 20 s before a lock broke the locked team had taken a yellow 62% of the time, an RL 50%, a mega 32%, on
dm2 the red 68%, and had killed a stacked enemy 12%. The frag that ends it comes from a spawn-level player,
12–36 s into a life, in the farmer's own room, with a shotgun half the time — that player is you. Sequence per
map: dm2 yellow → red; dm3 a frag → the hill mega; e1m2 frags + mega; schloss yellow/RL → red. Go to the room
he holds with two teammates, not to a spot; the most stacked walks in first (first-in survives 25% under 100
stack, 76% at 220).

**You just spawned and it is open.** This is the life you build with. Fights opened with a rocket go 67% kill /
10% die; opened with a shotgun 24% / 46%. The RL multiplies kill odds by 3.8 and divides death odds by 4. First
decision: the route to a gun you can run blind. Second: the stack. Players who take the stack first and sit
without a gun 36% of their alive time die stacked-without-a-weapon almost twice a game, the costliest death
after dying with quad. Stack goes to the gun, never the other way.

**You have 150 and no gun.** Get the gun. Those deaths last 2.8 s, the killer is smaller than you 78% of the
time, and dm2 is where it happens most.

**You heard them take the red.** Everyone hears it (86% of fights started from behind had the cue, and the
player who died knew the enemy's stack as often as the one who lived). What decides the fight is what you
carry: without the RL a solo run at a fresh red dies 70–80% at any level; with it, players attack the fresh
red-taker more and die less (57% vs 68%). Red heard + no RL = not your fight; the yellow he did not take is.
Red heard + RL = go now, and hit first: hitting first turns a 51–63% death into 39–49% in every state.

**A fight is starting.** Hit first — 61% vs 50% is the one thing that separates at every level and under every
condition, and it is seeing him first, position and aim together. Hit first and you decide whether it
continues. Hit first by him: answer inside 5 s (kill the starter 28%, die 47%) rather than back off (die 58%).

**Quad in ten seconds.** Attendance is equal; the last ten seconds decide. Players who walk out of the room in
the last 10 s (54% of the time for most of us) hand it over; players who stay, with the rocket, take it.

**You know something your team does not.** NA runs on voice, so the MM2 line is the one nobody sends; on EU it
is the floor. One line on the spawn (`need armor weapon @ loc`), one when a room is lost (`lost loc 2>`), one
when an item goes (`enemy took ra`). The player with the RL then knows where the fight is without anyone talking.

**Stop coaching** chained-death share, "don't die", waiting to respawn, "listen more": none separates anyone.

**Omicron, in this frame.** Fewest fight starts on his team, RL 30–39% of alive time, deaths alone into two
with the shotgun; 28 of 35 behind-starts had the cue and he died in 27, because he arrived without the rocket.
His decisions: the open-spawn route to the gun, hitting first, and the farmer's room with two others, not alone.

## Caveats and data issues
- 10 s state samples and coarse areas for everything except the 60-game one-second study; the decisive
  flood cells hold 16–39 events. `player_state10s.loc` is filled for dead players too (the death spot), so any
  "area at the tick" table mixes destinations with death spots — finding 7 was rebuilt on real spawn points.
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

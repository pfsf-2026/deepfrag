<!-- Generated from the session's advanced_metrics.html; keep the two in sync. -->

# DeepFrag Advanced Metrics

Every number on a DeepFrag profile that comes from the demo rather than the scoreboard: what it measures, how it is computed, why it earned a place, and how to read it in a 4on4.

_Fitted on 2,485 Den and LA fours and 14,028 duels, September 2023 to September 2026 · 12.3 million recorded hits · all damage figures use KTX's overkill cap so they match the in-game stats page_

## Quick reference

| metric | what it is | why we track it |
|---|---|---|
| +/- | Frag differential where each kill and death is weighted by how much it moved the map's win probability at that moment. | Separates frags that decided a game from frags that padded a decided one. Zero-sum between the teams, so nobody farms it. |
| Above average / game | Your +/- minus what an average active player would have posted in your slot, with your teammates, against those opponents, on that map. | The individual-performance input to the rating. Strips out lineup luck. |
| Above replacement / game | The same, measured against the 25th-percentile active player instead of average. | The counting stat: being average is worth something against the guy you would otherwise get. |
| WAR | Career above-replacement points converted to wins at the rate the corpus says points are worth, about 250 per win. | One career number that rewards both quality and showing up. |
| Game Impact Score | One grade per game, 1.00 = average for the eight players: adjusted kills, damage, stacked DDR, deaths, items, multi-kills. | "How well did you play tonight" in absolute terms. The queue-rule number and the player card headline. |
| Adjusted kills | Frags re-weighted by fight difficulty from the stack of both players at first contact, and split by damage share. | A kill on a stacked RL carrier while naked is worth three; a spawn kill from full red is worth half. |
| Stacked DDR | Damage dealt while holding 150+ effective HP divided by damage taken while holding 150+. | The map-control number. Finds the carry and the anchor, ignores naked chip damage. |
| Rocket efficiency | Damage per rocket fired and the share of rockets that did any damage, splash included. | Direct-hit percentage misses most of what a rocket does in fours. |
| Red armor rate | Red armors per game and the share taken within 3 s of spawning. | Are you running the map or waiting for fights. The count separates players; the timing does not. |
| Power-up efficiency | Frags per full quad or pent run, how often you die holding it, and the run's win-probability swing. | Quad decides fours and 45% of holders die during the run. |
| Spawn and chained deaths | Deaths within 3 s of spawning versus deaths within 14 s of the previous one after living longer than 3 s. | The first is the map and everyone's is 12 to 15%. The second is a habit you can change. |
| Fights taken from behind | Fights you started while 60+ effective HP down, per minute spent in that situation. | Against an equal fighter it is the only lever you control. |
| Map profile | Above average per game by map, shrunk toward your overall number until you have the games to earn it. | Some players are map-specific; most are not, and the profile says which. |

## The corpus and the two models behind everything

Every metric here is computed from the match demo, not from the end-of-game stats. The demo records every hit with attacker, victim, weapon and damage, every kill, every item pickup, and every player's health, armor, weapons and ammo at every server frame. We parse all of it into a per-event table with both players' state attached, plus a snapshot of each team's state every ten seconds.

Two fitted models turn that into meaning. The **fight table** is the empirical win rate of a fight given the two players' stack at first contact and whether either holds a power-up, measured across 1.03 million enemy frags in fours. The **map win-probability model** is a per-map logistic regression on 591,000 team-state samples that gives each team a live chance of winning the map from the frag difference, time left, total stack, launchers held and power-ups. Held out by game it scores log-loss 0.401 and AUC 0.894, calibrated within three points in every decile.

| stack edge at first contact | no power-up | you hold quad or pent | they hold it |
|---|---|---|---|
| Behind by 100 or more | 6% | 53% | 2% |
| Behind by 40 to 100 | 20% | 70% | 4% |
| Even | 50% | 89% | 11% |
| Ahead by 40 to 100 | 80% | 96% | 30% |
| Ahead by 100 or more | 94% | 98% | 47% |

"Effective HP" throughout means health plus what your armor will absorb before you die: 100 health and 200 red is 300 effective, 100 health and 100 green is 143. "Stack edge" is your effective HP minus theirs.

## Impact

### +/-

> **Definition.** Sum over your kills of the win-probability they added, minus the sum over your deaths of the win-probability they cost. Unit: frag-equivalents, where 1.0 is a frag at even score with ten minutes left.

Plus-minus in hockey is goal differential while you are on the ice. Ours is frag differential where every kill and death is weighted by when it happened and what it removed. Before each kill the model has a live probability that the killer's team wins the map; after it, the frag difference has moved by one and the victim's remaining stack, launchers and power-up are gone. The difference between those two probabilities is the kill's value. A frag at 0–0 in the first minute is worth about one point. A frag when you are up 40 with a minute left is worth almost nothing. Killing the quad carrier at 60–62 with three minutes left is worth five.

Credit for each kill is split. The finisher keeps 15 percent; the other 85 percent is divided among his teammates by how much of the victim's health they took off in the last ten seconds. A player who does 90 damage and a teammate who lands the last pellet both get paid, in proportion. The victim is debited the full value. Nothing else moves the number: damage that does not end in a kill, item pickups and respawns are not scored, because when we tried scoring them the totals inflated fivefold, since a respawn hands stack back to a team for free and nobody can be charged for it. Kill-only is also how HLTV's Rating 3.0 and FACEIT's Round Swing do it.

In a 4on4 the number does two things a scoreboard cannot. It discounts garbage time, so the player padding frags in a decided blowout gets less than the player fragging at minus 15 with eight minutes left. And it is zero-sum, so whatever one team gains the other loses, which means shotgun percentage, spawn farming and withholding fire cannot raise it. A player on the losing side can post a strongly positive +/-, and BLooD_DoG's career line is the canonical example: +27 a game across 2,114 fours with a 40 percent win rate, nearly eight times his raw frag differential of +3.5, because his kills come while behind and against stacked players.

Two things to know when reading it. First, +/- is 57 percent frag differential by R-squared; the other 43 percent is timing and context, so it is not a new skill, it is fragging re-weighted by leverage. Second, the per-game total is not a percentage of anything. The winning team's gross +/- is about +58 at the median while the net move is always +50, and it ranges from −40 to +115, because the clock and respawns move probability between kills. Read it per game and per minute, relative to other players, and never as "moved the game 68 percent." It is as stable a trait as frag rate: split any player's games into two random halves and the two halves' averages correlate at 0.97.

### Above average and above replacement

> **Definition.** Above average = your +/- in a game minus the +/- an average active player would post in your exact slot. Above replacement = the same, against the 25th-percentile active player.

Raw +/- still depends on who you play with and against. A regression on every player-game predicts a player's +/- per minute from three things plus the map: his own strength, his three teammates' mean strength, and the four opponents' mean strength, where strength is a player's career +/- per minute with the game in question left out and shrunk toward zero for thin histories. The fit explains 41 percent of per-game +/- and its weights make sense: your own strength counts fully, strong teammates take about half a point off you because they take the frags, strong opponents take about half a point off you because they take your life.

Above average swaps your own strength in that prediction for the average active player's, then subtracts the prediction from what you actually posted. What is left is what you did that an average player in your seat would not have. Above replacement does the same with the 25th-percentile player as the baseline, which is pinned each season from players with fifteen or more games in the last twelve months. Baseball pins replacement to a freely available minor leaguer; in a pool of 62 active players the guy you get when you are one short at 11 PM is a real, measurable person, and he posts about −28 +/- a game.

Because pickup lineups are balanced, the lineup adjustment is small for most players and above average tracks raw +/- closely. That is the balancer working, and the players where the two diverge are the ones whose raw number misleads: dusty gains eight points a game because he plays with strong teammates who take his frags, namtsui gains five because an average player would also go negative next to bogojoker. The above-average number is the individual-performance input to the rating, where a player who beats his expectation on a losing team loses less rating than his teammates and a player who coasts on a winning team gains less.

Above replacement is the counting stat. Being an average regular is worth about +18 above replacement every game just by showing up, exactly as WAR treats a league-average starter, and it goes negative only for players who would lose to the fill-in. On the profile, above average is shown per game and drives the rating; above replacement is summed into WAR.

### WAR

> **Definition.** Career above-replacement points multiplied by the wins each point is worth, fitted from the corpus at 0.0040 wins per point, about 250 points per win.

WAR in baseball answers one question: how many more games did your team win because you were in the lineup instead of a replacement player. The Quake version sums above-replacement points across a career and converts them to wins. The conversion rate is not assumed; it is the slope of team wins on team +/- total across every game in the corpus, and it comes out at 250 points per win. That is the part most often taken on faith in other systems and it is the part we fitted.

Like any counting stat it rewards volume. BLooD_DoG leads the fours table at +390 on 2,114 games, yeti is +250 on 1,226, bogojoker +164 on 442. The rate view, above average or above replacement per game, is where bogojoker leads by a wide margin at +72 above average. Both views belong on a profile: the career total says how much a player has been worth to the pickups, the rate says how good he is right now.

It is a v0 in two known ways. The wins conversion is a straight line, so a season total like +390 overstates the way real baseball WAR would not, and a proper version fits wins non-linearly. And the strength prior is thin under twenty games, so new players' WAR moves a lot early. Neither changes the ordering among regulars.

### Game Impact Score

> **Definition.** A per-game composite normalized so the eight players average 1.00: 30% adjusted kills, 15% damage, 15% stacked DDR, 15% survival, 20% items, 5% multi-kills. Weights are provisional.

+/- says who decided the game. The Game Impact Score says how well each player played, in absolute terms, including the work +/- cannot see: taking armor, holding stack, not dying. It is built from the things that actually predict winning in fours, each normalized to the game's mean so that 1.30 means "30 percent better than the average player in this game" regardless of map or pace. It is not zero-sum; four players on a dominant team can all be above 1.00.

The composite correlates with +/- at 0.78 and with being on the winning team at 0.38, which is stronger than +/-'s own 0.24, because +/-'s leverage discount deliberately shaves the winning team's late frags. That difference is why the two coexist. Use the score for "who played well tonight" and for the pickup queue rule on a rolling ten games, since it does not punish a player for being on the side that stomped. Use +/- for the MVP of a close game and for the rating's individual layer, since it does not reward being on the stacked team.

The weights are ours for now and that is the honest caveat. They are being replaced by an out-of-sample fit: which component averages over a player's previous games best predict his team's *next* results, controlling for everyone's ratings. Whatever survives that test stays in the score; whatever does not moves to the profile as a habit. In-sample fits are meaningless here, since the components are the result: regress team frag margin on the components and you get an R-squared of 0.97 that tells you nothing.

On a card the score sits next to its components, so a 1.4 built on stacked DDR and red armors reads differently from a 1.4 built on adjusted kills alone. Last night's example: BLooD_DoG posted 1.73 in the 282–123 schloss, best of eight, on 10 reds, 4 quads, 14,900 damage and a stacked DDR of 2.61.

## Fighting

### Adjusted kills

> **Definition.** Each kill is worth 0.5 divided by the fight-table probability that the killer wins that fight, from both players' stack at first contact and power-up state, capped at 3.0, and split 15% finisher / 85% damage share.

```
kill points = min(3.0, 0.5 / P(win | stack edge at first contact, power-up state))
```

This is CS's economy adjustment done with Quake's currency. HLTV weights a rifle-on-pistol kill at 0.54 and a pistol-on-rifle kill above one because the duel win rates say so. We do the same with armor and weapons: an even fight is 50 percent and worth 1.0, a kill from 100 or more ahead is a 94 percent fight and worth 0.53, a kill from 100 or more behind is a 6 percent fight and worth the cap of 3.0. A quad holder's kill on an even opponent is 0.56; killing the quad holder from even is capped at 3.0.

Two details matter. The edge is measured at *first contact* between killer and victim, walking back through their damage exchange as long as no gap exceeds four seconds, not at the killing blow. Measured at the kill shot every kill looks like it came from ahead, because the victim is nearly dead by then; the first-contact version is what makes the table honest. And credit is split by damage share, so in a fight where one player does 99 percent of the damage and a teammate finishes with a pellet, the finisher gets 0.16 of the kill and the damage dealer 0.84. A solo kill where you did all the damage is worth the full amount.

In a 4on4 this is the stat that answers "I got a lot of frags" with "of what kind." A 54-frag night can become 40 adjusted when most of the kills came from ahead, and a 31-frag night can become 42 when the player was fighting from behind all game. It also defuses the lock-farming problem: killing a fresh spawner from full stack scores about half, so a team sitting on a lock gets paid less per kill than the numbers on the board suggest, and the player who breaks a lock by killing a stacked carrier gets paid three times.

It is a rate stat and a total stat both: adjusted kills per minute is the fighting-quality number on a profile, and its career split-half reliability is 0.98, the highest of anything we track.

### Stacked DDR

> **Definition.** Damage you dealt while holding 150 or more effective HP, divided by damage you took while holding 150 or more. Plain DDR is all damage dealt over all damage taken.

DDR, damage dealt over damage taken, is the Corsi of Quake: a pressure stat that does not care about frags and so cannot be gamed by kill-stealing. The 4on4 methodology bible argued from the start that the version that matters in team modes is damage while stacked, because damage is cheap when you are naked and dying. A player who respawns, chips 60 off someone with the shaft on the way to the next death, and repeats it twenty times posts a big damage total without ever threatening the map.

Stacked DDR keeps only the exchanges you fought from strength. It asks two things at once: how often did you get yourself stacked, and what did you do with it. The 150 threshold is roughly yellow armor plus full health, the point where a player is a threat rather than a target. Damage is KTX-capped throughout, so overkill on a 30-health victim counts 30, not 110, and the numbers reconcile with the in-game stats page.

It finds the carry. In last night's 170–144 dm3 two players on one side posted 3.4 and 2.5, the other side's best two 1.6 and 1.5, and the remaining four were all under 0.8; same scoreboard, but the stat says two players spent the game holding stack and using it, two traded roughly even from stack, and the rest were doing their damage on the way to dying. It is also the number that credits the anchor: a red-armor holder who fights every exchange from 250 effective HP and rarely dies scores well here even with a modest frag count.

Its split-half reliability across a career is 0.88, lower than +/- or adjusted kills, because it is a ratio and small denominators swing it. Read it over ten or more games, and read the absolute damage next to it.

### Rocket efficiency

> **Definition.** Damage per rocket fired, with direct and splash damage stored separately, and the share of rockets fired that did any damage at all.

Direct-hit percentage is the rocket stat everyone quotes and it is the wrong one for fours. Most rocket damage in a team game is splash: on a typical night the top rocket player lands 14 direct hits out of 110 rockets, but 58 of those 110 do damage, and the total is 4,000 for 36 damage per rocket. The demo records every hit with a splash flag, so we count both kinds and attribute them to rockets fired, which come from the ammo counter.

Two numbers go on the profile. Damage per rocket is the quality number, and among regulars with a hundred or more games it runs from the mid 20s to the low 40s, with grisling at 41.4 and bogojoker at 40.5. Connect rate, the share of rockets that touched anyone, separates the player who fires at map control from the player who fires at nothing. Neither rewards holding fire: a player who withholds rockets to protect a percentage loses on damage per minute and on stacked DDR.

The same pass records cells fired and lightning damage, so the equivalent LG number, damage per cell, is available, though it varies far less between players than the rocket one does.

## Control

### Red armor rate

> **Definition.** Red armors taken per game, the median seconds after the red respawned that you took it, and the share taken within 3 s of its spawn.

Every item pickup in the demo carries the item, the taker and the time since the item became available, so red-armor timing is measured directly rather than inferred. We keep three views: how many reds you take per game, how long after it spawns you typically arrive, and the share of your takes that were on the timer.

The finding that shaped how it is displayed: timing does not separate players. Everyone with thirty or more games takes about 60 percent of their reds on the timer, from Pred to bogojoker. Count does. The top group, grisling, zorak, nico, bogojoker, takes nine or ten reds a game; the middle takes eight; the players who post negative above-average numbers take four to six. So the profile leads with reds per game, and the timing is there to answer "was he late or absent."

Red armor is also the item the win-probability model values most through stack, and it is the reason zone-possession data added nothing to the model: holding the red platform is already expressed as holding red armor. Yellow, green and mega takes are tracked the same way and feed the items term of the Game Impact Score at 0.6, 0.3 and 0.8 of a red respectively, with quad and pent at 2.0.

### Power-up efficiency

> **Definition.** Per quad, pent or ring run: holder frags, teammate frags during the run, holder damage, whether the holder died and when, team deaths, the frag-difference change and the win-probability change from take to expiry. Summarized as frags per full run, died-with-it rate, and wasted-run rate.

Quad decides fours and the demo gives us the exact interval each player held it, so every run in the corpus is scored. Across 48,529 quad runs, the holder dies during 45 percent of them and inside ten seconds on 27 percent. A full thirty-second run averages 3.9 holder frags, 3.8 teammate frags around it, a +4.5 swing in frag difference and +4.1 points of win probability. Pent is safer and smaller, 2.5 holder frags and no deaths. Ring is the least valuable power-up on the map at +1.2 frags, and it gets the holder killed as often as quad does.

Per player the spread is enormous. Bogojoker averages 5.1 frags per full run and wastes 21 percent of his quads; players at the bottom of the table average 2.1 and waste 67 percent, where a wasted run is dying inside ten seconds or finishing a full run with no frags. The died-with-it rate is usually the more instructive number than the frag average, because the frags follow from staying alive: a player who dies holding quad on 56 percent of runs cannot post a good average no matter how well he aims.

The run's win-probability change is the impact view of the same event, and it is what turns "6 frags" into "+9 frag difference and the game" versus "6 frags in garbage time." Teammate frags during the run are kept because the escort effect is real: on a full run the three teammates add almost as many frags as the holder does. On the profile these appear as a power-up card: runs, frags per full run, died-with-it, wasted, and the average swing.

## Discipline

### Spawn deaths and chained deaths

> **Definition.** Spawn death: killed within 3 s of spawning. Chained death: killed within 14 s of your previous death after living more than 3 s. KTX's own spawn-frag stat uses a 2 s window.

These two used to be one number and separating them was the single most useful thing the corpus taught us about deaths. A spawn death is the map: with KTX's spawn model a spawn point is excluded only if you used it last or a live player is standing within 84 units of it, everything else is random, and a third of the time in fours somebody is standing near where you appear. Every regular from Pred to bogojoker dies within three seconds of spawning on 12 to 15 percent of his deaths. It is not a skill and it is not on the profile as one.

A chained death is a choice. You lived long enough to pick up something, went straight back in without it, and died again. It is the tilt loop, and in the duel analysis it was the number that separated the same player's game one from his game five. In fours it is also mostly a property of the mode, 41 to 52 percent of deaths for the whole top tier, so on a fours profile it is shown against the night's and the team's rate rather than as an absolute, and it is judged relative to context: a whole team chaining because they are locked out at minus 60 is not four individual failures.

Neither number is scored by +/-, on purpose. Dying naked removes nothing the win-probability model values, so a chained death costs almost nothing in swing even though it is exactly the habit you want to discourage. That is why survival stays in the Game Impact Score as its own term rather than being folded into +/-, and why the profile shows deaths per minute alongside the two rates.

### Fights taken from behind

> **Definition.** Fights you started while 60 or more effective HP behind, divided by the minutes you spent within 700 units of an opponent while that far behind.

A fight is a cluster of damage between two players with no gap longer than four seconds; whoever landed the first hit started it. Because the demo carries both players' stack at every hit, we know how far behind the starter was, and because we sample positions, we know how much opportunity he had. The rate is fights started from behind per minute of being behind and in range, so a player who is rarely under-stacked is not rewarded for it and a player who is often under-stacked is not punished for it.

The fight table says what such a fight is worth: from 60 or more behind you win between 6 and 20 percent of them in fours. Against an opponent who is your equal in even fights, which the corpus shows is common between regulars, the fights you decline are the whole margin. The duel version of this stat is what showed the same player starting far more fights from behind in the games he lost than in the games he won, and it is the stat behind the rule "60 behind means you do not shoot first."

It sits on the profile with its two neighbours from the same analysis, item-first spawns and the even-fight win rate, because together they describe how a player picks his fights rather than how he fights them.

## Context

### Map profile

> **Definition.** Above average per game on each map, shrunk toward the player's overall number until the map has enough games to stand on its own.

The maps are not the same game. dm3 is the map where one player matters most: the fewest frags, each worth the most, and a player 50 above average drags his team to a 67 percent win chance. e1m2 is the opposite, the most frags, 296 +/- points per win against dm3's 219, and the same +50 player only gets his team to 60 percent. dm2 has the cheapest individual frags of the four because there are so many of them, and schloss sits between. A rocket launcher is worth about 50 percent more than a lightning gun on dm3, and the LG only exists on dm3 among the maps we play.

Players differ by map too, but less than the folklore says. Across 25 regulars with thirty or more games on three or more maps, a player's map averages scatter about 7 points around his overall number while his individual games on any one map scatter by 37. Map identity is real and it is a fifth the size of ordinary variance, so it takes about thirty games on a map before the split means anything. That is why the profile shows a shrunk per-map deviation rather than four independent numbers: with few games it sits near your overall figure, and it moves away only as the evidence accumulates, which is the same design the duel engine already uses for per-map ratings.

The exceptions are worth showing precisely because they are exceptions. bogojoker is +98 above average on e1m2 and +51 on dm3; zorak is +67 on e1m2 and +39 on dm3; BLooD_DoG is +34 on dm2 and +18 on schloss. The spread, best map minus worst, is the one number that says "map specialist" or "same player everywhere."

## Tested and rejected

Part of the method is what did not make it. Each of these was built, fitted and measured before being left out, so nobody re-tries them.

- **LG cells and RL rockets as state.** Weighting a lightning gun by its ammo, or counting only loaded guns, changed held-out log-loss by less than 0.001. The gun itself is the signal, because holding the LG on dm3 means holding the LG area and the cells refill there. Ammo stays on the profile only as a habit stat.
- **Zone possession.** Players in each zone, yours minus theirs, for the twelve busiest zones per map, added under 0.001 to the model on every map once stack and launchers were in. The anchor's value already flows through the team stack term.
- **Alive count.** It carried a large weight but it was a proxy for who just lost the last fight, and it lasts a second per death. Removing it cost 0.002 log-loss and made the swing arithmetic honest.
- **Damage and item swing.** Scoring damage and pickups as swing events inflated team totals fivefold because respawns give stack back for free. Kill-only is the version that stays zero-sum.
- **Time holding a dry LG.** Followed from the ammo finding; dropped.
- **Direct-hit percentage as the rocket stat.** Kept for reference, replaced by damage per rocket.

## Reading a profile

The metrics answer four questions in order, and a profile is laid out the same way.

- **How good is he?** The rating, which moves on team results and on above-average performance, plus above average per game and WAR as the rate and the career total.
- **How well did he play tonight?** Game Impact Score per game with its components, and +/- for who decided it.
- **How does he play?** Adjusted kills per minute, stacked DDR and rocket efficiency for the gun; red armor rate and power-up efficiency for the map; chained deaths and fights taken from behind for the head.
- **Where?** The map profile.

Two rules for reading them together. Never sit a player for low +/- after a blowout win, because the leverage discount guarantees it; sit on the Game Impact Score and break ties on +/-. And when a habit number looks bad, check the context column first: spawn deaths are the map, chained deaths on a locked-out team are the lock, and a bad rocket connect rate on a night of long-range dm2 pokes is the map choice. The stats find the players who are genuinely bad at something, which is what they are for, but only after the context has had its say.

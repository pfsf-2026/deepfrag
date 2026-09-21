// Plain-English glossary for every number DeepFrag shows (2026-09-21, Peter: "5th-grade
// English, in Quake terms, explain EVERYTHING"). One source for the /glossary page and
// for the "what is this?" links on the coach pages. Keys match the engine's lever and
// outcome keys (coaching_fours.py) so the coach can link a stat straight to its entry.
export type GlossGroup = 'start' | 'basics' | 'items' | 'quad' | 'fighting' | 'scores' | 'duel'
export interface GlossEntry {
  key: string
  name: string
  group: GlossGroup
  /** imperative, what the coach is really asking for ("Take more quads") — levers only */
  headline?: string
  /** what it is, one or two short sentences */
  plain: string
  /** how we count it */
  count?: string
  /** what good looks like */
  good?: string
  /** how to move it */
  move?: string
}

export const GLOSS_GROUPS: { key: GlossGroup; title: string; blurb: string }[] = [
  { key: 'start', title: 'Start here: the words on your coach page', blurb: 'Read these five first. Every card on the coach uses them.' },
  { key: 'basics', title: 'The basics', blurb: 'Frags, stack, armor, the items. If you play Quake you know these, but this is exactly how we count them.' },
  { key: 'items', title: 'Armor and items', blurb: 'Who took the armor. In 4on4 the team that owns the reds owns the map.' },
  { key: 'quad', title: 'Quad', blurb: 'The item that decides fours. Showing up, taking it, and turning it into frags are three different stats.' },
  { key: 'fighting', title: 'Fighting', blurb: 'How you fight and how you die.' },
  { key: 'scores', title: 'The big scores', blurb: 'The one-number grades: +/-, above average, impact.' },
  { key: 'duel', title: 'The 1on1 coach', blurb: 'Numbers that only show up on the duel side of the coach.' },
]

export const GLOSSARY: GlossEntry[] = [
  // ── start here ─────────────────────────────────────────────────────────────
  { key: 'you', group: 'start', name: 'You',
    plain: 'Your own number from your last 40 fours (4on4 games with a demo) on the Den or LA servers. Every number on the coach that says "you" comes from those 40 games. Older games do not count.' },
  { key: 'target', group: 'start', name: 'Target (the promotion line)',
    plain: 'The number a player has when they are just good enough to move up one level. Match it and you are doing that one thing like a player one level above you.',
    count: 'We line up every active player by how far above average they play and by this stat, draw the trend line, and read it off at the edge of the next level. It always sits between what your level does and what the next level does.',
    good: 'Reaching the target on both gates is what moves you up. It is the next step, not the best in the world.' },
  { key: 'level_median', group: 'start', name: 'What your level does (the median)',
    plain: 'The middle player at your level. Half the players at your level are above this number and half are below. If you are under it, this stat is behind even your own level.' },
  { key: 'level', group: 'start', name: 'Level (L1 to L5)',
    plain: 'Your belt. It comes from one number: how much you help your team win compared with an average player, over your last 40 fours. L1 Survive, L2 Stack, L3 Fight, L4 Control, L5 Carry.',
    count: 'Mean of your "above average per game" over the last 40 fours. Under -30 is L1, -30 to -10 is L2, -10 to +15 is L3, +15 to +40 is L4, over +40 is L5. You need 15 games to get one.',
    good: 'It is not a rating and nobody votes on it. It moves when your play moves.' },
  { key: 'gates', group: 'start', name: 'Gates',
    plain: 'The two stats you must reach to move up a level. Each gate has a target (the promotion line). Pass both and the coach says you are ready to move up.',
    count: 'L1 gates: share of the reds and damage per minute. L2: deaths per minute and even-fight win rate. L3: quads per game and share of the reds. L4: adjusted kills per minute and stacked damage ratio.' },
  { key: 'focus', group: 'start', name: 'Your one focus',
    plain: 'The single thing the coach wants you to work on right now. Not a list. One thing.',
    count: 'The stat where you are furthest below the target, with a bonus if it is one of your gates and if it is something you do in your wins but not in your losses. It stays your focus for 10 games, then the coach checks whether it moved.' },
  { key: 'drill', group: 'start', name: 'Drill',
    plain: 'The one habit to actually do in the game to move the focus stat. Say it on comms, do it every spawn.' },
  { key: 'plays_like', group: 'start', name: 'Plays like L3',
    plain: 'On one map your play can match a different level than your overall one. "Plays like L2" on e1m2 means: on that map you play like a Level 2 player, even if you are L3 overall.' },
  { key: 'map_baseline', group: 'start', name: 'Map baselines vs pooled',
    plain: '"Map" means the targets on that tab come from players who have played that map a lot (8 or more games), so a one-red map is judged against one-red-map play. "Pooled" means not enough players have a baseline there yet, so the targets come from all maps together.' },

  // ── basics ─────────────────────────────────────────────────────────────────
  { key: 'frags', group: 'basics', name: 'Frags',
    plain: 'Your score. You get one frag for every enemy you kill. You lose one when you kill yourself (a suicide, like discharging in water) or kill a teammate.' },
  { key: 'kills', group: 'basics', name: 'Kills',
    plain: 'Enemies you killed. Kills minus your suicides and teamkills is your frags.' },
  { key: 'deaths', group: 'basics', name: 'Deaths',
    plain: 'How many times you died, from anything: an enemy, lava, a fall, your own rocket, a teammate.' },
  { key: 'damage', group: 'basics', name: 'Damage given and taken',
    plain: 'Damage given is how much health and armor you took off enemies, added up over the game. Damage taken is how much they took off you. 100 damage is one fresh spawn.' },
  { key: 'stack', group: 'basics', name: 'Stack',
    plain: 'How much punishment you can take right now: your health plus what your armor will soak up. 100 health with a full red is a stack of about 300; a fresh spawn is 100. On this site "stacked" means 150 or more.',
    count: 'Red soaks up 80% of each hit, yellow 60%, green 30%, until the armor runs out. Stack = health / (1 - soak), or health + armor if that is smaller.' },
  { key: 'armors', group: 'basics', name: 'Green, yellow and red armor',
    plain: 'Green (GA) is 100 armor that soaks 30% of each hit. Yellow (YA) is 150 that soaks 60%. Red (RA) is 200 that soaks 80%. Red is the big one: it is the difference between dying to two rockets and surviving five. An armor comes back 20 seconds after it is taken.' },
  { key: 'mega', group: 'basics', name: 'Mega health (MH)',
    plain: 'A health pack that takes you to 250 health, which then ticks back down to 100. It comes back 20 seconds after your health is back at 100. Megas are the second stack item after red.' },
  { key: 'quad_item', group: 'basics', name: 'Quad',
    plain: 'Quad damage: four times damage for 30 seconds. It spawns every 60 seconds, so a 20-minute game has 20 of them. A quad rocket kills a fresh spawn in one hit. It is the item that decides the most fours games.' },
  { key: 'pent', group: 'basics', name: 'Pent',
    plain: 'Pentagram of protection: 30 seconds where you take no damage at all. It spawns every 5 minutes on the maps that have one (dm3, schloss). Nothing hurts a pent player, so the play against one is to run, hide the items, and count the 30 seconds.' },
  { key: 'ring', group: 'basics', name: 'Ring',
    plain: 'Ring of shadows: 30 seconds of being nearly invisible. Only dm3 and schloss have it. Good for stealing a red or sneaking up on the quad room.' },
  { key: 'rl_lg', group: 'basics', name: 'RL and LG',
    plain: 'Rocket launcher and lightning gun, the two weapons that decide fights. A direct rocket does 100 to 120 damage and its splash hurts everyone near it. The LG does 30 per cell, 10 cells a second, with no splash. "Armed" on this site means carrying one of them.' },
  { key: 'units', group: 'basics', name: 'Units',
    plain: 'Quake\'s ruler. Every distance in the game is measured in units. A player is 56 units tall and 32 wide. You run at 320 units a second, so 650 units is about two seconds of running. A rocket flies 1,000 units a second and the lightning gun reaches 600 units.',
    count: 'We read positions straight from the demo, ten times a second, and measure straight-line distance in units. When the coach says "within 650 units of the quad", picture the quad room and the hallway leading into it: close enough to be in the fight for it, not just on the same side of the map.' },
  { key: 'timer', group: 'basics', name: 'The timer',
    plain: 'Big items come back on a schedule: armors and megas 20 seconds after they are taken, quad 60 seconds after it was taken, pent 5 minutes. Good teams say the take time out loud on comms and add the respawn. Being "on the timer" means you were standing there when it came back, not walking past it later.',
    count: 'There is no fixed quad second. Across all our fours the quad is taken within one second of spawning nine times in ten (dm2 is the slow one, at about two), so the quad time drifts roughly a second later every minute. Take the last quad time, add 60, add a second, and be at the door five seconds before that.' },

  // ── armor and items ────────────────────────────────────────────────────────
  { key: 'ra_share', group: 'items', name: 'Share of the reds', headline: 'Take more reds',
    plain: 'Out of all the red armors anyone took in the game, the share you took. If the game had 60 red pickups and you took 9, your share is 15%. Eight players share the reds, so an equal cut is 12.5%.',
    count: 'Your red pickups divided by every red pickup in the game, both teams. We use the share, not the count, so a one-red map (dm3, schloss) and a two-red map (dm2) count the same. e1m2 has no red, so it is left out.',
    good: 'L1 players sit around 5%. L3 is about 13%. The top players take 17% or more, which means they are taking more than their fair cut off the other team.',
    move: 'Know the red time: last take plus 20. Leave the fight five seconds before that and be standing on the red with a rocket loaded when it comes back. Do not spend a red on a 50-50 fight.' },
  { key: 'ya_share', group: 'items', name: 'Share of the yellows', headline: 'Restack with yellows',
    plain: 'Same idea as share of the reds, but for yellow armor. Yellows are cheaper and there are more of them, so this is about restacking after every death instead of running back in naked.',
    count: 'Your yellow pickups divided by every yellow pickup in the game, both teams.',
    move: 'Every respawn: yellow first, then the fight. On dm2 there are three, so there is no excuse.' },
  { key: 'ra_pg', group: 'items', name: 'Red armors per game',
    plain: 'How many reds you picked up in a game. We show it because everyone knows what 8 reds means, but the coach uses share of the reds instead, because a two-red map hands out twice as many.' },
  { key: 'ya_pg', group: 'items', name: 'Yellow armors per game',
    plain: 'How many yellows you picked up in a game. Shown for reference; the coach uses the share.' },
  { key: 'ra_on_timer_pct', group: 'items', name: 'Reds taken on the timer', headline: 'Be there when the red spawns',
    plain: 'Of the reds you took, the share you took right as it came back. That means you were there on purpose, on the clock, not walking past it half a minute later. A late red is one the enemy could have had.',
    count: 'A red counts as on the timer when you take it within 3 seconds of its respawn. Needs at least 30 reds in your last 40 games to be judged.',
    move: 'Say the time when anyone takes it. Be at the red three seconds early with a rocket ready and hold the door, not the item.' },
  { key: 'mh_pg', group: 'items', name: 'Megas per game',
    plain: 'How many megas you took. A mega makes you a two-rocket problem instead of a one-rocket problem. Shown on the game cards, not coached.' },

  // ── quad ───────────────────────────────────────────────────────────────────
  { key: 'quad_pg', group: 'quad', name: 'Quads per game', headline: 'Take more quads',
    plain: 'How many quads you picked up in a game. There are 20 in a game, spread across eight players. Two a game is Level 3 play; three or more is Level 4.',
    count: 'Quad pickups per game, averaged over your last 40 fours.',
    good: 'Players who take three or more a game sit a full level above players who take two.',
    move: 'Own the quad clock: when anyone takes it, say the time out loud and add 60. Be at the door five seconds before that with armor on, and have a teammate cover the other way in.' },
  { key: 'quad_contests_pg', group: 'quad', name: 'Quad spawns contested per game', headline: 'Show up to quad',
    plain: 'Of the 20 quad spawns in a game, how many you were near when it came back. It is attendance. Dying there while trying counts too.',
    count: '"Near" means within 650 units of the quad at any point in the last 10 seconds before it spawned, up to the spawn. Nothing after the spawn counts. Measured from every player position in the demo.',
    good: 'Almost everyone shows up to about 14 of 20, at every level. The levels split on what happens next: quad conversion.',
    move: 'Know when it is due (last take plus 60). Leave what you are doing 10 seconds before that with a yellow on, and be at the door five seconds early, not on the pad.' },
  { key: 'quad_conversion', group: 'quad', name: 'Quad conversion', headline: 'Win the quad when you are there',
    plain: 'Of the quad spawns you showed up to, the share where YOU walked away with the quad. Show up to 14 and take 2 and your conversion is 14%.',
    count: 'Your quad pickups at contested spawns divided by the spawns you contested.',
    good: 'L1 players convert about 4%, L3 about 14%, L5 about 27%. The best player on the NA servers is over 30%. This is the stat that actually separates the levels at quad.',
    move: 'Arrive with stack and a rocket loaded, not naked. Do not stand on the pad; hold the door the enemy comes through and rocket them on the way in.' },
  { key: 'quad_contest_died_pg', group: 'quad', name: 'Died at quad before it spawned',
    plain: 'Times per game you died within 650 units of the quad in the 10 seconds before it came back. That is you fighting for it and losing. It still counts as showing up.' },
  { key: 'quad_died_pct', group: 'quad', name: 'Died holding quad', headline: 'Do not die with quad',
    plain: 'Of your quad runs, the share where you died before the 30 seconds ran out. Dying with quad hands four-times damage to nobody, and often hands the next quad to the enemy.',
    count: 'Runs that ended in your death divided by all your quad runs. Needs 8 runs to be judged.',
    move: 'With quad, kill the players in front of you; do not chase into a room with three enemies. Shoot at feet: quad splash kills on its own.' },
  { key: 'quad_frags_per_full', group: 'quad', name: 'Frags per full quad run', headline: 'Turn the quad into frags',
    plain: 'In the quad runs where you lived the whole 30 seconds, how many frags you got on average. A full run should be worth four or more.',
    count: 'Frags during runs of 28 seconds or more, divided by the number of those runs.',
    move: 'Plan the route before you take it: quad, then straight to where the enemy stacks (their red), then their spawns. Never wait for them to come to you.' },

  // ── fighting ───────────────────────────────────────────────────────────────
  { key: 'dmg_pm', group: 'fighting', name: 'Damage per minute', headline: 'Do more damage',
    plain: 'Damage you dealt per minute of the game. A fresh spawn has 100 health, so 500 a minute is five spawns worth of health every minute.',
    count: 'Total damage given divided by minutes played.',
    move: 'Shoot at where they will be, not where they are. Shoot at feet. Keep the RL loaded and hold the corners where enemies come to you.' },
  { key: 'deaths_pm', group: 'fighting', name: 'Deaths per minute', headline: 'Die less',
    plain: 'How many times you died per minute. Every death hands the enemy your armor and gives you a fresh 100-health spawn to lose again. 2.0 a minute is 40 deaths in a game.',
    count: 'Deaths divided by minutes played.',
    good: 'Going from 2.5 to 2.0 a minute is ten fewer deaths a game. Ten fewer respawns is ten more chances to hold stack.',
    move: 'Count to three after you lose an exchange before you go back in. Armor first, then the fight. On a bad spawn, walk away from the fight, not into it.' },
  { key: 'sddr', group: 'fighting', name: 'Stacked damage ratio', headline: 'Fight from stack',
    plain: 'Damage you dealt divided by damage you took, counting only the time you had a stack of 150 or more. It ignores naked chip damage. Above 1.0 means that when you are strong you win the trade; below 1.0 means you waste your stacks.',
    count: 'Damage given while stacked / damage taken while stacked.',
    good: 'L3 players are around 1.35. L5 players are over 1.6.',
    move: 'When you are stacked, fight the fight in front of you and finish it. When you drop under 150, leave, restack, come back. Do not spend a red on a 50-50.' },
  { key: 'adj_kills_pm', group: 'fighting', name: 'Adjusted kills per minute', headline: 'Win the hard kills',
    plain: 'Kills per minute, but each kill is scored by how hard the fight was. Finishing a player who was already at 20 health from a teammate\'s rocket is worth a little; killing a stacked RL carrier while you are naked is worth three kills. Whoever did the damage gets the credit.',
    count: 'Each kill is worth 0.5 divided by the chance the killer wins that fight (from both players\' stack when the fight started, and any power-up), capped at 3. It is split 15% to whoever landed the last hit and 85% by damage done.',
    move: 'Take fights you can win from stack, and finish them yourself instead of leaving a 20-health enemy for a teammate.' },
  { key: 'even_win_pct', group: 'fighting', name: 'Even-fight win rate', headline: 'Win the even fights',
    plain: 'When you and one enemy start a fight with about the same stack, how often you get the kill. This is pure skill: aim, movement, and picking the moment.',
    count: 'A fight is even when the stack gap at first contact is under 60. Needs 30 even fights in your last 40 games to be judged.',
    good: 'L1 players win 34% of their even fights, L3 about 53%, L5 about 65%.',
    move: 'Even fights are won by the first rocket. Prefire the corner. If you miss the first one, jump out and reset instead of trading.' },
  { key: 'started_behind_pct', group: 'fighting', name: 'Fights started from behind', headline: 'Stop starting fights you are losing',
    plain: 'Of the fights you started (you hit first), the share where you were the weaker player by 60 stack or more. Starting a fight you are behind in is how stacks get wasted.',
    count: 'Fights you started with a stack gap of -60 or worse, divided by all fights you started. Needs 30 started fights to be judged.',
    move: 'Before you shoot, ask: am I stronger? If not, go get armor and come back.' },
  { key: 'chained_pct', group: 'fighting', name: 'Chained deaths',
    plain: 'A death within 14 seconds of your last one, after you lived long enough to pick something up. It is the tilt loop: die, respawn, run back naked, die again.',
    count: 'Chained deaths divided by all your deaths.',
    good: 'In 4on4 it turns out not to separate wins from losses once deaths per minute is counted, so the coach shows it but does not coach it. In duels it matters a lot.' },
  { key: 'spawn_deaths', group: 'fighting', name: 'Spawn deaths',
    plain: 'Deaths within 3 seconds of spawning, before you could pick anything up. Some are bad luck (you spawned next to the quad carrier). Many are running the same route out of the spawn every time.' },
  { key: 'tk_pg', group: 'fighting', name: 'Teamkills and team damage',
    plain: 'Teamkills: teammates you killed. Each one costs you a frag and costs them their stack and a spawn. Team damage: health and armor you took off your own team.',
    good: 'The coach charges teamkills in +/- but does not rank them as a lever: the good players are the stacked ones in the middle of the pack and they teamkill more, not less.' },
  { key: 'rl_dmg_per_rocket', group: 'fighting', name: 'Damage per rocket', headline: 'Make every rocket count',
    plain: 'Damage per rocket fired, direct hits and splash together. A direct hit is 100 to 120; a rocket that lands near someone does less; a rocket into a wall does zero.',
    count: 'All your rocket damage divided by rockets fired.',
    good: 'Around 45 a rocket is Level 3 play. The top players are over 55.',
    move: 'Shoot at feet, not at chests. Wait half a second for the shot you can land instead of firing the one you cannot.' },
  { key: 'rl_connect_pct', group: 'fighting', name: 'RL connect %',
    plain: 'The share of your rockets that hurt someone, direct or splash. It is not the same as direct-hit accuracy: a rocket that splashes two players connects.' },
  { key: 'lg_accuracy', group: 'fighting', name: 'LG accuracy',
    plain: 'Of the cells you fired, the share that hit. 30% is a very good fours game; over 35% is elite. Only maps with an LG count (dm3).' },
  { key: 'multi', group: 'fighting', name: 'Multi-frags',
    plain: 'Frags that came within a few seconds of your last one: a double, a triple. A quad run is mostly multi-frags.' },

  // ── the big scores ─────────────────────────────────────────────────────────
  { key: 'plus_minus', group: 'scores', name: '+/- per game',
    plain: 'Your whole game turned into frags: every bit of damage, every kill, every red and quad, every death and teamkill, each turned into frag units by how much it swings a game in NA fours, then added up. It is your raw contribution before we look at who you played with.',
    count: 'Each event is worth what it moves the win chance in the corpus of NA fours. A frag is about one unit; a red or a quad is worth part of a frag; a death costs one.' },
  { key: 'expected', group: 'scores', name: 'Expected',
    plain: 'What an average active player would have scored in your exact spot: same teammates, same opponents, same map. Strong teammates and weak opponents raise it.' },
  { key: 'above_avg', group: 'scores', name: 'Above average per game',
    plain: 'How many frags better (or worse) you were than an average active player would have been in your spot. It is your +/- minus what was expected of you. Zero is average. +15 is Level 4 play. +40 is carrying.',
    count: 'Your +/- minus the expected +/- for your seat, given your teammates and opponents (rated from their own games). Averaged over the last 40 fours. This is the number your level comes from.' },
  { key: 'above_repl', group: 'scores', name: 'Above replacement',
    plain: 'Same as above average, but compared with a "replacement" player: the kind you get when you fill the last slot with whoever is online. Almost everyone is positive here. It is the "how much would we miss you" number.' },
  { key: 'agi', group: 'scores', name: 'Impact (Game Impact Score)',
    plain: 'One grade for one game. 1.00 is the average of the eight players in that game; 1.30 means 30% better than average that night. It counts things +/- cannot see: taking armor, holding stack, not dying.',
    count: 'Adjusted kills, damage, stacked damage ratio, deaths, items taken and multi-frags, each divided by the game average, weighted and added. It is not zero-sum: all four players on the winning team can be above 1.00.' },
  { key: 'efficiency', group: 'scores', name: 'Efficiency',
    plain: 'Frags divided by frags plus deaths. 50% means one death for every frag. 60% means you frag three for every two deaths.' },

  // ── the 1on1 coach ─────────────────────────────────────────────────────────
  { key: 'ra_control', group: 'duel', name: 'Red armor control',
    plain: 'Of the reds in the duel, the share you took. In a duel this is the whole map: the player with the reds wins the fights.' },
  { key: 'fso', group: 'duel', name: 'First-spawn optimization',
    plain: 'How well you used the first seconds after each spawn compared with what the top players do from that same spawn on that map: the route, the first item, the first fight.' },
  { key: 'stack_at_kill', group: 'duel', name: 'Stack at kills',
    plain: 'Your average stack at the moment you got a kill. High means you fight from armor; low means you are winning naked fights, which stops working against better players.' },
  { key: 'pct_stacked', group: 'duel', name: 'Time stacked',
    plain: 'The share of the game you spent with a stack of 150 or more.' },
  { key: 'armor_first', group: 'duel', name: 'Armor first',
    plain: 'The share of your spawns where the first thing you picked up was an armor, not a weapon.' },
  { key: 'restack_sec', group: 'duel', name: 'Restack time',
    plain: 'Seconds after a death until you were back at 150 stack. Lower is better.' },
  { key: 'enemy_stack_at_my_death', group: 'duel', name: 'Enemy stack when you died',
    plain: 'How stacked the enemy was when they killed you. High means you fought them at the wrong time; go take an item instead.' },
  { key: 'item_first', group: 'duel', name: 'Item-first spawns',
    plain: 'Spawns where you took an item before dealing any damage.' },
  { key: 'ddr', group: 'duel', name: 'DDR and stacked DDR',
    plain: 'Damage dealt divided by damage received. Stacked DDR counts only the time you were at 150 or more, so it shows whether you cash in your stacks.' },
]

export const GLOSS: Record<string, GlossEntry> = Object.fromEntries(GLOSSARY.map(e => [e.key, e]))

// Terms inside stat text that deserve their own definition (Peter: "define units, and
// hotlink every reference back to it"). Text is escaped first, then the terms become links.
const TERM_LINKS: [RegExp, string][] = [
  [/\b(units?)\b/gi, 'units'],
  [/\b(effective HP)\b/g, 'stack'],
  [/\b(promotion line)\b/gi, 'target'],
]
export function linkTerms(text: string | null | undefined, skip?: string): string {
  if (!text) return ''
  let out = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  for (const [re, key] of TERM_LINKS) {
    if (key === skip) continue
    out = out.replace(re, (m) => `<a class="term" href="/glossary#${key}">${m}</a>`)
  }
  return out
}
export function gloss(key: string | null | undefined): GlossEntry | undefined { return key ? GLOSS[key] : undefined }
export function glossHref(key: string | null | undefined): string { return key && GLOSS[key] ? `/glossary#${key}` : '/glossary' }

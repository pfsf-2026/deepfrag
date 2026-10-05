<script setup>
// Glossary for the KOTH 1v1 Stats tab's "Advanced Metrics" view (duel numbers read from the
// demos). Linked from the button at the top of that view; each leader card links to its own
// term (#even-fights, #mega-timing, ...). Full write-up: docs/advanced_metrics.md.
useHead({ title: 'Advanced duel metrics: what they mean · DeepFrag' })
const route = useRoute()
const hit = id => route.hash === `#${id}`   // the term a stats-tab card linked to

const stats = [
  { id: 'even-fights', name: 'Even fights won', col: 'Even',
    body: 'A fight is every hit between the two of you with no gap longer than four seconds. It is <strong>even</strong> when neither player was 60 or more health-and-armor ahead at the first hit. This is your record in even fights that ended in a frag.',
    why: 'With the stack taken out of it, what is left is aim, movement and the decisions inside the fight.' },
  { id: 'stacked', name: 'Stacked damage ratio', col: 'Stacked',
    body: 'Damage you dealt while holding 150 or more health-and-armor, divided by the damage you took while holding that much. Above 1.0 you come out ahead when you are stacked.',
    why: 'It is the map-control number. Chip damage while you are weak does not move it; what you do with the armor does.' },
  { id: 'damage', name: 'Damage per minute', col: 'Dmg/min',
    body: 'Damage dealt to the other player per minute, counted the way the in-game stats page counts it (a hit cannot do more than the health that was left).',
    why: 'Pace. Two players can have the same frags and very different amounts of work behind them.' },
  { id: 'behind', name: 'Fights started from behind', col: 'Behind',
    body: 'Of the fights <strong>you</strong> started, the share you started while 60 or more health-and-armor behind. <strong>Lower is better.</strong>',
    why: 'A fight taken 60 behind is won about three times in ten. Against an equal player, when you choose to fight is the lever you control.' },
  { id: 'ra-share', name: 'RA %', col: 'RA %',
    body: 'Of all the red armors taken in your games, the share that went to you.',
    why: 'Whoever takes more red armors wins three duels in four.' },
  { id: 'ra-timing', name: 'RA Timing', col: 'RA Timing',
    body: 'Of the red armors you took, the share you took <strong>within 3 seconds</strong> of it coming back. The one on the map when the game starts is not counted.',
    why: 'Red armor comes back exactly 20 seconds after it is taken, so this is the plainest timing test in the game.',
    caveat: 'Read it next to RA %. Across about 14,000 duels the strongest and weakest quarters of players all sit between 40% and 44% here: a player who owns the armor can pick it up late and lose nothing.' },
  { id: 'mega-timing', name: 'Mega Timing', col: 'Mega Timing',
    body: 'Of the megas you took, the share you took <strong>within 3 seconds</strong> of it coming back. The mega that is on the map when the game starts is not counted.',
    why: 'The mega’s clock only starts once its holder’s extra health has worn off, so it is a harder timer to keep than red armor’s. The weakest quarter of players sit near 37%; everyone else is between 46% and 49%.',
    caveat: 'On its own it is a light guide to who wins: the player with the better Mega Timing wins 54% of duels. Mega Control and Mega % say more.' },
  { id: 'mega-control', name: 'Mega Control', col: 'Mega Control',
    body: 'Every time you take a mega you know when the next one is due and the other player has to guess. <strong>Mega Control</strong> is how often you also took that next one.',
    why: 'You had the timer: were you there? The player with the better number wins 72% of duels. Top-quarter players are near 63%, bottom-quarter players near 45%.' },
  { id: 'mega-share', name: 'Mega %', col: 'Mega %',
    body: 'Of all the megas taken in your games, the share that went to you.',
    why: 'The strongest single item number we have: the player who takes more megas wins 75% of duels.' },
  { id: 'top-speed', name: 'Top 10% Speed', col: 'Top 10% Speed',
    body: 'The speed you are at or above for the fastest tenth of the time you are alive, in units per second. Running is 320; the quickest players are near 500 or above.',
    why: 'Movement is half the game, and of everything we read from how a player moves, this is the number that goes with winning most.' },
  { id: 'avg-speed', name: 'Avg Speed', col: 'Avg Speed',
    body: 'Your average speed over the game, in units per second: the same number the end-of-match stats show. The middle player averages about 317.',
    why: 'How much of the game you spend moving at pace. It goes with winning too, though less than Top 10% Speed does.' },
]
</script>

<template>
<div class="guide">
  <NuxtLink class="back" to="/ladder?l=1v1#stats">← back to stats</NuxtLink>
  <h1>Advanced duel metrics: what they mean</h1>
  <p class="intro">
    These are read from <strong>the demo of every game</strong>, not the end-of-match scoreboard, so they see
    what a scoreboard cannot: who had the stack when a fight started, who took each item and when, and how
    fast each player was moving. There is no plus/minus here. In a duel that is the score.
  </p>

  <section id="games" class="stat" :class="{ hit: hit('games') }">
    <h2>Which games are counted</h2>
    <p><strong>Ladder Matches</strong> counts only the maps played in ladder matches. <strong>Last 90 Days Overall</strong> counts every duel a ladder player finished in that time, against anyone.</p>
    <p>A dash means there is not enough behind that number yet. A dimmed row is a player with only a few games in the view.</p>
  </section>

  <section id="opponent-rating" class="stat" :class="{ hit: hit('opponent-rating') }">
    <h2>Opponent rating</h2>
    <p>A player who mostly plays stronger opponents has every number pulled down by it. The <strong>Opponent rating</strong> switch shows the same table for only part of the games, going by both players' 1on1 ratings just before each game:</p>
    <p><strong>Evenly matched</strong>: the opponent was rated within 200 points. <strong>Higher rated</strong>: the opponent was 200 or more points above. <strong>Lower rated</strong>: 200 or more points below.</p>
    <p class="why"><strong>Why 200:</strong> inside 200 points the higher-rated player wins about 60% of the time, which is still a contest. At 200 to 250 that jumps to 74%, and past 400 it is nine in ten or more.</p>
  </section>

  <section v-for="s in stats" :id="s.id" :key="s.id" class="stat" :class="{ hit: hit(s.id) }">
    <h2>{{ s.name }} <span v-if="s.col !== s.name" class="col">{{ s.col }}</span></h2>
    <p v-html="s.body"></p>
    <p v-if="s.why" class="why"><strong>Why it matters:</strong> {{ s.why }}</p>
    <p v-if="s.caveat" class="caveat">{{ s.caveat }}</p>
  </section>

  <section class="stat">
    <h2>Where the numbers come from</h2>
    <p>
      Every finished duel with a demo is read once, a few minutes after it shows up, and the result is stored.
      The win rates quoted above come from about 14,000 duels played between March 2024 and September 2026.
    </p>
  </section>

  <NuxtLink class="back" to="/ladder?l=1v1#stats">← back to stats</NuxtLink>
</div>
</template>

<style scoped>
.guide { max-width: 760px; margin: 0 auto; padding: 14px 18px 60px; color: var(--fg, #f2ead9); line-height: 1.6; }
.back { display: inline-block; margin: 10px 0; padding: 8px 0; font-size: 13px; color: var(--accent, #ff7a1a); text-decoration: none; }
h1 { font-size: 26px; font-weight: 800; margin: 6px 0 12px; text-wrap: balance; }
.intro { color: var(--fg-2, #c9bca9); font-size: 14px; background: var(--panel, #14100c); border: 1px solid var(--border, #2a2018); border-left: 3px solid var(--accent, #ff7a1a); border-radius: 10px; padding: 14px 16px; }
.intro strong { color: var(--fg, #f2ead9); }
/* a card on the stats tab links straight to its term: land below the sticky header and mark it */
.stat { margin-top: 22px; scroll-margin-top: 84px; }
.stat.hit { background: var(--panel, #14100c); border: 1px solid var(--accent, #ff7a1a); border-radius: 10px; padding: 12px 14px; margin-left: -15px; margin-right: -15px; }
.stat h2 { font-size: 16px; font-weight: 800; margin: 0 0 4px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.col { font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--accent, #ff7a1a); background: rgba(255,122,26,.1); border: 1px solid rgba(255,122,26,.3); border-radius: 5px; padding: 1px 7px; }
.stat p { margin: 4px 0; font-size: 14px; color: #d9cfbd; overflow-wrap: anywhere; }
.stat p :deep(strong) { color: var(--fg, #f2ead9); }
.why { color: var(--fg-2, #c9bca9) !important; font-size: 13px !important; }
.why strong { color: var(--accent, #ff7a1a); }
.caveat { color: var(--draw, #f59e0b) !important; font-size: 12.5px !important; }
@media (max-width: 480px) { h1 { font-size: 22px; } .guide { padding: 10px 16px 48px; } }
</style>

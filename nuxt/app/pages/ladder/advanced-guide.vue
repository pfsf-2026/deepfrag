<script setup>
// Glossary for the KOTH 1v1 Stats tab's "Advanced" view (duel numbers read from the demos).
// Linked from the top of that view. Full write-up: docs/advanced_metrics.md.
useHead({ title: 'Advanced duel stats: what they mean · DeepFrag' })

const stats = [
  { k: 'even', name: 'Even fights won', col: 'Even',
    body: 'A fight is every hit between the two of you with no gap longer than four seconds. It is <strong>even</strong> when neither player was 60 or more health-and-armor ahead at the first hit. This is your record in even fights that ended in a frag.',
    why: 'With the stack taken out of it, what is left is aim, movement and the decisions inside the fight.' },
  { k: 'stacked', name: 'Stacked damage ratio', col: 'Stacked',
    body: 'Damage you dealt while holding 150 or more health-and-armor, divided by the damage you took while holding that much. Above 1.0 you come out ahead when you are stacked.',
    why: 'It is the map-control number. Chip damage while you are weak does not move it; what you do with the armor does.' },
  { k: 'dmg', name: 'Damage per minute', col: 'Dmg/min',
    body: 'Damage dealt to the other player per minute, counted the way the in-game stats page counts it (a hit cannot do more than the health that was left).',
    why: 'Pace. Two players can have the same frags and very different amounts of work behind them.' },
  { k: 'behind', name: 'Fights started from behind', col: 'Behind',
    body: 'Of the fights <strong>you</strong> started, the share you started while 60 or more health-and-armor behind. <strong>Lower is better.</strong>',
    why: 'A fight taken 60 behind is won about three times in ten. Against an equal player, when you choose to fight is the lever you control.' },
  { k: 'ra', name: 'Red armor share', col: 'RA',
    body: 'Of all the red armors taken in your games, the share that went to you.',
    why: 'Whoever takes more red armors wins three duels in four. How quickly it gets picked up after it comes back does not separate players at all, so the tab shows the share and leaves that out.' },
  { k: 'mega', name: 'Mega share', col: 'Mega',
    body: 'Of all the megas taken in your games, the share that went to you.',
    why: 'The strongest single item number we have: the player who takes more megas wins 75% of duels.' },
  { k: 'held', name: 'Mega held', col: 'Held',
    body: 'Every time you take a mega you know when the next one is due and the other player has to guess. <strong>Held</strong> is how often you also took that next one.',
    why: 'This is mega timing in the sense that wins games: you had the timer, were you there? The player with the better number wins 72% of duels. Top-quarter players hold about 63%, bottom-quarter players about 45%.' },
  { k: 'ontime', name: 'Mega on time', col: 'On time',
    body: 'Of the megas you took, the share you took <strong>within one second</strong> of it coming back. The mega that is on the map when the game starts is not counted.',
    why: 'Precision. Most players are between 10% and 20%; the sharpest are above 25%.',
    caveat: 'Read it next to Held and Mega share, not instead of them. On its own it is a weak guide to who wins (the player with the better number wins about 59% of the time), because a player who owns the mega can take it late and lose nothing. It is also jumpy until you have a few dozen megas behind it.' },
  { k: 'speed', name: 'Cruising top speed', col: 'Speed',
    body: 'The speed you are at or above for the fastest tenth of the time you are alive, in units per second. Running is 320; the quickest players cruise near 500 or above.',
    why: 'Movement is half the game, and of everything we read from how a player moves, this is the number that goes with winning most.' },
  { k: 'hop', name: 'Speed gained per hop', col: 'Hop',
    body: 'The typical speed, in units per second, that one of your bunny hops adds. Read from every hop in your games: wall bumps and rocket-boosted hops are left out.',
    why: 'This is the mechanic the strafe coach on den.qwsrv.com:29001 trains, and the AI Coach page has the full movement report.',
    caveat: 'A hop adds less the faster you are already going, so a player who rarely gets up to speed can post a big number here. Read it next to Speed.' },
]
</script>

<template>
<div class="guide">
  <NuxtLink class="back" to="/ladder?l=1v1#stats">← back to stats</NuxtLink>
  <h1>Advanced duel stats: what they mean</h1>
  <p class="intro">
    These are read from <strong>the demo of every game</strong>, not the end-of-match scoreboard, so they see
    what a scoreboard cannot: who had the stack when a fight started, who took each item and when, and what
    every hop gained. There is no plus/minus here. In a duel that is the score.
  </p>

  <section class="stat">
    <h2>Two ways to look</h2>
    <p><strong>Last 60 days</strong> counts every duel a ladder player finished in that time, against anyone. <strong>Ladder matches</strong> counts only the maps played in ladder matches. A new ladder is two to four maps per player, which is too few to read much into, so the 60-day view is shown first until the ladder has more games behind it.</p>
    <p>A dash means there is not enough behind that number yet. A dimmed row is a player with only a few games in the view.</p>
  </section>

  <section v-for="s in stats" :key="s.k" class="stat">
    <h2>{{ s.name }} <span class="col">{{ s.col }}</span></h2>
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
.stat { margin-top: 22px; }
.stat h2 { font-size: 16px; font-weight: 800; margin: 0 0 4px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.col { font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--accent, #ff7a1a); background: rgba(255,122,26,.1); border: 1px solid rgba(255,122,26,.3); border-radius: 5px; padding: 1px 7px; }
.stat p { margin: 4px 0; font-size: 14px; color: #d9cfbd; overflow-wrap: anywhere; }
.stat p :deep(strong) { color: var(--fg, #f2ead9); }
.why { color: var(--fg-2, #c9bca9) !important; font-size: 13px !important; }
.why strong { color: var(--accent, #ff7a1a); }
.caveat { color: var(--draw, #f59e0b) !important; font-size: 12.5px !important; }
@media (max-width: 480px) { h1 { font-size: 22px; } .guide { padding: 10px 16px 48px; } }
</style>

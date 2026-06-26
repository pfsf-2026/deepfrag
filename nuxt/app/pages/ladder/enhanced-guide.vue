<script setup>
// Detailed glossary for the ladder Enhanced Stats (mvd-api demo-parser metrics).
// Linked from the top of the Stats tab's "✨ Enhanced" view.
useHead({ title: 'Enhanced Stats — what they mean · DeepFrag' })

const stats = [
  { k: 'dmg', name: 'Damage / map', col: 'Dmg',
    body: 'Total damage you dealt to enemies, averaged per map — summed from the demo’s <strong>per-hit</strong> log (every shot that connected, direct and splash). Real damage output, independent of who got the frag.',
    why: 'A high fragger riding a teammate looks great on the scoreboard; damage shows who’s actually doing the work.' },
  { k: 'fd', name: 'Frag +/− per map', col: '+/−',
    body: 'Kills minus deaths, per map. A clean read on whether you come out ahead in the exchanges you take.',
    why: 'Frags alone reward aggression; the differential rewards <em>winning</em> fights, not just starting them.' },
  { k: 'spot', name: 'Spot → Fire (reaction)', col: 'Spot→Fire',
    body: 'The headline new metric. The parser knows, frame by frame, the exact moment a <strong>clear line of sight</strong> opens between you and an enemy — walls and map geometry accounted for (computed against the map’s BSP). This is the <strong>median time from that sightline opening to your first shot landing on them</strong>: how fast you find a target and put damage on it once it’s genuinely visible. Lower is faster.',
    why: 'It isolates pure target acquisition from positioning/luck — the closest thing we have to a raw "reflexes + tracking" number.',
    caveat: 'Includes your network ping, so compare players to each other, not to an absolute "human" figure. Averaged over every spot-then-hit sequence in the match (the "sample" count).' },
  { k: 'rkts', name: 'Rockets that hit / map', col: 'Rkts hit',
    body: 'How many of your rockets actually <strong>caused damage</strong> per map (direct + splash). The scoreboard only gives an accuracy %; this is real landed-rocket volume.',
    why: 'Rocket pressure is the engine of QW damage — this is how much of it you’re generating.' },
  { k: 'dirspl', name: 'Direct / Splash', col: 'Direct · Splash',
    body: 'Of those damaging rockets, how many were <strong>direct</strong> hits versus <strong>splash</strong> (blast) damage, per map.',
    why: 'A high direct share is precision; lots of splash is area-control / chip damage — two very different rocket styles.' },
  { k: 'avg', name: 'Average rocket', col: 'Avg rkt',
    body: 'The average damage of each rocket that landed. (Already a per-rocket figure, so it isn’t divided by maps.)',
    why: 'Big directs and well-placed splash push this up; grazing chip damage pulls it down — a quality-of-contact number.' },
  { k: 'rl', name: 'RL preference', col: 'RL%',
    body: 'Of your combined rocket + lightning damage, the share dealt with the <strong>rocket launcher</strong>. 80% means you lean heavily on RL; 50% is a balanced RL/LG split.',
    why: 'Shows weapon style and, paired with accuracy, whether someone should be picking up the shaft more.' },
  { k: 'ewep', name: 'EWep (vs armed)', col: 'EWep',
    body: 'The share of your damage dealt to <strong>armed</strong> enemies — opponents actually holding a real weapon (RL/LG/SG) rather than freshly spawned with a peashooter.',
    why: 'Damage on dangerous, fighting-back opponents is far harder than farming the under-armed. With 2v2 weapon-stay everyone’s usually armed, so it clusters high — it matters most in 4v4.' },
]
</script>

<template>
<div class="guide">
  <NuxtLink class="back" to="/ladder#stats">← back to stats</NuxtLink>
  <h1>✨ Enhanced Stats — what they mean</h1>
  <p class="intro">
    These come from <strong>parsing the actual demo</strong> (the mvd-api parser), not the
    end-of-match scoreboard — so they see things a box score can’t: where rockets landed,
    who you were fighting, and how fast you reacted once you could actually see them.
    Everything is a <strong>per-map average</strong> (totals ÷ maps played) so a player with
    more games stays comparable to one with fewer.
  </p>

  <section v-for="s in stats" :key="s.k" class="stat">
    <h2>{{ s.name }} <span class="col">{{ s.col }}</span></h2>
    <p v-html="s.body"></p>
    <p v-if="s.why" class="why"><strong>Why it matters:</strong> {{ s.why }}</p>
    <p v-if="s.caveat" class="caveat">⚠ {{ s.caveat }}</p>
  </section>

  <section class="stat">
    <h2>Where the data comes from</h2>
    <p>
      Each reported ladder match links its maps to the ingested demos. We parse every map
      once with the current parser version and store the result — the numbers are stable and
      we never re-parse the same demo twice. New metrics light up automatically as the parser
      gains them.
    </p>
  </section>

  <NuxtLink class="back" to="/ladder#stats">← back to stats</NuxtLink>
</div>
</template>

<style scoped>
.guide { max-width: 760px; margin: 0 auto; padding: 14px 18px 60px; color: var(--fg, #e8edf5); line-height: 1.6; }
.back { display: inline-block; margin: 12px 0; font-size: 13px; color: var(--accent, #14e6c0); text-decoration: none; }
h1 { font-size: 26px; font-weight: 800; margin: 6px 0 12px; }
.intro { color: var(--fg-2, #94a3b8); font-size: 14px; background: var(--panel, #131820); border: 1px solid var(--border, #2b3445); border-left: 3px solid var(--accent, #14e6c0); border-radius: 10px; padding: 14px 16px; }
.intro strong { color: var(--fg, #e8edf5); }
.stat { margin-top: 22px; }
.stat h2 { font-size: 16px; font-weight: 800; margin: 0 0 4px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.col { font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--accent, #14e6c0); background: rgba(20,230,192,.1); border: 1px solid rgba(20,230,192,.3); border-radius: 5px; padding: 1px 7px; }
.stat p { margin: 4px 0; font-size: 14px; color: #cfd8e6; }
.stat p :deep(strong) { color: var(--fg, #e8edf5); }
.why { color: var(--fg-2, #94a3b8) !important; font-size: 13px !important; }
.why strong { color: var(--accent, #14e6c0); }
.caveat { color: var(--draw, #f59e0b) !important; font-size: 12.5px !important; }
</style>

<script setup>
// KOTH 1v1 Stats tab, "Advanced" view: demo-derived duel numbers for the ladder's players
// (/api/ladder/{id}/duel-stats). Two lenses: every duel they finished in the last N days,
// or only the maps played in ladder matches (thin for the ladder's first weeks). No +/-:
// in a duel that is the score.
const props = defineProps({ ladderId: { type: Number, required: true } })
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const data = ref(null); const loading = ref(true); const failed = ref(false)
const lens = ref('recent')
const sortKey = ref('rung'); const sortDir = ref(1)

async function load() {
  loading.value = true; failed.value = false
  try {
    data.value = await $fetch(`${base}/api/ladder/${props.ladderId}/duel-stats`)
    lens.value = data.value.default || 'recent'
  } catch (e) { failed.value = true; console.error('[duelstats]', e) } finally { loading.value = false }
}
onMounted(load)
watch(() => props.ladderId, load)

// k = field · l = header · g = starts a column group · low = lower is better · t = hover text
const COLS = [
  { k: 'even_win_pct', l: 'Even', g: 'Fights', pct: true, t: 'Even fights won: fights that ended in a frag where neither player was 60+ health and armor ahead when it started' },
  { k: 'stacked_ratio', l: 'Stacked', fix: 2, t: 'Damage dealt ÷ damage taken while holding 150+ health and armor' },
  { k: 'dmg_pm', l: 'Dmg/min', int: true, t: 'Damage dealt per minute' },
  { k: 'behind_pct', l: 'Behind', g: 'Discipline', pct: true, low: true, t: 'Share of the fights you started while 60+ health and armor behind. Lower is better' },
  { k: 'ra_share', l: 'RA', g: 'Items', pct: true, cls: 'c-ra', t: 'Your share of the red armors taken in your games' },
  { k: 'mh_share', l: 'Mega', pct: true, cls: 'c-mh', t: 'Your share of the megas taken in your games' },
  { k: 'mh_held_pct', l: 'Held', pct: true, cls: 'c-mh', t: 'After you took a mega, how often you also took the next one' },
  { k: 'mh_on_time_pct', l: 'On time', pct: true, cls: 'c-mh', t: 'Megas you took within a second of it coming back' },
  { k: 'top_speed', l: 'Speed', g: 'Movement', int: true, t: 'Cruising top speed: you are at or above this speed for the fastest tenth of the game' },
  { k: 'hop_gain', l: 'Hop', fix: 1, t: 'Speed gained per bunny hop, in units per second' },
]
const GROUPS = COLS.reduce((acc, c) => { if (c.g) acc.push({ name: c.g, n: 1 }); else acc[acc.length - 1].n++; return acc }, [])
const LEADERS = [
  { k: 'even_win_pct', title: 'Even fights', sub: 'won when neither player had the edge' },
  { k: 'mh_held_pct', title: 'Mega timing', sub: 'took the next mega after taking one' },
  { k: 'behind_pct', title: 'Discipline', sub: 'fewest fights started from behind' },
  { k: 'top_speed', title: 'Movement', sub: 'cruising top speed' },
]

const rows = computed(() => data.value?.lenses?.[lens.value]?.players || [])
// a few games say little: below this a row is dimmed and cannot lead a column
const floor = computed(() => (lens.value === 'recent' ? 5 : 2))
const qualifies = r => r.games >= floor.value
const sorted = computed(() => {
  const k = sortKey.value, dir = sortDir.value
  return [...rows.value].sort((a, b) => {
    const av = a[k], bv = b[k]
    if (av == null || bv == null) return (av == null) - (bv == null)   // blanks last either way
    return (av - bv) * dir
  })
})
function sortBy(c) {
  if (sortKey.value === c.k) sortDir.value *= -1
  else { sortKey.value = c.k; sortDir.value = c.low ? 1 : -1 }
}
function sortRung() { sortKey.value = 'rung'; sortDir.value = 1 }

const range = computed(() => {
  const out = {}
  for (const c of COLS) {
    const vals = rows.value.filter(qualifies).map(r => r[c.k]).filter(v => v != null)
    out[c.k] = vals.length >= 2 ? { min: Math.min(...vals), max: Math.max(...vals) } : null
  }
  return out
})
// 0..1 along the column, 1 = best (so "Behind" runs the other way)
function frac(r, c) {
  const g = range.value[c.k], v = r[c.k]
  if (!g || v == null || g.max === g.min) return 0
  const f = Math.min(1, Math.max(0, (v - g.min) / (g.max - g.min)))
  return c.low ? 1 - f : f
}
const isBest = (r, c) => qualifies(r) && range.value[c.k] && frac(r, c) === 1
function fmt(v, c) {
  if (v == null) return '—'
  if (c.pct) return Math.round(v) + '%'
  if (c.int) return Math.round(v).toLocaleString()
  return v.toFixed(c.fix ?? 0)
}
const leaders = computed(() => LEADERS.map((L) => {
  const c = COLS.find(x => x.k === L.k)
  const pool = rows.value.filter(r => qualifies(r) && r[L.k] != null)
  if (pool.length < 3) return null
  const top = pool.reduce((a, b) => ((c.low ? b[L.k] < a[L.k] : b[L.k] > a[L.k]) ? b : a))
  return { ...L, name: top.name, cid: top.canonical_id, value: fmt(top[L.k], c) }
}).filter(Boolean))
const lensNote = computed(() => {
  if (!data.value) return ''
  if (lens.value === 'recent') return `every duel they finished, any opponent · ${rows.value.length} of ${data.value.entrants} players`
  const n = data.value.lenses.ladder.maps
  return `${n} map${n === 1 ? '' : 's'} played in ladder matches`
})
</script>

<template>
  <div class="ds">
    <div v-if="loading" class="muted small pad">Loading advanced stats…</div>
    <div v-else-if="failed" class="muted small pad">Could not load the advanced stats. <button class="retry" @click="load">Try again</button></div>
    <template v-else-if="data">
      <div class="ds-bar">
        <span class="seg" role="group" aria-label="Which games to count">
          <button :class="{ on: lens === 'recent' }" @click="lens = 'recent'">Last {{ data.days }} days</button>
          <button :class="{ on: lens === 'ladder' }" @click="lens = 'ladder'">Ladder matches</button>
        </span>
        <span class="ds-note">{{ lensNote }}</span>
        <NuxtLink to="/ladder/advanced-guide" class="glink">What do these mean? →</NuxtLink>
      </div>

      <div v-if="leaders.length" class="leaders">
        <NuxtLink v-for="L in leaders" :key="L.k" :to="`/p/${L.cid}`" class="lead">
          <span class="lead-t">{{ L.title }}</span>
          <span class="lead-n">{{ L.name }}</span>
          <span class="lead-v">{{ L.value }}</span>
          <span class="lead-s">{{ L.sub }}</span>
        </NuxtLink>
      </div>

      <div v-if="rows.length" class="scroll">
        <table class="adv">
          <thead>
            <tr class="grp">
              <th class="team" /><th />
              <th v-for="g in GROUPS" :key="g.name" :colspan="g.n" class="colgrp">{{ g.name }}</th>
            </tr>
            <tr>
              <th class="team" :class="{ sorted: sortKey === 'rung' }" title="Ladder order" @click="sortRung">Player</th>
              <th class="plain" title="Wins and losses in these games">W–L</th>
              <th v-for="c in COLS" :key="c.k" :class="{ sorted: sortKey === c.k, colgrp: c.g }" :title="c.t" @click="sortBy(c)">{{ c.l }}<span v-if="sortKey === c.k">{{ sortDir < 0 ? ' ▾' : ' ▴' }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in sorted" :key="p.canonical_id" :class="{ thin: !qualifies(p) }">
              <td class="team"><span class="tc"><span class="rung">{{ p.rung ?? '–' }}</span><NuxtLink :to="`/p/${p.canonical_id}`" class="pl-name">{{ p.name }}</NuxtLink></span></td>
              <td class="wl">{{ p.wins }}–{{ p.losses }}</td>
              <td v-for="c in COLS" :key="c.k" :class="[c.cls, { colgrp: c.g, best: isBest(p, c) }]">
                {{ fmt(p[c.k], c) }}<i v-if="p[c.k] != null && range[c.k]" class="m" :style="{ '--f': frac(p, c) }" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="muted small pad">
        {{ lens === 'ladder' ? 'No ladder maps scored yet. They show up a few minutes after a match is recorded.' : 'No duels with demos in this window yet.' }}
      </div>

      <p v-if="rows.length" class="ds-foot">
        Read from the demo of every game, not the scoreboard. The bar under a number shows where it sits between the lowest and highest
        player in that column. A dash, or a dimmed row, means too few games to say (under {{ floor }}).
      </p>
    </template>
  </div>
</template>

<style scoped>
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 18px 0; }
.retry { background: none; border: 0; color: var(--accent); font: inherit; cursor: pointer; padding: 8px 4px; }
.ds-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; margin-bottom: 14px; }
.seg { display: inline-flex; gap: 2px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 2px; }
.seg button { background: none; border: 0; color: var(--fg-3); font-family: inherit; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap; }
.seg button.on { background: var(--panel-3); color: var(--fg); }
.ds-note { font-size: 12px; color: var(--fg-3); flex: 1 1 200px; min-width: 0; }
.glink { font-size: 12px; color: var(--accent); text-decoration: none; font-weight: 600; white-space: nowrap; }
.glink:hover { text-decoration: underline; }

.leaders { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.lead { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 8px; row-gap: 2px; align-items: baseline; background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; text-decoration: none; color: var(--fg); }
.lead:hover { border-color: var(--accent); }
.lead-t { grid-column: 1 / -1; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--accent); font-weight: 800; }
.lead-n { font-size: 15px; font-weight: 800; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lead-v { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-size: 15px; font-weight: 700; }
.lead-s { grid-column: 1 / -1; font-size: 11.5px; color: var(--fg-3); line-height: 1.35; }

.scroll { overflow-x: auto; }
table.adv { --px: 9px; border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13px; }
table.adv th, table.adv td { padding: 7px var(--px); text-align: right; white-space: nowrap; }
table.adv th { font-size: 11px; color: var(--fg-3); font-weight: 700; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; }
table.adv th.plain { cursor: default; }
table.adv th.sorted { color: var(--accent); }
table.adv tr.grp th { border-bottom: 0; padding-bottom: 2px; text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; cursor: default; }
table.adv th.team, table.adv td.team { text-align: left; position: sticky; left: 0; z-index: 1; background: var(--panel); }
table.adv td { position: relative; font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; border-bottom: 1px solid rgba(42,32,24,.45); padding-bottom: 10px; }
table.adv tbody tr:hover td { background: var(--panel-2); }
table.adv .colgrp { border-left: 1px solid var(--border); }
table.adv td.best { font-weight: 800; color: var(--accent); }
table.adv td.wl { color: var(--fg-2); }
table.adv tr.thin td:not(.team) { opacity: .5; }
/* where this value sits in its column: full width = the best player */
.m { position: absolute; right: var(--px); bottom: 4px; height: 2px; border-radius: 1px; background: currentColor; opacity: .38;
     width: max(2px, calc((100% - 2 * var(--px)) * var(--f, 0))); }
td.best .m { opacity: .9; }
.tc { display: flex; align-items: center; gap: 8px; font-family: system-ui, sans-serif; font-weight: 700; }
.rung { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; min-width: 22px; padding: 1px 4px; border-radius: 4px; background: var(--panel-3); color: var(--fg-3); text-align: center; box-sizing: border-box; flex: 0 0 auto; }
.pl-name { color: var(--fg); text-decoration: none; font-weight: 700; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-name:hover { color: var(--accent); }
.c-ra { color: var(--loss); } .c-mh { color: #60a5fa; }
.ds-foot { margin: 12px 2px 0; font-size: 12px; line-height: 1.5; color: var(--fg-3); max-width: 78ch; }

@media (max-width: 880px) {
  .leaders { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .seg button { padding: 9px 12px; min-height: 36px; }
  .glink { display: inline-flex; align-items: center; min-height: 36px; }
  /* taller tap area for the name without making the row taller */
  .pl-name { max-width: 104px; padding: 8px 0; margin: -8px 0; }
  table.adv th { padding-top: 10px; padding-bottom: 10px; }
}
@media (max-width: 480px) {
  table.adv { --px: 7px; }
  .tc { gap: 6px; }
}
@media (max-width: 360px) {
  .lead { padding: 9px 10px; }
  .lead-n, .lead-v { font-size: 14px; }
  .pl-name { max-width: 76px; }
}
</style>

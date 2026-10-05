<script setup>
// KOTH 1v1 Stats tab, "Advanced Metrics" view: demo-derived duel numbers for the ladder's
// players (/api/ladder/{id}/duel-stats). Two lenses (maps played in ladder matches, or every
// duel in the last N days), each of which can be cut by how the opponent was rated going
// into the game. No +/-: in a duel that is the score.
const props = defineProps({ ladderId: { type: Number, required: true } })
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const GUIDE = '/ladder/advanced-guide'
const WL_TIP = 'Wins and losses in the games being counted.'
const data = ref(null); const loading = ref(true); const failed = ref(false)
const lens = ref('ladder')
const opp = ref('all')
const sortKey = ref('rung'); const sortDir = ref(1)

async function load() {
  loading.value = true; failed.value = false
  try {
    data.value = await $fetch(`${base}/api/ladder/${props.ladderId}/duel-stats`)
    lens.value = data.value.default || 'ladder'
  } catch (e) { failed.value = true; console.error('[duelstats]', e) } finally { loading.value = false }
}
onMounted(load)
watch(() => props.ladderId, load)

// k = field · l = header · n = full name · a = glossary anchor · g = starts a column group
// low = lower is better · t = what the tooltip says
const COLS = [
  { k: 'even_win_pct', l: 'Even', n: 'Even fights won', a: 'even-fights', g: 'Fights', pct: true, t: 'Fights that ended in a frag where neither player was 60+ health and armor ahead when it started.' },
  { k: 'stacked_ratio', l: 'Stacked', n: 'Stacked damage ratio', a: 'stacked', fix: 2, t: 'Damage dealt ÷ damage taken while holding 150+ health and armor.' },
  { k: 'dmg_pm', l: 'Dmg/min', n: 'Damage per minute', a: 'damage', int: true, t: 'Damage dealt to the other player per minute.' },
  { k: 'behind_pct', l: 'Behind', n: 'Fights started from behind', a: 'behind', g: 'Discipline', pct: true, low: true, t: 'Share of the fights you started while 60+ health and armor behind. Lower is better.' },
  { k: 'ra_share', l: 'RA\u00A0%', n: 'RA %', a: 'ra-share', g: 'Items', pct: true, cls: 'c-ra', t: 'Your share of the red armors taken in your games.' },
  { k: 'ra_on_time_pct', l: 'RA Timing', n: 'RA Timing', a: 'ra-timing', pct: true, cls: 'c-ra', t: 'Red armors you took within 3 seconds of it coming back.' },
  { k: 'mh_on_time_pct', l: 'Mega Timing', n: 'Mega Timing', a: 'mega-timing', pct: true, cls: 'c-mh', t: 'Megas you took within 3 seconds of it coming back.' },
  { k: 'mh_held_pct', l: 'Mega Control', n: 'Mega Control', a: 'mega-control', pct: true, cls: 'c-mh', t: 'After you took a mega, how often you also took the next one.' },
  { k: 'mh_share', l: 'Mega\u00A0%', n: 'Mega %', a: 'mega-share', pct: true, cls: 'c-mh', t: 'Your share of the megas taken in your games.' },
  { k: 'top_speed', l: 'Top 10% Speed', n: 'Top 10% Speed', a: 'top-speed', g: 'Movement', int: true, t: 'You are at or above this speed for the fastest tenth of the game.' },
  { k: 'avg_speed', l: 'Avg Speed', n: 'Avg Speed', a: 'avg-speed', int: true, t: 'Your average speed over the game, as the end-of-match stats report it.' },
]
// header text that may wrap: everything but the last word, then the last word (kept with its icon).
// "RA %" and "Mega %" carry a no-break space so the % never drops to its own line.
for (const c of COLS) { const w = c.l.split(' '); c.tail = w.pop(); c.head = w.join(' ') }
const GROUPS = COLS.reduce((acc, c) => { if (c.g) acc.push({ name: c.g, n: 1 }); else acc[acc.length - 1].n++; return acc }, [])
const LEADERS = [
  { k: 'even_win_pct', title: 'Even Fights', sub: 'won when neither player had the edge' },
  { k: 'mh_on_time_pct', title: 'Mega Timing', sub: 'megas taken within 3 seconds of coming back' },
  { k: 'behind_pct', title: 'Discipline', sub: 'fewest fights started from behind' },
  { k: 'top_speed', title: 'Movement', sub: 'top 10% speed' },
]
const gap = computed(() => data.value?.opp_gap ?? 200)
const OPPS = computed(() => [
  { k: 'all', l: 'All', s: 'All', t: 'Every game, whoever the opponent was.' },
  { k: 'even', l: 'Evenly matched', s: 'Even', t: `Only games where the opponent was rated within ${gap.value} points of the player going in.` },
  { k: 'higher', l: 'Higher rated', s: 'Higher', t: `Only games where the opponent was rated ${gap.value} or more points higher going in.` },
  { k: 'lower', l: 'Lower rated', s: 'Lower', t: `Only games where the opponent was rated ${gap.value} or more points lower going in.` },
])

const view = computed(() => data.value?.lenses?.[lens.value])
const rows = computed(() => (opp.value === 'all' ? view.value?.players : view.value?.opp?.[opp.value]) || [])
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
  return { ...L, a: c.a, name: top.name, value: fmt(top[L.k], c) }
}).filter(Boolean))
const lensNote = computed(() => {
  const d = data.value
  if (!d) return ''
  const n = d.lenses.ladder.maps
  const what = lens.value === 'ladder' ? `${n} map${n === 1 ? '' : 's'} played in ladder matches` : `every duel they finished in the last ${d.days} days`
  const who = {
    all: '',
    even: `, only against opponents rated within ${gap.value} points going in`,
    higher: `, only against opponents rated ${gap.value}+ points higher going in`,
    lower: `, only against opponents rated ${gap.value}+ points lower going in`,
  }[opp.value]
  return `${what}${who} · ${rows.value.length} of ${d.entrants} players`
})

// Tooltip: shows a quarter of a second after the pointer lands (the browser's own title
// tooltip takes about a second), or at once when its (i) is tapped or focused. Drawn on
// <body> so the table's scroll frame cannot clip it.
const TIP_DELAY = 250
const tip = ref(null)             // { title, text, x, y, below }
let tipTimer = null
function showTip(ev, title, text, delay = TIP_DELAY) {
  const el = ev.currentTarget
  clearTimeout(tipTimer)
  tipTimer = setTimeout(() => {
    const r = el.getBoundingClientRect()
    const vw = document.documentElement.clientWidth
    const half = Math.min(130, (vw - 16) / 2)
    const below = r.top < 120      // no room above: drop it under the header instead
    tip.value = { title, text, below, x: Math.min(vw - 8 - half, Math.max(8 + half, r.left + r.width / 2)), y: below ? r.bottom + 8 : r.top - 8 }
  }, delay)
}
function hideTip() { clearTimeout(tipTimer); tip.value = null }
const hoverTip = (ev, title, text) => { if (ev.pointerType === 'mouse') showTip(ev, title, text) }
function tapTip(ev, title, text) {
  if (tip.value?.title === title) hideTip()
  else showTip(ev, title, text, 0)
}
onMounted(() => { window.addEventListener('scroll', hideTip, true); window.addEventListener('resize', hideTip) })
onBeforeUnmount(() => { hideTip(); window.removeEventListener('scroll', hideTip, true); window.removeEventListener('resize', hideTip) })
watch([lens, opp], hideTip)
</script>

<template>
  <div class="ds" @click="hideTip">
    <div v-if="loading" class="muted small pad">Loading advanced metrics…</div>
    <div v-else-if="failed" class="muted small pad">Could not load the advanced metrics. <button class="retry" @click="load">Try again</button></div>
    <template v-else-if="data">
      <div class="ds-bar">
        <div class="ctl">
          <span class="ctl-l">Games</span>
          <span class="seg" role="group" aria-label="Which games to count">
            <button :class="{ on: lens === 'ladder' }" @click="lens = 'ladder'">Ladder Matches</button>
            <button :class="{ on: lens === 'recent' }" @click="lens = 'recent'">Last {{ data.days }} Days Overall</button>
          </span>
        </div>
        <div class="ctl">
          <span class="ctl-l">Opponent rating</span>
          <span class="seg" role="group" aria-label="Opponent rating">
            <button v-for="o in OPPS" :key="o.k" :class="{ on: opp === o.k }"
                    @click="opp = o.k" @pointerenter="hoverTip($event, o.l, o.t)" @pointerleave="hideTip">
              <span class="long">{{ o.l }}</span><span class="short">{{ o.s }}</span>
            </button>
          </span>
        </div>
        <NuxtLink :to="GUIDE" class="help-btn">
          <svg class="help-i" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.6" /><path d="M6.2 6.3a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.6-.8 1.1v.3M8 11.6v.1" /></svg>
          What do these stats mean?
        </NuxtLink>
      </div>
      <p class="ds-note">{{ lensNote }}</p>

      <div v-if="leaders.length" class="leaders">
        <NuxtLink v-for="L in leaders" :key="L.k" :to="`${GUIDE}#${L.a}`" class="lead" :title="`What is ${L.title}?`">
          <span class="lead-t">{{ L.title }}<svg class="info" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.6" /><path d="M8 7.2v4M8 4.6v.2" /></svg></span>
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
              <th class="plain" @pointerenter="hoverTip($event, 'W–L', WL_TIP)" @pointerleave="hideTip">
                <span class="nw">W–L<button type="button" class="ti" aria-label="What is W–L?" @click.stop="tapTip($event, 'W–L', WL_TIP)"
                  @focus="showTip($event, 'W–L', WL_TIP, 0)" @blur="hideTip"><svg class="info" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.6" /><path d="M8 7.2v4M8 4.6v.2" /></svg></button></span>
              </th>
              <th v-for="c in COLS" :key="c.k" :class="{ sorted: sortKey === c.k, colgrp: c.g }"
                  @click="sortBy(c)" @pointerenter="hoverTip($event, c.n, c.t)" @pointerleave="hideTip">
                {{ c.head }} <span class="nw">{{ c.tail }}<span v-if="sortKey === c.k">{{ sortDir < 0 ? ' ▾' : ' ▴' }}</span><button
                  type="button" class="ti" :aria-label="`What is ${c.n}?`" @click.stop="tapTip($event, c.n, c.t)"
                  @focus="showTip($event, c.n, c.t, 0)" @blur="hideTip"><svg class="info" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.6" /><path d="M8 7.2v4M8 4.6v.2" /></svg></button></span>
              </th>
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
        {{ opp !== 'all' ? 'No games in this view yet. Try All, or the other set of games.'
          : lens === 'ladder' ? 'No ladder maps scored yet. They show up a few minutes after a match is recorded.' : 'No duels with demos in this window yet.' }}
      </div>

      <p v-if="rows.length" class="ds-foot">
        Read from the demo of every game, not the scoreboard. The bar under a number shows where it sits between the lowest and highest
        player in that column. A dash, or a dimmed row, means too few games to say (under {{ floor }}).
      </p>
    </template>

    <Teleport to="body">
      <div v-if="tip" class="ds-tip" :class="{ below: tip.below }" role="tooltip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
        <b>{{ tip.title }}</b>{{ tip.text }}
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 18px 0; }
.retry { background: none; border: 0; color: var(--accent); font: inherit; cursor: pointer; padding: 8px 4px; }
.ds-bar { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 10px 16px; margin-bottom: 8px; }
.ctl { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.ctl-l { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); font-weight: 700; }
.seg { display: inline-flex; gap: 2px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 2px; }
.seg button { background: none; border: 0; color: var(--fg-3); font-family: inherit; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap; }
.seg button:hover { color: var(--fg); }
.seg button.on { background: var(--panel-3); color: var(--fg); }
.seg .short { display: none; }
/* the way into the glossary: a real button, not a text link */
.help-btn { margin-left: auto; display: inline-flex; align-items: center; gap: 7px; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--accent);
            background: rgba(255, 122, 26, .13); color: var(--accent); font-size: 12.5px; font-weight: 800; text-decoration: none; white-space: nowrap; transition: background .12s, color .12s; }
.help-btn:hover, .help-btn:focus-visible { background: var(--accent); color: var(--bg); }
.help-i { width: 15px; height: 15px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; }
.ds-note { margin: 0 2px 14px; font-size: 12px; line-height: 1.45; color: var(--fg-3); }
.info { width: 11px; height: 11px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; }

.leaders { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.lead { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 8px; row-gap: 2px; align-items: baseline; background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; text-decoration: none; color: var(--fg); }
.lead:hover { border-color: var(--accent); }
.lead-t { grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--accent); font-weight: 800; }
.lead-t .info { opacity: .7; }
.lead-n { font-size: 15px; font-weight: 800; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lead-v { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-size: 15px; font-weight: 700; }
.lead-s { grid-column: 1 / -1; font-size: 11.5px; color: var(--fg-3); line-height: 1.35; }

.scroll { overflow-x: auto; }
table.adv { --px: 9px; border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13px; }
table.adv th, table.adv td { padding: 7px var(--px); text-align: right; white-space: nowrap; }
/* a long header ("Top 10% Speed") may break onto two lines before the table has to scroll */
table.adv th { font-size: 11px; line-height: 1.25; color: var(--fg-3); font-weight: 700; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; white-space: normal; vertical-align: bottom; }
table.adv th.plain { cursor: default; }
table.adv th:hover, table.adv th.sorted { color: var(--accent); }
table.adv tr.grp th { border-bottom: 0; padding-bottom: 2px; text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; cursor: default; color: var(--fg-3); }
table.adv th.team, table.adv td.team { text-align: left; position: sticky; left: 0; z-index: 1; background: var(--panel); }
.nw { white-space: nowrap; }
.ti { background: none; border: 0; padding: 0 0 0 4px; margin: 0; color: inherit; cursor: help; vertical-align: -1px; line-height: 0; opacity: .6; }
th:hover .ti, .ti:focus-visible { opacity: 1; }
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

.ds-tip { position: fixed; z-index: 1000; transform: translate(-50%, -100%); width: max-content; max-width: min(260px, calc(100vw - 16px)); box-sizing: border-box;
          padding: 9px 11px; border-radius: 8px; background: var(--panel-3); border: 1px solid var(--border-2); color: var(--fg-2);
          font-size: 12px; line-height: 1.45; text-align: left; box-shadow: 0 8px 24px rgba(0, 0, 0, .55); pointer-events: none; }
.ds-tip.below { transform: translate(-50%, 0); }
.ds-tip b { display: block; margin-bottom: 2px; color: var(--fg); font-size: 12.5px; }

/* eleven columns: on a laptop-width panel, tighter cells keep the whole table in view without
   sideways scroll (below that it scrolls in its frame anyway, so phones keep roomier cells) */
.ds { container-type: inline-size; }
@container (min-width: 700px) and (max-width: 1010px) { table.adv { --px: 5px; } }
@media (max-width: 880px) {
  .leaders { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .seg button { padding: 9px 12px; min-height: 36px; }
  .help-btn { min-height: 38px; box-sizing: border-box; }
  /* taller tap area for the name without making the row taller */
  .pl-name { max-width: 104px; padding: 8px 0; margin: -8px 0; }
  table.adv th { padding-top: 10px; padding-bottom: 10px; }
  .ti { padding: 13px 3px 13px 5px; margin: -13px -3px -13px 0; }   /* 36px+ tap area around the (i) */
}
@media (max-width: 640px) {
  .ctl, .seg { width: 100%; }
  .seg { display: flex; box-sizing: border-box; }
  .seg button { flex: 1 1 auto; padding: 9px 6px; }
  .seg .long { display: none; } .seg .short { display: inline; }
  .help-btn { margin-left: 0; width: 100%; justify-content: center; }
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

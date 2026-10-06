<script setup>
// /non-entity: Cronus's unlisted register of the players passed on the KOTH 1v1 ladder. Not in
// any menu and marked noindex; only the link gets you here. Each entry pulls the last 90 days of
// duels between the two from /api/duel/vs: record by map, the end-of-match numbers and the
// demo-derived advanced numbers (same definitions as the ladder's Advanced Metrics tab).
// To add a name, append to ENTRIES; the number is its position in the list.
const ME = { id: 'cronus', name: 'Cronus' }
const ENTRIES = [
  { id: 'kingstud', name: 'Kingstud' },
  { id: 'pred', name: 'Pred' },
]
// House rule: a name goes on only once Cronus is above 50% against them over the window.
// (war checked 2026-10-06: 27-51, so not yet.)
const DAYS = 90

const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
useHead({
  title: 'Non-Entity',
  meta: [{ name: 'robots', content: 'noindex, nofollow' }],
  link: [{ rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Rubik+Mono+One&family=Special+Elite&display=swap' }],
})

const data = ref({})       // id -> /api/duel/vs payload
const rungs = ref({})      // canonical id -> ladder rung
const failed = ref({})
onMounted(async () => {
  try {
    const l = await $fetch(`${base}/api/ladder/2`)
    for (const t of l.teams || []) for (const m of t.members || []) rungs.value[m.id] = t.rung
  } catch { /* the rung line is decoration */ }
  await Promise.all(ENTRIES.map(async (e) => {
    try { data.value[e.id] = await $fetch(`${base}/api/duel/vs`, { query: { a: ME.id, b: e.id, days: DAYS } }) }
    catch (err) { failed.value[e.id] = true; console.error('[non-entity]', e.id, err) }
  }))
})

const num = i => String(i + 1).padStart(3, '0')
function pct(w, n) { return n ? Math.round(100 * w / n) : 0 }
function fmtDate(s) { return s ? new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '' }
function fmtShort(s) { return s ? new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '' }
const eff = s => (s && s.frags != null && (s.frags + s.deaths) > 0) ? Math.round(100 * s.frags / (s.frags + s.deaths)) : null

// standard (end-of-match) rows: k = field in `standard`, low = lower is better
const STANDARD = [
  { k: 'frags', l: 'Frags / game', d: 1 }, { k: 'deaths', l: 'Deaths / game', d: 1, low: true }, { k: 'eff', l: 'Efficiency', unit: '%' },
  { k: 'dmg_given', l: 'Damage given', d: 0 }, { k: 'dmg_taken', l: 'Damage taken', d: 0, low: true },
  { k: 'ra', l: 'Red armors', d: 1 }, { k: 'ya', l: 'Yellow armors', d: 1 }, { k: 'mh', l: 'Megas', d: 1 },
  { k: 'lg', l: 'LG accuracy', unit: '%', d: 0 }, { k: 'rl', l: 'RL direct hits', unit: '%', d: 0 },   // no SG: a spawn weapon in a duel
]
// advanced (demo) rows: k = field in `advanced`
const ADVANCED = [
  { k: 'even_win_pct', l: 'Even fights won', unit: '%' }, { k: 'stacked_ratio', l: 'Stacked damage ratio', d: 2 },
  { k: 'dmg_pm', l: 'Damage per minute', d: 0 }, { k: 'behind_pct', l: 'Fights started from behind', unit: '%', low: true },
  { k: 'ra_share', l: 'RA %', unit: '%' }, { k: 'ra_on_time_pct', l: 'RA timing', unit: '%' },
  { k: 'mh_on_time_pct', l: 'Mega timing', unit: '%' }, { k: 'mh_held_pct', l: 'Mega control', unit: '%' }, { k: 'mh_share', l: 'Mega %', unit: '%' },
  { k: 'top_speed', l: 'Top 10% speed', d: 0 }, { k: 'avg_speed', l: 'Avg speed', d: 0 },
]
function val(src, k) {
  if (!src) return null
  if (k === 'eff') return eff(src)
  return src[k]
}
function fmt(v, c) {
  if (v == null) return '—'
  const d = c.d ?? 0
  const s = d ? Number(v).toFixed(d) : Math.round(v).toLocaleString()
  return c.unit ? s + c.unit : s
}
// one comparison row: who leads, and bar widths scaled to the larger of the two
function row(c, va, vb) {
  const both = va != null && vb != null && va !== vb
  const aLead = both && (c.low ? va < vb : va > vb)
  const max = Math.max(Math.abs(va || 0), Math.abs(vb || 0)) || 1
  return { label: c.l, a: fmt(va, c), b: fmt(vb, c), aw: Math.round(100 * Math.abs(va || 0) / max), bw: Math.round(100 * Math.abs(vb || 0) / max), aLead, bLead: both && !aLead }
}
function standardRows(d) { return STANDARD.map(c => row(c, val(d.standard?.[ME.id], c.k), val(d.standard?.[d.b.canonical_id], c.k))) }
function advancedRows(d) { return ADVANCED.map(c => row(c, d.advanced?.[ME.id]?.[c.k], d.advanced?.[d.b.canonical_id]?.[c.k])) }
function mapRows(d) {
  const top = Math.max(...(d.maps || []).map(m => m.games), 1)
  return (d.maps || []).map(m => ({ ...m, w: Math.round(100 * m.games / top), aw: Math.round(100 * m.wins_a / m.games), bw: Math.round(100 * m.wins_b / m.games) }))
}
function verdict(d) {
  const p = pct(d.wins_a, d.games)
  if (!d.games) return 'No duels in the window. The entry stands.'
  if (p >= 70) return 'A formality.'
  if (p >= 60) return 'Comfortable.'
  if (p > 50) return 'Closer than it should have been.'
  if (p === 50) return 'Even, which is not the point of this page.'
  return 'Under review.'
}
</script>

<template>
  <div class="ne">
    <header class="hero">
      <div class="stamp"><span>Unlisted</span><small>Office of Cronus</small></div>
      <h1>Non-Entity</h1>
      <p class="lede">A register of those passed on the road to greatness. Entries are permanent. Appeals are not heard.</p>
    </header>

    <article v-for="(e, i) in ENTRIES" :key="e.id" class="entry">
      <div class="entry-head">
        <div class="no">No. {{ num(i) }}</div>
        <div class="who">
          <h2>{{ e.name }}</h2>
          <div class="rung" v-if="rungs[e.id] != null || rungs[ME.id] != null">
            <span v-if="rungs[e.id] != null">rung {{ rungs[e.id] }}</span>
            <span v-if="rungs[ME.id] != null"> · {{ ME.name }} on rung {{ rungs[ME.id] }}</span>
          </div>
        </div>
        <div class="passed">Passed</div>
      </div>

      <div v-if="failed[e.id]" class="state">Could not load this entry.</div>
      <div v-else-if="!data[e.id]" class="state">Loading…</div>
      <template v-else-if="data[e.id]">
        <div class="record">
          <div class="score">
            <span class="me">{{ data[e.id].wins_a }}</span><span class="dash">–</span><span class="them">{{ data[e.id].wins_b }}</span>
          </div>
          <div class="record-text">
            <div class="line1">{{ ME.name }} {{ data[e.id].wins_a }}, {{ e.name }} {{ data[e.id].wins_b }} over {{ data[e.id].games }} duel{{ data[e.id].games === 1 ? '' : 's' }} · {{ pct(data[e.id].wins_a, data[e.id].games) }}%</div>
            <div class="line2" v-if="data[e.id].games">{{ fmtDate(data[e.id].first) }} to {{ fmtDate(data[e.id].last) }} · {{ verdict(data[e.id]) }}</div>
          </div>
        </div>

        <section v-if="data[e.id].maps.length" class="block">
          <h3>By map</h3>
          <div class="maps">
            <div v-for="m in mapRows(data[e.id])" :key="m.map" class="map">
              <span class="mname">{{ m.map }}</span>
              <span class="mbar" :style="{ width: m.w + '%' }"><i class="a" :style="{ width: m.aw + '%' }" /><i class="b" :style="{ width: m.bw + '%' }" /></span>
              <span class="mrec"><b class="me">{{ m.wins_a }}</b>–<b class="them">{{ m.wins_b }}</b></span>
              <span class="mavg">{{ m.avg_a }} to {{ m.avg_b }} frags a game</span>
            </div>
          </div>
        </section>

        <div class="two">
          <section class="block">
            <h3>Standard numbers <small>per game</small></h3>
            <div class="cols"><span class="me">{{ ME.name }}</span><span /><span class="them">{{ e.name }}</span></div>
            <div v-for="r in standardRows(data[e.id])" :key="r.label" class="cmp">
              <span class="v l" :class="{ lead: r.aLead }"><b>{{ r.a }}</b><i class="bar a" :style="{ width: r.aw + '%' }" /></span>
              <span class="lbl">{{ r.label }}</span>
              <span class="v r" :class="{ lead: r.bLead }"><i class="bar b" :style="{ width: r.bw + '%' }" /><b>{{ r.b }}</b></span>
            </div>
          </section>
          <section class="block">
            <h3>Advanced numbers <small>from the demos</small></h3>
            <div class="cols"><span class="me">{{ ME.name }}</span><span /><span class="them">{{ e.name }}</span></div>
            <div v-for="r in advancedRows(data[e.id])" :key="r.label" class="cmp">
              <span class="v l" :class="{ lead: r.aLead }"><b>{{ r.a }}</b><i class="bar a" :style="{ width: r.aw + '%' }" /></span>
              <span class="lbl">{{ r.label }}</span>
              <span class="v r" :class="{ lead: r.bLead }"><i class="bar b" :style="{ width: r.bw + '%' }" /><b>{{ r.b }}</b></span>
            </div>
            <p class="note">Fights started from behind: lower is better. Definitions: <NuxtLink to="/ladder/advanced-guide">the glossary</NuxtLink>.</p>
          </section>
        </div>

        <section v-if="data[e.id].recent.length" class="block">
          <h3>Latest meetings</h3>
          <div class="recent">
            <a v-for="g in data[e.id].recent" :key="g.game_id" class="g" :class="g.fa > g.fb ? 'w' : g.fa < g.fb ? 'l' : 'd'"
               :href="`https://hub.quakeworld.nu/games/?gameId=${g.game_id}`" target="_blank" rel="noopener">
              <span class="gd">{{ fmtShort(g.date) }}</span><span class="gm">{{ g.map }}</span><span class="gs">{{ g.fa }}–{{ g.fb }}</span>
            </a>
          </div>
        </section>
      </template>
    </article>

    <footer class="foot">Compiled from public match records. Nobody was consulted.</footer>
  </div>
</template>

<style scoped>
.ne { max-width: 1000px; margin: 0 auto; padding: 24px 16px 80px; color: var(--fg); }
.hero { position: relative; padding: 36px 20px 30px; margin-bottom: 26px; border: 2px solid var(--accent); border-radius: 14px;
        background: radial-gradient(ellipse at 20% 0%, rgba(255,122,26,.18), transparent 55%), var(--panel); overflow: hidden; }
.hero h1 { margin: 0; font-family: 'Rubik Mono One', 'Big Shoulders Display', Impact, sans-serif; font-size: clamp(38px, 9vw, 84px); line-height: .95; letter-spacing: .02em; color: var(--accent); text-transform: uppercase; }
.lede { margin: 14px 0 0; font-family: 'Special Elite', 'Courier New', monospace; font-size: 17px; line-height: 1.45; color: var(--fg); max-width: 60ch; }
.stamp, .passed { font-family: 'Special Elite', 'Courier New', monospace; text-transform: uppercase; letter-spacing: .12em; font-weight: 700; border: 2px solid var(--loss); color: var(--loss); border-radius: 6px; padding: 4px 10px; transform: rotate(-6deg); opacity: .9; }
/* two-line stamp: UNLISTED over the office that keeps the register */
.stamp { position: absolute; top: 10px; right: 14px; display: grid; gap: 1px; padding: 5px 10px; font-size: 11px; line-height: 1.15; text-align: center; }
.stamp small { font-size: 8.5px; letter-spacing: .1em; }

.entry { margin-bottom: 34px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 20px 20px 10px; }
.entry-head { display: flex; align-items: center; gap: 16px; padding-bottom: 14px; border-bottom: 1px dashed var(--border-2); }
.no { font-family: 'Special Elite', 'Courier New', monospace; font-size: 14px; color: var(--fg-3); letter-spacing: .1em; white-space: nowrap; }
.who { flex: 1 1 auto; min-width: 0; }
.who h2 { margin: 0; font-family: 'Rubik Mono One', 'Big Shoulders Display', Impact, sans-serif; font-size: clamp(24px, 5vw, 40px); line-height: 1; text-transform: uppercase; overflow-wrap: anywhere; }
.rung { font-size: 12px; color: var(--fg-3); margin-top: 6px; }
.passed { font-size: 15px; flex: none; }
.state { padding: 24px 0; color: var(--fg-3); }

.record { display: flex; align-items: center; gap: 22px; padding: 18px 0 8px; flex-wrap: wrap; }
.score { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: clamp(44px, 9vw, 72px); line-height: 1; font-variant-numeric: tabular-nums; }
.score .dash { color: var(--fg-3); margin: 0 6px; }
.me { color: var(--accent); } .them { color: var(--fg-3); }
.record-text { min-width: 0; }
.line1 { font-size: 15px; font-weight: 700; }
.line2 { font-size: 13px; color: var(--fg-3); margin-top: 4px; font-family: 'Special Elite', 'Courier New', monospace; }

.block { padding: 14px 0 12px; border-top: 1px solid var(--border); }
.block h3 { margin: 0 0 10px; font-size: 12px; text-transform: uppercase; letter-spacing: .07em; color: var(--fg-3); font-weight: 800; }
.block h3 small { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--fg-3); margin-left: 6px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 0 28px; }

.maps { display: grid; gap: 7px; }
.map { display: grid; grid-template-columns: 76px minmax(0, 1fr) 54px auto; align-items: center; gap: 10px; font-size: 13px; }
.mname { font-family: 'JetBrains Mono', monospace; color: var(--fg-2); }
.mbar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--panel-3); min-width: 24px; }
.mbar .a { display: block; height: 100%; background: var(--accent); } .mbar .b { display: block; height: 100%; background: var(--fg-3); opacity: .6; }
.mrec { font-family: 'JetBrains Mono', monospace; font-weight: 700; text-align: right; } .mrec .them { font-weight: 700; }
.mavg { font-size: 11.5px; color: var(--fg-3); white-space: nowrap; }

.cols { display: grid; grid-template-columns: 1fr 150px 1fr; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; padding-bottom: 6px; border-bottom: 1px solid var(--border); margin-bottom: 2px; }
.cols :first-child { text-align: right; } .cols :last-child { text-align: left; }
.cmp { display: grid; grid-template-columns: 1fr 150px 1fr; align-items: center; padding: 6px 0; border-top: 1px solid rgba(42,32,24,.5); }
.lbl { text-align: center; font-size: 10.5px; text-transform: uppercase; letter-spacing: .03em; color: var(--fg-3); line-height: 1.2; }
.v { display: flex; align-items: center; gap: 7px; font-family: 'JetBrains Mono', monospace; font-size: 13.5px; color: var(--fg-2); min-width: 0; }
.v.l { justify-content: flex-end; } .v.r { justify-content: flex-start; }
.v b { font-weight: 700; } .v.lead b { color: var(--win); }
.bar { height: 6px; border-radius: 3px; flex: 0 1 auto; max-width: 70px; min-width: 2px; }
.bar.a { background: var(--accent); } .bar.b { background: var(--fg-3); opacity: .6; }
.note { margin: 10px 0 0; font-size: 11.5px; color: var(--fg-3); }
.note a { color: var(--accent); text-decoration: none; display: inline-block; padding: 10px 0; margin: -10px 0; }

.recent { display: flex; flex-wrap: wrap; gap: 8px; }
.g { display: grid; grid-template-rows: auto auto auto; gap: 2px; min-width: 78px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel-2); text-decoration: none; color: var(--fg); text-align: center; }
.g.w { border-color: rgba(34,197,94,.45); } .g.l { border-color: rgba(239,68,68,.45); }
.gd { font-size: 10px; color: var(--fg-3); text-transform: uppercase; letter-spacing: .04em; }
.gm { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--fg-2); }
.gs { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 14px; }
.g.w .gs { color: var(--win); } .g.l .gs { color: var(--loss); }
.foot { margin-top: 20px; text-align: center; font-family: 'Special Elite', 'Courier New', monospace; font-size: 13px; color: var(--fg-3); }

/* below ~900px the title's last letters can sit under the stamp, so the hero opens lower */
@media (max-width: 900px) { .hero { padding-top: 66px; } }
@media (max-width: 760px) {
  .two { grid-template-columns: 1fr; }
  .cols, .cmp { grid-template-columns: 1fr 104px 1fr; }
  .lbl { font-size: 10px; }
  .bar { max-width: 34px; }
  .map { grid-template-columns: 64px minmax(0, 1fr) 46px; }
  .mavg { grid-column: 2 / -1; margin-top: -2px; }
  .g { min-width: 0; flex: 1 1 calc(33.33% - 8px); padding: 10px 6px; }
}
@media (max-width: 480px) {
  /* number and stamp on one line, the name on its own line underneath, so a long name never breaks mid-word */
  .entry-head { display: grid; grid-template-columns: 1fr auto; align-items: center; row-gap: 8px; }
  .no { grid-row: 1; grid-column: 1; }
  .passed { grid-row: 1; grid-column: 2; justify-self: end; }
  .who { grid-row: 2; grid-column: 1 / -1; }
  .who h2 { font-size: clamp(24px, 7.4vw, 34px); }
  .passed { font-size: 13px; }
}
@media (max-width: 420px) {
  .ne { padding: 16px 16px 60px; }
  .hero { padding: 66px 16px 22px; }
  .entry { padding: 16px 14px 8px; }
  .entry-head { gap: 10px; }
  .record { gap: 14px; }
  .v { font-size: 12.5px; gap: 5px; }
  .g { flex-basis: calc(50% - 8px); }
}
</style>

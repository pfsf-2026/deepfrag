<script setup>
// Profile deep-dive tabs, ported from the legacy profile.html SPA into Nuxt
// one tab at a time (so there's ONE profile UI / one tab bar incl Coach).
// Data: /api/players/{id}/full?window=N (same as the Overview page). Tabs not yet
// ported redirect to the legacy SPA so deep links keep working during migration.
const route = useRoute()
const router = useRouter()
const df = useDeepFrag()

const id = computed(() => String(route.params.id))
const tab = computed(() => String(route.params.tab || ''))
const windowKey = ref('90')

const PORTED = new Set(['recent', 'opponents', '1on1', '4on4', '2on2', 'trends', 'compare'])  // grows as tabs are migrated

const profile = ref(null)
const pending = ref(true)

async function load() {
  // Unported tab → fall back to the legacy SPA (preserves the deep link).
  if (!PORTED.has(tab.value)) {
    if (import.meta.client) window.location.replace(`/profile.html?id=${encodeURIComponent(id.value)}#${tab.value}`)
    return
  }
  pending.value = true
  try {
    const url = df.useApi ? `${df.profileUrl(id.value)}/full?window=${windowKey.value}` : df.profileUrl(id.value)
    const r = await fetch(url)
    profile.value = r.ok ? await r.json() : null
    // Mode tabs need division averages for the weapon-donut reference arcs.
    if (MODES.includes(tab.value) && !divisions.value[tab.value + '_loaded']) {
      try {
        const dr = await fetch(`/api/divisions/avg-stats?mode=${tab.value}&since_days=365`)
        if (dr.ok) divisions.value = { ...((await dr.json()).divisions || {}), [tab.value + '_loaded']: true }
      } catch { /* donuts just omit the reference arc */ }
    }
  } catch { profile.value = null } finally { pending.value = false }
}
onMounted(load)
watch([id, tab, windowKey], load)

const recent = computed(() => profile.value?.recent_matches || [])
const d = computed(() => profile.value?.windows?.[windowKey.value] || {})
const rivals = computed(() => (d.value.head_to_head_1on1 || []).filter(r => (r.matches || 0) >= 3))

function fmtNum(v) { return v == null ? '—' : Number(v).toLocaleString() }
function fmtDelta(v) { return v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(1) }
const winLoss = v => v > 0 ? 'win' : v < 0 ? 'loss' : ''
const rivalCols = [
  { key: 'opponent', label: 'Opponent' },
  { key: 'matches', label: 'N', num: true, fmt: fmtNum },
  { key: 'wins', label: 'W', num: true },
  { key: 'losses', label: 'L', num: true },
  { key: 'win_rate', label: 'Win%', num: true, bar: true, fmt: v => fmtPct(v) },
  { key: 'avg_frag_diff', label: 'Avg ±', num: true, fmt: fmtDelta, cls: winLoss },
  { key: 'last_played', label: 'Last', fmt: v => fmtDate(v) },
]

// ── mode tabs (1on1/4on4/2on2): stats + weapon donuts + item pickups + by_map ──
const MODES = ['1on1', '4on4', '2on2']
const isMode = computed(() => MODES.includes(tab.value))
const modeStats = computed(() => d.value.by_mode?.[tab.value] || null)
const priorStats = computed(() => d.value.prior?.by_mode?.[tab.value] || null)
const byMap = computed(() => d.value['by_map_' + tab.value] || [])
const divisions = ref({})
const divSlug = computed(() => profile.value?.ratings?.[tab.value]?.tier?.slug || null)
function divAvg(k) { return (divisions.value[divSlug.value] || {})[k] ?? null }
const WEAPONS = [
  { name: 'LG', key: 'lg_accuracy', max: 0.35 }, { name: 'RL', key: 'rl_accuracy', max: 0.50 },
  { name: 'SSG', key: 'ssg_accuracy', max: 0.40 }, { name: 'SG', key: 'sg_accuracy', max: 0.30 },
  { name: 'GL', key: 'gl_accuracy', max: 0.30 },
]
function dec(v, n = 1) { return v == null ? '—' : Number(v).toFixed(n) }
function delta(cur, prv, fmtFn, higherBetter = true) {
  if (cur == null || prv == null || windowKey.value === 'all' || !priorStats.value) return null
  const diff = cur - prv
  if (Math.abs(diff) < 1e-9) return { text: '±0', good: null }
  return { text: (diff > 0 ? '+' : '') + fmtFn(diff) + ' vs prior', good: higherBetter ? diff > 0 : diff < 0 }
}
const ddr = computed(() => { const s = modeStats.value; return s?.avg_dmg_given && s?.avg_dmg_taken ? s.avg_dmg_given / s.avg_dmg_taken : null })
const priorDdr = computed(() => { const p = priorStats.value; return p?.avg_dmg_given && p?.avg_dmg_taken ? p.avg_dmg_given / p.avg_dmg_taken : null })
const modeCards = computed(() => {
  const s = modeStats.value, p = priorStats.value
  if (!s) return []
  return [
    { label: `${tab.value} matches`, value: fmtNum(s.matches), delta: delta(s.matches, p?.matches, v => fmtNum(Math.round(v))) },
    { label: 'Win rate', value: fmtPct(s.win_rate), sub: `${s.wins}W · ${s.losses}L`, delta: delta(s.win_rate, p?.win_rate, v => (v * 100).toFixed(1) + 'pp') },
    { label: 'DDR', value: ddr.value != null ? ddr.value.toFixed(2) : '—', sub: 'dmg given / taken', delta: delta(ddr.value, priorDdr.value, v => v.toFixed(2)) },
    { label: 'Avg ±', value: fmtDelta(s.avg_frag_diff), cls: winLoss(s.avg_frag_diff), delta: delta(s.avg_frag_diff, p?.avg_frag_diff, v => v.toFixed(1)) },
    { label: 'Dmg/match', value: fmtNum(Math.round(s.avg_dmg_given || 0)), delta: delta(s.avg_dmg_given, p?.avg_dmg_given, v => Math.round(v).toLocaleString()) },
  ]
})
const itemCards = computed(() => {
  const s = modeStats.value
  if (!s) return []
  return [
    { label: 'Red armor', value: dec(s.avg_ra, 1) }, { label: 'Yellow armor', value: dec(s.avg_ya, 1) },
    { label: 'Green armor', value: dec(s.avg_ga, 1) }, { label: 'Megahealth', value: dec(s.avg_mh, 1) }, { label: 'Quads', value: dec(s.avg_quads, 2) },
  ]
})
const mapCols = [
  { key: 'bucket', label: 'Map' },
  { key: 'matches', label: 'N', num: true, fmt: fmtNum },
  { key: 'wins', label: 'W', num: true }, { key: 'losses', label: 'L', num: true },
  { key: 'win_rate', label: 'Win%', num: true, bar: true, fmt: v => fmtPct(v) },
  { key: 'avg_frags', label: 'Frags', num: true, fmt: v => dec(v, 1) },
  { key: 'avg_frag_diff', label: '±', num: true, fmt: fmtDelta, cls: winLoss },
  { key: 'lg_accuracy', label: 'LG%', num: true, fmt: v => fmtPct(v) },
  { key: 'rl_accuracy', label: 'RL%', num: true, fmt: v => fmtPct(v) },
]

// ── Trends tab: per-metric weekly trend cards (sparklines) ──
const trendsMode = ref('1on1')
const trendSeries = computed(() => d.value.trend_weekly_by_mode?.[trendsMode.value] || [])
const TREND_METRICS = [
  { label: 'Win rate', key: 'win_rate', fmt: v => fmtPct(v), pp: true, hb: true },
  { label: 'Avg frags', key: 'avg_frags', fmt: v => dec(v, 1), hb: true },
  { label: 'Avg ±', key: 'avg_frag_diff', fmt: v => fmtDelta(v), hb: true },
  { label: 'LG accuracy', key: 'lg_accuracy', fmt: v => fmtPct(v), pp: true, hb: true },
  { label: 'RL accuracy', key: 'rl_accuracy', fmt: v => fmtPct(v), pp: true, hb: true },
  { label: 'Dmg given', key: 'avg_dmg_given', fmt: v => fmtNum(Math.round(v)), hb: true },
  { label: 'Dmg taken', key: 'avg_dmg_taken', fmt: v => fmtNum(Math.round(v)), hb: false },
  { label: 'Ping', key: 'avg_ping', fmt: v => v == null ? '—' : Math.round(v) + 'ms', hb: false },
]
const trendCards = computed(() => {
  const s = trendSeries.value
  return TREND_METRICS.map(m => {
    const series = s.map(b => b[m.key] == null ? null : b[m.key])
    const vals = series.filter(v => v != null)
    const cur = vals.length ? vals[vals.length - 1] : null
    const first = vals.length ? vals[0] : null
    let deltaTxt = null, good = null
    if (cur != null && first != null && vals.length > 1 && Math.abs(cur - first) > 1e-9) {
      const diff = cur - first
      good = m.hb ? diff > 0 : diff < 0
      deltaTxt = (diff > 0 ? '+' : '') + (m.pp ? (diff * 100).toFixed(1) + 'pp' : (Math.abs(diff) >= 100 ? Math.round(diff) : diff.toFixed(1)))
    }
    return { label: m.label, value: m.fmt(cur), series, deltaTxt, good, color: good === false ? '#ff5d6c' : '#34e6b0' }
  })
})

// ── Compare tab: current window vs prior / same-period-last-year (per mode) ──
const cmpMode = ref('1on1')
const cmpPeriod = ref('prior')   // 'prior' | 'year_ago'
const cmpCur = computed(() => d.value.by_mode?.[cmpMode.value] || {})
const cmpPrev = computed(() => d.value[cmpPeriod.value]?.by_mode?.[cmpMode.value] || {})
const DEC1 = v => dec(v, 1), DEC2 = v => dec(v, 2), NUM = v => v == null ? '—' : fmtNum(Math.round(v))
function cmpDelta(cv, pv, higher, pp) {
  if (cv == null || pv == null) return { text: '—', good: null }
  const diff = cv - pv
  if (Math.abs(diff) < 1e-9) return { text: '±0', good: null }
  const t = pp ? (diff > 0 ? '+' : '') + (diff * 100).toFixed(1) + 'pp'
    : (diff > 0 ? '+' : '') + (Math.abs(diff) >= 100 ? Math.round(diff) : diff.toFixed(1))
  return { text: t, good: higher ? diff > 0 : diff < 0 }
}
const cmpSections = computed(() => {
  const team = cmpMode.value !== '1on1'
  return [
    { h: 'Volume', rows: [
      { l: 'Matches', k: 'matches', f: fmtNum, higher: true }, { l: 'Wins', k: 'wins', f: fmtNum, higher: true },
      { l: 'Losses', k: 'losses', f: fmtNum, higher: false }, { l: 'Win rate', k: 'win_rate', f: v => fmtPct(v), higher: true, pp: true } ] },
    { h: 'Performance', rows: [
      { l: 'Avg frags', k: 'avg_frags', f: DEC1, higher: true }, { l: 'Avg deaths', k: 'avg_deaths', f: DEC1, higher: false },
      { l: 'Avg ±', k: 'avg_frag_diff', f: fmtDelta, higher: true }, { l: 'Spawn frags', k: 'avg_spawnfrags', f: DEC2, higher: true },
      ...(team ? [{ l: 'Teamkills', k: 'avg_teamkills', f: DEC2, higher: false }] : []) ] },
    { h: 'Damage', rows: [
      { l: 'Dmg given', k: 'avg_dmg_given', f: NUM, higher: true }, { l: 'Dmg taken', k: 'avg_dmg_taken', f: NUM, higher: false },
      { l: 'Dmg to die', k: 'avg_dmg_to_die', f: NUM, higher: true }, { l: 'Self damage', k: 'avg_dmg_self', f: NUM, higher: false },
      ...(team ? [{ l: 'EWEP', k: 'avg_dmg_enemy_weapons', f: NUM, higher: true }, { l: 'Team damage', k: 'avg_dmg_team', f: NUM, higher: false }, { l: 'Team wpn dmg', k: 'avg_dmg_team_weapons', f: NUM, higher: false }] : []) ] },
    { h: 'Weapon accuracy', rows: [
      { l: 'LG %', k: 'lg_accuracy', f: v => fmtPct(v), higher: true, pp: true }, { l: 'RL %', k: 'rl_accuracy', f: v => fmtPct(v), higher: true, pp: true },
      { l: 'SG %', k: 'sg_accuracy', f: v => fmtPct(v), higher: true, pp: true }, { l: 'SSG %', k: 'ssg_accuracy', f: v => fmtPct(v), higher: true, pp: true } ] },
    { h: 'Weapon damage / match', rows: [
      { l: 'LG damage', k: 'avg_lg_dmg', f: NUM, higher: true }, { l: 'RL damage', k: 'avg_rl_dmg', f: NUM, higher: true },
      { l: 'RL kills', k: 'avg_rl_kills', f: DEC1, higher: true }, { l: 'LG kills', k: 'avg_lg_kills', f: DEC1, higher: true },
      { l: 'RL dropped', k: 'avg_rl_dropped', f: DEC1, higher: false }, { l: 'LG dropped', k: 'avg_lg_dropped', f: DEC1, higher: false },
      ...(team ? [{ l: 'RL transfers', k: 'avg_rl_transfer', f: DEC1, higher: true }, { l: 'LG transfers', k: 'avg_lg_transfer', f: DEC1, higher: true }] : []) ] },
    { h: 'Item control / match', rows: [
      { l: 'Red armor', k: 'avg_ra', f: DEC1, higher: true }, { l: 'Yellow armor', k: 'avg_ya', f: DEC1, higher: true },
      { l: 'Mega health', k: 'avg_mh', f: DEC1, higher: true }, { l: 'RL pickups', k: 'avg_rl_taken', f: DEC1, higher: true },
      { l: 'LG pickups', k: 'avg_lg_taken', f: DEC1, higher: true },
      ...(team ? [{ l: 'Quads', k: 'avg_quads', f: DEC2, higher: true }, { l: 'Pents', k: 'avg_pents', f: DEC2, higher: true }] : []) ] },
  ]
})
const cmpView = computed(() => cmpSections.value.map(sec => ({
  h: sec.h,
  rows: sec.rows.map(r => {
    const cv = cmpCur.value[r.k], pv = cmpPrev.value[r.k]
    return { l: r.l, cur: r.f(cv), prv: r.f(pv), delta: cmpDelta(cv, pv, r.higher, r.pp) }
  }),
})))
const hasCmp = computed(() => Object.keys(cmpPrev.value).length > 0)

function enc(s) { return encodeURIComponent(s) }
// Tabs already in Nuxt link internally; not-yet-ported tabs link straight to the
// legacy SPA (avoids a broken hop / direct-load 404). PORTED grows per migration.
const INTERNAL = new Set(['overview', 'coach', 'maps', ...PORTED])
const TABS = computed(() => {
  const b = `/p/${enc(id.value)}`
  const defs = [
    { key: 'overview', label: 'Overview', to: b },
    { key: 'coach', label: '🎯 Coach', to: { path: b, query: { view: 'coach' } } },
    { key: 'trends', label: 'Trends' }, { key: 'compare', label: 'Compare' },
    { key: '1on1', label: '1on1' }, { key: '4on4', label: '4on4' }, { key: '2on2', label: '2on2' },
    { key: 'dmm', label: 'By DMM' },
    { key: 'maps', label: 'Maps', to: `${b}/maps` },
    { key: 'servers', label: 'Servers' }, { key: 'opponents', label: 'Rivals' },
    { key: 'recent', label: 'Recent', to: `${b}/recent` },
  ]
  return defs.map(t => ({
    ...t,
    internal: INTERNAL.has(t.key),
    to: t.to || `${b}/${t.key}`,
    legacy: `/profile.html?id=${enc(id.value)}#${t.key}`,
  }))
})

function fmtDate(d) { if (!d) return '—'; const x = new Date(d); return isNaN(x) ? d : x.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }
function fmtPct(v) { return v == null ? '—' : Math.round(v * 100) + '%' }

useHead({ title: () => `${id.value} · ${tab.value} · DeepFrag` })
</script>

<template>
  <div class="page">
    <div class="head">
      <NuxtLink :to="`/p/${enc(id)}`" class="back">← {{ id }} overview</NuxtLink>
    </div>

    <div class="profile-tabbar">
      <div class="profile-tabs">
        <template v-for="t in TABS" :key="t.key">
          <NuxtLink v-if="t.internal" :to="t.to" class="ptab" :class="{ active: t.key === tab, 'ptab-coach': t.key === 'coach' }">{{ t.label }}</NuxtLink>
          <a v-else :href="t.legacy" class="ptab">{{ t.label }}</a>
        </template>
      </div>
      <select v-model="windowKey" class="window-select">
        <option value="7">Last 7d</option><option value="30">Last 30d</option>
        <option value="90">Last 90d</option><option value="365">Last year</option><option value="all">All time</option>
      </select>
    </div>

    <div v-if="pending" class="placeholder">Loading…</div>

    <!-- RECENT -->
    <template v-else-if="tab === 'recent'">
      <div class="section-h"><h2>Last 50 matches</h2></div>
      <div class="panel">
        <table class="rtab">
          <thead><tr>
            <th>When</th><th>Mode</th><th>DMM</th><th>Map</th><th>Server</th><th>Result</th>
            <th>Opp</th><th class="num">F</th><th class="num">Opp F</th><th class="num">LG%</th><th class="num">RL%</th>
          </tr></thead>
          <tbody>
            <tr v-for="(m, i) in recent" :key="i">
              <td>{{ fmtDate(m.match_date) }}</td>
              <td><span class="chip" :class="'chip-' + m.match_mode">{{ m.match_mode }}</span></td>
              <td>{{ m.match_dmm ? 'DMM' + m.match_dmm : '—' }}</td>
              <td>{{ m.match_map }}</td>
              <td class="small muted">{{ m.server_hostname || '—' }}</td>
              <td><span v-if="m.outcome" class="result-pill" :class="m.outcome">{{ m.outcome }}</span><span v-else>—</span></td>
              <td>{{ m.opponent_name || '—' }}</td>
              <td class="num">{{ m.player_frags ?? '—' }}</td>
              <td class="num">{{ m.opponent_frags ?? '—' }}</td>
              <td class="num">{{ fmtPct(m.lg_acc) }}</td>
              <td class="num">{{ fmtPct(m.rl_acc) }}</td>
            </tr>
            <tr v-if="!recent.length"><td colspan="11" class="muted" style="text-align:center;padding:20px">No recent matches.</td></tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- RIVALS (1on1 head-to-head) -->
    <template v-else-if="tab === 'opponents'">
      <div class="section-h"><h2>1on1 head-to-head</h2><span class="meta">{{ rivals.length }} opponents (≥3 matches)</span></div>
      <StatTable :rows="rivals" :cols="rivalCols" sort-key="matches" sort-dir="desc" />
    </template>

    <!-- MODE BREAKDOWN (1on1 / 4on4 / 2on2) -->
    <template v-else-if="isMode">
      <template v-if="modeStats">
        <div class="grid5">
          <div v-for="c in modeCards" :key="c.label" class="stat-card">
            <div class="l">{{ c.label }}</div>
            <div class="v" :class="c.cls">{{ c.value }}</div>
            <div v-if="c.sub" class="s">{{ c.sub }}</div>
            <div v-if="c.delta" class="s delta" :class="c.delta.good === true ? 'up' : c.delta.good === false ? 'down' : ''">{{ c.delta.text }}</div>
          </div>
        </div>

        <div class="section-h" style="margin-top:20px"><h2>Weapon proficiency</h2>
          <span v-if="divSlug" class="meta">reference arc = your division average</span></div>
        <div class="panel"><div class="donuts">
          <WeaponDonut v-for="w in WEAPONS" :key="w.name" :name="w.name" :val="modeStats[w.key]" :max="w.max" :div-avg="divAvg(w.key)" />
        </div></div>

        <div class="section-h" style="margin-top:20px"><h2>Item pickups / match</h2></div>
        <div class="grid5">
          <div v-for="c in itemCards" :key="c.label" class="stat-card"><div class="l">{{ c.label }}</div><div class="v">{{ c.value }}</div></div>
        </div>

        <template v-if="byMap.length">
          <div class="section-h" style="margin-top:20px"><h2>{{ tab }} map breakdown</h2><span class="meta">{{ byMap.length }} maps</span></div>
          <StatTable :rows="byMap" :cols="mapCols" sort-key="matches" sort-dir="desc" />
        </template>
      </template>
      <div v-else class="placeholder">No {{ tab }} matches in this window.</div>
    </template>

    <!-- TRENDS (weekly per-metric) -->
    <template v-else-if="tab === 'trends'">
      <div class="section-h"><h2>Weekly trends</h2><span class="meta">{{ trendSeries.length }} weeks</span></div>
      <div class="pill-row">
        <button v-for="m in ['1on1', '4on4', '2on2']" :key="m" class="mpill" :class="{ on: trendsMode === m }" @click="trendsMode = m">{{ m }}</button>
      </div>
      <div v-if="trendSeries.length" class="trendgrid">
        <div v-for="c in trendCards" :key="c.label" class="tcard">
          <div class="tc-top"><span class="tc-l">{{ c.label }}</span>
            <span v-if="c.deltaTxt" class="tc-d" :class="c.good ? 'up' : 'down'">{{ c.deltaTxt }}</span></div>
          <div class="tc-v">{{ c.value }}</div>
          <Sparkline :data="c.series" :color="c.color" :height="40" />
        </div>
      </div>
      <div v-else class="placeholder">No {{ trendsMode }} trend data in this window.</div>
    </template>

    <!-- COMPARE (period over period) -->
    <template v-else-if="tab === 'compare'">
      <div class="pill-row">
        <span class="ptlabel">Mode</span>
        <button v-for="m in ['1on1', '4on4', '2on2']" :key="m" class="mpill" :class="{ on: cmpMode === m }" @click="cmpMode = m">{{ m }}</button>
        <span class="ptlabel" style="margin-left:12px">Compare to</span>
        <button class="mpill" :class="{ on: cmpPeriod === 'prior' }" @click="cmpPeriod = 'prior'">Prior period</button>
        <button class="mpill" :class="{ on: cmpPeriod === 'year_ago' }" @click="cmpPeriod = 'year_ago'">Same period last year</button>
      </div>
      <div v-if="hasCmp" class="cmp-table">
        <div class="cmp-row cmp-headrow"><div /><div class="cmp-val">Current</div><div /><div class="cmp-val">{{ cmpPeriod === 'year_ago' ? 'Last year' : 'Prior' }}</div></div>
        <template v-for="sec in cmpView" :key="sec.h">
          <div class="cmp-section-h">{{ sec.h }}</div>
          <div v-for="r in sec.rows" :key="r.l" class="cmp-row">
            <div class="cmp-label">{{ r.l }}</div>
            <div class="cmp-val now">{{ r.cur }}</div>
            <div class="cmp-diff" :class="r.delta.good === true ? 'up' : r.delta.good === false ? 'down' : ''">{{ r.delta.text }}</div>
            <div class="cmp-val prv">{{ r.prv }}</div>
          </div>
        </template>
      </div>
      <div v-else class="placeholder">No comparison data for this window/mode. Try a different window (7d/30d/90d/1y).</div>
    </template>

    <div v-else class="placeholder">Redirecting…</div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 32px 80px; }
.head .back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; }
.head .back:hover { color: var(--accent); }
.profile-tabbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 14px 0 20px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.profile-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.ptab { padding: 8px 14px; color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; border-bottom: 2px solid transparent; cursor: pointer; }
.ptab:hover { color: var(--fg); }
.ptab.active { color: var(--accent); border-bottom-color: var(--accent); }
.ptab-coach { color: var(--accent); }
.window-select { background: var(--panel); border: 1px solid var(--border); color: var(--fg); padding: 6px 10px; border-radius: 7px; font-size: 12px; }
.section-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12px; }
.section-h h2 { font-size: 16px; font-weight: 800; }
.section-h .meta { color: var(--fg-3); font-size: 12px; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 4px 14px; overflow-x: auto; }
.rtab { width: 100%; border-collapse: collapse; font-size: 13px; }
.rtab th, .rtab td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.rtab th { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.rtab td.num, .rtab th.num { text-align: right; font-variant-numeric: tabular-nums; }
.small { font-size: 12px; } .muted { color: var(--fg-3); }
.chip { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; background: var(--panel-2, #1a2433); }
.result-pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.result-pill.win { background: rgba(52,230,176,0.16); color: #34e6b0; }
.result-pill.loss { background: rgba(255,93,108,0.16); color: #ff5d6c; }
.result-pill.draw { background: rgba(245,158,11,0.16); color: #f59e0b; }
.placeholder { padding: 50px; text-align: center; color: var(--fg-3); }
.grid5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
@media (max-width: 760px) { .grid5 { grid-template-columns: repeat(2, 1fr); } }
.stat-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.stat-card .l { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
.stat-card .v { font-size: 24px; font-weight: 800; margin-top: 4px; font-variant-numeric: tabular-nums; }
.stat-card .v.win { color: var(--win, #34e6b0); } .stat-card .v.loss { color: var(--loss, #ff5d6c); }
.stat-card .s { font-size: 11px; color: var(--fg-3); margin-top: 3px; }
.stat-card .s.delta { font-weight: 700; font-variant-numeric: tabular-nums; }
.stat-card .s.delta.up { color: var(--win, #34e6b0); } .stat-card .s.delta.down { color: var(--loss, #ff5d6c); }
.donuts { display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; padding: 14px 4px; }
@media (max-width: 760px) { .donuts { grid-template-columns: repeat(3, 1fr); } }
.pill-row { display: flex; gap: 4px; margin-bottom: 14px; }
.mpill { background: var(--panel); border: 1px solid var(--border); color: var(--fg-2); border-radius: 7px; padding: 6px 14px; font-size: 12px; font-weight: 600; cursor: pointer; }
.mpill.on { background: var(--accent); color: var(--bg); border-color: var(--accent); }
.trendgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 12px; }
.tcard { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.tc-top { display: flex; justify-content: space-between; align-items: baseline; }
.tc-l { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
.tc-d { font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; }
.tc-d.up { color: var(--win, #34e6b0); } .tc-d.down { color: var(--loss, #ff5d6c); }
.tc-v { font-size: 22px; font-weight: 800; margin: 4px 0 8px; font-variant-numeric: tabular-nums; }
.ptlabel { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }
.cmp-table { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 6px 14px 14px; }
.cmp-section-h { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); font-weight: 700; margin: 14px 0 4px; }
.cmp-row { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr; align-items: center; padding: 6px 4px; border-bottom: 1px solid var(--border); font-size: 13px; }
.cmp-headrow { border-bottom: 1px solid var(--border); color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.cmp-label { color: var(--fg-2); }
.cmp-val { text-align: right; font-variant-numeric: tabular-nums; }
.cmp-val.prv { color: var(--fg-3); }
.cmp-diff { text-align: right; font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }
.cmp-diff.up { color: var(--win, #34e6b0); } .cmp-diff.down { color: var(--loss, #ff5d6c); }
</style>

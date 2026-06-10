<script setup>
const config = useRuntimeConfig()
// Client = '' → same-origin → CF Pages Function → edge cached. SSR = Cloud Run.
const isBrowser = typeof window !== 'undefined'
const apiBase = isBrowser ? '' : (config.public.apiBase || '')

const mode = ref('1on1')
const mapFilter = ref('all')
const regionFilter = ref('all')
const minMatches = ref(100)
const window = ref('all')
const maps = ref([])
const data = ref(null)
const pending = ref(true)

async function loadMaps() {
  if (!apiBase && !isBrowser) return
  try {
    const r = await $fetch(`${apiBase}/api/stats/maps?mode=${mode.value}`)
    maps.value = r.maps || []
  } catch { maps.value = [] }
}

async function loadStats() {
  pending.value = true
  if (!apiBase && !isBrowser) { pending.value = false; return }
  try {
    const params = new URLSearchParams({
      mode: mode.value,
      map: mapFilter.value,
      region: regionFilter.value,
      min_matches: String(minMatches.value),
      window: window.value,
      top: '10',
    })
    data.value = await $fetch(`${apiBase}/api/stats/leaderboards?${params}`)
  } catch (e) {
    console.error('[stats] load failed', e)
    data.value = null
  } finally {
    pending.value = false
  }
}

// ── Cards / Table view switch ───────────────────────────────────────────────
const view = ref('cards')
const tableData = ref(null)
const tableSort = ref({ key: 'frag_diff', dir: 'desc' })
const pageSize = ref(100)
async function loadTable() {
  if (!apiBase && !isBrowser) return
  try {
    const params = new URLSearchParams({ mode: mode.value, map: mapFilter.value, region: regionFilter.value, min_matches: String(minMatches.value), window: window.value })
    tableData.value = await $fetch(`${apiBase}/api/stats/table?${params}`)
  } catch (e) { console.error('[stats-table]', e); tableData.value = null }
}
watch(view, v => { if (v === 'table' && !tableData.value) loadTable() })
watch([mode, mapFilter, regionFilter, minMatches, window], () => { if (view.value === 'table') loadTable() })
function setSort(col) {
  if (tableSort.value.key === col.id) tableSort.value = { key: col.id, dir: tableSort.value.dir === 'desc' ? 'asc' : 'desc' }
  else tableSort.value = { key: col.id, dir: col.direction }   // default to the stat's natural direction
}
const sortedPlayers = computed(() => {
  const ps = [...(tableData.value?.players || [])]
  const k = tableSort.value.key, dir = tableSort.value.dir === 'asc' ? 1 : -1
  ps.sort((a, b) => {
    const av = a[k], bv = b[k]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return (av - bv) * dir
  })
  return ps.slice(0, pageSize.value)
})
function fmtVal(v, fmt) {
  if (v == null) return '—'
  switch (fmt) {
    case 'pct': return (v * 100).toFixed(1) + '%'
    case 'plus1': return (v >= 0 ? '+' : '') + v.toFixed(1)
    case 'ratio2': return v.toFixed(2)
    case 'plusnum': return (v >= 0 ? '+' : '') + Math.round(v).toLocaleString()
    case 'num0': return Math.round(v).toLocaleString()
    case 'num1': return v.toFixed(1)
    case 'num2': return v.toFixed(2)
    default: return v
  }
}

onMounted(async () => {
  await loadMaps()
  await loadStats()
})
watch([mode, mapFilter, regionFilter, minMatches, window], loadStats)
watch(mode, loadMaps)

function profileHref(cid) { return `/p/${encodeURIComponent(cid)}` }

useHead({ title: 'Stats leaderboards · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="head">
      <h1>Stats leaderboards</h1>
      <p class="sub">
        Mechanical-skill leaderboards — accuracy, damage, item control. <strong>Separate</strong> from
        the skill rankings; this measures how you play, not who you beat.
      </p>
    </div>

    <div class="controls">
      <div class="dd-group">
        <label>Mode</label>
        <select v-model="mode" class="dd" :disabled="true" title="Only 1on1 available right now">
          <option value="1on1">1on1</option>
          <option value="2on2" disabled>2on2 — coming with team rating</option>
          <option value="4on4" disabled>4on4 — coming with team rating</option>
        </select>
      </div>
      <div class="dd-group">
        <label>Map</label>
        <select v-model="mapFilter" class="dd">
          <option value="all">All maps</option>
          <option v-for="m in maps" :key="m.map" :value="m.map">{{ m.map }} ({{ m.games.toLocaleString() }})</option>
        </select>
      </div>
      <div class="dd-group">
        <label>Region</label>
        <select v-model="regionFilter" class="dd">
          <option value="all">All regions</option>
          <option v-for="r in ['EU','NA','SA','OC','AS-AF']" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>
      <div class="dd-group">
        <label>Min matches</label>
        <select v-model.number="minMatches" class="dd">
          <option :value="10">10</option>
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="250">250</option>
        </select>
      </div>
      <div class="dd-group">
        <label>Window</label>
        <select v-model="window" class="dd">
          <option value="30d">Last 30d</option>
          <option value="90d">Last 90d</option>
          <option value="6mo">Last 6mo</option>
          <option value="1yr">Last 1yr</option>
          <option value="all">All time</option>
        </select>
      </div>
      <span class="count" v-if="data">{{ data.player_count }} players qualify</span>
      <span class="viewtoggle">
        <button :class="{ on: view === 'cards' }" @click="view = 'cards'">Cards</button>
        <button :class="{ on: view === 'table' }" @click="view = 'table'">Table</button>
      </span>
    </div>

    <!-- CARDS -->
    <template v-if="view === 'cards'">
      <div v-if="pending" class="placeholder">Loading stats…</div>
      <div v-else-if="!data || !Object.keys(data.leaderboards || {}).length" class="placeholder">
        No stats data for these filters. Try lowering Min matches or picking a different map.
      </div>
      <div v-else class="grid">
        <div v-for="(lb, statId) in data.leaderboards" :key="statId" class="card">
          <div class="card-head">
            <h3>{{ lb.display }}</h3>
            <span class="dir" :title="lb.direction === 'asc' ? 'Lower is better' : 'Higher is better'">
              {{ lb.direction === 'asc' ? '↑ lower' : '↓ higher' }} better
            </span>
          </div>
          <div v-if="!lb.top.length" class="empty-card">No qualifying players.</div>
          <div v-else>
            <div v-for="(p, i) in lb.top.slice(0, 5)" :key="p.canonical_id" class="row" :class="{ top1: i === 0 }">
              <span class="rank">#{{ p.rank }}</span>
              <NuxtLink :to="profileHref(p.canonical_id)" class="name">{{ p.display }}</NuxtLink>
              <span v-if="p.region" class="region-pill">{{ p.region }}</span>
              <span class="val">{{ p.formatted }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- TABLE -->
    <template v-else>
      <div v-if="!tableData" class="placeholder">Loading table…</div>
      <div v-else-if="!tableData.players.length" class="placeholder">No stats for these filters.</div>
      <div v-else>
        <div class="tabletop">
          <span class="count">{{ tableData.players.length }} players · sorted by {{ (tableData.columns.find(c => c.id === tableSort.key) || {}).full || tableSort.key }}</span>
          <select v-model.number="pageSize" class="dd">
            <option :value="100">Show 100</option>
            <option :value="250">Show 250</option>
            <option :value="1000">Show 1000</option>
          </select>
        </div>
        <div class="scroll">
          <table class="stbl">
            <thead><tr>
              <th class="rk">#</th><th class="nm">Player</th><th class="rg">Reg</th>
              <th v-for="c in tableData.columns" :key="c.id" :class="{ sorted: tableSort.key === c.id }" :title="c.full" @click="setSort(c)">
                {{ c.label }}<span v-if="tableSort.key === c.id">{{ tableSort.dir === 'asc' ? ' ▴' : ' ▾' }}</span>
              </th>
              <th class="mt">M</th>
            </tr></thead>
            <tbody>
              <tr v-for="(p, i) in sortedPlayers" :key="p.canonical_id">
                <td class="rk">{{ i + 1 }}</td>
                <td class="nm"><NuxtLink :to="profileHref(p.canonical_id)" class="name">{{ p.display }}</NuxtLink></td>
                <td class="rg"><span v-if="p.region" class="region-pill">{{ p.region }}</span></td>
                <td v-for="c in tableData.columns" :key="c.id" :class="{ sorted: tableSort.key === c.id }">{{ fmtVal(p[c.id], c.fmt) }}</td>
                <td class="mt">{{ p.matches }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1320px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 20px; }
.head h1 { margin: 0 0 6px; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; }

.controls { display: flex; align-items: flex-end; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }
.dd-group { display: flex; flex-direction: column; gap: 4px; }
.dd-group label { color: var(--fg-3); font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.dd {
  background: var(--panel); border: 1px solid var(--border); color: var(--fg);
  padding: 8px 12px; border-radius: 8px; font-family: inherit; font-size: 13px; font-weight: 600;
  min-width: 140px; cursor: pointer;
}
.dd:focus { outline: none; border-color: var(--accent); }
.dd:disabled { color: var(--fg-3); cursor: not-allowed; }
.count { color: var(--fg-3); font-size: 12px; margin-left: auto; padding-bottom: 8px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px 18px; display: flex; flex-direction: column; gap: 8px;
}
.card-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
.card h3 { margin: 0; font-size: 14px; font-weight: 700; }
.card .dir { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }

.row {
  display: grid; grid-template-columns: 26px 1fr auto auto;
  gap: 8px; align-items: center; padding: 6px 0; font-size: 13px;
  border-bottom: 1px solid var(--border);
}
.row:last-child { border-bottom: 0; }
.row .rank { color: var(--fg-3); font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; text-align: right; }
.row.top1 .rank { color: var(--draw); }
.row .avatar {
  width: 24px; height: 24px; border-radius: 5px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 900; color: var(--bg);
}
.row .name {
  font-weight: 600; color: var(--fg); text-decoration: none;
  border-bottom: 1px dotted transparent; transition: border-color 0.12s, color 0.12s;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.row .name:hover { color: var(--accent); border-bottom-color: var(--accent); }
.region-pill {
  display: inline-block; padding: 1px 5px; border-radius: 4px;
  background: var(--panel-3); color: var(--fg-3);
  font-size: 9px; font-weight: 700; letter-spacing: 0.04em;
}
.row .val {
  color: var(--accent); font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 13px; min-width: 60px; text-align: right;
}
.row.top1 .val { color: var(--draw); }

.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
.empty-card { padding: 12px; text-align: center; color: var(--fg-3); font-size: 12px; }

/* view toggle */
.viewtoggle { display: inline-flex; gap: 2px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 2px; margin-left: 10px; }
.viewtoggle button { background: none; border: 0; color: var(--fg-3); font-family: inherit; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 6px; cursor: pointer; }
.viewtoggle button.on { background: var(--accent); color: var(--bg); }

/* full stats table */
.tabletop { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.tabletop .count { color: var(--fg-3); font-size: 12px; }
.tabletop .dd { margin-left: auto; }
.scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; }
.stbl { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13px; background: var(--panel); }
.stbl th, .stbl td { padding: 8px 10px; text-align: right; white-space: nowrap; }
.stbl thead th { position: sticky; top: 0; background: var(--panel-2); font-size: 11px; color: var(--fg-3); font-weight: 700; cursor: pointer; user-select: none; border-bottom: 1px solid var(--border); }
.stbl th.sorted, .stbl td.sorted { color: var(--accent); }
.stbl th.rk, .stbl td.rk { text-align: right; color: var(--fg-3); font-family: 'JetBrains Mono', monospace; }
.stbl th.nm, .stbl td.nm, .stbl th.rg, .stbl td.rg { text-align: left; }
.stbl td { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; border-bottom: 1px solid rgba(43,54,80,.4); color: var(--fg-2); }
.stbl td.nm { font-family: system-ui, sans-serif; }
.stbl td.nm .name { color: var(--fg); font-weight: 700; text-decoration: none; }
.stbl td.nm .name:hover { color: var(--accent); }
.stbl tbody tr:hover td { background: var(--panel-2); }
.stbl .mt { color: var(--fg-3); }

@media (max-width: 640px) {
  .page { padding: 18px 12px 64px; }
  .head h1 { font-size: 22px; }
  .controls { flex-wrap: wrap; gap: 6px; }
  .viewtoggle { margin-left: 0; }
  .grid { grid-template-columns: 1fr; }
}
</style>

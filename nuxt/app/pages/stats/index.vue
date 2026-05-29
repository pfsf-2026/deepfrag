<script setup>
const config = useRuntimeConfig()
// Client = '' → same-origin → CF Pages Function → edge cached. SSR = Cloud Run.
const isBrowser = typeof window !== 'undefined'
const apiBase = isBrowser ? '' : (config.public.apiBase || '')

const mode = ref('1on1')
const mapFilter = ref('all')
const regionFilter = ref('all')
const minMatches = ref(100)
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

onMounted(async () => {
  await loadMaps()
  await loadStats()
})
watch([mode, mapFilter, regionFilter, minMatches], loadStats)
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
      <span class="count" v-if="data">{{ data.player_count }} players qualify</span>
    </div>

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
            <div class="avatar">{{ (p.display || '?')[0].toUpperCase() }}</div>
            <NuxtLink :to="profileHref(p.canonical_id)" class="name">{{ p.display }}</NuxtLink>
            <span v-if="p.region" class="region-pill">{{ p.region }}</span>
            <span class="val">{{ p.formatted }}</span>
          </div>
        </div>
      </div>
    </div>
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
  display: grid; grid-template-columns: 26px 26px 1fr auto auto;
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
</style>

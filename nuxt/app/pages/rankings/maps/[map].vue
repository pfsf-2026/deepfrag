<script setup>
const route = useRoute()
const router = useRouter()
const df = useDeepFrag()

const mapName = computed(() => String(route.params.map || ''))
const mode = ref('1on1')
const minMatches = ref(10)
const search = ref('')

const rankings = ref(null)
const pending = ref(true)

const allMaps = ref([])

async function loadRankings() {
  pending.value = true
  try {
    const url = df.mapRankingsUrl(mapName.value, mode.value)
    if (!url) { rankings.value = { players: [] }; return }
    const r = await fetch(url)
    rankings.value = await r.json()
  } catch (e) {
    console.error('rankings load failed', e)
    rankings.value = { players: [] }
  } finally {
    pending.value = false
  }
}

async function loadMaps() {
  const url = df.mapListUrl(mode.value)
  if (!url) return
  try {
    const r = await fetch(url)
    const data = await r.json()
    allMaps.value = data.maps || []
  } catch { /* ignore */ }
}

onMounted(() => { loadRankings(); loadMaps() })
watch([mapName, mode], () => { loadRankings(); loadMaps() })

const filtered = computed(() => {
  const list = (rankings.value?.players || []).filter(p => p.matches >= minMatches.value)
  if (!search.value) return list
  const q = search.value.toLowerCase()
  return list.filter(p => (p.display || '').toLowerCase().includes(q)
                        || p.canonical_id.toLowerCase().includes(q))
})

function fmtPct(v) { return v == null ? '—' : (v * 100).toFixed(0) + '%' }
function profileHref(cid) { return `/p/${encodeURIComponent(cid)}` }

function pickMap(m) { router.push(`/rankings/maps/${encodeURIComponent(m)}`) }

useHead({ title: () => `${mapName.value} ${mode.value} rankings · DeepFrag` })
</script>

<template>
  <div class="page">
    <div class="head">
      <NuxtLink to="/" class="back">← All rankings</NuxtLink>
      <h1>{{ mapName }} <span class="mode-chip" :class="'chip-' + mode">{{ mode }}</span></h1>
      <p class="sub">Per-map ratings on <strong>{{ mapName }}</strong>. Sorted by conservative (μ − 3σ).</p>
    </div>

    <div class="controls">
      <span class="label">Mode</span>
      <div class="pill-group">
        <button v-for="m in ['1on1','2on2','4on4']" :key="m" :class="{active: mode === m}" @click="mode = m">{{ m }}</button>
      </div>

      <span class="label">Map</span>
      <select :value="mapName" class="search" @change="pickMap($event.target.value)">
        <option v-for="m in allMaps" :key="m.map" :value="m.map">
          {{ m.map }} ({{ m.players }})
        </option>
      </select>

      <span class="label">Min matches</span>
      <div class="pill-group">
        <button v-for="n in [5, 10, 20, 50, 100]" :key="n" :class="{active: minMatches === n}" @click="minMatches = n">{{ n }}</button>
      </div>

      <input v-model="search" type="text" placeholder="Filter by name…" class="search">
      <span class="count">{{ filtered.length }} of {{ rankings?.players?.length || 0 }}</span>
    </div>

    <div v-if="pending" class="placeholder">Loading {{ mapName }} rankings…</div>
    <div v-else-if="!filtered.length" class="placeholder">
      No players rated on <code>{{ mapName }}</code> in {{ mode }} mode yet.
    </div>

    <div v-else class="list">
      <div class="header-row">
        <span class="center">Rank</span>
        <span></span>
        <span>Player</span>
        <span>Tier</span>
        <span class="num">Rating · ± σ</span>
        <span class="num">Win rate</span>
        <span class="num">Matches</span>
      </div>

      <a v-for="p in filtered.slice(0, 500)" :key="p.canonical_id"
         :href="profileHref(p.canonical_id)"
         :class="['row', p.rank === 1 ? 'top1' : p.rank === 2 ? 'top2' : p.rank === 3 ? 'top3' : '']">
        <div class="rank">#{{ p.rank }}</div>
        <div class="avatar">{{ (p.display || '?')[0].toUpperCase() }}</div>
        <div class="id">
          <div class="name">{{ p.display }}</div>
          <div class="meta">{{ p.wins }}W – {{ p.losses }}L</div>
        </div>
        <div class="tier-cell">
          <span v-if="p.tier" class="tier-badge"
                :style="{ color: p.tier.color, borderColor: p.tier.color, background: p.tier.color + '14' }">
            {{ p.tier.name }}
          </span>
        </div>
        <div class="rating">
          {{ Math.round(p.conservative) }}
          <div class="sigma">μ {{ Math.round(p.mu) }} · ±σ {{ Math.round(p.sigma) }}</div>
        </div>
        <div class="winbar">
          <div class="bar">
            <span class="w" :style="{ width: ((p.win_rate || 0) * 100) + '%' }"></span>
            <span class="l" :style="{ width: ((1 - (p.win_rate || 0)) * 100) + '%' }"></span>
          </div>
          <div class="pct">{{ fmtPct(p.win_rate) }}</div>
        </div>
        <div class="num matches">{{ p.matches.toLocaleString() }}</div>
      </a>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 20px; }
.head .back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; display: inline-block; margin-bottom: 8px; }
.head .back:hover { color: var(--accent); }
.head h1 { margin: 0 0 6px; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; display: flex; align-items: center; gap: 12px; }
.head h1 .mode-chip {
  font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.head h1 .chip-1on1 { background: rgba(20,230,192,0.12); color: var(--accent); }
.head h1 .chip-4on4 { background: rgba(34,197,94,0.12); color: var(--win); }
.head h1 .chip-2on2 { background: rgba(245,158,11,0.12); color: var(--draw); }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; }

.controls { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin-bottom: 24px; }
.controls .label { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
.pill-group { display: inline-flex; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 3px; gap: 2px; }
.pill-group button { background: transparent; border: 0; color: var(--fg-2); padding: 6px 14px; border-radius: 5px; cursor: pointer; font-family: inherit; font-size: 12px; font-weight: 600; }
.pill-group button:hover { color: var(--fg); background: var(--panel-2); }
.pill-group button.active { background: var(--accent); color: var(--bg); }
.search { background: var(--panel); border: 1px solid var(--border); color: var(--fg); padding: 8px 14px; border-radius: 8px; font-size: 13px; min-width: 180px; font-family: inherit; }
.search:focus { outline: none; border-color: var(--accent); }
.count { color: var(--fg-3); font-size: 12px; margin-left: auto; }

.list { display: flex; flex-direction: column; gap: 8px; }
.header-row { display: grid; grid-template-columns: 60px 56px 1fr 110px 110px 200px 80px; align-items: center; gap: 16px; padding: 8px 18px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; color: var(--fg-3); }
.header-row .num { text-align: right; }
.header-row .center { text-align: center; }

.row { display: grid; grid-template-columns: 60px 56px 1fr 110px 110px 200px 80px; align-items: center; gap: 16px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; text-decoration: none; color: inherit; transition: all 0.12s; }
.row:hover { border-color: var(--accent); transform: translateX(4px); }
.row.top1 { background: linear-gradient(90deg, rgba(251,191,36,0.06), var(--panel) 30%); border-color: rgba(251,191,36,0.4); }
.row.top2 { border-color: rgba(203,213,225,0.3); }
.row.top3 { border-color: rgba(184,115,51,0.3); }

.row .rank { font-size: 18px; font-weight: 800; color: var(--fg-3); font-variant-numeric: tabular-nums; text-align: center; }
.row.top1 .rank { color: #fbbf24; }
.row.top2 .rank { color: #cbd5e1; }
.row.top3 .rank { color: #b87333; }

.row .avatar { width: 44px; height: 44px; border-radius: 10px; background: linear-gradient(135deg, var(--accent), var(--accent-2)); display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 900; color: var(--bg); }
.row .id .name { font-size: 16px; font-weight: 700; letter-spacing: -0.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row .id .meta { color: var(--fg-3); font-size: 11px; margin-top: 2px; }

.tier-cell { display: flex; }
.tier-badge { display: inline-block; padding: 4px 10px; border-radius: 999px; border: 1px solid; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }

.row .rating { font-size: 24px; font-weight: 800; color: var(--accent); font-variant-numeric: tabular-nums; line-height: 1; text-align: right; }
.row .rating .sigma { color: var(--fg-3); font-size: 11px; font-weight: 500; margin-top: 3px; }

.row .winbar { display: flex; align-items: center; gap: 8px; }
.row .winbar .bar { flex: 1; height: 6px; background: var(--panel-3); border-radius: 3px; overflow: hidden; display: flex; }
.row .winbar .bar .w { background: var(--win); height: 100%; }
.row .winbar .bar .l { background: var(--loss); height: 100%; }
.row .winbar .pct { color: var(--fg-2); font-size: 11px; font-variant-numeric: tabular-nums; min-width: 38px; text-align: right; }

.row .matches { color: var(--fg-2); font-size: 13px; font-variant-numeric: tabular-nums; }
.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
</style>

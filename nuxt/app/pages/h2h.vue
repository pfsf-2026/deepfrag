<script setup>
const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
// Client = '' → same-origin → CF Pages Function → edge cached. SSR = Cloud Run URL.
const isBrowser = typeof window !== 'undefined'
const apiBase = isBrowser ? '' : (config.public.apiBase || '')

useHead({ title: 'Head to head · DeepFrag' })

const mode = ref('1on1')
const p1 = ref(route.query.p1 ? String(route.query.p1) : '')
const p2 = ref(route.query.p2 ? String(route.query.p2) : '')
const sinceDays = ref(route.query.since ? Number(route.query.since) : 0)  // 0 = all time
const p1Search = ref('')
const p2Search = ref('')
const players = ref([])
const playersLoading = ref(true)
const data = ref(null)
const dataLoading = ref(false)
const error = ref('')

async function loadPlayers() {
  if (!apiBase && !isBrowser) { playersLoading.value = false; return }
  try {
    // /api/search requires q>=1 char, so use /api/rankings to get the full
    // rated-player list for the mode in one call. Shape: { players: [{ canonical_id, display, matches }] }
    const r = await $fetch(`${apiBase}/api/rankings?mode=${mode.value}&min_matches=10&limit=2000`)
    players.value = (r.players || []).map(p => ({
      canonical_id: p.canonical_id,
      display: p.display,
      matches: p.matches
    }))
  } catch (e) {
    console.error('[h2h] player list load failed', e)
  } finally {
    playersLoading.value = false
  }
}

async function loadH2H() {
  if (!p1.value || !p2.value || p1.value === p2.value) {
    data.value = null
    return
  }
  if (!apiBase && !isBrowser) return
  dataLoading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ p1: p1.value, p2: p2.value, mode: mode.value })
    if (sinceDays.value > 0) params.set('since_days', String(sinceDays.value))
    const r = await $fetch(`${apiBase}/api/h2h?${params}`)
    data.value = r
  } catch (e) {
    console.error('[h2h] fetch failed', e)
    error.value = e?.data?.detail || 'Failed to load H2H data'
    data.value = null
  } finally {
    dataLoading.value = false
  }
}

function syncUrl() {
  router.replace({ query: {
    ...(p1.value && { p1: p1.value }),
    ...(p2.value && { p2: p2.value }),
    ...(sinceDays.value > 0 && { since: String(sinceDays.value) })
  } })
}

function selectP1(cid) { p1.value = cid; p1Search.value = ''; syncUrl(); loadH2H() }
function selectP2(cid) { p2.value = cid; p2Search.value = ''; syncUrl(); loadH2H() }
function swap() {
  const t = p1.value; p1.value = p2.value; p2.value = t
  syncUrl(); loadH2H()
}
function changeP1() { p1.value = ''; data.value = null; syncUrl() }
function changeP2() { p2.value = ''; data.value = null; syncUrl() }
function setWindow(days) { sinceDays.value = days; syncUrl(); loadH2H() }

const WINDOWS = [
  { days: 30,  label: '30d' },
  { days: 90,  label: '90d' },
  { days: 365, label: '1y' },
  { days: 0,   label: 'All time' }
]

// Only show dropdown after 2+ chars — single-letter matches are too noisy
// (200+ players starting with 'a' isn't useful).
const p1Match = computed(() => {
  const q = p1Search.value.trim().toLowerCase()
  if (q.length < 2) return []
  return players.value.filter(x => (x.display || x.canonical_id).toLowerCase().includes(q)).slice(0, 10)
})
const p2Match = computed(() => {
  const q = p2Search.value.trim().toLowerCase()
  if (q.length < 2) return []
  return players.value.filter(x => (x.display || x.canonical_id).toLowerCase().includes(q)).slice(0, 10)
})

// Sort state for the maps table
const sortKey = ref('h2h_matches')
const sortDir = ref('desc')
function setSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  else { sortKey.value = key; sortDir.value = 'desc' }
}
const sortedMaps = computed(() => {
  if (!data.value?.maps) return []
  const k = sortKey.value
  const dir = sortDir.value === 'desc' ? -1 : 1
  const get = (m) => {
    if (k === 'h2h_matches') return m.h2h_matches
    if (k === 'h2h_wins_a') return m.h2h_wins_a
    if (k === 'h2h_wins_b') return m.h2h_wins_b
    if (k === 'rating_a') return m.rating_a?.cons ?? -Infinity
    if (k === 'rating_b') return m.rating_b?.cons ?? -Infinity
    if (k === 'gap') return (m.rating_a?.cons || 0) - (m.rating_b?.cons || 0)
    if (k === 'predict_a') return m.predict_win_a ?? -1
    return m.map
  }
  return [...data.value.maps].sort((a, b) => {
    const va = get(a); const vb = get(b)
    if (va === vb) return 0
    return va < vb ? -dir : dir
  })
})

function fmtPct(v) { return v == null ? '—' : `${Math.round(v * 100)}%` }
function fmtRating(r) {
  if (!r) return null
  return `${Math.round(r.cons)} (${r.wins}-${r.losses})`
}
function fmtAcc(v) { return v == null ? '—' : `${(v * 100).toFixed(1)}%` }

// Skill Profile radar — mirrors profile.html's sidebar radar (LG/RL/DDR/±frag/Net dmg).
// Inner pentagon = population MIN on that axis (worst rated player), outer
// pentagon = population MAX (best). Both players plotted on the same pentagon
// so the skill mismatch is visible. Ranges come from the H2H endpoint
// (skill_profile_ranges, mode-scoped, last 365d, rated players only) with
// fallback caps when the API doesn't deliver them.
const weaponAxes = computed(() => {
  const r = data.value?.skill_profile_ranges || {}
  const rng = (key, fallbackMin, fallbackMax) => ({
    min: r[key]?.min ?? fallbackMin,
    max: r[key]?.max ?? fallbackMax
  })
  return [
    { key: 'lg_accuracy',   label: 'LG',      type: 'pct',   ...rng('lg_accuracy',   0, 0.50) },
    { key: 'rl_accuracy',   label: 'RL',      type: 'pct',   ...rng('rl_accuracy',   0, 0.50) },
    { key: 'avg_ddr',       label: 'DDR',     type: 'ratio', ...rng('avg_ddr',       0, 2.50) },
    { key: 'avg_frag_diff', label: '±frag',   type: 'frag',  ...rng('avg_frag_diff', -20, 40) },
    { key: 'avg_net_dmg',   label: 'Net dmg', type: 'dmg',   ...rng('avg_net_dmg',   -3000, 8000) }
  ]
})
const radarR = 70
const radarAngles = computed(() => weaponAxes.value.map((_, i) => -Math.PI / 2 + i * (2 * Math.PI / weaponAxes.value.length)))
function ringPath(frac) {
  return radarAngles.value.map(a => `${(Math.cos(a) * radarR * frac).toFixed(1)},${(Math.sin(a) * radarR * frac).toFixed(1)}`).join(' ')
}
function dataPath(shape) {
  if (!shape) return ''
  return weaponAxes.value.map((w, i) => {
    const v = shape[w.key]
    if (v == null) return `${(Math.cos(radarAngles.value[i]) * 0).toFixed(1)},${(Math.sin(radarAngles.value[i]) * 0).toFixed(1)}`
    const span = w.max - w.min
    const f = span > 0 ? Math.min(1, Math.max(0, (v - w.min) / span)) : 0
    return `${(Math.cos(radarAngles.value[i]) * radarR * f).toFixed(1)},${(Math.sin(radarAngles.value[i]) * radarR * f).toFixed(1)}`
  }).join(' ')
}
function fmtAxisValue(ax, v) {
  if (v == null) return '—'
  if (ax.type === 'pct') return `${(v * 100).toFixed(1)}%`
  if (ax.type === 'ratio') return v.toFixed(2)
  if (ax.type === 'frag') return `${v > 0 ? '+' : ''}${v.toFixed(1)}`
  if (ax.type === 'dmg') return `${v > 0 ? '+' : ''}${Math.round(v).toLocaleString()}`
  return String(v)
}
const hasWeaponShape = computed(() => {
  const a = data.value?.player_a?.weapon_shape
  const b = data.value?.player_b?.weapon_shape
  return a && b && (a.lg_accuracy != null || a.rl_accuracy != null)
})

onMounted(async () => {
  await loadPlayers()
  if (p1.value && p2.value) await loadH2H()
})

watch(mode, loadH2H)
</script>

<template>
  <div class="page">
    <div class="head">
      <h1>Head to head</h1>
      <p class="sub">Compare any two players — overall record, per-map H2H, and per-map prediction.</p>
    </div>

    <!-- PLAYER PICKER (when no players selected yet) -->
    <div v-if="!data || !p1 || !p2" class="picker-wrap">
      <div class="picker-side">
        <label>Player A</label>
        <div class="picker-input">
          <input v-model="p1Search" :placeholder="p1 ? `Selected: ${p1}` : 'Type to search…'">
          <div v-if="p1Match.length" class="dropdown">
            <a v-for="p in p1Match" :key="p.canonical_id" href="#" @click.prevent="selectP1(p.canonical_id)">
              <strong>{{ p.display }}</strong>
              <span class="meta">{{ p.matches }} 1on1</span>
            </a>
          </div>
        </div>
      </div>
      <div class="picker-vs">VS</div>
      <div class="picker-side">
        <label>Player B</label>
        <div class="picker-input">
          <input v-model="p2Search" :placeholder="p2 ? `Selected: ${p2}` : 'Type to search…'">
          <div v-if="p2Match.length" class="dropdown">
            <a v-for="p in p2Match" :key="p.canonical_id" href="#" @click.prevent="selectP2(p.canonical_id)">
              <strong>{{ p.display }}</strong>
              <span class="meta">{{ p.matches }} 1on1</span>
            </a>
          </div>
        </div>
      </div>
    </div>

    <div v-if="dataLoading" class="placeholder">Loading H2H…</div>
    <div v-else-if="error" class="placeholder err">{{ error }}</div>

    <!-- MAIN VIEW -->
    <template v-if="data && !dataLoading">
      <!-- HEADER BAR -->
      <div class="head-bar">
        <div class="p">
          <div class="avatar a">{{ (data.player_a.display || '?')[0].toUpperCase() }}</div>
          <div>
            <div class="name">{{ data.player_a.display }}</div>
            <div class="micro">
              <span v-if="data.player_a.region" class="region-pill">{{ data.player_a.region }}</span>
              <span v-if="data.player_a.tier" class="tier" :style="{ color: data.player_a.tier.color, borderColor: data.player_a.tier.color, background: data.player_a.tier.color + '14' }">
                {{ data.player_a.tier.name }}
              </span>
              <span class="wl">{{ data.player_a.wins }}W-{{ data.player_a.losses }}L</span>
            </div>
            <button class="change-link" @click="changeP1">Change player ↺</button>
          </div>
          <div class="cons a">{{ Math.round(data.player_a.conservative) }}</div>
        </div>
        <div class="center">
          <div class="label">Head to head</div>
          <div class="h2h-score">
            <span class="a">{{ data.h2h.wins_a }}</span> — <span class="b">{{ data.h2h.wins_b }}</span>
          </div>
          <div class="meta">
            {{ data.h2h.matches }} matches
            <span v-if="data.h2h.matches"> · last {{ String(data.h2h.last_match || '').slice(0, 10) }}</span>
          </div>
          <button class="swap" @click="swap">↔ swap</button>
        </div>
        <div class="p right">
          <div class="cons b">{{ Math.round(data.player_b.conservative) }}</div>
          <div style="text-align: right;">
            <div class="name">{{ data.player_b.display }}</div>
            <div class="micro" style="justify-content: flex-end;">
              <span class="wl">{{ data.player_b.wins }}W-{{ data.player_b.losses }}L</span>
              <span v-if="data.player_b.tier" class="tier" :style="{ color: data.player_b.tier.color, borderColor: data.player_b.tier.color, background: data.player_b.tier.color + '14' }">
                {{ data.player_b.tier.name }}
              </span>
              <span v-if="data.player_b.region" class="region-pill">{{ data.player_b.region }}</span>
            </div>
            <button class="change-link" @click="changeP2">Change player ↺</button>
          </div>
          <div class="avatar b">{{ (data.player_b.display || '?')[0].toUpperCase() }}</div>
        </div>
      </div>

      <!-- TIME WINDOW PILLS -->
      <div class="window-bar">
        <span class="window-label">H2H window</span>
        <div class="window-pills">
          <button v-for="w in WINDOWS" :key="w.days"
                  :class="['window-pill', { active: sinceDays === w.days }]"
                  @click="setWindow(w.days)">
            {{ w.label }}
          </button>
        </div>
      </div>

      <!-- STRIP -->
      <div class="strip">
        <div class="cell"><div class="v a">{{ data.h2h.wins_a }}</div><div class="l">{{ data.player_a.display }} wins</div></div>
        <div class="cell"><div class="v b">{{ data.h2h.wins_b }}</div><div class="l">{{ data.player_b.display }} wins</div></div>
        <div class="cell"><div class="v a">{{ data.h2h.ddr_a ?? '—' }}</div><div class="l">H2H DDR (A)</div></div>
        <div class="cell"><div class="v b">{{ data.h2h.ddr_b ?? '—' }}</div><div class="l">H2H DDR (B)</div></div>
        <div class="cell">
          <div class="v" style="color: var(--draw);">
            {{ fmtPct(data.overall_predict_win_a) }} / {{ fmtPct(data.overall_predict_win_b) }}
          </div>
          <div class="l">overall expected</div>
        </div>
        <div class="cell"><div class="v" style="color: var(--fg-2); font-size: 14px;">{{ String(data.h2h.last_match || '').slice(0, 10) || '—' }}</div><div class="l">last match</div></div>
      </div>

      <!-- SKILL PROFILE OVERLAY -->
      <div v-if="hasWeaponShape" class="weapon-overlay">
        <div class="wo-head">
          <div>
            <div class="wo-title">Skill profile — {{ mode }}</div>
            <div class="wo-sub">LG / RL / DDR / ±frag / Net dmg — inner = population min, outer = population max</div>
          </div>
          <div class="wo-legend">
            <span class="swatch a"></span><span class="lbl">{{ data.player_a.display }}</span>
            <span class="swatch b"></span><span class="lbl">{{ data.player_b.display }}</span>
          </div>
        </div>
        <div class="wo-body">
          <svg viewBox="-110 -100 220 200" class="wo-svg">
            <!-- background rings -->
            <polygon v-for="frac in [0.25, 0.5, 0.75, 1.0]" :key="'r' + frac"
                     :points="ringPath(frac)" fill="none" stroke="#2b3445" stroke-width="0.7" />
            <!-- axes -->
            <line v-for="(a, i) in radarAngles" :key="'ax' + i"
                  x1="0" y1="0"
                  :x2="Math.cos(a) * radarR" :y2="Math.sin(a) * radarR"
                  stroke="#2b3445" stroke-width="0.7" />
            <!-- Player B (drawn first so A overlays cleaner) -->
            <polygon :points="dataPath(data.player_b.weapon_shape)"
                     fill="rgba(168,85,247,0.18)" stroke="#a855f7" stroke-width="1.8" stroke-linejoin="round" />
            <!-- Player A -->
            <polygon :points="dataPath(data.player_a.weapon_shape)"
                     fill="rgba(20,230,192,0.18)" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round" />
            <!-- labels -->
            <text v-for="(w, i) in weaponAxes" :key="'l' + i"
                  :x="Math.cos(radarAngles[i]) * (radarR + 14)"
                  :y="Math.sin(radarAngles[i]) * (radarR + 14)"
                  fill="var(--fg-2)" font-size="9" font-weight="700"
                  text-anchor="middle" dominant-baseline="middle">{{ w.label }}</text>
          </svg>
          <div class="wo-grid">
            <div v-for="w in weaponAxes" :key="w.key" class="wo-cell">
              <div class="wo-cell-l">{{ w.label }}</div>
              <div class="wo-cell-vals">
                <span class="va">{{ fmtAxisValue(w, data.player_a.weapon_shape[w.key]) }}</span>
                <span class="vsep">·</span>
                <span class="vb">{{ fmtAxisValue(w, data.player_b.weapon_shape[w.key]) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TABLE -->
      <div v-if="sortedMaps.length === 0" class="placeholder">
        No H2H matches between {{ data.player_a.display }} and {{ data.player_b.display }} on top-20 1on1 maps yet.
      </div>
      <div v-else class="table-wrap">
      <table class="matchup">
        <thead>
          <tr>
            <th @click="setSort('map')" class="sortable">Map <span class="arrow" v-if="sortKey==='map'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
            <th class="num sortable" @click="setSort('h2h_wins_a')">{{ data.player_a.display }} W <span class="arrow" v-if="sortKey==='h2h_wins_a'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
            <th class="num sortable" @click="setSort('h2h_wins_b')">{{ data.player_b.display }} W <span class="arrow" v-if="sortKey==='h2h_wins_b'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
            <th class="num">H2H DDR (A / B)</th>
            <th class="num sortable" @click="setSort('rating_a')">{{ data.player_a.display }} rating <span class="arrow" v-if="sortKey==='rating_a'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
            <th class="num sortable" @click="setSort('rating_b')">{{ data.player_b.display }} rating <span class="arrow" v-if="sortKey==='rating_b'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
            <th class="num sortable" @click="setSort('gap')">Gap <span class="arrow" v-if="sortKey==='gap'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
            <th class="center sortable" @click="setSort('predict_a')">Predicted next <span class="arrow" v-if="sortKey==='predict_a'">{{ sortDir === 'desc' ? '▼' : '▲' }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in sortedMaps" :key="m.map">
            <td>
              <div class="map">{{ m.map }}</div>
              <div class="totalmatches">{{ m.h2h_matches }} H2H {{ m.h2h_matches === 1 ? 'match' : 'matches' }}</div>
            </td>
            <td class="a-cell">{{ m.h2h_wins_a }}</td>
            <td class="b-cell">{{ m.h2h_wins_b }}</td>
            <td class="rating">{{ m.h2h_ddr_a ?? '—' }} / {{ m.h2h_ddr_b ?? '—' }}</td>
            <td class="rating">
              <template v-if="m.rating_a">{{ Math.round(m.rating_a.cons) }} <span class="muted">({{ m.rating_a.wins }}-{{ m.rating_a.losses }})</span></template>
              <span v-else class="nodata">no rating</span>
            </td>
            <td class="rating">
              <template v-if="m.rating_b">{{ Math.round(m.rating_b.cons) }} <span class="muted">({{ m.rating_b.wins }}-{{ m.rating_b.losses }})</span></template>
              <span v-else class="nodata">no rating</span>
            </td>
            <td class="rating" :class="{ up: m.rating_a && m.rating_b && m.rating_a.cons > m.rating_b.cons, down: m.rating_a && m.rating_b && m.rating_a.cons < m.rating_b.cons }">
              <template v-if="m.rating_a && m.rating_b">
                {{ Math.abs(Math.round(m.rating_a.cons - m.rating_b.cons)) }}
                {{ m.rating_a.cons > m.rating_b.cons ? data.player_a.display : data.player_b.display }}
              </template>
              <span v-else class="nodata">—</span>
            </td>
            <td>
              <div v-if="m.predict_win_a != null" class="pred">
                <div class="swatch">
                  <div class="a" :style="{ width: (m.predict_win_a * 100) + '%' }"></div>
                  <div class="b" :style="{ width: (m.predict_win_b * 100) + '%' }"></div>
                </div>
                <span :class="m.predict_win_a >= 0.5 ? 'win-a' : 'win-b'">
                  {{ m.predict_win_a >= 0.5 ? data.player_a.display : data.player_b.display }} {{ Math.round(Math.max(m.predict_win_a, m.predict_win_b) * 100) }}%
                </span>
              </div>
              <span v-else class="nodata">insufficient data</span>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1480px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 20px; }
.head h1 { margin: 0 0 6px; font-size: 28px; font-weight: 800; letter-spacing: -0.02em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; }

/* PICKER */
.picker-wrap {
  display: grid; grid-template-columns: 1fr 60px 1fr; gap: 16px; align-items: end;
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; margin-bottom: 24px;
}
.picker-side label {
  display: block; font-size: 10px; color: var(--fg-3); font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 6px;
}
.picker-input { position: relative; }
.picker-input input {
  width: 100%; background: var(--panel-2); border: 1px solid var(--border); color: var(--fg);
  padding: 10px 14px; border-radius: 8px; font-family: inherit; font-size: 14px;
}
.picker-input input:focus { outline: none; border-color: var(--accent); }
.picker-input .dropdown {
  position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
  z-index: 10; max-height: 320px; overflow-y: auto;
}
.picker-input .dropdown a {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 14px; color: var(--fg); text-decoration: none;
  font-size: 13px; border-bottom: 1px solid var(--border);
}
.picker-input .dropdown a:last-child { border-bottom: 0; }
.picker-input .dropdown a:hover { background: var(--panel-3); }
.picker-input .dropdown .meta { color: var(--fg-3); font-size: 11px; }
.picker-vs { text-align: center; color: var(--fg-3); font-weight: 700; letter-spacing: 0.16em; padding-bottom: 10px; }

/* HEADER BAR */
.head-bar {
  display: grid; grid-template-columns: 1fr auto 1fr;
  gap: 24px; align-items: center;
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 24px; margin-bottom: 8px;
}
.head-bar .p { display: flex; align-items: center; gap: 14px; }
.head-bar .p.right { justify-content: flex-end; }
.head-bar .avatar {
  width: 56px; height: 56px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 26px; font-weight: 900; color: var(--bg);
}
.head-bar .avatar.a { background: linear-gradient(135deg, var(--accent), var(--accent-2)); }
.head-bar .avatar.b { background: linear-gradient(135deg, #a855f7, #ec4899); }
.head-bar .name { font-size: 20px; font-weight: 800; }
.head-bar .micro { font-size: 11px; color: var(--fg-3); display: flex; gap: 8px; margin-top: 4px; align-items: center; }
.head-bar .region-pill { background: var(--panel-3); padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 10px; }
.head-bar .tier {
  padding: 2px 8px; border-radius: 4px; border: 1px solid; font-weight: 700;
  font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase;
}
.head-bar .wl { color: var(--fg-2); font-size: 10px; }
.head-bar .cons {
  font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums;
}
.head-bar .p .cons { margin-left: 16px; }
.head-bar .p.right .cons { margin-right: 16px; }
.head-bar .cons.a { color: var(--accent); }
.head-bar .cons.b { color: #a855f7; }
.head-bar .center { text-align: center; position: relative; }
.head-bar .center .label {
  font-size: 9px; color: var(--fg-3); letter-spacing: 0.16em;
  text-transform: uppercase; font-weight: 700;
}
.head-bar .center .h2h-score {
  font-size: 32px; font-weight: 900; font-variant-numeric: tabular-nums; margin-top: 2px;
}
.head-bar .center .h2h-score .a { color: var(--accent); }
.head-bar .center .h2h-score .b { color: #a855f7; }
.head-bar .center .meta { font-size: 11px; color: var(--fg-3); margin-top: 2px; }
.head-bar .center .swap {
  margin-top: 6px; background: transparent; border: 1px solid var(--border);
  color: var(--fg-3); font-size: 11px; padding: 3px 10px;
  border-radius: 4px; cursor: pointer; font-family: inherit;
}
.head-bar .center .swap:hover { color: var(--fg); border-color: var(--accent); }

/* Change Player link — same compact pill as .swap, sits under the name */
.head-bar .change-link {
  margin-top: 6px; background: transparent; border: 1px solid var(--border);
  color: var(--fg-3); font-size: 11px; padding: 3px 10px;
  border-radius: 4px; cursor: pointer; font-family: inherit;
}
.head-bar .change-link:hover { color: var(--fg); border-color: var(--accent); }

/* Time window pill group */
.window-bar {
  display: flex; align-items: center; gap: 12px;
  margin: 16px 0 8px;
}
.window-label {
  font-size: 10px; color: var(--fg-3); text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 700;
}
.window-pills { display: flex; gap: 6px; }
.window-pill {
  background: var(--panel); border: 1px solid var(--border); color: var(--fg-2);
  padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
  cursor: pointer; font-family: inherit;
}
.window-pill:hover { color: var(--fg); border-color: var(--accent); }
.window-pill.active {
  color: var(--accent); border-color: var(--accent);
  background: rgba(20,230,192,0.06);
}

/* Weapon shape overlay card — two players' radars on the same pentagon */
.weapon-overlay {
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px 24px; margin-bottom: 16px;
}
.wo-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 14px;
}
.wo-title { font-size: 13px; font-weight: 700; color: var(--fg); letter-spacing: -0.01em; }
.wo-sub { font-size: 11px; color: var(--fg-3); margin-top: 2px; }
.wo-legend { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--fg-2); }
.wo-legend .swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }
.wo-legend .swatch.a { background: var(--accent); }
.wo-legend .swatch.b { background: #a855f7; }
.wo-legend .lbl { font-weight: 700; margin-right: 4px; }

.wo-body { display: grid; grid-template-columns: 280px 1fr; gap: 32px; align-items: center; }
.wo-svg { width: 280px; height: 240px; }
.wo-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.wo-cell { padding: 10px 12px; background: var(--panel-2); border-radius: 8px; text-align: center; }
.wo-cell-l { font-size: 10px; color: var(--fg-3); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.wo-cell-vals { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 12px; margin-top: 4px; }
.wo-cell-vals .va { color: var(--accent); }
.wo-cell-vals .vb { color: #a855f7; }
.wo-cell-vals .vsep { color: var(--fg-3); margin: 0 4px; }

/* STRIP */
.strip {
  display: grid; grid-template-columns: repeat(6, 1fr);
  gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 12px;
  overflow: hidden; margin-bottom: 24px;
}
.strip .cell { background: var(--panel); padding: 14px; text-align: center; }
.strip .cell .v { font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; }
.strip .cell .v.a { color: var(--accent); }
.strip .cell .v.b { color: #a855f7; }
.strip .cell .l {
  font-size: 10px; color: var(--fg-3); text-transform: uppercase;
  letter-spacing: 0.06em; margin-top: 3px; font-weight: 700;
}

/* TABLE */
table.matchup {
  width: 100%; border-collapse: separate; border-spacing: 0;
  background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
}
table.matchup thead { background: var(--panel-2); }
table.matchup th {
  text-align: left; padding: 12px 14px; font-size: 10px; color: var(--fg-3);
  font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  border-bottom: 1px solid var(--border);
}
table.matchup th.num { text-align: right; }
table.matchup th.center { text-align: center; }
table.matchup th.sortable { cursor: pointer; user-select: none; }
table.matchup th.sortable:hover { color: var(--fg); }
table.matchup th .arrow { color: var(--accent); font-size: 9px; margin-left: 4px; }
table.matchup td { padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
table.matchup tr:last-child td { border-bottom: 0; }
table.matchup tr:hover td { background: rgba(20,230,192,0.02); }
table.matchup .map { font-weight: 700; color: var(--fg); }
table.matchup .totalmatches { color: var(--fg-3); font-size: 11px; margin-top: 2px; }
table.matchup .a-cell { color: var(--accent); font-weight: 700; font-family: 'JetBrains Mono', monospace; text-align: right; }
table.matchup .b-cell { color: #a855f7; font-weight: 700; font-family: 'JetBrains Mono', monospace; text-align: right; }
table.matchup .rating { font-family: 'JetBrains Mono', monospace; color: var(--fg-2); text-align: right; }
table.matchup .rating .muted { color: var(--fg-3); }
table.matchup .rating.up { color: var(--accent); }
table.matchup .rating.down { color: #a855f7; }
table.matchup .nodata { color: var(--fg-3); font-size: 11px; }
table.matchup .pred {
  display: inline-flex; align-items: center; gap: 8px;
  font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 12px;
}
table.matchup .pred .swatch {
  width: 50px; height: 8px; border-radius: 2px; display: flex; overflow: hidden; background: var(--panel-3);
}
table.matchup .pred .swatch .a { background: var(--accent); height: 100%; }
table.matchup .pred .swatch .b { background: #a855f7; height: 100%; }
table.matchup .pred .win-a { color: var(--accent); }
table.matchup .pred .win-b { color: #a855f7; }

.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
.placeholder.err { color: var(--loss); }

.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }

@media (max-width: 760px) {
  .page { padding: 20px 14px 64px; }
  .head h1 { font-size: 22px; }

  /* Picker: stack the two sides, VS divider between */
  .picker-wrap { grid-template-columns: 1fr; gap: 12px; padding: 16px; }
  .picker-vs { padding: 2px 0; }

  /* Header bar: stack A / score / B vertically */
  .head-bar { grid-template-columns: 1fr; gap: 16px; padding: 16px; text-align: center; }
  .head-bar .p, .head-bar .p.right { justify-content: center; }
  .head-bar .avatar { width: 46px; height: 46px; font-size: 22px; }
  .head-bar .name { font-size: 17px; }
  .head-bar .p .cons, .head-bar .p.right .cons { margin: 0 0 0 12px; font-size: 22px; }
  .head-bar .center .h2h-score { font-size: 26px; }

  /* Skill profile overlay: stack radar over the value grid */
  .wo-body { grid-template-columns: 1fr; gap: 16px; justify-items: center; }
  .wo-svg { width: 100%; max-width: 280px; height: auto; }
  .wo-grid { grid-template-columns: repeat(3, 1fr); width: 100%; }

  /* Strip: 6 cells -> 3x2 */
  .strip { grid-template-columns: repeat(3, 1fr); }
  .strip .cell { padding: 12px 8px; }
  .strip .cell .v { font-size: 16px; }
}

@media (max-width: 400px) {
  .wo-grid { grid-template-columns: repeat(2, 1fr); }
  .strip { grid-template-columns: repeat(2, 1fr); }
}
</style>

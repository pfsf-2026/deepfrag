<script setup>
const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const apiBase = config.public.apiBase || ''

useHead({ title: 'Head to head · DeepFrag' })

const mode = ref('1on1')
const p1 = ref(route.query.p1 ? String(route.query.p1) : '')
const p2 = ref(route.query.p2 ? String(route.query.p2) : '')
const p1Search = ref('')
const p2Search = ref('')
const players = ref([])
const playersLoading = ref(true)
const data = ref(null)
const dataLoading = ref(false)
const error = ref('')

async function loadPlayers() {
  if (!apiBase) { playersLoading.value = false; return }
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
  if (!apiBase) return
  dataLoading.value = true
  error.value = ''
  try {
    const r = await $fetch(`${apiBase}/api/h2h?p1=${encodeURIComponent(p1.value)}&p2=${encodeURIComponent(p2.value)}&mode=${mode.value}`)
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
  router.replace({ query: { ...(p1.value && { p1: p1.value }), ...(p2.value && { p2: p2.value }) } })
}

function selectP1(cid) { p1.value = cid; p1Search.value = ''; syncUrl(); loadH2H() }
function selectP2(cid) { p2.value = cid; p2Search.value = ''; syncUrl(); loadH2H() }
function swap() {
  const t = p1.value; p1.value = p2.value; p2.value = t
  syncUrl(); loadH2H()
}

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
          </div>
          <div class="avatar b">{{ (data.player_b.display || '?')[0].toUpperCase() }}</div>
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

      <!-- TABLE -->
      <div v-if="sortedMaps.length === 0" class="placeholder">
        No H2H matches between {{ data.player_a.display }} and {{ data.player_b.display }} on top-20 1on1 maps yet.
      </div>
      <table v-else class="matchup">
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
</style>

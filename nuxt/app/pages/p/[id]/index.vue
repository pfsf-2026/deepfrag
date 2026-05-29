<script setup>
const route = useRoute()
const id = computed(() => String(route.params.id))

const profile = ref(null)
const pending = ref(true)
const view = ref('nav')   // 'nav' (Mock 5 launchpad) | 'metrics' (Mock 3 grid)
const windowKey = ref('90')
const df = useDeepFrag()

async function loadProfile() {
  pending.value = true
  try {
    // API mode: hit /api/players/{id}/full?window=N. The endpoint returns the same
    // top-level shape as the legacy static JSON but only includes the requested window
    // (it's the only one rendered), keeping the payload ~5× smaller than the static file.
    const url = df.useApi
      ? `${df.profileUrl(id.value)}/full?window=${windowKey.value}`
      : df.profileUrl(id.value)
    const r = await fetch(url)
    if (!r.ok) throw new Error(r.status)
    profile.value = await r.json()
  } catch {
    profile.value = null
  } finally {
    pending.value = false
  }
}
onMounted(loadProfile)
watch(id, loadProfile)
// When user clicks a window pill in API mode, refetch (each window comes from
// a separate API call now instead of all being pre-baked in the static JSON).
watch(windowKey, () => { if (df.useApi) loadProfile() })

const w = computed(() => profile.value?.windows?.[windowKey.value] || {})
// Human-friendly window label for card subtitles ("last 90d" / "last year" / "all time")
const windowLabel = computed(() => ({
  '7':   'last 7d',
  '30':  'last 30d',
  '90':  'last 90d',
  '365': 'last year',
  'all': 'all time'
}[windowKey.value] || windowKey.value))
const m1on1 = computed(() => w.value.by_mode?.['1on1'] || {})
const m4on4 = computed(() => w.value.by_mode?.['4on4'] || {})
const m2on2 = computed(() => w.value.by_mode?.['2on2'] || {})
const ratings = computed(() => profile.value?.ratings || {})

// Rating history — fetched once after profile loads, used by the ELO history chart.
// Defaults to overall 1on1 (the mode most players care about). API-only feature.
const ratingHistory = ref([])
const ratingHistoryMode = ref('1on1')
const ratingHistoryLoading = ref(false)

async function loadRatingHistory() {
  const url = df.ratingHistoryUrl(id.value, ratingHistoryMode.value)
  if (!url) { ratingHistory.value = []; return }
  ratingHistoryLoading.value = true
  try {
    const r = await fetch(url)
    if (r.ok) {
      const data = await r.json()
      ratingHistory.value = data.points || []
    }
  } catch {
    ratingHistory.value = []
  } finally {
    ratingHistoryLoading.value = false
  }
}
onMounted(loadRatingHistory)
watch(id, loadRatingHistory)
watch(ratingHistoryMode, loadRatingHistory)

// ── Config Profile (hardware/settings) ──────────────────────────────────────
// Seeded from the community config sheet; user-editable. Stored as a free-form
// key→value bag plus nationality. We render it grouped (mouse/screen/cfg/binds)
// and offer an inline edit form (admin-gated server-side for now).
const config = ref(null)
const configLoading = ref(true)
const configEditing = ref(false)
const configDraft = ref({})

async function loadConfig() {
  const url = df.configUrl(id.value)
  if (!url) { config.value = null; configLoading.value = false; return }
  configLoading.value = true
  try {
    const r = await fetch(url)
    config.value = r.ok ? await r.json() : null
  } catch { config.value = null } finally { configLoading.value = false }
}
onMounted(loadConfig)
watch(id, loadConfig)

// Field groups for display + editing. label → config key.
const configGroups = [
  { title: 'Mouse', fields: [
    ['Sensitivity (cm/360)', 'sens_cm360'], ['DPI', 'dpi'], ['Mouse', 'mouse'],
    ['Grip', 'grip'], ['Hand', 'hand'], ['Accel', 'accel'], ['Wireless', 'wireless'],
  ]},
  { title: 'Mousepad / Screen', fields: [
    ['Mousepad', 'mousepad'], ['Pad size', 'mousepad_size'], ['Pad type', 'mousepad_type'],
    ['Monitor', 'monitor'], ['Resolution', 'resolution'], ['Refresh (Hz)', 'refresh_hz'],
    ['Monitor inches', 'monitor_inches'],
  ]},
  { title: 'Config', fields: [
    ['FOV', 'fov'], ['Movement', 'movement'], ['Invert X', 'invert_x'], ['Invert Y', 'invert_y'],
    ['Shaft lower sens', 'shaft_lower_sens'],
  ]},
  { title: 'Binds', fields: [
    ['RL', 'bind_rl'], ['LG', 'bind_lg'], ['GL', 'bind_gl'], ['SNG', 'bind_sng'],
    ['NG', 'bind_ng'], ['SSG', 'bind_ssg'], ['SG', 'bind_sg'], ['Axe', 'bind_axe'],
    ['Jump', 'bind_jump'], ['Movement keys', 'bind_movement'], ['Weapon change', 'bind_weapon_change'],
  ]},
]
const configHasData = computed(() => {
  const c = config.value?.config
  return c && Object.keys(c).length > 0
})

function startConfigEdit() {
  configDraft.value = { ...(config.value?.config || {}), _nationality: config.value?.nationality || '' }
  configEditing.value = true
}
function cancelConfigEdit() { configEditing.value = false }

const configSaving = ref(false)
const configSaveErr = ref('')
async function saveConfig() {
  const url = df.configUrl(id.value)
  if (!url) return
  configSaving.value = true; configSaveErr.value = ''
  const draft = { ...configDraft.value }
  const nationality = draft._nationality || null
  delete draft._nationality
  // Drop empties so we don't store blank keys
  const clean = {}
  for (const [k, v] of Object.entries(draft)) if (v != null && String(v).trim() !== '') clean[k] = v
  try {
    const r = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: clean, nationality }),
    })
    if (!r.ok) throw new Error(r.status === 401 || r.status === 503
      ? 'Editing is admin-only right now (per-user login coming soon).'
      : `Save failed (${r.status})`)
    configEditing.value = false
    await loadConfig()
  } catch (e) { configSaveErr.value = String(e.message || e) } finally { configSaving.value = false }
}

function fmtPct(v) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }
function fmtNum(v) { return v == null ? '—' : Number(v).toLocaleString() }
function fmtDec(v, d = 1) { return v == null ? '—' : Number(v).toFixed(d) }
function fmtDelta(v) { return v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(1) }
function fmtDate(v) { return v == null ? '—' : new Date(v).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) }
// Deep-link into the detailed profile.html with a specific tab pre-selected.
// 90d window is the default there, so no need to pass window in URL.
function deepHref(tab) { return `/profile.html?id=${encodeURIComponent(id.value)}#${tab}` }

// Metric definitions for the Mock 3 metric grid. Each shows current value + delta vs
// prior period + sparkline of the metric over the active window's weekly buckets.
// `higherBetter: false` flips the green/red on the delta arrow (e.g. damage taken).
// `pp: true` formats the delta as percentage points (for ratio-style stats).
const metricDefs = [
  { label: 'Win rate', key: 'win_rate', fmt: fmtPct, higherBetter: true, pp: true },
  { label: 'Avg frags', key: 'avg_frags', fmt: v => fmtDec(v, 1), higherBetter: true },
  { label: 'Avg ±', key: 'avg_frag_diff', fmt: fmtDelta, higherBetter: true },
  { label: 'Damage given', key: 'avg_dmg_given', fmt: v => fmtNum(Math.round(v || 0)), higherBetter: true },
  { label: 'Damage taken', key: 'avg_dmg_taken', fmt: v => fmtNum(Math.round(v || 0)), higherBetter: false },
  { label: 'LG accuracy', key: 'lg_accuracy', fmt: fmtPct, higherBetter: true, pp: true },
  { label: 'RL accuracy', key: 'rl_accuracy', fmt: fmtPct, higherBetter: true, pp: true },
  { label: 'SG accuracy', key: 'sg_accuracy', fmt: fmtPct, higherBetter: true, pp: true },
  { label: 'SSG accuracy', key: 'ssg_accuracy', fmt: fmtPct, higherBetter: true, pp: true },
  { label: 'LG dmg / m', key: 'avg_lg_dmg', fmt: v => fmtNum(Math.round(v || 0)), higherBetter: true },
  { label: 'RL dmg / m', key: 'avg_rl_dmg', fmt: v => fmtNum(Math.round(v || 0)), higherBetter: true },
  { label: 'Red armor / m', key: 'avg_ra', fmt: v => fmtDec(v, 1), higherBetter: true },
  { label: 'Yellow armor / m', key: 'avg_ya', fmt: v => fmtDec(v, 1), higherBetter: true },
  { label: 'Mega health / m', key: 'avg_mh', fmt: v => fmtDec(v, 1), higherBetter: true },
  { label: 'Avg ping', key: 'avg_ping', fmt: v => v == null ? '—' : Math.round(v) + 'ms', higherBetter: false },
  { label: 'Matches', key: 'matches', fmt: fmtNum, higherBetter: true }
]

function priorM1on1() {
  return w.value.prior?.by_mode?.['1on1'] || {}
}
function deltaInfo(def) {
  const cur = m1on1.value[def.key]
  const prior = priorM1on1()[def.key]
  if (cur == null || prior == null) return { str: '', cls: 'flat' }
  const d = cur - prior
  if (Math.abs(d) < 0.0001) return { str: '·', cls: 'flat' }
  const up = def.higherBetter ? d > 0 : d < 0
  const arrow = d > 0 ? '▲' : '▼'
  let str
  if (def.pp) str = (d > 0 ? '+' : '') + (d * 100).toFixed(1)
  else if (Math.abs(prior) > 50) str = (d > 0 ? '+' : '') + Math.round(d)
  else if (Math.abs(prior) > 1) str = (d > 0 ? '+' : '') + d.toFixed(1)
  else str = (d > 0 ? '+' : '') + d.toFixed(2)
  return { str: arrow + ' ' + str, cls: up ? 'up' : 'down' }
}
function sparkData(key) {
  const trend = w.value.trend_weekly_by_mode?.['1on1'] || []
  return trend.map(t => t[key] ?? null)
}

// Snapshot data for the Trends nav-card. Pulls weekly 1on1 buckets and turns
// them into a quick "X weeks · peak WR · 3 deltas + sparkline" summary so the
// card has something useful before the user clicks through.
const trendsSnapshot = computed(() => {
  const trend = (w.value.trend_weekly_by_mode || {})['1on1'] || []
  const live = trend.filter(t => (t.matches || 0) > 0)
  if (live.length === 0) {
    return { weeks: 0, peakWin: null, spark: [],
             winRateDelta: { str: '—', cls: 'flat' },
             lgDelta: { str: '—', cls: 'flat' },
             fragDiffDelta: { str: '—', cls: 'flat' } }
  }
  const peakWin = live.reduce((m, t) => Math.max(m, t.win_rate ?? 0), 0)
  // Delta = average of last third vs average of first third (smoother than first/last week)
  const slice = (arr, a, b) => arr.slice(Math.floor(arr.length * a), Math.floor(arr.length * b))
  const avgKey = (rows, key) => {
    const vals = rows.map(r => r[key]).filter(v => v != null)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }
  const earlyWR = avgKey(slice(live, 0, 0.33), 'win_rate')
  const recentWR = avgKey(slice(live, 0.66, 1), 'win_rate')
  const earlyLG = avgKey(slice(live, 0, 0.33), 'lg_accuracy')
  const recentLG = avgKey(slice(live, 0.66, 1), 'lg_accuracy')
  const earlyFD = avgKey(slice(live, 0, 0.33), 'avg_frag_diff')
  const recentFD = avgKey(slice(live, 0.66, 1), 'avg_frag_diff')
  return {
    weeks: live.length,
    peakWin,
    spark: trend.map(t => t.avg_frag_diff ?? 0),
    winRateDelta: trendDelta(earlyWR, recentWR, { pp: true }),
    lgDelta: trendDelta(earlyLG, recentLG, { pp: true }),
    fragDiffDelta: trendDelta(earlyFD, recentFD)
  }
})

function trendDelta(early, recent, { pp = false } = {}) {
  if (early == null || recent == null) return { str: '—', cls: 'flat' }
  const d = recent - early
  if (Math.abs(d) < 0.0001) return { str: '·', cls: 'flat' }
  const arrow = d > 0 ? '▲' : '▼'
  const str = pp ? (d > 0 ? '+' : '') + (d * 100).toFixed(1) + 'pp'
                 : (d > 0 ? '+' : '') + d.toFixed(1)
  return { str: arrow + ' ' + str, cls: d > 0 ? 'up' : 'down' }
}

// Compare card — current 1on1 stat vs prior period (same key)
const hasPrior = computed(() => !!w.value.prior?.by_mode?.['1on1'])
function compareCardDelta(key, { pp = false } = {}) {
  const cur = m1on1.value[key]
  const prior = w.value.prior?.by_mode?.['1on1']?.[key]
  if (cur == null || prior == null) return { str: '—', cls: 'flat' }
  const d = cur - prior
  if (Math.abs(d) < 0.0001) return { str: '·', cls: 'flat' }
  const arrow = d > 0 ? '▲' : '▼'
  const str = pp ? (d > 0 ? '+' : '') + (d * 100).toFixed(1) + 'pp'
                 : (d > 0 ? '+' : '') + (Math.abs(prior) > 50 ? Math.round(d).toLocaleString() : d.toFixed(1))
  return { str: arrow + ' ' + str, cls: d > 0 ? 'up' : 'down' }
}

// Compact delta widget for nav-card stat bubbles. Returns { str, cls } or null
// when no prior data exists (e.g. window === 'all'). Used below each label.
function modeDelta(mode, key, opts = {}) {
  const cur = (w.value.by_mode || {})[mode]?.[key]
  const prior = (w.value.prior?.by_mode || {})[mode]?.[key]
  return computeDelta(cur, prior, opts)
}
// Per-map ratings (1on1 only for now). Keyed by lowercase map name.
const mapRatings1on1 = computed(() => profile.value?.map_ratings_1on1 || {})
function mapRating(bucket) { return mapRatings1on1.value[bucket]?.conservative }

function oppDelta(opponent, key = 'win_rate', opts = {}) {
  const curList = w.value.head_to_head_1on1 || []
  const priorList = w.value.prior?.head_to_head_1on1 || []
  const cur = curList.find(x => x.opponent === opponent)?.[key]
  const prior = priorList.find(x => x.opponent === opponent)?.[key]
  return computeDelta(cur, prior, { pp: key === 'win_rate', ...opts })
}

function computeDelta(cur, prior, { higherBetter = true, pp = false } = {}) {
  if (cur == null || prior == null) return null
  const d = cur - prior
  if (Math.abs(d) < 0.0001) return null
  const up = higherBetter ? d > 0 : d < 0
  const arrow = d > 0 ? '▲' : '▼'
  let str
  // Percent-pt deltas (pp:true) render the difference in absolute pts but drop
  // the 'pp' suffix — context already says "this is a percentage stat".
  if (pp) str = (d > 0 ? '+' : '') + (d * 100).toFixed(1)
  else if (Math.abs(prior) > 50) str = (d > 0 ? '+' : '') + Math.round(d)
  else if (Math.abs(prior) > 1) str = (d > 0 ? '+' : '') + d.toFixed(1)
  else str = (d > 0 ? '+' : '') + d.toFixed(2)
  return { str: `${arrow} ${str}`, cls: up ? 'up' : 'down' }
}

useHead({ title: () => profile.value ? `${profile.value.player} · DeepFrag` : 'Player · DeepFrag' })
</script>

<template>
  <div class="page">
    <div v-if="pending" class="placeholder">Loading profile…</div>
    <div v-else-if="!profile" class="placeholder">
      No profile data for <code>{{ id }}</code>. Try a different player from the <NuxtLink to="/players">browse page</NuxtLink>.
    </div>

    <template v-else>
      <!-- ── Hero ── -->
      <div class="hero">
        <div class="avatar">{{ (profile.player || '?')[0].toUpperCase() }}</div>
        <div class="id">
          <h1>{{ profile.player }}</h1>
          <div class="sub">
            <span>{{ fmtNum(profile.career.hub.matches) }} hub matches</span>
            <span class="sep">·</span>
            <span>Active since {{ fmtDate(profile.career.hub.first_match) }}</span>
            <span class="sep">·</span>
            <span>Last seen {{ fmtDate(profile.career.hub.last_match) }}</span>
          </div>
        </div>
        <div class="hero-actions">
          <div class="pill-group">
            <button :class="{active: view === 'nav'}" @click="view = 'nav'" title="Launchpad layout">Nav</button>
            <button :class="{active: view === 'metrics'}" @click="view = 'metrics'" title="Metric grid">Metrics</button>
          </div>
        </div>
      </div>

      <!-- ── Per-mode ratings ── -->
      <div class="rating-row">
        <div v-for="mode in ['1on1', '2on2', '4on4']" :key="mode" class="rating-group">
          <div class="rating-tile" :class="{ 'rating-tile-active': ratingHistoryMode === mode && ratings[mode] }"
               @click="ratings[mode] && (ratingHistoryMode = mode)">
            <div class="rt-label"><span :class="['chip', 'chip-' + mode]">{{ mode }}</span></div>
            <template v-if="ratings[mode]">
              <div class="rt-val">{{ Math.round(ratings[mode].conservative) }}</div>
              <div class="rt-sigma">μ {{ Math.round(ratings[mode].mu) }} · ±σ {{ Math.round(ratings[mode].sigma) }}</div>
              <div class="rt-meta">#{{ ratings[mode].rank }} of {{ ratings[mode].total_rated }} · {{ ratings[mode].wins }}W–{{ ratings[mode].losses }}L</div>
              <span v-if="ratings[mode].tier" class="rt-tier"
                    :style="{ color: ratings[mode].tier.color, borderColor: ratings[mode].tier.color, background: ratings[mode].tier.color + '14' }">
                {{ ratings[mode].tier.name }}
              </span>
            </template>
            <template v-else>
              <div class="rt-val muted">—</div>
              <div class="rt-sigma">not rated yet</div>
            </template>
          </div>
        </div>
      </div>

      <!-- ── ELO history chart — only in Nav view ──
           The Metrics view is meant for dense numerical scanning; the chart
           occupies ~500px and disrupts that. The Nav/Metrics toggle in the
           hero now meaningfully gates this: chart visible in Nav, hidden in
           Metrics. The toggle itself was previously cosmetic (just swapped
           the section below the tab bar). -->
      <template v-if="view === 'nav'">
        <div v-if="ratings[ratingHistoryMode]?.provisional" class="rh-section rh-empty">
          <strong>Not enough unique opponents</strong> to plot a meaningful {{ ratingHistoryMode }} rating history.
          Faced {{ ratings[ratingHistoryMode].unique_opponents }} of 10 needed for a stable rating —
          the trajectory would be dominated by a tiny pool and wouldn't reflect real skill.
        </div>
        <div v-else-if="ratingHistory.length" class="rh-section">
          <div class="rh-head">
            <h3>{{ ratingHistoryMode }} rating history <span class="rh-sub">· {{ ratingHistory.length }} rated matches</span></h3>
            <span class="rh-hint">Click a mode tile above to switch</span>
          </div>
          <RatingHistoryChart :points="ratingHistory" :height="220" />
        </div>
        <div v-else-if="ratingHistoryLoading" class="rh-section rh-empty">Loading rating history…</div>
      </template>

      <!-- ── Config Profile (hardware/settings) — Nav view only ── -->
      <template v-if="view === 'nav'">
        <div class="cfg-section">
          <div class="cfg-head">
            <h3>⚙️ Config Profile
              <span class="cfg-sub" v-if="config && config.source">· from {{ config.source === 'sheet' ? 'community sheet' : config.source }}</span>
            </h3>
            <button v-if="!configEditing" class="cfg-edit-btn" @click="startConfigEdit">
              {{ configHasData ? 'Edit' : 'Add config' }}
            </button>
          </div>

          <div v-if="configLoading" class="cfg-empty">Loading config…</div>

          <!-- View mode -->
          <div v-else-if="!configEditing && configHasData" class="cfg-grid">
            <div v-for="g in configGroups" :key="g.title" class="cfg-group">
              <div class="cfg-group-title">{{ g.title }}</div>
              <template v-for="[label, key] in g.fields" :key="key">
                <div v-if="config.config[key]" class="cfg-row">
                  <span class="cfg-k">{{ label }}</span>
                  <span class="cfg-v">{{ config.config[key] }}</span>
                </div>
              </template>
            </div>
          </div>

          <div v-else-if="!configEditing && !configHasData" class="cfg-empty">
            No config on file. <a href="#" @click.prevent="startConfigEdit">Add yours</a> — sens, mouse, binds, screen.
          </div>

          <!-- Edit mode -->
          <div v-else class="cfg-edit">
            <div class="cfg-grid">
              <div v-for="g in configGroups" :key="g.title" class="cfg-group">
                <div class="cfg-group-title">{{ g.title }}</div>
                <label v-for="[label, key] in g.fields" :key="key" class="cfg-field">
                  <span>{{ label }}</span>
                  <input v-model="configDraft[key]" type="text" :placeholder="label">
                </label>
              </div>
              <div class="cfg-group">
                <div class="cfg-group-title">Location</div>
                <label class="cfg-field"><span>Nationality (e.g. US, SE, PL)</span>
                  <input v-model="configDraft._nationality" type="text" placeholder="country code"></label>
              </div>
            </div>
            <div class="cfg-actions">
              <button class="cfg-save" :disabled="configSaving" @click="saveConfig">
                {{ configSaving ? 'Saving…' : 'Save config' }}
              </button>
              <button class="cfg-cancel" @click="cancelConfigEdit">Cancel</button>
              <span v-if="configSaveErr" class="cfg-err">{{ configSaveErr }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- ── Tab bar (shared chrome with /profile.html) ── -->
      <!-- Overview is this page; other tabs deep-link to the legacy profile.html
           SPA at the matching #tab. Window dropdown sits inline on the right. -->
      <div class="profile-tabbar">
        <div class="profile-tabs">
          <a class="ptab active">Overview</a>
          <a class="ptab" :href="deepHref('trends')">Trends</a>
          <a class="ptab" :href="deepHref('compare')">Compare</a>
          <a class="ptab" :href="deepHref('1on1')">1on1</a>
          <a class="ptab" :href="deepHref('4on4')">4on4</a>
          <a class="ptab" :href="deepHref('2on2')">2on2</a>
          <a class="ptab" :href="deepHref('dmm')">By DMM</a>
          <NuxtLink class="ptab" :to="`/p/${encodeURIComponent(id)}/maps`">Maps</NuxtLink>
          <a class="ptab" :href="deepHref('servers')">Servers</a>
          <a class="ptab" :href="deepHref('opponents')">Rivals</a>
          <a class="ptab" :href="deepHref('recent')">Recent</a>
        </div>
        <select v-model="windowKey" class="window-select">
          <option value="7">Last 7d</option>
          <option value="30">Last 30d</option>
          <option value="90">Last 90d</option>
          <option value="365">Last year</option>
          <option value="all">All time</option>
        </select>
      </div>

      <!-- ── NAV view (default, Mock 5 — large launchpad cards) ── -->
      <!-- Each card links into /profile.html?id=X#TAB. Tabs default to 90d window. -->
      <div v-if="view === 'nav'" class="nav-grid">
        <a class="nav-card" :href="deepHref('1on1')">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Mode breakdown · {{ windowLabel }}</div>
              <div class="nc-title">1on1 duel</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview" v-if="m1on1.matches">
            <strong>{{ fmtNum(m1on1.matches) }}</strong> matches · <strong>{{ fmtPct(m1on1.win_rate) }}</strong> win rate · avg ± <strong>{{ fmtDelta(m1on1.avg_frag_diff) }}</strong>
            <span v-if="m1on1.avg_dmg_given && m1on1.avg_dmg_taken">
              · DDR <strong>{{ (m1on1.avg_dmg_given / m1on1.avg_dmg_taken).toFixed(2) }}</strong>
            </span>
          </div>
          <div class="nc-preview muted" v-else>No 1on1 in last 90 days</div>
          <div class="nc-stats" v-if="m1on1.matches">
            <div class="ks">
              <div class="v">{{ fmtPct(m1on1.lg_accuracy) }}</div>
              <div class="l">LG</div>
              <div v-if="modeDelta('1on1', 'lg_accuracy', { pp: true })" class="d" :class="modeDelta('1on1', 'lg_accuracy', { pp: true }).cls">{{ modeDelta('1on1', 'lg_accuracy', { pp: true }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtPct(m1on1.rl_accuracy) }}</div>
              <div class="l">RL</div>
              <div v-if="modeDelta('1on1', 'rl_accuracy', { pp: true })" class="d" :class="modeDelta('1on1', 'rl_accuracy', { pp: true }).cls">{{ modeDelta('1on1', 'rl_accuracy', { pp: true }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtPct(m1on1.sg_accuracy) }}</div>
              <div class="l">SG</div>
              <div v-if="modeDelta('1on1', 'sg_accuracy', { pp: true })" class="d" :class="modeDelta('1on1', 'sg_accuracy', { pp: true }).cls">{{ modeDelta('1on1', 'sg_accuracy', { pp: true }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtDec(m1on1.avg_ra, 1) }}</div>
              <div class="l">RA/m</div>
              <div v-if="modeDelta('1on1', 'avg_ra')" class="d" :class="modeDelta('1on1', 'avg_ra').cls">{{ modeDelta('1on1', 'avg_ra').str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtNum(Math.round(m1on1.avg_lg_dmg || 0)) }}</div>
              <div class="l">LG dmg/m</div>
              <div v-if="modeDelta('1on1', 'avg_lg_dmg')" class="d" :class="modeDelta('1on1', 'avg_lg_dmg').cls">{{ modeDelta('1on1', 'avg_lg_dmg').str }}</div>
            </div>
          </div>
        </a>

        <a class="nav-card" :href="deepHref('4on4')">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Mode breakdown · {{ windowLabel }}</div>
              <div class="nc-title">4on4 team</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview" v-if="m4on4.matches">
            <strong>{{ fmtNum(m4on4.matches) }}</strong> matches · <strong>{{ fmtPct(m4on4.win_rate) }}</strong> win rate · {{ fmtNum(Math.round(m4on4.avg_dmg_given || 0)) }} dmg/m
          </div>
          <div class="nc-preview muted" v-else>No 4on4 in last 90 days</div>
          <div class="nc-stats" v-if="m4on4.matches">
            <div class="ks">
              <div class="v">{{ fmtNum(Math.round(m4on4.avg_dmg_given || 0)) }}</div>
              <div class="l">Dmg given</div>
              <div v-if="modeDelta('4on4', 'avg_dmg_given')" class="d" :class="modeDelta('4on4', 'avg_dmg_given').cls">{{ modeDelta('4on4', 'avg_dmg_given').str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtNum(Math.round(m4on4.avg_dmg_taken || 0)) }}</div>
              <div class="l">Dmg taken</div>
              <div v-if="modeDelta('4on4', 'avg_dmg_taken', { higherBetter: false })" class="d" :class="modeDelta('4on4', 'avg_dmg_taken', { higherBetter: false }).cls">{{ modeDelta('4on4', 'avg_dmg_taken', { higherBetter: false }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtNum(Math.round(m4on4.avg_dmg_enemy_weapons || 0)) }}</div>
              <div class="l">EWEP</div>
              <div v-if="modeDelta('4on4', 'avg_dmg_enemy_weapons')" class="d" :class="modeDelta('4on4', 'avg_dmg_enemy_weapons').cls">{{ modeDelta('4on4', 'avg_dmg_enemy_weapons').str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtPct(m4on4.lg_accuracy) }}</div>
              <div class="l">LG</div>
              <div v-if="modeDelta('4on4', 'lg_accuracy', { pp: true })" class="d" :class="modeDelta('4on4', 'lg_accuracy', { pp: true }).cls">{{ modeDelta('4on4', 'lg_accuracy', { pp: true }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtPct(m4on4.rl_accuracy) }}</div>
              <div class="l">RL</div>
              <div v-if="modeDelta('4on4', 'rl_accuracy', { pp: true })" class="d" :class="modeDelta('4on4', 'rl_accuracy', { pp: true }).cls">{{ modeDelta('4on4', 'rl_accuracy', { pp: true }).str }}</div>
            </div>
          </div>
        </a>

        <a class="nav-card" :href="deepHref('2on2')">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Mode breakdown · {{ windowLabel }}</div>
              <div class="nc-title">2on2 team</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview" v-if="m2on2.matches">
            <strong>{{ fmtNum(m2on2.matches) }}</strong> matches · <strong>{{ fmtPct(m2on2.win_rate) }}</strong> win rate · avg ± <strong>{{ fmtDelta(m2on2.avg_frag_diff) }}</strong>
          </div>
          <div class="nc-preview muted" v-else>No 2on2 in last 90 days</div>
          <div class="nc-stats" v-if="m2on2.matches">
            <div class="ks">
              <div class="v">{{ fmtNum(Math.round(m2on2.avg_dmg_given || 0)) }}</div>
              <div class="l">Dmg given</div>
              <div v-if="modeDelta('2on2', 'avg_dmg_given')" class="d" :class="modeDelta('2on2', 'avg_dmg_given').cls">{{ modeDelta('2on2', 'avg_dmg_given').str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtNum(Math.round(m2on2.avg_dmg_taken || 0)) }}</div>
              <div class="l">Dmg taken</div>
              <div v-if="modeDelta('2on2', 'avg_dmg_taken', { higherBetter: false })" class="d" :class="modeDelta('2on2', 'avg_dmg_taken', { higherBetter: false }).cls">{{ modeDelta('2on2', 'avg_dmg_taken', { higherBetter: false }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtPct(m2on2.lg_accuracy) }}</div>
              <div class="l">LG</div>
              <div v-if="modeDelta('2on2', 'lg_accuracy', { pp: true })" class="d" :class="modeDelta('2on2', 'lg_accuracy', { pp: true }).cls">{{ modeDelta('2on2', 'lg_accuracy', { pp: true }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtPct(m2on2.rl_accuracy) }}</div>
              <div class="l">RL</div>
              <div v-if="modeDelta('2on2', 'rl_accuracy', { pp: true })" class="d" :class="modeDelta('2on2', 'rl_accuracy', { pp: true }).cls">{{ modeDelta('2on2', 'rl_accuracy', { pp: true }).str }}</div>
            </div>
            <div class="ks">
              <div class="v">{{ fmtDec(m2on2.avg_ra, 1) }}</div>
              <div class="l">RA/m</div>
              <div v-if="modeDelta('2on2', 'avg_ra')" class="d" :class="modeDelta('2on2', 'avg_ra').cls">{{ modeDelta('2on2', 'avg_ra').str }}</div>
            </div>
          </div>
        </a>

        <a class="nav-card" :href="deepHref('trends')">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Time analysis · {{ windowLabel }}</div>
              <div class="nc-title">Trends</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview" v-if="trendsSnapshot.weeks > 0">
            <strong>{{ trendsSnapshot.weeks }}</strong> weeks with matches
            <span v-if="trendsSnapshot.peakWin" class="muted">· peak {{ fmtPct(trendsSnapshot.peakWin) }} WR</span>
          </div>
          <div class="nc-preview muted" v-else>No weekly trend data in this window</div>
          <div class="nc-stats" v-if="trendsSnapshot.weeks > 0">
            <div class="ks">
              <div class="v" :class="trendsSnapshot.winRateDelta.cls">{{ trendsSnapshot.winRateDelta.str }}</div>
              <div class="l">Δ Win rate</div>
            </div>
            <div class="ks">
              <div class="v" :class="trendsSnapshot.lgDelta.cls">{{ trendsSnapshot.lgDelta.str }}</div>
              <div class="l">Δ LG accuracy</div>
            </div>
            <div class="ks">
              <div class="v" :class="trendsSnapshot.fragDiffDelta.cls">{{ trendsSnapshot.fragDiffDelta.str }}</div>
              <div class="l">Δ avg ±frag</div>
            </div>
          </div>
          <!-- Tiny sparkline of frag-diff over the window. Reuses the trend buckets. -->
          <Sparkline v-if="trendsSnapshot.spark.length > 1"
                     :values="trendsSnapshot.spark"
                     :height="36" :width="280" stroke="var(--accent)" />
        </a>

        <NuxtLink class="nav-card" :to="`/p/${encodeURIComponent(id)}/maps`">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Per-map ELO + stats · {{ windowLabel }}</div>
              <div class="nc-title">Maps</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview">
            <span v-if="(w.by_map_1on1 || []).length"><strong>{{ (w.by_map_1on1 || []).length }}</strong> 1on1 maps played</span>
            <span v-else class="muted">No map data</span>
          </div>
          <div class="nc-list nc-list-maps" v-if="(w.by_map_1on1 || []).length">
            <div v-for="m in (w.by_map_1on1 || []).slice(0, 4)" :key="m.bucket" class="row">
              <span class="name">{{ m.bucket }}</span>
              <span class="sub">{{ m.matches }}m</span>
              <span class="rating" :class="mapRating(m.bucket) ? '' : 'muted'">
                {{ mapRating(m.bucket) ? Math.round(mapRating(m.bucket)) : '—' }}
              </span>
              <span class="pct" :class="(m.win_rate || 0) >= 0.5 ? 'win' : 'loss'">{{ fmtPct(m.win_rate) }}</span>
            </div>
          </div>
        </NuxtLink>

        <a class="nav-card" :href="deepHref('opponents')">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Head-to-head · {{ windowLabel }}</div>
              <div class="nc-title">Rivals</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview">
            <span v-if="(w.head_to_head_1on1 || []).length"><strong>{{ (w.head_to_head_1on1 || []).length }}</strong> 1on1 opponents</span>
            <span v-else class="muted">No opponent data</span>
          </div>
          <div class="nc-list" v-if="(w.head_to_head_1on1 || []).length">
            <div v-for="o in (w.head_to_head_1on1 || []).slice(0, 4)" :key="o.opponent" class="row">
              <NuxtLink v-if="o.opponent_canonical_id" :to="`/p/${encodeURIComponent(o.opponent_canonical_id)}`"
                        class="name name-link" @click.stop>{{ o.opponent }}</NuxtLink>
              <span v-else class="name">{{ o.opponent }}</span>
              <span class="sub">{{ o.wins }}–{{ o.losses }}</span>
              <span class="pct" :class="(o.win_rate || 0) >= 0.5 ? 'win' : 'loss'">{{ fmtPct(o.win_rate) }}</span>
              <span v-if="oppDelta(o.opponent)" class="d-inline" :class="oppDelta(o.opponent).cls">{{ oppDelta(o.opponent).str }}</span>
              <span v-else class="d-inline muted">·</span>
            </div>
          </div>
        </a>

        <a class="nav-card" :href="deepHref('compare')">
          <div class="nc-head">
            <div>
              <div class="nc-sub">Period comparison · {{ windowLabel }}</div>
              <div class="nc-title">Compare</div>
            </div>
            <div class="nc-arrow">→</div>
          </div>
          <div class="nc-preview" v-if="hasPrior">
            Current {{ windowLabel }} vs <strong>previous {{ windowLabel }}</strong>
          </div>
          <div class="nc-preview muted" v-else>No prior period to compare against</div>
          <div class="nc-stats" v-if="hasPrior">
            <div class="ks">
              <div class="v" :class="compareCardDelta('win_rate', {pp: true}).cls">{{ compareCardDelta('win_rate', {pp: true}).str }}</div>
              <div class="l">Win rate</div>
            </div>
            <div class="ks">
              <div class="v" :class="compareCardDelta('avg_frag_diff').cls">{{ compareCardDelta('avg_frag_diff').str }}</div>
              <div class="l">Avg ±frag</div>
            </div>
            <div class="ks">
              <div class="v" :class="compareCardDelta('lg_accuracy', {pp: true}).cls">{{ compareCardDelta('lg_accuracy', {pp: true}).str }}</div>
              <div class="l">LG</div>
            </div>
            <div class="ks">
              <div class="v" :class="compareCardDelta('avg_dmg_given').cls">{{ compareCardDelta('avg_dmg_given').str }}</div>
              <div class="l">Dmg given</div>
            </div>
          </div>
        </a>
      </div>

      <!-- ── METRICS view (Mock 3 dense grid) ── -->
      <div v-else class="metrics">
        <div class="section-h">
          <h2>1on1 · last {{ windowKey === 'all' ? 'all time' : windowKey + 'd' }}</h2>
          <a :href="deepHref('1on1')">Full breakdown →</a>
        </div>
        <div class="metric-grid">
          <div class="metric" v-for="m in metricDefs" :key="m.label">
            <div class="m-head">
              <div>
                <div class="label">{{ m.label }}</div>
                <div class="v">{{ m.fmt(m1on1[m.key]) }}</div>
              </div>
              <span class="delta" v-if="deltaInfo(m).str" :class="deltaInfo(m).cls">{{ deltaInfo(m).str }}</span>
            </div>
            <Sparkline :data="sparkData(m.key)" class="m-spark" />
            <div class="m-foot">vs prior {{ windowKey === 'all' ? '?' : windowKey + 'd' }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 32px 40px 80px; }
.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }

.hero {
  display: flex; align-items: center; gap: 24px; margin-bottom: 28px;
}
.hero .avatar {
  width: 80px; height: 80px; border-radius: 16px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: flex; align-items: center; justify-content: center;
  font-size: 36px; font-weight: 900; color: var(--bg);
  box-shadow: 0 10px 28px rgba(20,230,192,0.20);
}
.hero .id { flex: 1; min-width: 0; }
.hero .id h1 { margin: 0; font-size: 38px; font-weight: 800; letter-spacing: -0.02em; }
.hero .id .sub { color: var(--fg-2); font-size: 13px; margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap; }
.hero .id .sub .sep { color: var(--fg-3); }
.hero-actions { display: flex; gap: 8px; }

.pill-group {
  display: inline-flex; background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 3px; gap: 2px;
}
.pill-group button {
  background: transparent; border: 0; color: var(--fg-2);
  padding: 6px 14px; border-radius: 5px; cursor: pointer;
  font-family: inherit; font-size: 12px; font-weight: 600;
}
.pill-group button:hover { color: var(--fg); background: var(--panel-2); }
.pill-group button.active { background: var(--accent); color: var(--bg); }

/* Rating row */
.rating-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.rating-tile {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 18px; min-width: 180px;
  display: flex; flex-direction: column; gap: 4px;
}
.rt-label .chip {
  display: inline-flex; align-items: center;
  padding: 3px 9px; border-radius: 999px;
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
}
.chip-1on1 { background: rgba(20,230,192,0.12); color: var(--accent); }
.chip-4on4 { background: rgba(34,197,94,0.12); color: var(--win); }
.chip-2on2 { background: rgba(245,158,11,0.12); color: var(--draw); }
.rt-val {
  font-size: 28px; font-weight: 800; letter-spacing: -0.02em; line-height: 1;
  color: var(--accent); font-variant-numeric: tabular-nums; margin-top: 4px;
}
.rt-val.muted { color: var(--fg-3); }
.rt-sigma { color: var(--fg-3); font-size: 11px; font-family: 'JetBrains Mono', monospace; }
.rt-meta { color: var(--fg-2); font-size: 11px; }
.rt-tier {
  display: inline-block; margin-top: 6px; padding: 3px 9px; border-radius: 999px;
  border: 1px solid; font-size: 10px; font-weight: 700;
  letter-spacing: 0.05em; text-transform: uppercase; align-self: flex-start;
}
.rating-tile { cursor: pointer; transition: border-color 0.12s; }
.rating-tile:hover { border-color: var(--accent); }
.rating-tile-active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }

.rh-section {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 18px 18px; margin-bottom: 24px;
}
.rh-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.rh-head h3 { margin: 0; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--fg-2); }
.rh-head .rh-sub { color: var(--fg-3); font-weight: 400; }
.rh-head .rh-hint { color: var(--fg-3); font-size: 11px; }
.rh-empty { color: var(--fg-3); padding: 30px; text-align: center; font-size: 13px; }

/* Config Profile card */
.cfg-section { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 18px 18px; margin-bottom: 24px; }
.cfg-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.cfg-head h3 { margin: 0; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--fg-2); }
.cfg-head .cfg-sub { color: var(--fg-3); font-weight: 400; text-transform: none; letter-spacing: 0; }
.cfg-edit-btn { background: var(--panel-2); border: 1px solid var(--border); color: var(--accent); padding: 5px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; }
.cfg-edit-btn:hover { border-color: var(--accent); }
.cfg-empty { color: var(--fg-3); padding: 20px; text-align: center; font-size: 13px; }
.cfg-empty a { color: var(--accent); }
.cfg-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.cfg-group-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--fg-3); font-weight: 700; margin-bottom: 6px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.cfg-row { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; font-size: 13px; }
.cfg-k { color: var(--fg-2); }
.cfg-v { color: var(--fg); font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; }
.cfg-field { display: flex; flex-direction: column; gap: 3px; margin-bottom: 7px; font-size: 11px; color: var(--fg-3); }
.cfg-field input { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 5px 8px; border-radius: 5px; font-size: 13px; font-family: inherit; }
.cfg-field input:focus { outline: none; border-color: var(--accent); }
.cfg-actions { display: flex; gap: 10px; align-items: center; margin-top: 14px; }
.cfg-save { background: var(--accent); color: var(--bg); border: 0; padding: 7px 18px; border-radius: 6px; font-weight: 700; cursor: pointer; font-size: 13px; }
.cfg-save:disabled { opacity: 0.6; cursor: default; }
.cfg-cancel { background: transparent; border: 1px solid var(--border); color: var(--fg-2); padding: 7px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.cfg-err { color: var(--loss, #ef4444); font-size: 12px; }

/* Controls */
.controls { display: flex; gap: 12px; align-items: center; margin-bottom: 24px; flex-wrap: wrap; }

/* Profile tabbar — shared chrome with /profile.html so Overview lives under the
   same nav strip as the deep-dive tabs. Window dropdown inline on the right. */
.profile-tabbar {
  display: flex; align-items: center; gap: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 24px; padding-bottom: 0;
}
.profile-tabs { display: flex; gap: 0; flex: 1; flex-wrap: wrap; }
.ptab {
  padding: 10px 14px; color: var(--fg-2); font-size: 13px; font-weight: 500;
  text-decoration: none; border-bottom: 2px solid transparent; margin-bottom: -1px;
  cursor: pointer;
}
.ptab:hover { color: var(--fg); }
.ptab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.window-select {
  background: rgba(20, 230, 192, 0.08);
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 7px 14px; border-radius: 999px;
  font-family: inherit; font-size: 13px;
  font-weight: 700; letter-spacing: 0.01em;
  cursor: pointer;
  /* Native arrow styling varies by OS — replace with our own teal chevron */
  appearance: none; -webkit-appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, var(--accent) 50%),
                    linear-gradient(135deg, var(--accent) 50%, transparent 50%);
  background-position: calc(100% - 16px) 50%, calc(100% - 11px) 50%;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
  padding-right: 28px;
  transition: background-color 0.12s, box-shadow 0.12s;
}
.window-select:hover { background-color: rgba(20, 230, 192, 0.15); box-shadow: 0 0 0 3px rgba(20, 230, 192, 0.08); }
.window-select:focus { outline: none; box-shadow: 0 0 0 3px rgba(20, 230, 192, 0.18); }
.window-select option { background: var(--panel-2); color: var(--fg); font-weight: 600; }
.ctl-label {
  color: var(--fg-3); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 700;
}

/* Nav cards (Mock 5) */
.nav-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;
  /* All cards stretch to the same height (default grid behavior). Maps/Rivals
     are capped at 4 list items so their natural height matches the mode cards. */
}
@media (max-width: 900px) { .nav-grid { grid-template-columns: 1fr; } }
.nav-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 16px; padding: 28px;
  text-decoration: none; color: inherit;
  transition: all 0.18s; display: flex; flex-direction: column; gap: 16px;
  min-height: 200px; position: relative; overflow: hidden;
}
.nav-card:hover { border-color: var(--accent); transform: translateY(-3px); }
.nc-head {
  display: flex; align-items: center; justify-content: space-between;
}
.nc-title {
  font-size: 22px; font-weight: 800; letter-spacing: -0.02em;
}
.nc-arrow {
  font-size: 22px; color: var(--fg-3);
  transition: all 0.18s;
}
.nav-card:hover .nc-arrow { color: var(--accent); transform: translateX(4px); }
.nc-sub {
  color: var(--fg-3); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 700;
}
.nc-preview {
  flex: 1; color: var(--fg-2); font-size: 14px; line-height: 1.6;
}
.nc-preview strong { color: var(--accent); font-weight: 700; font-variant-numeric: tabular-nums; }
.nc-preview.muted strong, .muted { color: var(--fg-3); }
.nc-stats {
  display: flex; gap: 18px; margin-top: 4px; flex-wrap: wrap;
}
.nc-stats .ks { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.nc-stats .ks .v { font-size: 20px; font-weight: 800; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
.nc-stats .ks .l { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--fg-3); font-weight: 700; white-space: nowrap; }
.nc-stats .ks .d {
  font-size: 11px; font-weight: 700; margin-top: 4px; font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.nc-stats .ks .d.up { color: var(--win); }
.nc-stats .ks .d.down { color: var(--loss); }

/* Compact list (used for top-6 maps / opponents) */
.nc-list {
  display: flex; flex-direction: column;
}
.nc-list .row {
  display: grid; grid-template-columns: 1fr auto auto;
  gap: 12px; align-items: baseline;
  padding: 6px 0; border-top: 1px solid var(--border);
  font-size: 13px;
}
.nc-list .row:first-child { border-top: 0; padding-top: 8px; }
.nc-list .row .name { font-weight: 600; }
.nc-list .row .name-link {
  color: inherit; text-decoration: none;
  border-bottom: 1px dotted transparent; transition: border-color 0.12s, color 0.12s;
}
.nc-list .row .name-link:hover { color: var(--accent); border-bottom-color: var(--accent); }
.nc-list .row .sub { color: var(--fg-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.nc-list .row .pct { font-weight: 700; font-size: 13px; font-variant-numeric: tabular-nums; min-width: 48px; text-align: right; }
.nc-list .row .pct.win { color: var(--win); }
.nc-list .row .pct.loss { color: var(--loss); }
.nc-list .row .d-inline {
  font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums;
  min-width: 56px; text-align: right; white-space: nowrap;
}
.nc-list .row .d-inline.up { color: var(--win); }
.nc-list .row .d-inline.down { color: var(--loss); }
.nc-list .row .d-inline.muted { color: var(--fg-3); }
/* List row grid expanded to accommodate the trailing delta column */
.nc-list .row { grid-template-columns: 1fr auto auto auto; }
/* Maps list swaps the trailing delta for a per-map ELO rating column */
.nc-list-maps .row { grid-template-columns: 1fr auto auto auto; }
.nc-list-maps .row .rating {
  font-weight: 700; font-size: 13px; font-variant-numeric: tabular-nums;
  color: var(--accent); min-width: 52px; text-align: right;
}
.nc-list-maps .row .rating.muted { color: var(--fg-3); font-weight: 500; }

/* Metrics view (Mock 3) */
.metrics .section-h {
  display: flex; align-items: baseline; justify-content: space-between;
  margin: 4px 0 12px;
}
.metrics .section-h h2 {
  margin: 0; font-size: 14px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em; color: var(--fg-2);
}
.metrics .section-h a {
  color: var(--accent); text-decoration: none; font-size: 12px; font-weight: 600;
}
.metric-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px;
}
.metric {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px;
  transition: all 0.12s;
}
.metric:hover { border-color: var(--border-2); }
.metric .m-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 8px;
}
.metric .label {
  color: var(--fg-3); font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 700;
}
.metric .v {
  font-size: 22px; font-weight: 800; margin-top: 4px;
  font-variant-numeric: tabular-nums; line-height: 1.1;
}
.metric .delta {
  font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.metric .delta.up { color: var(--win); }
.metric .delta.down { color: var(--loss); }
.metric .delta.flat { color: var(--fg-3); }
.metric .m-spark { margin-top: 8px; }
.metric .m-foot {
  margin-top: 6px;
  color: var(--fg-3); font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
}
</style>

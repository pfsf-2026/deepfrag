<script setup>
/**
 * DeepFrag Admin — Wave 1 MVP.
 *
 * Layout: left sidebar (Design 2) + right pane that swaps based on activeSection.
 * Auth: SYNC_SECRET in localStorage. Entered once via the prompt overlay.
 *
 * Sections live as section-id strings; only 'dashboard' and 'players' have
 * real content in Wave 1 — the rest are placeholders that explain what they'll
 * become.
 */

definePageMeta({ layout: false })   // bypass top nav — admin has its own chrome

const config = useRuntimeConfig()
const apiBase = config.public.apiBase || ''

const authed = ref(false)
const tokenInput = ref('')
const tokenError = ref('')

const status = ref(null)            // /api/admin/status payload
const statusError = ref('')
const statusLoading = ref(false)

const players = ref([])             // populated when players section activated
const playersLoading = ref(false)
const selectedPlayer = ref(null)
const playerSearch = ref('')
const playerRegion = ref('')
const playerDiv = ref('')
const playerActivity = ref('all')

const activeSection = ref('dashboard')
const eventLog = ref([])
const eventLogMax = 200

const schedulerToggling = ref(false)
const rerateState = ref('idle')     // 'idle' | 'confirming' | 'running' | 'done' | 'error'
const rerateResult = ref(null)

const sections = [
  { group: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'activity', label: 'Activity log' }
  ]},
  { group: 'Data', items: [
    { id: 'players', label: 'Players' },
    { id: 'matches', label: 'Matches' },
    { id: 'servers', label: 'Servers' },
    { id: 'canon', label: 'Canonicalize queue' },
    { id: 'ratings', label: 'Ratings' }
  ]},
  { group: 'Operations', items: [
    { id: 'scheduler', label: 'Scheduler' },
    { id: 'rerate', label: 'Re-rate' },
    { id: 'costs', label: 'Costs' },
    { id: 'deploys', label: 'Deploy log' }
  ]},
  { group: 'Federation', items: [
    { id: 'users', label: 'Users' },
    { id: 'oauth', label: 'OAuth providers' },
    { id: 'tokens', label: 'API tokens' }
  ]}
]

// ─── Auth ────────────────────────────────────────────────────────────────
onMounted(() => {
  const t = localStorage.getItem('deepfrag_admin_token')
  if (t) authed.value = true
  if (authed.value) {
    loadStatus()
    loadActivity()
    loadDeploys()    // dashboard "Latest deploys" card
  }
})

function submitToken() {
  if (!tokenInput.value) return
  localStorage.setItem('deepfrag_admin_token', tokenInput.value)
  tokenError.value = ''
  authed.value = true
  loadStatus()
}

function logout() {
  localStorage.removeItem('deepfrag_admin_token')
  authed.value = false
}

function token() { return localStorage.getItem('deepfrag_admin_token') || '' }
function adminHeaders() { return { Authorization: `Bearer ${token()}` } }

// ─── Status / dashboard ──────────────────────────────────────────────────
async function loadStatus() {
  statusLoading.value = true
  statusError.value = ''
  try {
    const r = await $fetch(`${apiBase}/api/admin/status`, { headers: adminHeaders() })
    status.value = r
    pushEvent('info', 'STATUS', `loaded · ${r.stats.matches.toLocaleString()} matches · scheduler ${r.scheduler.state}`)
  } catch (e) {
    statusError.value = e?.data?.detail || e?.message || 'Failed to load'
    if (e?.status === 401) { authed.value = false; localStorage.removeItem('deepfrag_admin_token') }
  } finally {
    statusLoading.value = false
  }
}

const deploys = ref([])
const deploysLoading = ref(false)
const deploysError = ref('')
const activeRevision = ref(null)
async function loadDeploys() {
  deploysLoading.value = true
  deploysError.value = ''
  try {
    const r = await $fetch(`${apiBase}/api/admin/deploys?limit=50`, { headers: adminHeaders() })
    deploys.value = r.deploys || []
    activeRevision.value = r.active_revision
  } catch (e) {
    deploysError.value = e?.data?.detail || e?.message || 'Failed to load'
  } finally {
    deploysLoading.value = false
  }
}

async function loadActivity() {
  try {
    const r = await $fetch(`${apiBase}/api/admin/activity?limit=40`, { headers: adminHeaders() })
    // Replace prior backend-sourced events; keep any session events at the front
    const sessionEvents = eventLog.value.filter(e => !e.fromBackend)
    const backendEvents = (r.events || []).map(e => ({
      ts: fmtTimeET(e.ts),
      level: e.level,
      tag: e.tag,
      msg: e.msg,
      fromBackend: true,
    }))
    eventLog.value = [...sessionEvents, ...backendEvents].slice(0, eventLogMax)
  } catch (e) {
    // Silent — feed just stays empty
  }
}

function pushEvent(level, tag, msg) {
  eventLog.value.unshift({ ts: fmtTimeET(new Date()), level, tag, msg })
  if (eventLog.value.length > eventLogMax) eventLog.value = eventLog.value.slice(0, eventLogMax)
}

// ─── Scheduler pause/resume ──────────────────────────────────────────────
async function toggleScheduler() {
  if (!status.value) return
  schedulerToggling.value = true
  const action = status.value.scheduler.state === 'enabled' ? 'pause' : 'resume'
  try {
    const r = await $fetch(`${apiBase}/api/admin/scheduler/${action}`, {
      method: 'POST', headers: adminHeaders()
    })
    pushEvent('ok', 'SCHED', `${action} → state=${r.state}`)
    await loadStatus()
  } catch (e) {
    pushEvent('err', 'SCHED', `${action} failed: ${e?.data?.detail || e?.message}`)
  } finally {
    schedulerToggling.value = false
  }
}

// ─── Sync trigger ────────────────────────────────────────────────────────
async function triggerSync() {
  pushEvent('info', 'SYNC', 'manual trigger…')
  try {
    const r = await $fetch(`${apiBase}/api/admin/sync?skip_rate=false`, {
      method: 'POST', headers: adminHeaders(), timeout: 1200000
    })
    const totalMatches = r.steps?.find(s => s.step === 'sync_all_recent')?.matches_fetched ?? 0
    pushEvent('ok', 'SYNC', `done · ${totalMatches} new matches · ${r.steps.length} steps`)
    await loadStatus()
  } catch (e) {
    pushEvent('err', 'SYNC', e?.data?.detail || e?.message || 'failed')
  }
}

// ─── Full re-rate ────────────────────────────────────────────────────────
function startRerate() {
  rerateState.value = 'confirming'
}
async function confirmRerate() {
  rerateState.value = 'running'
  rerateResult.value = null
  pushEvent('warn', 'RERATE', 'full 1on1 re-rate started (3-8 min)…')
  try {
    const r = await $fetch(
      `${apiBase}/api/admin/rerate?confirm=I-understand-this-wipes-ratings`,
      { method: 'POST', headers: adminHeaders(), timeout: 1300000 }
    )
    rerateResult.value = r
    rerateState.value = 'done'
    pushEvent('ok', 'RERATE', `done · rate rc=${r.rerate.returncode} · invariants rc=${r.invariants.returncode}`)
    await loadStatus()
  } catch (e) {
    rerateState.value = 'error'
    rerateResult.value = { error: e?.data?.detail || e?.message || 'failed' }
    pushEvent('err', 'RERATE', rerateResult.value.error)
  }
}
function cancelRerate() { rerateState.value = 'idle' }

// ─── Players section ─────────────────────────────────────────────────────
async function loadPlayers() {
  if (players.value.length) return
  playersLoading.value = true
  try {
    const r = await $fetch(`${apiBase}/api/rankings?mode=1on1&min_matches=10&limit=2000`)
    players.value = r.players || []
  } catch (e) {
    pushEvent('err', 'PLAYERS', e?.message || 'load failed')
  } finally {
    playersLoading.value = false
  }
}

watch(activeSection, (s) => {
  if (s === 'players') loadPlayers()
  if (s === 'deploys') loadDeploys()
  if (s === 'matches') loadMatches()
})

// ─── Matches tab: Region Switcher ─────────────────────────────────────────
const matchesData = ref(null)
const matchesLoading = ref(false)
const matchesError = ref('')
const matchesRegion = ref('all')
const matchesWindow = ref('30')
const matchesMode = ref('all')

async function loadMatches() {
  matchesLoading.value = true
  matchesError.value = ''
  try {
    const params = new URLSearchParams({
      region: matchesRegion.value,
      window: matchesWindow.value,
      mode: matchesMode.value,
    })
    matchesData.value = await $fetch(`${apiBase}/api/admin/matches/by-region?${params}`,
      { headers: adminHeaders() })
  } catch (e) {
    matchesError.value = e?.data?.detail || e?.message || 'fetch failed'
    pushEvent('err', 'MATCHES', matchesError.value)
  } finally {
    matchesLoading.value = false
  }
}

// Re-load whenever any filter changes (debounced via Vue's reactivity batching).
watch([matchesRegion, matchesWindow, matchesMode], () => {
  if (activeSection.value === 'matches') loadMatches()
})

// Pretty 12h labels for the heatmap axis without bringing in a TZ lib.
const HEAT_HOUR_LABELS = ['00', '06', '12', '18', '23']

const playersFiltered = computed(() => {
  let list = players.value
  if (playerRegion.value) list = list.filter(p => p.region === playerRegion.value)
  if (playerDiv.value) list = list.filter(p => p.tier?.slug === playerDiv.value)
  if (playerActivity.value === '90') list = list.filter(p => p.active_90d)
  if (playerSearch.value) {
    const q = playerSearch.value.toLowerCase()
    list = list.filter(p => (p.display || '').toLowerCase().includes(q)
                          || p.canonical_id.toLowerCase().includes(q))
  }
  return list
})

const playerDetail = ref(null)
const playerDetailLoading = ref(false)
async function selectPlayer(p) {
  selectedPlayer.value = p
  playerDetail.value = null
  playerDetailLoading.value = true
  try {
    playerDetail.value = await $fetch(
      `${apiBase}/api/admin/players/${encodeURIComponent(p.canonical_id)}`,
      { headers: adminHeaders() }
    )
  } catch (e) {
    pushEvent('err', 'PLAYER', `detail fetch failed: ${e?.data?.detail || e?.message}`)
  } finally {
    playerDetailLoading.value = false
  }
}
function closeInspector() { selectedPlayer.value = null; playerDetail.value = null }

// Hotkeys removed 2026-05-27 — conflicted with macOS system shortcuts
// (⌘S = save page, ⌘R = reload, etc). Buttons still work via click.

useHead({ title: 'Admin · DeepFrag' })

function fmtPct(v) { return v == null ? '—' : (v * 100).toFixed(0) + '%' }
// All admin times render in US Eastern regardless of viewer locale — Peter is
// the sole admin and lives in ET, and consistent timestamps across the UI
// make the activity + deploy feeds easier to scan.
const ET_TZ = 'America/New_York'
function fmtDate(s) {
  if (!s) return '—'
  return new Date(s).toLocaleString('en-US', {
    timeZone: ET_TZ,
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }) + ' ET'
}
function fmtTimeET(s) {
  if (!s) return ''
  return new Date(s).toLocaleTimeString('en-US', {
    timeZone: ET_TZ, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  })
}
// Status mapping covers both Cloud Run (CONDITION_SUCCEEDED/FAILED/UNKNOWN)
// and Cloudflare Pages (success/failure/active) so the same badge component
// works for both deploy sources.
function isOkStatus(s) { return s === 'CONDITION_SUCCEEDED' || s === 'success' }
function isErrStatus(s) { return s === 'CONDITION_FAILED' || s === 'failure' }
function shortStatus(s) {
  if (!s) return '—'
  // Normalize CF Pages tense (success/failure) to match Cloud Run (succeeded/failed)
  // so both sources read consistently in the badge.
  const lower = s.replace('CONDITION_', '').toLowerCase()
  if (lower === 'success') return 'succeeded'
  if (lower === 'failure') return 'failed'
  return lower
}
</script>

<template>
  <div class="admin-shell">
    <!-- AUTH GATE -->
    <div v-if="!authed" class="auth-gate">
      <div class="auth-card">
        <h1>DeepFrag Admin</h1>
        <p>Enter the admin token to continue.</p>
        <input v-model="tokenInput" type="password" placeholder="SYNC_SECRET" @keyup.enter="submitToken">
        <button @click="submitToken">Authenticate</button>
        <p v-if="tokenError" class="err">{{ tokenError }}</p>
      </div>
    </div>

    <!-- MAIN ADMIN UI -->
    <div v-else class="layout">
      <!-- LEFT SIDEBAR -->
      <aside class="rail">
        <div class="brand">
          <span class="dot" />
          <span class="name">DeepFrag</span>
          <span class="admin-pill">Admin</span>
        </div>

        <div v-for="g in sections" :key="g.group" class="group">
          <h4>{{ g.group }}</h4>
          <div v-for="it in g.items" :key="it.id"
               class="nav-item"
               :class="{ active: activeSection === it.id }"
               @click="activeSection = it.id">
            <span>{{ it.label }}</span>
            <!-- Scheduler nav item gets the inline on/off pill -->
            <span v-if="it.id === 'scheduler' && status" class="sched-pill"
                  :class="status.scheduler.state === 'enabled' ? 'on' : 'off'"
                  @click.stop="toggleScheduler"
                  :title="`Click to ${status.scheduler.state === 'enabled' ? 'pause' : 'resume'} scheduler`">
              <span class="d" />
              {{ status.scheduler.state === 'enabled' ? 'on' : 'off' }}
            </span>
          </div>
        </div>

        <div class="rail-footer">
          <div v-if="status">rev {{ (status.api_revision || '').replace('deepfrag-api-', '') }}</div>
          <a class="logout" @click="logout">Sign out</a>
        </div>
      </aside>

      <!-- RIGHT PANE -->
      <main class="pane">
        <!-- DASHBOARD -->
        <template v-if="activeSection === 'dashboard'">
          <div class="pane-head">
            <div>
              <h2>Dashboard</h2>
              <div class="scope">live status · refreshed {{ status?.now ? fmtDate(status.now) : '—' }}</div>
            </div>
            <div class="actions">
              <button class="btn" @click="loadStatus" :disabled="statusLoading">⟳ Refresh</button>
              <button class="btn ghost" @click="triggerSync">Trigger sync</button>
              <button class="btn warn" @click="startRerate">Full re-rate</button>
            </div>
          </div>

          <div v-if="statusError" class="placeholder err">{{ statusError }}</div>
          <div v-else-if="statusLoading && !status" class="placeholder">Loading status…</div>
          <template v-else-if="status">
            <!-- Numbers strip -->
            <div class="num-strip">
              <div class="nt"><div class="l">Matches</div><div class="v brand">{{ status.stats.matches.toLocaleString() }}</div></div>
              <div class="nt"><div class="l">Rated 1on1</div><div class="v">{{ status.stats.rated_1on1.toLocaleString() }}</div></div>
              <div class="nt"><div class="l">Servers</div><div class="v">{{ status.stats.servers }} <span class="muted">/ {{ status.stats.servers_live }} live</span></div></div>
              <div class="nt"><div class="l">Canonical players</div><div class="v">{{ status.stats.canonical_players.toLocaleString() }}</div></div>
              <div class="nt"><div class="l">Last match</div><div class="v small">{{ fmtDate(status.stats.last_match_date) }}</div></div>
            </div>

            <!-- Live activity + latest deploys, side-by-side -->
            <div class="dash-grid">
              <div class="card">
                <h3>Live activity <span class="meta">{{ eventLog.length }} events</span></h3>
                <div class="feed">
                  <div v-if="!eventLog.length" class="muted center">No events yet. Trigger an action to see it here.</div>
                  <div v-for="(e, i) in eventLog" :key="i" class="line">
                    <span class="ts">{{ e.ts }}</span>
                    <span :class="['level', e.level]">{{ e.tag }}</span>
                    <span class="msg">{{ e.msg }}</span>
                  </div>
                </div>
              </div>

              <div class="card">
                <h3>Latest deploys
                  <span class="meta">
                    <a class="link" @click="activeSection = 'deploys'">view all →</a>
                  </span>
                </h3>
                <div v-if="deploysLoading && !deploys.length" class="muted center" style="padding:20px 0;">Loading…</div>
                <div v-else-if="deploysError" class="muted center" style="padding:20px 0; color: var(--loss);">{{ deploysError }}</div>
                <div v-else-if="!deploys.length" class="muted center" style="padding:20px 0;">No revisions found.</div>
                <div v-else class="feed">
                  <div v-for="d in deploys.slice(0, 8)" :key="d.name" class="line deploy-line"
                       :class="{ active: d.active }">
                    <span class="ts">{{ fmtTimeET(d.create_time) }}</span>
                    <span :class="['level', d.source === 'api' ? 'info' : 'ok']" style="min-width: 32px; text-align: center;">
                      {{ d.source === 'api' ? 'API' : 'Web' }}
                    </span>
                    <span class="msg">
                      <span class="rev-name">{{ d.name.replace('deepfrag-api-', '') }}</span>
                      <span v-if="d.active" class="muted">· LIVE</span>
                      <span v-else-if="d.traffic_percent" class="muted">· {{ d.traffic_percent }}%</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Re-rate confirmation modal -->
          <div v-if="rerateState !== 'idle'" class="modal-bg" @click.self="rerateState === 'confirming' && cancelRerate()">
            <div class="modal">
              <template v-if="rerateState === 'confirming'">
                <h3>Re-rate every 1on1 row?</h3>
                <p>This wipes the <code>ratings</code> table for mode=1on1 (all map buckets) and rebuilds from scratch by re-walking 158k matches.</p>
                <p>Takes ~3–8 minutes. The site won't break, but ratings will be transiently stale during the rebuild.</p>
                <p><strong>Only do this when:</strong> the rating algorithm changed, you just fixed a rate.py bug, or invariants are failing.</p>
                <div class="modal-actions">
                  <button class="btn ghost" @click="cancelRerate">Cancel</button>
                  <button class="btn warn" @click="confirmRerate">Yes, re-rate now</button>
                </div>
              </template>
              <template v-else-if="rerateState === 'running'">
                <h3>Re-rating…</h3>
                <p>Walking all 1on1 matches. Hold tight — this takes 3-8 minutes. Live events will appear in the feed.</p>
                <div class="spinner">⟳</div>
              </template>
              <template v-else-if="rerateState === 'done'">
                <h3>Re-rate complete</h3>
                <pre>{{ rerateResult }}</pre>
                <button class="btn" @click="cancelRerate">Close</button>
              </template>
              <template v-else-if="rerateState === 'error'">
                <h3>Re-rate failed</h3>
                <pre>{{ rerateResult }}</pre>
                <button class="btn" @click="cancelRerate">Close</button>
              </template>
            </div>
          </div>
        </template>

        <!-- PLAYERS — Design 4 inspector pattern -->
        <template v-else-if="activeSection === 'players'">
          <div class="pane-head">
            <div>
              <h2>Players</h2>
              <div class="scope">{{ players.length.toLocaleString() }} rated · 1on1</div>
            </div>
          </div>

          <div class="players-toolbar">
            <input v-model="playerSearch" placeholder="Search by name or canonical_id…" class="dd search-left">
            <div class="filter-right">
              <select v-model="playerRegion" class="dd">
                <option value="">All regions</option>
                <option v-for="r in ['EU','NA','SA','OC','AS-AF']" :key="r" :value="r">{{ r }}</option>
              </select>
              <select v-model="playerDiv" class="dd">
                <option value="">All divs</option>
                <option v-for="d in ['div0','div1','div2','div3','div4']" :key="d" :value="d">{{ d.replace('div', 'Div ') }}</option>
              </select>
              <select v-model="playerActivity" class="dd">
                <option value="all">All time</option>
                <option value="90">Active 90d</option>
              </select>
              <span class="count">{{ playersFiltered.length }} / {{ players.length }}</span>
            </div>
          </div>

          <div class="players-grid">
            <div class="players-table">
              <table>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Region</th>
                    <th>Div</th>
                    <th class="num">Cons</th>
                    <th class="num">Matches</th>
                    <th class="num">DDR</th>
                    <th>Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in playersFiltered.slice(0, 500)" :key="p.canonical_id"
                      :class="{selected: selectedPlayer?.canonical_id === p.canonical_id}"
                      @click="selectPlayer(p)">
                    <td>{{ p.display }}</td>
                    <td>{{ p.region || '—' }}</td>
                    <td><span v-if="p.tier" class="badge" :style="{ color: p.tier.color, borderColor: p.tier.color, background: p.tier.color + '14' }">{{ p.tier.name }}</span></td>
                    <td class="num">{{ Math.round(p.conservative) }}</td>
                    <td class="num">{{ p.matches.toLocaleString() }}</td>
                    <td class="num">{{ p.avg_ddr ?? '—' }}</td>
                    <td class="muted">{{ String(p.last_match || '').slice(0, 10) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Inspector slide-in — richer detail from /api/admin/players/{id} -->
            <div v-if="selectedPlayer" class="inspector">
              <div class="insp-head">
                <h3>{{ selectedPlayer.display }}</h3>
                <button class="x" @click="closeInspector">✕</button>
              </div>
              <div v-if="playerDetailLoading" class="muted center" style="padding: 20px 0;">Loading detail…</div>
              <template v-else-if="playerDetail">
                <div class="insp-section-h">Identity</div>
                <div class="kv">
                  <span class="k">canonical_id</span><span class="v">{{ playerDetail.canonical_id }}</span>
                  <span class="k">display</span><span class="v">{{ playerDetail.display }}</span>
                  <span class="k">login</span><span class="v">{{ playerDetail.login || '—' }}</span>
                  <span class="k">region</span><span class="v">{{ playerDetail.region || '—' }}<span v-if="playerDetail.region_confidence" class="muted"> · conf {{ Math.round(playerDetail.region_confidence * 100) }}%</span></span>
                  <span class="k">created</span><span class="v">{{ String(playerDetail.created_at || '').slice(0, 10) }}</span>
                </div>

                <div class="insp-section-h">Career</div>
                <div class="kv">
                  <span class="k">hub matches</span><span class="v brand">{{ (playerDetail.career.matches || 0).toLocaleString() }}</span>
                  <span class="k">first match</span><span class="v">{{ String(playerDetail.career.first_match || '').slice(0, 10) }}</span>
                  <span class="k">last match</span><span class="v">{{ String(playerDetail.career.last_match || '').slice(0, 10) }}</span>
                  <span class="k">by mode</span><span class="v">{{ playerDetail.career.matches_1on1 }} · {{ playerDetail.career.matches_2on2 }} · {{ playerDetail.career.matches_4on4 }} <span class="muted">1/2/4on</span></span>
                  <span class="k">last 90d</span><span class="v">{{ playerDetail.career.matches_90d || 0 }} matches</span>
                </div>

                <div v-if="playerDetail.ratings['1on1']" class="insp-section-h">1on1 rating</div>
                <div v-if="playerDetail.ratings['1on1']" class="kv">
                  <span class="k">division</span><span class="v">
                    <span v-if="playerDetail.ratings['1on1'].tier" class="badge" :style="{ color: playerDetail.ratings['1on1'].tier.color, borderColor: playerDetail.ratings['1on1'].tier.color, background: playerDetail.ratings['1on1'].tier.color + '14' }">{{ playerDetail.ratings['1on1'].tier.name }}</span>
                  </span>
                  <span class="k">cons</span><span class="v brand">{{ Math.round(playerDetail.ratings['1on1'].conservative) }}</span>
                  <span class="k">μ / σ</span><span class="v">{{ Math.round(playerDetail.ratings['1on1'].mu) }} / {{ Math.round(playerDetail.ratings['1on1'].sigma) }}</span>
                  <span class="k">matches</span><span class="v">{{ playerDetail.ratings['1on1'].matches_rated.toLocaleString() }}</span>
                  <span class="k">W / L / D</span><span class="v">{{ playerDetail.ratings['1on1'].wins }} / {{ playerDetail.ratings['1on1'].losses }} / {{ playerDetail.ratings['1on1'].draws }}</span>
                  <span class="k">win rate</span><span class="v">{{ fmtPct(playerDetail.ratings['1on1'].wins / playerDetail.ratings['1on1'].matches_rated) }}</span>
                  <span class="k">DDR</span><span class="v">{{ playerDetail.ratings['1on1'].avg_ddr?.toFixed(2) ?? '—' }}</span>
                  <span class="k">±frag</span><span class="v">{{ playerDetail.ratings['1on1'].avg_frag_diff != null ? (playerDetail.ratings['1on1'].avg_frag_diff >= 0 ? '+' : '') + playerDetail.ratings['1on1'].avg_frag_diff.toFixed(1) : '—' }}</span>
                  <span class="k">unique opps</span><span class="v">{{ playerDetail.ratings['1on1'].unique_opponents }}</span>
                  <span class="k">rated at</span><span class="v small">{{ fmtDate(playerDetail.ratings['1on1'].updated_at) }}</span>
                </div>

                <div v-if="playerDetail.aliases?.length" class="insp-section-h">Aliases ({{ playerDetail.aliases.length }})</div>
                <div v-if="playerDetail.aliases?.length" class="alias-list">
                  <div v-for="a in playerDetail.aliases.slice(0, 8)" :key="a.name" class="alias-row">
                    <span class="alias-name">{{ a.name }}</span>
                    <span class="alias-uses">{{ a.uses.toLocaleString() }}</span>
                  </div>
                  <div v-if="playerDetail.aliases.length > 8" class="muted small" style="text-align:center; padding:4px;">+ {{ playerDetail.aliases.length - 8 }} more</div>
                </div>

                <div class="insp-section-h">Federation</div>
                <div class="muted small" style="padding: 4px 0 0;">No identity linked yet. Q2 federation will let this player claim their canonical_id.</div>
              </template>

              <div class="insp-actions">
                <a :href="`/p/${encodeURIComponent(selectedPlayer.canonical_id)}`" target="_blank" class="btn ghost">Open public profile →</a>
              </div>
            </div>
          </div>
        </template>

        <!-- DEPLOY LOG — full table of every Cloud Run revision -->
        <template v-else-if="activeSection === 'matches'">
          <div class="pane-head">
            <div>
              <h2>Matches by region</h2>
              <div class="scope">Click a region to drill in · numbers reflect the window + mode picker</div>
            </div>
            <div class="actions">
              <select v-model="matchesWindow" class="btn">
                <option value="7">Last 7d</option>
                <option value="30">Last 30d</option>
                <option value="90">Last 90d</option>
                <option value="365">Last year</option>
                <option value="all">All time</option>
              </select>
              <button class="btn ghost" @click="loadMatches" :disabled="matchesLoading">⟳ Refresh</button>
            </div>
          </div>

          <div v-if="matchesError" class="placeholder err">{{ matchesError }}</div>
          <div v-else-if="matchesLoading && !matchesData" class="placeholder">Loading matches…</div>

          <template v-else-if="matchesData">
            <!-- Region tab row -->
            <div class="region-tabs">
              <div v-for="r in matchesData.region_totals" :key="r.region"
                   class="rt" :class="{ active: matchesRegion === r.region }"
                   @click="matchesRegion = r.region">
                <div v-if="r.servers_live" class="rt-live"><i></i>{{ r.servers_live }} LIVE</div>
                <div class="rt-flag">{{ r.flag }}</div>
                <div class="rt-name">{{ r.name }}</div>
                <div class="rt-val">{{ r.matches.toLocaleString() }}</div>
                <div class="rt-sub">{{ r.servers != null ? `${r.servers} server${r.servers === 1 ? '' : 's'}` : `${matchesData.region_totals.length - 1} regions` }}</div>
              </div>
            </div>

            <!-- Region header -->
            <div class="region-header">
              <h3>
                {{ matchesData.region_totals.find(r => r.region === matchesRegion)?.flag }}
                {{ matchesData.region_totals.find(r => r.region === matchesRegion)?.name }} activity
              </h3>
              <span v-if="matchesData.summary.servers_live" class="chip">{{ matchesData.summary.servers_live }} live</span>
            </div>

            <!-- KPI strip -->
            <div class="m-kpi-strip">
              <div class="m-kpi"><div class="l">Matches</div><div class="v">{{ matchesData.summary.matches.toLocaleString() }}</div></div>
              <div class="m-kpi"><div class="l">Unique players</div><div class="v">{{ matchesData.summary.unique_players.toLocaleString() }}</div></div>
              <div class="m-kpi"><div class="l">Servers</div><div class="v">{{ matchesData.summary.servers }}<span v-if="matchesData.summary.servers_live" class="sub-inline">{{ matchesData.summary.servers_live }} live</span></div></div>
              <div class="m-kpi"><div class="l">Peak hour</div><div class="v">{{ matchesData.summary.peak_hour_matches }}<span v-if="matchesData.summary.peak_hour != null" class="sub-inline">{{ String(matchesData.summary.peak_hour).padStart(2,'0') }}:00 {{ matchesData.summary.timezone_label }}</span></div></div>
            </div>

            <!-- Mode sub-tabs -->
            <div class="mode-tabs">
              <div class="mt" :class="{ active: matchesMode === 'all' }" @click="matchesMode = 'all'">
                All modes <span class="count">{{ (matchesData.mode_breakdown.all || 0).toLocaleString() }}</span>
              </div>
              <div class="mt" :class="{ active: matchesMode === '1on1' }" @click="matchesMode = '1on1'">
                1on1 <span class="count">{{ (matchesData.mode_breakdown['1on1'] || 0).toLocaleString() }}</span>
              </div>
              <div class="mt" :class="{ active: matchesMode === '2on2' }" @click="matchesMode = '2on2'">
                2on2 <span class="count">{{ (matchesData.mode_breakdown['2on2'] || 0).toLocaleString() }}</span>
              </div>
              <div class="mt" :class="{ active: matchesMode === '4on4' }" @click="matchesMode = '4on4'">
                4on4 <span class="count">{{ (matchesData.mode_breakdown['4on4'] || 0).toLocaleString() }}</span>
              </div>
            </div>

            <!-- 3-col: heatmap + top maps + top servers -->
            <div class="m-grid-3">
              <div class="card">
                <h4>Hourly activity · last 7 days <span class="total">{{ matchesData.timezone_label }}</span></h4>
                <div v-for="row in matchesData.heatmap" :key="row.day" class="hm-day-row">
                  <span class="d">{{ row.day }}</span>
                  <div class="heatmap">
                    <div v-for="h in row.hours" :key="h.hour" class="hm" :class="'l' + h.level"
                         :title="`${row.day} ${String(h.hour).padStart(2,'0')}:00 ${matchesData.timezone_label} · ${h.n} match${h.n === 1 ? '' : 'es'}`"></div>
                  </div>
                </div>
                <div class="hm-hours">
                  <span></span>
                  <div class="h"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>
                </div>
                <div class="hm-legend">
                  Less
                  <i></i><i class="l1-i"></i><i class="l2-i"></i><i class="l3-i"></i><i class="l4-i"></i><i class="l5-i"></i>
                  More · peak {{ matchesData.heatmap_max }} matches/hr
                </div>
              </div>

              <div class="card">
                <h4>Top maps <span class="total">{{ matchesData.top_maps.length }} unique</span></h4>
                <div class="m-lb">
                  <div v-for="(m, i) in matchesData.top_maps" :key="m.map" class="m-lb-row">
                    <span class="rank">{{ i + 1 }}</span>
                    <span class="name">{{ m.map }}</span>
                    <span class="val">{{ m.n.toLocaleString() }}</span>
                  </div>
                  <div v-if="!matchesData.top_maps.length" class="muted center" style="padding:20px 0;">No matches in scope</div>
                </div>
              </div>

              <div class="card">
                <h4>Top servers <span class="total">{{ matchesData.top_servers.length }} active</span></h4>
                <div class="m-lb">
                  <div v-for="(s, i) in matchesData.top_servers" :key="s.host_root" class="m-lb-row" :class="{ live: s.is_live }">
                    <span class="rank">{{ i + 1 }}</span>
                    <span class="name">{{ s.host_root }} <span class="sub" v-if="s.country">· {{ s.country }}</span></span>
                    <span class="val">{{ s.n.toLocaleString() }}</span>
                  </div>
                  <div v-if="!matchesData.top_servers.length" class="muted center" style="padding:20px 0;">No matches in scope</div>
                </div>
              </div>
            </div>

            <!-- Top players strip -->
            <div class="card" style="margin-top: 14px;">
              <h4>Top players in scope <span class="total">{{ matchesData.top_players.length }} unique</span></h4>
              <div class="m-players-grid">
                <div v-for="(p, i) in matchesData.top_players" :key="p.canonical_id" class="m-lb-row">
                  <span class="rank">{{ i + 1 }}</span>
                  <span class="name">{{ p.canonical_id }}</span>
                  <span class="val">{{ p.n.toLocaleString() }}</span>
                </div>
              </div>
            </div>
          </template>
        </template>

        <template v-else-if="activeSection === 'deploys'">
          <div class="pane-head">
            <div>
              <h2>Deploy log</h2>
              <div class="scope">Cloud Run + Cloudflare Pages · {{ deploys.length }} deploys</div>
            </div>
            <div class="actions">
              <button class="btn ghost" @click="loadDeploys" :disabled="deploysLoading">⟳ Refresh</button>
            </div>
          </div>

          <div v-if="deploysError" class="placeholder err">{{ deploysError }}</div>
          <div v-else-if="deploysLoading && !deploys.length" class="placeholder">Loading deploys…</div>
          <div v-else class="card" style="padding: 0;">
            <table class="deploy-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Revision</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th class="num">Traffic</th>
                  <th>SHA</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in deploys" :key="`${d.source}-${d.name}`" :class="{ active: d.active }">
                  <td>
                    <span :class="['badge', d.source === 'api' ? 'info' : 'ok']" style="min-width: 56px; text-align: center;">
                      {{ d.source === 'api' ? 'API' : 'Web' }}
                    </span>
                  </td>
                  <td>
                    <div class="rev-name">{{ d.name }}</div>
                    <div v-if="d.image" class="muted small">{{ d.image }}</div>
                    <div v-else-if="d.url" class="muted small"><a :href="d.url" target="_blank">{{ d.url.replace('https://','') }}</a></div>
                  </td>
                  <td class="muted small">{{ fmtDate(d.create_time) }}</td>
                  <td>
                    <span :class="['badge', isOkStatus(d.status) ? 'ok' : isErrStatus(d.status) ? 'err' : 'info']">
                      {{ shortStatus(d.status) }}
                    </span>
                  </td>
                  <td class="num">
                    <span v-if="d.active" class="badge ok">LIVE</span>
                    <span v-else-if="d.traffic_percent" class="badge ok">{{ d.traffic_percent }}%</span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="muted small mono">{{ d.image_sha || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <template v-else-if="activeSection === 'activity'">
          <div class="pane-head">
            <div>
              <h2>Activity log</h2>
              <div class="scope">{{ eventLog.length }} events · runtime data only (deploys live in their own tab)</div>
            </div>
            <div class="actions">
              <button class="btn ghost" @click="loadActivity">⟳ Refresh</button>
            </div>
          </div>
          <div class="card" style="padding: 0;">
            <div class="feed feed-full">
              <div v-if="!eventLog.length" class="muted center" style="padding: 24px;">No events yet.</div>
              <div v-for="(e, i) in eventLog" :key="i" class="line">
                <span class="ts">{{ e.ts }}</span>
                <span :class="['level', e.level]">{{ e.tag }}</span>
                <span class="msg">{{ e.msg }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- Placeholders for other sections -->
        <template v-else>
          <div class="pane-head">
            <h2>{{ sections.flatMap(g => g.items).find(i => i.id === activeSection)?.label }}</h2>
          </div>
          <div class="card placeholder">
            <p>This section is a placeholder for Wave 2.</p>
            <p class="muted">Will surface: detail tables, drill-down filters, manage actions (where applicable).</p>
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-shell { background: var(--bg); color: var(--fg); min-height: 100vh; }

/* AUTH GATE */
.auth-gate { display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 40px; }
.auth-card { max-width: 360px; width: 100%; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 32px; }
.auth-card h1 { font-size: 22px; font-weight: 800; margin-bottom: 8px; }
.auth-card p { color: var(--fg-3); font-size: 13px; margin-bottom: 16px; }
.auth-card input { width: 100%; background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 14px; border-radius: 8px; font-family: inherit; font-size: 14px; margin-bottom: 12px; }
.auth-card input:focus { outline: none; border-color: var(--accent); }
.auth-card button { width: 100%; background: var(--accent); color: var(--bg); border: 0; padding: 10px; border-radius: 8px; font-weight: 700; cursor: pointer; font-family: inherit; }
.auth-card .err { color: var(--loss); margin-top: 10px; }

/* LAYOUT */
.layout { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }

/* SIDEBAR */
.rail { background: var(--panel); border-right: 1px solid var(--border); padding: 20px 14px; display: flex; flex-direction: column; gap: 22px; }
.rail .brand { display: flex; align-items: center; gap: 10px; padding: 0 6px; }
.rail .brand .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.rail .brand .name { font-weight: 800; font-size: 14px; }
.rail .brand .admin-pill { background: var(--accent); color: var(--bg); padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 900; margin-left: auto; }
.group h4 { font-size: 9px; color: var(--fg-3); font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 6px; padding: 0 6px; }
.nav-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border-radius: 6px; color: var(--fg-2); cursor: pointer; font-size: 13px; font-weight: 500; }
.nav-item:hover { background: var(--panel-2); color: var(--fg); }
.nav-item.active { background: rgba(20,230,192,0.08); color: var(--accent); font-weight: 700; }

/* Scheduler on/off pill inside nav-item */
.sched-pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; cursor: pointer; }
.sched-pill .d { width: 6px; height: 6px; border-radius: 50%; }
.sched-pill.on { background: rgba(34,197,94,0.12); color: var(--win); border: 1px solid rgba(34,197,94,0.4); }
.sched-pill.on .d { background: var(--win); animation: pulse 2s infinite; }
.sched-pill.off { background: rgba(239,68,68,0.10); color: var(--loss); border: 1px solid rgba(239,68,68,0.4); }
.sched-pill.off .d { background: var(--loss); }
.sched-pill:hover { filter: brightness(1.2); }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.rail-footer { margin-top: auto; padding: 12px 6px; color: var(--fg-3); font-size: 10px; font-family: 'JetBrains Mono', monospace; }
.rail-footer .logout { display: block; margin-top: 6px; color: var(--accent); text-decoration: none; cursor: pointer; }
.rail-footer .logout:hover { text-decoration: underline; }

/* PANE */
.pane { padding: 28px 36px; overflow-x: hidden; }
.pane-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 22px; gap: 16px; }
.pane-head h2 { font-size: 22px; font-weight: 800; letter-spacing: -0.01em; }
.pane-head .scope { color: var(--fg-3); font-size: 11px; font-family: 'JetBrains Mono', monospace; margin-top: 4px; }
.actions { display: flex; gap: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 8px 14px; border-radius: 6px; font-weight: 700; font-size: 12px; cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 8px; }
.btn .kbd { font-family: 'JetBrains Mono', monospace; font-size: 10px; opacity: 0.6; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn.ghost .kbd { color: var(--fg-3); }
.btn.warn { background: var(--loss); color: white; }
.btn:hover { filter: brightness(1.1); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.placeholder { padding: 40px; text-align: center; color: var(--fg-3); }
.placeholder.err { color: var(--loss); }
.placeholder p { margin: 6px 0; }
.muted { color: var(--fg-3); }
.center { text-align: center; }

.num-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 16px; }
.nt { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.nt .l { font-size: 9px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
.nt .v { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 4px; }
.nt .v.small { font-size: 13px; font-family: 'JetBrains Mono', monospace; }
.nt .v.brand { color: var(--accent); }
.nt .v .muted { font-size: 12px; font-weight: 500; }

.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 18px 22px; }
.card h3 { font-size: 12px; color: var(--fg-3); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
.card h3 .meta { color: var(--fg-3); text-transform: none; letter-spacing: 0; font-size: 11px; font-family: 'JetBrains Mono', monospace; font-weight: 500; }

/* Dashboard 2-col grid (activity feed + latest deploys) */
.dash-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; }
.card h3 .link { color: var(--accent); text-decoration: none; cursor: pointer; font-weight: 600; font-size: 11px; }
.card h3 .link:hover { text-decoration: underline; }

/* Deploy lines in the dashboard mini-card */
.deploy-line.active { background: rgba(20,230,192,0.04); border-left: 2px solid var(--accent); padding-left: 8px; }
.deploy-line .rev-name { color: var(--fg); font-weight: 700; }

/* Deploy log full table */
.deploy-table { width: 100%; border-collapse: separate; border-spacing: 0; }
.deploy-table th { padding: 10px 14px; font-size: 10px; color: var(--fg-3); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; text-align: left; background: var(--panel-2); border-bottom: 1px solid var(--border); }
.deploy-table th.num { text-align: right; }
.deploy-table td { padding: 10px 14px; border-bottom: 1px solid var(--panel-2); font-size: 12px; vertical-align: middle; }
.deploy-table tr:last-child td { border-bottom: 0; }
.deploy-table td.num { text-align: right; font-family: 'JetBrains Mono', monospace; }
.deploy-table .rev-name { font-weight: 700; color: var(--fg); font-family: 'JetBrains Mono', monospace; }
.deploy-table tr.active td { background: rgba(20,230,192,0.04); }
.deploy-table tr.active td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.deploy-table .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.04em; }
.deploy-table .badge.ok { background: rgba(34,197,94,0.15); color: var(--win); }
.deploy-table .badge.err { background: rgba(239,68,68,0.15); color: var(--loss); }
.deploy-table .badge.info { background: rgba(74,159,255,0.15); color: var(--accent-2); }
.deploy-table .mono { font-family: 'JetBrains Mono', monospace; }

/* Live feed */
.feed { font-family: 'JetBrains Mono', monospace; font-size: 11px; max-height: 380px; overflow-y: auto; }
.feed-full { max-height: none; padding: 8px 16px; }
.line { display: grid; grid-template-columns: 72px 56px 1fr; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--panel-2); align-items: baseline; }
.line:last-child { border-bottom: 0; }
.line .ts { color: var(--fg-3); }
.line .level { font-weight: 700; }
.line .level.info { color: var(--accent-2); }
.line .level.ok { color: var(--win); }
.line .level.warn { color: var(--gold); }
.line .level.err { color: var(--loss); }
.line .msg { color: var(--fg-2); }

/* ─── Matches by Region (Region Switcher) ─────────────────────────────── */
.region-tabs { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin-bottom: 22px; }
.region-tabs .rt { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px 12px; cursor: pointer; transition: all 0.15s; position: relative; text-align: center; }
.region-tabs .rt:hover { border-color: var(--accent); transform: translateY(-1px); }
.region-tabs .rt.active { border-color: var(--accent); background: linear-gradient(180deg, rgba(20,230,192,0.12), var(--panel)); }
.region-tabs .rt.active::after { content: ''; position: absolute; bottom: -22px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent; border-top: 7px solid var(--accent); }
.region-tabs .rt .rt-flag { font-size: 24px; line-height: 1; margin-bottom: 5px; }
.region-tabs .rt .rt-name { font-size: 10px; color: var(--fg-2); text-transform: uppercase; font-weight: 700; letter-spacing: 0.06em; margin-bottom: 6px; }
.region-tabs .rt .rt-val { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.region-tabs .rt.active .rt-val { color: var(--accent); }
.region-tabs .rt .rt-sub { font-size: 10px; color: var(--fg-3); margin-top: 5px; font-family: 'JetBrains Mono', monospace; }
.region-tabs .rt .rt-live { position: absolute; top: 6px; right: 8px; display: flex; align-items: center; gap: 3px; font-size: 9px; color: var(--win); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
.region-tabs .rt .rt-live i { display: inline-block; width: 5px; height: 5px; background: var(--win); border-radius: 50%; animation: pulse-dot 2s infinite; }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.region-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.region-header h3 { font-size: 17px; font-weight: 800; }
.region-header .chip { padding: 3px 10px; border-radius: 5px; background: var(--accent); color: var(--bg); font-size: 9px; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; }

.m-kpi-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 18px; }
.m-kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }
.m-kpi .l { font-size: 10px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; margin-bottom: 4px; }
.m-kpi .v { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1; }
.m-kpi .v .sub-inline { font-size: 10px; color: var(--fg-3); margin-left: 6px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }

.mode-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 18px; }
.mode-tabs .mt { padding: 10px 18px; color: var(--fg-2); font-size: 12px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; }
.mode-tabs .mt:hover { color: var(--fg); }
.mode-tabs .mt.active { color: var(--accent); border-bottom-color: var(--accent); }
.mode-tabs .mt .count { margin-left: 6px; color: var(--fg-3); font-size: 10px; font-variant-numeric: tabular-nums; font-family: 'JetBrains Mono', monospace; }

.m-grid-3 { display: grid; grid-template-columns: 1.5fr 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.m-grid-3 .card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; }
.m-grid-3 .card h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--fg-2); font-weight: 700; margin-bottom: 14px; display: flex; justify-content: space-between; }
.m-grid-3 .card h4 .total { color: var(--fg-3); font-weight: 600; }

/* Heatmap */
.heatmap { display: grid; grid-template-columns: repeat(24, 1fr); gap: 2px; }
.hm { aspect-ratio: 1; border-radius: 2px; background: var(--panel-3); cursor: default; }
.hm.l0 { background: var(--panel-3); }
.hm.l1 { background: rgba(20,230,192,0.18); }
.hm.l2 { background: rgba(20,230,192,0.35); }
.hm.l3 { background: rgba(20,230,192,0.55); }
.hm.l4 { background: rgba(20,230,192,0.75); }
.hm.l5 { background: rgba(20,230,192,1); }
.hm:hover { outline: 1px solid var(--accent); }
.hm-day-row { display: grid; grid-template-columns: 30px 1fr; gap: 6px; align-items: center; margin-bottom: 3px; }
.hm-day-row .d { font-size: 10px; color: var(--fg-3); text-transform: uppercase; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.hm-hours { display: grid; grid-template-columns: 30px 1fr; gap: 6px; margin-top: 6px; color: var(--fg-3); font-size: 9px; font-family: 'JetBrains Mono', monospace; }
.hm-hours .h { display: flex; justify-content: space-between; }
.hm-legend { display: flex; align-items: center; gap: 5px; margin-top: 12px; font-size: 10px; color: var(--fg-3); }
.hm-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: var(--panel-3); }
.hm-legend i.l1-i { background: rgba(20,230,192,0.18); }
.hm-legend i.l2-i { background: rgba(20,230,192,0.35); }
.hm-legend i.l3-i { background: rgba(20,230,192,0.55); }
.hm-legend i.l4-i { background: rgba(20,230,192,0.75); }
.hm-legend i.l5-i { background: rgba(20,230,192,1); }

/* Matches leaderboards */
.m-lb { display: flex; flex-direction: column; }
.m-lb-row { display: grid; grid-template-columns: 18px 1fr auto; gap: 10px; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid var(--panel-2); }
.m-lb-row:last-child { border-bottom: 0; }
.m-lb-row .rank { color: var(--fg-3); font-variant-numeric: tabular-nums; text-align: right; font-size: 10px; font-family: 'JetBrains Mono', monospace; }
.m-lb-row .name { color: var(--fg); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-lb-row .name .sub { color: var(--fg-3); font-size: 10px; font-weight: 400; margin-left: 4px; }
.m-lb-row .val { color: var(--fg); font-weight: 700; font-variant-numeric: tabular-nums; font-size: 11px; font-family: 'JetBrains Mono', monospace; }
.m-lb-row.live { position: relative; }
.m-lb-row.live::before { content: ''; position: absolute; left: -6px; top: 50%; transform: translateY(-50%); width: 4px; height: 4px; background: var(--win); border-radius: 50%; animation: pulse-dot 2s infinite; }
.m-players-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0 18px; }

/* Modal */
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 24px 28px; max-width: 520px; }
.modal h3 { font-size: 18px; font-weight: 800; margin-bottom: 12px; }
.modal p { font-size: 13px; color: var(--fg-2); margin-bottom: 10px; }
.modal code { background: var(--panel-3); padding: 1px 5px; border-radius: 3px; font-size: 11px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.modal pre { background: var(--bg); border: 1px solid var(--border); padding: 12px; border-radius: 6px; font-size: 10px; max-height: 240px; overflow: auto; color: var(--fg-2); }
.modal .spinner { text-align: center; font-size: 32px; color: var(--accent); animation: spin 2s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* PLAYERS */
.players-toolbar { display: flex; gap: 12px; margin-bottom: 12px; align-items: center; }
.search-left { flex: 0 0 320px; }
.filter-right { display: flex; gap: 8px; align-items: center; margin-left: auto; }
.dd { background: var(--panel); border: 1px solid var(--border); color: var(--fg); padding: 7px 26px 7px 12px; border-radius: 6px; font-family: inherit; font-size: 12px; font-weight: 600; cursor: pointer; appearance: none; -webkit-appearance: none; background-image: linear-gradient(45deg, transparent 50%, var(--fg-3) 50%), linear-gradient(135deg, var(--fg-3) 50%, transparent 50%); background-position: calc(100% - 12px) 50%, calc(100% - 8px) 50%; background-size: 4px 4px; background-repeat: no-repeat; }
.dd:focus { outline: none; border-color: var(--accent); }
input.dd { padding-right: 12px; background-image: none; cursor: text; }
.filter-right .count { color: var(--fg-3); font-size: 11px; font-family: 'JetBrains Mono', monospace; }

.players-grid { display: grid; grid-template-columns: 1fr 380px; gap: 12px; }
.players-grid:has(.inspector) .players-table { grid-column: 1; }
.players-table { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; max-height: calc(100vh - 280px); overflow-y: auto; }
.players-table table { width: 100%; border-collapse: separate; border-spacing: 0; }
.players-table thead { position: sticky; top: 0; background: var(--panel-2); z-index: 1; }
.players-table th { padding: 9px 14px; font-size: 10px; color: var(--fg-3); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; text-align: left; border-bottom: 1px solid var(--border); }
.players-table th.num { text-align: right; }
.players-table td { padding: 8px 14px; border-bottom: 1px solid var(--panel-2); font-size: 12px; }
.players-table td.num { text-align: right; font-family: 'JetBrains Mono', monospace; }
.players-table tbody tr { cursor: pointer; }
.players-table tbody tr:hover td { background: rgba(20,230,192,0.02); }
.players-table tbody tr.selected td { background: rgba(20,230,192,0.08); }
.players-table tbody tr.selected td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.players-table .badge { display: inline-block; padding: 1px 6px; border-radius: 3px; border: 1px solid; font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }

.inspector { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 20px 22px; height: fit-content; position: sticky; top: 28px; }
.insp-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.insp-head h3 { font-size: 18px; font-weight: 800; }
.insp-head .x { background: transparent; border: 0; color: var(--fg-3); font-size: 16px; cursor: pointer; padding: 4px 8px; }
.insp-head .x:hover { color: var(--fg); }
.kv { display: grid; grid-template-columns: 110px 1fr; gap: 6px 12px; font-size: 12px; }
.kv .k { color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; font-size: 10px; padding-top: 2px; }
.kv .v { font-family: 'JetBrains Mono', monospace; color: var(--fg); }
.kv .v.brand { color: var(--accent); font-weight: 700; }
.insp-actions { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }
.insp-actions .btn { text-decoration: none; }
.insp-section-h {
  margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--border);
  font-size: 10px; color: var(--fg-3); font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; margin-bottom: 8px;
}
.insp-section-h:first-of-type { margin-top: 0; padding-top: 0; border-top: 0; }
.kv .v.small { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg-2); }
.alias-list { display: flex; flex-direction: column; gap: 2px; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.alias-row { display: flex; justify-content: space-between; padding: 4px 8px; background: var(--panel); border-radius: 4px; }
.alias-name { color: var(--fg); }
.alias-uses { color: var(--fg-3); }
.small { font-size: 11px; }
</style>

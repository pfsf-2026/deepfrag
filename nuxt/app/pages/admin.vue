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
  if (authed.value) loadStatus()
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

function pushEvent(level, tag, msg) {
  eventLog.value.unshift({ ts: new Date().toISOString().slice(11, 19), level, tag, msg })
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
})

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

function selectPlayer(p) { selectedPlayer.value = p }
function closeInspector() { selectedPlayer.value = null }

// ─── hotkeys ─────────────────────────────────────────────────────────────
function onKey(e) {
  if (!authed.value) return
  if (e.target?.tagName === 'INPUT' || e.target?.tagName === 'SELECT') return
  if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); triggerSync() }
  if ((e.metaKey || e.ctrlKey) && e.key === 'r') { e.preventDefault(); startRerate() }
  if ((e.metaKey || e.ctrlKey) && e.key === 'i') { e.preventDefault(); loadStatus() }
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'p') {
    e.preventDefault(); toggleScheduler()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

useHead({ title: 'Admin · DeepFrag' })

function fmtPct(v) { return v == null ? '—' : (v * 100).toFixed(0) + '%' }
function fmtDate(s) { return s ? new Date(s).toLocaleString() : '—' }
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
              <button class="btn" @click="loadStatus" :disabled="statusLoading">⟳ Refresh <span class="kbd">⌘I</span></button>
              <button class="btn ghost" @click="triggerSync">Trigger sync <span class="kbd">⌘S</span></button>
              <button class="btn warn" @click="startRerate">Full re-rate <span class="kbd">⌘R</span></button>
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

            <!-- Live activity feed -->
            <div class="card">
              <h3>Live activity <span class="meta">{{ eventLog.length }} events this session</span></h3>
              <div class="feed">
                <div v-if="!eventLog.length" class="muted center">No events yet. Trigger an action to see it here.</div>
                <div v-for="(e, i) in eventLog" :key="i" class="line">
                  <span class="ts">{{ e.ts }}</span>
                  <span :class="['level', e.level]">{{ e.tag }}</span>
                  <span class="msg">{{ e.msg }}</span>
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

            <!-- Inspector slide-in -->
            <div v-if="selectedPlayer" class="inspector">
              <div class="insp-head">
                <h3>{{ selectedPlayer.display }}</h3>
                <button class="x" @click="closeInspector">✕</button>
              </div>
              <div class="kv">
                <span class="k">canonical_id</span><span class="v">{{ selectedPlayer.canonical_id }}</span>
                <span class="k">region</span><span class="v">{{ selectedPlayer.region || '—' }}</span>
                <span class="k">division</span><span class="v">{{ selectedPlayer.tier?.name || '—' }}</span>
                <span class="k">cons</span><span class="v brand">{{ Math.round(selectedPlayer.conservative) }}</span>
                <span class="k">μ / σ</span><span class="v">{{ Math.round(selectedPlayer.mu) }} / {{ Math.round(selectedPlayer.sigma) }}</span>
                <span class="k">matches</span><span class="v">{{ selectedPlayer.matches.toLocaleString() }}</span>
                <span class="k">W / L / D</span><span class="v">{{ selectedPlayer.wins }} / {{ selectedPlayer.losses }} / {{ selectedPlayer.draws }}</span>
                <span class="k">DDR</span><span class="v">{{ selectedPlayer.avg_ddr ?? '—' }}</span>
                <span class="k">±frag</span><span class="v">{{ selectedPlayer.avg_frag_diff != null ? (selectedPlayer.avg_frag_diff >= 0 ? '+' : '') + selectedPlayer.avg_frag_diff.toFixed(1) : '—' }}</span>
                <span class="k">unique opps</span><span class="v">{{ selectedPlayer.unique_opponents }}</span>
                <span class="k">last seen</span><span class="v">{{ fmtDate(selectedPlayer.last_match) }}</span>
              </div>
              <div class="insp-actions">
                <a :href="`/p/${encodeURIComponent(selectedPlayer.canonical_id)}`" target="_blank" class="btn ghost">Open public profile →</a>
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

/* Live feed */
.feed { font-family: 'JetBrains Mono', monospace; font-size: 11px; max-height: 380px; overflow-y: auto; }
.line { display: grid; grid-template-columns: 72px 56px 1fr; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--panel-2); align-items: baseline; }
.line:last-child { border-bottom: 0; }
.line .ts { color: var(--fg-3); }
.line .level { font-weight: 700; }
.line .level.info { color: var(--accent-2); }
.line .level.ok { color: var(--win); }
.line .level.warn { color: var(--gold); }
.line .level.err { color: var(--loss); }
.line .msg { color: var(--fg-2); }

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
</style>

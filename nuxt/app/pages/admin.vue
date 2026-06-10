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
  { group: 'Ladder', items: [
    { id: 'ladder', label: 'King of the Hill' }
  ]},
  { group: 'Support', items: [
    { id: 'support', label: 'Support tickets' }
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

// ─── Apply aliases (fast: explicit aliases.yaml only, no fuzzy) ───────────
const aliasRunning = ref(false)
async function applyAliases() {
  aliasRunning.value = true
  pushEvent('info', 'CANON', 'apply-aliases started…')
  try {
    const r = await $fetch(`${apiBase}/api/admin/apply-aliases`, {
      method: 'POST', headers: adminHeaders(), timeout: 120000
    })
    pushEvent('ok', 'CANON', `aliases applied · ${r.rows_repointed} rows re-pointed · ${r.orphans_hidden} orphans hidden`)
  } catch (e) {
    pushEvent('err', 'CANON', e?.data?.detail || e?.message || 'failed')
  } finally {
    aliasRunning.value = false
  }
}

// ─── Recanonicalize names (fast name pass; surfaces errors) ───────────────
const recanonRunning = ref(false)
async function recanon() {
  recanonRunning.value = true
  pushEvent('info', 'CANON', 'recanonicalize started…')
  try {
    const r = await $fetch(`${apiBase}/api/admin/recanonicalize`, {
      method: 'POST', headers: adminHeaders(), timeout: 620000
    })
    if (r.returncode === 0) {
      pushEvent('ok', 'CANON', `done · ${(r.stdout_tail || '').split('\n').filter(Boolean).slice(-1)[0] || 'ok'}`)
    } else {
      pushEvent('err', 'CANON', `rc=${r.returncode} · ${(r.stderr_tail || '').slice(-400)}`)
    }
    // Always surface the tails so we can read them
    console.log('[recanon] stdout:', r.stdout_tail)
    console.log('[recanon] stderr:', r.stderr_tail)
    recanonResult.value = r
  } catch (e) {
    pushEvent('err', 'CANON', e?.data?.detail || e?.message || 'failed')
  } finally {
    recanonRunning.value = false
  }
}
const recanonResult = ref(null)

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
  if (s === 'users') { loadUsers(); loadClaims() }
  if (s === 'oauth') { loadOAuth(); loadClaims() }
  if (s === 'ladder') loadLadder()
  if (s === 'canon') loadCanon()
  if (s === 'support') loadSupport()
})

// ─── Support tickets ───────────────────────────────────────────────────────
const tickets = ref([])
const ticketsLoading = ref(false)
const ticketOpen = ref(null)        // expanded ticket id
const claudeBrief = ref(null)       // { id, text } for the "Resolve w/ Claude" box
async function loadSupport() {
  ticketsLoading.value = true
  try {
    const r = await $fetch(`${apiBase}/api/admin/support/tickets`, { headers: adminHeaders() })
    tickets.value = r.tickets || []
  } catch (e) {
    pushEvent('err', 'SUPPORT', e?.data?.detail || e?.message || 'load failed')
  } finally {
    ticketsLoading.value = false
  }
}
const resolveForm = ref({})   // ticket_id -> { summary, detail }
async function setTicketStatus(t, status, body = {}) {
  try {
    const r = await $fetch(`${apiBase}/api/admin/support/tickets/${t.id}/status`, {
      method: 'POST', headers: adminHeaders(), body: { status, ...body }
    })
    const em = r.email_status ? ` · email ${r.email_status}` : ''
    pushEvent('ok', 'SUPPORT', `#${t.id} → ${status}${em}`)
    await loadSupport()
  } catch (e) {
    pushEvent('err', 'SUPPORT', e?.data?.detail || e?.message || 'update failed')
  }
}
async function resolveTicket(t) {
  const f = resolveForm.value[t.id] || {}
  if (!f.summary || !f.summary.trim()) { pushEvent('err', 'SUPPORT', 'add a plain-English summary first'); return }
  await setTicketStatus(t, 'resolved', { resolution_summary: f.summary, resolution_detail: f.detail || '' })
}
// Build a ready-to-paste brief for a Claude Code session, and mark in-progress.
async function resolveWithClaude(t) {
  const lines = [
    `Resolve DeepFrag support ticket #${t.id}.`,
    `Area: ${t.area || '—'}`,
    `Summary: ${t.title}`,
    '',
    'Details:',
    t.description,
    '',
    `Reported on page: ${t.page_url || '—'}`,
    `Reporter: ${t.username || t.email || 'anonymous'}${t.canonical_id ? ' (profile ' + t.canonical_id + ')' : ''}`,
    '',
    'Diagnose the root cause in the codebase, fix it, and report what you changed.'
  ]
  if (t.attachments?.length) lines.splice(9, 0, `Screenshots: ${t.attachments.length} attached (view in the Support panel).`, '')
  claudeBrief.value = { id: t.id, text: lines.join('\n') }
  try { await navigator.clipboard.writeText(claudeBrief.value.text) } catch { /* clipboard optional */ }
  if (t.status === 'open') await setTicketStatus(t, 'in_progress')
}

// Screenshots are admin-gated, so <img src> can't carry the bearer token — fetch
// each as an authed blob once and cache an object URL.
const attBlobs = ref({})    // attachment id -> object URL
const lightbox = ref('')    // object URL for full-size view
async function loadAttachment(id) {
  if (attBlobs.value[id]) return
  try {
    const blob = await $fetch(`${apiBase}/api/admin/support/attachment/${id}`, { headers: adminHeaders(), responseType: 'blob' })
    attBlobs.value = { ...attBlobs.value, [id]: URL.createObjectURL(blob) }
  } catch (e) { pushEvent('err', 'SUPPORT', `image ${id}: ${e?.message || 'load failed'}`) }
}
watch(ticketOpen, (id) => {
  const t = tickets.value.find(x => x.id === id)
  ;(t?.attachments || []).forEach(loadAttachment)
})

// ─── Canonicalize queue: clean up orphan/junk profiles ─────────────────────
const canonList = ref([])
const canonLoading = ref(false)
const canonMin = ref(20)
const canonMax = ref(100)
const canonOnlyIsolated = ref(true)
const canonLink = ref({})   // canonical_id -> {q, results, picked}

async function loadCanon() {
  canonLoading.value = true
  try {
    const p = new URLSearchParams({
      min_matches: String(canonMin.value), max_matches: String(canonMax.value),
      only_isolated: String(canonOnlyIsolated.value)
    })
    const r = await $fetch(`${apiBase}/api/admin/canon/review?${p}`, { headers: adminHeaders() })
    canonList.value = r.profiles || []
  } catch (e) {
    pushEvent('err', 'CANON', e?.data?.detail || e?.message || 'load failed')
  } finally {
    canonLoading.value = false
  }
}

let canonTimer = {}
function canonSearch(cid) {
  const st = canonLink.value[cid] || (canonLink.value[cid] = { q: '', results: [], picked: null })
  clearTimeout(canonTimer[cid])
  st.picked = null
  if (!st.q || st.q.length < 2) { st.results = []; return }
  canonTimer[cid] = setTimeout(async () => {
    try {
      const r = await $fetch(`${apiBase}/api/search?q=${encodeURIComponent(st.q)}&limit=8`)
      st.results = (r.results || []).filter(x => x.canonical_id !== cid)
    } catch { st.results = [] }
  }, 220)
}
function canonPick(cid, p) {
  const st = canonLink.value[cid]
  st.picked = { id: p.canonical_id, display: p.display }
  st.q = p.display; st.results = []
}
// Inspect any profile by canonical_id (opens the slide-in with aliases + counts).
const inspectId = ref('')
function inspectById() {
  const id = inspectId.value.trim()
  if (id) selectPlayer({ canonical_id: id, display: id })
}
// Hide/delete any profile by canonical_id (not just queue rows). Soft + reversible.
const delProfileId = ref('')
async function deleteProfileById() {
  const id = delProfileId.value.trim()
  if (!id) return
  if (!confirm(`Hide profile "${id}" everywhere? Reversible — match data is untouched.`)) return
  try {
    await $fetch(`${apiBase}/api/admin/canon/${encodeURIComponent(id)}/review`, {
      method: 'POST', headers: adminHeaders(), body: { action: 'delete', target: null }
    })
    pushEvent('ok', 'CANON', `hidden ${id}`)
    delProfileId.value = ''
    canonList.value = canonList.value.filter(x => x.canonical_id !== id)
  } catch (e) {
    pushEvent('err', 'CANON', e?.data?.detail || e?.message || 'delete failed')
  }
}
async function canonAction(row, action) {
  const target = action === 'merge' ? canonLink.value[row.canonical_id]?.picked?.id : null
  if (action === 'merge' && !target) { pushEvent('err', 'CANON', 'pick a profile to link into first'); return }
  try {
    await $fetch(`${apiBase}/api/admin/canon/${encodeURIComponent(row.canonical_id)}/review`, {
      method: 'POST', headers: adminHeaders(), body: { action, target }
    })
    pushEvent('ok', 'CANON', `${action} ${row.display}${target ? ' → ' + target : ''}`)
    canonList.value = canonList.value.filter(x => x.canonical_id !== row.canonical_id)
  } catch (e) {
    pushEvent('err', 'CANON', e?.data?.detail || e?.message || `${action} failed`)
  }
}

// ─── Ladder admin: create ladder + seed teams + report results ─────────────
const ladders = ref([])
const ladderId = ref(null)
const ladderDetail = ref(null)
const ladderLoading = ref(false)
const newLadder = ref({ name: 'King of the Hill 2v2', season: 'Xmas 2026', team_size: 2 })
const DEFAULT_MAPS = ['aerowalk', 'ztndm3', 'dm2', 'dm4', 'bravado', 'nova', 'shifter']
const newTeam = ref({ name: '', members: '', rung: '' })
const reportFor = ref(null)        // challenge being reported
const reportForm = ref({ winner_id: null, score_a: null, score_b: null, hub: '' })

const ladderPending = ref([])
async function loadLadder() {
  ladderLoading.value = true
  try {
    const r = await $fetch(`${apiBase}/api/ladder`)
    ladders.value = r.ladders || []
    if (!ladderId.value && ladders.value.length) ladderId.value = ladders.value[0].id
    if (ladderId.value) {
      ladderDetail.value = await $fetch(`${apiBase}/api/ladder/${ladderId.value}`)
      const p = await $fetch(`${apiBase}/api/admin/ladder/${ladderId.value}/teams/pending`, { headers: adminHeaders() })
      ladderPending.value = p.pending || []
    }
  } catch (e) {
    pushEvent('err', 'LADDER', e?.data?.detail || e?.message || 'load failed')
  } finally {
    ladderLoading.value = false
  }
}

async function approveTeam(t) {
  try { await $fetch(`${apiBase}/api/admin/ladder/team/${t.id}/approve`, { method: 'POST', headers: adminHeaders() }); pushEvent('ok', 'LADDER', `approved ${t.name}`); await loadLadder() }
  catch (e) { pushEvent('err', 'LADDER', e?.data?.detail || 'approve failed') }
}
async function rejectTeam(t) {
  try { await $fetch(`${apiBase}/api/admin/ladder/team/${t.id}/reject`, { method: 'POST', headers: adminHeaders() }); pushEvent('ok', 'LADDER', `rejected ${t.name}`); await loadLadder() }
  catch (e) { pushEvent('err', 'LADDER', e?.data?.detail || 'reject failed') }
}

// Admin team editor — set name/tag and assign player profiles (the roster).
const teamEdit = ref(null)               // team being edited
const teamEditForm = ref({ name: '', tag: '', slots: [] })  // slots: [{id, display}|null]
const slotQ = ref(['', ''])
const slotRes = ref([[], []])
function openTeamEdit(t) {
  teamEdit.value = t
  const m = t.members || []
  teamEditForm.value = {
    name: t.name || '',
    tag: t.tag || '',
    slots: [m[0] ? { id: m[0].id, display: m[0].display } : null,
            m[1] ? { id: m[1].id, display: m[1].display } : null]
  }
  slotQ.value = ['', '']
  slotRes.value = [[], []]
}
let slotTimer = [null, null]
function onSlotInput(i) {
  clearTimeout(slotTimer[i])
  teamEditForm.value.slots[i] = null
  const q = slotQ.value[i]
  if (!q || q.length < 2) { slotRes.value[i] = []; return }
  slotTimer[i] = setTimeout(async () => {
    try {
      const r = await $fetch(`${apiBase}/api/search?q=${encodeURIComponent(q)}&limit=8`)
      slotRes.value[i] = r.results || []
    } catch { slotRes.value[i] = [] }
  }, 220)
}
function pickSlot(i, p) {
  teamEditForm.value.slots[i] = { id: p.canonical_id, display: p.display }
  slotQ.value[i] = ''
  slotRes.value[i] = []
}
function clearSlot(i) { teamEditForm.value.slots[i] = null }
async function saveTeamEdit() {
  const t = teamEdit.value
  const members = teamEditForm.value.slots.filter(Boolean).map(s => s.id)
  try {
    await $fetch(`${apiBase}/api/ladder/team/${t.id}/edit`, {
      method: 'POST', headers: adminHeaders(),
      body: { name: teamEditForm.value.name, tag: teamEditForm.value.tag, members }
    })
    pushEvent('ok', 'LADDER', `updated ${teamEditForm.value.name}`)
    teamEdit.value = null
    await loadLadder()
  } catch (e) { pushEvent('err', 'LADDER', e?.data?.detail || 'edit failed') }
}

async function createLadder() {
  if (!newLadder.value.name) return
  try {
    const r = await $fetch(`${apiBase}/api/admin/ladder/create`, {
      method: 'POST', headers: adminHeaders(),
      body: {
        name: newLadder.value.name,
        season: newLadder.value.season,
        team_size: Number(newLadder.value.team_size) || 2,
        map_pool: DEFAULT_MAPS,
        rules: { rung_jump: 2, forfeit_days: 7, best_of: 3, ruleset: 'smackdown', timelimit: 10 }
      }
    })
    pushEvent('ok', 'LADDER', `created "${r.name}" (id ${r.ladder_id})`)
    ladderId.value = r.ladder_id
    await loadLadder()
  } catch (e) {
    pushEvent('err', 'LADDER', e?.data?.detail || e?.message || 'create failed')
  }
}

async function addTeam() {
  if (!newTeam.value.name) return
  const members = newTeam.value.members.split(',').map(s => s.trim()).filter(Boolean)
  try {
    await $fetch(`${apiBase}/api/admin/ladder/${ladderId.value}/teams`, {
      method: 'POST', headers: adminHeaders(),
      body: {
        name: newTeam.value.name,
        members,
        rung: newTeam.value.rung === '' ? null : Number(newTeam.value.rung)
      }
    })
    pushEvent('ok', 'LADDER', `added team ${newTeam.value.name}`)
    newTeam.value = { name: '', members: '', rung: '' }
    await loadLadder()
  } catch (e) {
    pushEvent('err', 'LADDER', e?.data?.detail || e?.message || 'add failed')
  }
}

function startReport(c) {
  reportFor.value = c
  reportForm.value = { winner_id: c.challenger_id, score_a: 2, score_b: 0, hub: '' }
}
async function submitReport() {
  const c = reportFor.value
  const maps = reportForm.value.hub
    ? reportForm.value.hub.split(',').map(h => ({ hub_game_id: h.trim() })).filter(m => m.hub_game_id)
    : []
  try {
    await $fetch(`${apiBase}/api/admin/ladder/challenge/${c.id}/result`, {
      method: 'POST', headers: adminHeaders(),
      body: {
        winner_id: Number(reportForm.value.winner_id),
        score_a: Number(reportForm.value.score_a),
        score_b: Number(reportForm.value.score_b),
        maps
      }
    })
    pushEvent('ok', 'LADDER', `result recorded for challenge ${c.id}`)
    reportFor.value = null
    await loadLadder()
  } catch (e) {
    pushEvent('err', 'LADDER', e?.data?.detail || e?.message || 'report failed')
  }
}
async function forfeitChallenge(c) {
  try {
    await $fetch(`${apiBase}/api/admin/ladder/challenge/${c.id}/forfeit`, {
      method: 'POST', headers: adminHeaders()
    })
    pushEvent('ok', 'LADDER', `forfeit recorded for challenge ${c.id}`)
    await loadLadder()
  } catch (e) {
    pushEvent('err', 'LADDER', e?.data?.detail || e?.message || 'forfeit failed')
  }
}

// ─── Federation: users, OAuth providers, account-claims ────────────────────
const users = ref([])
const usersLoading = ref(false)
const oauth = ref(null)
const claims = ref([])
const claimsLoading = ref(false)
const linkInput = ref({})            // discord_id -> canonical_id being typed

async function loadUsers() {
  usersLoading.value = true
  try {
    const r = await $fetch(`${apiBase}/api/admin/users`, { headers: adminHeaders() })
    users.value = r.users || []
  } catch (e) {
    pushEvent('err', 'USERS', e?.data?.detail || e?.message || 'load failed')
  } finally {
    usersLoading.value = false
  }
}

async function loadOAuth() {
  try {
    oauth.value = await $fetch(`${apiBase}/api/admin/oauth/status`, { headers: adminHeaders() })
  } catch (e) {
    pushEvent('err', 'OAUTH', e?.data?.detail || e?.message || 'load failed')
  }
}

async function loadClaims() {
  claimsLoading.value = true
  try {
    const r = await $fetch(`${apiBase}/api/admin/claims?status=pending`, { headers: adminHeaders() })
    claims.value = r.claims || []
  } catch (e) {
    pushEvent('err', 'CLAIMS', e?.data?.detail || e?.message || 'load failed')
  } finally {
    claimsLoading.value = false
  }
}

async function resolveClaim(c, approve) {
  try {
    await $fetch(`${apiBase}/api/admin/claims/${c.id}/resolve`, {
      method: 'POST', headers: adminHeaders(), body: { approve }
    })
    pushEvent('ok', 'CLAIMS', `${approve ? 'approved' : 'rejected'} ${c.global_name || c.username} → ${c.profile_display || c.canonical_id}`)
    await Promise.all([loadClaims(), loadUsers(), loadOAuth()])
  } catch (e) {
    pushEvent('err', 'CLAIMS', e?.data?.detail || e?.message || 'resolve failed')
  }
}

async function verifyUser(u) {
  try {
    await $fetch(`${apiBase}/api/admin/users/${u.discord_id}/verify`, {
      method: 'POST', headers: adminHeaders(), body: { verified: !u.verified }
    })
    pushEvent('ok', 'USERS', `${u.global_name || u.username} verified → ${!u.verified}`)
    await loadUsers()
  } catch (e) {
    pushEvent('err', 'USERS', e?.data?.detail || e?.message || 'failed')
  }
}

async function toggleAdmin(u) {
  try {
    await $fetch(`${apiBase}/api/admin/users/${u.discord_id}/admin`, {
      method: 'POST', headers: adminHeaders(), body: { is_admin: !u.is_admin }
    })
    pushEvent('ok', 'USERS', `${u.global_name || u.username} admin → ${!u.is_admin}`)
    await loadUsers()
  } catch (e) {
    pushEvent('err', 'USERS', e?.data?.detail || e?.message || 'failed')
  }
}

// Fuzzy autocomplete for the link field (type "aard" → aardappel).
const linkResults = ref({})   // discord_id -> [{canonical_id, display, matches}]
const linkPicked = ref({})    // discord_id -> canonical_id chosen
let linkTimer = {}
function userLinkSearch(discordId) {
  clearTimeout(linkTimer[discordId])
  linkPicked.value[discordId] = null
  const q = (linkInput.value[discordId] || '').trim()
  if (q.length < 2) { linkResults.value[discordId] = []; return }
  linkTimer[discordId] = setTimeout(async () => {
    try {
      const r = await $fetch(`${apiBase}/api/search?q=${encodeURIComponent(q)}&limit=8`)
      linkResults.value[discordId] = r.results || []
    } catch { linkResults.value[discordId] = [] }
  }, 220)
}
function pickLink(discordId, p) {
  linkInput.value[discordId] = p.display
  linkPicked.value[discordId] = p.canonical_id
  linkResults.value[discordId] = []
}
async function linkUser(u) {
  // prefer an explicitly-picked profile; else treat the typed text as a canonical_id
  const cid = (linkPicked.value[u.discord_id] || linkInput.value[u.discord_id] || '').trim()
  if (!cid) return
  try {
    await $fetch(`${apiBase}/api/admin/users/${u.discord_id}/link`, {
      method: 'POST', headers: adminHeaders(), body: { canonical_id: cid }
    })
    pushEvent('ok', 'USERS', `linked ${u.global_name || u.username} → ${cid}`)
    linkInput.value[u.discord_id] = ''
    linkPicked.value[u.discord_id] = null
    linkResults.value[u.discord_id] = []
    await loadUsers()
  } catch (e) {
    pushEvent('err', 'USERS', e?.data?.detail || e?.message || 'link failed')
  }
}

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
              <button class="btn ghost" @click="applyAliases" :disabled="aliasRunning">{{ aliasRunning ? 'Applying…' : 'Apply aliases (fast)' }}</button>
              <button class="btn ghost" @click="recanon" :disabled="recanonRunning">{{ recanonRunning ? 'Recanonicalizing…' : 'Recanonicalize names' }}</button>
              <button class="btn warn" @click="startRerate">Full re-rate</button>
            </div>
          </div>

          <div v-if="recanonResult" class="card" style="margin-bottom:14px;">
            <h3>Recanonicalize output
              <span class="meta">rc={{ recanonResult.returncode }} <a class="link" @click="recanonResult=null">dismiss</a></span>
            </h3>
            <pre style="background:var(--bg); border:1px solid var(--border); padding:12px; border-radius:6px; font-size:11px; max-height:260px; overflow:auto; white-space:pre-wrap;">{{ recanonResult.stderr_tail || recanonResult.stdout_tail || '(no output)' }}</pre>
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
                <div v-if="playerDetail.aliases?.length" class="alias-list" style="max-height:320px; overflow-y:auto;">
                  <div v-for="a in playerDetail.aliases" :key="a.name" class="alias-row">
                    <span class="alias-name">{{ a.name }}</span>
                    <span class="alias-uses">{{ a.uses.toLocaleString() }}</span>
                  </div>
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

        <!-- LADDER · King of the Hill (KOTH) -->
        <template v-else-if="activeSection === 'ladder'">
          <div class="pane-head">
            <div>
              <h2>King of the Hill (KOTH) Ladder</h2>
              <div class="scope">create the ladder · seed teams · report results</div>
            </div>
            <div class="actions">
              <a href="/ladder" target="_blank" class="btn ghost">Open public board →</a>
              <button class="btn ghost" @click="loadLadder" :disabled="ladderLoading">⟳ Refresh</button>
            </div>
          </div>

          <!-- No ladder yet → create form -->
          <div v-if="!ladderLoading && !ladders.length" class="card" style="max-width: 520px;">
            <h3>Create the ladder</h3>
            <div class="form-grid">
              <label>Name<input v-model="newLadder.name"></label>
              <label>Season<input v-model="newLadder.season"></label>
              <label>Team size<input v-model="newLadder.team_size" type="number"></label>
            </div>
            <p class="muted small" style="margin:10px 0;">Maps: {{ DEFAULT_MAPS.join(' · ') }} · Bo3 · 1–2 rung challenges · 7-day forfeit window.</p>
            <button class="btn" @click="createLadder">Create ladder</button>
          </div>

          <template v-else-if="ladderDetail">
            <!-- Pending team signups -->
            <div v-if="ladderPending.length" class="card" style="margin-bottom:12px; border-color: var(--accent);">
              <h3>Pending team signups <span class="meta">{{ ladderPending.length }}</span></h3>
              <div v-for="t in ladderPending" :key="t.id" class="claim-row">
                <img v-if="t.has_logo" :src="`${apiBase}/api/ladder/team/${t.id}/logo`" class="av" alt="">
                <strong>{{ t.name }}</strong>
                <span class="muted small">{{ (t.members || []).map(m => m.display).join(' · ') || '—' }}</span>
                <span class="spacer" />
                <button class="btn sm ghost" @click="openTeamEdit(t)">Edit</button>
                <button class="btn sm" @click="approveTeam(t)">Approve</button>
                <button class="btn sm ghost" @click="rejectTeam(t)">Reject</button>
              </div>
            </div>

            <!-- KotH + add team -->
            <div class="ladder-grid">
              <div>
                <div v-if="ladderDetail.koth" class="card" style="margin-bottom:12px;">
                  <h3>👑 King of the Hill</h3>
                  <div style="font-size:18px; font-weight:800;">{{ ladderDetail.koth.name }}</div>
                  <div class="muted small" v-if="ladderDetail.koth.weeks != null">{{ ladderDetail.koth.weeks }} week(s) held</div>
                </div>

                <div class="card" style="padding:0;">
                  <table class="deploy-table">
                    <thead><tr><th>#</th><th>Team</th><th>Players</th><th></th></tr></thead>
                    <tbody>
                      <tr v-for="t in ladderDetail.teams" :key="t.id" :class="{ active: t.rung === 1 }">
                        <td class="mono">{{ t.rung }}</td>
                        <td><span v-if="t.tag" class="badge info">{{ t.tag }}</span> <strong>{{ t.name }}</strong></td>
                        <td class="muted small">{{ (t.members || []).map(m => m.display).join(', ') || '—' }}</td>
                        <td><button class="btn sm ghost" @click="openTeamEdit(t)">Edit</button></td>
                      </tr>
                      <tr v-if="!ladderDetail.teams.length"><td colspan="4" class="muted center" style="padding:20px;">No teams yet — add the first below.</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="card" style="height:fit-content;">
                <h3>Add / seed team</h3>
                <div class="form-grid">
                  <label>Team name<input v-model="newTeam.name" placeholder="e.g. Bootleggers"></label>
                  <label>Members (canonical_ids, comma-sep)<input v-model="newTeam.members" placeholder="cronus, nin"></label>
                  <label>Rung (blank = bottom)<input v-model="newTeam.rung" type="number" placeholder="auto"></label>
                </div>
                <button class="btn" style="margin-top:10px;" @click="addTeam">Add team</button>
                <p class="muted small" style="margin-top:10px;">Seed in ranked order (rung 1 = top), or leave rung blank to drop each new team at the bottom.</p>
              </div>
            </div>

            <!-- Open challenges to report -->
            <div v-if="ladderDetail.challenges.length" class="card" style="margin-top:14px;">
              <h3>Open challenges <span class="meta">{{ ladderDetail.challenges.length }}</span></h3>
              <div v-for="c in ladderDetail.challenges" :key="c.id" class="claim-row">
                <strong>{{ ladderDetail.teams.find(t => t.id === c.challenger_id)?.name || ('#'+c.challenger_id) }}</strong>
                <span class="arrow">vs</span>
                <strong>{{ ladderDetail.teams.find(t => t.id === c.challenged_id)?.name || ('#'+c.challenged_id) }}</strong>
                <span class="muted small">{{ c.rungs_up }} rung(s) up</span>
                <span class="spacer" />
                <button class="btn sm" @click="startReport(c)">Report result</button>
                <button class="btn sm ghost" @click="forfeitChallenge(c)">Forfeit</button>
              </div>
            </div>
          </template>
          <div v-else-if="ladderLoading" class="placeholder">Loading ladder…</div>

          <!-- Report modal -->
          <div v-if="reportFor" class="modal-bg" @click.self="reportFor = null">
            <div class="modal">
              <h3>Report result</h3>
              <div class="form-grid">
                <label>Winner
                  <select v-model="reportForm.winner_id" class="dd">
                    <option :value="reportFor.challenger_id">{{ ladderDetail.teams.find(t => t.id === reportFor.challenger_id)?.name }}</option>
                    <option :value="reportFor.challenged_id">{{ ladderDetail.teams.find(t => t.id === reportFor.challenged_id)?.name }}</option>
                  </select>
                </label>
                <label>Score (challenger)<input v-model="reportForm.score_a" type="number"></label>
                <label>Score (challenged)<input v-model="reportForm.score_b" type="number"></label>
                <label>Hub game IDs (comma-sep, optional)<input v-model="reportForm.hub" placeholder="12345, 12346"></label>
              </div>
              <div class="modal-actions">
                <button class="btn ghost" @click="reportFor = null">Cancel</button>
                <button class="btn" @click="submitReport">Save result</button>
              </div>
            </div>
          </div>

          <!-- Team roster editor -->
          <div v-if="teamEdit" class="modal-bg" @click.self="teamEdit = null">
            <div class="modal">
              <h3>Edit team — assign profiles</h3>
              <div class="form-grid">
                <label>Team name<input v-model="teamEditForm.name"></label>
                <label>Tag<input v-model="teamEditForm.tag" maxlength="6" style="text-transform:uppercase;"></label>
                <div v-for="(slot, i) in teamEditForm.slots" :key="i" class="slot">
                  <label>Player {{ i + 1 }}
                    <div v-if="slot" class="slot-picked">
                      <span>{{ slot.display }}</span>
                      <button class="x" @click="clearSlot(i)">✕</button>
                    </div>
                    <input v-else v-model="slotQ[i]" placeholder="search QW name…" @input="onSlotInput(i)">
                  </label>
                  <div v-if="slotRes[i].length" class="slot-res">
                    <button v-for="p in slotRes[i]" :key="p.canonical_id" @click="pickSlot(i, p)">
                      {{ p.display }} <span class="muted">{{ p.matches }}m</span>
                    </button>
                  </div>
                </div>
              </div>
              <div class="modal-actions">
                <button class="btn ghost" @click="teamEdit = null">Cancel</button>
                <button class="btn" @click="saveTeamEdit">Save team</button>
              </div>
            </div>
          </div>
        </template>

        <!-- FEDERATION · USERS -->
        <template v-else-if="activeSection === 'users'">
          <div class="pane-head">
            <div>
              <h2>Users</h2>
              <div class="scope">Discord-authed accounts · link them to QW player profiles</div>
            </div>
            <div class="actions">
              <button class="btn ghost" @click="loadUsers" :disabled="usersLoading">⟳ Refresh</button>
            </div>
          </div>

          <div class="muted small" style="margin-bottom: 14px;">
            Players link their own profile on sign-in (instant). Confirm each with <strong>Verify</strong> — unverified accounts are listed first.
          </div>

          <div class="card" style="padding: 0;">
            <table class="deploy-table">
              <thead>
                <tr>
                  <th>Account</th><th>Discord ID</th><th>Linked profile</th>
                  <th>Verified</th><th>Admin</th><th>Link / re-link</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in users" :key="u.discord_id">
                  <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                      <img v-if="u.avatar" :src="`https://cdn.discordapp.com/avatars/${u.discord_id}/${u.avatar}.png?size=32`" class="av" alt="">
                      <span>{{ u.global_name || u.username }}</span>
                    </div>
                  </td>
                  <td class="muted small mono">{{ u.discord_id }}</td>
                  <td>
                    <a v-if="u.canonical_id" :href="`/p/${encodeURIComponent(u.canonical_id)}`" target="_blank" class="badge ok" style="text-decoration:none;">{{ u.profile_display || u.canonical_id }}</a>
                    <span v-else class="muted small">— unlinked</span>
                  </td>
                  <td>
                    <button v-if="u.canonical_id" class="pill" :class="u.verified ? 'on' : 'off'" @click="verifyUser(u)">
                      {{ u.verified ? '✓ verified' : 'verify' }}
                    </button>
                    <span v-else class="muted small">—</span>
                  </td>
                  <td>
                    <button class="pill" :class="u.is_admin ? 'on' : 'off'" @click="toggleAdmin(u)">
                      {{ u.is_admin ? 'admin' : 'no' }}
                    </button>
                  </td>
                  <td>
                    <div style="display:flex; gap:6px; position:relative;">
                      <div style="position:relative;">
                        <input v-model="linkInput[u.discord_id]" placeholder="type a name…" class="dd" style="width:160px;"
                               autocomplete="off" @input="userLinkSearch(u.discord_id)" @keyup.enter="linkUser(u)">
                        <div v-if="(linkResults[u.discord_id] || []).length" class="link-res">
                          <button v-for="p in linkResults[u.discord_id]" :key="p.canonical_id" @click="pickLink(u.discord_id, p)">
                            {{ p.display }} <span class="muted">{{ p.matches }}</span>
                          </button>
                        </div>
                      </div>
                      <button class="btn sm ghost" @click="linkUser(u)">Link</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!users.length && !usersLoading"><td colspan="6" class="muted center" style="padding:24px;">No users have signed in with Discord yet.</td></tr>
              </tbody>
            </table>
          </div>
        </template>

        <!-- FEDERATION · OAUTH PROVIDERS -->
        <template v-else-if="activeSection === 'oauth'">
          <div class="pane-head">
            <div>
              <h2>OAuth providers</h2>
              <div class="scope">Identity federation · login + account linking</div>
            </div>
            <div class="actions">
              <button class="btn ghost" @click="loadOAuth" :disabled="!oauth">⟳ Refresh</button>
            </div>
          </div>

          <template v-if="oauth">
            <div class="num-strip" style="grid-template-columns: repeat(4,1fr);">
              <div class="nt"><div class="l">Users</div><div class="v">{{ oauth.counts.users }}</div></div>
              <div class="nt"><div class="l">Linked</div><div class="v brand">{{ oauth.counts.linked }}</div></div>
              <div class="nt"><div class="l">Admins</div><div class="v">{{ oauth.counts.admins }}</div></div>
              <div class="nt"><div class="l">Pending claims</div><div class="v">{{ oauth.counts.pending_claims }}</div></div>
            </div>

            <div class="card" style="margin-top:14px;">
              <h3>
                <span style="display:flex; align-items:center; gap:8px;">
                  <svg width="16" height="16" viewBox="0 0 127 96" fill="#5865f2"><path d="M107.7 8.1A105 105 0 0 0 81.5 0c-1.2 2-2.5 4.8-3.4 7a97.5 97.5 0 0 0-29.2 0c-1-2.2-2.3-5-3.5-7a105 105 0 0 0-26.2 8.1C2.6 33 .3 57.1 1.4 80.9A106 106 0 0 0 33.7 96c2.6-3.5 4.9-7.3 6.9-11.2-3.8-1.4-7.4-3.2-10.8-5.3.9-.7 1.8-1.4 2.6-2.1a75.6 75.6 0 0 0 64.6 0c.9.8 1.8 1.5 2.6 2.1-3.4 2-7 3.9-10.8 5.3 2 4 4.3 7.7 6.9 11.2a106 106 0 0 0 32.3-15.1c1.4-27.6-2.3-51.5-19.9-72.8ZM42.5 66.3c-6.3 0-11.5-5.8-11.5-13 0-7.1 5.1-13 11.5-13s11.6 5.9 11.5 13c0 7.2-5.1 13-11.5 13Zm42.5 0c-6.3 0-11.5-5.8-11.5-13 0-7.1 5-13 11.5-13s11.6 5.9 11.5 13c0 7.2-5.1 13-11.5 13Z"/></svg>
                  Discord
                </span>
                <span class="badge" :class="oauth.discord.configured ? 'ok' : 'err'">
                  {{ oauth.discord.configured ? 'configured' : 'not configured' }}
                </span>
              </h3>
              <div class="kv">
                <span class="k">client id</span><span class="v">{{ oauth.discord.client_id || '—' }}</span>
                <span class="k">client secret</span><span class="v">{{ oauth.discord.client_secret || '— missing' }}</span>
                <span class="k">redirect uri</span><span class="v small">{{ oauth.discord.redirect_uri || '—' }}</span>
                <span class="k">frontend url</span><span class="v small">{{ oauth.discord.frontend_url || '—' }}</span>
                <span class="k">scopes</span><span class="v">{{ oauth.discord.scopes.join(', ') }}</span>
                <span class="k">jwt secret</span><span class="v">{{ oauth.discord.jwt_secret }}</span>
                <span class="k">webhook</span><span class="v">{{ oauth.discord.webhook_configured ? 'configured' : '— not set' }}</span>
              </div>
            </div>

            <div v-if="claims.length" class="card" style="margin-top:14px;">
              <h3>Pending claims <span class="meta">{{ claims.length }}</span></h3>
              <div v-for="c in claims" :key="c.id" class="claim-row">
                <span class="who">{{ c.global_name || c.username }}</span>
                <span class="arrow">→</span>
                <span class="prof">{{ c.profile_display || c.canonical_id }}</span>
                <span class="spacer" />
                <button class="btn sm" @click="resolveClaim(c, true)">Approve</button>
                <button class="btn sm ghost" @click="resolveClaim(c, false)">Reject</button>
              </div>
            </div>
          </template>
          <div v-else class="placeholder">Loading OAuth status…</div>
        </template>

        <!-- CANONICALIZE QUEUE — profile cleanup -->
        <template v-else-if="activeSection === 'canon'">
          <div class="pane-head">
            <div>
              <h2>Canonicalize queue</h2>
              <div class="scope">isolated profiles by match count · delete junk, link alts, or keep</div>
            </div>
            <div class="actions">
              <label class="muted small">min <input v-model.number="canonMin" type="number" class="dd" style="width:64px;"></label>
              <label class="muted small">max <input v-model.number="canonMax" type="number" class="dd" style="width:64px;"></label>
              <label class="muted small" style="display:flex;align-items:center;gap:4px;"><input v-model="canonOnlyIsolated" type="checkbox"> isolated only</label>
              <button class="btn ghost" @click="loadCanon" :disabled="canonLoading">⟳ Load</button>
            </div>
          </div>

          <div class="del-by-id">
            <span class="muted small">Inspect any profile by id (aliases + counts):</span>
            <input v-model="inspectId" placeholder="canonical_id e.g. chris" class="dd" style="width:200px;" @keyup.enter="inspectById">
            <button class="btn sm" :disabled="!inspectId.trim()" @click="inspectById">Inspect</button>
            <span style="width:18px;"></span>
            <span class="muted small">Delete by id (hide, reversible):</span>
            <input v-model="delProfileId" placeholder="canonical_id" class="dd" style="width:160px;" @keyup.enter="deleteProfileById">
            <button class="btn sm danger" :disabled="!delProfileId.trim()" @click="deleteProfileById">Hide</button>
          </div>

          <div v-if="canonLoading" class="placeholder">Loading profiles…</div>
          <div v-else-if="!canonList.length" class="placeholder">No profiles in this range. 🎉</div>
          <div v-else class="muted small" style="margin-bottom:10px;">{{ canonList.length }} profiles · {{ canonMin }}–{{ canonMax }} games{{ canonOnlyIsolated ? ' · single-variant (no connections)' : '' }}</div>

          <div v-for="row in canonList" :key="row.canonical_id" class="canon-row">
            <div class="canon-info">
              <a :href="`/p/${encodeURIComponent(row.canonical_id)}`" target="_blank" class="canon-name">{{ row.display || row.canonical_id }}</a>
              <span class="muted small">{{ row.matches }} games · {{ row.variants }} variant{{ row.variants === 1 ? '' : 's' }}<span v-if="row.region"> · {{ row.region }}</span><span v-if="row.last_seen"> · last {{ String(row.last_seen).slice(0,10) }}</span></span>
            </div>
            <div class="canon-link">
              <input :value="canonLink[row.canonical_id]?.q || ''"
                     @input="(e) => { (canonLink[row.canonical_id] || (canonLink[row.canonical_id]={q:'',results:[],picked:null})).q = e.target.value; canonSearch(row.canonical_id) }"
                     placeholder="link into…" class="dd" style="width:160px;">
              <div v-if="canonLink[row.canonical_id]?.results?.length" class="canon-res">
                <button v-for="p in canonLink[row.canonical_id].results" :key="p.canonical_id" @click="canonPick(row.canonical_id, p)">
                  {{ p.display }} <span class="muted">{{ p.matches }}</span>
                </button>
              </div>
              <span v-if="canonLink[row.canonical_id]?.picked" class="picked-tag">→ {{ canonLink[row.canonical_id].picked.display }}</span>
            </div>
            <div class="canon-actions">
              <button class="btn sm" :disabled="!canonLink[row.canonical_id]?.picked" @click="canonAction(row, 'merge')">Link</button>
              <button class="btn sm ghost" @click="canonAction(row, 'keep')">Keep</button>
              <button class="btn sm danger" @click="canonAction(row, 'delete')">Delete</button>
            </div>
          </div>
        </template>

        <!-- SUPPORT TICKETS -->
        <template v-else-if="activeSection === 'support'">
          <div class="pane-head">
            <div>
              <h2>Support tickets</h2>
              <div class="scope">{{ tickets.filter(t => t.status !== 'resolved').length }} open · {{ tickets.length }} total</div>
            </div>
            <div class="actions">
              <button class="btn ghost" @click="loadSupport" :disabled="ticketsLoading">⟳ Refresh</button>
            </div>
          </div>

          <div v-if="claudeBrief" class="card" style="margin-bottom:14px; border-color: var(--accent);">
            <h3>Claude brief · ticket #{{ claudeBrief.id }} <span class="meta">copied to clipboard — paste into a Claude Code session <a class="link" @click="claudeBrief=null">dismiss</a></span></h3>
            <pre style="background:var(--bg); border:1px solid var(--border); padding:12px; border-radius:6px; font-size:11px; max-height:240px; overflow:auto; white-space:pre-wrap;">{{ claudeBrief.text }}</pre>
          </div>

          <div v-if="ticketsLoading && !tickets.length" class="placeholder">Loading tickets…</div>
          <div v-else-if="!tickets.length" class="placeholder">No tickets yet. 🎉</div>
          <div v-else class="card" style="padding:0;">
            <table class="deploy-table">
              <thead><tr><th>#</th><th>Area</th><th>Summary</th><th>From</th><th>Status</th><th>When</th><th></th></tr></thead>
              <tbody>
                <template v-for="t in tickets" :key="t.id">
                  <tr :class="{ active: t.status !== 'resolved' }" style="cursor:pointer;" @click="ticketOpen = ticketOpen === t.id ? null : t.id">
                    <td class="mono">{{ t.id }}</td>
                    <td class="small">{{ t.area || '—' }}</td>
                    <td>{{ t.title }}</td>
                    <td class="small muted">{{ t.username || t.email || 'anon' }}</td>
                    <td><span class="badge" :class="t.status === 'resolved' ? 'ok' : t.status === 'in_progress' ? 'info' : 'err'">{{ t.status }}</span></td>
                    <td class="small muted">{{ fmtDate(t.created_at) }}</td>
                    <td class="small">{{ ticketOpen === t.id ? '▾' : '▸' }}</td>
                  </tr>
                  <tr v-if="ticketOpen === t.id">
                    <td colspan="7" style="background:var(--panel-2);">
                      <div style="padding:6px 4px 12px;">
                        <div class="kv">
                          <span class="k">description</span><span class="v" style="white-space:pre-wrap;">{{ t.description }}</span>
                          <span class="k">page</span><span class="v">{{ t.page_url || '—' }}</span>
                          <span class="k">reporter</span><span class="v">{{ t.username || '—' }}<span v-if="t.canonical_id" class="muted"> · {{ t.canonical_id }}</span></span>
                          <span class="k">email</span><span class="v">{{ t.email || '—' }}<span v-if="t.email_status" class="muted"> · email {{ t.email_status }}</span></span>
                        </div>

                        <!-- Screenshots -->
                        <div v-if="t.attachments?.length" class="shots" @click.stop>
                          <img v-for="aid in t.attachments" :key="aid" :src="attBlobs[aid]"
                               class="shot-thumb" alt="screenshot" @click="lightbox = attBlobs[aid]">
                        </div>

                        <!-- Resolved: summary (user/email) on top, detail (admin) below -->
                        <div v-if="t.status === 'resolved'" class="resolved-box">
                          <div class="rb-label">Resolution summary <span class="muted">(sent to user)</span></div>
                          <div class="rb-summary">{{ t.resolution_summary || '—' }}</div>
                          <div v-if="t.resolution_detail" class="rb-label" style="margin-top:10px;">Detailed writeup <span class="muted">(admin)</span></div>
                          <div v-if="t.resolution_detail" class="rb-detail">{{ t.resolution_detail }}</div>
                        </div>

                        <!-- Open/in-progress: resolve form -->
                        <div v-else class="resolve-form" @click.stop>
                          <label>Resolution summary <span class="muted">(plain English — shown to the user{{ t.email ? ' + emailed' : '' }})</span>
                            <textarea v-model="(resolveForm[t.id] ||= {}).summary" rows="2" placeholder="What was fixed, in plain language…"></textarea>
                          </label>
                          <label>Detailed writeup <span class="muted">(admin — root cause, fix, prevention)</span>
                            <textarea v-model="(resolveForm[t.id] ||= {}).detail" rows="4" placeholder="Root cause · code change · how we'll prevent recurrence…"></textarea>
                          </label>
                        </div>

                        <div style="display:flex; gap:8px; margin-top:12px;">
                          <button class="btn sm" @click.stop="resolveWithClaude(t)">🤖 Resolve w/ Claude</button>
                          <button v-if="t.status !== 'resolved'" class="btn sm" @click.stop="resolveTicket(t)">Resolve &amp; notify</button>
                          <button v-else class="btn sm ghost" @click.stop="setTicketStatus(t, 'open')">Reopen</button>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <div v-if="lightbox" class="lightbox" @click="lightbox = ''">
            <img :src="lightbox" alt="screenshot">
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

/* Federation */
.av { width: 24px; height: 24px; border-radius: 50%; }
.claim-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--panel-2); font-size: 13px; }
.claim-row:last-child { border-bottom: 0; }
.claim-row .who { font-weight: 700; }
.claim-row .arrow { color: var(--fg-3); font-size: 11px; }
.claim-row .prof { color: var(--accent); font-weight: 600; }
.claim-row .spacer { flex: 1; }
.claim-row .link { color: var(--accent); text-decoration: none; }
.deploy-table .badge.ok { background: rgba(34,197,94,0.15); color: var(--win); }
.deploy-table .av { display: inline-block; }
.btn.sm { padding: 4px 10px; font-size: 11px; }
.pill { border: 1px solid; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; cursor: pointer; font-family: inherit; }
.pill.on { background: rgba(20,230,192,0.12); color: var(--accent); border-color: rgba(20,230,192,0.4); }
.pill.off { background: var(--panel-2); color: var(--fg-3); border-color: var(--border); }
.pill:hover { filter: brightness(1.2); }
.mono { font-family: 'JetBrains Mono', monospace; }

/* Ladder admin */
.ladder-grid { display: grid; grid-template-columns: 1fr 320px; gap: 12px; align-items: start; }
.form-grid { display: flex; flex-direction: column; gap: 10px; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }
.form-grid input, .form-grid select { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; border-radius: 6px; font-family: inherit; font-size: 13px; font-weight: 400; text-transform: none; letter-spacing: 0; }
.form-grid input:focus, .form-grid select:focus { outline: none; border-color: var(--accent); }
.slot { display: flex; flex-direction: column; gap: 4px; }
.slot-picked { display: flex; align-items: center; justify-content: space-between; background: rgba(20,230,192,0.1); border: 1px solid rgba(20,230,192,0.3); border-radius: 6px; padding: 8px 12px; font-size: 13px; }
.slot-picked .x { background: none; border: 0; color: var(--fg-3); cursor: pointer; }
.slot-res { display: flex; flex-direction: column; gap: 3px; }
.slot-res button { text-align: left; background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); border-radius: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; font-family: inherit; }
.slot-res button:hover { border-color: var(--accent); }
.slot-res .muted { color: var(--fg-3); }

/* Canonicalize queue */
.canon-row { display: grid; grid-template-columns: 1fr 220px auto; gap: 14px; align-items: center; padding: 10px 14px; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 8px; }
.canon-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.canon-name { font-weight: 700; color: var(--fg); text-decoration: none; }
.canon-name:hover { color: var(--accent); }
.canon-link { position: relative; }
.canon-res { position: absolute; top: 100%; left: 0; right: 0; z-index: 5; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; margin-top: 4px; max-height: 220px; overflow-y: auto; }
.canon-res button { display: block; width: 100%; text-align: left; background: none; border: 0; color: var(--fg); padding: 7px 10px; font-size: 12px; cursor: pointer; font-family: inherit; }
.canon-res button:hover { background: var(--panel-3); }
.canon-res .muted { color: var(--fg-3); }
.picked-tag { display: inline-block; margin-top: 4px; font-size: 11px; color: var(--accent); }
.canon-actions { display: flex; gap: 6px; }
.link-res { position: absolute; top: 100%; left: 0; z-index: 20; min-width: 200px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; margin-top: 4px; max-height: 240px; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
.link-res button { display: block; width: 100%; text-align: left; background: none; border: 0; color: var(--fg); padding: 7px 10px; font-size: 12px; cursor: pointer; font-family: inherit; }
.link-res button:hover { background: var(--panel-3); }
.link-res .muted { color: var(--fg-3); }
.btn.danger { background: rgba(239,68,68,0.15); color: var(--loss); }
.btn.danger:hover { background: rgba(239,68,68,0.28); }
/* Support resolution */
.resolved-box { margin-top: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.rb-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--fg-3); font-weight: 700; }
.rb-summary { color: var(--win); font-size: 13px; margin-top: 4px; white-space: pre-wrap; }
.rb-detail { color: var(--fg-2); font-size: 12px; margin-top: 4px; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; }
.resolve-form { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.resolve-form label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.resolve-form .muted { text-transform: none; font-weight: 400; }
.resolve-form textarea { background: var(--panel); border: 1px solid var(--border); color: var(--fg); border-radius: 6px; padding: 8px 10px; font-family: inherit; font-size: 13px; font-weight: 400; resize: vertical; }
.resolve-form textarea:focus { outline: none; border-color: var(--accent); }
.del-by-id { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 4px 0 14px; padding: 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; }
/* Support screenshots */
.shots { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.shot-thumb { width: 88px; height: 88px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); cursor: zoom-in; background: var(--bg); }
.shot-thumb:hover { border-color: var(--accent); }
.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; z-index: 200; cursor: zoom-out; padding: 30px; }
.lightbox img { max-width: 95vw; max-height: 92vh; border-radius: 8px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); }
</style>

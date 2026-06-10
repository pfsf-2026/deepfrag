<script setup>
// KOTH ladder admin — accessible to ANY Discord-authed admin (Cronus/Nin/Bance),
// NOT behind the SYNC_SECRET god panel. Auth is the user's Discord JWT; the
// backend's _check_ladder_admin accepts is_admin users here. Surfaces the
// ladder-management actions co-admins share: approve pending teams, seed teams,
// report results / forfeits. (The full /admin panel stays Peter's god key only.)
const { user, loggedIn, ready, authHeader, fetchMe, login } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const ladder = ref(null)
const teams = ref([])
const challenges = ref([])
const pending = ref([])
const loading = ref(false)
const msg = ref('')
const err = ref('')

const isAdmin = computed(() => loggedIn.value && user.value?.is_admin)

const newTeam = ref({ name: '', members: '', rung: '' })
const report = ref(null)  // challenge being reported
const schedulerC = ref(null)  // challenge being scheduled (admin can act either side)
const editTeam = ref(null)  // team being edited (roster/name/tag/logo)
function startEditTeam(t) {
  // AddTeam expects {id, name, tag, members:[{id,display}], has_logo}
  editTeam.value = { id: t.id, name: t.name, tag: t.tag || '', members: t.members || [], has_logo: t.has_logo }
}
function onTeamEdited() { editTeam.value = null; note('team updated'); load() }
const supportTickets = ref([])  // ladder-area tickets (read-only monitoring)
const ticketOpen = ref(null)
function fmtTicketDate(s) { return s ? new Date(s).toLocaleString() : '—' }
// Screenshots are admin-gated → fetch as authed blobs and cache object URLs.
const attBlobs = ref({})
const lightbox = ref('')
async function loadAttachment(id) {
  if (attBlobs.value[id]) return
  try {
    const blob = await $fetch(`${base}/api/admin/support/attachment/${id}`, { headers: authHeader(), responseType: 'blob' })
    attBlobs.value = { ...attBlobs.value, [id]: URL.createObjectURL(blob) }
  } catch { /* skip */ }
}
watch(ticketOpen, (id) => {
  const t = supportTickets.value.find(x => x.id === id)
  ;(t?.attachments || []).forEach(loadAttachment)
})
const reportForm = ref({ winner_id: null, score_a: 2, score_b: 0, hub: '' })

onMounted(async () => {
  await fetchMe()
  if (isAdmin.value) await load()
})

function note(m) { msg.value = m; setTimeout(() => { if (msg.value === m) msg.value = '' }, 4000) }

async function load() {
  loading.value = true
  err.value = ''
  try {
    const list = await $fetch(`${base}/api/ladder`, { query: { _: Date.now() } })
    ladder.value = (list.ladders || [])[0] || null
    if (ladder.value) {
      const d = await $fetch(`${base}/api/ladder/${ladder.value.id}`, { query: { _: Date.now() } })
      teams.value = d.teams || []
      order.value = [...teams.value]
      orderDirty.value = false
      challenges.value = d.challenges || []
      const p = await $fetch(`${base}/api/admin/ladder/${ladder.value.id}/teams/pending`, { headers: authHeader() })
      pending.value = p.pending || []
      try {
        const s = await $fetch(`${base}/api/admin/ladder/support`, { headers: authHeader() })
        supportTickets.value = s.tickets || []
      } catch { supportTickets.value = [] }
    }
  } catch (e) {
    err.value = e?.data?.detail || e?.message || 'load failed'
  } finally {
    loading.value = false
  }
}

// Drag-and-drop reorder of the standings.
const order = ref([])
const orderDirty = ref(false)
const dragIdx = ref(null)
function onDragStart(i) { dragIdx.value = i }
function onDrop(i) {
  if (dragIdx.value === null || dragIdx.value === i) return
  const arr = [...order.value]
  const [m] = arr.splice(dragIdx.value, 1)
  arr.splice(i, 0, m)
  order.value = arr
  dragIdx.value = null
  orderDirty.value = true
}
async function saveOrder() {
  try {
    await $fetch(`${base}/api/admin/ladder/${ladder.value.id}/reorder`, {
      method: 'POST', headers: authHeader(), body: { order: order.value.map(t => t.id) }
    })
    note('ladder reordered'); await load()
  } catch (e) { err.value = e?.data?.detail || 'reorder failed' }
}

async function approve(t) {
  try { await $fetch(`${base}/api/admin/ladder/team/${t.id}/approve`, { method: 'POST', headers: authHeader() }); note(`approved ${t.name}`); await load() }
  catch (e) { err.value = e?.data?.detail || 'approve failed' }
}
async function reject(t) {
  try { await $fetch(`${base}/api/admin/ladder/team/${t.id}/reject`, { method: 'POST', headers: authHeader() }); note(`rejected ${t.name}`); await load() }
  catch (e) { err.value = e?.data?.detail || 'reject failed' }
}
async function addTeam() {
  if (!newTeam.value.name) return
  const members = newTeam.value.members.split(',').map(s => s.trim()).filter(Boolean)
  try {
    await $fetch(`${base}/api/admin/ladder/${ladder.value.id}/teams`, {
      method: 'POST', headers: authHeader(),
      body: { name: newTeam.value.name, members, rung: newTeam.value.rung === '' ? null : Number(newTeam.value.rung) }
    })
    note(`added ${newTeam.value.name}`); newTeam.value = { name: '', members: '', rung: '' }; await load()
  } catch (e) { err.value = e?.data?.detail || 'add failed' }
}
function teamName(id) { return teams.value.find(t => t.id === id)?.name || `#${id}` }
const newChal = ref({ challenger: null, challenged: null })
async function createChallenge() {
  if (!newChal.value.challenger || !newChal.value.challenged) return
  try {
    await $fetch(`${base}/api/ladder/${ladder.value.id}/challenge`, {
      method: 'POST', headers: authHeader(),
      body: { challenger_id: Number(newChal.value.challenger), challenged_id: Number(newChal.value.challenged) }
    })
    note('challenge created'); newChal.value = { challenger: null, challenged: null }; await load()
  } catch (e) { err.value = e?.data?.detail || 'create challenge failed' }
}
// Report flow: pull candidate hub games (may be >3 — warmups/re-dos) and let the
// admin tick the decisive Bo3 maps in order. Only ticked games count.
const candGames = ref([])        // [{hub_game_id, map, a_frags, b_frags, winner, played_at, pick(0-based order)}]
const candLoading = ref(false)
const candInfo = ref(null)       // {a_name,b_name,challenger_id,challenged_id}
const autoDetected = ref(false)
async function startReport(c) {
  report.value = c
  candGames.value = []; candInfo.value = null; candLoading.value = true; autoDetected.value = false
  try {
    const r = await $fetch(`${base}/api/admin/ladder/challenge/${c.id}/candidate-games`, { headers: authHeader() })
    candInfo.value = r
    // Pre-tick the auto-detected decisive Bo3 maps; admin reviews + confirms.
    candGames.value = (r.candidates || []).map(g => ({ ...g, picked: !!g.suggested }))
    autoDetected.value = r.suggested_complete && candGames.value.some(g => g.picked)
  } catch (e) { err.value = e?.data?.detail || 'could not load games' } finally { candLoading.value = false }
}
function toggleGame(g) { g.picked = !g.picked }
// Derived from the ticked games (challenger=a, challenged=b).
const picked = computed(() => candGames.value.filter(g => g.picked))
const reportScore = computed(() => {
  let a = 0, b = 0
  for (const g of picked.value) { if (g.winner === 'a') a++; else if (g.winner === 'b') b++ }
  return { a, b }
})
const reportWinnerId = computed(() => {
  const { a, b } = reportScore.value
  if (a === b) return null
  return a > b ? candInfo.value?.challenger_id : candInfo.value?.challenged_id
})
const reportValid = computed(() => {
  const { a, b } = reportScore.value
  const n = picked.value.length
  // Bo3 only: first to 2 (2-0 or 2-1). Extra games don't count.
  return n >= 2 && n <= 3 && Math.max(a, b) === 2
})
async function submitReport() {
  const c = report.value
  if (!reportValid.value) { err.value = 'Pick the decisive Bo3 maps — a 2–0 or 2–1 (first to 2). Extra games don\'t count.'; return }
  const maps = picked.value.map(g => ({ map: g.map, a_frags: g.a_frags, b_frags: g.b_frags, hub_game_id: g.hub_game_id }))
  try {
    await $fetch(`${base}/api/admin/ladder/challenge/${c.id}/result`, {
      method: 'POST', headers: authHeader(),
      body: { winner_id: reportWinnerId.value, score_a: reportScore.value.a, score_b: reportScore.value.b, maps }
    })
    note('result recorded'); report.value = null; await load()
  } catch (e) { err.value = e?.data?.detail || 'report failed' }
}
async function forfeit(c) {
  try { await $fetch(`${base}/api/admin/ladder/challenge/${c.id}/forfeit`, { method: 'POST', headers: authHeader() }); note('forfeit recorded'); await load() }
  catch (e) { err.value = e?.data?.detail || 'forfeit failed' }
}
const ladderOpen = computed(() => !!ladder.value?.rules?.open)
async function toggleOpen() {
  try {
    await $fetch(`${base}/api/admin/ladder/${ladder.value.id}/open`, {
      method: 'POST', headers: authHeader(), body: { open: !ladderOpen.value }
    })
    note(ladderOpen.value ? 'ladder closed' : 'ladder opened'); await load()
  } catch (e) { err.value = e?.data?.detail || 'toggle failed' }
}
async function cancelChallenge(c) {
  try { await $fetch(`${base}/api/admin/ladder/challenge/${c.id}/cancel`, { method: 'POST', headers: authHeader() }); note('challenge cancelled'); await load() }
  catch (e) { err.value = e?.data?.detail || 'cancel failed' }
}

// ── Reschedule a scheduled match (admin) ────────────────────────────────────
// The ladder is ET-anchored, so the admin enters the new time in ET; convert to
// a UTC instant (browser-tz-independent) before sending.
const ET_ZONE = 'America/New_York'
const reschedC = ref(null)     // challenge being rescheduled
const reschedVal = ref('')     // datetime-local string, ET wall clock
const reschedSrv = ref('')     // server hostname
const reschedSugs = ref([])    // ping-based server suggestions
function utcToEtInput(iso) {
  const p = new Intl.DateTimeFormat('en-CA', { timeZone: ET_ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(new Date(iso))
  const g = t => p.find(x => x.type === t).value
  let hh = g('hour'); if (hh === '24') hh = '00'
  return `${g('year')}-${g('month')}-${g('day')}T${hh}:${g('minute')}`
}
function etInputToUtc(s) {
  const [date, time] = s.split('T')
  const [y, mo, d] = date.split('-').map(Number)
  const [h, mi] = time.split(':').map(Number)
  const asUTC = Date.UTC(y, mo - 1, d, h, mi, 0)
  const inst = new Date(asUTC)
  const etMs = new Date(inst.toLocaleString('en-US', { timeZone: ET_ZONE })).getTime()
  const utcMs = new Date(inst.toLocaleString('en-US', { timeZone: 'UTC' })).getTime()
  return new Date(asUTC + (utcMs - etMs)).toISOString()
}
async function startReschedule(c) {
  reschedC.value = c
  reschedVal.value = c.agreed_at ? utcToEtInput(c.agreed_at) : ''
  reschedSrv.value = c.server || ''
  reschedSugs.value = []
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/server-suggestion`)
    reschedSugs.value = r.suggestions || []
  } catch { reschedSugs.value = [] }
}
async function doReschedule() {
  if (!reschedVal.value) { err.value = 'pick a new time'; return }
  const c = reschedC.value
  try {
    await $fetch(`${base}/api/admin/ladder/challenge/${c.id}/reschedule`, {
      method: 'POST', headers: authHeader(),
      body: { slot: etInputToUtc(reschedVal.value), server: reschedSrv.value || null }
    })
    note('rescheduled — Discord updated'); reschedC.value = null; await load()
  } catch (e) { err.value = e?.data?.detail || 'reschedule failed' }
}

useHead({ title: 'KOTH Admin · DeepFrag' })
</script>

<template>
  <div class="wrap">
    <h1>KOTH Ladder — Admin</h1>

    <ClientOnly>
      <div v-if="!ready" class="muted pad">Loading…</div>
      <div v-else-if="!loggedIn" class="gate">
        <p>Sign in with Discord to manage the ladder.</p>
        <button class="cta" @click="login">Sign in with Discord</button>
      </div>
      <div v-else-if="!isAdmin" class="gate">
        <p>Your account ({{ user?.global_name || user?.username }}) isn't a ladder admin. Ask Cronus to grant access.</p>
      </div>

      <template v-else>
        <p v-if="msg" class="ok-note">{{ msg }}</p>
        <p v-if="err" class="err-note">{{ err }}</p>
        <div v-if="!ladder" class="muted pad">No ladder yet — create it in the /admin panel.</div>

        <template v-else>
          <!-- Ladder status / open toggle -->
          <section class="card" :style="{ borderColor: ladderOpen ? 'rgba(34,197,94,0.4)' : 'rgba(245,158,11,0.4)' }">
            <h2>
              Ladder status: <span :style="{ color: ladderOpen ? 'var(--win)' : 'var(--draw)' }">{{ ladderOpen ? 'OPEN' : 'not open' }}</span>
              <span class="muted small">· {{ teams.length }} teams seeded</span>
              <button class="btn sm" style="margin-left:auto;" @click="toggleOpen">{{ ladderOpen ? 'Close ladder' : 'Open ladder' }}</button>
            </h2>
            <p class="muted small">Closed = pre-launch: players can't challenge (board shows a "not open yet" banner); you can still arrange challenges here for testing. Open it once ~10 teams are seeded.</p>
          </section>

          <!-- Pending team approvals -->
          <section class="card">
            <h2>Pending teams <span class="count">{{ pending.length }}</span></h2>
            <div v-if="!pending.length" class="muted small">No pending signups.</div>
            <div v-for="t in pending" :key="t.id" class="prow">
              <img v-if="t.has_logo" :src="`${base}/api/ladder/team/${t.id}/logo`" class="tlogo" alt="">
              <div class="pinfo">
                <strong>{{ t.name }}</strong>
                <span class="muted small">{{ (t.members || []).map(m => m.display).join(' · ') || '—' }}</span>
              </div>
              <span class="spacer" />
              <button class="btn sm ghost" @click="startEditTeam(t)">Edit</button>
              <button class="btn sm" @click="approve(t)">Approve</button>
              <button class="btn sm ghost" @click="reject(t)">Reject</button>
            </div>
          </section>

          <!-- Standings (drag to reorder) -->
          <section class="card">
            <h2>Standings <span class="muted small">— drag rows to reorder</span>
              <button v-if="orderDirty" class="btn sm" style="margin-left:auto;" @click="saveOrder">Save order</button>
            </h2>
            <div v-for="(t, i) in order" :key="t.id" class="srow drag" :class="{ top: i === 0, dragging: dragIdx === i }"
                 draggable="true" @dragstart="onDragStart(i)" @dragover.prevent @drop="onDrop(i)">
              <span class="grip">⠿</span>
              <span class="rung">{{ i + 1 }}</span>
              <img v-if="t.has_logo" :src="`${base}/api/ladder/team/${t.id}/logo`" class="tlogo" alt="">
              <strong>{{ t.name }}</strong>
              <span class="muted small">{{ (t.members || []).map(m => m.display).join(' · ') }}</span>
              <span class="spacer" />
              <button class="btn sm ghost" draggable="false" @click.stop="startEditTeam(t)">Edit</button>
            </div>
            <div v-if="!order.length" class="muted small">No teams placed yet.</div>
          </section>

          <!-- Open challenges -->
          <section v-if="challenges.length" class="card">
            <h2>Open challenges</h2>
            <div v-for="c in challenges" :key="c.id" class="prow">
              <strong>{{ teamName(c.challenger_id) }}</strong>
              <span class="muted">vs</span>
              <strong>{{ teamName(c.challenged_id) }}</strong>
              <span class="muted small">{{ c.agreed_at ? ('📅 ' + new Date(c.agreed_at).toLocaleString()) : ((c.proposed||[]).length ? 'awaiting pick' : 'awaiting availability') }}</span>
              <span class="spacer" />
              <button class="btn sm" @click="schedulerC = c">Schedule</button>
              <button v-if="c.agreed_at" class="btn sm ghost" @click="startReschedule(c)">Reschedule</button>
              <button class="btn sm ghost" @click="startReport(c)">Report</button>
              <button class="btn sm ghost" @click="forfeit(c)">Forfeit</button>
              <button class="btn sm danger" @click="cancelChallenge(c)">Cancel</button>
              <div v-if="reschedC && reschedC.id === c.id" class="resched" @click.stop>
                <div class="resched-row">
                  <span class="muted small">New time (ET):</span>
                  <input type="datetime-local" step="900" v-model="reschedVal">
                </div>
                <div class="resched-row">
                  <span class="muted small">Server:</span>
                  <input type="text" v-model="reschedSrv" placeholder="server hostname" style="min-width:200px;">
                </div>
                <div v-if="reschedSugs.length" class="resched-row" style="flex-wrap:wrap;">
                  <span class="muted small">Suggested:</span>
                  <button v-for="s in reschedSugs" :key="s.host" class="srv-chip" :class="{ on: reschedSrv === s.host }" @click="reschedSrv = s.host">
                    <strong>{{ s.host }}</strong>
                    <span class="muted">{{ s.city || s.country || 'NA' }} · worst {{ s.max_ping }}ms</span>
                  </button>
                </div>
                <div class="resched-row">
                  <button class="btn sm" @click="doReschedule">Save &amp; notify</button>
                  <button class="btn sm ghost" @click="reschedC = null">Cancel</button>
                </div>
              </div>
            </div>
          </section>

          <!-- Ladder support tickets (read-only monitoring) -->
          <section class="card">
            <h2>Support tickets <span class="count">{{ supportTickets.filter(t => t.status !== 'resolved').length }} open</span></h2>
            <p class="muted small">Ladder-related reports (read-only). Resolving happens in the main admin panel.</p>
            <div v-if="!supportTickets.length" class="muted small">No ladder tickets.</div>
            <div v-for="t in supportTickets" :key="t.id" class="srow" style="flex-wrap:wrap; cursor:pointer;" @click="ticketOpen = ticketOpen === t.id ? null : t.id">
              <span class="rung">#{{ t.id }}</span>
              <strong>{{ t.title }}</strong>
              <span class="muted small">{{ t.username || t.email || 'anon' }}</span>
              <span class="spacer" />
              <span class="badge" :class="t.status === 'resolved' ? 'ok' : t.status === 'in_progress' ? 'info' : 'warn'">{{ t.status }}</span>
              <div v-if="ticketOpen === t.id" style="flex-basis:100%; margin-top:8px; color:var(--fg-2); font-size:13px; white-space:pre-wrap;">
                {{ t.description }}
                <div v-if="t.attachments?.length" class="shots" @click.stop>
                  <img v-for="aid in t.attachments" :key="aid" :src="attBlobs[aid]" class="shot-thumb" alt="screenshot" @click="lightbox = attBlobs[aid]">
                </div>
                <div v-if="t.resolution_summary" style="margin-top:8px; color:var(--win);">✓ {{ t.resolution_summary }}</div>
                <div class="muted small" style="margin-top:6px;">opened {{ fmtTicketDate(t.created_at) }}<span v-if="t.resolved_at"> · resolved {{ fmtTicketDate(t.resolved_at) }}</span></div>
              </div>
            </div>
          </section>
          <div v-if="lightbox" class="lightbox" @click="lightbox = ''"><img :src="lightbox" alt="screenshot"></div>

          <!-- Create challenge (admin-arranged matchup) -->
          <section class="card">
            <h2>Create challenge</h2>
            <div class="form">
              <select v-model="newChal.challenger">
                <option :value="null">Challenger…</option>
                <option v-for="t in teams" :key="t.id" :value="t.id">#{{ t.rung }} {{ t.name }}</option>
              </select>
              <span class="muted">vs</span>
              <select v-model="newChal.challenged">
                <option :value="null">Challenged…</option>
                <option v-for="t in teams" :key="t.id" :value="t.id">#{{ t.rung }} {{ t.name }}</option>
              </select>
              <button class="btn" @click="createChallenge">Create</button>
            </div>
            <p class="muted small" style="margin-top:6px;">Challenger must be 1–2 rungs below the challenged team. As admin you can arrange any valid matchup, then schedule it below / on the board.</p>
          </section>

          <!-- Manual add/seed team -->
          <section class="card">
            <h2>Add / seed team</h2>
            <div class="form">
              <input v-model="newTeam.name" placeholder="Team name">
              <input v-model="newTeam.members" placeholder="members (canonical_ids, comma-sep)">
              <input v-model="newTeam.rung" type="number" placeholder="rung (blank=bottom)" style="width:120px;">
              <button class="btn" @click="addTeam">Add</button>
            </div>
          </section>
        </template>
      </template>
    </ClientOnly>

    <!-- Scheduler (admin can fill availability OR pick a time for either side) -->
    <Scheduler v-if="schedulerC" :challenge="schedulerC" :user-team-id="null"
               @done="schedulerC = null; load()" @saved="load" @close="schedulerC = null" />

    <!-- Team editor (admin: fix roster / add a missing teammate, name, tag, logo) -->
    <AddTeam v-if="editTeam && ladder" :ladder-id="ladder.id" :edit-team="editTeam"
             @done="onTeamEdited" @close="editTeam = null" />

    <!-- Report modal -->
    <div v-if="report" class="modal-bg" @click.self="report = null">
      <div class="modal" style="max-width:560px;">
        <h3>Report result · {{ teamName(report.challenger_id) }} vs {{ teamName(report.challenged_id) }}</h3>
        <p class="muted small" style="margin:-6px 0 12px;">Tick the <strong>decisive Bo3 maps</strong> (first to 2 — a 2–0 or 2–1). Extra games are just for fun and <strong>don't count</strong>. Auto-detect pre-ticks the decisive set; adjust if it grabbed a warm-up.</p>

        <div v-if="autoDetected" class="auto-banner">🤖 Auto-detected Bo3 — review the pre-ticked maps and confirm. Untick a warm-up / extra game if needed.</div>
        <div v-if="candLoading" class="muted small pad">Finding played games…</div>
        <div v-else-if="!candGames.length" class="muted small" style="padding:8px 0;">
          No ingested 2on2 games found for these two teams yet. They appear here ~within the 2h sync after the match is played (rosters must be linked to profiles).
        </div>
        <div v-else class="cand-list">
          <label v-for="g in candGames" :key="g.hub_game_id" class="cand" :class="{ on: g.picked }">
            <input type="checkbox" :checked="g.picked" @change="toggleGame(g)">
            <span class="cand-map">{{ g.map || '?' }}</span>
            <span class="cand-score">
              <b :class="{ win: g.winner==='a' }">{{ g.a_frags }}</b>–<b :class="{ win: g.winner==='b' }">{{ g.b_frags }}</b>
            </span>
            <span class="cand-win">{{ g.winner==='a' ? teamName(report.challenger_id) : g.winner==='b' ? teamName(report.challenged_id) : 'tie' }}</span>
            <span class="cand-time">{{ new Date(g.played_at).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}) }}</span>
          </label>
        </div>

        <div v-if="candGames.length" class="report-sum" :class="{ ok: reportValid, bad: picked.length && !reportValid }">
          <span>{{ teamName(report.challenger_id) }} <b>{{ reportScore.a }}</b> – <b>{{ reportScore.b }}</b> {{ teamName(report.challenged_id) }}</span>
          <span v-if="reportValid" class="winner">🏆 {{ teamName(reportWinnerId) }}</span>
          <span v-else-if="picked.length" class="hint">need a 2–0 or 2–1 (Bo3, first to 2)</span>
        </div>

        <div class="m-actions">
          <button class="btn ghost" @click="report = null">Cancel</button>
          <button class="btn" :disabled="!reportValid" @click="submitReport">Save result</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { max-width: 760px; margin: 0 auto; padding: 32px 24px 80px; }
h1 { font-size: 24px; font-weight: 900; margin: 0 0 20px; }
.gate { text-align: center; padding: 50px 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; }
.gate p { color: var(--fg-2); margin-bottom: 16px; }
.cta { background: #5865f2; color: #fff; border: 0; padding: 10px 18px; border-radius: 9px; font-weight: 700; cursor: pointer; }
.muted { color: var(--fg-2); }
.small { font-size: 12px; }
.pad { padding: 30px 0; text-align: center; }
.ok-note { background: rgba(34,197,94,0.12); color: #86efac; padding: 8px 14px; border-radius: 8px; font-size: 13px; }
.err-note { background: rgba(239,68,68,0.12); color: #fca5a5; padding: 8px 14px; border-radius: 8px; font-size: 13px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; margin-bottom: 16px; }
.card h2 { font-size: 15px; font-weight: 800; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }
.card h2 .count { background: var(--panel-2); color: var(--fg-2); border-radius: 999px; padding: 1px 8px; font-size: 12px; }
.prow, .srow { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-top: 1px solid var(--border); font-size: 14px; }
.card .prow:first-of-type, .card .srow:first-of-type { border-top: 0; }
.prow .spacer { flex: 1; }
.pinfo { display: flex; flex-direction: column; }
.srow .rung { font-family: 'JetBrains Mono', monospace; color: var(--fg-3); width: 24px; }
.srow.drag { cursor: grab; }
.srow.drag:hover { background: var(--panel-2); }
.srow.dragging { opacity: 0.4; }
.srow .grip { color: var(--fg-3); cursor: grab; font-size: 14px; }
.card h2 { display: flex; align-items: center; gap: 8px; }
.srow.top { color: var(--draw); }
.tlogo { width: 26px; height: 26px; border-radius: 6px; object-fit: cover; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 8px 14px; border-radius: 7px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.sm { padding: 5px 11px; font-size: 12px; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.auto-banner { background: rgba(20,230,192,.1); border: 1px solid rgba(20,230,192,.4); color: var(--accent-2, #5eead4); border-radius: 8px; padding: 8px 11px; font-size: 12px; margin-bottom: 10px; }
.cand-list { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; margin-bottom: 12px; }
.cand { display: flex; align-items: center; gap: 10px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 11px; cursor: pointer; font-size: 13px; }
.cand.on { border-color: var(--accent); background: rgba(20,230,192,0.08); }
.cand-map { font-family: 'JetBrains Mono', monospace; font-weight: 700; width: 76px; }
.cand-score { font-family: 'JetBrains Mono', monospace; width: 72px; color: var(--fg-3); }
.cand-score b { color: var(--fg-2); } .cand-score b.win { color: var(--accent); }
.cand-win { flex: 1; color: var(--fg-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cand-time { color: var(--fg-3); font-size: 11px; font-family: 'JetBrains Mono', monospace; }
.report-sum { display: flex; align-items: center; gap: 12px; padding: 9px 12px; border-radius: 8px; background: var(--panel-2); border: 1px solid var(--border); font-size: 14px; margin-bottom: 12px; }
.report-sum.ok { border-color: rgba(34,197,94,0.5); }
.report-sum.bad { border-color: rgba(245,158,11,0.5); }
.report-sum .winner { margin-left: auto; color: var(--win); font-weight: 700; }
.report-sum .hint { margin-left: auto; color: var(--draw); font-size: 12px; }
.btn.danger { background: rgba(239,68,68,0.15); color: var(--loss); }
.btn.danger:hover { background: rgba(239,68,68,0.28); }
.badge { padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.badge.ok { background: rgba(34,197,94,0.15); color: var(--win); }
.badge.info { background: rgba(74,159,255,0.15); color: var(--accent-2); }
.badge.warn { background: rgba(245,158,11,0.15); color: var(--draw); }
.form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.form.col { flex-direction: column; align-items: stretch; }
.form input, .form select { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; border-radius: 7px; font-family: inherit; font-size: 13px; flex: 1; min-width: 120px; }
.form.col label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--fg-3); }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px 24px; width: 100%; max-width: 380px; }
.modal h3 { margin: 0 0 14px; font-size: 18px; font-weight: 800; }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.resched { flex-basis: 100%; display: flex; flex-direction: column; gap: 8px; margin-top: 8px; padding: 10px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; }
.resched-row { display: flex; gap: 8px; align-items: center; }
.resched input { background: var(--panel); border: 1px solid var(--border); color: var(--fg); border-radius: 8px; padding: 7px 10px; font-family: inherit; font-size: 13px; }
.resched input:focus { outline: none; border-color: var(--accent); }
.srv-chip { display: inline-flex; gap: 6px; align-items: baseline; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 5px 10px; font-size: 12px; color: var(--fg); cursor: pointer; font-family: inherit; }
.srv-chip:hover { border-color: var(--accent); }
.srv-chip.on { border-color: var(--accent); background: rgba(20,230,192,0.08); }
.srv-chip .muted { font-size: 11px; }
.shots { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.shot-thumb { width: 80px; height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); cursor: zoom-in; background: var(--bg); }
.shot-thumb:hover { border-color: var(--accent); }
.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; z-index: 200; cursor: zoom-out; padding: 30px; }
.lightbox img { max-width: 95vw; max-height: 92vh; border-radius: 8px; }
</style>

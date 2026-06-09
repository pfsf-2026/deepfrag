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
const supportTickets = ref([])  // ladder-area tickets (read-only monitoring)
const ticketOpen = ref(null)
function fmtTicketDate(s) { return s ? new Date(s).toLocaleString() : '—' }
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
function startReport(c) { report.value = c; reportForm.value = { winner_id: c.challenger_id, score_a: 2, score_b: 0, hub: '' } }
async function submitReport() {
  const c = report.value
  const maps = reportForm.value.hub ? reportForm.value.hub.split(',').map(h => ({ hub_game_id: h.trim() })).filter(m => m.hub_game_id) : []
  try {
    await $fetch(`${base}/api/admin/ladder/challenge/${c.id}/result`, {
      method: 'POST', headers: authHeader(),
      body: { winner_id: Number(reportForm.value.winner_id), score_a: Number(reportForm.value.score_a), score_b: Number(reportForm.value.score_b), maps }
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
              <button class="btn sm ghost" @click="startReport(c)">Report</button>
              <button class="btn sm ghost" @click="forfeit(c)">Forfeit</button>
              <button class="btn sm danger" @click="cancelChallenge(c)">Cancel</button>
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
                <div v-if="t.resolution_summary" style="margin-top:8px; color:var(--win);">✓ {{ t.resolution_summary }}</div>
                <div class="muted small" style="margin-top:6px;">opened {{ fmtTicketDate(t.created_at) }}<span v-if="t.resolved_at"> · resolved {{ fmtTicketDate(t.resolved_at) }}</span></div>
              </div>
            </div>
          </section>

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

    <!-- Report modal -->
    <div v-if="report" class="modal-bg" @click.self="report = null">
      <div class="modal">
        <h3>Report result</h3>
        <div class="form col">
          <label>Winner
            <select v-model="reportForm.winner_id">
              <option :value="report.challenger_id">{{ teamName(report.challenger_id) }}</option>
              <option :value="report.challenged_id">{{ teamName(report.challenged_id) }}</option>
            </select>
          </label>
          <label>Score (challenger)<input v-model="reportForm.score_a" type="number"></label>
          <label>Score (challenged)<input v-model="reportForm.score_b" type="number"></label>
          <label>Hub game IDs (comma-sep, optional)<input v-model="reportForm.hub"></label>
        </div>
        <div class="m-actions">
          <button class="btn ghost" @click="report = null">Cancel</button>
          <button class="btn" @click="submitReport">Save</button>
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
</style>

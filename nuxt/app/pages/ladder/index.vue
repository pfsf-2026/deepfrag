<script setup>
// King of the Hill (KOTH) 2v2 ladder — public standings board. Reads /api/ladder (active
// ladders) then /api/ladder/{id} for the ranked rungs, King of the Hill, and
// open challenges. Captain self-serve (challenge/report) is Discord-gated and
// lands on top of this once OAuth is live.
const df = useDeepFrag()
const { user, loggedIn, login } = useAuth()
const showSettings = useState('show-settings', () => false)
const openTeamSettings = useState('open-team-settings', () => false)
// Prompt linked players who haven't set a location (state is the required field).
const needsLocation = computed(() => loggedIn.value && user.value?.canonical_id && !user.value?.state)
// Show the claim flow when signed in but not yet linked to a profile (and no
// pending claim already in flight).
const needsClaim = computed(() => loggedIn.value && user.value && !user.value.canonical_id && !user.value.pending_claim)
const showAddTeam = ref(false)
const showAvail = useState('show-availability', () => false)   // editor mounted in app.vue
const editingTeam = ref(null)        // team object being edited (Team Settings)
const teamSubmitted = ref('')
// Already rostered on an active team? (pending teams aren't in standings.)
const onTeam = computed(() => {
  const cid = user.value?.canonical_id
  return !!cid && teams.value.some(t => (t.members || []).some(m => m.id === cid))
})
// Linked player, not yet on a team, ladder is open → can register a team.
const canAddTeam = computed(() => loggedIn.value && user.value?.canonical_id && ladder.value && !onTeam.value)
function isMyTeam(t) {
  const cid = user.value?.canonical_id
  return (!!cid && (t.members || []).some(m => m.id === cid)) || !!user.value?.is_admin
}
// The current user's own active team (for challenge eligibility).
const myTeam = computed(() => {
  const cid = user.value?.canonical_id
  if (!cid) return null
  return teams.value.find(t => (t.members || []).some(m => m.id === cid)) || null
})
const myOpenChallenge = computed(() => {
  if (!myTeam.value) return null
  return challenges.value.find(c => c.challenger_id === myTeam.value.id || c.challenged_id === myTeam.value.id) || null
})
// Pre-launch: challenging is off until an admin opens the ladder (rules.open).
const ladderOpen = computed(() => !!ladder.value?.rules?.open)
const TEAMS_TO_OPEN = 10
// Can I challenge team t? Ladder must be open, t 1-2 rungs above me, no open challenge.
function canChallenge(t) {
  if (!ladderOpen.value) return false
  if (!myTeam.value || !myTeam.value.rung || !t.rung || myOpenChallenge.value) return false
  const gap = myTeam.value.rung - t.rung
  return gap === 1 || gap === 2
}
const challengeErr = ref('')
const schedulerChallenge = ref(null)
async function doChallenge(t) {
  challengeErr.value = ''
  try {
    await $fetch(`${base}/api/ladder/${ladder.value.id}/challenge`, {
      method: 'POST', headers: useAuth().authHeader(),
      body: { challenger_id: myTeam.value.id, challenged_id: t.id }
    })
    await load()
    const nc = challenges.value.find(c => c.challenger_id === myTeam.value.id && c.challenged_id === t.id)
    if (nc) schedulerChallenge.value = nc
  } catch (e) {
    challengeErr.value = e?.data?.detail || e?.message || 'Could not create challenge'
  }
}
function challengeStatus(c) {
  if (c.agreed_at) return `📅 ${new Date(c.agreed_at).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}${c.server ? ' · ' + c.server : ''}`
  if ((c.proposed || []).length) return 'Awaiting time pick'
  return 'Awaiting availability'
}
function involvesMe(c) {
  return myTeam.value && (c.challenger_id === myTeam.value.id || c.challenged_id === myTeam.value.id)
}
async function onScheduled() { schedulerChallenge.value = null; await load() }
function editTeam(t) { editingTeam.value = t }
async function onTeamAdded(name) {
  showAddTeam.value = false
  editingTeam.value = null
  teamSubmitted.value = name
  await load()
}
function logoUrl(id) { return `${base}/api/ladder/team/${id}/logo` }
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const ladder = ref(null)
const teams = ref([])
const koth = ref(null)
const challenges = ref([])
const loading = ref(true)
const err = ref(null)

async function loadDetail(id, bust = true) {
  // bust: right after a mutation (challenge/schedule/reorder) we need the fresh
  // state, not the browser/edge copy. Background refreshes skip it so they ride
  // the endpoint's short edge cache (cheap) instead of hammering the origin.
  const d = await $fetch(`${base}/api/ladder/${id}`, { query: bust ? { _: Date.now() } : {} })
  ladder.value = d.ladder
  teams.value = d.teams || []
  koth.value = d.koth
  challenges.value = d.challenges || []
}

async function load({ silent = false, bust = true } = {}) {
  if (!silent) loading.value = true
  err.value = null
  try {
    const list = await $fetch(`${base}/api/ladder`, { query: bust ? { _: Date.now() } : {} })
    const first = (list.ladders || [])[0]
    if (!first) { ladder.value = null; return }
    await loadDetail(first.id, bust)
  } catch (e) {
    if (!silent) err.value = 'Could not load the ladder.'
    console.error('[ladder]', e)
  } finally {
    if (!silent) loading.value = false
  }
}
onMounted(() => load())

// Keep the board live: refetch when the player returns to the tab (focus /
// visibility) and on a gentle poll while the tab is visible — so newly approved
// teams + challenge updates show up without a manual reload.
let pollTimer = null
function refreshIfVisible() {
  if (typeof document !== 'undefined' && document.visibilityState === 'visible') load({ silent: true, bust: false })
}
onMounted(() => {
  if (typeof document === 'undefined') return
  document.addEventListener('visibilitychange', refreshIfVisible)
  window.addEventListener('focus', refreshIfVisible)
  pollTimer = setInterval(refreshIfVisible, 90000)
})
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', refreshIfVisible)
    window.removeEventListener('focus', refreshIfVisible)
  }
  if (pollTimer) clearInterval(pollTimer)
})

// Topbar "Team settings" flips a shared flag — open the edit modal for the
// user's team (works for pending teams too, fetched fresh + enriched). Using a
// flag (not a query param) so repeat clicks always reopen it.
async function openMyTeamSettings() {
  if (!user.value?.team) { openTeamSettings.value = false; return }
  try { editingTeam.value = await $fetch(`${base}/api/ladder/team/${user.value.team.id}`) }
  catch { /* ignore */ }
  finally { openTeamSettings.value = false }
}
watch(openTeamSettings, (v) => { if (v) openMyTeamSettings() })
onMounted(() => { if (openTeamSettings.value) openMyTeamSettings() })

// A team is busy if it's in ANY active challenge — as the challenged side OR the
// challenger. Map both so the board never shows a committed team as "Open".
const incoming = computed(() => {
  const m = {}
  for (const c of challenges.value) (m[c.challenged_id] ||= []).push(c)
  return m
})
const outgoing = computed(() => {
  const m = {}
  for (const c of challenges.value) (m[c.challenger_id] ||= []).push(c)
  return m
})
// This team's active challenge (either role), or null.
function teamChallenge(t) {
  return incoming.value[t.id]?.[0] || outgoing.value[t.id]?.[0] || null
}
// Row status label: scheduled vs / challenged by / challenging.
function teamStatus(t) {
  const c = teamChallenge(t)
  if (!c) return null
  const other = c.challenger_id === t.id ? teamName(c.challenged_id) : teamName(c.challenger_id)
  if (c.agreed_at) return `📅 Scheduled vs ${other}`
  return c.challenged_id === t.id ? `⚔ Challenged by ${other}` : `⚔ Challenging ${other}`
}

function teamName(id) {
  return teams.value.find(t => t.id === id)?.name || `#${id}`
}
// Scheduled (agreed) matches for the right-rail list.
const scheduledMatches = computed(() => challenges.value.filter(c => c.agreed_at)
  .sort((a, b) => new Date(a.agreed_at) - new Date(b.agreed_at)))
function fmtMatchTime(iso) {
  return new Date(iso).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
// The action label for the user's own challenge in the rail.
function myChallengeAction(c) {
  if (c.agreed_at) return 'View match'
  const amChallenger = myTeam.value && c.challenger_id === myTeam.value.id
  if (amChallenger) return (c.proposed || []).length ? 'Edit availability' : 'Set availability'
  return (c.proposed || []).length ? 'Pick a time' : 'Waiting on opponent'
}
function membersLabel(t) {
  return (t.members || []).map(m => m.display).join(' · ')
}

useHead({ title: 'KOTH 2v2 Ladder · DeepFrag' })
</script>

<template>
  <div class="wrap">
    <header class="head">
      <img src="/koth-ladder.jpg" alt="KOTH — 2v2 Ladder" class="koth-logo">
      <p class="sub">Challenge up. Win to climb. Hold the hill till Christmas.</p>
      <button v-if="!loggedIn" class="cta" @click="login">Sign in with Discord to play</button>
      <ClientOnly>
        <button v-if="loggedIn && user?.canonical_id" class="cta avail-cta" @click="showAvail = true">📅 Set your general availability</button>
      </ClientOnly>
    </header>

    <ClientOnly>
      <div v-if="needsLocation" class="loc-prompt" @click="showSettings = true">
        📍 <strong>Optional:</strong> add your location to sharpen server suggestions before you've built up ping history — click here (or your name → Personal settings).
      </div>
      <ClaimProfile v-if="needsClaim" />
      <div v-else-if="user?.pending_claim" class="pending-note">
        ⏳ Profile claim for <strong>{{ user.pending_claim.display }}</strong> is awaiting admin approval.
      </div>

      <div v-if="teamSubmitted" class="pending-note">
        ✅ Team <strong>{{ teamSubmitted }}</strong> submitted — an admin will approve it and you'll appear on the board.
      </div>
      <div v-else-if="canAddTeam" class="add-team-bar">
        <div>
          <strong>You're not on a team yet.</strong>
          <span class="muted"> Register yourself + a teammate to join the ladder.</span>
        </div>
        <button class="cta" @click="showAddTeam = true">+ Add Your Team</button>
      </div>

      <AddTeam v-if="showAddTeam && ladder" :ladder-id="ladder.id" @done="onTeamAdded" @close="showAddTeam = false" />
      <AddTeam v-if="editingTeam && ladder" :ladder-id="ladder.id" :edit-team="editingTeam" @done="onTeamAdded" @close="editingTeam = null" />
      <Scheduler v-if="schedulerChallenge" :challenge="schedulerChallenge" :user-team-id="myTeam?.id" @done="onScheduled" @saved="load" @close="schedulerChallenge = null" />
      <div v-if="challengeErr" class="pending-note" style="border-color: var(--loss); color: #fca5a5;">{{ challengeErr }}</div>
    </ClientOnly>

    <div v-if="loading" class="muted pad">Loading the board…</div>
    <div v-else-if="err" class="muted pad">{{ err }}</div>
    <div v-else-if="!ladder" class="empty">
      <h2>The ladder isn't open yet</h2>
      <p>Teams are being seeded. Sign in with Discord and you'll be ready to challenge the moment it goes live.</p>
      <button v-if="!loggedIn" class="cta" @click="login">Sign in with Discord</button>
    </div>

    <template v-else>
     <div class="cols">
      <div class="main">
      <!-- Pre-launch banner -->
      <section v-if="!ladderOpen" class="notopen">
        <div class="lock">🔒</div>
        <div>
          <div class="notopen-title">The ladder isn't open yet</div>
          <div class="notopen-sub">It opens once we have {{ TEAMS_TO_OPEN }} teams seeded — <strong>{{ teams.length }}/{{ TEAMS_TO_OPEN }}</strong> so far. Challenging is disabled until then. Get your team in!</div>
        </div>
      </section>

      <!-- King of the Hill -->
      <section v-if="koth" class="koth">
        <div class="crown">👑</div>
        <div>
          <div class="koth-label">King of the Hill</div>
          <div class="koth-team">{{ koth.name }}</div>
        </div>
        <div v-if="koth.weeks != null" class="koth-weeks">
          <strong>{{ koth.weeks }}</strong> {{ koth.weeks === 1 ? 'week' : 'weeks' }} held
        </div>
      </section>

      <!-- Standings -->
      <section class="board">
        <div class="board-head">
          <span class="c-rung">#</span>
          <span class="c-team">Team</span>
          <span class="c-members">Players</span>
          <span class="c-status">Status</span>
        </div>
        <div
          v-for="t in teams"
          :key="t.id"
          class="row"
          :class="{ top: t.rung === 1 }"
        >
          <span class="c-rung">{{ t.rung }}</span>
          <span class="c-team">
            <img v-if="t.has_logo" :src="logoUrl(t.id)" class="tlogo" alt="">
            <span v-if="t.tag" class="ttag">{{ t.tag }}</span>
            <span class="tname">{{ t.name }}</span>
            <button v-if="isMyTeam(t)" class="edit" title="Team settings" @click="editTeam(t)">✎</button>
          </span>
          <span class="c-members">
            <template v-for="(m, i) in (t.members || [])" :key="m.id">
              <NuxtLink :to="`/p/${m.id}`" class="plink">{{ m.display }}</NuxtLink><span v-if="i < t.members.length - 1" class="dot"> · </span>
            </template>
            <span v-if="!(t.members || []).length">—</span>
          </span>
          <span class="c-status">
            <span v-if="teamStatus(t)" class="badge challenged">{{ teamStatus(t) }}</span>
            <button v-else-if="canChallenge(t)" class="chal-btn" @click="doChallenge(t)">⚔ Challenge</button>
            <span v-else class="badge open">Open</span>
          </span>
        </div>
      </section>

      <!-- Open challenges -->
      <section v-if="challenges.length" class="challenges">
        <h2>Active challenges</h2>
        <ul>
          <li v-for="c in challenges" :key="c.id">
            <strong>{{ teamName(c.challenger_id) }}</strong>
            <span class="arrow">→</span>
            <strong>{{ teamName(c.challenged_id) }}</strong>
            <span class="meta">({{ c.rungs_up }} rung{{ c.rungs_up === 1 ? '' : 's' }} up)</span>
            <span class="cstatus">{{ challengeStatus(c) }}</span>
            <span class="spacer" />
            <button v-if="involvesMe(c)" class="sched-btn" @click="schedulerChallenge = c">
              {{ c.agreed_at ? 'View' : 'Schedule' }}
            </button>
            <span v-else-if="c.deadline && !c.agreed_at" class="deadline">by {{ new Date(c.deadline).toLocaleDateString() }}</span>
          </li>
        </ul>
      </section>

      <!-- Format -->
      <section class="rules">
        <h2>Format</h2>
        <ul>
          <li><strong>Ruleset:</strong> {{ ladder?.rules?.ruleset || 'smackdown' }} <span class="muted">(KTX competitive standard)</span></li>
          <li><strong>Mode:</strong> 2on2 (TDM) · <strong>Best of {{ ladder?.rules?.best_of || 3 }}</strong></li>
          <li><strong>Timelimit:</strong> {{ ladder?.rules?.timelimit || 10 }} min per map · overtime on a draw</li>
          <li><strong>Maps:</strong> Aerowalk · ztndm3 · DM2 · DM4 · Bravado · Nova · Shifter</li>
        </ul>
      </section>

      <!-- Rules -->
      <section class="rules">
        <h2>How it works</h2>
        <ul>
          <li>Challenge a team <strong>1 or 2 rungs</strong> above you.</li>
          <li><strong>Win a 1-rung challenge</strong> → swap places.</li>
          <li><strong>Win a 2-rung challenge</strong> → jump up 2; the teams you passed each drop one.</li>
          <li><strong>Forfeit</strong> (no game within a week) → the challenged team drops a rung.</li>
          <li>Best of 3. Winners may re-challenge immediately.</li>
          <li><strong>After a loss</strong> you can't re-challenge the same team for a week — but you can challenge a <em>different</em> team (up to 2 rungs up) right away.</li>
          <li>Maps: Aerowalk · ztndm3 · DM2 · DM4 · Bravado · Nova · Shifter.</li>
        </ul>
      </section>

      <!-- Servers & ping -->
      <section class="rules">
        <h2>Servers &amp; ping</h2>
        <ul>
          <li><strong>NA servers</strong> for any match involving a North American team. This is a North American tournament.</li>
          <li><strong>Exception — Brazil vs Brazil:</strong> two Brazilian teams may play on a Brazilian server (both are closer to it). DeepFrag picks a BR server automatically for those.</li>
          <li><strong>No ping-ups.</strong> We just get average ping as close as possible between both teams on a single server.</li>
          <li>A Brazilian team vs an NA team plays the <strong>closest-proximity NA server</strong> (e.g. Brazil on Miami, ~100–130ms; most US players sit ~45–70ms).</li>
          <li><strong>DeepFrag suggests the server automatically</strong> from both teams' player locations — no guesswork. Set yours under your name → <em>Personal settings</em>.</li>
          <li>Server pool: Denver · Miami · Chicago · Dallas · New York · LA · Iowa · Washington.</li>
        </ul>
      </section>

      <!-- Full match ruleset (collapsible) -->
      <section class="rules">
        <details class="ruleset" open>
          <summary>
            <span class="rs-title">📋 Full match ruleset</span>
            <span class="rs-sum">smackdown · 2on2 · Bo3 · 10-min maps</span>
          </summary>

          <div class="rs-body">
            <h4>Format</h4>
            <ul>
              <li>2on2 TDM, ruleset <strong>smackdown</strong>, <strong>best of 3</strong> maps, 10-minute maps.</li>
              <li>Client: a recent <strong>ezQuake</strong> or <strong>unEzQuake</strong>. In-game: set mode <code>2on2</code>, <code>ruleset smackdown</code>.</li>
              <li><strong>SmackDrive is not permitted.</strong></li>
            </ul>

            <h4>Maps &amp; picks (Bo3)</h4>
            <ul>
              <li>Pool: Aerowalk · ztndm3 · DM2 · DM4 · Bravado · Nova · Shifter.</li>
              <li><code>rnd team1 team2</code> decides who picks first.</li>
              <li>Team A picks map 1 → Team B picks map 2.</li>
              <li>If it's 1–1, the team that picked 2nd tosses first for the decider.</li>
              <li>No map is played twice.</li>
            </ul>

            <h4>Servers &amp; ping</h4>
            <ul>
              <li><strong>NA servers only</strong> (a Brazil-vs-Brazil match may use a BR server).</li>
              <li>Aim for <strong>even pings</strong> on the closest-proximity NA server. <strong>No ping-ups / delay commands.</strong></li>
              <li>DeepFrag auto-suggests the fairest server from both teams' ping history.</li>
              <li>Proxy / routing allowed. Packet-loss disputes: both teams agree on a server; if you can't, an admin picks — refusing the admin's server is a forfeit.</li>
            </ul>

            <h4>Client integrity</h4>
            <ul>
              <li>unEzQuake must pass the ruleset check (shows <strong>CLEAR</strong>).</li>
              <li><strong>unEzQuake only</strong> — required commands: <code>scr_allowsnap 1</code>, <code>tp_triggers 0</code>, <code>allow_scripts 0</code>.</li>
              <li><strong>Allowed:</strong> the standard team HUD — <code>teamoverlay</code> / <code>show teaminfo</code> (teammate location, health, armor &amp; weapons). It's standard team-game info and fully permitted.</li>
              <li>Banned: anything that changes gameplay or graphics vs standard ezQuake — jump automation, <em>enemy</em> radar/wallhack overlays, colored backpacks, smartspawn, etc. (This does <strong>not</strong> include the teammate overlay above.)</li>
              <li>unEzQuake must behave exactly like ezQuake — no visual or gameplay edge. No wallhacks, no homebuilt client features. Period.</li>
            </ul>

            <h4>Match conduct</h4>
            <ul>
              <li><strong>Names:</strong> use consistent clan tags + player names all season — critical for stats tracking.</li>
              <li><strong>Pacing:</strong> play at least one ladder match per week; prioritize ladder games over pracs.</li>
              <li><strong>Pauses:</strong> one pause per team per map (don't abuse it).</li>
              <li><strong>Sportsmanship:</strong> fair play expected, always.</li>
            </ul>

            <h4>Roster</h4>
            <ul>
              <li>Declare your full roster at signup.</li>
              <li>No playing for multiple teams.</li>
              <li>Roster changes after signup need admin approval.</li>
              <li>No stand-ins.</li>
            </ul>

            <h4>Admins</h4>
            <ul>
              <li>Head admins: <strong>Cronus, Nin, Bance</strong>. Questions / disputes → the KOTH Discord channel.</li>
            </ul>
          </div>
        </details>
      </section>
      </div><!-- /main -->

      <!-- Schedule rail -->
      <aside class="rail">
        <ClientOnly>
          <div class="rail-card">
            <h3>📅 Your match</h3>
            <template v-if="myOpenChallenge">
              <div class="ym-teams">
                <strong>{{ teamName(myOpenChallenge.challenger_id) }}</strong>
                <span class="vs">vs</span>
                <strong>{{ teamName(myOpenChallenge.challenged_id) }}</strong>
              </div>
              <div class="ym-status">{{ challengeStatus(myOpenChallenge) }}</div>
              <button class="rail-btn" @click="schedulerChallenge = myOpenChallenge">{{ myChallengeAction(myOpenChallenge) }}</button>
            </template>
            <p v-else-if="myTeam" class="muted small">No active match. Hit <strong>⚔ Challenge</strong> on a team 1–2 rungs above you to start one.</p>
            <p v-else-if="loggedIn && user?.canonical_id" class="muted small">Join or create a team to start scheduling matches.</p>
            <p v-else class="muted small">Sign in and join a team to schedule matches.</p>
          </div>

          <div class="rail-card">
            <h3>Scheduled matches</h3>
            <div v-if="!scheduledMatches.length" class="muted small">Nothing scheduled yet.</div>
            <div v-for="c in scheduledMatches" :key="c.id" class="sm-row">
              <div class="sm-teams">{{ teamName(c.challenger_id) }} vs {{ teamName(c.challenged_id) }}</div>
              <div class="sm-when">📅 {{ fmtMatchTime(c.agreed_at) }}</div>
              <div v-if="c.server" class="sm-srv">🖥️ {{ c.server }}</div>
            </div>
          </div>
        </ClientOnly>
      </aside>
     </div><!-- /cols -->
    </template>
  </div>
</template>

<style scoped>
.wrap { max-width: 1140px; margin: 0 auto; padding: 32px 24px 80px; }
.cols { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 22px; align-items: start; }
.main { min-width: 0; }
.rail { display: flex; flex-direction: column; gap: 14px; position: sticky; top: 84px; }
.rail-card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }
.rail-card h3 { margin: 0 0 12px; font-size: 14px; font-weight: 800; }
.rail-card .small { font-size: 12px; }
.ym-teams { display: flex; align-items: center; gap: 8px; font-size: 15px; flex-wrap: wrap; }
.ym-teams .vs { color: var(--fg-3); font-size: 12px; }
.ym-status { color: var(--fg-2); font-size: 13px; margin: 8px 0 12px; }
.rail-btn { width: 100%; background: var(--accent); color: var(--bg); border: 0; padding: 9px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.rail-btn:hover { filter: brightness(1.1); }
.sm-row { padding: 8px 0; border-top: 1px solid var(--border); font-size: 13px; }
.sm-row:first-of-type { border-top: 0; }
.sm-teams { font-weight: 600; }
.sm-when { color: var(--accent); font-size: 12px; margin-top: 2px; }
.sm-srv { color: var(--fg-3); font-size: 12px; font-family: 'JetBrains Mono', monospace; }
@media (max-width: 860px) { .cols { grid-template-columns: 1fr; } .rail { position: static; } }
.head { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 10px; margin-bottom: 28px; }
.head .koth-logo { width: 100%; max-width: 520px; height: auto; display: block; filter: drop-shadow(0 6px 24px rgba(0,0,0,0.5)); }
.head .sub { color: var(--fg-2); margin: 2px 0 0; font-size: 15px; }
.head .cta { margin-top: 6px; }
.cta {
  background: #5865f2; color: #fff; border: none; white-space: nowrap;
  padding: 10px 18px; border-radius: 9px; font-size: 14px; font-weight: 700; cursor: pointer;
}
.cta:hover { background: #4752c4; }
.avail-cta { margin-top: 10px; background: var(--panel-2); color: var(--fg); border: 1px solid var(--accent); }
.avail-cta:hover { background: var(--panel-3); }
.muted { color: var(--fg-2); }
.pad { padding: 40px 0; text-align: center; }
.pending-note { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; color: var(--fg-2); font-size: 14px; }
.loc-prompt { background: rgba(20,230,192,0.08); border: 1px solid rgba(20,230,192,0.3); border-radius: 12px; padding: 12px 18px; margin-bottom: 16px; color: var(--fg-2); font-size: 14px; cursor: pointer; }
.loc-prompt:hover { background: rgba(20,230,192,0.14); }
.notopen { display: flex; align-items: center; gap: 16px; background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(20,230,192,0.05)); border: 1px solid rgba(245,158,11,0.4); border-radius: 14px; padding: 16px 20px; margin-bottom: 18px; }
.notopen .lock { font-size: 28px; }
.notopen-title { font-size: 17px; font-weight: 800; }
.notopen-sub { color: var(--fg-2); font-size: 14px; margin-top: 2px; }
.notopen-sub strong { color: var(--fg); }
.loc-prompt strong { color: var(--fg); }
.add-team-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; background: var(--panel); border: 1px solid var(--accent); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; }
.add-team-bar .muted { color: var(--fg-3); }
.tlogo { width: 22px; height: 22px; border-radius: 5px; object-fit: cover; margin-right: 8px; vertical-align: middle; }

.empty { text-align: center; padding: 60px 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; }
.empty h2 { margin: 0 0 8px; }
.empty p { color: var(--fg-2); max-width: 420px; margin: 0 auto 20px; }

.koth {
  display: flex; align-items: center; gap: 16px;
  background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(20,230,192,0.06));
  border: 1px solid rgba(245,158,11,0.35); border-radius: 14px;
  padding: 18px 22px; margin-bottom: 20px;
}
.koth .crown { font-size: 30px; }
.koth-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--draw); font-weight: 700; }
.koth-team { font-size: 20px; font-weight: 800; }
.koth-weeks { margin-left: auto; color: var(--fg-2); font-size: 14px; }
.koth-weeks strong { color: var(--fg); font-size: 22px; }

.board { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.board-head, .row {
  display: grid; grid-template-columns: 48px 1.4fr 1.6fr 1.4fr; align-items: center;
  gap: 12px; padding: 12px 18px;
}
.board-head { background: var(--panel-2); color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
.row { border-top: 1px solid var(--border); }
.row .c-rung { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--fg-2); }
.row.top { background: rgba(245,158,11,0.07); }
.row.top .c-rung { color: var(--draw); }
.row.top .tname::before { content: '👑 '; }
.c-team { display: flex; align-items: center; gap: 8px; }
.ttag { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; color: var(--accent); background: rgba(20,230,192,0.12); border: 1px solid rgba(20,230,192,0.3); border-radius: 5px; padding: 1px 6px; letter-spacing: 0.04em; }
.tname { font-weight: 700; }
.edit { background: none; border: 0; color: var(--fg-3); cursor: pointer; font-size: 13px; padding: 2px 4px; opacity: 0.7; }
.edit:hover { color: var(--accent); opacity: 1; }
.plink { color: var(--fg-2); text-decoration: none; }
.plink:hover { color: var(--accent); text-decoration: underline; }
.c-members .dot { color: var(--fg-3); }
.c-members { color: var(--fg-2); font-size: 13px; }
.badge { font-size: 12px; padding: 3px 9px; border-radius: 999px; font-weight: 600; }
.badge.open { background: var(--panel-2); color: var(--fg-3); }
.badge.challenged { background: rgba(239,68,68,0.15); color: #fca5a5; }

.challenges, .rules { margin-top: 28px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 20px 22px; }
.challenges h2, .rules h2 { margin: 0 0 14px; font-size: 16px; font-weight: 800; }
.challenges ul, .rules ul { margin: 0; padding-left: 0; list-style: none; }
.challenges li { padding: 8px 0; border-top: 1px solid var(--border); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.challenges li:first-child { border-top: none; }
.challenges .arrow { color: var(--accent); }
.challenges .meta { color: var(--fg-3); font-size: 13px; }
.challenges .deadline { color: var(--draw); font-size: 12px; font-family: 'JetBrains Mono', monospace; }
.challenges .cstatus { color: var(--fg-2); font-size: 12px; }
.challenges .spacer { flex: 1; }
.chal-btn { background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); border-radius: 6px; padding: 4px 10px; font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; }
.chal-btn:hover { background: rgba(239,68,68,0.28); }
.sched-btn { background: var(--accent); color: var(--bg); border: 0; border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; }
.sched-btn:hover { filter: brightness(1.1); }
.rules li { padding: 6px 0; color: var(--fg-2); padding-left: 20px; position: relative; }
.rules li::before { content: '▸'; position: absolute; left: 0; color: var(--accent); }
.rules strong { color: var(--fg); }
/* Collapsible full ruleset */
.ruleset { }
.ruleset summary { cursor: pointer; list-style: none; display: flex; flex-direction: column; gap: 2px; padding: 2px 0; }
.ruleset summary::-webkit-details-marker { display: none; }
.ruleset summary::before { content: '▸'; color: var(--accent); position: absolute; margin-left: -16px; transition: transform 0.15s; }
.ruleset[open] summary::before { transform: rotate(90deg); }
.ruleset summary { padding-left: 16px; }
.rs-title { font-size: 16px; font-weight: 800; color: var(--fg); }
.rs-sum { font-size: 12px; color: var(--fg-3); }
.rs-body { margin-top: 14px; padding-left: 16px; }
.rs-body h4 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent); font-weight: 800; margin: 16px 0 6px; }
.rs-body h4:first-child { margin-top: 0; }
.rs-body ul { margin: 0; padding-left: 18px; list-style: none; }
.rs-body li { color: var(--fg-2); font-size: 13px; padding: 3px 0; position: relative; }
.rs-body li::before { content: '·'; position: absolute; left: -12px; color: var(--fg-3); }
.rs-body code { background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; font-size: 11px; font-family: 'JetBrains Mono', monospace; color: var(--accent); }
.rs-body strong { color: var(--fg); }
</style>

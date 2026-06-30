<script setup>
// KOTH 2v2 ladder — tabbed hub: Standings (bento home) · Schedule · Stats · Rules.
// Reads /api/ladder then /api/ladder/{id}. Captain self-serve is Discord-gated.
const { user, loggedIn, login } = useAuth()
const showSettings = useState('show-settings', () => false)
const openTeamSettings = useState('open-team-settings', () => false)
const showAvail = useState('show-availability', () => false)
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const TABS = ['standings', 'schedule', 'stats', 'rules']
const tab = ref('standings')
function setTab(t) { tab.value = t; if (isBrowser) history.replaceState(null, '', `#${t}`) }

const needsLocation = computed(() => loggedIn.value && user.value?.canonical_id && !user.value?.state)
const needsClaim = computed(() => loggedIn.value && user.value && !user.value.canonical_id && !user.value.pending_claim)
const showAddTeam = ref(false)
const editingTeam = ref(null)
const teamSubmitted = ref('')
const onTeam = computed(() => {
  const cid = user.value?.canonical_id
  return !!cid && teams.value.some(t => (t.members || []).some(m => m.id === cid))
})
const canAddTeam = computed(() => loggedIn.value && user.value?.canonical_id && ladder.value && !onTeam.value)
function isMyTeam(t) {
  const cid = user.value?.canonical_id
  return (!!cid && (t.members || []).some(m => m.id === cid)) || !!user.value?.is_admin
}
const myTeam = computed(() => {
  const cid = user.value?.canonical_id
  if (!cid) return null
  return teams.value.find(t => (t.members || []).some(m => m.id === cid)) || null
})
const myOpenChallenge = computed(() => {
  if (!myTeam.value) return null
  return challenges.value.find(c => c.challenger_id === myTeam.value.id || c.challenged_id === myTeam.value.id) || null
})
const ladderOpen = computed(() => !!ladder.value?.rules?.open)
const TEAMS_TO_OPEN = 10
// Live "now" for the loss-cooldown countdown (tick every minute).
const now = ref(isBrowser ? Date.now() : 0)
let nowTimer = null
onMounted(() => { nowTimer = setInterval(() => { now.value = Date.now() }, 60000) })
onBeforeUnmount(() => { if (nowTimer) clearInterval(nowTimer) })
// A team that lost in the last week can't ISSUE challenges.
// Returns "6d 23h", "5h 12m", "45m", "<1m", or null. Drops down to minutes once
// under an hour so the badge never reads a useless "0h" near expiry.
function teamCooldown(t) {
  if (!t.cooldown_until) return null
  const until = new Date(t.cooldown_until).getTime()
  if (until <= now.value) return null
  const rem = until - now.value
  const d = Math.floor(rem / 86400000)
  const h = Math.floor((rem % 86400000) / 3600000)
  const m = Math.floor((rem % 3600000) / 60000)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return m > 0 ? `${m}m` : '<1m'
}
const myCooldown = computed(() => myTeam.value ? teamCooldown(myTeam.value) : null)
function canChallenge(t) {
  if (!ladderOpen.value) return false
  if (!myTeam.value || !myTeam.value.rung || !t.rung || myOpenChallenge.value) return false
  if (myCooldown.value) return false   // my team lost recently — benched from challenging
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
  } catch (e) { challengeErr.value = e?.data?.detail || e?.message || 'Could not create challenge' }
}
function challengeStatus(c) {
  if (c.agreed_at) return `📅 ${new Date(c.agreed_at).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}${c.server ? ' · ' + c.server : ''}`
  if ((c.proposed || []).length) return 'Awaiting time pick'
  return 'Awaiting availability'
}
function involvesMe(c) { return myTeam.value && (c.challenger_id === myTeam.value.id || c.challenged_id === myTeam.value.id) }
// Only the CHALLENGER may withdraw, and only while still open (no time agreed).
function canWithdraw(c) {
  return !!myTeam.value && c.challenger_id === myTeam.value.id && c.status === 'open' && !c.agreed_at
}
const withdrawingId = ref(null)
async function doWithdraw(c) {
  if (!canWithdraw(c)) return
  if (!confirm('Withdraw your challenge? Both teams will be freed up.')) return
  withdrawingId.value = c.id
  challengeErr.value = ''
  try {
    await $fetch(`${base}/api/ladder/challenge/${c.id}/withdraw`, { method: 'POST', headers: useAuth().authHeader() })
    if (schedulerChallenge.value?.id === c.id) schedulerChallenge.value = null
    await load()
  } catch (e) { challengeErr.value = e?.data?.detail || e?.message || 'Could not withdraw challenge' }
  finally { withdrawingId.value = null }
}
const reschedulingId = ref(null)
async function doReschedule(c) {
  if (!confirm('Reschedule this match? The agreed time is cleared and both teams re-pick new times.')) return
  reschedulingId.value = c.id
  challengeErr.value = ''
  try {
    await $fetch(`${base}/api/ladder/challenge/${c.id}/reschedule`, { method: 'POST', headers: useAuth().authHeader() })
    await load()
    schedulerChallenge.value = challenges.value.find(x => x.id === c.id) || null   // reopen in propose mode
  } catch (e) { challengeErr.value = e?.data?.detail || e?.message || 'Could not reschedule' }
  finally { reschedulingId.value = null }
}
async function onScheduled() { schedulerChallenge.value = null; await load() }
function editTeam(t) { editingTeam.value = t }
async function onTeamAdded(name) { showAddTeam.value = false; editingTeam.value = null; teamSubmitted.value = name; await load() }
function logoUrl(id) { return `${base}/api/ladder/team/${id}/logo` }

const ladder = ref(null)
const teams = ref([])
const koth = ref(null)
const challenges = ref([])
const loading = ref(true)
const err = ref(null)
// home cards
const recentMatches = ref([])
const statLeaders = ref([])
const openMatchId = ref(null)

async function loadDetail(id, bust = true) {
  const d = await $fetch(`${base}/api/ladder/${id}`, { query: bust ? { _: Date.now() } : {} })
  ladder.value = d.ladder; teams.value = d.teams || []; koth.value = d.koth; challenges.value = d.challenges || []
  loadHomeExtras(id)
}
async function loadHomeExtras(id) {
  try {
    const [mr, ts] = await Promise.all([
      $fetch(`${base}/api/ladder/${id}/matches?limit=5`),
      $fetch(`${base}/api/ladder/${id}/team-stats`),
    ])
    recentMatches.value = mr.matches || []
    const wd = (ts.teams || []).filter(t => t.maps > 0)
    const top = k => wd.slice().sort((a, b) => (b[k] ?? -1) - (a[k] ?? -1))[0]
    statLeaders.value = wd.length ? [
      { label: 'Efficiency', team: top('eff')?.name, val: top('eff')?.eff != null ? top('eff').eff + '%' : '—' },
      { label: 'Frags / map', team: top('frags')?.name, val: top('frags')?.frags ?? '—' },
      { label: 'Quad control', team: top('quad')?.name, val: top('quad')?.quad ?? '—' },
    ] : []
  } catch { /* empty until data */ }
}
async function load({ silent = false, bust = true } = {}) {
  if (!silent) loading.value = true
  err.value = null
  try {
    const list = await $fetch(`${base}/api/ladder`, { query: bust ? { _: Date.now() } : {} })
    const first = (list.ladders || [])[0]
    if (!first) { ladder.value = null; return }
    await loadDetail(first.id, bust)
  } catch (e) { if (!silent) err.value = 'Could not load the ladder.'; console.error('[ladder]', e) }
  finally { if (!silent) loading.value = false }
}
onMounted(() => {
  load()
  const h = isBrowser ? location.hash.replace('#', '') : ''
  if (TABS.includes(h)) tab.value = h
})

let pollTimer = null
function refreshIfVisible() { if (typeof document !== 'undefined' && document.visibilityState === 'visible') load({ silent: true, bust: false }) }
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

async function openMyTeamSettings() {
  if (!user.value?.team) { openTeamSettings.value = false; return }
  try { editingTeam.value = await $fetch(`${base}/api/ladder/team/${user.value.team.id}`) }
  catch { /* ignore */ } finally { openTeamSettings.value = false }
}
watch(openTeamSettings, (v) => { if (v) openMyTeamSettings() })
onMounted(() => { if (openTeamSettings.value) openMyTeamSettings() })

const incoming = computed(() => { const m = {}; for (const c of challenges.value) (m[c.challenged_id] ||= []).push(c); return m })
const outgoing = computed(() => { const m = {}; for (const c of challenges.value) (m[c.challenger_id] ||= []).push(c); return m })
function teamChallenge(t) { return incoming.value[t.id]?.[0] || outgoing.value[t.id]?.[0] || null }
function teamStatus(t) {
  const c = teamChallenge(t)
  if (!c) return null
  // Use the short clan tag (falls back to name) so the badge stays one line.
  const other = teamLabel(c.challenger_id === t.id ? c.challenged_id : c.challenger_id)
  if (c.agreed_at) return `📅 vs ${other}`
  return c.challenged_id === t.id ? `⚔ Challenged by ${other}` : `⚔ Challenging ${other}`
}
function teamName(id) { return teams.value.find(t => t.id === id)?.name || `#${id}` }
function teamTag(id) { const t = teams.value.find(t => t.id === id); return t?.tag || t?.name || `#${id}` }
function teamLabel(id) { const t = teams.value.find(x => x.id === id); return t ? (t.tag || t.name) : `#${id}` }
const scheduledMatches = computed(() => challenges.value.filter(c => c.agreed_at).sort((a, b) => new Date(a.agreed_at) - new Date(b.agreed_at)))
const openChallengeCount = computed(() => challenges.value.length)
function fmtMatchTime(iso) { return new Date(iso).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
function fmtDate(s) { return s ? new Date(s).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '' }
// Recent results are shown WINNER-first (⚔ marks the challenger) so a row never
// reads "A def B 0-2" — winner's name + score come first. (BloodDog feedback.)
function orientMatch(m) {
  const bWon = m.winner_id != null && m.winner_id === m.team_b_id
  const A = { id: m.team_a_id, name: m.a_name, score: m.score_a }
  const B = { id: m.team_b_id, name: m.b_name, score: m.score_b }
  const w = bWon ? B : A, l = bWon ? A : B
  return { w, l, wIsChallenger: w.id === m.team_a_id }
}
function myChallengeAction(c) {
  if (c.agreed_at) return 'View match'
  const amChallenger = myTeam.value && c.challenger_id === myTeam.value.id
  if (amChallenger) return (c.proposed || []).length ? 'Edit availability' : 'Set availability'
  return (c.proposed || []).length ? 'Pick a time' : 'Waiting on opponent'
}

useHead({ title: 'KOTH 2v2 Ladder · DeepFrag' })
</script>

<template>
  <div class="wrap">
    <header class="head">
      <img src="/koth-ladder.jpg" alt="KOTH — 2v2 Ladder" class="koth-logo">
      <p class="sub">Challenge up. Win to climb. Hold the hill till Christmas.</p>
      <div class="head-actions">
        <button v-if="!loggedIn" class="cta" @click="login">Sign in with Discord to play</button>
        <ClientOnly>
          <button v-if="loggedIn && user?.canonical_id" class="cta ghost" @click="showAvail = true">📅 My availability</button>
          <button v-if="canAddTeam" class="cta" @click="showAddTeam = true">+ Add your team</button>
        </ClientOnly>
      </div>
    </header>

    <div v-if="loading" class="muted pad">Loading the board…</div>
    <div v-else-if="err" class="muted pad">{{ err }}</div>
    <div v-else-if="!ladder" class="empty">
      <h2>The ladder isn't open yet</h2>
      <p>Teams are being seeded. Sign in with Discord and you'll be ready to challenge the moment it goes live.</p>
      <button v-if="!loggedIn" class="cta" @click="login">Sign in with Discord</button>
    </div>

    <template v-else>
      <!-- Tabs -->
      <nav class="tabs">
        <button class="tab" :class="{ on: tab === 'standings' }" @click="setTab('standings')">Standings</button>
        <button class="tab" :class="{ on: tab === 'schedule' }" @click="setTab('schedule')">Schedule <span v-if="openChallengeCount" class="tcount">{{ openChallengeCount }}</span></button>
        <button class="tab" :class="{ on: tab === 'stats' }" @click="setTab('stats')">Stats</button>
        <button class="tab" :class="{ on: tab === 'rules' }" @click="setTab('rules')">Rules &amp; info</button>
      </nav>

      <!-- prompts -->
      <ClientOnly>
        <ClaimProfile v-if="needsClaim" />
        <div v-else-if="user?.pending_claim" class="note">⏳ Profile claim for <strong>{{ user.pending_claim.display }}</strong> is awaiting admin approval.</div>
        <div v-if="teamSubmitted" class="note">✅ Team <strong>{{ teamSubmitted }}</strong> submitted — an admin will approve it and you'll appear on the board.</div>
        <div v-if="needsLocation" class="note tip" @click="showSettings = true">📍 Add your location (Personal settings) to sharpen server suggestions.</div>
        <div v-if="myCooldown" class="note cooldown-note">⏳ Your team lost recently — you can't issue challenges for <strong>{{ myCooldown }}</strong>. You can still be challenged.</div>
        <div v-if="challengeErr" class="note err">{{ challengeErr }}</div>
      </ClientOnly>

      <!-- ============ STANDINGS (bento) ============ -->
      <div v-show="tab === 'standings'" class="bento">
        <section v-if="!ladderOpen" class="card notopen span2">
          <div class="lock">🔒</div>
          <div><div class="notopen-title">The ladder isn't open yet</div>
            <div class="notopen-sub">Opens at {{ TEAMS_TO_OPEN }} seeded teams — <strong>{{ teams.length }}/{{ TEAMS_TO_OPEN }}</strong> so far. Challenging is disabled until then.</div></div>
        </section>

        <!-- Standings board (big) -->
        <section class="card board-card">
          <h3>🏆 Standings <button class="exp" @click="setTab('rules')">how it works ⓘ</button></h3>
          <div class="board">
            <div class="board-head"><span class="c-rung">#</span><span class="c-team">Team</span><span class="c-members">Players</span><span class="c-rec" title="Match record (won–lost)">Match</span><span class="c-rec" title="Game/map record (won–lost)">Games</span><span class="c-status">Status</span></div>
            <div v-for="t in teams" :key="t.id" class="row" :class="{ top: t.rung === 1 }">
              <span class="c-rung">{{ t.rung }}</span>
              <span class="c-team">
                <img v-if="t.has_logo" :src="logoUrl(t.id)" class="tlogo" alt="">
                <span v-else class="tlogo tlogo-ph">👑</span>
                <span class="ttag">{{ t.tag || '—' }}</span>
                <NuxtLink class="tname tlink" :to="`/ladder/team/${t.id}`" title="View team page">{{ t.name }}</NuxtLink>
                <button v-if="isMyTeam(t)" class="edit" title="Team settings" @click="editTeam(t)">✎</button>
              </span>
              <span class="c-members">
                <template v-for="(m, i) in (t.members || [])" :key="m.id">
                  <NuxtLink :to="`/p/${m.id}`" class="plink">{{ m.display }}</NuxtLink><span v-if="i < t.members.length - 1" class="dot"> · </span>
                </template>
                <span v-if="!(t.members || []).length">—</span>
              </span>
              <span class="c-rec c-match"><span class="rec-lbl">M </span><b>{{ t.match_w ?? 0 }}</b><span class="dash">–</span>{{ t.match_l ?? 0 }}</span>
              <span class="c-rec c-games"><span class="rec-lbl">G </span><b>{{ t.game_w ?? 0 }}</b><span class="dash">–</span>{{ t.game_l ?? 0 }}</span>
              <span class="c-status">
                <span v-if="teamStatus(t)" class="badge challenged">{{ teamStatus(t) }}</span>
                <button v-else-if="canChallenge(t)" class="chal-btn" @click="doChallenge(t)">⚔ Challenge</button>
                <span v-else-if="teamCooldown(t)" class="badge cooldown" title="Lost recently — can't issue challenges (can still be challenged)">⏳ Cooldown · {{ teamCooldown(t) }}</span>
                <span v-else class="badge open">Open</span>
              </span>
            </div>
          </div>
          <div class="legend">
            <span class="lg-item"><span class="badge open">Open</span> free to challenge / be challenged</span>
            <span class="lg-item"><span class="badge challenged">📅 vs</span> match scheduled</span>
            <span class="lg-item"><span class="badge challenged">⚔</span> in an active challenge</span>
            <span class="lg-item"><span class="badge cooldown">⏳ Cooldown</span> lost recently — can't <em>issue</em> challenges (still challengeable)</span>
          </div>
        </section>

        <!-- right column cards -->
        <div class="rail">
          <section v-if="koth" class="card koth">
            <div class="crown">👑</div>
            <div><div class="koth-label">King of the Hill</div><div class="koth-team">{{ koth.name }}</div></div>
            <div v-if="koth.weeks != null" class="koth-weeks"><strong>{{ koth.weeks }}</strong> {{ koth.weeks === 1 ? 'wk' : 'wks' }}</div>
          </section>

          <section class="card">
            <h3>📅 Upcoming <button class="exp" @click="setTab('schedule')">schedule →</button></h3>
            <div v-if="!scheduledMatches.length" class="muted small">Nothing scheduled yet.</div>
            <div v-for="c in scheduledMatches.slice(0, 4)" :key="c.id" class="uprow">
              <span class="up-teams">
                <NuxtLink class="up-tag" :to="`/ladder/team/${c.challenger_id}`">{{ teamTag(c.challenger_id) }}</NuxtLink>
                <span class="up-vs">vs</span>
                <NuxtLink class="up-tag" :to="`/ladder/team/${c.challenged_id}`">{{ teamTag(c.challenged_id) }}</NuxtLink>
              </span>
              <span class="up-when muted small">{{ fmtMatchTime(c.agreed_at) }}</span>
              <NuxtLink class="up-prev" :to="`/ladder/match/${c.id}`">Preview →</NuxtLink>
            </div>
          </section>

          <section class="card">
            <h3>✅ Recent results <button class="exp" @click="setTab('stats')">all →</button></h3>
            <div v-if="!recentMatches.length" class="muted small">No matches reported yet.</div>
            <div v-if="recentMatches.length" class="res res-head">
              <span class="res-t">Winner</span><span class="res-s"></span><span class="res-t right">Loser</span>
            </div>
            <button v-for="m in recentMatches.slice(0, 5)" :key="m.id" class="res" @click="openMatchId = m.id">
              <template v-for="o in [orientMatch(m)]" :key="'o'+m.id">
                <span class="res-t" :title="o.w.name">{{ teamTag(o.w.id) }}<span v-if="o.wIsChallenger" class="chal" title="Challenger">⚔</span></span>
                <span class="res-s"><b class="w">{{ o.w.score }}</b>–<b>{{ o.l.score }}</b></span>
                <span class="res-t right" :title="o.l.name"><span v-if="!o.wIsChallenger" class="chal" title="Challenger">⚔</span>{{ teamTag(o.l.id) }}</span>
              </template>
            </button>
          </section>

          <section v-if="statLeaders.length" class="card">
            <h3>📊 Stat leaders <button class="exp" @click="setTab('stats')">full stats →</button></h3>
            <div v-for="s in statLeaders" :key="s.label" class="kpi"><span class="muted small">{{ s.label }}</span><b>{{ s.team }} · {{ s.val }}</b></div>
          </section>

          <section class="card more">
            <h3>🎁 More <span class="soon">soon</span></h3>
            <p class="muted small">King history · awards · leaderboards — coming.</p>
          </section>
        </div>
      </div>

      <!-- ============ SCHEDULE ============ -->
      <div v-show="tab === 'schedule'" class="bento">
        <section class="card board-card">
          <h3>📅 Your match</h3>
          <ClientOnly>
            <template v-if="myOpenChallenge">
              <div class="ym-teams"><strong>{{ teamName(myOpenChallenge.challenger_id) }}</strong><span class="vs">vs</span><strong>{{ teamName(myOpenChallenge.challenged_id) }}</strong></div>
              <div class="ym-status">{{ challengeStatus(myOpenChallenge) }}</div>
              <div class="ym-actions">
                <button class="rail-btn" @click="schedulerChallenge = myOpenChallenge">{{ myChallengeAction(myOpenChallenge) }}</button>
                <button v-if="myOpenChallenge.agreed_at" class="rail-btn ghost" :disabled="reschedulingId === myOpenChallenge.id" @click="doReschedule(myOpenChallenge)">{{ reschedulingId === myOpenChallenge.id ? 'Reopening…' : 'Reschedule' }}</button>
                <button v-if="canWithdraw(myOpenChallenge)" class="rail-btn ghost" :disabled="withdrawingId === myOpenChallenge.id" @click="doWithdraw(myOpenChallenge)">{{ withdrawingId === myOpenChallenge.id ? 'Withdrawing…' : 'Withdraw' }}</button>
              </div>
            </template>
            <p v-else-if="myTeam" class="muted small">No active match. Go to <a class="lnk" @click="setTab('standings')">Standings</a> and hit ⚔ Challenge on a team 1–2 rungs above you.</p>
            <p v-else-if="loggedIn && user?.canonical_id" class="muted small">Join or create a team to start scheduling matches.</p>
            <p v-else class="muted small">Sign in and join a team to schedule matches.</p>
          </ClientOnly>

          <h3 style="margin-top:18px">Active challenges</h3>
          <div v-if="!challenges.length" class="muted small">No active challenges.</div>
          <div v-for="c in challenges" :key="c.id" class="chal-row">
            <strong>{{ teamName(c.challenger_id) }}</strong><span class="arrow">→</span><strong>{{ teamName(c.challenged_id) }}</strong>
            <span class="cstatus">{{ challengeStatus(c) }}</span>
            <span class="spacer" />
            <button v-if="involvesMe(c)" class="sched-btn" @click="schedulerChallenge = c">{{ c.agreed_at ? 'View' : 'Schedule' }}</button>
            <button v-if="canWithdraw(c)" class="sched-btn ghost" :disabled="withdrawingId === c.id" @click="doWithdraw(c)">{{ withdrawingId === c.id ? '…' : 'Withdraw' }}</button>
            <span v-else-if="!involvesMe(c) && c.deadline && !c.agreed_at" class="deadline">by {{ new Date(c.deadline).toLocaleDateString() }}</span>
          </div>
        </section>

        <div class="rail">
          <section class="card">
            <h3>Scheduled matches</h3>
            <div v-if="!scheduledMatches.length" class="muted small">Nothing scheduled yet.</div>
            <div v-for="c in scheduledMatches" :key="c.id" class="sm-row">
              <div class="sm-teams">{{ teamName(c.challenger_id) }} vs {{ teamName(c.challenged_id) }}</div>
              <div class="sm-when">📅 {{ fmtMatchTime(c.agreed_at) }}</div>
              <div v-if="c.server" class="sm-srv">🖥️ {{ c.server }}</div>
            </div>
          </section>
        </div>
      </div>

      <!-- ============ STATS ============ -->
      <div v-show="tab === 'stats'">
        <LadderStats :ladder-id="ladder.id" />
      </div>

      <!-- ============ RULES ============ -->
      <div v-show="tab === 'rules'" class="rules-wrap">
        <div class="rcols">
        <div class="rcol">
        <section class="card rules">
          <h3>Format</h3>
          <ul>
            <li><strong>Ruleset:</strong> {{ ladder?.rules?.ruleset || 'smackdown' }} <span class="muted">(KTX competitive standard)</span></li>
            <li><strong>Mode:</strong> 2on2 (TDM) · <strong>Best of {{ ladder?.rules?.best_of || 3 }}</strong></li>
            <li><strong>Timelimit:</strong> {{ ladder?.rules?.timelimit || 10 }} min per map · overtime on a draw</li>
            <li><strong>Maps:</strong> Aerowalk · ztndm3 · DM2 · DM4 · Bravado · Nova · Shifter</li>
          </ul>
        </section>
        <section class="card rules">
          <h3>How it works</h3>
          <ul>
            <li>Challenge a team <strong>1 or 2 rungs</strong> above you.</li>
            <li><strong>Win a 1-rung challenge</strong> → swap places.</li>
            <li><strong>Win a 2-rung challenge</strong> → swap places too. The two teams that played simply exchange rungs; no other team moves (e.g. rung 5 beats rung 3 → 5 and 3 swap, rung 4 is untouched).</li>
            <li><strong>Forfeit</strong> (no game within a week) → the challenged team drops a rung.</li>
            <li>Best of 3 (first to 2) sets the ladder W/L. Natural Bo3 only — a 2–0 is two games, a 2–1 is three; only those games count toward stats, no extra/dead-rubber games. Winners may challenge again immediately.</li>
            <li><strong>Withdraw:</strong> the <strong>challenging</strong> team can pull a challenge any time <strong>before it's scheduled</strong> (no agreed time yet) — this frees both teams. The challenged team can't withdraw; only the side that issued it.</li>
            <li><strong>After a loss</strong> your team <strong>can't issue challenges for 3 days</strong> — you can still be challenged. (A live countdown shows on your row.)</li>
            <li><strong>Win a defense, lift the cooldown:</strong> if a team in cooldown is challenged and <strong>wins</strong>, the cooldown clears <strong>immediately</strong> and they can challenge again right away.</li>
          </ul>
        </section>
        </div>
        <div class="rcol">
        <section class="card rules">
          <h3>Servers &amp; ping</h3>
          <ul>
            <li><strong>NA servers</strong> for any match involving a North American team. This is a North American tournament.</li>
            <li><strong>Exception — Brazil vs Brazil:</strong> two Brazilian teams may play on a BR server. DeepFrag picks it automatically.</li>
            <li><strong>Ping-ups optional (not required).</strong> We match average ping as closely as possible on one server. Players may optionally even up — we recommend a max of <strong>50ms</strong> since this is an NA-focused ladder, with <code>cl_delay_packet_target 50</code>.</li>
            <li>Brazil vs NA plays the <strong>closest-proximity NA server</strong> (e.g. Brazil on Miami, ~100–130ms).</li>
            <li><strong>DeepFrag suggests the server automatically</strong> from both teams' player locations.</li>
            <li>Pool: Denver · Miami · Chicago · Dallas · New York · LA · Iowa · Washington.</li>
          </ul>
        </section>
        </div>
        </div>
        <section class="card rules">
          <details class="ruleset" open>
            <summary><span class="rs-title">📋 Full match ruleset</span><span class="rs-sum">smackdown · 2on2 · Bo3 · 10-min maps</span></summary>
            <div class="rs-body">
              <h4>Format</h4>
              <ul><li>2on2 TDM, ruleset <strong>smackdown</strong>, <strong>best of 3</strong>, 10-minute maps.</li>
                <li>Recent <strong>ezQuake</strong> / <strong>unEzQuake</strong>. In-game: <code>2on2</code>, <code>ruleset smackdown</code>.</li>
                <li><strong>SmackDrive is not permitted.</strong></li></ul>
              <h4>Maps &amp; picks (Bo3)</h4>
              <ul><li>Pool: Aerowalk · ztndm3 · DM2 · DM4 · Bravado · Nova · Shifter.</li>
                <li><code>rnd team1 team2</code> decides the first-pick team (<strong>Team A</strong>; the other is Team B).</li>
                <li><strong>Game 1:</strong> Team A picks. <strong>Game 2:</strong> Team B picks.</li>
                <li><strong>Decider (Game 3, only if 1–1):</strong> from the 5 remaining maps, <strong>Team B tosses first</strong>, then teams <strong>alternate tossing</strong> (B, A, B, A) until <strong>one map remains</strong> — that's the decider.</li>
                <li>No map is played twice.</li></ul>
              <h4>Servers &amp; ping</h4>
              <ul><li><strong>NA servers only</strong> (a Brazil-vs-Brazil match may use a BR server).</li>
                <li>Even pings on the closest-proximity NA server. <strong>Ping-ups optional</strong> (not required) — NA recommended max <strong>50ms</strong> via <code>cl_delay_packet_target 50</code>.</li>
                <li>Proxy / routing allowed. Disputes: agree on a server, else an admin picks — refusing is a forfeit.</li></ul>
              <h4>Client integrity</h4>
              <ul><li>unEzQuake must pass the ruleset check (<strong>CLEAR</strong>).</li>
                <li><strong>unEzQuake only</strong> — required: <code>scr_allowsnap 1</code>, <code>tp_triggers 0</code>, <code>allow_scripts 0</code>.</li>
                <li><strong>Allowed:</strong> the standard team HUD — <code>teamoverlay</code> / <code>show teaminfo</code> (teammate location, health, armor &amp; weapons).</li>
                <li>Banned: anything that changes gameplay/graphics vs ezQuake — jump automation, <em>enemy</em> radar/wallhack overlays, colored backpacks, smartspawn (NOT the teammate overlay above).</li></ul>
              <h4>Match conduct</h4>
              <ul><li><strong>Names:</strong> consistent clan tags + player names all season — critical for stats.</li>
                <li><strong>Pacing:</strong> ≥1 ladder match/week; prioritize ladder over pracs.</li>
                <li><strong>Pauses:</strong> one per team per map. <strong>Sportsmanship</strong> always.</li></ul>
              <h4>Roster</h4>
              <ul><li>Declare full roster at signup. No playing for multiple teams. Changes need admin approval. No stand-ins.</li></ul>
              <h4>Admins</h4>
              <ul><li>Head admins: <strong>Cronus, Nin, Bance</strong>. Disputes → the KOTH Discord channel.</li></ul>
            </div>
          </details>
        </section>
      </div>
    </template>

    <!-- modals -->
    <ClientOnly>
      <AddTeam v-if="showAddTeam && ladder" :ladder-id="ladder.id" @done="onTeamAdded" @close="showAddTeam = false" />
      <AddTeam v-if="editingTeam && ladder" :ladder-id="ladder.id" :edit-team="editingTeam" @done="onTeamAdded" @close="editingTeam = null" />
      <Scheduler v-if="schedulerChallenge" :challenge="schedulerChallenge" :user-team-id="myTeam?.id" @done="onScheduled" @saved="load" @close="schedulerChallenge = null" />
      <MatchDetailModal v-if="openMatchId" :match-id="openMatchId" @close="openMatchId = null" />
    </ClientOnly>
  </div>
</template>

<style scoped>
.wrap { max-width: 1320px; margin: 0 auto; padding: 28px 28px 80px; }
.head { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 8px; margin-bottom: 18px; }
.head .koth-logo { width: 100%; max-width: 440px; height: auto; display: block; filter: drop-shadow(0 6px 24px rgba(0,0,0,0.5)); }
.head .sub { color: var(--fg-2); margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 4px; }
.cta { background: #5865f2; color: #fff; border: none; white-space: nowrap; padding: 9px 16px; border-radius: 9px; font-size: 13px; font-weight: 700; cursor: pointer; }
.cta:hover { background: #4752c4; }
.cta.ghost { background: var(--panel-2); color: var(--fg); border: 1px solid var(--accent); }
.cta.ghost:hover { background: var(--panel-3); }
.muted { color: var(--fg-2); } .small { font-size: 12px; } .pad { padding: 40px 0; text-align: center; }

/* tabs */
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
.tab { background: none; border: 0; color: var(--fg-3); font-weight: 700; font-size: 14px; padding: 12px 18px; cursor: pointer; border-bottom: 2px solid transparent; font-family: inherit; display: flex; align-items: center; gap: 7px; }
.tab:hover { color: var(--fg-2); }
.tab.on { color: var(--accent); border-bottom-color: var(--accent); }
.tcount { background: var(--panel-3); color: var(--fg-2); border-radius: 999px; font-size: 11px; padding: 0 7px; font-family: 'JetBrains Mono', monospace; }

.note { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; margin-bottom: 14px; color: var(--fg-2); font-size: 14px; }
.note.tip { background: rgba(20,230,192,0.08); border-color: rgba(20,230,192,0.3); cursor: pointer; }
.note.err { border-color: var(--loss); color: #fca5a5; }
.note strong { color: var(--fg); }
.empty { text-align: center; padding: 60px 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; }
.empty h2 { margin: 0 0 8px; } .empty p { color: var(--fg-2); max-width: 420px; margin: 0 auto 20px; }

/* bento */
.bento { display: grid; grid-template-columns: minmax(0,2.25fr) minmax(0,1fr); gap: 16px; align-items: start; }
.span2 { grid-column: 1 / -1; }
.rail { display: flex; flex-direction: column; gap: 16px; }
@media (max-width: 880px) { .bento { grid-template-columns: 1fr; } }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }
.card h3 { margin: 0 0 12px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--fg-3); font-weight: 800; display: flex; align-items: center; gap: 8px; }
.card h3 .exp { margin-left: auto; background: none; border: 0; color: var(--accent); font-size: 11px; cursor: pointer; text-transform: none; letter-spacing: 0; font-weight: 600; font-family: inherit; }
.board-card { padding-bottom: 6px; }

.notopen { display: flex; align-items: center; gap: 14px; background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(20,230,192,0.05)); border-color: rgba(245,158,11,0.4); }
.notopen .lock { font-size: 26px; } .notopen-title { font-size: 16px; font-weight: 800; } .notopen-sub { color: var(--fg-2); font-size: 13px; } .notopen-sub strong { color: var(--fg); }

.koth { display: flex; align-items: center; gap: 14px; background: linear-gradient(135deg, rgba(245,158,11,0.14), rgba(20,230,192,0.06)); border-color: rgba(245,158,11,0.35); }
.koth .crown { font-size: 26px; }
.koth-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--draw); font-weight: 700; }
.koth-team { font-size: 18px; font-weight: 800; }
.koth-weeks { margin-left: auto; color: var(--fg-2); font-size: 13px; } .koth-weeks strong { color: var(--fg); font-size: 18px; }

.board { margin: 0 -18px; }
.board-head, .row { display: grid; grid-template-columns: 34px minmax(0,1.5fr) minmax(0,1.1fr) 58px 58px minmax(0,1.15fr); align-items: center; gap: 12px; padding: 10px 18px; }
.c-rec { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--fg-3); text-align: left; white-space: nowrap; }
.c-rec b { color: var(--win); font-weight: 700; } .c-rec .dash { color: var(--fg-3); margin: 0 1px; }
.board-head .c-rec { font-size: 11px; }
.rec-lbl { display: none; }   /* shown only on mobile, where the header row is hidden */
.board-head { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; border-bottom: 1px solid var(--border); }
.row { border-top: 1px solid rgba(43,54,80,.5); font-size: 14px; }
.row:first-of-type { border-top: 0; }
.row .c-rung { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: var(--fg-2); }
.row.top { background: rgba(245,158,11,0.07); } .row.top .c-rung { color: var(--draw); } .row.top .tname::before { content: '👑 '; }
.c-team { display: flex; align-items: center; gap: 8px; min-width: 0; }
.tlogo { width: 22px; height: 22px; border-radius: 5px; object-fit: cover; flex: 0 0 22px; }
.tlogo-ph { display: inline-flex; align-items: center; justify-content: center; background: var(--panel-3); font-size: 12px; opacity: 0.55; }
.ttag { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; color: var(--accent); background: rgba(20,230,192,0.12); border: 1px solid rgba(20,230,192,0.3); border-radius: 5px; padding: 1px 4px; flex: 0 0 auto; min-width: 42px; text-align: center; box-sizing: border-box; }
.tname { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.tlink { color: var(--fg); text-decoration: none; cursor: pointer; } .tlink:hover { color: var(--accent); text-decoration: underline; }
.edit { background: none; border: 0; color: var(--fg-3); cursor: pointer; font-size: 13px; padding: 2px 4px; opacity: .7; } .edit:hover { color: var(--accent); opacity: 1; }
.plink { color: var(--fg-2); text-decoration: none; } .plink:hover { color: var(--accent); text-decoration: underline; }
.c-members { color: var(--fg-2); font-size: 13px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .c-members .dot { color: var(--fg-3); }
.c-status { display: flex; align-items: center; gap: 6px; min-width: 0; }
.badge { font-size: 12px; padding: 4px 11px; border-radius: 999px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; padding: 12px 18px 4px; margin: 0 -18px; border-top: 1px solid var(--border); }
.legend .lg-item { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; color: var(--fg-3); }
.legend .badge { font-size: 11px; padding: 2px 8px; }
.legend em { font-style: italic; }
.badge.open { background: var(--panel-2); color: var(--fg-3); }
.badge.challenged { background: rgba(239,68,68,0.15); color: #fca5a5; }
.badge.cooldown { background: rgba(245,158,11,0.14); color: var(--draw); font-family: 'JetBrains Mono', monospace; }
.note.cooldown-note { background: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.4); color: var(--draw); }
.note.cooldown-note strong { color: var(--fg); font-family: 'JetBrains Mono', monospace; }
.chal-btn { background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.4); border-radius: 6px; padding: 4px 10px; font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; }
.chal-btn:hover { background: rgba(239,68,68,0.28); }

/* small card rows */
.mrow { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; padding: 6px 0; border-bottom: 1px solid rgba(43,54,80,.4); }
.mrow:last-child { border-bottom: 0; } .mrow .mr-t { font-weight: 600; }
/* Upcoming card row: team tags + nowrap time on one line, Preview link indented below */
.uprow { display: grid; grid-template-columns: 1fr auto; align-items: baseline; gap: 4px 10px; font-size: 13px; padding: 8px 0; border-bottom: 1px solid rgba(43,54,80,.4); }
.uprow:last-child { border-bottom: 0; }
.up-teams { font-weight: 700; display: flex; align-items: center; gap: 7px; min-width: 0; }
.up-tag { font-family: 'JetBrains Mono', monospace; color: var(--fg); text-decoration: none; }
.up-tag:hover { color: var(--accent); }
.up-vs { color: var(--fg-3); font-weight: 600; font-size: 12px; }
.up-when { white-space: nowrap; text-align: right; justify-self: end; }
.up-prev { grid-column: 1 / 2; margin-left: 4px; font-size: 12px; font-weight: 600; color: var(--accent); text-decoration: none; }
.up-prev:hover { text-decoration: underline; }
.res { display: flex; align-items: center; gap: 8px; width: 100%; background: none; border: 0; border-bottom: 1px solid rgba(43,54,80,.4); padding: 7px 4px; cursor: pointer; color: var(--fg); font-family: inherit; font-size: 13px; text-align: left; border-radius: 6px; }
.res:last-child { border-bottom: 0; } .res:hover { background: var(--panel-2); }
.res-t { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .res-t.right { text-align: right; }
.res-s { font-family: 'JetBrains Mono', monospace; font-weight: 800; } .res-s b { color: var(--fg-3); } .res-s b.w { color: var(--accent); }
.chal { font-size: 10px; opacity: .5; margin: 0 3px; cursor: help; }
.kpi { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 5px 0; font-size: 13px; }
.kpi b { font-family: 'JetBrains Mono', monospace; color: var(--accent-2, #5eead4); }
.more .soon { margin-left: auto; color: var(--fg-3); font-weight: 400; text-transform: none; font-size: 11px; }

/* schedule */
.ym-teams { display: flex; align-items: center; gap: 8px; font-size: 15px; flex-wrap: wrap; } .ym-teams .vs { color: var(--fg-3); font-size: 12px; }
.ym-status { color: var(--fg-2); font-size: 13px; margin: 8px 0 12px; }
.rail-btn { width: 100%; background: var(--accent); color: var(--bg); border: 0; padding: 9px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.rail-btn:hover { filter: brightness(1.1); }
.ym-actions { display: flex; gap: 8px; }
.rail-btn.ghost, .sched-btn.ghost { background: var(--panel-2); color: var(--fg-2); border: 1px solid var(--border); }
.rail-btn.ghost:hover, .sched-btn.ghost:hover { color: var(--loss); border-color: var(--loss); filter: none; }
.rail-btn:disabled, .sched-btn:disabled { opacity: 0.6; cursor: default; }
.lnk { color: var(--accent); cursor: pointer; }
.chal-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 9px 0; border-top: 1px solid rgba(43,54,80,.5); font-size: 14px; }
.chal-row .arrow { color: var(--accent); } .chal-row .cstatus { color: var(--fg-2); font-size: 12px; } .chal-row .spacer { flex: 1; }
.chal-row .deadline { color: var(--draw); font-size: 12px; font-family: 'JetBrains Mono', monospace; }
.sched-btn { background: var(--accent); color: var(--bg); border: 0; border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit; }
.sm-row { padding: 8px 0; border-top: 1px solid var(--border); font-size: 13px; } .sm-row:first-of-type { border-top: 0; }
.sm-teams { font-weight: 600; } .sm-when { color: var(--accent); font-size: 12px; margin-top: 2px; } .sm-srv { color: var(--fg-3); font-size: 12px; font-family: 'JetBrains Mono', monospace; }

/* rules */
.rules-wrap { display: flex; flex-direction: column; gap: 16px; }
.rcols { display: flex; gap: 16px; align-items: flex-start; }
.rcol { flex: 1; display: flex; flex-direction: column; gap: 16px; min-width: 0; }
@media (max-width: 880px) { .rcols { flex-direction: column; } }
.rules h3 { color: var(--fg-3); }
.rules ul { margin: 0; padding-left: 0; list-style: none; }
.rules li { padding: 6px 0; color: var(--fg-2); padding-left: 18px; position: relative; font-size: 14px; }
.rules li::before { content: '▸'; position: absolute; left: 0; color: var(--accent); }
.rules strong { color: var(--fg); }
.ruleset summary { cursor: pointer; list-style: none; display: flex; flex-direction: column; gap: 2px; padding-left: 16px; position: relative; }
.ruleset summary::-webkit-details-marker { display: none; }
.ruleset summary::before { content: '▸'; color: var(--accent); position: absolute; left: 0; transition: transform .15s; }
.ruleset[open] summary::before { transform: rotate(90deg); }
.rs-title { font-size: 15px; font-weight: 800; color: var(--fg); } .rs-sum { font-size: 12px; color: var(--fg-3); }
.rs-body { margin-top: 14px; padding-left: 16px; }
.rs-body h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--accent); font-weight: 800; margin: 16px 0 6px; } .rs-body h4:first-child { margin-top: 0; }
.rs-body ul { margin: 0; padding-left: 18px; list-style: none; }
.rs-body li { color: var(--fg-2); font-size: 13px; padding: 3px 0; position: relative; } .rs-body li::before { content: '·'; position: absolute; left: -12px; color: var(--fg-3); }
.rs-body code { background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; font-size: 11px; font-family: 'JetBrains Mono', monospace; color: var(--accent); }
.rs-body strong { color: var(--fg); }

/* ── Mobile ─────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .wrap { padding: 16px 12px 64px; }
  .head { margin-bottom: 14px; }
  .head .koth-logo { max-width: 300px; }
  .head .sub { font-size: 13px; }
  /* tabs scroll horizontally instead of wrapping/squishing */
  .tabs { overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
  .tabs::-webkit-scrollbar { display: none; }
  .tab { padding: 11px 13px; flex: 0 0 auto; white-space: nowrap; font-size: 13px; }
  .bento { gap: 12px; }
  .card { padding: 13px 14px; }
  .card h3 .exp { font-size: 11px; }
  /* Standings board → stacked card per team (header row hidden) */
  .board { margin: 0 -14px; }
  .board-head { display: none; }
  .row {
    grid-template-columns: 26px minmax(0,1fr) auto auto;
    grid-template-areas:
      "rung team    team   status"
      "rung players players players"
      "rung match   games  games";
    column-gap: 8px; row-gap: 3px; padding: 11px 14px; align-items: center;
  }
  .row .c-rung    { grid-area: rung; }
  .row .c-team    { grid-area: team; }
  .row .c-members { grid-area: players; font-size: 12px; }
  .row .c-match   { grid-area: match; }
  .row .c-games   { grid-area: games; }
  .row .c-status  { grid-area: status; justify-self: end; }
  .c-rec { font-size: 12px; }
  .rec-lbl { display: inline; color: var(--fg-3); font-weight: 700; }
  /* legend wraps cleanly */
  .legend { gap: 5px 12px; padding: 12px 14px 4px; margin: 0 -14px; }
  /* schedule + rules already stack via their own breakpoints */
  .chal-row { font-size: 13px; }
  .koth-team { font-size: 17px; }
}
@media (max-width: 380px) {
  .row { grid-template-columns: 22px minmax(0,1fr) auto auto; }
  .head .koth-logo { max-width: 260px; }
}
</style>

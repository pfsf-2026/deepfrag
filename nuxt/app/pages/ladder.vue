<script setup>
// Speakeasy 2v2 ladder — public standings board. Reads /api/ladder (active
// ladders) then /api/ladder/{id} for the ranked rungs, King of the Hill, and
// open challenges. Captain self-serve (challenge/report) is Discord-gated and
// lands on top of this once OAuth is live.
const df = useDeepFrag()
const { user, loggedIn, login } = useAuth()
// Show the claim flow when signed in but not yet linked to a profile (and no
// pending claim already in flight).
const needsClaim = computed(() => loggedIn.value && user.value && !user.value.canonical_id && !user.value.pending_claim)
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const ladder = ref(null)
const teams = ref([])
const koth = ref(null)
const challenges = ref([])
const loading = ref(true)
const err = ref(null)

async function loadDetail(id) {
  const d = await $fetch(`${base}/api/ladder/${id}`)
  ladder.value = d.ladder
  teams.value = d.teams || []
  koth.value = d.koth
  challenges.value = d.challenges || []
}

async function load() {
  loading.value = true
  err.value = null
  try {
    const list = await $fetch(`${base}/api/ladder`)
    const first = (list.ladders || [])[0]
    if (!first) { ladder.value = null; return }
    await loadDetail(first.id)
  } catch (e) {
    err.value = 'Could not load the ladder.'
    console.error('[ladder]', e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// challenged_id -> list of incoming challenger names (to badge rows)
const incoming = computed(() => {
  const m = {}
  for (const c of challenges.value) {
    (m[c.challenged_id] ||= []).push(c)
  }
  return m
})

function teamName(id) {
  return teams.value.find(t => t.id === id)?.name || `#${id}`
}
function membersLabel(t) {
  return (t.members || []).map(m => m.display).join(' · ')
}

useHead({ title: 'Speakeasy Ladder · DeepFrag' })
</script>

<template>
  <div class="wrap">
    <header class="head">
      <div>
        <h1>Speakeasy <span class="accent">2v2</span> Ladder</h1>
        <p class="sub">Challenge up. Win to climb. King of the Hill runs to Christmas.</p>
      </div>
      <button v-if="!loggedIn" class="cta" @click="login">Sign in with Discord to play</button>
    </header>

    <ClientOnly>
      <ClaimProfile v-if="needsClaim" />
      <div v-else-if="user?.pending_claim" class="pending-note">
        ⏳ Profile claim for <strong>{{ user.pending_claim.display }}</strong> is awaiting admin approval.
      </div>
    </ClientOnly>

    <div v-if="loading" class="muted pad">Loading the board…</div>
    <div v-else-if="err" class="muted pad">{{ err }}</div>
    <div v-else-if="!ladder" class="empty">
      <h2>The ladder isn't open yet</h2>
      <p>Teams are being seeded. Sign in with Discord and you'll be ready to challenge the moment it goes live.</p>
      <button v-if="!loggedIn" class="cta" @click="login">Sign in with Discord</button>
    </div>

    <template v-else>
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
            <span class="tname">{{ t.name }}</span>
          </span>
          <span class="c-members">{{ membersLabel(t) || '—' }}</span>
          <span class="c-status">
            <span v-if="incoming[t.id]?.length" class="badge challenged">
              ⚔ Challenged by {{ incoming[t.id].map(c => teamName(c.challenger_id)).join(', ') }}
            </span>
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
            <span v-if="c.deadline" class="deadline">play by {{ new Date(c.deadline).toLocaleDateString() }}</span>
          </li>
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
          <li>Best of 3. Winners may re-challenge immediately; losers wait a week.</li>
          <li>Maps: Aerowalk · ztndm3 · DM2 · DM4 · Bravado · Nova · Shifter.</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.wrap { max-width: 880px; margin: 0 auto; padding: 32px 24px 80px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.head h1 { font-size: 28px; font-weight: 900; letter-spacing: -0.02em; margin: 0; }
.head .accent { color: var(--accent); }
.head .sub { color: var(--fg-2); margin: 6px 0 0; font-size: 14px; }
.cta {
  background: #5865f2; color: #fff; border: none; white-space: nowrap;
  padding: 10px 18px; border-radius: 9px; font-size: 14px; font-weight: 700; cursor: pointer;
}
.cta:hover { background: #4752c4; }
.muted { color: var(--fg-2); }
.pad { padding: 40px 0; text-align: center; }
.pending-note { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px; color: var(--fg-2); font-size: 14px; }

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
.tname { font-weight: 700; }
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
.challenges .deadline { margin-left: auto; color: var(--draw); font-size: 12px; font-family: 'JetBrains Mono', monospace; }
.rules li { padding: 6px 0; color: var(--fg-2); padding-left: 20px; position: relative; }
.rules li::before { content: '▸'; position: absolute; left: 0; color: var(--accent); }
.rules strong { color: var(--fg); }
</style>

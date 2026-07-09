<script setup>
// Phase 1 of the 4on4 scheduling engine: a "who's up for games tonight" board.
// Players mark what they're up for (duel / 2on2 / 4on4) + roughly when; everyone
// sees who's around and how close a game is. Presence/ready-check + in-game
// notifications come later.
useHead({ title: 'Mix — who’s on tonight · DeepFrag' })
const { user, loggedIn, ready, authHeader, fetchMe, login } = useAuth()
const base = import.meta.client ? '' : (useRuntimeConfig().public.apiBase || '')

const GAMES = [
  { k: 'duel', label: 'Duel', need: 2 },
  { k: '2on2', label: '2on2', need: 4 },
  { k: '4on4', label: '4on4', need: 8 },
]
const board = ref({ signups: [], counts: { duel: 0, '2on2': 0, '4on4': 0 }, total: 0 })
const loading = ref(true)
const saving = ref(false)

// my picks (prefilled from my existing signup if I'm already on the board)
const picks = reactive({ duel: false, '2on2': false, '4on4': false })
const fromHour = ref('') // '' = flexible/now, else '0'..'23'
const note = ref('')
const browserTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone } catch { return null } }

const me = computed(() => board.value.signups.find(s => s.is_me) || null)

function fmtHour(h) {
  if (h === null || h === undefined || h === '') return 'now / flexible'
  const n = Number(h); const ap = n < 12 ? 'am' : 'pm'; const h12 = (n % 12) || 12
  return `${h12}${ap}`
}
const hourOptions = Array.from({ length: 24 }, (_, i) => ({ v: String(i), t: fmtHour(i) }))

async function load() {
  try {
    board.value = await $fetch(`${base}/api/mix/tonight`, { headers: authHeader() })
  } catch { /* ignore */ } finally { loading.value = false }
  // prefill controls from my current signup once
  if (me.value && !dirty.value) {
    for (const g of GAMES) picks[g.k] = me.value.games.includes(g.k)
    fromHour.value = me.value.from_hour === null || me.value.from_hour === undefined ? '' : String(me.value.from_hour)
    note.value = me.value.note || ''
  }
}
const dirty = ref(false)
function touch() { dirty.value = true }

async function submit() {
  const games = GAMES.filter(g => picks[g.k]).map(g => g.k)
  if (!games.length) return
  saving.value = true
  try {
    await $fetch(`${base}/api/mix/signup`, {
      method: 'POST', headers: authHeader(),
      body: { games, from_hour: fromHour.value === '' ? null : Number(fromHour.value), tz: browserTz(), note: note.value },
    })
    dirty.value = false
    await load()
  } catch (e) { /* ignore */ } finally { saving.value = false }
}
async function leave() {
  saving.value = true
  try {
    await $fetch(`${base}/api/mix/leave`, { method: 'POST', headers: authHeader() })
    for (const g of GAMES) picks[g.k] = false
    dirty.value = false
    await load()
  } catch { /* ignore */ } finally { saving.value = false }
}

function playersFor(k) { return board.value.signups.filter(s => s.games.includes(k)) }

let timer = null
onMounted(async () => {
  if (!ready.value) await fetchMe()
  await load()
  timer = setInterval(load, 45000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<template>
<div class="mix">
  <header class="head">
    <h1>🎯 Mix — who's on tonight</h1>
    <p class="sub">Mark what you're up for tonight. Everyone sees who's around and how close a game is.
      <NuxtLink to="/ladder" class="ln">← ladder</NuxtLink></p>
  </header>

  <!-- Signup panel -->
  <section class="panel signup">
    <template v-if="ready && !loggedIn">
      <p class="muted">Sign in with Discord to add yourself to tonight's board.</p>
      <button class="btn primary" @click="login">Sign in with Discord</button>
    </template>
    <template v-else>
      <div class="row games">
        <span class="lbl">I'm up for</span>
        <label v-for="g in GAMES" :key="g.k" class="chip" :class="{ on: picks[g.k] }">
          <input type="checkbox" v-model="picks[g.k]" @change="touch"> {{ g.label }}
        </label>
      </div>
      <div class="row">
        <span class="lbl">from</span>
        <select v-model="fromHour" @change="touch" class="sel">
          <option value="">now / flexible</option>
          <option v-for="o in hourOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
        </select>
        <span class="muted sm">{{ browserTz() }}</span>
      </div>
      <div class="row">
        <span class="lbl">note</span>
        <input v-model="note" @input="touch" maxlength="140" class="txt" placeholder="optional — e.g. 'after 9, dm4 only'">
      </div>
      <div class="row actions">
        <button class="btn primary" :disabled="saving || !(picks.duel||picks['2on2']||picks['4on4'])" @click="submit">
          {{ me ? 'Update' : "I'm in tonight" }}
        </button>
        <button v-if="me" class="btn ghost" :disabled="saving" @click="leave">Leave</button>
        <span v-if="me" class="muted sm on-since">✓ you're on the board</span>
      </div>
    </template>
  </section>

  <!-- Count cards -->
  <section class="cards">
    <div v-for="g in GAMES" :key="g.k" class="card" :class="{ hot: board.counts[g.k] >= g.need }">
      <div class="c-top"><span class="c-label">{{ g.label }}</span><span class="c-need">need {{ g.need }}</span></div>
      <div class="c-num">{{ board.counts[g.k] }}</div>
      <div class="c-foot">
        <span v-if="board.counts[g.k] >= g.need" class="ready">🔥 enough for a game</span>
        <span v-else class="muted">{{ g.need - board.counts[g.k] }} more</span>
      </div>
    </div>
  </section>

  <!-- Per-game rosters -->
  <section v-if="!loading" class="rosters">
    <div v-for="g in GAMES" :key="g.k" class="rcol">
      <h3>{{ g.label }} <span class="muted">· {{ playersFor(g.k).length }}</span></h3>
      <div v-if="!playersFor(g.k).length" class="muted sm empty">nobody yet</div>
      <div v-for="s in playersFor(g.k)" :key="s.discord_id" class="prow" :class="{ me: s.is_me }">
        <span class="pn">{{ s.name }}</span>
        <span class="pr" :title="s.matches + ' games rated'">{{ s.rating ?? '—' }}</span>
        <span class="pt">{{ fmtHour(s.from_hour) }}</span>
      </div>
    </div>
  </section>
  <p v-if="!loading && !board.total" class="muted empty-all">No one's marked in yet tonight — be the first.</p>
</div>
</template>

<style scoped>
.mix { max-width: 900px; margin: 0 auto; padding: 14px 18px 60px; color: var(--fg, #e8edf5); }
.head h1 { font-size: 26px; font-weight: 800; margin: 6px 0 4px; }
.sub { color: var(--fg-2, #94a3b8); font-size: 14px; margin: 0 0 16px; }
.ln { color: var(--accent, #14e6c0); text-decoration: none; margin-left: 8px; }
.muted { color: var(--fg-3, #64748b); } .sm { font-size: 12px; }
.panel { background: var(--panel, #131820); border: 1px solid var(--border, #2b3445); border-radius: 12px; padding: 14px 16px; }
.signup .row { display: flex; align-items: center; gap: 10px; margin: 8px 0; flex-wrap: wrap; }
.lbl { width: 64px; color: var(--fg-3); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 20px; cursor: pointer; font-weight: 600; font-size: 14px; user-select: none; }
.chip.on { border-color: var(--accent); color: var(--accent); background: rgba(20,230,192,.08); }
.chip input { accent-color: var(--accent); }
.sel, .txt { background: var(--panel-2, #0d1219); border: 1px solid var(--border); border-radius: 8px; color: var(--fg); padding: 7px 10px; font: inherit; }
.txt { flex: 1; min-width: 200px; }
.actions { margin-top: 12px; }
.btn { border: 1px solid var(--border); background: var(--panel-2); color: var(--fg); border-radius: 8px; padding: 8px 16px; font-weight: 700; cursor: pointer; font: inherit; }
.btn.primary { background: var(--accent, #14e6c0); border-color: var(--accent); color: #04110d; }
.btn.ghost { background: none; }
.btn:disabled { opacity: .5; cursor: default; }
.on-since { color: var(--accent) !important; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 18px 0; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.card.hot { border-color: var(--accent); box-shadow: 0 0 0 1px rgba(20,230,192,.3) inset; }
.c-top { display: flex; justify-content: space-between; align-items: baseline; }
.c-label { font-weight: 800; font-size: 15px; } .c-need { font-size: 11px; color: var(--fg-3); }
.c-num { font-size: 40px; font-weight: 800; font-family: 'JetBrains Mono', monospace; line-height: 1.1; }
.card.hot .c-num { color: var(--accent); }
.c-foot { font-size: 12px; } .ready { color: var(--accent); font-weight: 700; }
.rosters { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.rcol h3 { font-size: 14px; font-weight: 800; margin: 0 0 8px; }
.prow { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; align-items: center; padding: 6px 8px; border-bottom: 1px solid rgba(43,54,80,.4); font-size: 13px; }
.prow.me { background: rgba(20,230,192,.07); border-radius: 6px; }
.pn { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pr { font-family: 'JetBrains Mono', monospace; color: var(--fg-2); font-size: 12px; }
.pt { color: var(--fg-3); font-size: 11px; font-family: 'JetBrains Mono', monospace; }
.empty { padding: 8px; } .empty-all { text-align: center; margin-top: 24px; }
@media (max-width: 640px) {
  .cards, .rosters { grid-template-columns: 1fr; }
  .lbl { width: 100%; }
}
</style>

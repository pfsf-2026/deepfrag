<script setup>
// /coach/player/{id}/game/{hub_game_id} — one game's report for one player (2026-10-17, Peter):
// summary, two-minute blocks, highlights, lowlights, each with a hub.quakeworld.nu link at that
// second, and 2-3 rewinds: a locked spawn where a better first move or an item on time existed.
// The player reads the team's MM2 from the 20 s before, types what they should have thought and
// where to go (no voice), then checks the answer and the MM2 line to send. Data:
// /api/players/{id}/games/{gid}/report (built from the demo on first open, cached after).
const route = useRoute()
const id = computed(() => String(route.params.id || ''))
const gid = computed(() => String(route.params.gid || ''))
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const { authHeader } = useAuth()

const rep = ref(null)
const loading = ref(false)
const err = ref('')
const step = ref(0)
const STEPS = ['Fetching the demo from the hub…', 'Reading all eight players at one second…', 'Finding your moments…', 'Writing the rewinds…']
let timer = null

async function load(fresh = false) {
  loading.value = true; err.value = ''; step.value = 0
  clearInterval(timer); timer = setInterval(() => { if (step.value < STEPS.length - 1) step.value++ }, 7000)
  try {
    const u = `${base}/api/players/${encodeURIComponent(id.value)}/games/${encodeURIComponent(gid.value)}/report` + (fresh ? `?fresh=${Date.now()}` : '')
    const r = await fetch(u)
    if (!r.ok) {
      let d = ''
      try { d = (await r.json()).detail || '' } catch { /* not json */ }
      throw new Error(d ? `${d}` : `report ${r.status}`)
    }
    rep.value = await r.json()
    restoreAnswers()
  } catch (e) { err.value = String(e?.message || e) } finally { loading.value = false; clearInterval(timer) }
}

// rewind answers: kept in the browser, and sent to the API (per Discord user when signed in)
const answers = ref({})
const revealed = ref({})
const saved = ref({})
const akey = () => `gr-ans:${id.value}:${gid.value}`
function restoreAnswers() {
  try { const c = JSON.parse(localStorage.getItem(akey()) || '{}'); answers.value = c.answers || {}; revealed.value = c.revealed || {} } catch { /* private mode */ }
}
function persist() { try { localStorage.setItem(akey(), JSON.stringify({ answers: answers.value, revealed: revealed.value })) } catch { /* ignore */ } }
async function check(w) {
  revealed.value = { ...revealed.value, [w.idx]: true }; persist()
  const a = (answers.value[w.idx] || '').trim()
  if (!a) return
  try {
    const r = await fetch(`${base}/api/players/${encodeURIComponent(id.value)}/games/${encodeURIComponent(gid.value)}/report/answers`,
      { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify({ idx: w.idx, answer: a }) })
    saved.value = { ...saved.value, [w.idx]: r.ok }
  } catch { saved.value = { ...saved.value, [w.idx]: false } }
}
function retry(w) { revealed.value = { ...revealed.value, [w.idx]: false }; persist() }

onMounted(() => { load() })
onBeforeUnmount(() => clearInterval(timer))
useHead({ title: () => `Game report · ${rep.value?.display || id.value} · DeepFrag` })

const s = computed(() => rep.value?.summary || {})
const myTeam = computed(() => (rep.value?.teams || []).find(t => t.name === rep.value?.team))
const oppTeam = computed(() => (rep.value?.teams || []).find(t => t.name !== rep.value?.team))
const win = computed(() => myTeam.value && oppTeam.value ? (myTeam.value.frags > oppTeam.value.frags ? 'W' : myTeam.value.frags < oppTeam.value.frags ? 'L' : '–') : '')
const maxDmg = computed(() => Math.max(1, ...(rep.value?.blocks || []).map(b => Math.max(b.dealt || 0, b.taken || 0))))
const mm2Team = computed(() => Object.entries(rep.value?.mm2?.team || {}).filter(([n]) => n !== rep.value?.player).sort((a, b) => b[1] - a[1]))
function mmss(ms) { ms = Math.max(0, ms | 0); return `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}` }
function fmtDate(d) { return d ? new Date(d).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '' }
const KIND = { powerup: 'powerup', streak: 'streak', streak_end: 'ended a streak', life: 'big life', item_locked: 'item under lock', quad_death: 'died with quad', stack_no_gun: 'stack, no gun', alone_into_2: 'alone into two', empty_cluster: 'empty lives' }
</script>

<template>
  <div class="page">
    <div class="crumbs">
      <NuxtLink :to="`/coach/player/${encodeURIComponent(id)}`" class="back">← {{ rep?.display || id }}'s coach</NuxtLink>
      <span class="sep">·</span>
      <NuxtLink :to="`/p/${encodeURIComponent(id)}`" class="back">profile</NuxtLink>
    </div>

    <div v-if="loading" class="box">
      <div class="steps"><div v-for="(st, i) in STEPS" :key="st" class="st" :class="{ on: i === step, done: i < step }">{{ st }}</div></div>
      <div class="muted">First open of a game takes about half a minute: the demo is read from the hub and every player is tracked at one second.</div>
    </div>
    <div v-else-if="err" class="box err">{{ err }} <button class="lnk" @click="load(true)">try again</button></div>

    <template v-else-if="rep">
      <header class="head">
        <h1>Game report <span class="who">· {{ rep.display || rep.player }}</span></h1>
        <div class="meta">
          <span class="map">{{ rep.map }}</span>
          <span class="res" :class="{ w: win === 'W', l: win === 'L' }">{{ win }}</span>
          <span v-if="myTeam && oppTeam" class="score">{{ myTeam.frags }}–{{ oppTeam.frags }}</span>
          <span class="muted">{{ fmtDate(rep.played_at) }}</span>
          <a v-if="rep.hub" :href="rep.hub" target="_blank" rel="noopener" class="hub">watch on the hub ↗</a>
        </div>
        <div class="teams muted">{{ rep.team }}: {{ [rep.player, ...(rep.mates || [])].join(', ') }} &nbsp;vs&nbsp; {{ (rep.foes || []).join(', ') }}</div>
      </header>

      <!-- summary -->
      <section class="sec">
        <div class="chips">
          <div class="chip"><b>{{ s.frags }}</b><span>frags</span></div>
          <div class="chip"><b>{{ s.deaths }}</b><span>deaths</span></div>
          <div class="chip"><b>{{ s.armed_pct }}%</b><span>of alive time with RL or LG</span></div>
          <div class="chip"><b>{{ s.empty_lives }}</b><span>empty lives (under 50 dmg, no frag, no item)</span></div>
          <div class="chip"><b>{{ s.locked_spawns }}</b><span>spawns while locked · {{ s.chained_locked }} died inside 14 s</span></div>
          <div class="chip" v-if="s.first_damage_pct != null"><b>{{ s.first_damage_pct }}%</b><span>of fights you hit first ({{ s.fights }})</span></div>
          <div class="chip"><b>{{ s.stack_no_gun_deaths }}</b><span>deaths stacked without a gun</span></div>
          <div class="chip"><b>{{ rep.mm2?.sent }}</b><span>MM2 lines sent · team {{ rep.mm2?.team_total }}</span></div>
        </div>
        <div class="muted small">Locked = your team's margin (enemy stack minus yours, plus 100 per RL) above the map's 85th percentile ({{ rep.lock_threshold }}); your team was locked {{ rep.locked_pct }}% of the game.</div>
      </section>

      <!-- rewinds -->
      <section class="sec" v-if="rep.rewinds?.length">
        <div class="sectitle">⏪ Rewinds <span class="muted small">— no voice. Read what your team's MM2 told you, then decide.</span></div>
        <div v-for="w in rep.rewinds" :key="w.idx" class="card rw">
          <div class="q">{{ w.question }}</div>
          <div class="comms">
            <div class="lbl">Your team's MM2 in the 20 s before</div>
            <ul v-if="w.comms?.length"><li v-for="(c, i) in w.comms" :key="i"><span class="t">{{ mmss(c.t) }}</span><span class="m">{{ c.text }}</span></li></ul>
            <div v-else class="muted small">nothing — your team sent no MM2 in those 20 s</div>
            <div class="lbl">You sent</div>
            <div class="muted small">{{ w.you_sent?.length ? w.you_sent.join(' · ') : 'nothing' }}</div>
          </div>
          <label class="lbl" :for="`ans-${w.idx}`">What should you have thought at that moment, and where do you go?</label>
          <textarea :id="`ans-${w.idx}`" v-model="answers[w.idx]" rows="3" placeholder="e.g. they have RL and quad, yellow is up in 5 s at …, I go …" :disabled="revealed[w.idx]" @input="persist"></textarea>
          <div class="btns">
            <button v-if="!revealed[w.idx]" class="btn" @click="check(w)">Check my answer</button>
            <button v-else class="lnk" @click="retry(w)">answer again</button>
            <a v-if="w.hub" :href="w.hub" target="_blank" rel="noopener" class="hub">watch this moment ↗</a>
          </div>
          <div v-if="revealed[w.idx]" class="reveal">
            <div class="lbl">What you did</div>
            <p>{{ w.did }}</p>
            <div class="lbl">Answer</div>
            <p>{{ w.answer }}</p>
            <div class="lbl">MM2 to send</div>
            <div class="mm2"><code v-for="(m, i) in w.mm2" :key="i">{{ m }}</code></div>
            <div v-if="saved[w.idx] === false" class="muted small">Your answer is kept in this browser; sign in to keep it on your profile.</div>
          </div>
        </div>
      </section>
      <section class="sec" v-else>
        <div class="sectitle">⏪ Rewinds</div>
        <div class="box muted">No rewind in this game: none of your locked spawns lasted long enough to be a decision, or your first moves were already the ones that survive most.</div>
      </section>

      <!-- blocks -->
      <section class="sec">
        <div class="sectitle">🕒 Two-minute blocks</div>
        <div class="blocks">
          <div v-for="b in rep.blocks" :key="b.t0" class="blk">
            <a v-if="b.hub" :href="b.hub" target="_blank" rel="noopener" class="bl">{{ b.label }}</a><span v-else class="bl">{{ b.label }}</span>
            <span class="fd"><b>{{ b.frags }}</b>F <b>{{ b.deaths }}</b>D</span>
            <span class="bars"><span class="bar d" :style="{ width: (100 * (b.dealt || 0) / maxDmg) + '%' }" :title="`dealt ${b.dealt}`"></span><span class="bar t" :style="{ width: (100 * (b.taken || 0) / maxDmg) + '%' }" :title="`taken ${b.taken}`"></span></span>
            <span class="items">{{ (b.items || []).join(' ') }}</span>
            <span class="lock" :class="{ hot: b.locked_s >= 60 }">{{ b.locked_s }}s locked</span>
          </div>
        </div>
        <div class="muted small">Bars: damage dealt (orange) and taken (grey) in the block. Click a block to watch it on the hub.</div>
      </section>

      <!-- highlights / lowlights -->
      <div class="two">
        <section class="sec">
          <div class="sectitle">▲ Highlights</div>
          <ul class="mom" v-if="rep.highlights?.length"><li v-for="(h, i) in rep.highlights" :key="i"><a v-if="h.hub" :href="h.hub" target="_blank" rel="noopener" class="t">{{ mmss(h.t) }}</a><span v-else class="t">{{ mmss(h.t) }}</span><span class="k good">{{ KIND[h.kind] || h.kind }}</span><span class="x">{{ h.text }}</span></li></ul>
          <div v-else class="box muted">No streak, powerup run or multi-frag life in this game.</div>
        </section>
        <section class="sec">
          <div class="sectitle">▼ Lowlights</div>
          <ul class="mom" v-if="rep.lowlights?.length"><li v-for="(h, i) in rep.lowlights" :key="i"><a v-if="h.hub" :href="h.hub" target="_blank" rel="noopener" class="t">{{ mmss(h.t) }}</a><span v-else class="t">{{ mmss(h.t) }}</span><span class="k bad">{{ KIND[h.kind] || h.kind }}</span><span class="x">{{ h.text }}</span></li></ul>
          <div v-else class="box muted">Nothing to flag.</div>
        </section>
      </div>

      <!-- MM2 -->
      <section class="sec">
        <div class="sectitle">💬 MM2</div>
        <div class="card">
          <p>You sent <b>{{ rep.mm2?.sent }}</b> team messages ({{ rep.mm2?.per_min }} a minute alive). Teammates: <span v-for="([n, c], i) in mm2Team" :key="n">{{ n }} {{ c }}<span v-if="i < mm2Team.length - 1">, </span></span>.</p>
          <p class="muted small">EU teams run on MM2 and NA teams on voice. The floor for a fours player is one line on every spawn (<code>need armor weapon @ loc</code>) and one on every loss (<code>lost loc 2&gt;</code>), so the player with the RL knows where the fight is without anyone talking.</p>
        </div>
      </section>

      <div class="muted small foot">Report v{{ rep.version }}{{ rep.cached ? ', cached' : '' }} · <button class="lnk" @click="load(true)">rebuild</button> · spawn points and first-room survival from 60 TB4 games at one second; moments from this game's demo.</div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 18px 16px 90px; display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.crumbs { display: flex; gap: 8px; align-items: baseline; font-size: 13px; flex-wrap: wrap; }
.back { color: var(--fg-2); text-decoration: none; font-weight: 600; } .back:hover { color: var(--accent); }
.sep { color: var(--fg-3); }
.box { padding: 16px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); font-size: 14px; line-height: 1.5; }
.box.err { color: #fca5a5; }
.steps { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.st { opacity: 0.45; } .st.on { opacity: 1; color: var(--accent); font-weight: 700; } .st.done { opacity: 0.7; }
.head { display: flex; flex-direction: column; gap: 6px; }
h1 { font-size: clamp(22px, 5vw, 30px); font-weight: 900; margin: 0; letter-spacing: -0.01em; line-height: 1.1; }
.who { color: var(--fg-2); font-weight: 700; }
.meta { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; font-size: 14px; }
.map { font-weight: 800; font-size: 16px; }
.res { font-weight: 900; } .res.w { color: #34d67a; } .res.l { color: #ff5d6c; }
.score { font-variant-numeric: tabular-nums; font-weight: 700; }
.teams { font-size: 12px; overflow-wrap: anywhere; }
.muted { color: var(--fg-2); } .small { font-size: 12px; line-height: 1.5; }
.hub { color: var(--accent); text-decoration: none; font-size: 13px; font-weight: 600; min-height: 36px; display: inline-flex; align-items: center; }
.sec { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.sectitle { font-weight: 800; font-size: 14px; letter-spacing: 0.02em; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; min-width: 0; }
.card p { margin: 0 0 8px; line-height: 1.5; font-size: 14px; }
.chips { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr)); gap: 8px; }
.chip { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.chip b { font-size: 20px; font-variant-numeric: tabular-nums; } .chip span { font-size: 12px; color: var(--fg-2); line-height: 1.3; }
/* rewinds */
.rw { display: flex; flex-direction: column; gap: 10px; border-left: 3px solid var(--accent); }
.q { font-weight: 700; font-size: 15px; line-height: 1.45; }
.lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--fg-2); font-weight: 700; }
.comms ul { list-style: none; margin: 4px 0 8px; padding: 0; display: flex; flex-direction: column; gap: 2px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.comms li { display: flex; gap: 8px; min-width: 0; } .comms .t { color: var(--fg-2); flex: 0 0 auto; } .comms .m { overflow-wrap: anywhere; }
textarea { width: 100%; box-sizing: border-box; background: #0d0a07; color: inherit; border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; font: inherit; font-size: 14px; resize: vertical; min-height: 72px; }
textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.btns { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.btn { background: var(--accent); color: #140b03; border: 0; border-radius: 999px; padding: 10px 16px; font-weight: 800; font-size: 14px; cursor: pointer; min-height: 40px; }
.lnk { background: none; border: 0; color: var(--accent); font: inherit; font-weight: 700; cursor: pointer; padding: 8px 0; min-height: 36px; }
.reveal { border-top: 1px dashed var(--border); padding-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.reveal p { margin: 0 0 6px; font-size: 14px; line-height: 1.5; }
.mm2 { display: flex; gap: 6px; flex-wrap: wrap; } .mm2 code, .card code { background: #0d0a07; border: 1px solid var(--border); border-radius: 6px; padding: 3px 8px; font-size: 12px; }
/* blocks */
.blocks { display: flex; flex-direction: column; gap: 4px; }
.blk { display: grid; grid-template-columns: 76px 64px 1fr; gap: 6px 10px; align-items: center; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; font-size: 13px; min-width: 0; }
.bl { font-variant-numeric: tabular-nums; color: var(--accent); text-decoration: none; font-weight: 700; } span.bl { color: inherit; }
.fd { font-variant-numeric: tabular-nums; white-space: nowrap; } .fd b { font-weight: 800; }
.bars { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.bar { display: block; height: 6px; border-radius: 3px; } .bar.d { background: var(--accent); } .bar.t { background: #6b6257; }
.items { grid-column: 1 / 3; font-size: 12px; color: var(--fg-2); text-transform: uppercase; letter-spacing: 0.04em; min-height: 1em; }
.lock { grid-column: 3; font-size: 12px; color: var(--fg-2); justify-self: end; } .lock.hot { color: #fca5a5; }
@media (min-width: 640px) {
  .blk { grid-template-columns: 76px 64px 1fr 110px 80px; }
  .items { grid-column: auto; } .lock { grid-column: auto; }
}
/* moments */
.two { display: grid; grid-template-columns: 1fr; gap: 18px; }
@media (min-width: 800px) { .two { grid-template-columns: 1fr 1fr; } }
.mom { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.mom li { display: grid; grid-template-columns: 48px 1fr; gap: 4px 10px; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 13px; line-height: 1.4; min-width: 0; }
.mom .t { color: var(--accent); text-decoration: none; font-weight: 700; font-variant-numeric: tabular-nums; } .mom span.t { color: inherit; }
.mom .k { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 800; } .k.good { color: #34d67a; } .k.bad { color: #ff5d6c; }
.mom .x { grid-column: 2; overflow-wrap: anywhere; }
.foot { padding-top: 8px; }
@media (min-width: 720px) { .page { padding: 24px 32px 100px; } }
</style>

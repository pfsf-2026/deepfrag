<script setup>
// Community vote: the upcoming KOTH duel (1v1) league — pool size + ranked
// map picks. Nin's spec: NO login, no hurdles — you vote as your in-game
// handle. "No randoms": the handle must resolve to a known DeepFrag player
// (autocomplete below is the player DB). One ballot per player, editable.
const poll = ref(null)
const loading = ref(true)
const err = ref(null)
const submitting = ref(false)
const editing = ref(false)

// who am I voting as
const handleQuery = ref('')
const picked = ref(null)          // {canonical_id, display}
const players = ref([])
const showDrop = ref(false)

const poolSize = ref(null)
const ranking = ref([])
const voted = ref(false)          // this browser submitted (results gate)

const VOTE_KEY = 'df_vote_duel_league'
const maxRanked = computed(() => poll.value?.question_2?.max_ranked || 11)
const matches = computed(() => {
  const q = handleQuery.value.trim().toLowerCase()
  if (!q || q.length < 2) return []
  return players.value.filter(p =>
    p.display.toLowerCase().includes(q) || p.canonical_id.includes(q)).slice(0, 8)
})

async function load() {
  loading.value = true
  try {
    let saved = null
    try { saved = JSON.parse(localStorage.getItem(VOTE_KEY) || 'null') } catch {}
    const q = saved?.canonical_id ? { player: saved.canonical_id } : {}
    poll.value = await $fetch('/api/vote/duel-league', { query: q })
    if (saved?.canonical_id && poll.value.my_vote) {
      picked.value = { canonical_id: saved.canonical_id, display: poll.value.my_vote.handle || saved.display }
      poolSize.value = poll.value.my_vote.pool_size
      ranking.value = [...(poll.value.my_vote.map_ranking || [])]
      voted.value = true
    }
  } catch (e) { err.value = 'Could not load the poll — try a refresh.' }
  loading.value = false
}
onMounted(() => {
  load()
  $fetch('/api/players?limit=5000').then(d => {
    players.value = (d.players || d || []).map(p => ({
      canonical_id: p.canonical_id, display: p.display || p.canonical_id }))
  }).catch(() => {})
})

function pick(p) { picked.value = p; handleQuery.value = p.display; showDrop.value = false }
function toggleMap(m) {
  const i = ranking.value.indexOf(m)
  if (i >= 0) ranking.value.splice(i, 1)
  else if (ranking.value.length < maxRanked.value) ranking.value.push(m)
}
function rankOf(m) { const i = ranking.value.indexOf(m); return i >= 0 ? i + 1 : null }

async function submit() {
  if (!picked.value || !poolSize.value || !ranking.value.length) return
  submitting.value = true
  err.value = null
  try {
    const r = await $fetch('/api/vote/duel-league', {
      method: 'POST',
      body: { handle: picked.value.canonical_id, pool_size: poolSize.value, map_ranking: ranking.value },
    })
    poll.value = { ...poll.value, my_vote: r.my_vote, results: r.results }
    try { localStorage.setItem(VOTE_KEY, JSON.stringify({ canonical_id: r.voter_id, display: r.my_vote.handle })) } catch {}
    voted.value = true
    editing.value = false
  } catch (e) {
    err.value = e?.data?.detail || 'Vote failed — try again.'
  }
  submitting.value = false
}

const showForm = computed(() => poll.value && (editing.value || !voted.value))
const showResults = computed(() => poll.value?.results && voted.value && !editing.value)
const sizeTotal = computed(() => {
  const s = poll.value?.results?.pool_size || {}
  return Object.values(s).reduce((a, b) => a + b, 0) || 1
})
const maxPoints = computed(() => Math.max(1, ...(poll.value?.results?.maps || []).map(m => m.points)))

useSeoMeta({ title: 'Duel League Vote · DeepFrag' })
</script>

<template>
  <div class="vote-page">
    <div class="head">
      <div class="kicker">COMMUNITY VOTE</div>
      <h1>KOTH Duel League</h1>
      <p class="sub">The 1v1 league is coming. Before signups open, the community picks the format:
        how big the bo5 map pool should be, and which maps belong in it.
        Vote as your in-game handle — no login, one ballot per player, change it any time.
        Results show after you vote.</p>
    </div>

    <div v-if="loading" class="card quiet">Loading…</div>
    <div v-else-if="err && !poll" class="card quiet">{{ err }}</div>

    <template v-else>
      <div v-if="showForm" class="ballot">
        <div class="card">
          <h2><span class="qnum">0</span> Who's voting?</h2>
          <p class="hint">Type your in-game name — it has to be a player DeepFrag knows (no randoms).</p>
          <div class="who">
            <input v-model="handleQuery" class="who-input" placeholder="your in-game handle…"
                   @focus="showDrop = true" @input="showDrop = true; picked = null">
            <div v-if="showDrop && matches.length && !picked" class="drop">
              <button v-for="p in matches" :key="p.canonical_id" class="drop-item" @click="pick(p)">
                {{ p.display }}
              </button>
            </div>
            <span v-if="picked" class="who-ok">✓ voting as {{ picked.display }}</span>
          </div>
        </div>

        <div class="card">
          <h2><span class="qnum">1</span> Total map pool for the best-of-5 format</h2>
          <div class="sizes">
            <button v-for="s in poll.question_1.options" :key="s"
                    class="size" :class="{ on: poolSize === s }" @click="poolSize = s">
              <span class="n">{{ s }}</span><span class="lbl">maps</span>
            </button>
          </div>
        </div>

        <div class="card">
          <h2><span class="qnum">2</span> Click the maps you want, in ranking order</h2>
          <p class="hint">First click = your #1 pick. Click again to remove. Rank up to {{ maxRanked }}.</p>
          <div class="mapgrid">
            <button v-for="m in poll.question_2.candidates" :key="m"
                    class="maptile" :class="{ on: rankOf(m) }" @click="toggleMap(m)">
              <span v-if="rankOf(m)" class="rank">{{ rankOf(m) }}</span>
              {{ m }}
            </button>
          </div>
          <div v-if="ranking.length" class="myorder">
            Your order: <span v-for="(m, i) in ranking" :key="m" class="chip">{{ i + 1 }}. {{ m }}</span>
            <button class="clear" @click="ranking = []">clear</button>
          </div>
        </div>

        <div class="submitrow">
          <span v-if="err" class="err">{{ err }}</span>
          <button class="btn primary big" :disabled="!picked || !poolSize || !ranking.length || submitting" @click="submit">
            {{ submitting ? 'Submitting…' : (voted ? 'Update my vote' : 'Submit my vote') }}
          </button>
        </div>
      </div>

      <div v-if="showResults" class="results">
        <div class="card">
          <div class="res-head">
            <h2>Results so far</h2>
            <span class="count">{{ poll.results.votes }} ballot{{ poll.results.votes === 1 ? '' : 's' }}</span>
            <button class="btn ghost" @click="editing = true">Change my vote</button>
          </div>

          <h3>Map pool size</h3>
          <div v-for="s in poll.question_1.options" :key="s" class="bar-row">
            <span class="bar-label">{{ s }} maps</span>
            <div class="bar"><i :style="{ width: (100 * (poll.results.pool_size[String(s)] || 0) / sizeTotal) + '%' }" /></div>
            <span class="bar-val">{{ poll.results.pool_size[String(s)] || 0 }}</span>
          </div>

          <h3>Map ranking <span class="hint">(points: #1 pick = {{ maxRanked }}, each rank below one less)</span></h3>
          <div v-for="(m, i) in poll.results.maps.filter(x => x.picks > 0)" :key="m.map" class="bar-row">
            <span class="bar-label">{{ i + 1 }}. {{ m.map }}</span>
            <div class="bar"><i :style="{ width: (100 * m.points / maxPoints) + '%' }" /></div>
            <span class="bar-val">{{ m.points }} pts · {{ m.first }}× first</span>
          </div>

          <p class="hint" style="margin-top:14px">
            Your ballot ({{ poll.my_vote.handle }}): {{ poll.my_vote.pool_size }} maps ·
            {{ (poll.my_vote.map_ranking || []).join(' → ') }}
          </p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.vote-page { max-width: 860px; margin: 0 auto; padding: 40px 20px 90px; }
.head .kicker { font-size: 11px; font-weight: 700; letter-spacing: 0.22em; color: var(--accent); }
.head h1 { font-size: 34px; margin: 6px 0 10px; }
.head .sub { color: var(--fg-2); max-width: 62ch; line-height: 1.6; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 22px 24px; margin-top: 18px; }
.card.quiet { color: var(--fg-3); }
.hint { color: var(--fg-3); font-size: 13px; }
h2 { font-size: 17px; margin: 0 0 12px; display: flex; align-items: center; gap: 10px; }
h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--fg-2); margin: 20px 0 10px; }
.qnum { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
        border-radius: 50%; background: var(--accent); color: #06251f; font-size: 13px; font-weight: 800; }
.who { position: relative; max-width: 380px; }
.who-input { width: 100%; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
             color: var(--fg); padding: 11px 14px; font-size: 15px; }
.who-input:focus { outline: none; border-color: var(--accent); }
.drop { position: absolute; top: 100%; left: 0; right: 0; z-index: 20; margin-top: 4px;
        background: var(--panel-2); border: 1px solid var(--border-2); border-radius: 8px; overflow: hidden; }
.drop-item { display: block; width: 100%; text-align: left; background: none; border: none;
             color: var(--fg-2); padding: 9px 14px; cursor: pointer; font-size: 14px; }
.drop-item:hover { background: var(--panel-3); color: var(--fg); }
.who-ok { display: inline-block; margin-top: 8px; color: var(--accent); font-size: 13px; font-weight: 600; }
.sizes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.size { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 16px 8px;
        cursor: pointer; color: var(--fg-2); transition: all .12s; }
.size .n { display: block; font-size: 28px; font-weight: 800; color: var(--fg); }
.size .lbl { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }
.size.on { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent), 0 0 18px var(--accent-glow); }
.mapgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; }
.maptile { position: relative; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
           padding: 12px 8px; cursor: pointer; color: var(--fg-2); font-size: 14px; font-weight: 600; transition: all .12s; }
.maptile.on { border-color: var(--accent); color: var(--fg); box-shadow: 0 0 0 1px var(--accent); }
.maptile .rank { position: absolute; top: -8px; right: -8px; width: 22px; height: 22px; border-radius: 50%;
                 background: var(--accent); color: #06251f; font-size: 12px; font-weight: 800;
                 display: flex; align-items: center; justify-content: center; }
.myorder { margin-top: 14px; color: var(--fg-3); font-size: 13px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.chip { background: var(--panel-3); border: 1px solid var(--border); border-radius: 999px; padding: 2px 10px; color: var(--fg-2); }
.clear { background: none; border: none; color: var(--loss); cursor: pointer; font-size: 12px; }
.submitrow { display: flex; justify-content: flex-end; align-items: center; gap: 14px; margin-top: 18px; }
.err { color: var(--loss); font-size: 13px; }
.btn { border-radius: 8px; padding: 10px 18px; cursor: pointer; font-weight: 700; border: 1px solid var(--border);
       background: var(--panel-2); color: var(--fg); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #06251f; }
.btn.primary:disabled { opacity: 0.45; cursor: default; }
.btn.big { padding: 12px 26px; font-size: 15px; }
.btn.ghost { margin-left: auto; }
.res-head { display: flex; align-items: center; gap: 14px; }
.res-head .count { color: var(--fg-3); font-size: 13px; }
.bar-row { display: grid; grid-template-columns: 110px 1fr auto; gap: 12px; align-items: center; margin: 7px 0; }
.bar-label { font-size: 13.5px; color: var(--fg-2); font-weight: 600; }
.bar { height: 10px; background: var(--panel-3); border-radius: 5px; overflow: hidden; }
.bar i { display: block; height: 100%; background: linear-gradient(90deg, var(--accent-2), var(--accent)); }
.bar-val { font-size: 12.5px; color: var(--fg-3); white-space: nowrap; }
@media (max-width: 560px) {
  .sizes { grid-template-columns: repeat(2, 1fr); }
  .bar-row { grid-template-columns: 90px 1fr auto; }
}
</style>

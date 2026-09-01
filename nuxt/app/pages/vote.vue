<script setup>
// Community vote: the upcoming KOTH duel (1v1) league — pool size + ranked
// map picks. Discord auth required to vote (NOT ladder membership); results
// reveal after you submit. One ballot per account, editable any time.
const { loggedIn, ready, login, authHeader, fetchMe } = useAuth()

const poll = ref(null)
const loading = ref(true)
const err = ref(null)
const submitting = ref(false)
const editing = ref(false)

const poolSize = ref(null)
const ranking = ref([])

const showForm = computed(() => poll.value && loggedIn.value && (editing.value || !poll.value.my_vote))
const showResults = computed(() => poll.value?.results && !editing.value && poll.value?.my_vote)
const maxRanked = computed(() => poll.value?.question_2?.max_ranked || 11)

async function load() {
  loading.value = true
  try {
    poll.value = await $fetch('/api/vote/duel-league', { headers: authHeader() })
    if (poll.value.my_vote) {
      poolSize.value = poll.value.my_vote.pool_size
      ranking.value = [...(poll.value.my_vote.map_ranking || [])]
    }
  } catch (e) { err.value = 'Could not load the poll — try a refresh.' }
  loading.value = false
}
onMounted(async () => { await fetchMe(); load() })

function toggleMap(m) {
  const i = ranking.value.indexOf(m)
  if (i >= 0) ranking.value.splice(i, 1)
  else if (ranking.value.length < maxRanked.value) ranking.value.push(m)
}
function rankOf(m) { const i = ranking.value.indexOf(m); return i >= 0 ? i + 1 : null }

async function submit() {
  if (!poolSize.value || !ranking.value.length) return
  submitting.value = true
  err.value = null
  try {
    const r = await $fetch('/api/vote/duel-league', {
      method: 'POST',
      headers: authHeader(),
      body: { pool_size: poolSize.value, map_ranking: ranking.value },
    })
    poll.value = { ...poll.value, my_vote: r.my_vote, results: r.results }
    editing.value = false
  } catch (e) {
    err.value = e?.data?.detail || 'Vote failed — try again.'
  }
  submitting.value = false
}

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
        how big the bo3 map pool should be, and which maps belong in it.
        One ballot per Discord account — you can change yours any time.
        Results unlock after you vote.</p>
    </div>

    <div v-if="loading || !ready" class="card quiet">Loading…</div>
    <div v-else-if="err && !poll" class="card quiet">{{ err }}</div>

    <!-- Sign-in gate: Discord auth only, no ladder signup needed -->
    <div v-else-if="!loggedIn" class="card gate">
      <p><strong>Sign in with Discord to vote.</strong></p>
      <p class="hint">Any Discord account works — you do not need to be on the 2v2 ladder.</p>
      <button class="btn primary" @click="login">Sign in with Discord</button>
    </div>

    <template v-else>
      <!-- Ballot -->
      <div v-if="showForm" class="ballot">
        <div class="card">
          <h2><span class="qnum">1</span> Total map pool for the best-of-3 format</h2>
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
          <button class="btn primary big" :disabled="!poolSize || !ranking.length || submitting" @click="submit">
            {{ submitting ? 'Submitting…' : (poll.my_vote ? 'Update my vote' : 'Submit my vote') }}
          </button>
        </div>
      </div>

      <!-- Results (after voting) -->
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
            Your ballot: {{ poll.my_vote.pool_size }} maps ·
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
.card.gate { text-align: center; padding: 40px 24px; }
.card.gate .hint { margin: 8px 0 18px; }
.hint { color: var(--fg-3); font-size: 13px; }
h2 { font-size: 17px; margin: 0 0 14px; display: flex; align-items: center; gap: 10px; }
h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--fg-2); margin: 20px 0 10px; }
.qnum { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
        border-radius: 50%; background: var(--accent); color: #06251f; font-size: 13px; font-weight: 800; }
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

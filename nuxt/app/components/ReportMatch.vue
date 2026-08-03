<script setup>
// "Report match" — player self-service for a played bo3 that didn't record.
// Two ways in, ONE validation path: paste hub game IDs, or find-by-time (which
// just fills the IDs after the player confirms). The backend re-derives the
// winner from frags and enforces the same roster gates as auto-resolve, so a
// report can never move rungs on someone's say-so.
const props = defineProps({
  challenge: { type: Object, required: true },
  userTeamId: { type: Number, default: null }
})
const emit = defineEmits(['done', 'close'])
const { user, authHeader } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const c = props.challenge

const mode = ref('ids')            // 'ids' | 'time'
const id1 = ref(''); const id2 = ref(''); const id3 = ref('')
const startLocal = ref('')         // datetime-local string
const searching = ref(false)
const found = ref(null)            // search results
const picked = ref(new Set())      // hub_game_ids selected from search
const saving = ref(false)
const err = ref('')
const outcome = ref(null)          // { outcome, ...payload } after submit

function togglePick(id) { picked.value.has(id) ? picked.value.delete(id) : picked.value.add(id); picked.value = new Set(picked.value) }

async function doSearch() {
  err.value = ''; found.value = null
  if (!startLocal.value) { err.value = 'Pick a rough start time first'; return }
  searching.value = true
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/report-search`, {
      method: 'POST', headers: authHeader(),
      body: { start_time: new Date(startLocal.value).toISOString() }
    })
    found.value = r
    picked.value = new Set((r.candidates || []).filter(g => g.suggested).map(g => g.hub_game_id))
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Search failed' }
  finally { searching.value = false }
}

const idsToSubmit = computed(() => {
  if (mode.value === 'time') return [...picked.value]
  return [id1.value, id2.value, id3.value].map(s => String(s).trim()).filter(Boolean)
})

async function submit() {
  err.value = ''
  const ids = idsToSubmit.value
  if (ids.length < 2) { err.value = 'Two game IDs minimum (three for a full series)'; return }
  if (ids.length > 3) { err.value = 'At most three games count in a bo3'; return }
  saving.value = true
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/report`, {
      method: 'POST', headers: authHeader(), body: { game_ids: ids }
    })
    outcome.value = r
    if (r.outcome === 'recorded') emit('done')   // board refresh; modal shows the summary
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not submit report' }
  finally { saving.value = false }
}

function fmt(iso) {
  try { return new Date(iso).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso }
}
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div class="m-head">
        <h3>Report match · {{ c.challenger }} vs {{ c.challenged }}</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>

      <!-- outcome states -->
      <template v-if="outcome">
        <p v-if="outcome.outcome === 'recorded'" class="ok">
          ✅ Recorded — <strong>{{ outcome.winner_id === c.challenger_id ? c.challenger : c.challenged }}</strong>
          won {{ outcome.score }}. Standings updated and the result was posted to Discord.
        </p>
        <p v-else-if="outcome.outcome === 'pending'" class="warn">
          ⏳ Those games aren't in DeepFrag yet (matches sync from the hub every ~2 hours).
          Your report is queued and will record automatically once they arrive — nothing else to do.
        </p>
        <p v-else-if="outcome.outcome === 'flagged'" class="warn">
          🚩 Series found, but not every rostered player matched in
          {{ (outcome.bad || []).join(', ') }} — usually an in-game name that isn't linked to a profile.
          Admins were pinged with your game IDs and will sort it out.
        </p>
        <div class="m-actions"><button class="btn" @click="emit('close')">Close</button></div>
      </template>

      <template v-else>
        <p class="lede">
          Played this match but it never recorded? Point DeepFrag at the games. The winner is
          computed from the actual frags — reports can't decide results, only locate games.
        </p>

        <div class="tabs">
          <button class="tab-btn" :class="{ on: mode === 'ids' }" @click="mode = 'ids'">I have game IDs</button>
          <button class="tab-btn" :class="{ on: mode === 'time' }" @click="mode = 'time'">Find by time</button>
        </div>

        <template v-if="mode === 'ids'">
          <p class="hint">The <code>gameId</code> number from each game's URL on hub.quakeworld.nu.</p>
          <div class="idrow">
            <input v-model="id1" inputmode="numeric" placeholder="Game 1 ID (required)">
            <input v-model="id2" inputmode="numeric" placeholder="Game 2 ID (required)">
            <input v-model="id3" inputmode="numeric" placeholder="Game 3 ID (if it went 3)">
          </div>
        </template>

        <template v-else>
          <p class="hint">Roughly when did the match start? We'll search the two hours before and eight after.</p>
          <div class="timerow">
            <input v-model="startLocal" type="datetime-local">
            <button class="btn ghost" :disabled="searching" @click="doSearch">{{ searching ? 'Searching…' : 'Search' }}</button>
          </div>
          <template v-if="found">
            <p v-if="!(found.candidates || []).length" class="warn">No games between these rosters in that window — try the game-ID tab, or a different time.</p>
            <div v-else class="cands">
              <label v-for="g in found.candidates" :key="g.hub_game_id" class="cand" :class="{ off: !picked.has(g.hub_game_id) }">
                <input type="checkbox" :checked="picked.has(g.hub_game_id)" @change="togglePick(g.hub_game_id)">
                <span class="cmap">{{ g.map }}</span>
                <span class="cscore">{{ g.a_frags }}–{{ g.b_frags }}</span>
                <span class="ctime">{{ fmt(g.played_at) }}</span>
                <span v-if="!g.full" class="cflag" title="Not all rostered players matched in this game">⚠</span>
              </label>
            </div>
          </template>
        </template>

        <p v-if="err" class="err">{{ err }}</p>
        <div class="m-actions">
          <button class="btn ghost" @click="emit('close')">Cancel</button>
          <button class="btn" :disabled="saving || idsToSubmit.length < 2" @click="submit">
            {{ saving ? 'Submitting…' : `Report ${idsToSubmit.length || ''} game${idsToSubmit.length === 1 ? '' : 's'}` }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px 24px; width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; }
.m-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 4px; }
.m-head h3 { margin: 0; font-size: 16px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 15px; cursor: pointer; padding: 4px; }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 14px; }
.tabs { display: flex; gap: 6px; margin-bottom: 12px; }
.tab-btn { background: transparent; color: var(--fg-2); border: 1px solid var(--border); border-radius: 8px; padding: 7px 12px; font-size: 13px; cursor: pointer; font-family: inherit; }
.tab-btn.on { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 700; }
.hint { color: var(--fg-3); font-size: 12px; margin: 0 0 8px; }
.hint code { font-family: 'JetBrains Mono', monospace; }
.idrow { display: flex; flex-direction: column; gap: 8px; }
.idrow input, .timerow input { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--fg-1); padding: 10px 12px; font-size: 14px; font-family: 'JetBrains Mono', monospace; width: 100%; }
.timerow { display: flex; gap: 8px; align-items: center; }
.timerow input { flex: 1; }
.cands { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.cand { display: flex; align-items: center; gap: 10px; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; cursor: pointer; font-size: 13px; }
.cand.off { opacity: 0.55; }
.cmap { font-weight: 700; min-width: 76px; }
.cscore { font-family: 'JetBrains Mono', monospace; }
.ctime { color: var(--fg-3); margin-left: auto; font-size: 12px; }
.cflag { color: var(--draw); }
.ok { color: var(--win); font-size: 14px; margin: 10px 0; }
.warn { color: var(--draw); font-size: 13px; margin: 10px 0; }
.err { color: var(--loss); font-size: 13px; margin: 8px 0 4px; }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
@media (max-width: 560px) {
  .modal { padding: 16px 14px; }
  .timerow { flex-direction: column; align-items: stretch; }
  .ctime { flex-basis: 100%; margin-left: 24px; }
  .cand { flex-wrap: wrap; }
}
</style>

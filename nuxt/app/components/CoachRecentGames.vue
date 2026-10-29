<script setup>
// Last 10 games, the right-hand column of the coach overview (2026-10-28, Peter: the L1-L5
// overview is front and center; the games sit beside it, minimal). Each fours game has a
// "Game Report" button that builds the report in place (~30 s, the demo is read once); when it
// exists the button becomes a small arrow link to it. "All games" opens the wide table
// (/coach/player/{id}/games). Data: /api/players/{id}/recent-games.
// `mode` from the coach page drives the list; without it the list shows its own 4on4/1on1 switch.
const props = defineProps({ cid: { type: String, required: true }, mode: { type: String, default: '' } })
const route = useRoute()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const ownMode = ref(route.query.mode === '1on1' ? '1on1' : '4on4')
const mode = computed(() => props.mode || ownMode.value)
const games = ref([])
const loading = ref(false)
const err = ref('')
const { state, build, reportPath } = useReportBuild(toRef(props, 'cid'))

async function load() {
  loading.value = true; err.value = ''
  try {
    const r = await fetch(`${base}/api/players/${encodeURIComponent(props.cid)}/recent-games?mode=${mode.value}&limit=10`)
    if (!r.ok) throw new Error(`recent games ${r.status}`)
    games.value = (await r.json()).games || []
  } catch (e) { err.value = String(e?.message || e) } finally { loading.value = false }
}
onMounted(load)
watch(mode, load)
watch(() => props.cid, load)
function fmtDate(d) { return d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '' }
function res(g) { return g.win === null || g.win === undefined ? '–' : g.win ? 'W' : 'L' }
const allHref = computed(() => ({ path: `/coach/player/${encodeURIComponent(props.cid)}/games`, query: mode.value === '1on1' ? { mode: '1on1' } : {} }))
</script>

<template>
  <section class="rg">
    <div class="head">
      <div class="title">🎮 Last 10 games</div>
      <div v-if="!props.mode" class="seg" role="tablist" aria-label="Game mode">
        <button class="sbtn" :class="{ on: mode === '4on4' }" role="tab" :aria-selected="mode === '4on4'" @click="ownMode = '4on4'">4on4</button>
        <button class="sbtn" :class="{ on: mode === '1on1' }" role="tab" :aria-selected="mode === '1on1'" @click="ownMode = '1on1'">1on1</button>
      </div>
    </div>
    <div v-if="loading" class="note">Loading…</div>
    <div v-else-if="err" class="note err">{{ err }}</div>
    <div v-else-if="!games.length" class="note">No {{ mode }} games on record yet.</div>
    <ul v-else class="list">
      <li v-for="g in games" :key="g.hub_game_id" class="row" :class="{ w: g.win === true, l: g.win === false }">
        <div class="main">
          <span class="map">{{ g.map }}</span>
          <span class="res" :class="{ w: g.win === true, l: g.win === false }">{{ res(g) }}</span>
          <span v-if="g.my_score != null && g.opp_score != null" class="score">{{ g.my_score }}–{{ g.opp_score }}</span>
          <span class="muted">{{ fmtDate(g.date) }}</span>
        </div>
        <div class="act">
          <template v-if="g.report_available">
            <NuxtLink v-if="g.has_report" :to="reportPath(g.hub_game_id)" class="go" title="Open the Game Report" aria-label="Open the Game Report">↗</NuxtLink>
            <span v-else-if="state[g.hub_game_id]?.busy" class="busy">building…</span>
            <button v-else class="rep" :title="state[g.hub_game_id]?.err || 'Build this game\'s report (about 30 s)'" @click="build(g)">{{ state[g.hub_game_id]?.err ? 'Retry' : 'Game Report' }}</button>
          </template>
          <a :href="`https://hub.quakeworld.nu/games/?gameId=${g.hub_game_id}`" target="_blank" rel="noopener" class="hub" title="Watch on the hub">hub</a>
        </div>
        <div v-if="state[g.hub_game_id]?.err" class="rowerr">{{ state[g.hub_game_id].err }}</div>
      </li>
    </ul>
    <NuxtLink :to="allHref" class="all">All games, with details →</NuxtLink>
    <div class="note">A Game Report is one game's key moments, with links into the hub at those seconds and two or three rewinds. Building one reads the demo, about half a minute.</div>
  </section>
</template>

<style scoped>
.rg { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.title { font-weight: 800; font-size: 14px; letter-spacing: 0.02em; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; }
.sbtn { background: transparent; color: var(--fg-2); border: 0; padding: 8px 14px; font-weight: 700; font-size: 13px; cursor: pointer; min-height: 36px; }
.sbtn.on { background: var(--accent); color: #140b03; }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; background: var(--panel); border: 1px solid var(--border); border-left: 3px solid var(--border); border-radius: 9px; padding: 6px 10px; min-width: 0; }
.row.w { border-left-color: #34d67a; } .row.l { border-left-color: #ff5d6c; }
.main { flex: 1 1 auto; min-width: 0; display: flex; gap: 7px; align-items: baseline; flex-wrap: wrap; font-size: 13px; }
.map { font-weight: 800; }
.res { font-weight: 900; font-size: 12px; } .res.w { color: #34d67a; } .res.l { color: #ff5d6c; }
.score { font-variant-numeric: tabular-nums; font-weight: 700; }
.muted { color: var(--fg-2); font-size: 12px; }
.act { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.rep { font-weight: 800; font-size: 12px; color: var(--accent); background: transparent; border: 1px solid var(--accent); border-radius: 999px; padding: 4px 10px; min-height: 30px; cursor: pointer; white-space: nowrap; }
.rep:hover { background: var(--accent); color: #140b03; }
.busy { font-size: 12px; color: var(--fg-2); font-style: italic; white-space: nowrap; min-height: 30px; display: inline-flex; align-items: center; }
.go { font-weight: 900; font-size: 15px; color: #140b03; background: var(--accent); border-radius: 999px; width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; }
.go:hover { filter: brightness(1.1); }
.hub { font-size: 12px; color: var(--fg-2); text-decoration: none; padding: 4px 2px; min-height: 30px; display: inline-flex; align-items: center; }
.hub:hover { color: var(--accent); }
.rowerr { flex-basis: 100%; font-size: 11.5px; color: #fca5a5; }
.all { font-weight: 800; font-size: 13px; color: var(--accent); text-decoration: none; padding: 6px 0; }
.all:hover { text-decoration: underline; }
.note { color: var(--fg-2); font-size: 12px; line-height: 1.5; }
.note.err { color: #fca5a5; }
</style>

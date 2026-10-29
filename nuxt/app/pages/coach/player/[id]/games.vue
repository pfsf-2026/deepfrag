<script setup>
// /coach/player/{id}/games — every game in one wide table (2026-10-28, Peter: "a way to get to the
// previous games list that is a single wide view with more details and summaries"). Per row: date,
// map, result and score, frags/deaths, teammates and opponents, the fours coach's per-game read
// (above average + the stats that explain it, for the games the level uses) and, once the Game
// Report exists, its summary (impact rank of the eight, adjusted kills, damage per minute, quads,
// reds, MM2). The report column builds a report in place, like the coach overview.
// SPA-only: served by the /coach/player/_fallback/ shell via _redirects.
const route = useRoute()
const router = useRouter()
const id = computed(() => String(route.params.id || ''))
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const mode = computed(() => route.query.mode === '1on1' ? '1on1' : '4on4')
function setMode(m) { router.replace({ query: m === '1on1' ? { mode: '1on1' } : {} }) }
const { report: coach } = useFoursCoach(id)
const display = computed(() => coach.value?.display || id.value)
const { state, build, reportPath } = useReportBuild(id)
useHead({ title: () => `${display.value} · games · DeepFrag` })

const PAGE = 25
const games = ref([])
const loading = ref(false)
const err = ref('')
const more = ref(true)

async function load(reset = true) {
  if (reset) { games.value = []; more.value = true }
  loading.value = true; err.value = ''
  try {
    const r = await fetch(`${base}/api/players/${encodeURIComponent(id.value)}/recent-games?mode=${mode.value}&limit=${PAGE}&offset=${games.value.length}`)
    if (!r.ok) throw new Error(`games ${r.status}`)
    const got = (await r.json()).games || []
    games.value = [...games.value, ...got]
    more.value = got.length === PAGE
  } catch (e) { err.value = String(e?.message || e) } finally { loading.value = false }
}
onMounted(() => load())
watch([mode, id], () => load())

// the fours coach's per-game read, for the games its level window covers
const coachGame = computed(() => Object.fromEntries((coach.value?.games || []).map(g => [String(g.hub_game_id), g])))
function fmtDate(d) { return d ? new Date(d).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '' }
function res(g) { return g.win === null || g.win === undefined ? '–' : g.win ? 'W' : 'L' }
function ordn(k) { return `${k}${10 <= k % 100 && k % 100 <= 20 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' })[k % 10] || 'th'}` }
const isFours = computed(() => mode.value === '4on4')
</script>

<template>
  <div class="page">
    <div class="head">
      <div class="crumbs">
        <NuxtLink :to="`/coach/player/${encodeURIComponent(id)}`" class="back">← {{ display }}'s coach</NuxtLink>
        <span class="sep">·</span>
        <NuxtLink :to="`/p/${encodeURIComponent(id)}`" class="back">profile</NuxtLink>
      </div>
      <div class="who">
        <h1>{{ display }} · games</h1>
        <div class="seg" role="tablist" aria-label="Game mode">
          <button class="sbtn" :class="{ on: mode === '4on4' }" role="tab" :aria-selected="mode === '4on4'" @click="setMode('4on4')">4on4</button>
          <button class="sbtn" :class="{ on: mode === '1on1' }" role="tab" :aria-selected="mode === '1on1'" @click="setMode('1on1')">1on1</button>
        </div>
      </div>
      <p v-if="isFours" class="muted intro">
        <b>Coach's read</b> is how far above an average player you were that game and the stats that explain it (only the games your level counts).
        <b>Report</b> appears once the game's report is built: your impact rank of the eight, then the same numbers as the report's table.
        <NuxtLink to="/glossary" class="gl">Every stat explained →</NuxtLink>
      </p>
    </div>

    <div v-if="err && !games.length" class="box err">{{ err }} <button class="lnk" @click="load()">try again</button></div>
    <div v-else-if="!loading && !games.length" class="box">No {{ mode }} games on record yet.</div>

    <div v-if="games.length" class="tblwrap">
      <table class="gt">
        <thead>
          <tr>
            <th>Date</th><th>Map</th><th>Result</th><th>Frags / deaths</th>
            <th v-if="isFours">With</th><th>vs</th>
            <th v-if="isFours">Coach's read</th>
            <th v-if="isFours">Report</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template v-for="g in games" :key="g.hub_game_id">
            <tr :class="{ w: g.win === true, l: g.win === false }">
              <td class="nowrap">{{ fmtDate(g.date) }}</td>
              <td class="map">{{ g.map }}<span v-if="g.has_bots" class="tag">bots</span></td>
              <td class="nowrap"><span class="res" :class="{ w: g.win === true, l: g.win === false }">{{ res(g) }}</span>
                <span v-if="g.my_score != null && g.opp_score != null" class="score">{{ g.my_score }}–{{ g.opp_score }}</span></td>
              <td class="num">{{ g.frags }} / {{ g.deaths }}</td>
              <td v-if="isFours" class="names">{{ g.teammates }}</td>
              <td class="names">{{ g.opponents }}</td>
              <td v-if="isFours" class="read">
                <template v-if="coachGame[g.hub_game_id]">
                  <b>{{ signed(coachGame[g.hub_game_id].above_avg) }}</b> above average
                  <div class="ex"><span v-for="e in coachGame[g.hub_game_id].explain" :key="e.key" :class="{ good: e.good, bad: !e.good }">{{ e.good ? '▲' : '▼' }} {{ e.label }} {{ e.value }}</span></div>
                </template>
                <span v-else class="muted">–</span>
              </td>
              <td v-if="isFours" class="rep">
                <template v-if="g.report_summary">
                  <b>{{ ordn(g.report_summary.rank) }} of {{ g.report_summary.of }}</b> · impact {{ g.report_summary.impact?.toFixed(2) }}
                  <div class="muted small">adj K {{ g.report_summary.adj }} · dmg/min {{ g.report_summary.dmg_pm }} · sDDR {{ g.report_summary.sddr }} · quads {{ g.report_summary.quads }}<template v-if="g.map !== 'e1m2'"> · RA {{ g.report_summary.ra }}</template> · MM2 {{ g.report_summary.mm2 }}</div>
                </template>
                <span v-else-if="g.has_report" class="muted">built</span>
                <span v-else class="muted">–</span>
              </td>
              <td class="act">
                <template v-if="g.report_available">
                  <NuxtLink v-if="g.has_report" :to="reportPath(g.hub_game_id)" class="go" title="Open the Game Report" aria-label="Open the Game Report">↗</NuxtLink>
                  <span v-else-if="state[g.hub_game_id]?.busy" class="busy">building…</span>
                  <button v-else class="btnrep" :title="state[g.hub_game_id]?.err || 'Build this game\'s report (about 30 s)'" @click="build(g)">{{ state[g.hub_game_id]?.err ? 'Retry' : 'Game Report' }}</button>
                </template>
                <a :href="`https://hub.quakeworld.nu/games/?gameId=${g.hub_game_id}`" target="_blank" rel="noopener" class="hub">hub</a>
              </td>
            </tr>
            <tr v-if="state[g.hub_game_id]?.err" class="errrow"><td :colspan="isFours ? 9 : 6">{{ state[g.hub_game_id].err }}</td></tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="foot">
      <span v-if="loading" class="muted">Loading…</span>
      <span v-else-if="err" class="err">{{ err }}</span>
      <button v-else-if="more && games.length" class="lnk" @click="load(false)">Show {{ PAGE }} more</button>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 18px 16px 90px; }
.head { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.crumbs { display: flex; gap: 8px; align-items: baseline; font-size: 13px; flex-wrap: wrap; }
.back { color: var(--fg-2); text-decoration: none; font-weight: 600; }
.back:hover { color: var(--accent); }
.sep { color: var(--fg-3); }
.who { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
h1 { font-size: clamp(22px, 4.5vw, 30px); font-weight: 900; margin: 0; letter-spacing: -0.01em; line-height: 1.1; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; }
.sbtn { background: transparent; color: var(--fg-2); border: 0; padding: 8px 14px; font-weight: 700; font-size: 13px; cursor: pointer; min-height: 36px; }
.sbtn.on { background: var(--accent); color: #140b03; }
.intro { font-size: 12.5px; line-height: 1.5; max-width: 900px; margin: 0; }
.gl { color: var(--accent); text-decoration: none; font-weight: 700; }
.muted { color: var(--fg-2); }
.small { font-size: 11.5px; }
.box { padding: 18px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); font-size: 14px; }
.err, .box.err { color: #fca5a5; }
.tblwrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--panel); }
.gt { width: 100%; border-collapse: collapse; font-size: 13px; }
.gt th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--fg-3); font-weight: 700; padding: 10px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.gt td { padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.gt tbody tr:last-child td { border-bottom: 0; }
.gt tr.w td:first-child { box-shadow: inset 3px 0 0 #34d67a; }
.gt tr.l td:first-child { box-shadow: inset 3px 0 0 #ff5d6c; }
.nowrap { white-space: nowrap; }
.map { font-weight: 800; white-space: nowrap; }
.tag { font-size: 10.5px; border: 1px solid var(--border); border-radius: 999px; padding: 0 6px; color: var(--fg-2); margin-left: 6px; font-weight: 600; }
.res { font-weight: 900; font-size: 12px; margin-right: 6px; } .res.w { color: #34d67a; } .res.l { color: #ff5d6c; }
.score, .num { font-variant-numeric: tabular-nums; font-weight: 700; white-space: nowrap; }
.names { color: var(--fg-2); font-size: 12px; min-width: 140px; max-width: 220px; overflow-wrap: anywhere; }
.read { min-width: 200px; font-size: 12.5px; }
.ex { display: flex; flex-wrap: wrap; gap: 3px 8px; margin-top: 3px; font-size: 11.5px; }
.ex .good { color: #34d67a; } .ex .bad { color: #ff8a95; }
.rep { min-width: 210px; font-size: 12.5px; }
.act { white-space: nowrap; text-align: right; }
.act > * { vertical-align: middle; }
.btnrep { font-weight: 800; font-size: 12px; color: var(--accent); background: transparent; border: 1px solid var(--accent); border-radius: 999px; padding: 4px 10px; min-height: 30px; cursor: pointer; }
.btnrep:hover { background: var(--accent); color: #140b03; }
.busy { font-size: 12px; color: var(--fg-2); font-style: italic; }
.go { font-weight: 900; font-size: 15px; color: #140b03; background: var(--accent); border-radius: 999px; width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; }
.hub { font-size: 12px; color: var(--fg-2); text-decoration: none; margin-left: 8px; }
.hub:hover { color: var(--accent); }
.errrow td { color: #fca5a5; font-size: 12px; padding-top: 0; }
.foot { padding: 14px 0; }
.lnk { background: none; border: 1px solid var(--border); color: var(--fg); border-radius: 8px; padding: 8px 14px; font-weight: 700; cursor: pointer; min-height: 36px; }
.lnk:hover { border-color: var(--accent); color: var(--accent); }
@media (min-width: 720px) { .page { padding: 24px 32px 100px; } }
</style>

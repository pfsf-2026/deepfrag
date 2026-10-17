<script setup>
// Last 10 games on the coach page (2026-10-17, Peter): a 4on4 / 1on1 switch and, on the
// right of every fours game, a "Game Report" link — the game's key moments, hub deep links
// and 2-3 rewinds (/coach/player/{id}/game/{hub_game_id}). Data: /api/players/{id}/recent-games.
const props = defineProps({ cid: { type: String, required: true } })
const route = useRoute()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const mode = ref(route.query.mode === '1on1' ? '1on1' : '4on4')
const games = ref([])
const loading = ref(false)
const err = ref('')

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
</script>

<template>
  <section class="rg">
    <div class="head">
      <div class="title">🎮 Last 10 games</div>
      <div class="seg" role="tablist" aria-label="Game mode">
        <button class="sbtn" :class="{ on: mode === '4on4' }" role="tab" :aria-selected="mode === '4on4'" @click="mode = '4on4'">4on4</button>
        <button class="sbtn" :class="{ on: mode === '1on1' }" role="tab" :aria-selected="mode === '1on1'" @click="mode = '1on1'">1on1</button>
      </div>
    </div>
    <div v-if="loading" class="note">Loading…</div>
    <div v-else-if="err" class="note err">{{ err }}</div>
    <div v-else-if="!games.length" class="note">No {{ mode }} games on record yet.</div>
    <ul v-else class="list">
      <li v-for="g in games" :key="g.hub_game_id" class="row" :class="{ w: g.win === true, l: g.win === false }">
        <div class="main">
          <div class="l1">
            <span class="map">{{ g.map }}</span>
            <span class="res" :class="{ w: g.win === true, l: g.win === false }">{{ res(g) }}</span>
            <span v-if="g.my_score != null && g.opp_score != null" class="score">{{ g.my_score }}–{{ g.opp_score }}</span>
            <span class="muted">{{ fmtDate(g.date) }}</span>
            <span v-if="g.has_bots" class="tag">bots</span>
          </div>
          <div class="l2 muted">
            <span>{{ g.frags }} frags / {{ g.deaths }} deaths</span>
            <span v-if="g.opponents" class="opp"> · vs {{ g.opponents }}</span>
          </div>
        </div>
        <div class="act">
          <NuxtLink v-if="g.report_available" :to="`/coach/player/${encodeURIComponent(props.cid)}/game/${g.hub_game_id}`" class="rep" :class="{ ready: g.has_report }">Game Report →</NuxtLink>
          <span v-else class="muted soon">report · fours first</span>
          <a :href="`https://hub.quakeworld.nu/games/?gameId=${g.hub_game_id}`" target="_blank" rel="noopener" class="hub" title="Watch on the hub">hub ↗</a>
        </div>
      </li>
    </ul>
    <div class="note">A Game Report lists the game's key moments for you — highlights, lowlights, two-minute blocks — with links straight into the hub at those seconds, and two or three rewinds: moments where a better first move was on the table. First open takes about half a minute while the demo is read.</div>
  </section>
</template>

<style scoped>
.rg { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.title { font-weight: 800; font-size: 14px; letter-spacing: 0.02em; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 999px; overflow: hidden; }
.sbtn { background: transparent; color: var(--fg-2); border: 0; padding: 8px 14px; font-weight: 700; font-size: 13px; cursor: pointer; min-height: 36px; }
.sbtn.on { background: var(--accent); color: #140b03; }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; background: var(--panel); border: 1px solid var(--border); border-left: 3px solid var(--border); border-radius: 10px; padding: 8px 12px; min-width: 0; }
.row.w { border-left-color: #34d67a; } .row.l { border-left-color: #ff5d6c; }
.main { flex: 1 1 220px; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.l1 { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; font-size: 14px; }
.map { font-weight: 800; }
.res { font-weight: 900; font-size: 12px; } .res.w { color: #34d67a; } .res.l { color: #ff5d6c; }
.score { font-variant-numeric: tabular-nums; font-weight: 700; }
.l2 { font-size: 12px; display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
.opp { overflow-wrap: anywhere; }
.muted { color: var(--fg-2); font-size: 12px; }
.tag { font-size: 11px; border: 1px solid var(--border); border-radius: 999px; padding: 1px 7px; color: var(--fg-2); }
.act { display: flex; align-items: center; gap: 10px; margin-left: auto; flex-wrap: wrap; }
.rep { font-weight: 800; font-size: 13px; color: var(--accent); text-decoration: none; border: 1px solid var(--accent); border-radius: 999px; padding: 7px 12px; min-height: 36px; display: inline-flex; align-items: center; white-space: nowrap; }
.rep.ready { background: var(--accent); color: #140b03; }
.rep:hover { filter: brightness(1.1); }
.hub { font-size: 12px; color: var(--fg-2); text-decoration: none; padding: 7px 4px; min-height: 36px; display: inline-flex; align-items: center; white-space: nowrap; }
.hub:hover { color: var(--accent); }
.soon { white-space: nowrap; }
.note { color: var(--fg-2); font-size: 12px; line-height: 1.5; }
.note.err { color: #fca5a5; }
</style>

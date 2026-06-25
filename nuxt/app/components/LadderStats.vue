<script setup>
// Full ladder stats: sortable Team Statistics, Map Statistics, and the reports
// list (→ MatchDetailModal). Used by the Stats tab and the /ladder/stats route.
const props = defineProps({ ladderId: { type: Number, required: true } })
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const teamStats = ref([]); const playerStats = ref([]); const mapStats = ref(null); const matches = ref([])
const enhanced = ref([])
const loading = ref(true); const openMatchId = ref(null)
const statView = ref('team')   // 'team' | 'players' | 'enhanced'

async function load() {
  loading.value = true
  try {
    const [ts, ps, ms, mr] = await Promise.all([
      $fetch(`${base}/api/ladder/${props.ladderId}/team-stats`),
      $fetch(`${base}/api/ladder/${props.ladderId}/player-stats`),
      $fetch(`${base}/api/ladder/${props.ladderId}/map-stats`),
      $fetch(`${base}/api/ladder/${props.ladderId}/matches`),
    ])
    teamStats.value = ts.teams || []; playerStats.value = ps.players || []
    mapStats.value = ms; matches.value = mr.matches || []
  } catch (e) { console.error('[ladderstats]', e) } finally { loading.value = false }
  // enhanced (mvd-api) stats — separate so a miss never breaks the core tables
  try { enhanced.value = (await $fetch(`${base}/api/ladder/${props.ladderId}/enhanced-stats`)).players || [] }
  catch { enhanced.value = [] }
}
function setView(v) { statView.value = v; sortKey.value = (v === 'enhanced' ? 'damage' : 'eff'); sortDir.value = -1 }
onMounted(load)

// Results are shown WINNER-first (not challenger-first) so a row always reads
// "winner  X–Y  loser" — never the contradictory "A def B 0-2" (BloodDog).
// ⚔ marks whichever side was the challenger, preserving that context.
function oriented(m) {
  const bWon = m.winner_id != null && m.winner_id === m.team_b_id
  const A = { id: m.team_a_id, name: m.a_name, logo: m.a_logo, score: m.score_a }
  const B = { id: m.team_b_id, name: m.b_name, logo: m.b_logo, score: m.score_b }
  const w = bWon ? B : A, l = bWon ? A : B
  return { w, l, wIsChallenger: w.id === m.team_a_id }
}

const COLS = [
  { k: 'eff', l: 'Eff', pct: true, cls: 'eff' }, { k: 'frags', l: 'F' }, { k: 'deaths', l: 'D' },
  { k: 'suicides', l: '☠' }, { k: 'tk', l: 'TK' },
  { k: 'dmg_given', l: 'Gvn', grp: true, fmt: 'int' }, { k: 'dmg_taken', l: 'Tkn', fmt: 'int' },
  { k: 'ya', l: 'YA', grp: true, cls: 'c-ya' }, { k: 'ra', l: 'RA', cls: 'c-ra' }, { k: 'mh', l: 'MH', cls: 'c-mh' },
  { k: 'sg', l: 'SG', grp: true, pct: true, cls: 'c-wpn' }, { k: 'lg', l: 'LG', pct: true, cls: 'c-wpn' },
  { k: 'rl', l: 'RL', pct: true, cls: 'c-wpn' }, { k: 'quad', l: 'Q', grp: true, cls: 'c-q' },
]
// Enhanced (mvd-api) leaderboard columns — the stats KTX box-score can't give.
const ENH_COLS = [
  { k: 'damage', l: 'Dmg', fmt: 'int' }, { k: 'frag_diff', l: '+/–', signed: true },
  { k: 'react_ms', l: 'Spot→Fire', fmt: 'ms' },
  { k: 'rockets_dmg', l: 'Rkts hit', grp: true }, { k: 'rockets_direct', l: 'Direct' }, { k: 'rockets_splash', l: 'Splash' },
  { k: 'avg_rocket', l: 'Avg rkt' }, { k: 'rl_pref', l: 'RL%', pct: true, cls: 'c-wpn' },
  { k: 'ewep_pct', l: 'EWep', pct: true, grp: true }, { k: 'frags', l: 'F' }, { k: 'deaths', l: 'D' },
]
const sortKey = ref('eff'); const sortDir = ref(-1)
function sortBy(k) { if (sortKey.value === k) sortDir.value *= -1; else { sortKey.value = k; sortDir.value = -1 } }
const sortedTeams = computed(() => [...teamStats.value].sort((a, b) => ((a[sortKey.value] ?? -1) - (b[sortKey.value] ?? -1)) * sortDir.value))
const sortedPlayers = computed(() => [...playerStats.value].sort((a, b) => ((a[sortKey.value] ?? -1) - (b[sortKey.value] ?? -1)) * sortDir.value))
// react_ms sorts ascending-as-better, but generic sort handles it via header click; default is damage desc.
const sortedEnhanced = computed(() => [...enhanced.value].sort((a, b) => ((a[sortKey.value] ?? -1e9) - (b[sortKey.value] ?? -1e9)) * sortDir.value))
const anyData = computed(() => teamStats.value.some(t => t.maps > 0))
function fmtCell(v, c) { if (v == null) return '—'; if (c.pct) return v + '%'; if (c.fmt === 'ms') return v + 'ms'; if (c.fmt === 'int') return Math.round(v).toLocaleString(); if (c.signed) return (v >= 0 ? '+' : '') + v; return v }
function logoUrl(id) { return `${base}/api/ladder/team/${id}/logo` }
function fmtDate(s) { return s ? new Date(s).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '' }
</script>

<template>
  <div>
    <div v-if="loading" class="muted pad">Loading stats…</div>
    <div v-else-if="!anyData && !matches.length" class="empty">
      <h3>No match stats yet</h3>
      <p>Team &amp; map stats fill in automatically once matches are reported. The first reported Bo3 lands here.</p>
    </div>
    <template v-else>
      <section class="panel">
        <h2>
          <span class="toggle">
            <button :class="{ on: statView === 'team' }" @click="setView('team')">Team Stats</button>
            <button :class="{ on: statView === 'players' }" @click="setView('players')">Player Stats</button>
            <button :class="{ on: statView === 'enhanced' }" @click="setView('enhanced')">✨ Enhanced</button>
          </span>
          <span class="meta">{{ statView === 'enhanced' ? 'mvd-api deep stats · per-map averages · click a header to sort' : 'per-map averages · click a header to sort' }}</span>
        </h2>
        <!-- Team Statistics -->
        <div v-if="statView === 'team'" class="scroll">
          <table class="stats">
            <thead><tr>
              <th class="team">Team</th>
              <th v-for="c in COLS" :key="c.k" :class="[{ sorted: sortKey === c.k, colgrp: c.grp }]" @click="sortBy(c.k)">{{ c.l }}<span v-if="sortKey === c.k">{{ sortDir < 0 ? ' ▾' : ' ▴' }}</span></th>
              <th>Maps</th>
            </tr></thead>
            <tbody>
              <tr v-for="t in sortedTeams" :key="t.team_id">
                <td class="team"><span class="tc"><img v-if="t.has_logo" :src="logoUrl(t.team_id)" class="lg" alt=""><span v-else class="lg lg-ph">👑</span><span class="tag">{{ t.tag || '—' }}</span> {{ t.name }}</span></td>
                <td v-for="c in COLS" :key="c.k" :class="[c.cls, { colgrp: c.grp }]">{{ fmtCell(t[c.k], c) }}</td>
                <td class="muted">{{ t.maps }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Player Statistics -->
        <div v-else-if="statView === 'players'" class="scroll">
          <table v-if="playerStats.length" class="stats">
            <thead><tr>
              <th class="team">Player</th>
              <th v-for="c in COLS" :key="c.k" :class="[{ sorted: sortKey === c.k, colgrp: c.grp }]" @click="sortBy(c.k)">{{ c.l }}<span v-if="sortKey === c.k">{{ sortDir < 0 ? ' ▾' : ' ▴' }}</span></th>
              <th>Maps</th>
            </tr></thead>
            <tbody>
              <tr v-for="p in sortedPlayers" :key="p.canonical_id">
                <td class="team"><span class="tc"><NuxtLink :to="`/p/${p.canonical_id}`" class="pl-name">{{ p.name }}</NuxtLink><span v-if="p.tag" class="tag sm">{{ p.tag }}</span></span></td>
                <td v-for="c in COLS" :key="c.k" :class="[c.cls, { colgrp: c.grp }]">{{ fmtCell(p[c.k], c) }}</td>
                <td class="muted">{{ p.maps }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="muted small" style="padding:8px 0;">No player stats yet.</div>
        </div>
        <!-- Enhanced (mvd-api) Statistics -->
        <div v-else-if="statView === 'enhanced'" class="scroll">
          <table v-if="enhanced.length" class="stats">
            <thead><tr>
              <th class="team">Player</th>
              <th v-for="c in ENH_COLS" :key="c.k" :class="[{ sorted: sortKey === c.k, colgrp: c.grp }]" @click="sortBy(c.k)">{{ c.l }}<span v-if="sortKey === c.k">{{ sortDir < 0 ? ' ▾' : ' ▴' }}</span></th>
              <th>Maps</th>
            </tr></thead>
            <tbody>
              <tr v-for="p in sortedEnhanced" :key="p.canonical_id">
                <td class="team"><span class="tc"><NuxtLink :to="`/p/${p.canonical_id}`" class="pl-name">{{ p.name }}</NuxtLink><span v-if="p.team" class="tag sm">{{ p.team }}</span></span></td>
                <td v-for="c in ENH_COLS" :key="c.k" :class="[c.cls, { colgrp: c.grp }]">{{ fmtCell(p[c.k], c) }}</td>
                <td class="muted">{{ p.maps }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="muted small" style="padding:8px 0;">No enhanced stats yet — they ingest from the demo parser as matches are reported.</div>
          <p class="muted small" style="margin:8px 2px 0;">All per-map averages (so players with more games stay comparable). Dmg = damage/map · Spot→Fire = median ms from a clear line-of-sight to your first hit (incl. ping) · Rkts hit = damaging rockets/map (direct/splash) · Avg rkt = damage per rocket · EWep = % of damage on armed enemies. From the mvd-api demo parser, not box-score.</p>
        </div>
      </section>

      <div class="two">
        <section class="panel" v-if="mapStats">
          <h2>Map Statistics <span class="meta">{{ mapStats.total_maps }} maps</span></h2>
          <div class="mapgrid">
            <div class="mcard"><div class="mh">Most played</div><div v-for="r in mapStats.most_played" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.count }} <small>({{ r.pct }}%)</small></span></div><div v-if="!mapStats.most_played.length" class="muted small">—</div></div>
            <div class="mcard"><div class="mh">First pick</div><div v-for="r in mapStats.first_pick" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.count }} <small>({{ r.pct }}%)</small></span></div><div v-if="!mapStats.first_pick.length" class="muted small">—</div></div>
            <div class="mcard"><div class="mh">Decider</div><div v-for="r in mapStats.decider" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.count }} <small>({{ r.pct }}%)</small></span></div><div v-if="!mapStats.decider.length" class="muted small">—</div></div>
            <div class="mcard"><div class="mh">High scoring <small>avg combined</small></div><div v-for="r in mapStats.high_scoring" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.avg }}</span></div><div v-if="!mapStats.high_scoring.length" class="muted small">—</div></div>
            <div class="mcard"><div class="mh">Closest</div><div v-for="(g, i) in mapStats.closest" :key="i" class="mrow match"><span class="k">{{ g.label }} · {{ g.map }}</span><span class="v">{{ g.a }}–{{ g.b }}</span></div><div v-if="!mapStats.closest.length" class="muted small">—</div></div>
            <div class="mcard"><div class="mh">Blowouts</div><div v-for="(g, i) in mapStats.blowouts" :key="i" class="mrow match"><span class="k">{{ g.label }} · {{ g.map }}</span><span class="v">{{ g.a }}–{{ g.b }}</span></div><div v-if="!mapStats.blowouts.length" class="muted small">—</div></div>
          </div>
        </section>

        <section class="panel">
          <h2>Match reports</h2>
          <div v-if="!matches.length" class="muted small">No matches reported yet.</div>
          <div class="reports">
            <div v-if="matches.length" class="rep-head">
              <span class="rt">Winner</span><span class="rs"></span><span class="rt right">Loser</span><span class="rd"></span>
            </div>
            <button v-for="m in matches" :key="m.id" class="rep" @click="openMatchId = m.id">
              <template v-for="o in [oriented(m)]" :key="'o'+m.id">
                <span class="rt"><img v-if="o.w.logo" :src="logoUrl(o.w.id)" class="lg" alt=""> {{ o.w.name }}<span v-if="o.wIsChallenger" class="chal" title="Challenger">⚔</span></span>
                <span class="rs"><b class="w">{{ o.w.score }}</b>–<b>{{ o.l.score }}</b></span>
                <span class="rt right"><span v-if="!o.wIsChallenger" class="chal" title="Challenger">⚔</span>{{ o.l.name }} <img v-if="o.l.logo" :src="logoUrl(o.l.id)" class="lg" alt=""></span>
              </template>
              <span class="rd">{{ fmtDate(m.played_at) }}</span>
            </button>
          </div>
        </section>
      </div>
    </template>

    <MatchDetailModal v-if="openMatchId" :match-id="openMatchId" @close="openMatchId = null" />
  </div>
</template>

<style scoped>
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 40px 0; text-align: center; }
.empty { text-align: center; padding: 50px 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; }
.empty h3 { margin: 0 0 8px; } .empty p { color: var(--fg-2); margin: 0; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; margin-bottom: 16px; }
.panel h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); margin: 0 0 14px; font-weight: 800; display: flex; gap: 8px; }
.panel h2 .meta { margin-left: auto; text-transform: none; letter-spacing: 0; font-weight: 400; }
.toggle { display: inline-flex; gap: 2px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 2px; }
.toggle button { background: none; border: 0; color: var(--fg-3); font-family: inherit; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 6px; cursor: pointer; text-transform: none; letter-spacing: 0; }
.toggle button.on { background: var(--accent); color: var(--bg); }
.pl-name { color: var(--fg); text-decoration: none; font-weight: 700; }
.pl-name:hover { color: var(--accent); }
.tag.sm { font-size: 9px; }
.two { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
@media (max-width: 860px) { .two { grid-template-columns: 1fr; } }
.scroll { overflow-x: auto; }
table.stats { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13px; }
table.stats th, table.stats td { padding: 7px 9px; text-align: right; white-space: nowrap; }
table.stats th { font-size: 11px; color: var(--fg-3); font-weight: 700; border-bottom: 1px solid var(--border); cursor: pointer; user-select: none; }
table.stats th.sorted { color: var(--accent); }
table.stats th.team, table.stats td.team { text-align: left; }
table.stats td { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; border-bottom: 1px solid rgba(43,54,80,.45); }
table.stats tbody tr:hover { background: var(--panel-2); }
.colgrp { border-left: 1px solid var(--border); }
.tc { display: flex; align-items: center; gap: 8px; font-family: system-ui, sans-serif; font-weight: 700; }
.lg { width: 20px; height: 20px; border-radius: 5px; object-fit: cover; flex: 0 0 20px; }
.lg-ph { display: inline-flex; align-items: center; justify-content: center; background: var(--panel-3); font-size: 11px; opacity: 0.55; }
.tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; padding: 1px 4px; border-radius: 4px; background: var(--panel-3); color: var(--accent); min-width: 40px; text-align: center; box-sizing: border-box; flex: 0 0 auto; }
.lg { width: 20px; height: 20px; border-radius: 5px; object-fit: cover; }
.eff { color: var(--accent); font-weight: 700; }
.c-ya { color: #fbbf24; } .c-ra { color: var(--loss); } .c-mh { color: #60a5fa; } .c-wpn { color: var(--accent); } .c-q { color: #22d3ee; }
.mapgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.mcard { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; }
.mcard .mh { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--accent); font-weight: 800; margin-bottom: 7px; }
.mcard .mh small { color: var(--fg-3); text-transform: none; font-weight: 400; }
.mrow { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; border-bottom: 1px solid rgba(43,54,80,.4); }
.mrow:last-child { border-bottom: 0; }
.mrow .k { color: var(--fg-2); font-family: 'JetBrains Mono', monospace; }
.mrow .v { font-family: 'JetBrains Mono', monospace; font-weight: 700; } .mrow .v small { color: var(--fg-3); font-weight: 400; }
.mrow.match .k { font-family: system-ui, sans-serif; font-size: 11px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reports { display: flex; flex-direction: column; gap: 7px; }
.rep-head { display: flex; align-items: center; gap: 9px; padding: 0 12px 1px; }
.rep-head .rt { flex: 1; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--fg-3); font-weight: 800; }
.rep-head .rt.right { justify-content: flex-end; text-align: right; }
.rep-head .rs { min-width: 30px; text-align: center; } .rep-head .rd { width: 44px; }
.rep { display: flex; align-items: center; gap: 9px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 9px; padding: 9px 12px; font-size: 13px; cursor: pointer; color: var(--fg); font-family: inherit; text-align: left; }
.rep:hover { border-color: var(--accent); }
.rep .rt { display: flex; align-items: center; gap: 7px; flex: 1; } .rep .rt.right { justify-content: flex-end; }
.rep .rs { font-family: 'JetBrains Mono', monospace; font-weight: 800; } .rep .rs b { color: var(--fg-3); } .rep .rs b.w { color: var(--accent); }
.rep .rd { color: var(--fg-3); font-size: 11px; width: 44px; text-align: right; }
.chal { font-size: 10px; opacity: .5; margin: 0 3px; cursor: help; }
</style>

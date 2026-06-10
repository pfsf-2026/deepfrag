<script setup>
// KOTH ladder stats — Team Statistics (per-map averages), Map Statistics, and
// recent match reports with a per-map/per-player deep-dive. All from reported
// matches' linked hub games. See /api/ladder/{id}/{team-stats,map-stats,matches}.
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const ladderId = ref(null)
const teamStats = ref([])
const mapStats = ref(null)
const matches = ref([])
const loading = ref(true)
const err = ref('')

async function load() {
  loading.value = true; err.value = ''
  try {
    const list = await $fetch(`${base}/api/ladder`, { query: { _: Date.now() } })
    const first = (list.ladders || [])[0]
    if (!first) { loading.value = false; return }
    ladderId.value = first.id
    const [ts, ms, mr] = await Promise.all([
      $fetch(`${base}/api/ladder/${first.id}/team-stats`),
      $fetch(`${base}/api/ladder/${first.id}/map-stats`),
      $fetch(`${base}/api/ladder/${first.id}/matches`),
    ])
    teamStats.value = ts.teams || []
    mapStats.value = ms
    matches.value = mr.matches || []
  } catch (e) { err.value = 'Could not load stats.'; console.error('[stats]', e) }
  finally { loading.value = false }
}
onMounted(load)

// ── team-stats table: sortable ──────────────────────────────────────────────
const COLS = [
  { k: 'eff', l: 'Eff', pct: true, cls: 'eff' }, { k: 'frags', l: 'F' }, { k: 'deaths', l: 'D' },
  { k: 'suicides', l: '☠' }, { k: 'tk', l: 'TK' },
  { k: 'dmg_given', l: 'Gvn', grp: true, fmt: 'k' }, { k: 'dmg_taken', l: 'Tkn', fmt: 'k' },
  { k: 'ya', l: 'YA', grp: true, cls: 'c-ya' }, { k: 'ra', l: 'RA', cls: 'c-ra' }, { k: 'mh', l: 'MH', cls: 'c-mh' },
  { k: 'sg', l: 'SG', grp: true, pct: true, cls: 'c-wpn' }, { k: 'lg', l: 'LG', pct: true, cls: 'c-wpn' },
  { k: 'rl', l: 'RL', pct: true, cls: 'c-wpn' }, { k: 'quad', l: 'Q', grp: true, cls: 'c-q' },
]
const sortKey = ref('eff')
const sortDir = ref(-1)
function sortBy(k) { if (sortKey.value === k) sortDir.value *= -1; else { sortKey.value = k; sortDir.value = -1 } }
const sortedTeams = computed(() => [...teamStats.value].sort((a, b) => ((a[sortKey.value] ?? -1) - (b[sortKey.value] ?? -1)) * sortDir.value))
const anyData = computed(() => teamStats.value.some(t => t.maps > 0))
function fmtCell(v, c) {
  if (v == null) return '—'
  if (c.pct) return v + '%'
  if (c.fmt === 'k') return v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v
  return v
}
function logoUrl(id) { return `${base}/api/ladder/team/${id}/logo` }

// ── match deep-dive modal ───────────────────────────────────────────────────
const detail = ref(null)
const detailLoading = ref(false)
async function openMatch(id) {
  detailLoading.value = true; detail.value = null
  try { detail.value = await $fetch(`${base}/api/ladder/match/${id}`) }
  catch { err.value = 'Could not load that match.' } finally { detailLoading.value = false }
}
function mapWinner(m) { return (m.a_frags ?? 0) > (m.b_frags ?? 0) ? 'a' : (m.b_frags ?? 0) > (m.a_frags ?? 0) ? 'b' : null }
function fmtDate(s) { return s ? new Date(s).toLocaleDateString([], { month: 'short', day: 'numeric' }) : '' }

useHead({ title: 'KOTH Stats · DeepFrag' })
</script>

<template>
  <div class="wrap">
    <header class="head">
      <div>
        <h1>KOTH — Stats</h1>
        <p class="sub">Per-map averages &amp; map analytics from reported ladder matches.</p>
      </div>
      <NuxtLink to="/ladder" class="back">← Ladder</NuxtLink>
    </header>

    <ClientOnly>
      <div v-if="loading" class="muted pad">Loading stats…</div>
      <div v-else-if="err" class="muted pad">{{ err }}</div>
      <div v-else-if="!anyData && !matches.length" class="empty">
        <h2>No match stats yet</h2>
        <p>Stats appear here once matches are reported. The first reported Bo3 lands here automatically.</p>
      </div>

      <template v-else>
        <!-- Team Statistics -->
        <section class="panel">
          <h2>Team Statistics <span class="meta">per-map averages · click a header to sort</span></h2>
          <div class="scroll">
            <table class="stats">
              <thead><tr>
                <th class="team">Team</th>
                <th v-for="c in COLS" :key="c.k" :class="[{ sorted: sortKey === c.k, colgrp: c.grp }]" @click="sortBy(c.k)">
                  {{ c.l }}<span v-if="sortKey === c.k">{{ sortDir < 0 ? ' ▾' : ' ▴' }}</span>
                </th>
                <th>Maps</th>
              </tr></thead>
              <tbody>
                <tr v-for="t in sortedTeams" :key="t.team_id">
                  <td class="team"><span class="tc"><img v-if="t.has_logo" :src="logoUrl(t.team_id)" class="lg" alt=""><span v-if="t.tag" class="tag">{{ t.tag }}</span> {{ t.name }}</span></td>
                  <td v-for="c in COLS" :key="c.k" :class="[c.cls, { colgrp: c.grp }]">{{ fmtCell(t[c.k], c) }}</td>
                  <td class="muted">{{ t.maps }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="key"><small>Color: <span class="c-ya">▉ armor</span> · <span class="c-mh">▉ health</span> · <span class="c-wpn">▉ weapon acc</span> · <span class="c-q">▉ quad</span></small></p>
        </section>

        <div class="two">
          <!-- Map Statistics -->
          <section class="panel" v-if="mapStats">
            <h2>Map Statistics <span class="meta">{{ mapStats.total_maps }} maps</span></h2>
            <div class="mapgrid">
              <div class="mcard">
                <div class="mh">Most played</div>
                <div v-for="r in mapStats.most_played" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.count }} <small>({{ r.pct }}%)</small></span></div>
                <div v-if="!mapStats.most_played.length" class="muted small">—</div>
              </div>
              <div class="mcard">
                <div class="mh">First pick</div>
                <div v-for="r in mapStats.first_pick" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.count }} <small>({{ r.pct }}%)</small></span></div>
                <div v-if="!mapStats.first_pick.length" class="muted small">—</div>
              </div>
              <div class="mcard">
                <div class="mh">Decider</div>
                <div v-for="r in mapStats.decider" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.count }} <small>({{ r.pct }}%)</small></span></div>
                <div v-if="!mapStats.decider.length" class="muted small">—</div>
              </div>
              <div class="mcard">
                <div class="mh">High scoring <small>avg combined</small></div>
                <div v-for="r in mapStats.high_scoring" :key="r.map" class="mrow"><span class="k">{{ r.map }}</span><span class="v">{{ r.avg }}</span></div>
                <div v-if="!mapStats.high_scoring.length" class="muted small">—</div>
              </div>
              <div class="mcard">
                <div class="mh">Closest</div>
                <div v-for="(g, i) in mapStats.closest" :key="i" class="mrow match"><span class="k">{{ g.label }} · {{ g.map }}</span><span class="v">{{ g.a }}–{{ g.b }}</span></div>
                <div v-if="!mapStats.closest.length" class="muted small">—</div>
              </div>
              <div class="mcard">
                <div class="mh">Blowouts</div>
                <div v-for="(g, i) in mapStats.blowouts" :key="i" class="mrow match"><span class="k">{{ g.label }} · {{ g.map }}</span><span class="v">{{ g.a }}–{{ g.b }}</span></div>
                <div v-if="!mapStats.blowouts.length" class="muted small">—</div>
              </div>
            </div>
          </section>

          <!-- Recent reports -->
          <section class="panel">
            <h2>Match reports</h2>
            <div v-if="!matches.length" class="muted small">No matches reported yet.</div>
            <div class="reports">
              <button v-for="m in matches" :key="m.id" class="rep" @click="openMatch(m.id)">
                <span class="rt"><img v-if="m.a_logo" :src="logoUrl(m.team_a_id)" class="lg" alt=""> {{ m.a_name }}</span>
                <span class="rs"><b :class="{ w: m.winner_id === m.team_a_id }">{{ m.score_a }}</b>–<b :class="{ w: m.winner_id === m.team_b_id }">{{ m.score_b }}</b></span>
                <span class="rt right">{{ m.b_name }} <img v-if="m.b_logo" :src="logoUrl(m.team_b_id)" class="lg" alt=""></span>
                <span class="rd">{{ fmtDate(m.played_at) }}</span>
              </button>
            </div>
          </section>
        </div>
      </template>

      <!-- deep-dive modal -->
      <div v-if="detail || detailLoading" class="modal-bg" @click.self="detail = null; detailLoading = false">
        <div class="modal">
          <div v-if="detailLoading" class="muted pad">Loading match…</div>
          <template v-else-if="detail">
            <div class="md-head">
              <span class="md-team"><img v-if="detail.a_logo" :src="logoUrl(detail.a_id)" class="lg2" alt=""> {{ detail.a_name }}</span>
              <span class="md-sc"><b :class="{ w: detail.winner_id === detail.a_id }">{{ detail.score_a }}</b> – <b :class="{ w: detail.winner_id === detail.b_id }">{{ detail.score_b }}</b></span>
              <span class="md-team right">{{ detail.b_name }} <img v-if="detail.b_logo" :src="logoUrl(detail.b_id)" class="lg2" alt=""></span>
              <button class="x" @click="detail = null">✕</button>
            </div>
            <div class="md-maps">
              <span v-for="(mp, i) in detail.maps" :key="i" class="m" :class="{ wa: mapWinner(mp)==='a', wb: mapWinner(mp)==='b' }">
                {{ mp.map }} <b>{{ mp.a_frags }}–{{ mp.b_frags }}</b>
              </span>
            </div>
            <div v-for="(mp, i) in detail.maps" :key="'t'+i" class="md-map-block">
              <div class="md-map-h">{{ mp.map }} <span class="muted small">{{ mp.a_frags }}–{{ mp.b_frags }}</span></div>
              <div v-if="!mp.players.length" class="muted small">No per-player stats linked for this map.</div>
              <table v-else class="pl">
                <thead><tr><th class="l">Player</th><th>F</th><th>D</th><th>Eff</th><th>RL%</th><th>LG%</th><th>RA</th><th>Q</th><th>Dmg</th></tr></thead>
                <tbody>
                  <tr v-for="p in mp.players" :key="p.canonical_id || p.name">
                    <td class="l">{{ p.name }}</td><td>{{ p.frags }}</td><td>{{ p.deaths }}</td>
                    <td>{{ p.eff }}%</td><td>{{ p.rl }}%</td><td>{{ p.lg }}%</td><td>{{ p.ra }}</td><td>{{ p.quad }}</td>
                    <td>{{ p.dmg >= 1000 ? (p.dmg/1000).toFixed(1)+'k' : p.dmg }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </div>
    </ClientOnly>
  </div>
</template>

<style scoped>
.wrap { max-width: 1080px; margin: 0 auto; padding: 28px 20px 80px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }
h1 { font-size: 24px; font-weight: 900; margin: 0; }
.sub { color: var(--fg-3); font-size: 13px; margin: 4px 0 0; }
.back { color: var(--accent); text-decoration: none; font-size: 13px; }
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 40px 0; text-align: center; }
.empty { text-align: center; padding: 60px 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; }
.empty h2 { margin: 0 0 8px; } .empty p { color: var(--fg-2); margin: 0; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; margin-bottom: 16px; }
.panel h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); margin: 0 0 14px; font-weight: 800; display: flex; gap: 8px; }
.panel h2 .meta { margin-left: auto; text-transform: none; letter-spacing: 0; font-weight: 400; }
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
.tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 4px; background: var(--panel-3); color: var(--accent); }
.lg { width: 20px; height: 20px; border-radius: 5px; object-fit: cover; }
.eff { color: var(--accent); font-weight: 700; }
.c-ya { color: #fbbf24; } .c-ra { color: var(--loss); } .c-mh { color: #60a5fa; }
.c-wpn { color: var(--accent); } .c-q { color: #22d3ee; }
.key { margin: 10px 0 0; color: var(--fg-3); }

.mapgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; }
.mcard { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; }
.mcard .mh { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--accent); font-weight: 800; margin-bottom: 7px; }
.mcard .mh small { color: var(--fg-3); text-transform: none; font-weight: 400; }
.mrow { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; border-bottom: 1px solid rgba(43,54,80,.4); }
.mrow:last-child { border-bottom: 0; }
.mrow .k { color: var(--fg-2); font-family: 'JetBrains Mono', monospace; }
.mrow .v { font-family: 'JetBrains Mono', monospace; font-weight: 700; }
.mrow .v small { color: var(--fg-3); font-weight: 400; }
.mrow.match .k { font-family: system-ui, sans-serif; font-size: 11px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.reports { display: flex; flex-direction: column; gap: 7px; }
.rep { display: flex; align-items: center; gap: 9px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 9px; padding: 9px 12px; font-size: 13px; cursor: pointer; color: var(--fg); font-family: inherit; text-align: left; }
.rep:hover { border-color: var(--accent); }
.rep .rt { display: flex; align-items: center; gap: 7px; flex: 1; }
.rep .rt.right { justify-content: flex-end; }
.rep .rs { font-family: 'JetBrains Mono', monospace; font-weight: 800; }
.rep .rs b { color: var(--fg-3); } .rep .rs b.w { color: var(--accent); }
.rep .rd { color: var(--fg-3); font-size: 11px; width: 44px; text-align: right; }

.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.7); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 20px 22px; width: 100%; max-width: 640px; max-height: 90vh; overflow-y: auto; }
.md-head { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.md-team { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 16px; flex: 1; }
.md-team.right { justify-content: flex-end; }
.lg2 { width: 28px; height: 28px; border-radius: 7px; object-fit: cover; }
.md-sc { font-family: 'JetBrains Mono', monospace; font-size: 22px; font-weight: 800; }
.md-sc b { color: var(--fg-3); } .md-sc b.w { color: var(--accent); }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.md-maps { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.md-maps .m { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 4px 9px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--border); }
.md-maps .m.wa, .md-maps .m.wb { border-color: var(--accent); }
.md-map-block { margin-bottom: 14px; }
.md-map-h { font-family: 'JetBrains Mono', monospace; font-weight: 700; margin-bottom: 6px; }
table.pl { border-collapse: collapse; width: 100%; font-size: 12px; }
table.pl th { font-size: 10px; color: var(--fg-3); text-transform: uppercase; text-align: right; padding: 5px 7px; border-bottom: 1px solid var(--border); }
table.pl th.l, table.pl td.l { text-align: left; }
table.pl td { font-family: 'JetBrains Mono', monospace; text-align: right; padding: 6px 7px; border-bottom: 1px solid rgba(43,54,80,.4); }
table.pl td.l { font-family: system-ui, sans-serif; font-weight: 700; }
</style>

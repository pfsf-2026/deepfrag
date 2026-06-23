<script setup>
// KOTH 2v2 ladder — team home page. Mirrors thebig4 Team Details: header + record,
// match history (us/them), per-map record, aggregate team stats, per-player stats.
// Reads /api/ladder/team/{id}/summary (client-side; matches the ladder hub pattern).
const route = useRoute()
const router = useRouter()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const id = computed(() => parseInt(route.params.id))
const data = ref(null)
const allTeams = ref([])
const loading = ref(true)
const err = ref(null)

function logoUrl(tid) { return `${base}/api/ladder/team/${tid}/logo` }
function fmtDate(s) {
  if (!s) return '—'
  try { return new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' }) }
  catch { return '—' }
}

async function load() {
  loading.value = true; err.value = null
  try {
    data.value = await $fetch(`${base}/api/ladder/team/${id.value}/summary`, { query: { _: Date.now() } })
  } catch (e) { err.value = 'Could not load this team.'; console.error('[team]', e) }
  finally { loading.value = false }
}
// team switcher (dropdown, like the big4 "Select Team")
async function loadTeams() {
  try {
    const list = await $fetch(`${base}/api/ladder`)
    const first = (list.ladders || [])[0]
    if (!first) return
    const d = await $fetch(`${base}/api/ladder/${first.id}`)
    allTeams.value = (d.teams || []).slice().sort((a, b) => (a.rung || 99) - (b.rung || 99))
  } catch { /* non-fatal */ }
}
function switchTeam(e) { const v = e.target.value; if (v) router.push(`/ladder/team/${v}`) }

const team = computed(() => data.value?.team)
const matches = computed(() => data.value?.matches || [])
const mapStats = computed(() => data.value?.map_stats || [])
const teamStats = computed(() => data.value?.team_stats || {})
const players = computed(() => data.value?.players || [])
const hasStats = computed(() => (teamStats.value?.maps || 0) > 0)

onMounted(() => { load(); loadTeams() })
watch(() => route.params.id, () => { load() })
useHead(() => ({ title: team.value ? `${team.value.name} · KOTH Ladder · DeepFrag` : 'Team · DeepFrag' }))
</script>

<template>
<div class="teampage">
  <div class="topbar">
    <h1>Team Details</h1>
    <div class="topright">
      <select class="teamsel" @change="switchTeam">
        <option value="">Select Team ▾</option>
        <option v-for="t in allTeams" :key="t.id" :value="t.id" :selected="t.id === id">
          #{{ t.rung }} · {{ t.name }}
        </option>
      </select>
      <NuxtLink class="closex" to="/ladder#standings" aria-label="Back to standings">✕</NuxtLink>
    </div>
  </div>

  <div v-if="loading" class="state">Loading team…</div>
  <div v-else-if="err" class="state err">{{ err }}</div>
  <div v-else-if="!team" class="state">Team not found.</div>

  <template v-else>
    <!-- HEADER -->
    <section class="card hero">
      <img v-if="team.has_logo" :src="logoUrl(team.id)" class="biglogo" alt="">
      <div v-else class="biglogo ph">👑</div>
      <div class="heroinfo">
        <div class="rankline">RUNG {{ team.rung ?? '—' }}<span class="dot">·</span>RANKED #{{ team.rung ?? '—' }}</div>
        <div class="name">{{ team.name }}</div>
        <div class="members">
          <template v-for="(m, i) in team.members" :key="m.id">
            <NuxtLink class="plink" :to="`/p/${m.id}`">{{ m.display }}</NuxtLink><span v-if="i < team.members.length - 1" class="sep">·</span>
          </template>
        </div>
      </div>
      <div class="herorec">
        <div class="rec"><span class="rn">{{ team.match_w }}–{{ team.match_l }}</span><span class="rl">Matches</span></div>
        <div class="rec"><span class="rn">{{ team.game_w }}–{{ team.game_l }}</span><span class="rl">Maps</span></div>
      </div>
    </section>

    <!-- MATCHES -->
    <section class="block">
      <div class="block-h"><span>Ladder Matches</span><span class="muted">{{ matches.length }} played</span></div>
      <div v-if="!matches.length" class="empty">No matches reported yet.</div>
      <div v-else class="matchgrid">
        <div v-for="m in matches" :key="m.id" class="match">
          <span class="wl" :class="m.won ? 'w' : 'l'">{{ m.won ? 'W' : 'L' }}</span>
          <span class="sc">{{ m.our_score }}<span class="dash">–</span>{{ m.their_score }}</span>
          <NuxtLink class="opp" :to="`/ladder/team/${m.opponent_id}`">
            <img v-if="m.opponent_logo" :src="logoUrl(m.opponent_id)" class="opplogo" alt="">
            <span class="oppname">{{ m.opponent }}</span>
          </NuxtLink>
          <span class="maps">
            <span v-for="(mp, i) in m.maps" :key="i" class="mtag"
                  :class="mp.our_frags > mp.their_frags ? 'mw' : (mp.their_frags > mp.our_frags ? 'ml' : '')">
              {{ mp.map }} <b>{{ mp.our_frags }}–{{ mp.their_frags }}</b>
            </span>
          </span>
          <span class="mdate">{{ fmtDate(m.played_at) }}</span>
        </div>
      </div>
    </section>

    <!-- MAP STATISTICS -->
    <section class="block" v-if="mapStats.length">
      <div class="block-h"><span>Map Statistics</span></div>
      <div class="mapcards">
        <div v-for="ms in mapStats" :key="ms.map" class="mapcard">
          <div class="mc-name">{{ ms.map }}</div>
          <div class="mc-row"><span>Record</span><b>{{ ms.w }}–{{ ms.l }}</b></div>
          <div class="mc-row"><span>Win Rate</span><b :class="ms.win_rate >= 50 ? 'good' : 'bad'">{{ ms.win_rate }}%</b></div>
          <div class="mc-row"><span>Biggest W</span><b class="good" :title="ms.biggest_w ? ms.biggest_w.score + ' v ' + ms.biggest_w.opp : ''">{{ ms.biggest_w ? ms.biggest_w.score : '—' }}<i v-if="ms.biggest_w"> v {{ ms.biggest_w.opp }}</i></b></div>
          <div class="mc-row"><span>Biggest L</span><b class="bad" :title="ms.biggest_l ? ms.biggest_l.score + ' v ' + ms.biggest_l.opp : ''">{{ ms.biggest_l ? ms.biggest_l.score : '—' }}<i v-if="ms.biggest_l"> v {{ ms.biggest_l.opp }}</i></b></div>
        </div>
      </div>
    </section>

    <!-- TEAM STATISTICS -->
    <section class="block" v-if="hasStats">
      <div class="block-h"><span>Team Statistics</span><span class="muted">avg / map · {{ teamStats.maps }} maps</span></div>
      <div class="statwrap">
        <table class="stat">
          <thead><tr>
            <th>Eff</th><th>F</th><th>D</th><th>TK</th><th>Gvn</th><th>Tkn</th>
            <th class="ya">YA</th><th class="ra">RA</th><th class="mh">MH</th><th class="sg">SG</th>
            <th class="lg">LG</th><th class="rl" title="RL direct hits / map">RLd</th><th class="q">Q</th>
          </tr></thead>
          <tbody><tr>
            <td class="hl">{{ teamStats.eff }}%</td><td>{{ teamStats.frags }}</td><td>{{ teamStats.deaths }}</td>
            <td>{{ teamStats.tk }}</td><td>{{ (teamStats.dmg_given/1000).toFixed(1) }}k</td><td>{{ (teamStats.dmg_taken/1000).toFixed(1) }}k</td>
            <td class="ya">{{ teamStats.ya }}</td><td class="ra">{{ teamStats.ra }}</td><td class="mh">{{ teamStats.mh }}</td>
            <td class="sg">{{ teamStats.sg }}%</td><td class="lg">{{ teamStats.lg }}%</td><td class="rl">{{ teamStats.rl }}</td><td class="q">{{ teamStats.quad }}</td>
          </tr></tbody>
        </table>
      </div>
    </section>

    <!-- PLAYER STATISTICS -->
    <section class="block" v-if="players.length">
      <div class="block-h"><span>Player Statistics</span><span class="muted">{{ players.length }} players · avg / map</span></div>
      <div class="statwrap">
        <table class="stat">
          <thead><tr>
            <th class="lft">Player</th><th>Maps</th><th>Eff</th><th>F</th><th>D</th>
            <th class="ya">YA</th><th class="ra">RA</th><th class="mh">MH</th><th class="sg">SG</th>
            <th class="lg">LG</th><th class="rl" title="RL direct hits / map">RLd</th><th class="q">Q</th>
          </tr></thead>
          <tbody>
            <tr v-for="p in players" :key="p.canonical_id">
              <td class="lft"><NuxtLink class="plink" :to="`/p/${p.canonical_id}`">{{ p.name }}</NuxtLink></td>
              <td>{{ p.maps }}</td><td class="hl">{{ p.eff }}%</td><td>{{ p.frags }}</td><td>{{ p.deaths }}</td>
              <td class="ya">{{ p.ya }}</td><td class="ra">{{ p.ra }}</td><td class="mh">{{ p.mh }}</td>
              <td class="sg">{{ p.sg }}%</td><td class="lg">{{ p.lg }}%</td><td class="rl">{{ p.rl }}</td><td class="q">{{ p.quad }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="!hasStats && matches.length" class="note">
      Detailed KTX stats appear once matches are reported with demo/game IDs. Match results above are from the ladder report.
    </div>
  </template>
</div>
</template>

<style scoped>
.teampage{max-width:1200px;margin:0 auto;padding:18px 16px 60px;color:var(--fg,#e8edf5)}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.topbar h1{font-size:22px;font-weight:800;margin:0}
.topright{display:flex;gap:10px;align-items:center}
.teamsel{background:var(--panel,#131820);color:var(--fg,#e8edf5);border:1px solid var(--border,#2b3445);border-radius:8px;padding:8px 10px;font-size:13px}
.closex{width:34px;height:34px;display:grid;place-items:center;border:1px solid var(--border,#2b3445);border-radius:8px;color:var(--fg-2,#94a3b8);background:var(--panel,#131820)}
.closex:hover{color:var(--fg,#e8edf5)}
.state{padding:40px;text-align:center;color:var(--fg-2,#94a3b8)} .state.err{color:var(--loss,#ef4444)}
.muted{color:var(--fg-2,#94a3b8);font-size:12px;font-weight:500}

.card{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:14px}
.hero{display:flex;align-items:center;gap:20px;padding:20px 22px;margin-bottom:18px}
.biglogo{width:72px;height:72px;border-radius:12px;object-fit:cover;border:1px solid var(--border-2,#3a4458);background:#0c1016}
.biglogo.ph{display:grid;place-items:center;font-size:34px}
.heroinfo{flex:1;min-width:0}
.rankline{font-size:11px;font-weight:800;letter-spacing:.08em;color:var(--accent,#14e6c0)}
.rankline .dot{margin:0 7px;color:var(--fg-3,#64748b)}
.name{font-size:26px;font-weight:800;line-height:1.1;margin:3px 0 5px}
.members{font-size:13px;color:var(--fg-2,#94a3b8)}
.members .sep{margin:0 7px;color:var(--fg-3,#64748b)}
.plink{color:var(--fg,#e8edf5);text-decoration:none;border-bottom:1px dotted var(--border-2,#3a4458)}
.plink:hover{color:var(--accent,#14e6c0)}
.herorec{display:flex;gap:24px}
.rec{text-align:center}
.rec .rn{display:block;font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:800}
.rec .rl{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--fg-3,#64748b)}

.block{margin-bottom:22px}
.block-h{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--fg-2,#94a3b8);margin:0 2px 10px}
.empty,.note{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:12px;padding:16px;color:var(--fg-2,#94a3b8);font-size:13px}
.note{border-left:3px solid var(--accent,#14e6c0);margin-top:6px}

.matchgrid{display:flex;flex-direction:column;gap:10px}
.match{display:flex;align-items:center;gap:12px;background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:10px;padding:11px 14px}
.wl{width:22px;height:22px;border-radius:6px;display:grid;place-items:center;font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:800;flex:none}
.wl.w{background:rgba(34,197,94,.15);color:var(--win,#22c55e)} .wl.l{background:rgba(239,68,68,.15);color:var(--loss,#ef4444)}
.sc{font-family:'JetBrains Mono',monospace;font-weight:800;font-size:15px;flex:none}.sc .dash{color:var(--fg-3,#64748b);margin:0 2px}
.opp{display:flex;align-items:center;gap:7px;min-width:0;flex:none;max-width:160px;text-decoration:none;color:var(--fg,#e8edf5)}
.opp:hover .oppname{color:var(--accent,#14e6c0)}
.opplogo{width:20px;height:20px;border-radius:5px;object-fit:cover}
.oppname{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.maps{display:flex;gap:5px;flex-wrap:nowrap;flex:1;justify-content:flex-end}
@media(max-width:600px){.maps{flex-wrap:wrap}}
.mtag{font-size:10.5px;font-family:'JetBrains Mono',monospace;color:var(--fg-2,#94a3b8);background:#0e1420;border:1px solid var(--border,#2b3445);border-radius:5px;padding:1px 6px;white-space:nowrap;flex:none}
.mtag.mw{border-color:rgba(34,197,94,.3);color:#86efac} .mtag.ml{border-color:rgba(239,68,68,.3);color:#fca5a5}
.mtag b{font-weight:700}
.mdate{font-size:11px;color:var(--fg-3,#64748b);flex:none}

.mapcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.mapcard{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:12px;padding:14px}
.mc-name{font-family:'JetBrains Mono',monospace;font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border,#2b3445)}
.mc-row{display:flex;justify-content:space-between;gap:8px;font-size:12px;padding:4px 0;color:var(--fg-2,#94a3b8);white-space:nowrap}
.mc-row>span{flex:none}
.mc-row b{color:var(--fg,#e8edf5);font-family:'JetBrains Mono',monospace;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right}
.mc-row b i{font-style:normal;color:var(--fg-3,#64748b);font-size:11px;font-family:inherit}
.good{color:var(--win,#22c55e)!important} .bad{color:var(--loss,#ef4444)!important}

.statwrap{overflow-x:auto;background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:12px}
table.stat{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;min-width:640px}
table.stat th{font-family:inherit;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--fg-3,#64748b);padding:11px 8px;text-align:center;border-bottom:1px solid var(--border,#2b3445)}
table.stat th.lft,table.stat td.lft{text-align:left;padding-left:16px}
table.stat td{padding:10px 8px;text-align:center;font-size:13px;border-bottom:1px solid rgba(43,52,69,.5)}
table.stat tbody tr:last-child td{border-bottom:none}
table.stat td.hl{color:var(--accent,#14e6c0);font-weight:700}
/* color-keyed columns echoing the big4 palette */
.ya{color:#fbbf24} .ra{color:#f87171} .mh{color:#93c5fd} .sg{color:#a3e635}
.lg{color:#e8edf5} .rl{color:#f59e0b} .q{color:#c084fc}
thead .ya,thead .ra,thead .mh,thead .sg,thead .lg,thead .rl,thead .q{opacity:.85}
</style>

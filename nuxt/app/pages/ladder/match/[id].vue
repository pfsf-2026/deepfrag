<script setup>
// KOTH 2v2 ladder — MATCH PREVIEW (ESPN-gamecast layout: left/right rails + center
// editorial). id = challenge id. Reads /api/ladder/challenge/{id}/preview: prediction
// (2v2-ladder-based) + LLM article + both team summaries. All real data.
const route = useRoute()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const id = computed(() => parseInt(route.params.id))
const d = ref(null)
const meetingEnh = ref([])
const loading = ref(true)
const err = ref(null)

function logoUrl(tid) { return `${base}/api/ladder/team/${tid}/logo` }
function fmtWhen(s) {
  if (!s) return 'time TBD'
  try { return new Date(s).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return 'time TBD' }
}
function ml(n) { return n > 0 ? `+${n}` : `${n}` }

async function load() {
  loading.value = true; err.value = null
  try { d.value = await $fetch(`${base}/api/ladder/challenge/${id.value}/preview`, { query: { _: Date.now() } }) }
  catch (e) { err.value = 'Could not load this preview.'; console.error('[preview]', e) }
  finally { loading.value = false }
  // enhanced stats for the prior meeting (if these teams have played)
  try {
    const mt = (d.value?.challenger?.matches || []).find(m => m.opponent_id === d.value?.defender?.team?.id)
    meetingEnh.value = mt ? ((await $fetch(`${base}/api/ladder/match/${mt.id}/enhanced`)).players || []) : []
  } catch { meetingEnh.value = [] }
}
onMounted(load)
watch(() => route.params.id, load)

const A = computed(() => d.value?.challenger)
const B = computed(() => d.value?.defender)
const P = computed(() => d.value?.prediction)
const probA = computed(() => Math.round((P.value?.win_prob_challenger || 0) * 100))
const probB = computed(() => Math.round((P.value?.win_prob_defender || 0) * 100))
const pickIsA = computed(() => P.value?.pick === 'challenger')
const pickPct = computed(() => Math.max(probA.value, probB.value))
const h2h = computed(() => P.value?.h2h || {})
const meeting = computed(() => (A.value?.matches || []).find(m => m.opponent_id === B.value?.team?.id))
function topPlayer(s) { return (s?.players || []).slice().sort((x, y) => (y.frags ?? 0) - (x.frags ?? 0))[0] }
function formOf(s) { return (s?.matches || []).slice(0, 5).map(m => (m.won ? 'W' : 'L')) }
const allPlayers = computed(() => {
  const tag = (s, t, id) => (s?.players || []).map(p => ({ ...p, _tag: t, _id: id }))
  return [...tag(A.value, A.value?.team?.tag, A.value?.team?.id), ...tag(B.value, B.value?.team?.tag, B.value?.team?.id)]
    .sort((x, y) => (y.frags ?? 0) - (x.frags ?? 0))
})
const tape = computed(() => {
  const a = A.value?.team_stats || {}, b = B.value?.team_stats || {}
  const row = (label, av, bv, lowerBetter = false) => {
    const max = Math.max(av || 0, bv || 0) || 1
    const aLead = lowerBetter ? (av <= bv) : (av >= bv)
    return { label, av, bv, aw: Math.round(60 * (av || 0) / max), bw: Math.round(60 * (bv || 0) / max), aLead, bLead: !aLead }
  }
  if (!a.maps && !b.maps) return []
  return [
    row('Efficiency', a.eff, b.eff), row('Frags / map', a.frags, b.frags),
    row('Deaths / map', a.deaths, b.deaths, true), row('LG accuracy', a.lg, b.lg),
    row('RL direct hits / map', a.rl, b.rl),
  ]
})
const donutStyle = computed(() => ({
  background: `conic-gradient(var(--accent) 0 ${pickPct.value}%, #2a2330 ${pickPct.value}% 100%)`,
}))
function mdToHtml(s) {
  if (!s) return ''
  const esc = t => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return s.split(/\n\n+/).map(p => '<p>' + esc(p).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>') + '</p>').join('')
}
const articleHtml = computed(() => mdToHtml(d.value?.preview_article || ''))
useHead(() => ({ title: A.value ? `${A.value.team.name} vs ${B.value.team.name} · Preview · DeepFrag` : 'Match Preview · DeepFrag' }))
</script>

<template>
<div class="preview">
  <NuxtLink class="back" to="/ladder#schedule">← back to schedule</NuxtLink>

  <div v-if="loading" class="state">Loading preview…</div>
  <div v-else-if="err" class="state err">{{ err }}</div>
  <template v-else-if="A && B && P">

    <!-- MATCH HEADER -->
    <div class="matchbar">
      <NuxtLink class="team away" :to="`/ladder/team/${A.team.id}`">
        <div class="ti">
          <div class="trung">RUNG {{ A.team.rung }} · CHALLENGER</div>
          <div class="tname a">{{ A.team.name }}</div>
          <div class="trec">{{ (A.team.members||[]).map(m=>m.display).join(' · ') }} · {{ A.team.match_w }}–{{ A.team.match_l }}</div>
        </div>
        <img v-if="A.team.has_logo" :src="logoUrl(A.team.id)" class="crest" alt=""><div v-else class="crest ph">{{ A.team.tag }}</div>
      </NuxtLink>
      <div class="center">
        <div class="time">{{ fmtWhen(d.challenge.agreed_at) }}</div>
        <div class="pill-line"><span class="pill">Bo3 · KOTH 2v2</span><span class="pill stake">⚔ winner takes rung {{ B.team.rung }}</span></div>
        <div v-if="h2h.played" class="rematch">⟲ rematch — H2H maps {{ h2h.maps_a }}–{{ h2h.maps_b }}</div>
      </div>
      <NuxtLink class="team home" :to="`/ladder/team/${B.team.id}`">
        <img v-if="B.team.has_logo" :src="logoUrl(B.team.id)" class="crest" alt=""><div v-else class="crest ph">{{ B.team.tag }}</div>
        <div class="ti">
          <div class="trung">RUNG {{ B.team.rung }} · DEFENDER</div>
          <div class="tname b">{{ B.team.name }}</div>
          <div class="trec">{{ (B.team.members||[]).map(m=>m.display).join(' · ') }} · {{ B.team.match_w }}–{{ B.team.match_l }}</div>
        </div>
      </NuxtLink>
    </div>

    <div class="grid">
      <!-- LEFT RAIL -->
      <div class="col rail">
        <div class="card">
          <div class="card-h"><h3>Match Odds</h3><span class="brand">DeepFrag Book</span></div>
          <table class="odds">
            <thead><tr><th>Team</th><th>Win</th><th>Total</th></tr></thead>
            <tbody>
              <tr><td class="t a">{{ A.team.tag }}</td><td><span class="bk">{{ ml(P.moneyline_challenger) }}</span></td><td rowspan="2" class="ou">o/u<br><b>{{ P.total_frags_line }}</b><br><span class="muted xs">frags</span></td></tr>
              <tr><td class="t b">{{ B.team.tag }}</td><td><span class="bk">{{ ml(P.moneyline_defender) }}</span></td></tr>
            </tbody>
          </table>
          <div class="for-fun">for fun · ~{{ P.expected_maps }} maps projected</div>
        </div>

        <div class="card">
          <div class="card-h"><h3>Matchup Predictor</h3></div>
          <div class="card-b donut-wrap">
            <div class="donut" :style="donutStyle"><div class="inner"><div class="big">{{ pickPct }}<span>%</span></div><div class="lbl">{{ P.pick_name }}</div></div></div>
            <div class="dleg">
              <span><i class="sw a"></i>{{ A.team.tag }} {{ probA }}%</span>
              <span><i class="sw track"></i>{{ B.team.tag }} {{ probB }}%</span>
            </div>
            <div class="muted xs cf">confidence: {{ P.confidence }} · from 2v2 ladder results</div>
          </div>
        </div>

        <div class="card">
          <div class="card-h"><h3>The Pick</h3></div>
          <div class="card-b pick">
            <div class="pickteam" :class="pickIsA ? 'a' : 'b'">{{ P.pick_name }}</div>
            <div class="muted small">to win outright ({{ pickIsA ? ml(P.moneyline_challenger) : ml(P.moneyline_defender) }})</div>
          </div>
        </div>
      </div>

      <!-- CENTER -->
      <div class="col">
        <div class="card" v-if="d.preview_article">
          <div class="card-b article"><div v-html="articleHtml"></div>
            <div class="byline">generated by DeepFrag Predictor from live 2v2 ladder data</div>
          </div>
        </div>

        <div class="card">
          <div class="card-h"><h3>Players to Watch</h3><span class="brand">top fragger · each side</span></div>
          <div class="card-b">
            <div class="pp">
              <div class="side"><div class="av a">{{ (topPlayer(A)?.name||'?')[0] }}</div><div class="nm">{{ topPlayer(A)?.name }}</div><div class="meta">{{ A.team.tag }}</div></div>
              <div class="vs">vs</div>
              <div class="side"><div class="av b">{{ (topPlayer(B)?.name||'?')[0] }}</div><div class="nm">{{ topPlayer(B)?.name }}</div><div class="meta">{{ B.team.tag }}</div></div>
            </div>
            <table class="stat">
              <thead><tr><th>Player</th><th>Eff</th><th>Frags</th><th title="RL direct hits / map">RLd</th></tr></thead>
              <tbody>
                <tr><td class="nmc a">{{ topPlayer(A)?.name }}</td><td>{{ topPlayer(A)?.eff }}%</td><td>{{ topPlayer(A)?.frags }}</td><td>{{ topPlayer(A)?.rl }}</td></tr>
                <tr><td class="nmc b">{{ topPlayer(B)?.name }}</td><td>{{ topPlayer(B)?.eff }}%</td><td>{{ topPlayer(B)?.frags }}</td><td>{{ topPlayer(B)?.rl }}</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card" v-if="meeting">
          <div class="card-h"><h3>The {{ (h2h.maps_a + h2h.maps_b) > 3 ? 'Last' : 'Only' }} Meeting</h3>
            <span class="brand">{{ meeting.won ? A.team.name : B.team.name }} {{ Math.max(meeting.our_score,meeting.their_score) }}–{{ Math.min(meeting.our_score,meeting.their_score) }}</span></div>
          <div class="card-b">
            <div v-for="(mp,i) in meeting.maps" :key="i" class="maprow">
              <span class="mn">{{ mp.map }}</span>
              <span class="split"><span class="sa" :style="{ width: (100*(mp.our_frags||0)/Math.max(1,(mp.our_frags||0)+(mp.their_frags||0)))+'%' }"></span></span>
              <span class="sc"><span class="a">{{ mp.our_frags }}</span>–<span class="b">{{ mp.their_frags }}</span>
                <span class="w" :class="mp.our_frags>mp.their_frags?'sa':'sb'">{{ mp.our_frags>mp.their_frags?A.team.tag:B.team.tag }}</span></span>
            </div>
            <table v-if="meetingEnh.length" class="meet-enh">
              <thead><tr><th class="l">From that match</th><th>Dmg</th><th>+/–</th><th title="line-of-sight to first hit">Spot→Fire</th><th title="rockets that hit">Rkts</th></tr></thead>
              <tbody>
                <tr v-for="p in meetingEnh" :key="p.canonical_id">
                  <td class="l">{{ p.name }} <span class="tt" :class="p.team===A.team.tag?'a':'b'">{{ p.team }}</span></td>
                  <td>{{ p.damage>=1000?(p.damage/1000).toFixed(1)+'k':p.damage }}</td>
                  <td>{{ p.frag_diff>=0?'+':'' }}{{ p.frag_diff }}</td>
                  <td>{{ p.react_ms!=null?p.react_ms+'ms':'—' }}</td>
                  <td>{{ p.rockets_dmg }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- RIGHT RAIL -->
      <div class="col rail">
        <div class="card">
          <div class="card-h"><h3>Predicted First Picks</h3></div>
          <div class="card-b">
            <div class="fprow"><span class="who a">{{ A.team.tag }} ▸</span><span class="map">{{ P.first_pick_challenger || '—' }}</span></div>
            <div class="fprow"><span class="who b">{{ B.team.tag }} ▸</span><span class="map">{{ P.first_pick_defender || '—' }}</span></div>
            <div class="muted xs" style="margin-top:8px">each team's strongest map</div>
          </div>
        </div>

        <div class="card">
          <div class="card-h"><h3>Recent Form</h3></div>
          <div class="card-b">
            <div class="formrow"><span class="ft a">{{ A.team.tag }}</span><span class="wls"><i v-for="(r,i) in formOf(A)" :key="i" class="wl" :class="r==='W'?'w':'l'">{{ r }}</i><span v-if="!formOf(A).length" class="muted xs">no games</span></span></div>
            <div class="formrow"><span class="ft b">{{ B.team.tag }}</span><span class="wls"><i v-for="(r,i) in formOf(B)" :key="i" class="wl" :class="r==='W'?'w':'l'">{{ r }}</i><span v-if="!formOf(B).length" class="muted xs">no games</span></span></div>
          </div>
        </div>

        <div class="card">
          <div class="card-h"><h3>Series History</h3></div>
          <div class="card-b center-b">
            <template v-if="h2h.played">
              <div class="big2">{{ h2h.maps_a }}–{{ h2h.maps_b }}</div>
              <div class="muted small">maps · {{ A.team.tag }} vs {{ B.team.tag }}</div>
              <div class="muted xs" style="margin-top:6px">series frags {{ h2h.frags_a }}–{{ h2h.frags_b }}</div>
            </template>
            <template v-else><div class="big2" style="font-size:18px">First meeting</div><div class="muted small">no prior games on record</div></template>
          </div>
        </div>
      </div>
    </div>

    <!-- FULL-WIDTH: tale of the tape + players -->
    <div class="wide" v-if="tape.length">
      <div class="card">
        <div class="card-h"><h3>Tale of the Tape</h3><span class="brand">team avg / map</span></div>
        <div class="card-b">
          <div class="tcols"><span class="l a">{{ A.team.name }}</span><span class="c"></span><span class="r b">{{ B.team.name }}</span></div>
          <div v-for="t in tape" :key="t.label" class="trow">
            <span class="vv l"><span :class="{lead:t.aLead}">{{ t.av }}</span><i class="bar a" :style="{width:t.aw+'px'}"></i></span>
            <span class="lbl">{{ t.label }}</span>
            <span class="vv r"><i class="bar b" :style="{width:t.bw+'px'}"></i><span :class="{lead:t.bLead}">{{ t.bv }}</span></span>
          </div>
        </div>
      </div>
    </div>

    <div class="wide" v-if="allPlayers.length">
      <div class="card">
        <div class="card-h"><h3>Players</h3><span class="brand">per map</span></div>
        <table class="stat full">
          <thead><tr><th class="lft">Player</th><th>Team</th><th>Eff</th><th>Frags</th><th title="RL direct hits / map">RLd</th></tr></thead>
          <tbody>
            <tr v-for="p in allPlayers" :key="p.canonical_id">
              <td class="lft"><NuxtLink class="plink" :to="`/p/${p.canonical_id}`">{{ p.name }}</NuxtLink></td>
              <td><span class="tt" :class="p._id===A.team.id?'a':'b'">{{ p._tag }}</span></td>
              <td>{{ p.eff }}%</td><td>{{ p.frags }}</td><td>{{ p.rl }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="note">Predictions use <b>2v2 ladder results</b> (head-to-head, maps won, series frag share, team stats) — not 1v1 ratings. With little data the model stays humble; moneyline / total / first-picks are illustrative.</div>
  </template>
</div>
</template>

<style scoped>
.preview{max-width:1180px;margin:0 auto;padding:6px 16px 60px;color:var(--fg,#e8edf5)}
.back{display:inline-block;margin:14px 0 10px;font-size:13px;color:var(--accent,#14e6c0);text-decoration:none}
.state{padding:40px;text-align:center;color:var(--fg-2,#94a3b8)} .state.err{color:var(--loss,#ef4444)}
.muted{color:var(--fg-2,#94a3b8)} .xs{font-size:11px} .small{font-size:12px}
.a{color:var(--accent,#14e6c0)} .b{color:var(--draw,#f59e0b)}

/* header */
.matchbar{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:14px;background:linear-gradient(180deg,#10151d,#0c1016);border:1px solid var(--border,#2b3445);border-radius:14px;padding:16px 18px}
.team{display:flex;align-items:center;gap:13px;text-decoration:none;color:var(--fg,#e8edf5);min-width:0}
.team.away{justify-content:flex-end;text-align:right} .team.home{justify-content:flex-start}
.team:hover .tname{text-decoration:underline}
.crest{width:54px;height:54px;border-radius:12px;object-fit:cover;border:1px solid var(--border-2,#3a4458);flex:none;background:#0c1016}
.crest.ph{display:grid;place-items:center;font-family:'JetBrains Mono',monospace;font-weight:800;font-size:16px}
.trung{font-size:10px;font-weight:800;letter-spacing:.06em;color:var(--fg-3,#64748b)}
.tname{font-size:19px;font-weight:800;line-height:1.1;margin:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tname.a{color:var(--accent,#14e6c0)} .tname.b{color:var(--draw,#f59e0b)}
.trec{font-size:11.5px;color:var(--fg-2,#94a3b8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.center{text-align:center;min-width:170px}
.center .time{font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700}
.pill-line{display:flex;gap:5px;justify-content:center;flex-wrap:wrap;margin-top:6px}
.pill{font-size:10.5px;border:1px solid var(--border-2,#3a4458);border-radius:999px;padding:2px 8px;color:var(--fg-2,#94a3b8)}
.pill.stake{color:var(--draw,#f59e0b);border-color:#f59e0b55}
.rematch{font-size:11px;color:var(--fg-3,#64748b);margin-top:7px}

/* grid */
.grid{display:grid;grid-template-columns:280px 1fr 280px;gap:16px;margin-top:16px}
.col{display:flex;flex-direction:column;gap:16px;min-width:0}
@media(max-width:980px){.grid{grid-template-columns:1fr}.col.rail{order:2}}
.card{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:12px;overflow:hidden}
.card-h{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;border-bottom:1px solid var(--border,#2b3445)}
.card-h h3{margin:0;font-size:12.5px;font-weight:800}
.brand{font-size:10px;color:var(--fg-3,#64748b)}
.card-b{padding:14px}
.center-b{text-align:center}

/* odds */
.odds{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace}
.odds th{font-family:inherit;font-size:9.5px;color:var(--fg-3,#64748b);text-transform:uppercase;padding:8px 6px;font-weight:600;text-align:center}
.odds td{padding:8px 6px;text-align:center;border-top:1px solid var(--border,#2b3445);font-size:13px}
.odds td.t{text-align:left;font-family:inherit;font-weight:700} .odds td.t.a{color:var(--accent,#14e6c0)} .odds td.t.b{color:var(--draw,#f59e0b)}
.bk{border:1px solid var(--border-2,#3a4458);border-radius:6px;padding:3px 8px;display:inline-block;color:var(--fg,#e8edf5)}
.ou{vertical-align:middle;line-height:1.3} .ou b{font-size:16px}
.for-fun{font-size:10px;color:var(--fg-3,#64748b);text-align:center;padding:8px;border-top:1px solid var(--border,#2b3445)}

/* donut */
.donut-wrap{display:flex;flex-direction:column;align-items:center;gap:8px}
.donut{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;position:relative}
.donut::after{content:"";position:absolute;width:104px;height:104px;border-radius:50%;background:var(--panel,#131820)}
.donut .inner{position:relative;z-index:2;text-align:center}
.donut .big{font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:800;line-height:1}.donut .big span{font-size:14px}
.donut .lbl{font-size:10.5px;color:var(--fg-2,#94a3b8);margin-top:3px;max-width:120px}
.dleg{display:flex;justify-content:space-between;width:100%;font-size:11.5px;font-family:'JetBrains Mono',monospace}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}
.sw.a{background:var(--accent,#14e6c0)} .sw.track{background:#2a2330}
.cf{text-align:center;margin-top:2px}

/* pick */
.pick{text-align:center}
.pickteam{font-size:18px;font-weight:800}.pickteam.a{color:var(--accent,#14e6c0)}.pickteam.b{color:var(--draw,#f59e0b)}

/* article */
.article :deep(p){margin:0 0 12px;color:#cfd8e6;line-height:1.6}
.article :deep(p:first-child){font-size:15px}
.article :deep(strong){color:var(--fg,#e8edf5)}
.article .byline{font-size:11px;color:var(--fg-3,#64748b);margin-top:6px}

/* players to watch */
.pp{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;padding:2px 0 12px}
.pp .side{display:flex;flex-direction:column;align-items:center;gap:5px}
.av{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;font-family:'JetBrains Mono',monospace;font-weight:800;font-size:16px;border:1px solid var(--border-2,#3a4458);text-transform:uppercase}
.av.a{background:#10302b;color:var(--accent,#14e6c0)} .av.b{background:#2e2410;color:var(--draw,#f59e0b)}
.pp .nm{font-weight:700;font-size:13px}.pp .meta{font-size:10.5px;color:var(--fg-3,#64748b)}
.vs{font-family:'JetBrains Mono',monospace;color:var(--fg-3,#64748b);font-size:12px}
.stat{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace}
.stat th{font-family:inherit;font-size:9.5px;color:var(--fg-3,#64748b);text-transform:uppercase;padding:7px 6px;font-weight:600;text-align:center;border-bottom:1px solid var(--border,#2b3445)}
.stat td{padding:8px 6px;text-align:center;font-size:12.5px;border-top:1px solid rgba(43,52,69,.5)}
.stat td.nmc{text-align:left;font-weight:700;font-family:inherit} .stat td.nmc.a{color:var(--accent,#14e6c0)} .stat td.nmc.b{color:var(--draw,#f59e0b)}
.stat.full td.lft,.stat.full th.lft{text-align:left;padding-left:14px}
.plink{color:var(--fg,#e8edf5);text-decoration:none}.plink:hover{color:var(--accent,#14e6c0)}
.tt{font-size:9.5px;font-weight:800;padding:1px 5px;border-radius:4px}.tt.a{background:#14e6c022;color:var(--accent,#14e6c0)}.tt.b{background:#f59e0b22;color:var(--draw,#f59e0b)}

/* meeting enhanced mini-table */
.meet-enh{width:100%;border-collapse:collapse;margin-top:10px;border-top:1px solid var(--border,#2b3445);font-family:'JetBrains Mono',monospace}
.meet-enh th{font-family:inherit;font-size:9px;text-transform:uppercase;letter-spacing:.04em;color:var(--fg-3,#64748b);font-weight:600;text-align:center;padding:8px 5px}
.meet-enh th.l,.meet-enh td.l{text-align:left;font-family:-apple-system,sans-serif}
.meet-enh td{padding:6px 5px;text-align:center;font-size:12px;border-top:1px solid rgba(43,52,69,.4)}

/* meeting maps */
.maprow{display:grid;grid-template-columns:74px 1fr auto;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--border,#2b3445)}
.maprow:first-child{border-top:none}
.mn{font-family:'JetBrains Mono',monospace;font-size:12.5px;text-transform:uppercase}
.split{height:9px;border-radius:5px;overflow:hidden;background:#f59e0b55}.split .sa{display:block;height:100%;background:var(--accent,#14e6c0)}
.sc{font-family:'JetBrains Mono',monospace;font-weight:700;font-size:12.5px}.sc .a{color:var(--accent,#14e6c0)}.sc .b{color:var(--draw,#f59e0b)}
.sc .w{font-size:9.5px;font-weight:800;padding:1px 5px;border-radius:4px;margin-left:7px}.sc .w.sa{background:#14e6c022;color:var(--accent,#14e6c0)}.sc .w.sb{background:#f59e0b22;color:var(--draw,#f59e0b)}

/* first picks */
.fprow{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-top:1px solid var(--border,#2b3445);font-family:'JetBrains Mono',monospace}
.fprow:first-child{border-top:none}.fprow .who{font-size:11px;font-weight:700}.fprow .who.a{color:var(--accent,#14e6c0)}.fprow .who.b{color:var(--draw,#f59e0b)}
.fprow .map{font-weight:800;font-size:14px;text-transform:uppercase}

/* form */
.formrow{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border,#2b3445)}
.formrow:first-child{border-top:none}
.ft{font-weight:800;font-size:12px}.ft.a{color:var(--accent,#14e6c0)}.ft.b{color:var(--draw,#f59e0b)}
.wls{display:flex;gap:4px}
.wl{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:800}
.wl.w{background:rgba(34,197,94,.15);color:var(--win,#22c55e)}.wl.l{background:rgba(239,68,68,.15);color:var(--loss,#ef4444)}
.big2{font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:800}

/* full-width tape + players */
.wide{margin-top:16px}
.tcols{display:grid;grid-template-columns:1fr 150px 1fr;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;padding-bottom:8px;border-bottom:1px solid var(--border,#2b3445);margin-bottom:4px}
.tcols .l{text-align:right}.tcols .c{text-align:center}
.trow{display:grid;grid-template-columns:1fr 150px 1fr;align-items:center;padding:8px 0;border-top:1px solid rgba(43,52,69,.5)}
.trow:first-of-type{border-top:none}
.lbl{text-align:center;font-size:10.5px;text-transform:uppercase;color:var(--fg-3,#64748b)}
.vv{font-family:'JetBrains Mono',monospace;font-weight:700;font-size:14px;color:var(--fg-2,#94a3b8);display:flex;align-items:center;gap:8px}
.vv.l{justify-content:flex-end}.vv.r{justify-content:flex-start}
.vv .bar{height:6px;border-radius:4px}.vv.l .bar.a{background:var(--accent,#14e6c0)}.vv.r .bar.b{background:var(--draw,#f59e0b)}
.lead{color:var(--win,#22c55e)}
.note{background:var(--panel-2,#1a2433);border:1px solid var(--border,#2b3445);border-left:3px solid var(--accent,#14e6c0);border-radius:10px;padding:12px 14px;color:var(--fg-2,#94a3b8);font-size:12px;margin-top:16px}
.note b{color:var(--fg,#e8edf5)}
</style>

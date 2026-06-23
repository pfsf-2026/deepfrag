<script setup>
// KOTH 2v2 ladder — MATCH PREVIEW for a scheduled/open challenge (id = challenge id).
// Reads /api/ladder/challenge/{id}/preview: prediction (2v2-ladder-based, not 1v1
// ratings) + both team summaries for tale-of-the-tape + players.
const route = useRoute()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const id = computed(() => parseInt(route.params.id))
const d = ref(null)
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
}
onMounted(load)
watch(() => route.params.id, load)

const A = computed(() => d.value?.challenger)        // challenger
const B = computed(() => d.value?.defender)          // defender
const P = computed(() => d.value?.prediction)
const probA = computed(() => Math.round((P.value?.win_prob_challenger || 0) * 100))
const probB = computed(() => Math.round((P.value?.win_prob_defender || 0) * 100))
const pickIsA = computed(() => P.value?.pick === 'challenger')
const h2h = computed(() => P.value?.h2h || {})
const meeting = computed(() => (A.value?.matches || []).find(m => m.opponent_id === B.value?.team?.id))
// merged player table, sorted by frags
const allPlayers = computed(() => {
  const tag = (s, t) => (s?.players || []).map(p => ({ ...p, _tag: t, _id: s.team.id }))
  return [...tag(A.value, A.value?.team?.tag), ...tag(B.value, B.value?.team?.tag)]
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
// preview article: render \n\n paragraphs + **bold** (escaped) to safe HTML
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
    <!-- HEAD -->
    <div class="head">
      <div class="ctx">KOTH 2v2 · Challenge #{{ d.challenge.id }} · Best of 3</div>
      <div class="matchup">
        <NuxtLink class="a" :to="`/ladder/team/${A.team.id}`">{{ A.team.name }}</NuxtLink>
        <span class="v">vs</span>
        <NuxtLink class="b" :to="`/ladder/team/${B.team.id}`">{{ B.team.name }}</NuxtLink>
      </div>
      <div class="when">{{ fmtWhen(d.challenge.agreed_at) }} · winner takes rung {{ B.team.rung }}</div>
      <div v-if="h2h.played" class="rematch">⟲ Rematch — they've met: maps {{ h2h.maps_a }}–{{ h2h.maps_b }}</div>
    </div>

    <!-- VERDICT -->
    <div class="verdict">
      <div class="vtitle"><span>The Pick</span>
        <span class="conf">Confidence: {{ (P.confidence || '').toUpperCase() }}<template v-if="h2h.played"> · {{ h2h.maps_a + h2h.maps_b }} prior maps</template></span>
      </div>
      <div class="probbar">
        <div class="p a" :style="{ width: probA + '%' }">{{ A.team.tag }} {{ probA }}%</div>
        <div class="p b" :style="{ width: probB + '%' }">{{ probB }}% {{ B.team.tag }}</div>
      </div>
      <div class="say">
        <b>{{ P.pick_name }}</b> is the pick at <b>{{ pickIsA ? probA : probB }}%</b> — confidence {{ P.confidence }}.
        <template v-if="h2h.played"> These two have played: the head-to-head sits <b>{{ h2h.maps_a }}–{{ h2h.maps_b }}</b> on maps ({{ h2h.frags_a }}–{{ h2h.frags_b }} frags). </template>
        <template v-else> No prior meeting — the lean is from team form, so treat it lightly. </template>
        Built from <b>2v2 ladder results</b>, not 1v1 ratings.
      </div>
    </div>

    <!-- BETTING STRIP -->
    <div class="bet">
      <div class="betbox">
        <div class="k">Win Outright (Moneyline)</div>
        <div class="mlrow">
          <div class="side"><span class="nm a">{{ A.team.tag }}<span v-if="pickIsA"> ✓</span></span><span class="od a">{{ ml(P.moneyline_challenger) }}</span><span class="pk">{{ pickIsA ? 'THE PICK' : ' ' }}</span></div>
          <div class="side"><span class="nm b">{{ B.team.tag }}<span v-if="!pickIsA"> ✓</span></span><span class="od b">{{ ml(P.moneyline_defender) }}</span><span class="pk">{{ !pickIsA ? 'THE PICK' : ' ' }}</span></div>
        </div>
      </div>
      <div class="betbox">
        <div class="k">Total Frags (series)</div>
        <div class="ouval">O/U {{ P.total_frags_line }}</div>
        <div class="ousub" v-if="h2h.played">last meeting {{ h2h.frags_a + h2h.frags_b }} · ~{{ P.expected_maps }} maps proj.</div>
        <div class="ousub" v-else>~{{ P.expected_maps }} maps projected</div>
      </div>
      <div class="betbox">
        <div class="k">Predicted First Pick</div>
        <div class="fprow">
          <div class="pkk"><div class="who a">{{ A.team.tag }} ▸</div><div class="mp">{{ P.first_pick_challenger || '—' }}</div></div>
          <div class="pkk"><div class="who b">{{ B.team.tag }} ▸</div><div class="mp">{{ P.first_pick_defender || '—' }}</div></div>
        </div>
        <div class="ousub">each team's strongest map</div>
      </div>
    </div>

    <!-- PREVIEW ARTICLE -->
    <template v-if="d.preview_article">
      <div class="h2">The Preview</div>
      <div class="article" v-html="articleHtml"></div>
    </template>

    <!-- THE MEETING -->
    <template v-if="meeting">
      <div class="h2">The {{ h2h.maps_a + h2h.maps_b > 3 ? 'Last' : 'Only' }} Meeting</div>
      <div class="series">
        <div class="series-h">
          <span class="res">{{ meeting.won ? A.team.name : B.team.name }} def. {{ meeting.won ? B.team.name : A.team.name }} <b>{{ Math.max(meeting.our_score, meeting.their_score) }}–{{ Math.min(meeting.our_score, meeting.their_score) }}</b></span>
        </div>
        <div v-for="(mp, i) in meeting.maps" :key="i" class="maprow">
          <span class="mn">{{ mp.map }}</span>
          <span class="split"><span class="sa" :style="{ width: (100 * (mp.our_frags || 0) / Math.max(1, (mp.our_frags || 0) + (mp.their_frags || 0))) + '%' }"></span></span>
          <span class="sc"><span class="a">{{ mp.our_frags }}</span>–<span class="b">{{ mp.their_frags }}</span>
            <span class="winner" :class="mp.our_frags > mp.their_frags ? 's' : 'w'">{{ mp.our_frags > mp.their_frags ? A.team.tag : B.team.tag }}</span></span>
        </div>
      </div>
    </template>

    <!-- TALE OF THE TAPE -->
    <template v-if="tape.length">
      <div class="h2">Tale of the Tape <span class="dim">— team average per map</span></div>
      <div class="tape">
        <div class="tcols"><div class="l">{{ A.team.name }}</div><div class="c"></div><div class="r">{{ B.team.name }}</div></div>
        <div v-for="t in tape" :key="t.label" class="trow">
          <div class="vv l"><span :class="{ lead: t.aLead }">{{ t.av }}</span><span class="bar a" :style="{ width: t.aw + 'px' }"></span></div>
          <div class="lbl">{{ t.label }}</div>
          <div class="vv r"><span class="bar b" :style="{ width: t.bw + 'px' }"></span><span :class="{ lead: t.bLead }">{{ t.bv }}</span></div>
        </div>
      </div>
    </template>

    <!-- PLAYERS -->
    <template v-if="allPlayers.length">
      <div class="h2">Players <span class="dim">— per map</span></div>
      <table class="ptab">
        <thead><tr><th class="l">Player</th><th>Eff</th><th>Frags</th><th title="RL direct hits / map">RLd</th></tr></thead>
        <tbody>
          <tr v-for="p in allPlayers" :key="p.canonical_id">
            <td class="l"><NuxtLink class="plink" :to="`/p/${p.canonical_id}`">{{ p.name }}</NuxtLink>
              <span class="tt" :class="p._id === A.team.id ? 'a' : 'b'">{{ p._tag }}</span></td>
            <td>{{ p.eff }}%</td><td>{{ p.frags }}</td><td>{{ p.rl }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <div class="note"><b>Methodology:</b> predictions use <b>2v2 ladder results</b> (head-to-head outcome, maps won, series frag share, team stats) — not 1v1 ratings. With little data the model stays humble: small lean, explicit confidence flag, clamped to 15–85%. Moneyline / total / first-pick are illustrative, for fun.</div>
  </template>
</div>
</template>

<style scoped>
.preview{max-width:860px;margin:0 auto;padding:6px 16px 60px;color:var(--fg,#e8edf5)}
.back{display:inline-block;margin:14px 0 4px;font-size:13px;color:var(--accent,#14e6c0);text-decoration:none}
.state{padding:40px;text-align:center;color:var(--fg-2,#94a3b8)} .state.err{color:var(--loss,#ef4444)}
.dim{color:var(--fg-3,#64748b);font-weight:400;text-transform:none}
.mono{font-family:'JetBrains Mono',monospace}
:root{}
.a{color:var(--accent,#14e6c0)} .b{color:var(--draw,#f59e0b)}

.head{text-align:center;padding:8px 0 10px}
.head .ctx{font-size:11px;font-weight:700;letter-spacing:.1em;color:var(--draw,#f59e0b);text-transform:uppercase}
.head .matchup{font-size:23px;font-weight:800;margin:8px 0 2px}
.head .matchup a{text-decoration:none} .head .matchup a.a{color:var(--accent,#14e6c0)} .head .matchup a.b{color:var(--draw,#f59e0b)}
.head .matchup .v{color:var(--fg-3,#64748b);margin:0 10px;font-weight:600;font-size:15px}
.head .when{font-size:12.5px;color:var(--fg-2,#94a3b8)}
.rematch{display:inline-block;margin-top:8px;font-size:11px;border:1px solid var(--border-2,#3a4458);border-radius:999px;padding:3px 12px;color:var(--fg-2,#94a3b8)}

.verdict{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:16px;padding:20px;margin-top:14px}
.vtitle{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--fg-3,#64748b);font-weight:700;margin-bottom:12px;display:flex;justify-content:space-between}
.conf{color:var(--draw,#f59e0b)}
.probbar{display:flex;height:46px;border-radius:10px;overflow:hidden;border:1px solid var(--border-2,#3a4458)}
.probbar .p{display:flex;align-items:center;font-family:'JetBrains Mono',monospace;font-weight:800;font-size:15px;padding:0 14px;white-space:nowrap}
.probbar .p.a{background:linear-gradient(90deg,#14e6c022,#14e6c00d);color:var(--accent,#14e6c0)}
.probbar .p.b{background:linear-gradient(270deg,#f59e0b22,#f59e0b0d);color:var(--draw,#f59e0b);justify-content:flex-end}
.say{margin-top:14px;color:#cfd8e6} .say b{color:var(--fg,#e8edf5)}

.bet{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:14px}
@media(max-width:640px){.bet{grid-template-columns:1fr}}
.betbox{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:12px;padding:14px;text-align:center}
.betbox .k{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--fg-3,#64748b)}
.mlrow{display:flex;justify-content:center;gap:16px;margin-top:8px}
.side{display:flex;flex-direction:column}
.nm{font-size:11px;font-weight:700}.nm.a{color:var(--accent,#14e6c0)}.nm.b{color:var(--draw,#f59e0b)}
.od{font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:800}.od.a{color:var(--accent,#14e6c0)}.od.b{color:var(--draw,#f59e0b)}
.pk{font-size:9px;color:var(--draw,#f59e0b);font-weight:800;letter-spacing:.05em;min-height:11px}
.ouval{font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:800;margin-top:6px}
.ousub{font-size:10.5px;color:var(--fg-3,#64748b);margin-top:4px}
.fprow{display:flex;justify-content:center;gap:12px;margin-top:8px}
.pkk{flex:1}.who{font-size:10px;font-weight:700}.who.a{color:var(--accent,#14e6c0)}.who.b{color:var(--draw,#f59e0b)}
.mp{font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:800;margin-top:3px}

.h2{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--fg-2,#94a3b8);margin:26px 2px 10px}
.series{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:14px;overflow:hidden}
.series-h{padding:13px 16px;border-bottom:1px solid var(--border,#2b3445);font-family:'JetBrains Mono',monospace;font-weight:700;font-size:13px}
.maprow{display:grid;grid-template-columns:90px 1fr auto;align-items:center;gap:12px;padding:12px 16px;border-top:1px solid var(--border,#2b3445)}
.mn{font-family:'JetBrains Mono',monospace;font-size:13px;text-transform:uppercase}
.split{height:10px;border-radius:6px;overflow:hidden;background:#f59e0b55}
.split .sa{display:block;height:100%;background:var(--accent,#14e6c0)}
.sc{font-family:'JetBrains Mono',monospace;font-weight:700;font-size:13px}
.sc .a{color:var(--accent,#14e6c0)}.sc .b{color:var(--draw,#f59e0b)}
.winner{font-size:10px;font-weight:800;padding:1px 6px;border-radius:4px;margin-left:8px}
.winner.s{background:#14e6c022;color:var(--accent,#14e6c0)}.winner.w{background:#f59e0b22;color:var(--draw,#f59e0b)}

.tape{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:14px;overflow:hidden}
.tcols{display:grid;grid-template-columns:1fr 130px 1fr;padding:10px 16px;border-bottom:1px solid var(--border,#2b3445);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.05em}
.tcols .l{text-align:right;color:var(--accent,#14e6c0)}.tcols .c{text-align:center}.tcols .r{color:var(--draw,#f59e0b)}
.trow{display:grid;grid-template-columns:1fr 130px 1fr;align-items:center;padding:10px 16px;border-top:1px solid var(--border,#2b3445)}
.lbl{text-align:center;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--fg-3,#64748b)}
.vv{font-family:'JetBrains Mono',monospace;font-weight:700;font-size:15px;color:var(--fg-2,#94a3b8)}
.vv.l{text-align:right}.vv.r{text-align:left}
.vv .bar{display:inline-block;height:6px;border-radius:4px;vertical-align:middle;margin:0 8px}
.vv.l .bar.a{background:var(--accent,#14e6c0)}.vv.r .bar.b{background:var(--draw,#f59e0b)}
.lead{color:var(--win,#22c55e)}

.ptab{width:100%;border-collapse:collapse;background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:14px;overflow:hidden}
.ptab th{font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--fg-3,#64748b);font-weight:700;padding:11px 10px;text-align:center;border-bottom:1px solid var(--border,#2b3445)}
.ptab th.l,.ptab td.l{text-align:left;padding-left:16px}
.ptab td{font-family:'JetBrains Mono',monospace;padding:11px 10px;text-align:center;font-size:13px;border-top:1px solid rgba(43,52,69,.5)}
.ptab td.l{font-family:inherit;font-weight:600}
.plink{color:var(--fg,#e8edf5);text-decoration:none}.plink:hover{color:var(--accent,#14e6c0)}
.tt{font-size:9.5px;font-weight:800;padding:1px 5px;border-radius:4px;margin-left:6px}
.tt.a{background:#14e6c022;color:var(--accent,#14e6c0)}.tt.b{background:#f59e0b22;color:var(--draw,#f59e0b)}
.article{background:var(--panel,#131820);border:1px solid var(--border,#2b3445);border-radius:14px;padding:18px 20px}
.article :deep(p){margin:0 0 12px;color:#cfd8e6;line-height:1.6}
.article :deep(p:last-child){margin-bottom:0}
.article :deep(strong){color:var(--fg,#e8edf5);font-weight:700}
.note{background:var(--panel-2,#1a2433);border:1px solid var(--border,#2b3445);border-left:3px solid var(--accent,#14e6c0);border-radius:10px;padding:13px 15px;color:var(--fg-2,#94a3b8);font-size:12.5px;margin-top:24px}
.note b{color:var(--fg,#e8edf5)}
</style>

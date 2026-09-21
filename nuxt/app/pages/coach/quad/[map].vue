<script setup>
// /coach/quad/{map} — the quad playbook for one map (2026-09-21, Peter): the real ways in,
// which of them converts, what stack the takers bring, and what decides the quad regardless
// of the way in. Words from Peter's map knowledge, numbers from every fours demo in the corpus.
const route = useRoute()
const map = computed(() => String(route.params.map || ''))
const pb = computed(() => quadPlaybook(map.value))
const others = computed(() => COACH_MAPS.filter(m => m !== map.value))
const top = computed(() => QUAD_TOP[map.value] || null)
const topNotes = computed(() => QUAD_TOP_NOTES[map.value] || [])
const topRows = computed(() => {
  if (!top.value) return []
  const pools = Object.entries(top.value.pools).map(([reg, r]) => ({ ...r, player: `everyone else (${reg})`, pool: true }))
  return [...top.value.players, ...pools]
})
function bestEntry(r) { const e = (r.entries || []).filter(x => x.n >= 100).sort((a, b) => b.conv - a.conv)[0]; return e ? `${e.spot} ${Math.round(e.conv)}%` : '—' }
const best = computed(() => (pb.value?.ways || []).filter(w => w.n >= 100).sort((a, b) => (b.conv ?? 0) - (a.conv ?? 0))[0] || null)
function pct(v) { return v == null ? '—' : `${Math.round(v)}%` }
useSeoMeta({ title: () => pb.value ? `${pb.value.title} · AI Coach · DeepFrag` : 'Quad · DeepFrag', description: () => pb.value ? `${pb.value.title}: the ways in, which one converts, and what decides it. From every fours demo on the NA servers.` : '' })
</script>

<template>
  <div class="page">
    <div class="crumbs"><NuxtLink to="/coach" class="back">← AI Coach</NuxtLink><span class="sep">·</span><span class="muted">quad playbooks:</span><NuxtLink v-for="m in COACH_MAPS" :key="m" :to="`/coach/quad/${m}`" class="mlink" :class="{ on: m === map }">{{ m }}</NuxtLink></div>
    <div v-if="!pb" class="empty">No quad playbook for "{{ map }}". Pick a map above.</div>
    <template v-else>
      <h1>{{ pb.title }}</h1>
      <p class="lede">{{ pb.geography }}</p>

      <section v-if="pb.data" class="sec">
        <div class="stitle">What decides the quad here</div>
        <div class="decide">
          <div class="dcard">
            <div class="dlabel">Stack when it spawns</div>
            <div class="rows"><div v-for="b in pb.data.by_eff" :key="b.bucket" class="row"><span class="bl">{{ b.bucket }}</span><span class="bar"><i :style="{ width: Math.min(100, b.conv * 1.5) + '%' }" /></span><span class="bv">{{ pct(b.conv) }}</span></div></div>
            <p class="dnote">Of the players near the quad when it came back, the share who took it, by their <NuxtLink to="/glossary#stack" class="term">stack</NuxtLink> two seconds before. Stack is the whole story: naked players almost never win it.</p>
          </div>
          <div class="dcard">
            <div class="dlabel">Distance two seconds before</div>
            <div class="rows"><div v-for="b in pb.data.by_d2" :key="b.bucket" class="row"><span class="bl">{{ b.bucket }}</span><span class="bar"><i :style="{ width: Math.min(100, b.conv * 1.5) + '%' }" /></span><span class="bv">{{ pct(b.conv) }}</span></div></div>
            <p class="dnote">Being there first matters: the closest player two seconds out takes it <b>{{ pct(pb.data.closest_at_minus2_takes_pct) }}</b> of the time, the most-stacked one <b>{{ pct(pb.data.most_stacked_takes_pct) }}</b>. Distances in <NuxtLink to="/glossary#units" class="term">units</NuxtLink>.</p>
          </div>
        </div>
      </section>

      <section class="sec">
        <div class="stitle">The ways in <span v-if="best" class="muted small">· best converting: {{ best.name.toLowerCase() }}</span></div>
        <div class="ways">
          <article v-for="w in pb.ways" :key="w.name" class="way" :class="{ best: best && w.name === best.name }">
            <div class="whead"><h3>{{ w.name }}</h3><span v-if="w.share != null" class="wshare">{{ w.share }}% of contests</span></div>
            <div v-if="w.n" class="wnums">
              <div class="wn"><b>{{ pct(w.conv) }}</b><span>convert</span></div>
              <div class="wn"><b>{{ w.takerEff ?? '—' }}</b><span>taker's stack</span></div>
              <div class="wn"><b>{{ w.enterS != null ? w.enterS + ' s' : '—' }}</b><span>takers arrive early</span></div>
              <div class="wn"><b>{{ pct(w.diedPre) }}</b><span>die before it spawns</span></div>
            </div>
            <div v-else class="muted small">Not enough demos yet to score this way in.</div>
            <p class="whow">{{ w.how }}</p>
          </article>
        </div>
      </section>

      <p v-if="pb.late && pb.late.n" class="late muted small">Too far to count: players {{ pb.late.note }} were {{ pb.late.share }}% of the contesters and took it <b>{{ pb.late.conv }}%</b> of the time. That is not a way in, that is being late.</p>

      <section v-if="top" class="sec">
        <div class="stitle">What the best players do here <span class="muted small">· the 20 seconds before every quad spawn, from their demos</span></div>
        <ul v-if="topNotes.length" class="notes"><li v-for="(n, i) in topNotes" :key="i" v-html="linkTerms(n)" /></ul>
        <div class="tbl">
          <table>
            <thead><tr><th>player</th><th class="num">games</th><th class="num">takes / game</th><th class="num">convert</th><th class="num">stacked convert</th><th class="num">naked convert</th><th class="num">with RL</th><th class="num">stack 5 s out</th><th class="num">RL in hand</th><th class="num">there 10 s early</th><th>best way in</th></tr></thead>
            <tbody>
              <tr v-for="r in topRows" :key="r.player + r.region" :class="{ pool: r.pool }">
                <td><b>{{ r.player }}</b><span v-if="!r.pool" class="muted small"> · {{ r.region }}</span></td>
                <td class="num">{{ r.games }}</td>
                <td class="num">{{ r.takes_per_game }}</td>
                <td class="num"><b>{{ pct(r.conv_pct) }}</b></td>
                <td class="num">{{ pct(r.conv_150) }}</td>
                <td class="num">{{ pct(r.conv_naked) }}</td>
                <td class="num">{{ pct(r.conv_rl) }}</td>
                <td class="num">{{ r.stack_m5 ?? '—' }}</td>
                <td class="num">{{ pct(r.rl_m5) }}</td>
                <td class="num">{{ pct(r.early10_pct) }}</td>
                <td>{{ bestEntry(r) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="dnote">"Convert" is takes divided by the spawns the player was near. "Stacked" is 150+ <NuxtLink to="/glossary#stack" class="term">stack</NuxtLink> five seconds before the spawn, "naked" under 150. "Best way in" is the spot they entered the 650-unit zone from that converts most for them (100+ times). Stack, RL and arrival are measured on the quads they took.</p>
      </section>

      <section class="sec">
        <div class="stitle">How to play it</div>
        <ol class="play"><li v-for="(p, i) in pb.play" :key="i">{{ p }}</li></ol>
      </section>

      <p class="foot muted small">From {{ pb.data?.contests?.toLocaleString() || '—' }} contested quad spawns on {{ map }} in the demo corpus (a player counts as contesting when within 650 units in the last 10 seconds before the spawn). Spots are the server's own location names for where a player stood 5 seconds before the spawn. <NuxtLink to="/glossary#quad_conversion">Quad conversion, explained →</NuxtLink></p>
      <div class="more"><span class="muted small">Other maps:</span> <NuxtLink v-for="m in others" :key="m" :to="`/coach/quad/${m}`" class="mlink">{{ m }}</NuxtLink></div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 20px 16px 90px; display: flex; flex-direction: column; gap: 18px; }
.crumbs { display: flex; gap: 8px; align-items: baseline; font-size: 13px; flex-wrap: wrap; }
.back { color: var(--fg-2); text-decoration: none; font-weight: 600; } .back:hover { color: var(--accent); }
.sep { color: var(--fg-3); }
.mlink { color: var(--fg-2); text-decoration: none; font-weight: 700; padding: 4px 8px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--border); }
.mlink.on, .mlink:hover { color: var(--accent); border-color: var(--accent); }
h1 { font-size: clamp(28px, 6vw, 40px); font-weight: 900; margin: 0; letter-spacing: -0.01em; line-height: 1.05; }
.lede { margin: -6px 0 0; font-size: 15px; line-height: 1.6; color: var(--fg-2); max-width: 70ch; }
.sec { display: flex; flex-direction: column; gap: 10px; }
.stitle { font-weight: 800; font-size: 15px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.muted { color: var(--fg-3); } .small { font-size: 12px; }
.decide { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; }
.dcard { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.dlabel { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--fg-3); font-weight: 700; }
.rows { display: flex; flex-direction: column; gap: 6px; }
.row { display: grid; grid-template-columns: 92px minmax(0, 1fr) 44px; gap: 8px; align-items: center; font-size: 13px; }
.bl { color: var(--fg-2); white-space: nowrap; }
.bar { height: 10px; background: var(--panel-3); border-radius: 999px; overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
.bv { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }
.dnote { margin: 0; font-size: 13px; line-height: 1.5; color: var(--fg-2); }
.term { color: inherit; text-decoration: underline dotted var(--accent); text-underline-offset: 3px; }
.ways { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; }
.way { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.way.best { border-color: var(--accent); }
.whead { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; flex-wrap: wrap; }
h3 { margin: 0; font-size: 17px; font-weight: 800; }
.wshare { font-size: 12px; color: var(--fg-3); white-space: nowrap; }
.wnums { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.wn { background: var(--panel-2); border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 1px; font-size: 11px; color: var(--fg-3); }
.wn b { font-size: 18px; color: var(--fg); font-variant-numeric: tabular-nums; }
.way.best .wn:first-child b { color: var(--accent); }
.whow { margin: 0; font-size: 14px; line-height: 1.5; color: var(--fg-2); }
.notes { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; font-size: 14px; line-height: 1.5; color: var(--fg); }
.notes li::marker { color: var(--accent); }
.tbl { overflow-x: auto; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 4px 8px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
th { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-3); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.pool td { color: var(--fg-3); } tr.pool td b { color: var(--fg-2); font-weight: 600; }
.play { margin: 0; padding-left: 22px; list-style: decimal; display: flex; flex-direction: column; gap: 8px; font-size: 15px; line-height: 1.5; }
.play li { display: list-item; }
.play li::marker { color: var(--accent); font-weight: 800; }
.foot { line-height: 1.5; margin: 0; }
.late { margin: -6px 0 0; line-height: 1.5; }
.late b { color: var(--fg); }
.foot a { color: var(--accent); }
.more { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.empty { padding: 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); }
@media (min-width: 720px) {
  .page { padding: 28px 32px 100px; }
  .decide { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .wnums { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
</style>

<script setup>
// The 4on4 coach OVERVIEW (2026-09-21 layout, Peter): level + gates, the ONE focus,
// the two levers after it, then one clickable box per map that opens that map's own
// tab (CoachFoursMap). The grade of the last focus, the narration, the full lever
// table (collapsed) and the last games sit below. Data comes from useFoursCoach so
// the map tabs share the fetch. Framework: docs/coaching_4on4.md.
const props = defineProps({ cid: { type: String, required: true } })
const { report, loading, err, level: lvl, maps } = useFoursCoach(toRef(props, 'cid'))

const focus = computed(() => report.value?.focus || null)
const prev = computed(() => report.value?.previous || null)
const levers = computed(() => report.value?.levers || [])
const games = computed(() => report.value?.games || [])
// the two levers to work on after the focus, in rank order
const then = computed(() => levers.value.filter(l => l.key !== focus.value?.lever).slice(0, 2))
const levelColor = computed(() => LEVEL_COLORS[lvl.value?.level] || 'var(--fg-3)')
const nextLevel = computed(() => Math.min((lvl.value?.level || 1) + 1, 5))
const fg = computed(() => gloss(focus.value?.lever))
const focusLever = computed(() => levers.value.find(l => l.key === focus.value?.lever) || null)
const focusPct = computed(() => progressPct(focus.value?.status === 'in_progress' ? (focus.value?.now ?? focus.value?.you) : focus.value?.you, focus.value?.target, focusLever.value?.higher_better !== false))
const VERDICT = { hit: ['✅', 'Hit'], improved: ['▲', 'Improving'], flat: ['▬', 'No change'], worse: ['▼', 'Went the wrong way'], pending: ['◍', 'In progress'] }
function verdict(s) { return VERDICT[s] || ['', s] }
</script>

<template>
  <div class="cf">
    <div v-if="loading && !report" class="loadbox">Reading your last 40 fours…</div>
    <div v-else-if="err" class="empty err">{{ err }}</div>
    <div v-else-if="report && !lvl?.placed" class="empty">
      <strong>{{ report.display }}</strong> has {{ report.games_total || 0 }} scored fours on Den or LA. A level needs 15. Play a few more pickup nights and the coach will place you.
    </div>

    <template v-else-if="report">
      <!-- level + gates -->
      <section class="sec">
        <div class="lvlcard" :style="{ '--lc': levelColor }">
          <div class="lvlbig"><span class="lvln">L{{ lvl.level }}</span><span class="lvlname">{{ lvl.name }}</span></div>
          <div class="lvlmeta">
            <div>{{ signed(lvl.above_avg_pg) }} above an average player per game · last {{ lvl.games }} fours · {{ report.record.wins }}W/{{ report.record.losses }}L</div>
            <div class="muted small">{{ lvl.blurb }}</div>
          </div>
          <div class="gates">
            <div class="gtitle">Gates to L{{ nextLevel }}<span v-if="lvl.ready" class="ready">ready to move up</span><NuxtLink to="/levels" class="howlink">how levels work →</NuxtLink></div>
            <div v-for="g in lvl.gates" :key="g.key" class="gate" :class="{ ok: g.passed }">
              <span class="gk">{{ g.passed ? '✓' : '○' }}</span>
              <span class="gl">{{ g.label }} <NuxtLink :to="glossHref(g.key)" class="q">?</NuxtLink></span>
              <span class="gv">you <b>{{ g.you }}</b> <span class="muted">· need {{ g.target }}</span></span>
            </div>
            <div v-if="!lvl.gates?.length" class="muted small">Top of the ladder. Hold it.</div>
            <div v-else class="muted small">"need" is the promotion line: what a player just moving up to L{{ nextLevel }} does. <NuxtLink to="/glossary#target" class="glink">what's that? →</NuxtLink></div>
          </div>
        </div>
      </section>

      <!-- the one focus + what comes after it -->
      <section v-if="focus" class="sec">
        <div class="sectitle">🎯 Your one focus</div>
        <div class="card focus">
          <div class="fhead">
            <h3 class="fheadline">{{ fg?.headline || focus.label }}</h3>
            <div class="fstat"><span class="statname">{{ focus.label }}</span><NuxtLink :to="glossHref(focus.lever)" class="what">what is this? →</NuxtLink><span v-if="focus.status === 'in_progress'" class="pill">{{ focus.games_since }} of {{ focus.window_games }} games in</span><span v-else class="pill new">new · your focus for the next {{ focus.window_games }} games</span></div>
          </div>
          <p v-if="fg?.plain" class="plain">{{ fg.plain }}</p>
          <div class="cmp">
            <div class="item you"><span class="n">{{ focus.status === 'in_progress' ? focus.now_fmt : focus.you_fmt }}</span>{{ focus.status === 'in_progress' ? 'you, since the focus started' : 'you now' }}</div>
            <div class="item tgt"><span class="n">{{ focus.target_fmt }}</span>target to play like L{{ nextLevel }}</div>
          </div>
          <div v-if="focusPct != null" class="bar" :title="`${focusPct}% of the way to the target`"><i :style="{ width: focusPct + '%' }" /></div>
          <p class="why"><b>Why it matters:</b> {{ focus.why }}</p>
          <p class="drill"><b>Do this:</b> {{ focus.drill }}</p>
        </div>
        <div v-if="then.length" class="then">
          <div class="thenlabel">After that</div>
          <div v-for="l in then" :key="l.key" class="thenitem">
            <span class="tl"><span class="th">{{ gloss(l.key)?.headline || l.label }}</span><span class="muted small">{{ l.label }}<span v-if="l.is_gate" class="gtag">gate</span> <NuxtLink :to="glossHref(l.key)" class="q">?</NuxtLink></span></span>
            <span class="tn">you <b>{{ l.you }}</b> · target <b class="acc">{{ l.target }}</b></span>
          </div>
        </div>
      </section>

      <!-- one box per map: click for that map's own coach -->
      <section v-if="maps.length" class="sec">
        <div class="sectitle">🗺️ By map <span class="muted small">· open a map for its own coach</span></div>
        <div class="mboxes">
          <NuxtLink v-for="c in maps" :key="c.map" :to="{ query: { map: c.map } }" class="mbox" :class="{ thin: c.thin }">
            <div class="mtop">
              <span class="mmap">{{ c.map }}</span>
              <span class="mrec muted small">{{ c.wins }}–{{ c.losses }}<template v-if="!c.thin"> · {{ signed(c.above_avg_pg) }}</template></span>
            </div>
            <template v-if="!c.thin && c.work_on">
              <div class="mlabel">{{ gloss(c.work_on.key)?.headline || c.work_on.label }}</div>
              <div class="mnums"><span class="muted">{{ c.work_on.label }}:</span> you <b>{{ c.work_on.you }}</b> · target <b class="acc">{{ c.work_on.target }}</b></div>
            </template>
            <div v-else class="mlabel muted">{{ c.games }}/{{ c.min_games }} games · not enough yet</div>
            <span class="mgo">open {{ c.map }} →</span>
          </NuxtLink>
        </div>
      </section>

      <!-- previous prescription, graded -->
      <section v-if="prev && prev.status !== 'pending'" class="sec">
        <div class="sectitle">📋 Last focus · {{ prev.label }}</div>
        <div class="card prevcard" :class="prev.status">
          <div class="pv"><span class="pvi">{{ verdict(prev.status)[0] }}</span><b>{{ verdict(prev.status)[1] }}</b></div>
          <div class="pvnums">at issue <b>{{ prev.at_issue_fmt }}</b> · target <b>{{ prev.target_fmt }}</b> · now <b>{{ prev.now_fmt }}</b> <span class="muted">over {{ prev.games_since }} games</span></div>
        </div>
      </section>

      <!-- narration -->
      <section v-if="report.narration" class="sec">
        <div class="sectitle">🗣️ Your coach</div>
        <div class="card"><div class="read" v-html="coachMd(report.narration.text)" />
          <div class="foot muted small">narration: {{ report.narration.source === 'llm' ? 'AI' : (report.narration.reason === 'model_error' ? 'auto (the coaching model is unavailable right now)' : 'auto') }} · pool: {{ report.pool?.n }} active players</div>
        </div>
      </section>

      <!-- all levers, collapsed -->
      <section v-if="levers.length" class="sec">
        <details class="card details">
          <summary>📐 All your numbers at L{{ lvl.level }} <span class="muted small">· {{ levers.length }} stats, most important first</span></summary>
          <div class="tbl">
            <table>
              <thead><tr><th>stat</th><th class="num">you</th><th class="num">in your wins</th><th class="num">in your losses</th><th class="num">L{{ lvl.level }} does</th><th class="num">target (L{{ nextLevel }} line)</th><th class="num">L{{ nextLevel }} does</th></tr></thead>
              <tbody>
                <tr v-for="l in levers" :key="l.key" :class="{ gate: l.is_gate }">
                  <td><NuxtLink :to="glossHref(l.key)" class="glink">{{ l.label }}</NuxtLink><span v-if="l.is_gate" class="gtag">gate</span></td>
                  <td class="num"><b>{{ l.you }}</b></td><td class="num">{{ l.win ?? '—' }}</td><td class="num">{{ l.loss ?? '—' }}</td>
                  <td class="num">{{ l.level_median }}</td><td class="num"><b>{{ l.target }}</b></td><td class="num muted">{{ l.next_median }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="muted small pad">The target is what this stat looks like for a player right at the edge of moving up; gates use it. Ranked by how far you sit from the target, plus how much the stat separates your own wins from your losses. <NuxtLink to="/glossary" class="glink">every stat explained →</NuxtLink></div>
        </details>
      </section>

      <!-- last games -->
      <section v-if="games.length" class="sec">
        <div class="sectitle">🎮 Last games</div>
        <div class="gcards">
          <div v-for="g in games" :key="g.hub_game_id" class="gcard" :class="{ w: g.win, l: !g.win }">
            <div class="ghead"><NuxtLink :to="{ query: { map: g.map } }" class="gmap">{{ g.map }}</NuxtLink><span class="gres">{{ g.win ? 'W' : 'L' }}</span><span class="muted small">{{ fmtCoachDate(g.played_at) }}</span></div>
            <div class="gscore"><b>{{ signed(g.above_avg) }}</b> above average <span class="muted">· {{ g.frags }} frags / {{ g.deaths }} deaths</span></div>
            <div class="gex"><span v-for="e in g.explain" :key="e.key" class="ex" :class="{ good: e.good, bad: !e.good }">{{ e.good ? '▲' : '▼' }} {{ e.label }} {{ e.value }}</span></div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cf { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.loadbox, .empty { padding: 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); font-size: 14px; line-height: 1.5; }
.empty.err { color: #fca5a5; }
.sec { display: flex; flex-direction: column; gap: 8px; }
.sectitle { font-weight: 800; font-size: 14px; letter-spacing: 0.02em; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 8px 0 0; }
.mono { font-family: 'JetBrains Mono', monospace; }
.arrow { color: var(--fg-3); }
/* level */
.lvlcard { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px 16px; align-items: center; background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--lc); border-radius: 12px; padding: 14px; }
.lvlbig { display: flex; flex-direction: column; align-items: center; min-width: 72px; }
.lvln { font-size: 36px; font-weight: 900; line-height: 1; color: var(--lc); font-variant-numeric: tabular-nums; }
.lvlname { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--fg-2); margin-top: 4px; }
.lvlmeta { display: flex; flex-direction: column; gap: 4px; font-size: 14px; min-width: 0; }
.gates { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 6px; }
.gtitle { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--fg-3); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.howlink { margin-left: auto; font-size: 11px; letter-spacing: 0; text-transform: none; color: var(--accent); }
.ready { background: rgba(52,214,122,0.15); color: #34d67a; border-radius: 999px; padding: 1px 8px; font-size: 11px; text-transform: none; letter-spacing: 0; }
.gate { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 8px; align-items: baseline; font-size: 13px; }
.gate .gk { color: var(--fg-3); } .gate.ok .gk { color: #34d67a; }
.gate .gv { font-variant-numeric: tabular-nums; white-space: nowrap; }
/* focus */
.focus { border-color: var(--accent); }
.fhead { display: flex; flex-direction: column; gap: 4px; }
.fheadline { margin: 0; font-size: 24px; font-weight: 900; line-height: 1.1; letter-spacing: -0.01em; text-wrap: balance; }
.fstat { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: baseline; font-size: 13px; color: var(--fg-2); }
.statname { font-weight: 700; color: var(--fg); }
.what { color: var(--accent); font-weight: 700; text-decoration: none; }
.plain { margin: 8px 0 0; font-size: 14px; line-height: 1.55; color: var(--fg-2); max-width: 70ch; }
.bar { height: 10px; background: var(--panel-3); border-radius: 999px; overflow: hidden; margin: 0 0 6px; }
.bar i { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
.q { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--border-2); color: var(--fg-3); font-size: 11px; font-weight: 700; text-decoration: none; vertical-align: middle; margin-left: 2px; }
.q:hover { color: var(--accent); border-color: var(--accent); }
.glink { color: inherit; text-decoration: underline dotted var(--fg-3); text-underline-offset: 3px; }
.glink:hover { color: var(--accent); }
.acc { color: var(--accent); }
.th { display: block; font-size: 14px; }
.pill { font-size: 11px; font-weight: 600; background: var(--panel-3); color: var(--fg-2); border-radius: 999px; padding: 2px 9px; }
.pill.new { background: rgba(255,122,26,0.15); color: var(--accent); }
.cmp { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 12px 0; }
.item { background: var(--panel-2); border-radius: 10px; padding: 10px 12px; font-size: 12px; color: var(--fg-2); display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.item .n { font-size: 26px; font-weight: 900; color: var(--fg); font-variant-numeric: tabular-nums; line-height: 1.1; }
.item.tgt .n { color: var(--accent); }
.why, .drill { margin: 6px 0 0; font-size: 14px; line-height: 1.5; }
.then { display: grid; grid-template-columns: minmax(0, 1fr); gap: 6px; }
.thenlabel { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--fg-3); padding: 2px 0; }
.thenitem { display: flex; flex-direction: column; gap: 4px; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px; min-width: 0; }
.tl { font-weight: 700; font-size: 13px; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.tn { font-size: 13px; font-variant-numeric: tabular-nums; color: var(--fg-2); }
.gtag { margin-left: 6px; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }
/* map boxes */
.mboxes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 230px), 1fr)); gap: 10px; }
.mbox { display: flex; flex-direction: column; gap: 4px; background: var(--panel); border: 1px solid var(--border-2); border-radius: 12px; padding: 12px 14px; text-decoration: none; color: inherit; min-width: 0; min-height: 44px; transition: border-color .15s, transform .15s; }
.mbox:hover, .mbox:focus-visible { border-color: var(--accent); transform: translateY(-1px); outline: none; }
.mbox.thin { border-style: dashed; }
.mtop { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.mmap { font-size: 18px; font-weight: 900; }
.mrec { white-space: nowrap; }
.mlabel { font-weight: 800; color: var(--accent); font-size: 15px; }
.mbox.thin .mlabel { color: var(--fg-3); font-weight: 600; }
.mnums { font-size: 13px; font-variant-numeric: tabular-nums; color: var(--fg-2); }
.mgo { margin-top: 4px; font-size: 12px; color: var(--fg-3); }
.mbox:hover .mgo { color: var(--accent); }
/* previous */
.prevcard { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: baseline; }
.prevcard.hit { border-color: rgba(52,214,122,0.5); } .prevcard.worse { border-color: rgba(255,93,108,0.5); }
.pv { display: flex; gap: 8px; align-items: baseline; font-size: 15px; } .pvi { font-size: 18px; }
.pvnums { font-size: 13px; font-variant-numeric: tabular-nums; }
/* narration */
.read :deep(p) { margin: 0 0 10px; line-height: 1.55; font-size: 14px; }
.foot { margin-top: 6px; }
/* levers table */
.details summary { cursor: pointer; font-weight: 800; font-size: 14px; list-style: none; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; min-height: 28px; }
.details summary::-webkit-details-marker { display: none; }
.details summary::before { content: '▸'; color: var(--fg-3); }
.details[open] summary::before { content: '▾'; }
.tbl { overflow-x: auto; padding: 10px 0 4px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
th { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-3); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.gate td:first-child { color: var(--fg); }
/* games */
.gcards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr)); gap: 10px; }
.gcard { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.gcard.w { border-top: 3px solid #34d67a; } .gcard.l { border-top: 3px solid #ff5d6c; }
.ghead { display: flex; gap: 8px; align-items: baseline; }
.gmap { font-weight: 700; color: inherit; text-decoration: none; } .gmap:hover { color: var(--accent); }
.gres { font-weight: 800; font-size: 12px; }
.gscore { font-size: 13px; font-variant-numeric: tabular-nums; }
.gex { display: flex; flex-wrap: wrap; gap: 4px; }
.ex { font-size: 11px; border-radius: 6px; padding: 2px 7px; background: var(--panel-2); }
.ex.good { color: #34d67a; } .ex.bad { color: #ff5d6c; }
@media (min-width: 760px) {
  .lvlcard { grid-template-columns: auto minmax(0, 1fr) minmax(220px, 0.9fr); }
  .gates { grid-column: auto; }
  .cmp { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
  .then { grid-template-columns: auto repeat(2, minmax(0, 1fr)); align-items: stretch; }
  .thenlabel { padding: 0 6px 0 2px; }
}
</style>

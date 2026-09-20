<script setup>
// The 4on4 coach: level + gates, ONE focus prescription (kept open for 10 games,
// then graded), ranked levers for that level, last games with explainers, and
// the narration. Data: /api/players/{cid}/coaching/fours (reads the scored
// corpus table — fast, no demo parsing). Framework: docs/coaching_4on4.md.
const props = defineProps({ cid: { type: String, required: true } })
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const report = ref(null)
const loading = ref(false)
const err = ref('')

async function load() {
  loading.value = true; err.value = ''
  try {
    const r = await fetch(`${base}/api/players/${encodeURIComponent(props.cid)}/coaching/fours`)
    if (!r.ok) throw new Error(`coach ${r.status}`)
    report.value = await r.json()
  } catch (e) { err.value = String(e.message || e) } finally { loading.value = false }
}
onMounted(load)
watch(() => props.cid, load)

const lvl = computed(() => report.value?.level || null)
const focus = computed(() => report.value?.focus || null)
const prev = computed(() => report.value?.previous || null)
const levers = computed(() => report.value?.levers || [])
const games = computed(() => report.value?.games || [])
const LEVEL_COLORS = { 1: '#ff5d6c', 2: '#e0a33c', 3: '#c9a66b', 4: '#38bdf8', 5: '#34d67a' }
const levelColor = computed(() => LEVEL_COLORS[lvl.value?.level] || 'var(--fg-3)')
const VERDICT = { hit: ['✅', 'Hit'], improved: ['▲', 'Improving'], flat: ['▬', 'No change'], worse: ['▼', 'Went the wrong way'], pending: ['◍', 'In progress'] }
function verdict(s) { return VERDICT[s] || ['', s] }
function fmtDate(d) { return d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '' }
// minimal markdown: **bold**, _italic_, paragraphs
function md(t) {
  if (!t) return ''
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc(t).split(/\n{2,}/).map(p => '<p>' + p.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/_(.+?)_/g, '<em>$1</em>').replace(/\n/g, '<br>') + '</p>').join('')
}
</script>

<template>
  <div class="cf">
    <div v-if="loading" class="loadbox">Reading your last 40 fours…</div>
    <div v-else-if="err" class="empty err">{{ err }}</div>
    <div v-else-if="report && !lvl?.placed" class="empty">
      <strong>{{ report.display }}</strong> has {{ report.games_total || 0 }} scored fours on Den or LA. A level needs 15. Play a few more pickup nights and the coach will place you.
    </div>

    <template v-else-if="report">
      <!-- level -->
      <section class="sec">
        <div class="lvlcard" :style="{ '--lc': levelColor }">
          <div class="lvlbig"><span class="lvln">L{{ lvl.level }}</span><span class="lvlname">{{ lvl.name }}</span></div>
          <div class="lvlmeta">
            <div>{{ lvl.above_avg_pg > 0 ? '+' : '' }}{{ lvl.above_avg_pg }} above an average player per game · last {{ lvl.games }} fours · {{ report.record.wins }}W/{{ report.record.losses }}L</div>
            <div class="muted small">{{ lvl.blurb }}</div>
          </div>
          <div class="gates">
            <div class="gtitle">Gates to L{{ Math.min(lvl.level + 1, 5) }}<span v-if="lvl.ready" class="ready">ready to move up</span><NuxtLink to="/levels" class="howlink">how levels work →</NuxtLink></div>
            <div v-for="g in lvl.gates" :key="g.key" class="gate" :class="{ ok: g.passed }">
              <span class="gk">{{ g.passed ? '✓' : '○' }}</span>
              <span class="gl">{{ g.label }}</span>
              <span class="gv"><b>{{ g.you }}</b> <span class="muted">vs {{ g.target }}</span></span>
            </div>
            <div v-if="!lvl.gates?.length" class="muted small">Top of the ladder. Hold it.</div>
            <div v-else class="muted small">Targets are the promotion line: what each stat looks like for a player just crossing into L{{ Math.min(lvl.level + 1, 5) }}.</div>
          </div>
        </div>
      </section>

      <!-- previous prescription -->
      <section v-if="prev && prev.status !== 'pending'" class="sec">
        <div class="sectitle">📋 Last focus · {{ prev.label }}</div>
        <div class="card prevcard" :class="prev.status">
          <div class="pv"><span class="pvi">{{ verdict(prev.status)[0] }}</span><b>{{ verdict(prev.status)[1] }}</b></div>
          <div class="pvnums">at issue <b>{{ prev.at_issue_fmt }}</b> · target <b>{{ prev.target_fmt }}</b> · now <b>{{ prev.now_fmt }}</b> <span class="muted">over {{ prev.games_since }} games</span></div>
        </div>
      </section>

      <!-- focus -->
      <section v-if="focus" class="sec">
        <div class="sectitle">🎯 Your one focus</div>
        <div class="card focus">
          <div class="ftitle">{{ focus.label }}<span v-if="focus.status === 'in_progress'" class="pill">{{ focus.games_since }}/{{ focus.window_games }} games</span><span v-else class="pill new">new · next {{ focus.window_games }} games</span></div>
          <div class="cmp">
            <div class="item you"><span class="n">{{ focus.status === 'in_progress' ? focus.now_fmt : focus.you_fmt }}</span>you now</div>
            <div class="item tgt"><span class="n">{{ focus.target_fmt }}</span>promotion line</div>
          </div>
          <p class="why">{{ focus.why }}</p>
          <p class="drill"><b>Drill:</b> {{ focus.drill }}</p>
        </div>
      </section>

      <!-- narration -->
      <section v-if="report.narration" class="sec">
        <div class="sectitle">🗣️ Your coach</div>
        <div class="card"><div class="read" v-html="md(report.narration.text)" />
          <div class="foot muted small">narration: {{ report.narration.source === 'llm' ? 'AI' : (report.narration.reason === 'model_error' ? 'auto (the coaching model is unavailable right now)' : 'auto') }} · pool: {{ report.pool?.n }} active players</div>
        </div>
      </section>

      <!-- levers -->
      <section v-if="levers.length" class="sec">
        <div class="sectitle">📐 Your levers at L{{ lvl.level }}</div>
        <div class="card tbl">
          <table>
            <thead><tr><th>lever</th><th class="num">you</th><th class="num">wins</th><th class="num">losses</th><th class="num">L{{ lvl.level }} median</th><th class="num">line to L{{ Math.min(lvl.level + 1, 5) }}</th><th class="num">L{{ Math.min(lvl.level + 1, 5) }} median</th></tr></thead>
            <tbody>
              <tr v-for="l in levers" :key="l.key" :class="{ gate: l.is_gate }">
                <td>{{ l.label }}<span v-if="l.is_gate" class="gtag">gate</span></td>
                <td class="num"><b>{{ l.you }}</b></td><td class="num">{{ l.win ?? '—' }}</td><td class="num">{{ l.loss ?? '—' }}</td>
                <td class="num">{{ l.level_median }}</td><td class="num"><b>{{ l.target }}</b></td><td class="num muted">{{ l.next_median }}</td>
              </tr>
            </tbody>
          </table>
          <div class="muted small pad">The line is what this lever looks like for a player right at the promotion threshold; targets and gates use it. Ranked by how far you sit from the line, plus how much the lever separates your own wins from your losses. Only levers coached at your level are shown.</div>
        </div>
      </section>

      <!-- last games -->
      <section v-if="games.length" class="sec">
        <div class="sectitle">🎮 Last games</div>
        <div class="gcards">
          <div v-for="g in games" :key="g.hub_game_id" class="gcard" :class="{ w: g.win, l: !g.win }">
            <div class="ghead"><span class="gmap">{{ g.map }}</span><span class="gres">{{ g.win ? 'W' : 'L' }}</span><span class="muted small">{{ fmtDate(g.played_at) }}</span></div>
            <div class="gscore"><b>{{ g.agi }}</b> impact <span class="muted">· {{ g.above_avg > 0 ? '+' : '' }}{{ g.above_avg }} above avg · {{ g.frags }}/{{ g.deaths }}</span></div>
            <div class="gex"><span v-for="e in g.explain" :key="e.key" class="ex" :class="{ good: e.good, bad: !e.good }">{{ e.label }} {{ e.value }}</span></div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cf { display: flex; flex-direction: column; gap: 18px; }
.loadbox, .empty { padding: 24px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); }
.empty.err { color: #fca5a5; }
.sec { display: flex; flex-direction: column; gap: 8px; }
.sectitle { font-weight: 800; font-size: 14px; letter-spacing: 0.02em; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 8px 0 0; }
.lvlcard { display: grid; grid-template-columns: auto minmax(0, 1fr) minmax(220px, 0.9fr); gap: 16px; align-items: center; background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--lc); border-radius: 12px; padding: 16px; }
.lvlbig { display: flex; flex-direction: column; align-items: center; min-width: 90px; }
.lvln { font-size: 40px; font-weight: 900; line-height: 1; color: var(--lc); font-variant-numeric: tabular-nums; }
.lvlname { font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--fg-2); margin-top: 4px; }
.lvlmeta { display: flex; flex-direction: column; gap: 4px; font-size: 14px; }
.gates { display: flex; flex-direction: column; gap: 6px; }
.gtitle { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--fg-3); display: flex; gap: 8px; align-items: center; }
.howlink { margin-left: auto; font-size: 11px; letter-spacing: 0; text-transform: none; color: var(--accent); }
.ready { background: rgba(52,214,122,0.15); color: #34d67a; border-radius: 999px; padding: 1px 8px; font-size: 11px; text-transform: none; letter-spacing: 0; }
.gate { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 8px; align-items: baseline; font-size: 13px; }
.gate .gk { color: var(--fg-3); } .gate.ok .gk { color: #34d67a; }
.gate .gv { font-variant-numeric: tabular-nums; white-space: nowrap; }
.prevcard { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: baseline; }
.prevcard.hit { border-color: rgba(52,214,122,0.5); } .prevcard.worse { border-color: rgba(255,93,108,0.5); }
.pv { display: flex; gap: 8px; align-items: baseline; font-size: 15px; } .pvi { font-size: 18px; }
.pvnums { font-size: 13px; font-variant-numeric: tabular-nums; }
.focus { border-color: var(--accent); }
.ftitle { font-size: 18px; font-weight: 800; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pill { font-size: 11px; font-weight: 600; background: var(--panel-3); color: var(--fg-2); border-radius: 999px; padding: 2px 9px; }
.pill.new { background: rgba(255,122,26,0.15); color: var(--accent); }
.cmp { display: flex; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.item { flex: 1 1 120px; background: var(--panel-2); border-radius: 10px; padding: 10px 12px; font-size: 12px; color: var(--fg-2); display: flex; flex-direction: column; gap: 2px; }
.item .n { font-size: 22px; font-weight: 800; color: var(--fg); font-variant-numeric: tabular-nums; }
.item.tgt .n { color: var(--accent); }
.why, .drill { margin: 6px 0 0; font-size: 14px; line-height: 1.5; }
.read :deep(p) { margin: 0 0 10px; line-height: 1.55; font-size: 14px; }
.foot { margin-top: 6px; }
.tbl { overflow-x: auto; padding: 6px 10px 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; }
th { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-3); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.gate td:first-child { color: var(--fg); }
.gtag { margin-left: 6px; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }
.gcards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.gcard { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.gcard.w { border-top: 3px solid #34d67a; } .gcard.l { border-top: 3px solid #ff5d6c; }
.ghead { display: flex; gap: 8px; align-items: baseline; }
.gmap { font-weight: 700; } .gres { font-weight: 800; font-size: 12px; }
.gscore { font-size: 13px; font-variant-numeric: tabular-nums; }
.gex { display: flex; flex-wrap: wrap; gap: 4px; }
.ex { font-size: 11px; border-radius: 6px; padding: 2px 7px; background: var(--panel-2); }
.ex.good { color: #34d67a; } .ex.bad { color: #ff5d6c; }
@media (max-width: 760px) { .lvlcard { grid-template-columns: auto minmax(0, 1fr); } .gates { grid-column: 1 / -1; } }
</style>

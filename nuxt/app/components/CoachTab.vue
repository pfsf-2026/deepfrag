<script setup>
// Combined AI Coach tab: coach read (with Read-more), simplified "what to work
// on" focus cards, training journal (weekly snapshots + since-first trends), and
// per-match Deep Analyze. Self-loads on demand (the report parses ~15 demos, so
// it's gated behind a button). Data: coaching/report + coaching/history +
// per-match deep-analyze endpoints.
const props = defineProps({ cid: { type: String, required: true } })
const df = useDeepFrag()

const report = ref(null)
const history = ref(null)
const loading = ref(false)
const err = ref('')
const requested = ref(false)
const readMore = ref(false)
const deep = ref({})          // game_id -> {loading, error, data}

async function analyze() {
  const rUrl = df.coachingReportUrl(props.cid, '1on1', 15)
  if (!rUrl) { err.value = 'Coaching requires the live API.'; return }
  requested.value = true; loading.value = true; err.value = ''
  try {
    const [rep, hist] = await Promise.all([
      fetch(rUrl).then(r => r.ok ? r.json() : Promise.reject(new Error(`report ${r.status}`))),
      fetch(df.coachingHistoryUrl(props.cid, '1on1')).then(r => r.ok ? r.json() : null).catch(() => null)
    ])
    report.value = rep
    history.value = hist
  } catch (e) { err.value = String(e.message || e) } finally { loading.value = false }
}

watch(() => props.cid, () => { report.value = null; history.value = null; requested.value = false; err.value = ''; deep.value = {} })

// ---- helpers ----
function md(t) {
  if (!t) return ''
  const esc = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/_(.+?)_/g, '<em>$1</em>').replace(/\n/g, '<br>')
}
const num = s => parseFloat(String(s).replace(/[^0-9.]/g, ''))

const levers = computed(() => report.value?.weakness?.levers || [])
const primary = computed(() => levers.value[0] || null)
const secondary = computed(() => levers.value.slice(1, 4))

// trend per lever from since-first snapshot deltas
const SNAP_KEY = { ra_control: 'ra_control', first_spawn_opt: 'fso', stack_at_kill: 'stack_at_kill', pct_stacked: 'pct_stacked', armor_first: 'armor_first' }
const LOWER_BETTER = new Set(['restack_sec', 'enemy_stack_at_my_death'])
function trend(L) {
  const sk = SNAP_KEY[L.key]
  const d = sk && history.value?.since_first?.[sk]
  if (!d || d.from == null || d.to == null) return null
  const delta = d.to - d.from
  if (Math.abs(delta) < 1e-6) return { dir: 'flat', label: '▬ flat' }
  const better = LOWER_BETTER.has(L.key) ? delta < 0 : delta > 0
  return better ? { dir: 'up', label: '▲ improving' } : { dir: 'down', label: '▼ slipping' }
}

const SNAP_LABELS = { ra_control: 'Red Armor control', fso: 'First-spawn optimization', stack_at_kill: 'Stack @ kills', pct_stacked: 'Time stacked', armor_first: 'Armor-first', win_rate: 'Win rate' }
const PCT_KEYS = new Set(['ra_control', 'fso', 'pct_stacked', 'armor_first', 'win_rate'])
function fmtSnap(k, v) { if (v == null) return '—'; return PCT_KEYS.has(k) ? Math.round(v * 100) + '%' : Math.round(v) }
const sinceRows = computed(() => {
  const sf = history.value?.since_first
  if (!sf) return []
  return Object.entries(sf).map(([k, d]) => ({
    key: k, label: SNAP_LABELS[k] || k, from: fmtSnap(k, d.from), to: fmtSnap(k, d.to),
    better: d.from != null && d.to != null && (LOWER_BETTER.has(k) ? d.to < d.from : d.to > d.from)
  }))
})

function fmtDate(d) { return d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '' }

async function runDeep(m) {
  const url = df.deepAnalyzeUrl(props.cid, m.game_id)
  if (!url) return
  deep.value = { ...deep.value, [m.game_id]: { loading: true } }
  try {
    const r = await fetch(url)
    if (!r.ok) throw new Error(`analyze ${r.status}`)
    deep.value = { ...deep.value, [m.game_id]: { data: await r.json() } }
  } catch (e) { deep.value = { ...deep.value, [m.game_id]: { error: String(e.message || e) } } }
}
</script>

<template>
  <div class="coach">
    <!-- gate -->
    <div v-if="!requested" class="intro">
      <p>Get a data-driven read on your 1on1 game — item control, stack management, first-spawn efficiency, and the specific levers separating your wins from losses.</p>
      <button class="btn" @click="analyze">Analyze my game</button>
    </div>
    <div v-else-if="loading" class="empty">Parsing your recent demos &amp; computing your levers… <span class="spin">(~20s)</span></div>
    <div v-else-if="err" class="empty err">{{ err }}</div>

    <template v-else-if="report">
      <!-- 1. COACH READ -->
      <section class="sec">
        <div class="sectitle">🗣️ Your coach · this week</div>
        <div class="card">
          <div class="read" :class="{ clamp: !readMore }" v-html="md(report.narration.text)" />
          <button class="readmore" @click="readMore = !readMore">{{ readMore ? '▾ Show less' : '▸ Read the full breakdown' }}</button>
          <div class="foot">{{ report.parsed }} demos · {{ report.weakness.record.wins }}W/{{ report.weakness.record.losses }}L · narration: {{ report.narration.source === 'llm' ? 'AI' : 'auto' }}</div>
        </div>
      </section>

      <!-- 2. WHAT TO WORK ON -->
      <section v-if="primary" class="sec">
        <div class="sectitle">🎯 What to work on</div>
        <div class="primary">
          <div class="rank">Priority #1 · biggest win available</div>
          <div class="ptitle">{{ primary.label }}</div>
          <div class="cmp">
            <div class="item you"><span class="n">{{ primary.you }}</span>you now</div>
            <div v-if="primary.win" class="item best"><span class="n">{{ primary.win }}</span>you, in your wins</div>
            <div class="item elite"><span class="n">{{ primary.elite }}</span>top players</div>
          </div>
          <span v-if="trend(primary)" class="trend" :class="trend(primary).dir">{{ trend(primary).label }}</span>
        </div>
        <div class="minis">
          <div v-for="L in secondary" :key="L.key" class="mini">
            <div class="l"><span class="what">{{ L.label }}</span>
              <span class="why">you {{ L.you }} · top players {{ L.elite }}</span></div>
            <span v-if="trend(L)" class="trend" :class="trend(L).dir">{{ trend(L).label }}</span>
          </div>
        </div>
      </section>

      <!-- 3. TRAINING JOURNAL -->
      <section v-if="history && history.runs.length" class="sec">
        <div class="sectitle">📔 Training journal <span class="muted">· a snapshot every time you analyze</span></div>
        <div class="jrow">
          <div class="tl">
            <div v-for="(r, i) in history.runs" :key="r.run_date" class="tlitem">
              <div class="tldate"><b :class="{ accent: i === 0 }">{{ fmtDate(r.run_date) }}</b> · {{ r.wins }}W–{{ r.losses }}L · {{ r.matches_analyzed }} demos
                <span v-if="i === 0" class="pill">latest</span></div>
              <div class="tlmeta">RA {{ fmtSnap('ra_control', r.metrics?.ra_control) }} · FSO {{ fmtSnap('fso', r.metrics?.fso) }} · win {{ fmtSnap('win_rate', r.metrics?.win_rate) }}</div>
            </div>
          </div>
          <div v-if="sinceRows.length" class="since card">
            <div class="sectitle small">Since your first report ({{ fmtDate(history.first_report) }})</div>
            <table>
              <tr v-for="row in sinceRows" :key="row.key"><td>{{ row.label }}</td>
                <td class="num">{{ row.from }} → <b :class="row.better ? 'win' : 'loss'">{{ row.to }}</b></td></tr>
            </table>
          </div>
        </div>
      </section>

      <!-- 4. DEEP ANALYZE -->
      <section v-if="report.recent_matches?.length" class="sec">
        <div class="sectitle">🔬 Deep Analyze a match <span class="muted">· full read of one game — movement, items, timings, spawn read</span></div>
        <div v-for="m in report.recent_matches.slice(0, 10)" :key="m.game_id" class="match">
          <div class="mrow">
            <div class="minfo"><b>{{ m.map }}</b> vs {{ m.opponent || '?' }} ·
              <span :class="m.result === 'W' ? 'win' : 'loss'">{{ m.result }} {{ m.my_frags }}–{{ m.opp_frags }}</span>
              <span class="muted"> · {{ fmtDate(m.date) }}</span></div>
            <button class="btn-ghost" :disabled="deep[m.game_id]?.loading" @click="runDeep(m)">
              {{ deep[m.game_id]?.data ? '↻ Re-read' : deep[m.game_id]?.loading ? 'Analyzing…' : '🔬 Deep Analyze' }}
            </button>
          </div>
          <div v-if="deep[m.game_id]?.error" class="empty err">{{ deep[m.game_id].error }}</div>
          <div v-else-if="deep[m.game_id]?.data" class="deepout">
            <div class="read" v-html="md(deep[m.game_id].data.analysis)" />
            <div class="foot">source: {{ deep[m.game_id].data.source === 'llm' ? 'AI' : 'auto' }}<span v-if="deep[m.game_id].data.cached"> · cached</span></div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.coach { --b: var(--border, #1f2a3a); --p2: var(--panel-2, #131c30); }
.intro p, .empty { color: var(--fg-2); font-size: 13.5px; max-width: 720px; }
.intro .btn { margin-top: 12px; }
.empty { padding: 22px 0; } .empty.err { color: var(--loss); }
.spin { color: var(--fg-3); }
.btn { background: var(--accent); color: var(--bg, #04110c); border: 0; padding: 9px 16px; border-radius: 7px; font-weight: 700; font-size: 13px; cursor: pointer; }
.btn-ghost { background: transparent; border: 1px solid var(--b); color: var(--fg-2); padding: 7px 13px; border-radius: 7px; font-size: 12.5px; cursor: pointer; }
.btn-ghost:disabled { opacity: .6; cursor: default; }
.sec { margin-bottom: 22px; }
.sectitle { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); font-weight: 700; margin-bottom: 10px; }
.sectitle.small { font-size: 11px; margin-bottom: 8px; }
.muted { color: var(--fg-3); font-weight: 500; text-transform: none; letter-spacing: 0; }
.card { background: var(--p2); border: 1px solid var(--b); border-radius: 10px; padding: 16px; }
.win { color: var(--win, #34e6b0); } .loss { color: var(--loss, #ff5d6c); } .accent { color: var(--accent); }

.read { font-size: 14px; line-height: 1.7; }
.read :deep(strong) { color: var(--accent); }
.read.clamp { max-height: 7.2em; overflow: hidden; -webkit-mask-image: linear-gradient(180deg, #000 60%, transparent); mask-image: linear-gradient(180deg, #000 60%, transparent); }
.readmore { background: none; border: 0; color: var(--accent); font-size: 13px; font-weight: 600; cursor: pointer; padding: 8px 0 0; }
.foot { color: var(--fg-3); font-size: 11px; margin-top: 10px; }

.primary { background: linear-gradient(180deg, rgba(52,230,176,.06), var(--p2)); border: 1px solid rgba(52,230,176,.3); border-radius: 12px; padding: 18px; }
.primary .rank { font-size: 11px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: .05em; }
.primary .ptitle { font-size: 20px; font-weight: 800; margin: 4px 0 10px; }
.cmp { display: flex; gap: 22px; flex-wrap: wrap; margin-bottom: 10px; }
.cmp .item { font-size: 12.5px; color: var(--fg-2); }
.cmp .item .n { font-size: 22px; font-weight: 800; display: block; }
.cmp .you .n { color: var(--loss); } .cmp .best .n { color: var(--win); } .cmp .elite .n { color: var(--fg-2); }
.trend { font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 20px; display: inline-block; }
.trend.up { background: rgba(52,230,176,.14); color: var(--win); }
.trend.down { background: rgba(255,93,108,.14); color: var(--loss); }
.trend.flat { background: rgba(155,176,197,.12); color: var(--fg-2); }
.minis { margin-top: 10px; }
.mini { display: flex; align-items: center; justify-content: space-between; padding: 11px 14px; border: 1px solid var(--b); border-radius: 9px; background: var(--p2); margin-bottom: 8px; }
.mini .what { font-weight: 700; font-size: 13.5px; } .mini .why { color: var(--fg-3); font-size: 12px; margin-left: 8px; }

.jrow { display: flex; gap: 16px; flex-wrap: wrap; }
.tl { flex: 1.4; min-width: 280px; position: relative; padding-left: 20px; }
.tl::before { content: ''; position: absolute; left: 6px; top: 4px; bottom: 4px; width: 2px; background: var(--b); }
.tlitem { position: relative; margin-bottom: 14px; }
.tlitem::before { content: ''; position: absolute; left: -18px; top: 4px; width: 9px; height: 9px; border-radius: 50%; background: var(--accent); }
.tldate { font-size: 13px; } .tlmeta { color: var(--fg-2); font-size: 12.5px; }
.pill { display: inline-block; font-size: 10px; padding: 1px 7px; border-radius: 20px; background: var(--p2); border: 1px solid var(--b); color: var(--fg-2); margin-left: 4px; }
.since { flex: 1; min-width: 240px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
td { padding: 6px 8px; border-bottom: 1px solid var(--b); } td.num { text-align: right; font-variant-numeric: tabular-nums; }

.match { border: 1px solid var(--b); border-radius: 9px; margin-bottom: 8px; padding: 11px 14px; }
.mrow { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.minfo { font-size: 13px; }
.deepout { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--b); }
</style>

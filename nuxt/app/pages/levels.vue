<script setup>
// Player-facing explainer for the 4on4 coach's levels: what a level is, the
// gates out of each one, what you work on at each level (the lever library),
// how the one-focus loop works, and the live medians per level. Definitions
// come from the engine via /api/coaching/fours/levels so this page can never
// drift from what the coach actually does. Framework: docs/coaching_4on4.md.
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const data = ref(null)
const err = ref('')
onMounted(async () => {
  try { data.value = await $fetch(`${base}/api/coaching/fours/levels`) }
  catch (e) { err.value = 'Could not load the level definitions.' }
})
useHead({ title: 'Levels — how the 4on4 coach works · DeepFrag' })

const COLORS = { 1: '#ff5d6c', 2: '#e0a33c', 3: '#c9a66b', 4: '#38bdf8', 5: '#34d67a' }
const levels = computed(() => data.value?.levels || [])
const levers = computed(() => data.value?.levers || {})
const rules = computed(() => data.value?.rules || { level_window_games: 40, min_games: 15, focus_window_games: 10 })
const pool = computed(() => data.value?.pool || null)
function band(L) {
  if (L.lo == null) return `under ${L.hi}`
  if (L.hi == null) return `${L.lo} and up`
  return `${L.lo} to ${L.hi}`
}
function fmtv(key, v) {
  if (v == null) return '—'
  const f = levers.value[key]?.fmt
  if (f === 'pct') return Math.round(v * 100) + '%'
  if (f === 'num0') return Math.round(v)
  if (f === 'num1') return v.toFixed(1)
  return v.toFixed(2)
}
function line(level, key) { return fmtv(key, pool.value?.levels?.[String(level)]?.line?.[key]) }
function med(level, key) {
  const v = pool.value?.levels?.[String(level)]?.median?.[key]
  if (v == null) return '—'
  const f = levers.value[key]?.fmt
  if (f === 'pct') return Math.round(v * 100) + '%'
  if (f === 'num0') return Math.round(v)
  if (f === 'num1') return v.toFixed(1)
  return v.toFixed(2)
}
function leversAt(level) {
  return Object.values(levers.value).filter(l => l.levels.includes(level)).sort((a, b) => {
    const ga = levels.value[level - 1]?.gates?.includes(a.key) ? 0 : 1
    const gb = levels.value[level - 1]?.gates?.includes(b.key) ? 0 : 1
    return ga - gb || a.label.localeCompare(b.label)
  })
}
const displayOnly = computed(() => Object.values(levers.value).filter(l => !l.levels.length))
</script>

<template>
<div class="guide">
  <NuxtLink class="back" to="/players">← players</NuxtLink>
  <h1>Levels — how the 4on4 coach works</h1>
  <p class="intro">
    Every player with {{ rules.min_games }} or more scored fours on the Den or LA servers gets a <strong>level</strong>, shown on
    their profile. It is a belt, not a rating: it says how much you have been helping your team win lately, and it tells the
    coach which things are worth your time right now. Different levels work on different things, because the corpus says the
    skill that separates each level from the next is a different one at every step.
  </p>

  <div v-if="err" class="note err">{{ err }}</div>
  <div v-else-if="!data" class="note">Loading the level definitions…</div>

  <template v-else>
    <section class="card">
      <h2>What a level is</h2>
      <p>
        Your level comes from one number: your <strong>above average</strong> per game over your last {{ rules.level_window_games }} fours.
        Above average is your +/- (frags weighted by how much each kill and death moved the win probability) minus what an average
        active player would have posted in your seat, with your teammates, against your opponents, on that map. It is earned only by
        results, so no habit stat can promote you. Levels are recomputed every night.
      </p>
      <div class="ladder">
        <div v-for="L in levels" :key="L.level" class="rung" :style="{ '--c': COLORS[L.level] }">
          <div class="rn">L{{ L.level }}</div>
          <div class="rname">{{ L.name }}</div>
          <div class="rband">{{ band(L) }} above avg / game</div>
          <div class="rblurb">{{ L.blurb }}</div>
          <div v-if="pool" class="rpool">{{ pool.levels[String(L.level)]?.n ?? 0 }} of {{ pool.n }} active players</div>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>Gates: the test for the next belt</h2>
      <p>
        Each level has two <strong>gates</strong>. A gate is a metric with a target, and the target is the <strong>promotion line</strong>:
        what that stat typically looks like for a player right at the edge of the next level, read off a fit of the stat against
        above-average across the whole pool. It is never easier than your own level's median and never harder than the next level's.
        Pass both over your last {{ rules.level_window_games }} games and the coach marks you <em>ready to move up</em>. The level itself
        still comes from results, so the gates are the syllabus, not the promotion. They are the two things the corpus says most
        separate your level from the next one.
      </p>
      <div class="tbl">
        <table>
          <thead><tr><th>from</th><th>gate 1</th><th>gate 2</th><th>promotion line</th><th class="muted">median of the level above</th></tr></thead>
          <tbody>
            <tr v-for="L in levels.filter(x => x.gates.length)" :key="L.level">
              <td><span class="lchip" :style="{ color: COLORS[L.level] }">L{{ L.level }} {{ L.name }}</span></td>
              <td>{{ levers[L.gates[0]]?.label }}</td>
              <td>{{ levers[L.gates[1]]?.label }}</td>
              <td class="mono"><b>{{ line(L.level, L.gates[0]) }} · {{ line(L.level, L.gates[1]) }}</b></td><td class="mono muted">{{ med(L.level + 1, L.gates[0]) }} · {{ med(L.level + 1, L.gates[1]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card">
      <h2>One focus at a time</h2>
      <p>
        The coach does not hand you the whole syllabus. It ranks every lever coached at your level by how far you sit from the promotion
        line, adds a discounted bonus for the levers that separate your own wins from your losses, gives the gates a head
        start, and prescribes exactly <strong>one</strong>: a lever, your number, the target, and a {{ rules.focus_window_games }}-game window.
        While the window is open the focus stays. Once you have played {{ rules.focus_window_games }} more fours the coach grades it
        (hit, improving, no change, or worse), tells you, and hands you the next one. The next one can be the same lever again.
      </p>
      <p class="muted">
        Three baselines sit under every lever: your own wins against your own losses (needs {{ rules.min_split }} of each), your level's
        median, and the promotion line (with the next level's median for context). Reds and red timing ignore e1m2, which has no red armor.
      </p>
    </section>

    <section v-for="L in levels" :key="'lv' + L.level" class="card lvsec" :style="{ '--c': COLORS[L.level] }">
      <h2><span class="lchip big">L{{ L.level }} {{ L.name }}</span> <span class="muted small">{{ band(L) }} · {{ L.blurb }}</span></h2>
      <div class="levers">
        <div v-for="lv in leversAt(L.level)" :key="lv.key" class="lever" :class="{ gate: L.gates.includes(lv.key) }">
          <div class="lhead">
            <span class="llabel">{{ lv.label }}</span>
            <span v-if="L.gates.includes(lv.key)" class="gtag">gate</span>
            <span class="lmed mono" :title="`median at L${L.level} → promotion line to L${Math.min(L.level + 1, 5)}`">{{ med(L.level, lv.key) }} → <b>{{ L.level < 5 ? line(L.level, lv.key) : med(5, lv.key) }}</b></span>
          </div>
          <p class="lwhy">{{ lv.why }}</p>
          <p class="ldrill"><b>Drill:</b> {{ lv.drill }}</p>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>What the corpus says is not a lever</h2>
      <p>
        These are on your Advanced tab as habits, but the coach will never prescribe them in fours, because the data says they do not
        move winning once the real levers are held constant.
      </p>
      <ul>
        <li v-for="lv in displayOnly" :key="lv.key"><strong>{{ lv.label }}.</strong> {{ lv.why }}</li>
        <li><strong>Spawn deaths.</strong> Dying within 3 seconds of spawning is the map, not you: every regular from Pred to bogojoker does it on 12 to 15 percent of deaths.</li>
      </ul>
      <p class="muted small">
        Chained deaths are 45% of a player's deaths in wins and 48% in losses, and once deaths per minute is known a game with more chaining
        is not a worse game. Teamkills per game rise with level, because the stacked players are the ones in the pack with rockets; they are
        charged per event in +/- instead.
      </p>
    </section>

    <section class="card">
      <h2>Live medians by level</h2>
      <p class="muted small">From the active pool ({{ pool?.n ?? '—' }} players with {{ rules.min_games }}+ games in the last year), each on their last {{ rules.level_window_games }} fours. Your targets are the promotion line, which sits between your column and the next one.</p>
      <div class="tbl">
        <table>
          <thead><tr><th>lever</th><th v-for="L in levels" :key="L.level" class="num" :style="{ color: COLORS[L.level] }">L{{ L.level }}</th></tr></thead>
          <tbody>
            <tr v-for="lv in Object.values(levers).filter(x => x.levels.length)" :key="lv.key">
              <td>{{ lv.label }}<span class="dir muted small">{{ lv.higher_better ? '↑' : '↓' }}</span></td>
              <td v-for="L in levels" :key="L.level" class="num mono">{{ med(L.level, lv.key) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <p class="muted small foot">
      Full definitions of every metric: <NuxtLink to="/ladder/enhanced-guide">enhanced stats</NuxtLink> for the ladder parser and the
      advanced-metrics methodology in the DeepFrag docs. The level bands and gates are reviewed against the corpus; if a gate stops
      predicting who moves up, it gets replaced, the way chained deaths already was.
    </p>
  </template>
</div>
</template>

<style scoped>
.guide { max-width: 980px; margin: 0 auto; padding: 24px 20px 80px; }
.back { color: var(--accent); font-size: 13px; text-decoration: none; }
h1 { font-size: 28px; font-weight: 900; margin: 10px 0 8px; letter-spacing: -0.01em; }
h2 { font-size: 17px; font-weight: 800; margin: 0 0 8px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.intro { color: var(--fg-2); font-size: 15px; line-height: 1.6; max-width: 72ch; margin: 0 0 18px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin: 0 0 14px; }
.card p { margin: 0 0 10px; line-height: 1.6; max-width: 76ch; }
.muted { color: var(--fg-3); } .small { font-size: 12px; } .mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
.note { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px; color: var(--fg-2); }
.note.err { color: #fca5a5; }
.ladder { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 12px; }
.rung { background: var(--panel-2); border: 1px solid var(--border); border-top: 4px solid var(--c); border-radius: 10px; padding: 12px; min-width: 0; }
.rn { font-size: 26px; font-weight: 900; color: var(--c); line-height: 1; font-variant-numeric: tabular-nums; }
.rname { font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--fg-2); margin-top: 4px; }
.rband { font-size: 12px; color: var(--fg-3); margin-top: 6px; font-family: 'JetBrains Mono', monospace; }
.rblurb { font-size: 13px; color: var(--fg-2); margin-top: 8px; line-height: 1.45; }
.rpool { font-size: 11px; color: var(--fg-3); margin-top: 8px; }
.tbl { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 8px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-3); font-weight: 600; }
td.num, th.num { text-align: right; }
.lchip { font-weight: 800; white-space: nowrap; }
.lchip.big { font-size: 17px; }
.lvsec { border-left: 4px solid var(--c); }
.levers { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }
.lever { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 12px; min-width: 0; }
.lever.gate { border-color: var(--c); }
.lhead { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.llabel { font-weight: 700; }
.gtag { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); font-family: 'JetBrains Mono', monospace; }
.lmed { margin-left: auto; font-size: 12px; color: var(--fg-3); white-space: nowrap; }
.lwhy { font-size: 13px; color: var(--fg-2); margin: 6px 0 0; line-height: 1.5; }
.ldrill { font-size: 13px; margin: 6px 0 0; line-height: 1.5; }
.dir { margin-left: 6px; }
ul { padding-left: 20px; margin: 0 0 10px; } li { margin: 4px 0; line-height: 1.5; }
.foot { margin-top: 18px; }
@media (max-width: 480px) { .lmed { margin-left: 0; } h1 { font-size: 24px; } }
</style>

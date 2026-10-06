<script setup>
// Movement report (1on1 coach overview). Numbers come from every hop in the player's recent
// duels (movement.py, pushed by tools/movement/extract_movement.py) and are shown next to
// the middle player and the top quarter of everyone analysed. Loads on its own: it does not
// wait for "Analyze my game".
const props = defineProps({ cid: { type: String, required: true } })
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const data = ref(null)
const failed = ref(false)

async function load() {
  failed.value = false
  try { data.value = await $fetch(`${base}/api/players/${encodeURIComponent(props.cid)}/movement?mode=1on1`) }
  catch { failed.value = true; data.value = null }
}
onMounted(load)
watch(() => props.cid, load)

// The numbers that track skill lead; the two context rows sit under a divider.
const main = computed(() => (data.value?.metrics || []).filter(m => m.better && m.you != null))
const context = computed(() => (data.value?.metrics || []).filter(m => !m.better && m.you != null))
function fmt(v, unit) {
  if (v == null) return '—'
  const n = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10
  return unit === '%' ? `${n}%` : `${n}`
}
// Where you stand: ahead of the top quarter, around the middle, or behind it.
function tone(m) {
  if (m.top != null && m.you >= m.top) return 'good'
  if (m.median != null && m.you < m.median) return 'behind'
  return ''
}
// Practice sessions on the strafe-coach server (logged by the patched KTX, pulled by the API).
const sessions = computed(() => data.value?.trainer?.sessions || [])
function when(s) { return s ? new Date(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '' }
function signed(v) { return v == null ? '—' : (v > 0 ? '+' : '') + Math.round(v) }
// The mistakes that happened, worst first, as "too far ×5".
const MISS = [['too_far', 'too far'], ['wall', 'wall'], ['late', 'late jump'], ['turn_more', 'turn more'], ['no_key', 'no strafe key']]
function misses(s) {
  return MISS.map(([k, l]) => [l, s.miss?.[k] || 0]).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]).map(([l, n]) => `${l} ×${n}`).join(', ')
}
</script>

<template>
  <section v-if="data && data.games" class="sec mv">
    <div class="sectitle">🏃 Movement <span class="muted">· every hop in your last {{ data.games }} duels ({{ data.hops }} hops)</span></div>
    <div class="card">
      <p v-for="(line, i) in data.read" :key="i" class="mv-read">{{ line }}</p>

      <div class="mv-table" role="table" aria-label="Movement numbers">
        <div class="mv-row mv-head" role="row">
          <span role="columnheader" />
          <span role="columnheader">you</span>
          <span role="columnheader">middle</span>
          <span role="columnheader">top quarter</span>
        </div>
        <div v-for="m in main" :key="m.key" class="mv-row" role="row">
          <span class="mv-label" role="cell">{{ m.label }}<small v-if="m.unit && m.unit !== '%'"> {{ m.unit }}</small></span>
          <b class="mv-you" :class="tone(m)" role="cell">{{ fmt(m.you, m.unit) }}</b>
          <span class="mv-ref" role="cell">{{ fmt(m.median, m.unit) }}</span>
          <span class="mv-ref" role="cell">{{ fmt(m.top, m.unit) }}</span>
        </div>
        <div v-for="m in context" :key="m.key" class="mv-row ctx" role="row">
          <span class="mv-label" role="cell">{{ m.label }}</span>
          <b class="mv-you" role="cell">{{ fmt(m.you, m.unit) }}</b>
          <span class="mv-ref" role="cell">{{ fmt(m.median, m.unit) }}</span>
          <span class="mv-ref" role="cell">{{ fmt(m.top, m.unit) }}</span>
        </div>
      </div>

      <div v-if="data.maps?.length" class="mv-maps">
        <div class="mv-sub">By map · speed gained per hop</div>
        <div class="mv-chips">
          <span v-for="mp in data.maps" :key="mp.map" class="mv-chip">
            <b>{{ mp.map }}</b> {{ mp.gain_med == null ? '—' : (mp.gain_med > 0 ? '+' : '') + fmt(mp.gain_med) }}
            <small>{{ mp.games }} games</small>
          </span>
        </div>
      </div>

      <div v-if="sessions.length" class="mv-sess">
        <div class="mv-sub">Trainer sessions on {{ data.trainer.server }} <span class="muted">· {{ data.trainer.session_count }} kept, {{ data.trainer.session_hops }} hops</span></div>
        <div v-for="s in sessions" :key="s.start" class="mv-s" role="row">
          <span class="mv-s-when">{{ when(s.start) }}<small>{{ s.map }} · {{ Math.round(s.min) }} min</small></span>
          <b class="mv-s-gain">{{ signed(s.avg) }}<small> a hop</small></b>
          <span class="mv-s-facts">{{ s.hops }} hops · best chain {{ s.best_chain }} · top {{ s.top_speed }}<span v-if="misses(s)" class="mv-s-miss"> · {{ misses(s) }}</span></span>
        </div>
      </div>

      <p class="mv-foot">
        Speed in the air comes from turning: hold a strafe key and turn the same way, with your view just behind your direction of travel.
        <template v-if="sessions.length">The coach on <code>{{ data.trainer?.server }}</code> is on when you join; <code>scend</code> closes a session, <code>scstats</code> shows it.</template>
        <template v-else>Practise it live on <code>{{ data.trainer?.server }}</code>: the in-game coach is on when you join, and every session you play there shows up here.</template>
        {{ ' ' }}<span v-if="data.pool_players" class="muted">Compared with {{ data.pool_players }} players.</span>
      </p>
    </div>
  </section>
  <section v-else-if="data && !data.games" class="sec mv">
    <div class="sectitle">🏃 Movement</div>
    <div class="card">
      <div v-if="sessions.length" class="mv-sess nomargin">
        <div class="mv-sub">Trainer sessions on {{ data.trainer.server }} <span class="muted">· {{ data.trainer.session_count }} kept, {{ data.trainer.session_hops }} hops</span></div>
        <div v-for="s in sessions" :key="s.start" class="mv-s" role="row">
          <span class="mv-s-when">{{ when(s.start) }}<small>{{ s.map }} · {{ Math.round(s.min) }} min</small></span>
          <b class="mv-s-gain">{{ signed(s.avg) }}<small> a hop</small></b>
          <span class="mv-s-facts">{{ s.hops }} hops · best chain {{ s.best_chain }} · top {{ s.top_speed }}<span v-if="misses(s)" class="mv-s-miss"> · {{ misses(s) }}</span></span>
        </div>
      </div>
      <p class="mv-foot" :class="{ nomargin: !sessions.length }">No recent duels with demos to read your movement from yet. Play a few and it fills in.</p>
    </div>
  </section>
</template>

<style scoped>
.sec { margin-bottom: 22px; }
.sectitle { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); font-weight: 700; margin-bottom: 10px; }
.muted { color: var(--fg-3); font-weight: 500; text-transform: none; letter-spacing: 0; }
.card { background: var(--p2, var(--panel-2)); border: 1px solid var(--b, var(--border)); border-radius: 10px; padding: 16px; }
.mv-read { margin: 0 0 8px; font-size: 14px; line-height: 1.5; color: var(--fg); }
.mv-table { margin-top: 12px; }
.mv-row { display: grid; grid-template-columns: minmax(0, 1fr) 64px 64px 84px; gap: 8px; align-items: baseline; padding: 8px 0; border-top: 1px solid var(--b, var(--border)); font-size: 13.5px; }
.mv-row > :not(.mv-label) { text-align: right; font-variant-numeric: tabular-nums; }
.mv-head { border-top: 0; padding: 0 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--fg-3); font-weight: 700; }
.mv-label { color: var(--fg-2); min-width: 0; overflow-wrap: anywhere; }
.mv-label small { color: var(--fg-3); font-size: 11px; margin-left: 4px; }
.mv-you { font-size: 15px; color: var(--fg); }
.mv-you.good { color: var(--win); }
.mv-you.behind { color: var(--loss); }
.mv-ref { color: var(--fg-3); }
.mv-row.ctx { font-size: 12.5px; }
.mv-row.ctx .mv-you { font-size: 13px; font-weight: 600; color: var(--fg-2); }
.mv-maps { margin-top: 14px; }
.mv-sub { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--fg-3); font-weight: 700; margin-bottom: 8px; }
.mv-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.mv-chip { border: 1px solid var(--b, var(--border)); border-radius: 8px; padding: 5px 10px; font-size: 13px; color: var(--fg-2); font-variant-numeric: tabular-nums; }
.mv-chip b { color: var(--fg); margin-right: 4px; }
.mv-chip small { color: var(--fg-3); font-size: 11px; margin-left: 6px; }
.mv-sess { margin-top: 14px; }
.mv-sess.nomargin { margin-top: 0; }
.mv-s { display: grid; grid-template-columns: 92px 76px minmax(0, 1fr); gap: 10px; align-items: baseline; padding: 7px 0; border-top: 1px solid var(--b, var(--border)); font-size: 13px; }
.mv-s-when { color: var(--fg); font-weight: 600; display: grid; }
.mv-s-when small { color: var(--fg-3); font-weight: 500; font-size: 11px; }
.mv-s-gain { font-size: 15px; color: var(--fg); font-variant-numeric: tabular-nums; }
.mv-s-gain small { font-size: 11px; color: var(--fg-3); font-weight: 500; }
.mv-s-facts { color: var(--fg-2); font-variant-numeric: tabular-nums; min-width: 0; overflow-wrap: anywhere; }
.mv-s-miss { color: var(--loss); }
.mv-foot { margin: 14px 0 0; font-size: 12.5px; line-height: 1.5; color: var(--fg-2); }
.mv-foot.nomargin { margin: 0; }
.mv-foot code { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--accent); overflow-wrap: anywhere; }
@media (max-width: 480px) {
  .card { padding: 13px 12px; }
  .mv-row { grid-template-columns: minmax(0, 1fr) 46px 52px 58px; gap: 6px; font-size: 13px; }
  .mv-head { font-size: 10px; letter-spacing: .02em; }
  .mv-head span:last-child { white-space: normal; line-height: 1.1; }
  /* phones: date and gain on one line, the facts underneath */
  .mv-s { grid-template-columns: minmax(0, 1fr) auto; gap: 4px 10px; }
  .mv-s-facts { grid-column: 1 / -1; font-size: 12.5px; }
}
</style>

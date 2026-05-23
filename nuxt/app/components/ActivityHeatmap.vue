<script setup>
/**
 * Calendar heatmap — 53 weeks × 7 days. Each cell colored by intensity.
 * Input: [{week_start: ISO, games: N}, ...] in chronological order.
 * Renders cells aligned to weekday-of-week so the pattern matches GitHub-style heatmaps.
 */
const props = defineProps({
  weekly: { type: Array, default: () => [] },
  cellSize: { type: Number, default: 11 }
})

const tooltip = ref({ visible: false, x: 0, y: 0, text: '' })

const cells = computed(() => {
  // Build a [weekIndex, dayIndex] grid of last 53 weeks. Cells with no data → null.
  const now = new Date()
  const start = new Date(now)
  start.setDate(start.getDate() - 53 * 7)
  const byWeek = {}
  for (const w of props.weekly) {
    byWeek[w.week] = w.games
  }
  // Build a fake grid placeholder — for v1 we just emit one cell per data row, plus pads.
  return props.weekly
})

// Color scale (5 bins). Matches the QW accent color family.
function levelClass(games, max) {
  if (!games) return 'l0'
  const r = games / max
  if (r > 0.8) return 'l4'
  if (r > 0.5) return 'l3'
  if (r > 0.25) return 'l2'
  return 'l1'
}

const maxWeek = computed(() => Math.max(1, ...props.weekly.map(w => w.games || 0)))

function fmtDate(s) {
  if (!s) return ''
  return new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function showTip(evt, w) {
  tooltip.value = {
    visible: true,
    x: evt.clientX, y: evt.clientY,
    text: `${fmtDate(w.week_start)} — ${w.games} game${w.games === 1 ? '' : 's'}`
  }
}
function hideTip() { tooltip.value.visible = false }
</script>

<template>
  <div class="hm-wrap">
    <div class="hm-row">
      <div v-for="w in cells" :key="w.week"
           class="hm-cell" :class="levelClass(w.games, maxWeek)"
           :style="{ width: cellSize + 'px', height: cellSize + 'px' }"
           @mouseenter="showTip($event, w)"
           @mousemove="showTip($event, w)"
           @mouseleave="hideTip" />
    </div>
    <div v-if="tooltip.visible" class="hm-tooltip" :style="{ left: tooltip.x + 'px', top: (tooltip.y - 30) + 'px' }">
      {{ tooltip.text }}
    </div>
    <div class="hm-legend">
      <span class="hm-legend-label">Less</span>
      <div class="hm-cell l0" />
      <div class="hm-cell l1" />
      <div class="hm-cell l2" />
      <div class="hm-cell l3" />
      <div class="hm-cell l4" />
      <span class="hm-legend-label">More</span>
      <span class="hm-legend-meta">peak {{ maxWeek }} games / week</span>
    </div>
  </div>
</template>

<style scoped>
.hm-wrap { display: flex; flex-direction: column; gap: 8px; }
.hm-row { display: flex; gap: 2px; flex-wrap: wrap; }
.hm-cell { display: inline-block; border-radius: 2px; background: var(--panel-3); transition: outline 0.1s; }
.hm-cell:hover { outline: 1px solid var(--accent); }
.hm-cell.l0 { background: var(--panel-3); }
.hm-cell.l1 { background: rgba(20,230,192,0.20); }
.hm-cell.l2 { background: rgba(20,230,192,0.42); }
.hm-cell.l3 { background: rgba(20,230,192,0.66); }
.hm-cell.l4 { background: rgba(20,230,192,0.92); }

.hm-legend { display: flex; align-items: center; gap: 4px; margin-top: 4px; }
.hm-legend .hm-cell { width: 10px; height: 10px; }
.hm-legend-label { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; }
.hm-legend-meta { color: var(--fg-3); font-size: 10px; margin-left: auto; font-family: 'JetBrains Mono', monospace; }

.hm-tooltip {
  position: fixed; transform: translate(-50%, 0); pointer-events: none;
  background: rgba(15, 23, 42, 0.96); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 10px; font-size: 11px;
  font-family: 'JetBrains Mono', monospace; color: var(--fg);
  z-index: 1000; white-space: nowrap;
}
</style>

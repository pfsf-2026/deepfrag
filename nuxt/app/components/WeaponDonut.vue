<script setup>
// Weapon accuracy gauge. Your arc (weapon-coloured) with the value and weapon
// name INSIDE the ring; a solid neutral reference ring + tick for your
// division's average; and a delta chip (pp vs division) under the ring so the
// comparison is explicit, not inferred from arc lengths.
const props = defineProps({
  name: { type: String, required: true },
  val: { type: Number, default: null },   // 0-1 accuracy
  max: { type: Number, default: 0.5 },     // scale ceiling for this weapon
  divAvg: { type: Number, default: null }, // 0-1 division average
  color: { type: String, default: 'var(--accent)' },
})
const R = 46
const C = 2 * Math.PI * R
// Ring scale: the configured ceiling, or 20% above whichever is larger of your
// value and the division average — so a 61% RL in fours never pins the ring
// and the average tick stays visible.
const scale = computed(() => Math.max(props.max, (props.val || 0) * 1.2, (props.divAvg || 0) * 1.2))
const pct = computed(() => props.val == null ? 0 : Math.min(1, props.val / scale.value))
const filled = computed(() => C * pct.value)
const avgPct = computed(() => props.divAvg == null ? null : Math.min(1, props.divAvg / scale.value))
const avgFilled = computed(() => avgPct.value == null ? 0 : C * avgPct.value)
const tickAngle = computed(() => avgPct.value == null ? null : -90 + 360 * avgPct.value)
const deltaPp = computed(() => (props.val == null || props.divAvg == null) ? null : Math.round((props.val - props.divAvg) * 100))
const deltaCls = computed(() => deltaPp.value == null ? '' : deltaPp.value > 0 ? 'up' : deltaPp.value < 0 ? 'down' : 'flat')
function pctTxt(v) { return v == null ? '—' : Math.round(v * 100) + '%' }
</script>

<template>
  <div class="donut" :class="{ empty: val == null }">
    <svg viewBox="0 0 120 120" role="img" :aria-label="`${name} ${pctTxt(val)}${divAvg != null ? ', division average ' + pctTxt(divAvg) : ''}`">
      <circle cx="60" cy="60" :r="R" stroke="var(--panel-3, #262017)" stroke-width="10" fill="none" />
      <!-- division average: solid neutral ring on top of the track, plus a tick at its end -->
      <circle v-if="avgPct != null" cx="60" cy="60" :r="R" stroke="var(--fg-2)" stroke-width="3" fill="none"
              :stroke-dasharray="`${avgFilled} ${C}`" transform="rotate(-90 60 60)" opacity="0.6" stroke-linecap="round" />
      <!-- you -->
      <circle v-if="val != null" cx="60" cy="60" :r="R" :stroke="color" stroke-width="10" fill="none"
              :stroke-dasharray="`${filled} ${C}`" transform="rotate(-90 60 60)" stroke-linecap="round" />
      <line v-if="tickAngle != null" x1="60" :y1="60 - R - 8" x2="60" :y2="60 - R + 8"
            stroke="var(--fg)" stroke-width="2" :transform="`rotate(${tickAngle} 60 60)`" opacity="0.9" />
      <text x="60" y="60" text-anchor="middle" class="t-val">{{ pctTxt(val) }}</text>
      <text x="60" y="77" text-anchor="middle" class="t-name" :style="{ fill: val != null ? color : 'var(--fg-3)' }">{{ name }}</text>
    </svg>
    <div class="sub">
      <template v-if="divAvg != null">
        <span class="avg">div {{ pctTxt(divAvg) }}</span>
        <span v-if="deltaPp != null" class="delta" :class="deltaCls">{{ deltaPp > 0 ? '+' : '' }}{{ deltaPp }}pp</span>
      </template>
      <span v-else class="avg">&nbsp;</span>
    </div>
  </div>
</template>

<style scoped>
.donut { text-align: center; min-width: 0; }
.donut svg { width: 100%; max-width: 124px; height: auto; display: block; margin: 0 auto; }
.t-val { font-size: 24px; font-weight: 800; fill: var(--fg); font-variant-numeric: tabular-nums; }
.t-name { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; }
.donut.empty .t-val { fill: var(--fg-3); }
.sub { display: flex; justify-content: center; gap: 6px; align-items: baseline; margin-top: 6px; font-size: 11px; white-space: nowrap; }
.sub .avg { color: var(--fg-3); }
.sub .delta { font-weight: 800; font-variant-numeric: tabular-nums; padding: 1px 6px; border-radius: 999px; }
.sub .delta.up { color: var(--win, #22c55e); background: rgba(34, 197, 94, 0.14); }
.sub .delta.down { color: var(--loss, #ef4444); background: rgba(239, 68, 68, 0.14); }
.sub .delta.flat { color: var(--fg-2); background: var(--panel-2); }
</style>

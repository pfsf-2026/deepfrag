<script setup>
// Weapon accuracy donut, ported from legacy profile.html weaponDonut(). Player
// arc + a faint division-average reference arc & tick so you see at a glance
// whether you're above/below your division's average on that weapon.
const props = defineProps({
  name: { type: String, required: true },
  val: { type: Number, default: null },   // 0-1 accuracy
  max: { type: Number, default: 0.5 },     // scale ceiling for this weapon
  divAvg: { type: Number, default: null }, // 0-1 division average
})
const R = 36
const C = 2 * Math.PI * R
const pct = computed(() => props.val == null ? 0 : Math.min(1, props.val / props.max))
const filled = computed(() => C * pct.value)
const avgPct = computed(() => props.divAvg == null ? null : Math.min(1, props.divAvg / props.max))
const avgFilled = computed(() => avgPct.value == null ? 0 : C * avgPct.value)
const tickAngle = computed(() => avgPct.value == null ? null : -90 + 360 * avgPct.value)
const gid = computed(() => 'wg-' + props.name)
function pctTxt(v) { return v == null ? '—' : Math.round(v * 100) + '%' }
</script>

<template>
  <div class="donut">
    <svg viewBox="0 0 92 92">
      <circle cx="46" cy="46" :r="R" stroke="var(--panel-3, #1a2433)" stroke-width="8" fill="none" />
      <circle v-if="avgPct != null" cx="46" cy="46" :r="R" stroke="var(--fg-3)" stroke-width="2" fill="none"
              :stroke-dasharray="`${avgFilled} ${C}`" transform="rotate(-90 46 46)" opacity="0.45" />
      <circle cx="46" cy="46" :r="R" :stroke="`url(#${gid})`" stroke-width="8" fill="none"
              :stroke-dasharray="`${filled} ${C}`" transform="rotate(-90 46 46)" stroke-linecap="round" />
      <line v-if="tickAngle != null" x1="46" :y1="46 - R - 5" x2="46" :y2="46 - R + 5"
            stroke="var(--fg-2)" stroke-width="1.5" :transform="`rotate(${tickAngle} 46 46)`" opacity="0.85" />
      <defs>
        <linearGradient :id="gid" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="var(--accent)" />
          <stop offset="100%" stop-color="var(--accent-2, #2dd4bf)" />
        </linearGradient>
      </defs>
      <title v-if="divAvg != null">{{ name }}: {{ pctTxt(val) }} (div avg {{ pctTxt(divAvg) }})</title>
    </svg>
    <div class="val">{{ pctTxt(val) }}</div>
    <div class="name">{{ name }}</div>
  </div>
</template>

<style scoped>
.donut { text-align: center; }
.donut svg { width: 84px; height: 84px; }
.donut .val { font-size: 15px; font-weight: 800; margin-top: 2px; font-variant-numeric: tabular-nums; }
.donut .name { font-size: 11px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.05em; }
</style>

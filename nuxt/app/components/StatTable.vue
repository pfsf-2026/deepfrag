<script setup>
// Reusable sortable stat table — ports the legacy profile.html tableInPanel().
// cols: [{ key, label, num?, bar?, fmt?(v)->string, cls?(v)->class, chip?, chipPrefix? }]
const props = defineProps({
  rows: { type: Array, default: () => [] },
  cols: { type: Array, required: true },
  sortKey: { type: String, default: '' },
  sortDir: { type: String, default: 'desc' },
})
const sk = ref(props.sortKey || props.cols[0]?.key)
const sd = ref(props.sortDir)
function setSort(k) {
  if (sk.value === k) sd.value = sd.value === 'desc' ? 'asc' : 'desc'
  else { sk.value = k; sd.value = 'desc' }
}
const sorted = computed(() => {
  const r = [...props.rows]
  const k = sk.value
  r.sort((a, b) => {
    const av = a[k], bv = b[k]
    if (av == null) return 1
    if (bv == null) return -1
    const cmp = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv))
    return sd.value === 'desc' ? -cmp : cmp
  })
  return r
})
function cell(col, row) {
  const v = row[col.key]
  return col.fmt ? col.fmt(v) : (v ?? '—')
}
function cls(col, row) {
  return col.cls ? col.cls(row[col.key]) : ''
}
function barW(v) { return Math.max(0, Math.min(100, Math.round((v || 0) * 100))) }
</script>

<template>
  <div class="panel">
    <table class="stab">
      <thead>
        <tr>
          <th v-for="col in cols" :key="col.key" :class="{ num: col.num, sortable: true, on: sk === col.key }" @click="setSort(col.key)">
            {{ col.label }}<span v-if="sk === col.key" class="arr">{{ sd === 'desc' ? '▾' : '▴' }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in sorted" :key="i">
          <td v-for="col in cols" :key="col.key" :class="[{ num: col.num }, cls(col, row)]">
            <template v-if="col.chip"><span class="chip" :class="'chip-' + (row[col.key] || '')">{{ (col.chipPrefix || '') + (row[col.key] ?? '—') }}</span></template>
            <template v-else-if="col.bar">
              <span class="barwrap"><span class="bar" :style="{ width: barW(row[col.key]) + '%' }" /></span>
              <span class="barval">{{ cell(col, row) }}</span>
            </template>
            <template v-else>{{ cell(col, row) }}</template>
          </td>
        </tr>
        <tr v-if="!sorted.length"><td :colspan="cols.length" class="empty">No data.</td></tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 4px 14px; overflow-x: auto; }
.stab { width: 100%; border-collapse: collapse; font-size: 13px; }
.stab th, .stab td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.stab th { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.stab th.sortable { cursor: pointer; user-select: none; }
.stab th.on { color: var(--accent); }
.stab th .arr { margin-left: 3px; }
.stab td.num, .stab th.num { text-align: right; font-variant-numeric: tabular-nums; }
.stab td.win { color: var(--win, #34e6b0); } .stab td.loss { color: var(--loss, #ff5d6c); }
.chip { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; background: var(--panel-2, #1a2433); }
.barwrap { display: inline-block; width: 54px; height: 6px; background: var(--panel-2, #1a2433); border-radius: 3px; overflow: hidden; vertical-align: middle; margin-right: 6px; }
.bar { display: block; height: 100%; background: var(--accent); }
.barval { font-variant-numeric: tabular-nums; }
.empty { text-align: center; color: var(--fg-3); padding: 20px; }
</style>

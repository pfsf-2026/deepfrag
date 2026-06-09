<script setup>
// General weekly availability — when a player is USUALLY free to play. Stored in
// the player's own time zone; the scheduler converts it onto each match slot to
// show "who's usually free" next to the proposed times. Click or drag to paint.
const emit = defineEmits(['close'])
const { user, authHeader, fetchMe } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const DAYS = [['mon', 'Mon'], ['tue', 'Tue'], ['wed', 'Wed'], ['thu', 'Thu'], ['fri', 'Fri'], ['sat', 'Sat'], ['sun', 'Sun']]
// Noon → 2am next day, covering the ladder's 7pm–2am ET prime window in any tz.
// 24 = midnight, 25 = 1am, 26 = 2am (of the following day).
const HOURS = Array.from({ length: 15 }, (_, i) => 12 + i)
function hourLabel(h) { return h === 12 ? '12p' : h < 24 ? `${h - 12}p` : h === 24 ? '12a' : `${h - 24}a` }

// tz: saved availability tz → preferred tz → state-derived → ET.
const tz = ref(user.value?.availability?.tz || resolveTz(user.value))

// grid[day] = Set of selected hours
const grid = reactive({})
for (const [d] of DAYS) grid[d] = new Set((user.value?.availability?.slots?.[d]) || [])
function isOn(d, h) { return grid[d].has(h) }
function setCell(d, h, on) {
  if (on) grid[d].add(h); else grid[d].delete(h)
  grid[d] = new Set(grid[d])  // trigger reactivity
}

// click / drag to paint
const painting = ref(false)
const paintVal = ref(true)
function down(d, h) { painting.value = true; paintVal.value = !isOn(d, h); setCell(d, h, paintVal.value) }
function enter(d, h) { if (painting.value) setCell(d, h, paintVal.value) }
function stop() { painting.value = false }
onMounted(() => window.addEventListener('pointerup', stop))
onBeforeUnmount(() => window.removeEventListener('pointerup', stop))

const totalSlots = computed(() => DAYS.reduce((n, [d]) => n + grid[d].size, 0))

function addPreset(daysList, hrs) { for (const d of daysList) for (const h of hrs) grid[d].add(h), grid[d] = new Set(grid[d]) }
function presetWeeknights() { addPreset(['mon', 'tue', 'wed', 'thu', 'fri'], [19, 20, 21, 22, 23]) }
function presetWeekends() { addPreset(['sat', 'sun'], [14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]) }
function clearAll() { for (const [d] of DAYS) grid[d] = new Set() }

const saving = ref(false)
const saved = ref(false)
const err = ref('')
async function save() {
  saving.value = true; err.value = ''
  const slots = {}
  for (const [d] of DAYS) { const a = [...grid[d]].sort((x, y) => x - y); if (a.length) slots[d] = a }
  try {
    await $fetch(`${base}/api/auth/availability`, {
      method: 'POST', headers: authHeader(), body: { tz: tz.value, slots },
      retry: 2, retryDelay: 700, timeout: 20000   // ride out Cloud Run cold-start blips
    })
    await fetchMe()
    saved.value = true
    setTimeout(() => emit('close'), 600)
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not save' } finally { saving.value = false }
}
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div class="m-head">
        <h3>Your general availability</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <p class="lede">Mark the days &amp; hours you're <strong>usually free</strong> to play. When a captain schedules a match, your free times light up next to the proposed slots — so it's easier to land on a time that works. Click or drag to paint.</p>

      <label class="fld">
        <span>These times are in <span class="muted">— your time zone</span></span>
        <select v-model="tz">
          <option v-for="[zone, label] in TZ_OPTIONS" :key="zone" :value="zone">{{ label }}</option>
        </select>
      </label>

      <div class="presets">
        <button class="chip" @click="presetWeeknights">+ Weeknights 7–11pm</button>
        <button class="chip" @click="presetWeekends">+ Weekends afternoon–late</button>
        <button class="chip ghost" @click="clearAll">Clear all</button>
      </div>

      <div class="gridwrap" @pointerleave="stop">
        <table class="avail">
          <thead>
            <tr>
              <th class="corner"></th>
              <th v-for="h in HOURS" :key="h" class="hh">{{ hourLabel(h) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[d, dl] in DAYS" :key="d">
              <th class="dd">{{ dl }}</th>
              <td v-for="h in HOURS" :key="h" class="cell" :class="{ on: isOn(d, h) }"
                  @pointerdown.prevent="down(d, h)" @pointerenter="enter(d, h)"></td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="err" class="err">{{ err }}</p>
      <div class="m-actions">
        <span class="count">{{ totalSlots }} hour{{ totalSlots === 1 ? '' : 's' }} selected</span>
        <button class="btn ghost" @click="emit('close')">Cancel</button>
        <button class="btn" :disabled="saving" @click="save">{{ saved ? '✓ Saved' : (saving ? 'Saving…' : 'Save availability') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 24px 26px; width: 100%; max-width: 600px; max-height: 92vh; overflow-y: auto; }
.m-head { display: flex; justify-content: space-between; align-items: center; }
.m-head h3 { margin: 0; font-size: 20px; font-weight: 800; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.x:hover { color: var(--fg); }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 16px; }
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.fld > span { font-size: 12px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.muted { color: var(--fg-3); font-weight: 400; text-transform: none; }
.fld select { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 12px; border-radius: 8px; font-family: inherit; font-size: 14px; }
.fld select:focus { outline: none; border-color: var(--accent); }
.presets { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.chip { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg-2); border-radius: 16px; padding: 5px 12px; font-size: 12px; cursor: pointer; font-family: inherit; }
.chip:hover { border-color: var(--accent); color: var(--fg); }
.chip.ghost { color: var(--fg-3); }
.gridwrap { overflow-x: auto; margin-bottom: 16px; touch-action: none; }
.avail { border-collapse: collapse; user-select: none; width: 100%; }
.avail th { font-weight: 700; color: var(--fg-3); }
.avail .hh { font-size: 10px; padding: 0 0 5px; font-family: 'JetBrains Mono', monospace; text-align: center; }
.avail .corner { width: 38px; }
.avail .dd { font-size: 12px; text-align: right; padding-right: 8px; color: var(--fg-2); }
.cell { width: 26px; height: 26px; border: 1px solid var(--border); background: var(--panel-2); cursor: pointer; border-radius: 3px; }
.cell:hover { border-color: var(--accent); }
.cell.on { background: var(--accent); border-color: var(--accent); }
.m-actions { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 8px; }
.count { margin-right: auto; font-size: 12px; color: var(--fg-3); }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
</style>

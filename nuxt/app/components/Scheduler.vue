<script setup>
// Doodle-style match scheduler for one challenge.
//  - Challenger: check every slot your team can play over the next 7 days → save.
//  - Challenged: pick one of the proposed slots + confirm the server → scheduled.
// Slots are stored as UTC ISO strings; each side sees them in their LOCAL time.
const props = defineProps({
  challenge: { type: Object, required: true },
  userTeamId: { type: Number, default: null }
})
const emit = defineEmits(['done', 'close'])
const { user, authHeader } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const c = props.challenge
const isChallenger = computed(() => c.challenger_id === props.userTeamId || user.value?.is_admin)
const isChallenged = computed(() => c.challenged_id === props.userTeamId || user.value?.is_admin)
const scheduled = computed(() => !!c.agreed_at)

// ── availability grid (challenger) ──────────────────────────────────────────
const HOURS = [17, 18, 19, 20, 21, 22, 23]   // local evening prime-time
const selected = ref(new Set(c.proposed || []))
const days = computed(() => {
  const out = []
  const base0 = new Date(); base0.setHours(0, 0, 0, 0)
  for (let d = 0; d < 7; d++) {
    const day = new Date(base0); day.setDate(base0.getDate() + d)
    const slots = HOURS.map((h) => {
      const dt = new Date(day); dt.setHours(h, 0, 0, 0)
      return { iso: dt.toISOString(), label: `${h}:00`, past: dt.getTime() < Date.now() }
    })
    out.push({ label: day.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' }), slots })
  }
  return out
})
function toggle(iso) { selected.value.has(iso) ? selected.value.delete(iso) : selected.value.add(iso); selected.value = new Set(selected.value) }

const saving = ref(false)
const err = ref('')
async function saveAvailability() {
  if (selected.value.size === 0) { err.value = 'Pick at least one slot'; return }
  saving.value = true; err.value = ''
  try {
    await $fetch(`${base}/api/ladder/challenge/${c.id}/availability`, {
      method: 'POST', headers: authHeader(), body: { slots: [...selected.value] }
    })
    emit('done')
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not save' } finally { saving.value = false }
}

// ── pick a slot (challenged) ────────────────────────────────────────────────
const pick = ref('')
const server = ref(c.server || user.value?.favorite_server || '')
// Server suggestions from both teams' real ping history.
const suggestions = ref([])
const sugLoading = ref(false)
async function loadSuggestions() {
  sugLoading.value = true
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/server-suggestion`)
    suggestions.value = r.suggestions || []
    if (!server.value && suggestions.value[0]) server.value = suggestions.value[0].host
  } catch { suggestions.value = [] } finally { sugLoading.value = false }
}
function fmtLocal(iso) {
  return new Date(iso).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
async function confirmSlot() {
  if (!pick.value) { err.value = 'Pick a time'; return }
  saving.value = true; err.value = ''
  try {
    await $fetch(`${base}/api/ladder/challenge/${c.id}/schedule`, {
      method: 'POST', headers: authHeader(), body: { slot: pick.value, server: server.value }
    })
    emit('done')
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not schedule' } finally { saving.value = false }
}

// Which view: scheduled summary > challenger-fills (no proposed yet, or editing) >
// challenged-picks (proposed exist) > waiting.
const view = computed(() => {
  if (scheduled.value) return 'done'
  const hasProposed = (c.proposed || []).length > 0
  if (isChallenged.value && hasProposed) return 'pick'
  if (isChallenger.value) return 'fill'
  if (hasProposed) return 'waiting-pick'
  return 'waiting-fill'
})

onMounted(() => { if (view.value === 'pick') loadSuggestions() })
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div class="m-head">
        <h3>Schedule · {{ c.challenger }} vs {{ c.challenged }}</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>

      <!-- already scheduled -->
      <div v-if="view === 'done'" class="done">
        <div class="big">📅 {{ fmtLocal(c.agreed_at) }}</div>
        <div v-if="c.server" class="muted">Server: <strong>{{ c.server }}</strong></div>
        <div class="muted small" style="margin-top:8px;">Shown in your local time. Good luck!</div>
      </div>

      <!-- challenger fills availability -->
      <template v-else-if="view === 'fill'">
        <p class="lede">Check every slot <strong>your team</strong> can play over the next 7 days. {{ c.challenged }} picks one. (Times in your local zone.)</p>
        <div class="grid">
          <div v-for="day in days" :key="day.label" class="day">
            <div class="day-lbl">{{ day.label }}</div>
            <div class="slots">
              <button v-for="s in day.slots" :key="s.iso" class="slot"
                      :class="{ on: selected.has(s.iso), past: s.past }" :disabled="s.past"
                      @click="toggle(s.iso)">{{ s.label }}</button>
            </div>
          </div>
        </div>
        <p v-if="err" class="err">{{ err }}</p>
        <div class="m-actions">
          <button class="btn ghost" @click="emit('close')">Cancel</button>
          <button class="btn" :disabled="saving" @click="saveAvailability">{{ saving ? 'Saving…' : `Save ${selected.size} slot${selected.size === 1 ? '' : 's'}` }}</button>
        </div>
      </template>

      <!-- challenged picks a slot -->
      <template v-else-if="view === 'pick'">
        <p class="lede"><strong>{{ c.challenger }}</strong> is available at these times — pick one (your local zone):</p>
        <div class="picklist">
          <label v-for="iso in c.proposed" :key="iso" class="pickrow" :class="{ on: pick === iso }">
            <input type="radio" :value="iso" v-model="pick"> {{ fmtLocal(iso) }}
          </label>
        </div>
        <div class="fld">
          <span>Server <span class="muted">— suggested from both teams' ping history</span></span>
          <div v-if="sugLoading" class="muted small">Crunching pings…</div>
          <div v-else-if="suggestions.length" class="sug-list">
            <button v-for="(s, i) in suggestions" :key="s.host" class="sug" :class="{ on: server === s.host }" @click="server = s.host">
              <div class="sug-head">
                <span v-if="i === 0" class="best">BEST</span>
                <strong>{{ s.host }}</strong>
                <span class="muted">{{ s.city || s.country || 'NA' }}</span>
                <span class="sug-ping">worst {{ s.max_ping }}ms · avg {{ s.avg_ping }}ms</span>
              </div>
              <div class="sug-pings">
                <span v-for="p in s.pings" :key="p.player" :class="{ est: p.est, none: p.ping == null }">
                  {{ p.name }}: {{ p.ping == null ? '—' : p.ping + (p.est ? '*' : '') }}
                </span>
              </div>
            </button>
            <div class="muted small">* estimated from location (no ping history yet)</div>
          </div>
          <div v-else class="muted small">No ping history yet — enter a server manually.</div>
          <input v-model="server" placeholder="server hostname" style="margin-top:8px;">
        </div>
        <p v-if="err" class="err">{{ err }}</p>
        <div class="m-actions">
          <button class="btn ghost" @click="emit('close')">Cancel</button>
          <button class="btn" :disabled="saving" @click="confirmSlot">{{ saving ? 'Scheduling…' : 'Confirm match' }}</button>
        </div>
      </template>

      <!-- waiting states -->
      <div v-else class="done">
        <p v-if="view === 'waiting-pick'" class="muted">Waiting for <strong>{{ c.challenged }}</strong> to pick a time from {{ c.challenger }}'s availability.</p>
        <p v-else class="muted">Waiting for <strong>{{ c.challenger }}</strong> to post their availability.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px 24px; width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; }
.m-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.m-head h3 { margin: 0; font-size: 17px; font-weight: 800; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 16px; }
.grid { display: flex; flex-direction: column; gap: 8px; }
.day { display: grid; grid-template-columns: 96px 1fr; gap: 10px; align-items: center; }
.day-lbl { font-size: 12px; color: var(--fg-2); font-weight: 700; }
.slots { display: flex; flex-wrap: wrap; gap: 5px; }
.slot { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg-2); border-radius: 6px; padding: 5px 9px; font-size: 12px; cursor: pointer; font-family: 'JetBrains Mono', monospace; }
.slot.on { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 700; }
.slot.past { opacity: 0.3; cursor: not-allowed; }
.slot:not(.past):hover { border-color: var(--accent); }
.picklist { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.pickrow { display: flex; align-items: center; gap: 10px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; cursor: pointer; font-size: 14px; }
.pickrow.on { border-color: var(--accent); background: rgba(20,230,192,0.08); }
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.fld > span { font-size: 12px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.muted { color: var(--fg-3); font-weight: 400; text-transform: none; }
.fld input { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 12px; border-radius: 8px; font-family: inherit; font-size: 14px; }
.fld input:focus { outline: none; border-color: var(--accent); }
.sug-list { display: flex; flex-direction: column; gap: 6px; }
.sug { text-align: left; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; cursor: pointer; font-family: inherit; }
.sug.on { border-color: var(--accent); background: rgba(20,230,192,0.08); }
.sug-head { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--fg); flex-wrap: wrap; }
.sug-head .best { background: var(--accent); color: var(--bg); font-size: 9px; font-weight: 800; padding: 1px 6px; border-radius: 4px; }
.sug-head .sug-ping { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg-2); }
.sug-pings { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; font-size: 11px; color: var(--fg-3); font-family: 'JetBrains Mono', monospace; }
.sug-pings .est { color: var(--draw); }
.sug-pings .none { opacity: 0.5; }
.small { font-size: 11px; }
.done { text-align: center; padding: 20px 0; }
.done .big { font-size: 20px; font-weight: 800; margin-bottom: 6px; }
.small { font-size: 12px; }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
</style>

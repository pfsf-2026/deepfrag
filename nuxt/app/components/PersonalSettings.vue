<script setup>
// Personal settings — the player's location (for best-server suggestion) +
// favorite server. State is required (dropdown so the data stays clean); city,
// country, favorite server are optional. Opened from the topbar name dropdown,
// the KOTH location prompt, and the scheduler gate (must have a state to play).
const emit = defineEmits(['close'])
const { user, authHeader, fetchMe } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

// US states + DC, Canadian provinces, then an International catch-all. Value =
// short code we store; label is what the player sees.
const STATES = [
  ['AL', 'Alabama'], ['AK', 'Alaska'], ['AZ', 'Arizona'], ['AR', 'Arkansas'], ['CA', 'California'],
  ['CO', 'Colorado'], ['CT', 'Connecticut'], ['DE', 'Delaware'], ['DC', 'Washington D.C.'], ['FL', 'Florida'],
  ['GA', 'Georgia'], ['HI', 'Hawaii'], ['ID', 'Idaho'], ['IL', 'Illinois'], ['IN', 'Indiana'],
  ['IA', 'Iowa'], ['KS', 'Kansas'], ['KY', 'Kentucky'], ['LA', 'Louisiana'], ['ME', 'Maine'],
  ['MD', 'Maryland'], ['MA', 'Massachusetts'], ['MI', 'Michigan'], ['MN', 'Minnesota'], ['MS', 'Mississippi'],
  ['MO', 'Missouri'], ['MT', 'Montana'], ['NE', 'Nebraska'], ['NV', 'Nevada'], ['NH', 'New Hampshire'],
  ['NJ', 'New Jersey'], ['NM', 'New Mexico'], ['NY', 'New York'], ['NC', 'North Carolina'], ['ND', 'North Dakota'],
  ['OH', 'Ohio'], ['OK', 'Oklahoma'], ['OR', 'Oregon'], ['PA', 'Pennsylvania'], ['RI', 'Rhode Island'],
  ['SC', 'South Carolina'], ['SD', 'South Dakota'], ['TN', 'Tennessee'], ['TX', 'Texas'], ['UT', 'Utah'],
  ['VT', 'Vermont'], ['VA', 'Virginia'], ['WA', 'Washington'], ['WV', 'West Virginia'], ['WI', 'Wisconsin'], ['WY', 'Wyoming'],
  ['AB', 'Alberta (CA)'], ['BC', 'British Columbia (CA)'], ['MB', 'Manitoba (CA)'], ['ON', 'Ontario (CA)'],
  ['QC', 'Quebec (CA)'], ['INTL', 'Outside US / Canada']
]

const state = ref(user.value?.state || '')
const city = ref(user.value?.city || '')
const country = ref(user.value?.country || '')
const favServer = ref(user.value?.favorite_server || '')
const timezone = ref(user.value?.timezone || '')
const saving = ref(false)
const saved = ref(false)
const err = ref('')

// Favorite-server autocomplete: pull the server list once, filter client-side.
const servers = ref([])
const srvResults = ref([])
onMounted(async () => {
  try {
    const r = await $fetch(`${base}/api/servers?active=true&limit=800`)
    servers.value = (r.servers || r || []).map(s => s.host_root || s.hostname || s).filter(Boolean)
  } catch { servers.value = [] }
})
function onFavInput() {
  const q = favServer.value.trim().toLowerCase()
  srvResults.value = q.length < 2 ? [] : servers.value.filter(s => s.toLowerCase().includes(q)).slice(0, 8)
}
function pickServer(s) { favServer.value = s; srvResults.value = [] }

async function save() {
  saving.value = true; err.value = ''
  try {
    await $fetch(`${base}/api/auth/location`, {
      method: 'POST', headers: authHeader(),
      body: { state: state.value, city: city.value, country: country.value, favorite_server: favServer.value, timezone: timezone.value }
    })
    await fetchMe()
    saved.value = true
    setTimeout(() => emit('close'), 600)
  } catch (e) {
    err.value = e?.data?.detail || e?.message || 'Could not save'
  } finally { saving.value = false }
}
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div class="m-head">
        <h3>Personal settings</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <p class="lede">All optional. DeepFrag already infers the fairest server from your match ping history — adding your location just helps when you don't have much history yet.</p>

      <div class="row2">
        <label class="fld grow">
          <span>City <span class="muted">(optional)</span></span>
          <input v-model="city" placeholder="e.g. Denver" maxlength="60">
        </label>
        <label class="fld grow">
          <span>State <span class="muted">(optional)</span></span>
          <select v-model="state">
            <option value="">Select…</option>
            <option v-for="[code, label] in STATES" :key="code" :value="code">{{ label }}</option>
          </select>
        </label>
      </div>
      <label class="fld">
        <span>Country <span class="muted">(optional)</span></span>
        <input v-model="country" placeholder="e.g. US, BR" maxlength="2" style="text-transform:uppercase; max-width:120px;">
      </label>

      <label class="fld">
        <span>Preferred time zone <span class="muted">(optional — overrides location)</span></span>
        <select v-model="timezone">
          <option value="">Auto (from my state, else Eastern)</option>
          <option v-for="[zone, label] in TZ_OPTIONS" :key="zone" :value="zone">{{ label }}</option>
        </select>
      </label>

      <label class="fld">
        <span>Favorite server <span class="muted">(optional)</span></span>
        <input v-model="favServer" placeholder="start typing a server…" @input="onFavInput" autocomplete="off">
      </label>
      <div v-if="srvResults.length" class="srv-res">
        <button v-for="s in srvResults" :key="s" @click="pickServer(s)">{{ s }}</button>
      </div>

      <p v-if="err" class="err">{{ err }}</p>
      <div class="m-actions">
        <button class="btn ghost" @click="emit('close')">Cancel</button>
        <button class="btn" :disabled="saving" @click="save">{{ saved ? '✓ Saved' : (saving ? 'Saving…' : 'Save') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 24px 26px; width: 100%; max-width: 460px; }
.m-head { display: flex; justify-content: space-between; align-items: center; }
.m-head h3 { margin: 0; font-size: 20px; font-weight: 800; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.x:hover { color: var(--fg); }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 18px; }
.row2 { display: flex; gap: 12px; }
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.fld.grow { flex: 1; }
.fld > span { font-size: 12px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.muted { color: var(--fg-3); font-weight: 400; text-transform: none; }
.fld select, .fld input { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 12px; border-radius: 8px; font-family: inherit; font-size: 14px; }
.fld select:focus, .fld input:focus { outline: none; border-color: var(--accent); }
.srv-res { display: flex; flex-direction: column; gap: 3px; margin: -8px 0 12px; max-height: 200px; overflow-y: auto; }
.srv-res button { text-align: left; background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); border-radius: 6px; padding: 7px 10px; font-size: 12px; cursor: pointer; font-family: inherit; }
.srv-res button:hover { border-color: var(--accent); }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
</style>

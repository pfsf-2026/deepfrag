<script setup>
// Personal settings — currently the player's approximate location, used to
// suggest the best match server. Opened from the topbar name dropdown and from
// the "set your location" prompt on the KOTH page.
const emit = defineEmits(['close'])
const { user, authHeader, fetchMe } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const REGIONS = [
  { code: 'EU', label: 'Europe' },
  { code: 'NA', label: 'North America' },
  { code: 'SA', label: 'South America' },
  { code: 'OC', label: 'Oceania' },
  { code: 'AS', label: 'Asia' },
  { code: 'AF', label: 'Africa' }
]

const region = ref(user.value?.region || '')
const country = ref(user.value?.country || '')
const city = ref(user.value?.city || '')
const saving = ref(false)
const saved = ref(false)
const err = ref('')

async function save() {
  if (!region.value) { err.value = 'Pick your region'; return }
  saving.value = true; err.value = ''
  try {
    await $fetch(`${base}/api/auth/location`, {
      method: 'POST', headers: authHeader(),
      body: { region: region.value, country: country.value, city: city.value }
    })
    await fetchMe()
    saved.value = true
    setTimeout(() => emit('close'), 700)
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
      <p class="lede">Your approximate location helps us pick the fairest server for your matches. We only use the region (and country/city if you add them) — never anything precise.</p>

      <label class="fld">
        <span>Region *</span>
        <select v-model="region">
          <option value="">Select your region…</option>
          <option v-for="r in REGIONS" :key="r.code" :value="r.code">{{ r.label }}</option>
        </select>
      </label>
      <div class="row2">
        <label class="fld grow">
          <span>Country <span class="muted">(optional)</span></span>
          <input v-model="country" placeholder="e.g. SE" maxlength="2" style="text-transform:uppercase;">
        </label>
        <label class="fld grow">
          <span>City <span class="muted">(optional)</span></span>
          <input v-model="city" placeholder="e.g. Stockholm" maxlength="60">
        </label>
      </div>

      <p v-if="err" class="err">{{ err }}</p>
      <div class="m-actions">
        <button class="btn ghost" @click="emit('close')">Cancel</button>
        <button class="btn" :disabled="saving" @click="save">{{ saved ? '✓ Saved' : (saving ? 'Saving…' : 'Save location') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 24px 26px; width: 100%; max-width: 440px; }
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
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
</style>

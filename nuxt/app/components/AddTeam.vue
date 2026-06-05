<script setup>
// Self-serve team registration (onboarding step 2, after profile claim).
// Captain picks a teammate (live fuzzy canonical search), names the team, and
// optionally uploads a logo (resized client-side to keep it small). Submits as a
// PENDING team for admin approval — never auto-placed on the board.
const props = defineProps({ ladderId: { type: Number, required: true } })
const emit = defineEmits(['done', 'close'])
const { authHeader } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const teamName = ref('')
const mateQuery = ref('')
const mate = ref(null)            // chosen teammate {canonical_id, display}
const results = ref([])
const searching = ref(false)
const logoData = ref('')          // data URI
const logoErr = ref('')
const submitting = ref(false)
const err = ref('')

let t = null
watch(mateQuery, (v) => {
  mate.value = null
  clearTimeout(t)
  if (!v || v.length < 2) { results.value = []; return }
  t = setTimeout(search, 220)
})
async function search() {
  searching.value = true
  try {
    const r = await $fetch(`${base}/api/search?q=${encodeURIComponent(mateQuery.value)}&limit=10`)
    results.value = r.results || []
  } catch { results.value = [] } finally { searching.value = false }
}
function pickMate(p) { mate.value = p; mateQuery.value = p.display; results.value = [] }

async function onLogo(e) {
  logoErr.value = ''
  const file = e.target.files?.[0]
  if (!file) return
  if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { logoErr.value = 'PNG/JPEG/WebP/GIF only'; return }
  try {
    logoData.value = await resizeToDataUri(file, 400)
  } catch { logoErr.value = 'Could not read that image' }
}
function resizeToDataUri(file, max) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height))
      const w = Math.round(img.width * scale), h = Math.round(img.height * scale)
      const c = document.createElement('canvas')
      c.width = w; c.height = h
      c.getContext('2d').drawImage(img, 0, 0, w, h)
      resolve(c.toDataURL('image/png'))
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

async function submit() {
  err.value = ''
  if (!teamName.value.trim()) { err.value = 'Give your team a name'; return }
  submitting.value = true
  try {
    await $fetch(`${base}/api/ladder/${props.ladderId}/team/signup`, {
      method: 'POST', headers: authHeader(),
      body: {
        name: teamName.value.trim(),
        teammate_canonical_id: mate.value?.canonical_id || null,
        logo: logoData.value || null
      }
    })
    emit('done', teamName.value.trim())
  } catch (e) {
    err.value = e?.data?.detail || e?.message || 'Could not register team'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div class="m-head">
        <h3>Add your team</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <p class="lede">Register for the KOTH ladder. An admin approves it, then you're on the board and can start challenging.</p>

      <label class="fld">
        <span>Team name</span>
        <input v-model="teamName" placeholder="e.g. Bootleggers" maxlength="40">
      </label>

      <label class="fld">
        <span>Teammate nickname</span>
        <input v-model="mateQuery" placeholder="Start typing your teammate's QW name…">
      </label>
      <div v-if="searching" class="hint">Searching…</div>
      <div v-else-if="results.length" class="res">
        <button v-for="p in results" :key="p.canonical_id" class="res-row" @click="pickMate(p)">
          <span>{{ p.display }}</span><span class="muted">{{ p.matches }} matches</span>
        </button>
      </div>
      <div v-if="mate" class="picked">✓ Teammate: <strong>{{ mate.display }}</strong></div>
      <div v-else-if="mateQuery && !results.length && !searching" class="hint">No match — you can still submit and an admin will sort it.</div>

      <label class="fld">
        <span>Team logo <span class="muted">(optional, PNG/JPEG)</span></span>
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="onLogo">
      </label>
      <div v-if="logoErr" class="err">{{ logoErr }}</div>
      <div v-if="logoData" class="logo-prev"><img :src="logoData" alt="logo preview"></div>

      <p v-if="err" class="err">{{ err }}</p>
      <div class="m-actions">
        <button class="btn ghost" @click="emit('close')">Cancel</button>
        <button class="btn" :disabled="submitting" @click="submit">{{ submitting ? 'Submitting…' : 'Submit for approval' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 24px 26px; width: 100%; max-width: 440px; max-height: 90vh; overflow-y: auto; }
.m-head { display: flex; justify-content: space-between; align-items: center; }
.m-head h3 { margin: 0; font-size: 20px; font-weight: 800; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.x:hover { color: var(--fg); }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 18px; }
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.fld > span { font-size: 12px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.fld input[type=text], .fld input:not([type]) { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 12px; border-radius: 8px; font-family: inherit; font-size: 14px; }
.fld input:focus { outline: none; border-color: var(--accent); }
.fld input[type=file] { font-size: 12px; color: var(--fg-2); }
.muted { color: var(--fg-3); font-weight: 400; }
.hint { color: var(--fg-3); font-size: 12px; margin: -8px 0 12px; }
.res { display: flex; flex-direction: column; gap: 4px; margin: -6px 0 12px; max-height: 200px; overflow-y: auto; }
.res-row { display: flex; justify-content: space-between; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; color: var(--fg); }
.res-row:hover { border-color: var(--accent); }
.picked { background: rgba(34,197,94,0.12); color: #86efac; border-radius: 8px; padding: 8px 12px; font-size: 13px; margin: -6px 0 12px; }
.logo-prev { margin: -4px 0 12px; }
.logo-prev img { max-width: 96px; max-height: 96px; border-radius: 10px; border: 1px solid var(--border); }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.5; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
</style>

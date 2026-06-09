<script setup>
// Report-a-problem form. No sign-in required; if signed in, the user's Discord/
// profile is attached server-side. Submits to /api/support/ticket.
const emit = defineEmits(['close'])
const { loggedIn, user, authHeader } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const AREAS = [
  'Ladder (KOTH)', 'Rankings', 'Player profiles', 'Servers', 'Stats',
  'Head-to-head', 'AI Coach', 'Account / sign-in', 'Something else'
]

const title = ref('')
const area = ref('')
const description = ref('')
const email = ref('')
const images = ref([])      // up to 3 resized data URIs
const imgErr = ref('')
const submitting = ref(false)
const done = ref(null)   // ticket number on success
const err = ref('')

const MAX_IMAGES = 3
async function onPickImages(e) {
  imgErr.value = ''
  const files = [...(e.target.files || [])]
  e.target.value = ''   // allow re-picking the same file
  for (const file of files) {
    if (images.value.length >= MAX_IMAGES) { imgErr.value = `Up to ${MAX_IMAGES} screenshots.`; break }
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { imgErr.value = 'PNG/JPEG/WebP/GIF only'; continue }
    try { images.value.push(await resizeToWebp(file, 2000, 0.82)) }
    catch { imgErr.value = 'Could not read that image' }
  }
}
function resizeToWebp(file, max, quality) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height))
      const w = Math.round(img.width * scale), h = Math.round(img.height * scale)
      const c = document.createElement('canvas'); c.width = w; c.height = h
      c.getContext('2d').drawImage(img, 0, 0, w, h)
      resolve(c.toDataURL('image/webp', quality))
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}
function removeImage(i) { images.value.splice(i, 1) }

async function submit() {
  if (!title.value.trim() || !description.value.trim()) { err.value = 'Add a short summary and a description.'; return }
  submitting.value = true; err.value = ''
  try {
    const r = await $fetch(`${base}/api/support/ticket`, {
      method: 'POST',
      headers: loggedIn.value ? authHeader() : {},
      body: {
        title: title.value, area: area.value, description: description.value,
        email: email.value, page_url: isBrowser ? window.location.pathname : '',
        images: images.value
      },
      retry: 1, retryDelay: 700, timeout: 30000
    })
    done.value = r.ticket
  } catch (e) {
    err.value = e?.data?.detail || e?.message || 'Could not submit — try again.'
  } finally { submitting.value = false }
}
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div class="m-head">
        <h3>Report a problem</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>

      <div v-if="done" class="done">
        <div class="check">✓</div>
        <div>
          <h4>Thanks — ticket #{{ done }} submitted.</h4>
          <p>{{ email ? "We'll email you when it's resolved." : "We're on it. Add an email next time if you'd like updates." }}</p>
        </div>
      </div>

      <template v-else>
        <p class="lede">Found a bug or something off? Tell us what happened and we'll dig in.</p>

        <label class="fld">
          <span>Issue summary</span>
          <input v-model="title" placeholder="e.g. Challenge button doesn't open the scheduler" maxlength="140">
        </label>

        <label class="fld">
          <span>Which part of DeepFrag?</span>
          <select v-model="area">
            <option value="">Select an area…</option>
            <option v-for="a in AREAS" :key="a" :value="a">{{ a }}</option>
          </select>
        </label>

        <label class="fld">
          <span>What exactly happened?</span>
          <textarea v-model="description" rows="5" placeholder="Steps to reproduce, what you expected, what you saw…"></textarea>
        </label>

        <label class="fld">
          <span>Email <span class="muted">(optional — for resolution updates)</span></span>
          <input v-model="email" type="email" placeholder="you@example.com">
        </label>

        <div class="fld">
          <span>Screenshots <span class="muted">(optional — up to {{ MAX_IMAGES }})</span></span>
          <div class="shots">
            <div v-for="(img, i) in images" :key="i" class="shot">
              <img :src="img" alt="screenshot">
              <button type="button" class="shot-x" @click="removeImage(i)">✕</button>
            </div>
            <label v-if="images.length < MAX_IMAGES" class="shot-add">
              + Add
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden @change="onPickImages">
            </label>
          </div>
          <p v-if="imgErr" class="err small">{{ imgErr }}</p>
        </div>

        <p v-if="loggedIn" class="signedin">Signed in as <strong>{{ user?.global_name || user?.username }}</strong> — we'll attach your account to the ticket.</p>

        <p v-if="err" class="err">{{ err }}</p>
        <div class="m-actions">
          <button class="btn ghost" @click="emit('close')">Cancel</button>
          <button class="btn" :disabled="submitting" @click="submit">{{ submitting ? 'Submitting…' : 'Submit ticket' }}</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 120; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 24px 26px; width: 100%; max-width: 480px; max-height: 90vh; overflow-y: auto; }
.m-head { display: flex; justify-content: space-between; align-items: center; }
.m-head h3 { margin: 0; font-size: 20px; font-weight: 800; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 18px; }
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.fld > span { font-size: 12px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.muted { color: var(--fg-3); font-weight: 400; text-transform: none; }
.fld input, .fld select, .fld textarea { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 12px; border-radius: 8px; font-family: inherit; font-size: 14px; }
.fld textarea { resize: vertical; }
.fld input:focus, .fld select:focus, .fld textarea:focus { outline: none; border-color: var(--accent); }
.signedin { font-size: 12px; color: var(--fg-3); margin: -4px 0 12px; }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
.err.small { font-size: 12px; }
.shots { display: flex; flex-wrap: wrap; gap: 8px; }
.shot { position: relative; }
.shot img { width: 64px; height: 64px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); display: block; }
.shot-x { position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--border); background: var(--panel-2); color: var(--fg-2); font-size: 10px; cursor: pointer; line-height: 1; }
.shot-add { width: 64px; height: 64px; border: 1px dashed var(--border); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: var(--fg-3); cursor: pointer; }
.shot-add:hover { border-color: var(--accent); color: var(--fg); }
.done { display: flex; gap: 14px; align-items: center; padding: 12px 0; }
.done .check { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; background: rgba(34,197,94,0.15); color: var(--win); display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 800; }
.done h4 { margin: 0 0 4px; }
.done p { margin: 0; color: var(--fg-2); font-size: 14px; }
</style>

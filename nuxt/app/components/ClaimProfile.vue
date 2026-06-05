<script setup>
// Account<->profile claim UI (option C with B fallback). Shown after Discord
// login when the user has no linked profile and no pending claim:
//  1. Fuzzy-match their Discord name(s) to player profiles -> one-click pick.
//  2. "Player Search" fallback if none of the suggestions are them.
// A pick creates a PENDING claim (admin approves in the federation panel) — we
// never auto-link, to stop someone grabbing another player's profile.
const { authHeader, fetchMe } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const suggestions = ref([])
const loadingSug = ref(true)
const namesTried = ref([])
const searching = ref(false)
const q = ref('')
const searchResults = ref([])
const showSearch = ref(false)
const submitting = ref(false)
const done = ref(false)
const picked = ref(null)
const err = ref('')

onMounted(async () => {
  try {
    const r = await $fetch(`${base}/api/auth/claim/suggestions`, { headers: authHeader() })
    suggestions.value = r.suggestions || []
    namesTried.value = r.names_tried || []
  } catch { /* fall straight to search */ } finally { loadingSug.value = false }
})

let t = null
watch(q, (v) => {
  clearTimeout(t)
  if (!v || v.length < 2) { searchResults.value = []; return }
  t = setTimeout(doSearch, 250)
})
async function doSearch() {
  searching.value = true
  try {
    const r = await $fetch(`${base}/api/search?q=${encodeURIComponent(q.value)}&limit=15`)
    searchResults.value = r.results || []
  } catch { searchResults.value = [] } finally { searching.value = false }
}

async function claim(p) {
  submitting.value = true
  err.value = ''
  try {
    await $fetch(`${base}/api/auth/claim`, {
      method: 'POST', headers: authHeader(), body: { canonical_id: p.canonical_id }
    })
    picked.value = p
    done.value = true
    await fetchMe()
  } catch (e) {
    err.value = e?.data?.detail || e?.message || 'Could not submit claim'
  } finally { submitting.value = false }
}
</script>

<template>
  <section class="claim">
    <div v-if="done" class="claim-done">
      <div class="check">✓</div>
      <div>
        <h3>You're linked to {{ picked.display }}</h3>
        <p>Your stats are connected. Go ahead and add your team — an admin will verify your profile later.</p>
      </div>
    </div>

    <template v-else>
      <div class="claim-head">
        <h3>Connect your player profile</h3>
        <p>Link your Discord to your QuakeWorld stats so your matches and rating show up. Pick yourself below.</p>
      </div>

      <div v-if="loadingSug" class="muted">Finding your profile…</div>

      <template v-else>
        <div v-if="suggestions.length && !showSearch" class="sug-grid">
          <button v-for="p in suggestions" :key="p.canonical_id" class="sug" :disabled="submitting" @click="claim(p)">
            <span class="sug-name">{{ p.display }}</span>
            <span class="sug-meta">{{ p.matches }} matches</span>
          </button>
        </div>

        <p v-if="!showSearch" class="none">
          <span v-if="suggestions.length">Not you? </span>
          <span v-else>We couldn't auto-match <strong v-if="namesTried.length">{{ namesTried.join(', ') }}</strong> to a profile. </span>
          <a class="link" @click="showSearch = true">Search for your player →</a>
        </p>

        <div v-if="showSearch" class="search-box">
          <input v-model="q" placeholder="Search your QW name…" autofocus>
          <div v-if="searching" class="muted small">Searching…</div>
          <div v-else-if="searchResults.length" class="res-list">
            <button v-for="p in searchResults" :key="p.canonical_id" class="res" :disabled="submitting" @click="claim(p)">
              <span class="sug-name">{{ p.display }}</span>
              <span class="sug-meta">{{ p.matches }} matches</span>
            </button>
          </div>
          <div v-else-if="q.length >= 2" class="muted small">No players match “{{ q }}”.</div>
          <a class="link small" @click="showSearch = false">← back to suggestions</a>
        </div>

        <p v-if="err" class="err">{{ err }}</p>
      </template>
    </template>
  </section>
</template>

<style scoped>
.claim { background: var(--panel); border: 1px solid var(--accent); border-radius: 14px; padding: 22px 24px; margin-bottom: 20px; }
.claim-head h3 { margin: 0 0 6px; font-size: 18px; font-weight: 800; }
.claim-head p { margin: 0 0 16px; color: var(--fg-2); font-size: 14px; }
.muted { color: var(--fg-2); }
.small { font-size: 12px; }
.sug-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.sug, .res { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; cursor: pointer; text-align: left; transition: all 0.12s; }
.sug:hover, .res:hover { border-color: var(--accent); background: var(--panel-3); }
.sug:disabled, .res:disabled { opacity: 0.5; cursor: wait; }
.sug-name { font-weight: 700; color: var(--fg); }
.sug-meta { font-size: 11px; color: var(--fg-3); font-family: 'JetBrains Mono', monospace; }
.none { margin: 14px 0 0; color: var(--fg-2); font-size: 13px; }
.link { color: var(--accent); cursor: pointer; text-decoration: none; font-weight: 600; }
.link:hover { text-decoration: underline; }
.search-box { margin-top: 6px; }
.search-box input { width: 100%; background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 14px; border-radius: 8px; font-family: inherit; font-size: 14px; margin-bottom: 10px; }
.search-box input:focus { outline: none; border-color: var(--accent); }
.res-list { display: flex; flex-direction: column; gap: 6px; max-height: 280px; overflow-y: auto; margin-bottom: 10px; }
.res { flex-direction: row; justify-content: space-between; align-items: center; }
.claim-done { display: flex; align-items: center; gap: 16px; }
.claim-done .check { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; background: rgba(34,197,94,0.15); color: var(--win); display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 800; }
.claim-done h3 { margin: 0 0 4px; font-size: 16px; }
.claim-done p { margin: 0; color: var(--fg-2); font-size: 14px; }
.err { color: var(--loss); margin-top: 10px; }
</style>

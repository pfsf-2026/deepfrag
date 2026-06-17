<script setup>
const { indexUrl } = useDeepFrag()
const isBrowser = typeof window !== 'undefined'
const apiBase = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const idx = ref(null)
const pending = ref(true)
const search = ref('')
const apiHits = ref([])           // authoritative backend search results (no index threshold)
const sortBy = ref('matches')     // 'matches' | 'recent' | 'name'

onMounted(async () => {
  try {
    const r = await fetch(indexUrl())
    idx.value = await r.json()
  } catch (e) {
    console.error('Failed to load index:', e)
  } finally {
    pending.value = false
  }
})

// The index only includes players above an activity threshold, so a pure
// client-side filter can miss low-match or just-added players (e.g. a player
// whose name only just got linked). Query the backend /api/search — which
// searches EVERY canonical player by display + id — and fold those in.
let searchTimer = null
watch(search, (val) => {
  const q = (val || '').trim()
  if (searchTimer) clearTimeout(searchTimer)
  if (q.length < 2) { apiHits.value = []; return }
  searchTimer = setTimeout(async () => {
    try {
      const r = await $fetch(`${apiBase}/api/search`, { params: { q, limit: 100 } })
      apiHits.value = r.results || []
    } catch { apiHits.value = [] }
  }, 200)
})

const filtered = computed(() => {
  if (!idx.value?.players) return []
  const q = search.value.trim().toLowerCase()
  let list = idx.value.players
  if (q) {
    const byId = new Map(list.map(p => [p.canonical_id, p]))
    const seen = new Set(); const out = []
    const push = (p) => { if (p && !seen.has(p.canonical_id)) { seen.add(p.canonical_id); out.push(p) } }
    // instant client-side substring matches first…
    list.filter(p => p.display.toLowerCase().includes(q) || p.canonical_id.toLowerCase().includes(q)).forEach(push)
    // …then authoritative backend hits (enriched with index dates when known)
    for (const r of apiHits.value) {
      push(byId.get(r.canonical_id) || { canonical_id: r.canonical_id, display: r.display || r.canonical_id, matches: r.matches || 0, first_seen: null, last_seen: null })
    }
    list = out
  }
  if (sortBy.value === 'matches') list = [...list].sort((a, b) => b.matches - a.matches)
  else if (sortBy.value === 'recent') list = [...list].sort((a, b) => (b.last_seen || '').localeCompare(a.last_seen || ''))
  else list = [...list].sort((a, b) => a.display.localeCompare(b.display))
  return list
})

function fmtDate(s) {
  return s ? new Date(s).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—'
}

useHead({ title: 'All Players · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="hero">
      <h1>QuakeWorld player profiles</h1>
      <p class="sub">
        <strong>{{ idx?.count || 0 }}</strong> players tracked · data from hub.quakeworld.nu
      </p>
    </div>

    <div class="controls">
      <input
        v-model="search"
        type="text"
        placeholder="Search by name…"
        class="search"
      >
      <div class="pill-group">
        <button :class="{ active: sortBy === 'matches' }" @click="sortBy = 'matches'">Most matches</button>
        <button :class="{ active: sortBy === 'recent' }" @click="sortBy = 'recent'">Most recent</button>
        <button :class="{ active: sortBy === 'name' }" @click="sortBy = 'name'">A–Z</button>
      </div>
      <span class="count">{{ filtered.length }} of {{ idx?.count || 0 }}</span>
    </div>

    <div v-if="pending" class="placeholder">Loading…</div>
    <div v-else class="grid">
      <a
        v-for="p in filtered.slice(0, 200)"
        :key="p.canonical_id"
        :href="`/p/${encodeURIComponent(p.canonical_id)}`"
        class="card"
      >
        <div class="avatar">{{ p.display[0]?.toUpperCase() }}</div>
        <div class="info">
          <div class="name">{{ p.display }}</div>
          <div class="meta">{{ p.matches.toLocaleString() }} matches</div>
          <div class="dates">{{ fmtDate(p.first_seen) }} → {{ fmtDate(p.last_seen) }}</div>
        </div>
      </a>
    </div>
    <div v-if="filtered.length > 200" class="more">
      Showing first 200 of {{ filtered.length }} matches. Use search to narrow down.
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1500px; margin: 0 auto; padding: 32px 40px 80px; }
.hero { margin-bottom: 24px; }
.hero h1 { margin: 0; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.hero .sub { color: var(--fg-2); font-size: 14px; margin-top: 6px; }
.hero strong { color: var(--accent); font-weight: 700; }

.controls {
  display: flex; gap: 16px; align-items: center; margin-bottom: 20px; flex-wrap: wrap;
}
.search {
  background: var(--panel); border: 1px solid var(--border); color: var(--fg);
  padding: 10px 16px; border-radius: 8px; font-size: 14px; min-width: 280px;
  font-family: inherit;
}
.search:focus { outline: none; border-color: var(--accent); }
.pill-group {
  display: inline-flex; background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 3px; gap: 2px;
}
.pill-group button {
  background: transparent; border: 0; color: var(--fg-2);
  padding: 6px 14px; border-radius: 5px;
  font-family: inherit; font-size: 12px; font-weight: 600; cursor: pointer;
}
.pill-group button:hover { color: var(--fg); background: var(--panel-2); }
.pill-group button.active { background: var(--accent); color: var(--bg); }
.count { color: var(--fg-3); font-size: 12px; margin-left: auto; }

.grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px;
}
.card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px; display: flex; align-items: center; gap: 14px;
  text-decoration: none; color: inherit; transition: all 0.12s;
}
.card:hover { border-color: var(--border-2); transform: translateY(-1px); }
.avatar {
  width: 48px; height: 48px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 900; color: var(--bg);
}
.info { flex: 1; min-width: 0; }
.name { font-size: 15px; font-weight: 700; letter-spacing: -0.01em;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta { color: var(--accent); font-size: 12px; font-weight: 600; margin-top: 2px; }
.dates { color: var(--fg-3); font-size: 11px; margin-top: 2px; }

.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
.more { color: var(--fg-3); font-size: 12px; text-align: center; margin-top: 24px; }

@media (max-width: 640px) {
  .page { padding: 18px 12px 64px; }
  .hero h1 { font-size: 22px; }
  .hero .sub { font-size: 13px; }
  .controls { gap: 10px; margin-bottom: 16px; }
  .search { min-width: 0; flex: 1 1 100%; }
  .count { margin-left: 0; }
}
</style>

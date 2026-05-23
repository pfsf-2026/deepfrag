<script setup>
const df = useDeepFrag()
const mode = ref('1on1')
const maps = ref([])
const pending = ref(true)

async function loadMaps() {
  pending.value = true
  try {
    const url = df.mapListUrl(mode.value)
    if (!url) { maps.value = []; return }
    const r = await fetch(url)
    const data = await r.json()
    maps.value = data.maps || []
  } catch {
    maps.value = []
  } finally {
    pending.value = false
  }
}

onMounted(loadMaps)
watch(mode, loadMaps)

useHead({ title: 'Map rankings · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="head">
      <NuxtLink to="/" class="back">← All rankings</NuxtLink>
      <h1>Map rankings</h1>
      <p class="sub">
        Each map has its own TrueSkill leaderboard. Pick a map below to see who's best on it.
      </p>
    </div>

    <div class="controls">
      <span class="label">Mode</span>
      <div class="pill-group">
        <button v-for="m in ['1on1','2on2','4on4']" :key="m" :class="{active: mode === m}" @click="mode = m">{{ m }}</button>
      </div>
    </div>

    <div v-if="pending" class="placeholder">Loading maps…</div>
    <div v-else-if="!maps.length" class="placeholder">No maps rated for {{ mode }} yet.</div>

    <div v-else class="map-grid">
      <NuxtLink v-for="m in maps" :key="m.map" :to="`/rankings/maps/${encodeURIComponent(m.map)}`" class="map-tile">
        <div class="map-name">{{ m.map }}</div>
        <div class="map-meta">{{ m.players }} player{{ m.players === 1 ? '' : 's' }} rated</div>
      </NuxtLink>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 20px; }
.head .back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; display: inline-block; margin-bottom: 8px; }
.head .back:hover { color: var(--accent); }
.head h1 { margin: 0 0 6px; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; }

.controls { display: flex; gap: 14px; align-items: center; margin-bottom: 24px; }
.controls .label { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
.pill-group { display: inline-flex; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 3px; gap: 2px; }
.pill-group button { background: transparent; border: 0; color: var(--fg-2); padding: 6px 14px; border-radius: 5px; cursor: pointer; font-family: inherit; font-size: 12px; font-weight: 600; }
.pill-group button:hover { color: var(--fg); background: var(--panel-2); }
.pill-group button.active { background: var(--accent); color: var(--bg); }

.map-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.map-tile {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px 18px; text-decoration: none; color: inherit;
  transition: transform 0.12s, border-color 0.12s;
}
.map-tile:hover { transform: translateY(-2px); border-color: var(--accent); }
.map-name { font-size: 16px; font-weight: 700; }
.map-meta { color: var(--fg-3); font-size: 11px; margin-top: 4px; font-family: 'JetBrains Mono', monospace; }
.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
</style>

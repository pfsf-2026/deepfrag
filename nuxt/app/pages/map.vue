<script setup>
// Player map — groups players by nationality (country code from the community
// config sheet). Most players have a country code; a few have precise lat/lon
// (shown with a 📍). A true dotted world map is a future upgrade once more
// players add precise coordinates — today the data is country-level, so we
// render an honest country-grouped view rather than fake precise pins.
const df = useDeepFrag()
const players = ref([])
const pending = ref(true)

onMounted(async () => {
  const url = df.playerMapUrl()
  if (!url) { pending.value = false; return }
  try {
    const r = await fetch(url)
    if (r.ok) players.value = (await r.json()).players || []
  } finally { pending.value = false }
})

// country code → flag emoji (best-effort; handles 2-letter ISO + a few sheet quirks)
function flag(cc) {
  if (!cc) return '🌐'
  const c = cc.trim().toUpperCase().split('/')[0].slice(0, 2)
  if (c.length !== 2 || !/^[A-Z]{2}$/.test(c)) return '🌐'
  return String.fromCodePoint(...[...c].map(ch => 0x1F1E6 + ch.charCodeAt(0) - 65))
}

const byCountry = computed(() => {
  const groups = {}
  for (const p of players.value) {
    const cc = (p.nationality || '??').trim().toUpperCase()
    ;(groups[cc] ||= []).push(p)
  }
  return Object.entries(groups)
    .map(([cc, ps]) => ({ cc, players: ps.sort((a, b) => (a.display || '').localeCompare(b.display || '')) }))
    .sort((a, b) => b.players.length - a.players.length)
})
const total = computed(() => players.value.length)
const withPin = computed(() => players.value.filter(p => p.lat != null).length)

useHead({ title: 'Player Map · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="hero">
      <h1>🌍 Player map</h1>
      <p class="sub">
        <strong>{{ total }}</strong> players across <strong>{{ byCountry.length }}</strong> countries
        · sourced from the community config sheet · <span class="pin-note">📍 {{ withPin }} with precise location</span>
      </p>
    </div>

    <div v-if="pending" class="placeholder">Loading…</div>
    <div v-else-if="!total" class="placeholder">No location data yet.</div>
    <div v-else class="countries">
      <div v-for="g in byCountry" :key="g.cc" class="country">
        <div class="country-head">
          <span class="flag">{{ flag(g.cc) }}</span>
          <span class="cc">{{ g.cc }}</span>
          <span class="cnt">{{ g.players.length }}</span>
        </div>
        <div class="players">
          <NuxtLink
            v-for="p in g.players" :key="p.canonical_id || p.nick"
            :to="p.canonical_id ? `/p/${encodeURIComponent(p.canonical_id)}` : ''"
            class="player" :class="{ nolink: !p.canonical_id }"
          >
            <span v-if="p.lat != null" class="pin">📍</span>{{ p.display || p.nick }}
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1500px; margin: 0 auto; padding: 32px 40px 80px; }
.hero { margin-bottom: 24px; }
.hero h1 { margin: 0; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.hero .sub { color: var(--fg-2); font-size: 14px; margin-top: 6px; }
.hero strong { color: var(--accent); font-weight: 700; }
.pin-note { color: var(--fg-3); }
.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
.countries { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.country { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.country-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.country-head .flag { font-size: 22px; }
.country-head .cc { font-weight: 700; font-size: 14px; letter-spacing: 0.03em; }
.country-head .cnt { margin-left: auto; color: var(--accent); font-weight: 700; font-variant-numeric: tabular-nums; }
.players { display: flex; flex-wrap: wrap; gap: 6px; }
.player { font-size: 12px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 3px 9px; text-decoration: none; color: var(--fg); transition: all 0.1s; }
.player:hover { border-color: var(--accent); color: var(--accent); }
.player.nolink { pointer-events: none; color: var(--fg-3); }
.player .pin { margin-right: 3px; }
</style>

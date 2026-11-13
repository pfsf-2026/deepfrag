<script setup>
// Stream overlay: one player's card (Peter, 2026-11-13 — casting from the office PC).
// Transparent page for an OBS browser source; ?mode=1on1|2on2|4on4 (default 1on1).
definePageMeta({ ssr: false })
useHead({ title: 'Player card · DeepFrag' })

const route = useRoute()
const id = computed(() => String(route.params.id || '').toLowerCase())
const mode = computed(() => ['1on1', '2on2', '4on4'].includes(route.query.mode) ? route.query.mode : '1on1')
const full = ref(null)
const display = ref('')

async function load() {
  try {
    const r = await fetch(`/api/players/${encodeURIComponent(id.value)}/full`)
    full.value = r.ok ? await r.json() : null
    const c = await fetch(`/api/players/${encodeURIComponent(id.value)}/config`)
    display.value = (c.ok && (await c.json())?.nick) || id.value
  } catch { full.value = null }
}
onMounted(load)
watch(id, load)
let t; onMounted(() => { t = setInterval(load, 120_000) }); onBeforeUnmount(() => clearInterval(t))

const rating = computed(() => full.value?.ratings?.[mode.value] || null)
const games = computed(() => (full.value?.recent_matches || []).filter(m => m.match_mode === mode.value).slice(0, 10))
const avg = k => { const v = games.value.map(m => m[k]).filter(x => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }
const pct = v => v == null ? '—' : `${Math.round(v * 100)}%`
</script>

<template>
  <div v-if="full" class="card">
    <div class="top">
      <span class="name">{{ display }}</span>
      <span v-if="rating?.tier" class="tier" :style="{ background: rating.tier.color }">{{ rating.tier.name }}</span>
    </div>
    <div class="row">
      <div><b>{{ rating ? Math.round(rating.mu) : '—' }}</b><span>rating</span></div>
      <div v-if="rating?.rank"><b>#{{ rating.rank }}</b><span>of {{ rating.total_rated }}</span></div>
      <div v-if="rating"><b>{{ rating.wins }}–{{ rating.losses }}</b><span>{{ mode }}</span></div>
      <div><b>{{ pct(avg('lg_acc')) }}</b><span>LG last 10</span></div>
      <div><b>{{ pct(avg('rl_acc')) }}</b><span>RL last 10</span></div>
    </div>
    <div v-if="mode === '1on1'" class="form">
      <span v-for="m in games" :key="m.match_id" class="dot" :class="m.outcome" :title="`${m.outcome} vs ${m.opponent_name}`" />
    </div>
    <div class="brand">DeepFrag</div>
  </div>
</template>

<style scoped>
.card { display: inline-flex; flex-direction: column; gap: 10px; margin: 16px; padding: 16px 20px; min-width: 420px;
        background: rgba(10, 8, 6, .86); border: 1px solid rgba(255,122,26,.5); border-radius: 14px; color: #f2ead9;
        font-variant-numeric: tabular-nums; box-shadow: 0 8px 30px rgba(0,0,0,.4); }
.top { display: flex; align-items: center; gap: 12px; }
.name { font-size: 30px; font-weight: 900; letter-spacing: -.01em; }
.tier { font-size: 12px; font-weight: 800; color: #111; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
.row { display: flex; gap: 22px; }
.row div { display: flex; flex-direction: column; }
.row b { font-size: 24px; }
.row span { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #988977; }
.form { display: flex; gap: 5px; }
.dot { width: 14px; height: 14px; border-radius: 4px; background: #3a2f22; }
.dot.win { background: #4ade80; } .dot.loss { background: #ff5d6c; }
.brand { font-size: 11px; color: #ff7a1a; text-transform: uppercase; letter-spacing: .14em; font-weight: 800; align-self: flex-end; }
</style>

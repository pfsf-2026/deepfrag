<script setup>
// Stream overlay: matchup bar for two players (Peter, 2026-11-13 — casting from the office PC).
// /overlay/matchup?a=cronus&b=sane&mode=1on1. Transparent page for an OBS browser source.
// The win chance is /api/h2h's overall prediction (rating + head-to-head blend).
useHead({ title: 'Matchup · DeepFrag' })

const route = useRoute()
const a = computed(() => String(route.query.a || '').toLowerCase())
const b = computed(() => String(route.query.b || '').toLowerCase())
const mode = computed(() => ['1on1', '2on2', '4on4'].includes(route.query.mode) ? route.query.mode : '1on1')
const d = ref(null)

async function load() {
  if (!a.value || !b.value) return
  try {
    const r = await fetch(`/api/h2h?p1=${encodeURIComponent(a.value)}&p2=${encodeURIComponent(b.value)}&mode=${mode.value}`)
    d.value = r.ok ? await r.json() : null
  } catch { d.value = null }
}
onMounted(load)
watch([a, b, mode], load)
let t; onMounted(() => { t = setInterval(load, 120_000) }); onBeforeUnmount(() => clearInterval(t))

const pa = computed(() => d.value?.overall_predict_win_a)
const pct = v => v == null ? '—' : `${Math.round(v * 100)}%`
const side = p => p ? { name: p.display || p.canonical_id, mu: p.mu != null ? Math.round(p.mu) : '—', tier: p.tier,
                        lg: pct(p.weapon_shape?.lg_accuracy), rl: pct(p.weapon_shape?.rl_accuracy) } : null
const A = computed(() => side(d.value?.player_a))
const B = computed(() => side(d.value?.player_b))
const h = computed(() => d.value?.h2h || {})
</script>

<template>
  <div v-if="A && B" class="mu">
    <div class="names">
      <div class="p left">
        <span class="n">{{ A.name }}</span>
        <span class="s">{{ A.mu }}<template v-if="A.tier"> · {{ A.tier.name }}</template> · LG {{ A.lg }} · RL {{ A.rl }}</span>
      </div>
      <div class="mid">
        <span class="rec">{{ h.wins_a ?? 0 }} – {{ h.wins_b ?? 0 }}</span>
        <span class="lbl">{{ mode }} head to head</span>
      </div>
      <div class="p right">
        <span class="n">{{ B.name }}</span>
        <span class="s">{{ B.mu }}<template v-if="B.tier"> · {{ B.tier.name }}</template> · LG {{ B.lg }} · RL {{ B.rl }}</span>
      </div>
    </div>
    <div v-if="pa != null" class="bar">
      <div class="fa" :style="{ width: (pa * 100) + '%' }"><span>{{ pct(pa) }}</span></div>
      <div class="fb"><span>{{ pct(1 - pa) }}</span></div>
    </div>
    <div class="foot"><span>win chance</span><span class="brand">DeepFrag</span></div>
  </div>
  <div v-else-if="!a || !b" class="hint">Add ?a=player&amp;b=player to the URL.</div>
</template>

<style scoped>
.mu { margin: 16px; padding: 14px 18px; width: min(900px, calc(100vw - 32px)); box-sizing: border-box;
      background: rgba(10, 8, 6, .86); border: 1px solid rgba(255,122,26,.5); border-radius: 14px; color: #f2ead9;
      font-variant-numeric: tabular-nums; box-shadow: 0 8px 30px rgba(0,0,0,.4); }
.names { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; }
.p { display: flex; flex-direction: column; min-width: 0; }
.p.right { text-align: right; }
.n { font-size: 28px; font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s { font-size: 13px; color: #c9bca9; }
.mid { display: flex; flex-direction: column; align-items: center; }
.rec { font-size: 26px; font-weight: 900; }
.lbl { font-size: 11px; color: #988977; text-transform: uppercase; letter-spacing: .06em; }
.bar { display: flex; height: 26px; border-radius: 8px; overflow: hidden; margin-top: 12px; font-weight: 800; font-size: 14px; }
.fa { background: #ff7a1a; color: #111; display: flex; align-items: center; padding-left: 10px; min-width: 48px; }
.fb { flex: 1; background: #3a2f22; display: flex; align-items: center; justify-content: flex-end; padding-right: 10px; min-width: 48px; }
.foot { display: flex; justify-content: space-between; margin-top: 6px; font-size: 11px; color: #988977; text-transform: uppercase; letter-spacing: .06em; }
.brand { color: #ff7a1a; font-weight: 800; letter-spacing: .14em; }
.hint { color: #fff; margin: 16px; font-family: sans-serif; }
</style>

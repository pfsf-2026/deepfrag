<script setup>
// Profile deep-dive tabs, ported from the legacy profile.html SPA into Nuxt
// one tab at a time (so there's ONE profile UI / one tab bar incl Coach).
// Data: /api/players/{id}/full?window=N (same as the Overview page). Tabs not yet
// ported redirect to the legacy SPA so deep links keep working during migration.
const route = useRoute()
const router = useRouter()
const df = useDeepFrag()

const id = computed(() => String(route.params.id))
const tab = computed(() => String(route.params.tab || ''))
const windowKey = ref('90')

const PORTED = new Set(['recent', 'opponents'])  // grows as tabs are migrated

const profile = ref(null)
const pending = ref(true)

async function load() {
  // Unported tab → fall back to the legacy SPA (preserves the deep link).
  if (!PORTED.has(tab.value)) {
    if (import.meta.client) window.location.replace(`/profile.html?id=${encodeURIComponent(id.value)}#${tab.value}`)
    return
  }
  pending.value = true
  try {
    const url = df.useApi ? `${df.profileUrl(id.value)}/full?window=${windowKey.value}` : df.profileUrl(id.value)
    const r = await fetch(url)
    profile.value = r.ok ? await r.json() : null
  } catch { profile.value = null } finally { pending.value = false }
}
onMounted(load)
watch([id, tab, windowKey], load)

const recent = computed(() => profile.value?.recent_matches || [])
const d = computed(() => profile.value?.windows?.[windowKey.value] || {})
const rivals = computed(() => (d.value.head_to_head_1on1 || []).filter(r => (r.matches || 0) >= 3))

function fmtNum(v) { return v == null ? '—' : Number(v).toLocaleString() }
function fmtDelta(v) { return v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(1) }
const winLoss = v => v > 0 ? 'win' : v < 0 ? 'loss' : ''
const rivalCols = [
  { key: 'opponent', label: 'Opponent' },
  { key: 'matches', label: 'N', num: true, fmt: fmtNum },
  { key: 'wins', label: 'W', num: true },
  { key: 'losses', label: 'L', num: true },
  { key: 'win_rate', label: 'Win%', num: true, bar: true, fmt: v => fmtPct(v) },
  { key: 'avg_frag_diff', label: 'Avg ±', num: true, fmt: fmtDelta, cls: winLoss },
  { key: 'last_played', label: 'Last', fmt: v => fmtDate(v) },
]

function enc(s) { return encodeURIComponent(s) }
// Tabs already in Nuxt link internally; not-yet-ported tabs link straight to the
// legacy SPA (avoids a broken hop / direct-load 404). PORTED grows per migration.
const INTERNAL = new Set(['overview', 'coach', 'maps', ...PORTED])
const TABS = computed(() => {
  const b = `/p/${enc(id.value)}`
  const defs = [
    { key: 'overview', label: 'Overview', to: b },
    { key: 'coach', label: '🎯 Coach', to: { path: b, query: { view: 'coach' } } },
    { key: 'trends', label: 'Trends' }, { key: 'compare', label: 'Compare' },
    { key: '1on1', label: '1on1' }, { key: '4on4', label: '4on4' }, { key: '2on2', label: '2on2' },
    { key: 'dmm', label: 'By DMM' },
    { key: 'maps', label: 'Maps', to: `${b}/maps` },
    { key: 'servers', label: 'Servers' }, { key: 'opponents', label: 'Rivals' },
    { key: 'recent', label: 'Recent', to: `${b}/recent` },
  ]
  return defs.map(t => ({
    ...t,
    internal: INTERNAL.has(t.key),
    to: t.to || `${b}/${t.key}`,
    legacy: `/profile.html?id=${enc(id.value)}#${t.key}`,
  }))
})

function fmtDate(d) { if (!d) return '—'; const x = new Date(d); return isNaN(x) ? d : x.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }
function fmtPct(v) { return v == null ? '—' : Math.round(v * 100) + '%' }

useHead({ title: () => `${id.value} · ${tab.value} · DeepFrag` })
</script>

<template>
  <div class="page">
    <div class="head">
      <NuxtLink :to="`/p/${enc(id)}`" class="back">← {{ id }} overview</NuxtLink>
    </div>

    <div class="profile-tabbar">
      <div class="profile-tabs">
        <template v-for="t in TABS" :key="t.key">
          <NuxtLink v-if="t.internal" :to="t.to" class="ptab" :class="{ active: t.key === tab, 'ptab-coach': t.key === 'coach' }">{{ t.label }}</NuxtLink>
          <a v-else :href="t.legacy" class="ptab">{{ t.label }}</a>
        </template>
      </div>
      <select v-model="windowKey" class="window-select">
        <option value="7">Last 7d</option><option value="30">Last 30d</option>
        <option value="90">Last 90d</option><option value="365">Last year</option><option value="all">All time</option>
      </select>
    </div>

    <div v-if="pending" class="placeholder">Loading…</div>

    <!-- RECENT -->
    <template v-else-if="tab === 'recent'">
      <div class="section-h"><h2>Last 50 matches</h2></div>
      <div class="panel">
        <table class="rtab">
          <thead><tr>
            <th>When</th><th>Mode</th><th>DMM</th><th>Map</th><th>Server</th><th>Result</th>
            <th>Opp</th><th class="num">F</th><th class="num">Opp F</th><th class="num">LG%</th><th class="num">RL%</th>
          </tr></thead>
          <tbody>
            <tr v-for="(m, i) in recent" :key="i">
              <td>{{ fmtDate(m.match_date) }}</td>
              <td><span class="chip" :class="'chip-' + m.match_mode">{{ m.match_mode }}</span></td>
              <td>{{ m.match_dmm ? 'DMM' + m.match_dmm : '—' }}</td>
              <td>{{ m.match_map }}</td>
              <td class="small muted">{{ m.server_hostname || '—' }}</td>
              <td><span v-if="m.outcome" class="result-pill" :class="m.outcome">{{ m.outcome }}</span><span v-else>—</span></td>
              <td>{{ m.opponent_name || '—' }}</td>
              <td class="num">{{ m.player_frags ?? '—' }}</td>
              <td class="num">{{ m.opponent_frags ?? '—' }}</td>
              <td class="num">{{ fmtPct(m.lg_acc) }}</td>
              <td class="num">{{ fmtPct(m.rl_acc) }}</td>
            </tr>
            <tr v-if="!recent.length"><td colspan="11" class="muted" style="text-align:center;padding:20px">No recent matches.</td></tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- RIVALS (1on1 head-to-head) -->
    <template v-else-if="tab === 'opponents'">
      <div class="section-h"><h2>1on1 head-to-head</h2><span class="meta">{{ rivals.length }} opponents (≥3 matches)</span></div>
      <StatTable :rows="rivals" :cols="rivalCols" sort-key="matches" sort-dir="desc" />
    </template>

    <div v-else class="placeholder">Redirecting…</div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 24px 32px 80px; }
.head .back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; }
.head .back:hover { color: var(--accent); }
.profile-tabbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 14px 0 20px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.profile-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.ptab { padding: 8px 14px; color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; border-bottom: 2px solid transparent; cursor: pointer; }
.ptab:hover { color: var(--fg); }
.ptab.active { color: var(--accent); border-bottom-color: var(--accent); }
.ptab-coach { color: var(--accent); }
.window-select { background: var(--panel); border: 1px solid var(--border); color: var(--fg); padding: 6px 10px; border-radius: 7px; font-size: 12px; }
.section-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12px; }
.section-h h2 { font-size: 16px; font-weight: 800; }
.section-h .meta { color: var(--fg-3); font-size: 12px; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 4px 14px; overflow-x: auto; }
.rtab { width: 100%; border-collapse: collapse; font-size: 13px; }
.rtab th, .rtab td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.rtab th { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
.rtab td.num, .rtab th.num { text-align: right; font-variant-numeric: tabular-nums; }
.small { font-size: 12px; } .muted { color: var(--fg-3); }
.chip { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; background: var(--panel-2, #1a2433); }
.result-pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.result-pill.win { background: rgba(52,230,176,0.16); color: #34e6b0; }
.result-pill.loss { background: rgba(255,93,108,0.16); color: #ff5d6c; }
.result-pill.draw { background: rgba(245,158,11,0.16); color: #f59e0b; }
.placeholder { padding: 50px; text-align: center; color: var(--fg-3); }
</style>

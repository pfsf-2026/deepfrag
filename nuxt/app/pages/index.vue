<script setup>
const rankings = ref(null)
const pending = ref(true)
const mode = ref('1on1')
const search = ref('')
const minMatches = ref(20)
const activeOnly = ref(true)   // hide players inactive in the last 90 days by default
const region = ref('')         // '' = Global; 'EU' / 'NA' / 'SA' / 'OC' / 'AS' / 'AF'

const df = useDeepFrag()

async function load() {
  pending.value = true
  try {
    const url = df.rankingsUrl(mode.value, region.value)
    const data = await $fetch(url)
    rankings.value = data
  } catch (e) {
    console.error('[rankings] FAILED:', e)
  } finally {
    pending.value = false
  }
}
onMounted(load)
watch([mode, region], load)

// API returns { players: [...] }; static returns { modes: { 1on1: [...] } }.
const current = computed(() => df.useApi
  ? (rankings.value?.players || [])
  : (rankings.value?.modes?.[mode.value] || []))

// Rich-tooltip content helpers — kept inline since each is tied to one
// stat's explanation. Returns { title, body }.
function tierRtip(t) {
  const labels = {
    div0: 'Top 15% of rated players. Genuinely elite across the game.',
    div1: 'Next 30% (55th–85th percentile). Strong, multi-region competitive.',
    div2: 'Next 35% (20th–55th percentile). Solid, regular competitors.',
    div3: 'Bottom 20%. Climbing or casual.'
  }
  return { title: t.name, body: labels[t.slug] || 'Percentile-based tier from the rated 1on1 population.' }
}
function provisionalRtip(p) {
  return {
    title: 'Provisional rating',
    body: `Only ${p.unique_opponents || 0} unique opponents so far. The rating is built from a thin opponent pool — flagged as a UX hint, not a math penalty.`
  }
}
function consRtip(p) {
  return {
    title: `Conservative rating: ${Math.round(p.conservative)}`,
    body: 'μ − 3σ — the 99.7% lower bound of our skill belief. Used for ranking so uncertain ratings don\'t inflate. Movement-resistant: a single match nudges this slightly.'
  }
}
function musigmaRtip(p) {
  return {
    title: `μ ${Math.round(p.mu)} · σ ${Math.round(p.sigma)}`,
    body: 'μ is the mean skill estimate from OpenSkill (Plackett-Luce). σ is the uncertainty — narrower σ = more settled rating. Inactivity widens σ over time.'
  }
}
function ddrRtip(p) {
  return {
    title: `DDR ${p.avg_ddr.toFixed(2)}`,
    body: 'Damage Differential Ratio — lifetime sum of damage you dealt ÷ damage you took. Above 1.00 = you generate more pressure than you absorb. The QW equivalent of hockey\'s Corsi.'
  }
}
function fragDiffRtip(p) {
  const sign = p.avg_frag_diff >= 0 ? '+' : ''
  return {
    title: `Avg ±frag: ${sign}${p.avg_frag_diff.toFixed(1)}`,
    body: 'Average per-match frag differential (your frags − your deaths). Captures finishing — how cleanly your DDR pressure converts to scoreboard wins.'
  }
}
const filtered = computed(() => {
  let list = current.value.filter(p => p.matches >= minMatches.value)
  if (activeOnly.value) list = list.filter(p => p.active_90d)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(p => (p.display || '').toLowerCase().includes(q)
                          || p.canonical_id.toLowerCase().includes(q))
  }
  // Keep the original rank (from rankings.json / API) so a player's #44 still
  // shows as #44 when filtered. Don't renumber based on visible position.
  return list
})

function fmtPct(v) { return v == null ? '—' : (v * 100).toFixed(0) + '%' }
function fmtDate(s) {
  return s ? new Date(s).toLocaleDateString(undefined, { year: '2-digit', month: 'short', day: 'numeric' }) : '—'
}
function profileHref(cid) { return `/p/${encodeURIComponent(cid)}` }

useHead({ title: 'Rankings · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="head">
      <div class="head-top">
        <h1>{{ region || 'Global' }} · {{ mode }} Rankings</h1>
        <NuxtLink to="/rankings/maps" class="maps-link" title="Browse per-map TrueSkill leaderboards">
          Per-map rankings →
        </NuxtLink>
      </div>
      <p class="sub">
        The rating shown is the <strong>conservative</strong> TrueSkill value (μ − 3σ) — that's what we sort by.
        μ is raw skill, σ is uncertainty (lower = more settled).
      </p>
    </div>

    <div class="controls">
      <span class="label">Region</span>
      <div class="pill-group">
        <button :class="{active: region === ''}" @click="region = ''">Global</button>
        <button v-for="r in ['EU','NA','SA','OC','AS-AF']" :key="r" :class="{active: region === r}" @click="region = r">{{ r }}</button>
      </div>
      <span class="label">Mode</span>
      <div class="pill-group">
        <button v-for="m in ['1on1','2on2','4on4']" :key="m" :class="{active: mode === m}" @click="mode = m">{{ m }}</button>
      </div>
      <span class="label">Min matches</span>
      <div class="pill-group">
        <button v-for="n in [10, 20, 50, 100, 250]" :key="n" :class="{active: minMatches === n}" @click="minMatches = n">{{ n }}</button>
      </div>
      <span class="label">Active</span>
      <div class="pill-group">
        <button :class="{active: activeOnly}" @click="activeOnly = true">Last 90d</button>
        <button :class="{active: !activeOnly}" @click="activeOnly = false">All time</button>
      </div>
      <input v-model="search" type="text" placeholder="Filter by name…" class="search">
      <span class="count">{{ filtered.length }} of {{ current.length }}</span>
    </div>

    <div v-if="pending" class="placeholder">Loading rankings…</div>
    <div v-else-if="!current.length" class="placeholder">
      No {{ mode }} ratings yet. Only 1on1 has been rated so far (Phase A).
    </div>

    <div v-else class="list">
      <!-- Column header row -->
      <div class="header-row">
        <span class="center">Rank</span>
        <span></span>
        <span>Player</span>
        <span>Tier</span>
        <span class="num">Rating · ± σ</span>
        <span class="num">Win rate</span>
        <span class="num">Matches</span>
      </div>

      <a v-for="p in filtered.slice(0, 500)" :key="p.canonical_id"
         :href="profileHref(p.canonical_id)"
         :class="['row', p.rank === 1 ? 'top1' : p.rank === 2 ? 'top2' : p.rank === 3 ? 'top3' : '']">
        <div class="rank">#{{ p.rank }}</div>
        <div class="avatar">{{ (p.display || '?')[0].toUpperCase() }}</div>
        <div class="id">
          <div class="name">
            {{ p.display }}
            <span v-if="p.region" class="region-pill" v-tip="`Primary region · ${Math.round((p.region_confidence||0)*100)}% of matches played on ${p.region} servers`">{{ p.region }}</span>
          </div>
          <div class="meta">last seen {{ fmtDate(p.last_match) }}</div>
        </div>
        <div class="tier-cell">
          <span v-if="p.tier" class="tier-badge"
                v-rtip="tierRtip(p.tier)"
                :style="{ color: p.tier.color, borderColor: p.tier.color, background: p.tier.color + '14' }">
            {{ p.tier.name }}
          </span>
          <span v-if="p.provisional" class="prov-badge"
                v-rtip="provisionalRtip(p)">
            ?
          </span>
        </div>
        <div class="rating">
          <span v-rtip="consRtip(p)">{{ Math.round(p.conservative) }}</span>
          <div class="sigma" v-rtip="musigmaRtip(p)">μ {{ Math.round(p.mu) }} · ±σ {{ Math.round(p.sigma) }}</div>
          <div v-if="p.avg_ddr || p.avg_frag_diff != null" class="perf">
            <span v-if="p.avg_ddr" v-rtip="ddrRtip(p)"
                  :class="{ pos: p.avg_ddr >= 1, neg: p.avg_ddr < 1 }">DDR {{ p.avg_ddr.toFixed(2) }}</span>
            <span v-if="p.avg_frag_diff != null" v-rtip="fragDiffRtip(p)"
                  :class="{ pos: p.avg_frag_diff >= 0, neg: p.avg_frag_diff < 0 }">
              {{ p.avg_frag_diff >= 0 ? '+' : '' }}{{ p.avg_frag_diff.toFixed(1) }}
            </span>
          </div>
        </div>
        <div class="winbar">
          <div class="bar">
            <span class="w" :style="{ width: ((p.win_rate || 0) * 100) + '%' }"></span>
            <span class="l" :style="{ width: ((1 - (p.win_rate || 0)) * 100) + '%' }"></span>
          </div>
          <div class="pct">{{ fmtPct(p.win_rate) }}</div>
        </div>
        <div class="num matches">{{ p.matches.toLocaleString() }}</div>
      </a>

      <div v-if="filtered.length > 500" class="more">
        Showing first 500 of {{ filtered.length }}. Use search or raise min-matches to narrow.
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 20px; }
.head h1 { margin: 0 0 6px; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; }
.head-top { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
.maps-link {
  color: var(--accent); text-decoration: none; font-size: 13px; font-weight: 600;
  padding: 8px 14px; border: 1px solid rgba(20,230,192,0.3); border-radius: 8px;
  background: rgba(20,230,192,0.06); transition: all 0.12s;
}
.maps-link:hover { background: rgba(20,230,192,0.12); border-color: var(--accent); }

.controls {
  display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin-bottom: 24px;
}
.controls .label {
  color: var(--fg-3); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 700;
}
.pill-group {
  display: inline-flex; background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 3px; gap: 2px;
}
.pill-group button {
  background: transparent; border: 0; color: var(--fg-2);
  padding: 6px 14px; border-radius: 5px; cursor: pointer;
  font-family: inherit; font-size: 12px; font-weight: 600;
}
.pill-group button:hover { color: var(--fg); background: var(--panel-2); }
.pill-group button.active { background: var(--accent); color: var(--bg); }
.search {
  background: var(--panel); border: 1px solid var(--border); color: var(--fg);
  padding: 8px 14px; border-radius: 8px; font-size: 13px; min-width: 220px; font-family: inherit;
}
.search:focus { outline: none; border-color: var(--accent); }
.count { color: var(--fg-3); font-size: 12px; margin-left: auto; }

.list { display: flex; flex-direction: column; gap: 8px; }

.header-row {
  display: grid; grid-template-columns: 60px 56px 1fr 110px 110px 200px 80px;
  align-items: center; gap: 16px;
  padding: 8px 18px;
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700;
  color: var(--fg-3);
}
.header-row .num { text-align: right; }
.header-row .center { text-align: center; }

.row {
  display: grid; grid-template-columns: 60px 56px 1fr 110px 110px 200px 80px;
  align-items: center; gap: 16px;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 18px;
  text-decoration: none; color: inherit; transition: all 0.12s;
}

.tier-cell { display: flex; }
.tier-badge {
  display: inline-block; padding: 4px 10px; border-radius: 999px;
  border: 1px solid; font-size: 11px; font-weight: 700;
  letter-spacing: 0.04em; text-transform: uppercase;
}
.prov-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; margin-left: 6px; border-radius: 50%;
  background: rgba(245,158,11,0.15); color: var(--draw);
  border: 1px solid var(--draw); font-size: 10px; font-weight: 700;
  cursor: help;
}
.row:hover { border-color: var(--accent); transform: translateX(4px); }
.row.top1 { background: linear-gradient(90deg, rgba(251,191,36,0.06), var(--panel) 30%); border-color: rgba(251,191,36,0.4); }
.row.top2 { border-color: rgba(203,213,225,0.3); }
.row.top3 { border-color: rgba(184,115,51,0.3); }

.row .rank {
  font-size: 18px; font-weight: 800; color: var(--fg-3);
  font-variant-numeric: tabular-nums; text-align: center;
}
.row.top1 .rank { color: #fbbf24; }
.row.top2 .rank { color: #cbd5e1; }
.row.top3 .rank { color: #b87333; }

.row .avatar {
  width: 44px; height: 44px; border-radius: 10px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 900; color: var(--bg);
}
.row .id .name {
  font-size: 16px; font-weight: 700; letter-spacing: -0.01em;
  display: flex; align-items: center; gap: 8px;
}
.row .id .region-pill {
  display: inline-block; font-size: 9px; font-weight: 700;
  padding: 2px 6px; border-radius: 4px; letter-spacing: 0.06em;
  background: var(--panel-3); color: var(--fg-3); cursor: help;
}
.row .id .meta { color: var(--fg-3); font-size: 11px; margin-top: 2px; }

.row .rating {
  font-size: 24px; font-weight: 800; color: var(--accent);
  font-variant-numeric: tabular-nums; line-height: 1; text-align: right;
}
.row .rating .sigma { color: var(--fg-3); font-size: 11px; font-weight: 500; margin-top: 3px; }
.row .rating .perf {
  display: flex; gap: 8px; justify-content: flex-end; align-items: center;
  margin-top: 3px; font-size: 10px; font-weight: 700; letter-spacing: 0.02em;
  font-family: 'JetBrains Mono', monospace;
}
.row .rating .perf .pos { color: var(--win); }
.row .rating .perf .neg { color: var(--loss); }

.row .winbar { display: flex; align-items: center; gap: 8px; }
.row .winbar .bar {
  flex: 1; height: 6px; background: var(--panel-3); border-radius: 3px; overflow: hidden; display: flex;
}
.row .winbar .bar .w { background: var(--win); height: 100%; }
.row .winbar .bar .l { background: var(--loss); height: 100%; }
.row .winbar .pct { color: var(--fg-2); font-size: 11px; font-variant-numeric: tabular-nums; min-width: 38px; text-align: right; }

.row .matches { color: var(--fg-2); font-size: 13px; font-variant-numeric: tabular-nums; }

.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
.more { padding: 16px; text-align: center; color: var(--fg-3); font-size: 12px; }
</style>

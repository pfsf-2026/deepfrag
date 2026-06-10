<script setup>
const rankings = ref(null)
const pending = ref(false)  // initial view is baked into the prerender; not pending
const mode = ref('1on1')
const search = ref('')
const minMatches = ref(20)
const activity = ref('all')    // 'all' or '90'
const region = ref('')         // '' = Global; 'EU' / 'NA' / 'SA' / 'OC' / 'AS-AF'
const divFilter = ref('')      // '' = all divs; 'div0' / 'div1' / 'div2' / 'div3' / 'div4'

const df = useDeepFrag()

// SUPER-FAST first load: bake the default ranking (1on1, global) into the
// prerendered static HTML at BUILD time via useAsyncData. The homepage then
// paints instantly from the CDN edge with data already present — zero origin /
// DB call on first load (critical: cold-cache visitors used to wait on the
// origin DB, which locked up under post-deploy herds). Mode/region toggles
// lazy-fetch client-side from the (CDN-cached) API.
const { data: baked } = await useAsyncData(
  'rankings-home',
  () => $fetch(df.rankingsUrl('1on1', '')),
  { default: () => null }
)
rankings.value = baked.value

async function load() {
  pending.value = true
  try {
    rankings.value = await $fetch(df.rankingsUrl(mode.value, region.value))
  } catch (e) {
    console.error('[rankings] FAILED:', e)
  } finally {
    pending.value = false
  }
}
// Only refetch on an actual toggle — the initial (1on1/global) view is baked in.
watch([mode, region], load)

// Silent background refresh AFTER the instant baked paint: the baked standings
// are up to ~2h old (until the next scheduled rebuild), so quietly pull current
// data from the CDN-cached API and swap it in. No spinner — the baked data stays
// on screen until this resolves, so the page is instant AND self-freshening.
onMounted(() => {
  $fetch(df.rankingsUrl(mode.value, region.value))
    .then((d) => { rankings.value = d })
    .catch(() => { /* keep baked data on any failure */ })
})

// API returns { players: [...] }; static returns { modes: { 1on1: [...] } }.
const current = computed(() => df.useApi
  ? (rankings.value?.players || [])
  : (rankings.value?.modes?.[mode.value] || []))

// Rich-tooltip content helpers — kept inline since each is tied to one
// stat's explanation. Returns { title, body }.
function tierRtip(t) {
  const labels = {
    div0: 'Top 5% of rated players. Elite of elites.',
    div1: 'Top 6–10%. The top tier proper.',
    div2: 'Top 11–40%. Strong, multi-region competitive.',
    div3: 'Top 41–75%. Solid, regular competitors.',
    div4: 'Bottom 25%. Climbing or casual.'
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
  if (activity.value === '90') list = list.filter(p => p.active_90d)
  if (divFilter.value) list = list.filter(p => p.tier?.slug === divFilter.value)
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
        <NuxtLink to="/rankings/maps" class="maps-link" title="Browse per-map leaderboards">
          Per-map rankings →
        </NuxtLink>
      </div>
      <p class="sub">
        The rating shown is the <strong>conservative</strong> OpenSkill value (μ − 3σ) — that's what we sort by.
        μ is raw skill, σ is uncertainty (lower = more settled).
      </p>
    </div>

    <div class="controls">
      <select v-model="region" class="dd">
        <option value="">Global</option>
        <option value="EU">EU</option>
        <option value="NA">NA</option>
        <option value="SA">SA</option>
        <option value="OC">OC</option>
        <option value="AS-AF">AS-AF</option>
      </select>
      <select v-model="mode" class="dd">
        <option value="1on1">1on1</option>
        <option value="2on2">2on2</option>
        <option value="4on4">4on4</option>
      </select>
      <select v-model="divFilter" class="dd">
        <option value="">All divs</option>
        <option value="div0">Div 0</option>
        <option value="div1">Div 1</option>
        <option value="div2">Div 2</option>
        <option value="div3">Div 3</option>
        <option value="div4">Div 4</option>
      </select>
      <select v-model.number="minMatches" class="dd">
        <option :value="10">10+ matches</option>
        <option :value="20">20+ matches</option>
        <option :value="50">50+ matches</option>
        <option :value="100">100+ matches</option>
        <option :value="250">250+ matches</option>
      </select>
      <select v-model="activity" class="dd">
        <option value="all">All time</option>
        <option value="90">Last 90d</option>
      </select>
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
  display: flex; gap: 8px; align-items: center; margin-bottom: 24px; flex-wrap: nowrap;
}
.dd {
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--fg);
  padding: 7px 26px 7px 12px;
  border-radius: 6px;
  font-family: inherit; font-size: 12px; font-weight: 600;
  cursor: pointer;
  appearance: none; -webkit-appearance: none;
  /* tiny chevron arrow drawn with two gradients */
  background-image: linear-gradient(45deg, transparent 50%, var(--fg-3) 50%),
                    linear-gradient(135deg, var(--fg-3) 50%, transparent 50%);
  background-position: calc(100% - 12px) 50%, calc(100% - 8px) 50%;
  background-size: 4px 4px;
  background-repeat: no-repeat;
}
.dd:hover { border-color: var(--accent); color: var(--fg); }
.dd:focus { outline: none; border-color: var(--accent); }
.dd option { background: var(--panel); color: var(--fg); }
.search {
  background: var(--panel); border: 1px solid var(--border); color: var(--fg);
  padding: 7px 12px; border-radius: 6px; font-size: 12px; font-family: inherit;
  flex: 1; min-width: 0;
}
.search:focus { outline: none; border-color: var(--accent); }
.count { color: var(--fg-3); font-size: 12px; font-family: 'JetBrains Mono', monospace; white-space: nowrap; flex-shrink: 0; }

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

/* ── Mobile ─────────────────────────────────────────────────────────────── */
@media (max-width: 640px) {
  .page { padding: 18px 12px 64px; }
  .head h1 { font-size: 22px; }
  .head .sub { font-size: 12px; }
  .controls { flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
  .controls .search { flex: 1 1 140px; }
  .controls .count { width: 100%; text-align: right; }
  .header-row { display: none; }
  .row {
    grid-template-columns: 30px 40px minmax(0,1fr) auto;
    grid-template-areas:
      "rank avatar id     rating"
      "rank avatar tier   rating"
      "rank avatar winbar matches";
    gap: 4px 10px; padding: 11px 12px;
  }
  .row:hover { transform: none; }
  .row .rank   { grid-area: rank; font-size: 15px; align-self: center; }
  .row .avatar { grid-area: avatar; width: 38px; height: 38px; font-size: 16px; align-self: center; }
  .row .id     { grid-area: id; align-self: center; }
  .row .id .name { font-size: 15px; }
  .row .tier-cell { grid-area: tier; align-self: center; }
  .row .tier-badge { font-size: 10px; padding: 3px 8px; }
  .row .rating { grid-area: rating; font-size: 20px; align-self: center; }
  .row .winbar { grid-area: winbar; align-self: center; }
  .row .matches { grid-area: matches; align-self: center; text-align: right; }
}
</style>

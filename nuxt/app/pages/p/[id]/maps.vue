<script setup>
const route = useRoute()
const id = computed(() => String(route.params.id))

const profile = ref(null)
const pending = ref(true)
const windowKey = ref('365')
const sortKey = ref('rating')   // rating | matches | win_rate | avg_frag_diff
const filter = ref('')
const openMap = ref(null)        // currently expanded map bucket name
const df = useDeepFrag()

async function loadProfile() {
  pending.value = true
  try {
    const url = df.useApi
      ? `${df.profileUrl(id.value)}/full?window=${windowKey.value}`
      : df.profileUrl(id.value)
    const r = await fetch(url)
    if (!r.ok) throw new Error(r.status)
    profile.value = await r.json()
  } catch {
    profile.value = null
  } finally {
    pending.value = false
  }
}
onMounted(loadProfile)
watch(id, loadProfile)
// In API mode each window is a separate fetch; static mode has all windows baked in.
watch(windowKey, () => { if (df.useApi) loadProfile() })

const w = computed(() => profile.value?.windows?.[windowKey.value] || {})
const mapRatings = computed(() => profile.value?.map_ratings_1on1 || {})
const headToHead = computed(() => w.value.head_to_head_1on1 || [])

// Per-map rows joined with per-map ELO. Maps with no rating still show
// in the table (matches/winrate/etc) but the rating column reads "—".
const MIN_MAP_MATCHES = 5  // hide one-off/two-game maps from the table

const rows = computed(() => {
  const list = w.value.by_map_1on1 || []
  const f = filter.value.trim().toLowerCase()
  return list
    .filter(r => (r.matches || 0) >= MIN_MAP_MATCHES)
    .filter(r => !f || r.bucket.toLowerCase().includes(f))
    .map((r) => {
      const rt = mapRatings.value[r.bucket]
      return {
        ...r,
        rating: rt?.conservative ?? null,
        mu: rt?.mu ?? null,
        sigma: rt?.sigma ?? null,
        rank: rt?.rank ?? null,
        total_rated: rt?.total_rated ?? null
      }
    })
})

// Sort handles nulls by pushing them to the bottom regardless of direction
// (so an unrated map never sneaks to the top when sorting by rating desc).
const sorted = computed(() => {
  const k = sortKey.value
  return [...rows.value].sort((a, b) => {
    const av = a[k]
    const bv = b[k]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return bv - av
  })
})

// Summary box on the right rail: aggregates over the current window's rated maps.
const summary = computed(() => {
  const rated = rows.value.filter(r => r.rating != null)
  if (!rated.length) return null
  const best = rated.reduce((a, b) => a.rating > b.rating ? a : b)
  const worst = rated.reduce((a, b) => a.rating < b.rating ? a : b)
  const avg = rated.reduce((s, r) => s + r.rating, 0) / rated.length
  return {
    count: rated.length,
    avg: Math.round(avg),
    best,
    worst,
    spread: Math.round(best.rating - worst.rating)
  }
})

// Per-map opponents: fetched lazily from the API the first time a map is
// expanded, then cached in this dict so re-expanding is instant.
const mapOpponents = ref({})       // { mapName: [{opponent, wins, losses, win_rate, ...}] }
const mapOpponentsLoading = ref({}) // { mapName: bool }

async function ensureMapOpponents(mapName) {
  if (!mapName || mapOpponents.value[mapName] || mapOpponentsLoading.value[mapName]) return
  const url = df.mapOpponentsUrl(id.value, mapName)
  if (!url) {
    // Static-JSON mode: no per-map H2H available, fall back to global.
    mapOpponents.value[mapName] = headToHead.value.slice(0, 8)
    return
  }
  mapOpponentsLoading.value[mapName] = true
  try {
    const r = await fetch(url)
    if (r.ok) {
      const data = await r.json()
      mapOpponents.value[mapName] = data.opponents || []
    } else {
      mapOpponents.value[mapName] = []
    }
  } catch {
    mapOpponents.value[mapName] = []
  } finally {
    mapOpponentsLoading.value[mapName] = false
  }
}

watch(openMap, (m) => { if (m) ensureMapOpponents(m) })

function opponentsForMap(mapName) {
  return mapOpponents.value[mapName] || headToHead.value.slice(0, 4)
}

function toggleOpen(bucket) { openMap.value = openMap.value === bucket ? null : bucket }
function thumb(name) { return name ? name[0].toUpperCase() : '?' }
function fmtPct(v) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }
function fmtNum(v) { return v == null ? '—' : Number(v).toLocaleString() }
function fmtDec(v, d = 1) { return v == null ? '—' : Number(v).toFixed(d) }
function fmtDate(v) { return v == null ? '—' : new Date(v).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) }

useHead({ title: () => profile.value ? `Maps · ${profile.value.player} · DeepFrag` : 'Maps · DeepFrag' })
</script>

<template>
  <div class="page">
    <div v-if="pending" class="placeholder">Loading…</div>
    <div v-else-if="!profile" class="placeholder">No profile data for <code>{{ id }}</code>.</div>

    <template v-else>
      <div class="hero">
        <NuxtLink :to="`/p/${encodeURIComponent(id)}`" class="back">← {{ profile.player }}</NuxtLink>
        <h1>Maps</h1>
        <div class="sub">1on1 per-map ELO + stats</div>
      </div>

      <div class="controls">
        <span class="ctl-label">Window</span>
        <div class="pill-group">
          <button v-for="wk in ['90', '365', 'all']" :key="wk" :class="{active: windowKey === wk}" @click="windowKey = wk">
            {{ wk === 'all' ? 'All time' : wk + 'd' }}
          </button>
        </div>
      </div>

      <div class="grid">
        <div class="table-wrap">
          <div class="table-controls">
            <input v-model="filter" placeholder="Filter maps…" />
            <span class="hint">Sort:</span>
            <button class="sort-btn" :class="{active: sortKey === 'rating'}" @click="sortKey = 'rating'">Rating</button>
            <button class="sort-btn" :class="{active: sortKey === 'matches'}" @click="sortKey = 'matches'">Matches</button>
            <button class="sort-btn" :class="{active: sortKey === 'win_rate'}" @click="sortKey = 'win_rate'">Win rate</button>
            <button class="sort-btn" :class="{active: sortKey === 'avg_frag_diff'}" @click="sortKey = 'avg_frag_diff'">Δ frag</button>
          </div>

          <table>
            <thead>
              <tr>
                <th>Map</th>
                <th class="num">Rating</th>
                <th class="num">Rank</th>
                <th class="num">Matches</th>
                <th>Win rate</th>
                <th class="num">Δ frag</th>
                <th class="num">LG</th>
                <th class="num">RL</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="m in sorted" :key="m.bucket">
                <tr class="map-row" :class="{open: openMap === m.bucket}" @click="toggleOpen(m.bucket)">
                  <td>
                    <div class="map-cell">
                      <span class="chev">▶</span>
                      <div class="map-thumb">{{ thumb(m.bucket) }}</div>
                      <span class="map-name">{{ m.bucket }}</span>
                    </div>
                  </td>
                  <td class="num">
                    <span v-if="m.rating != null" class="rating-cell">
                      <span class="v">{{ Math.round(m.rating) }}</span>
                      <span class="s">±{{ Math.round(m.sigma) }}</span>
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="num">
                    <NuxtLink v-if="m.rank" :to="`/rankings/maps/${encodeURIComponent(m.bucket)}`"
                              class="rank-pill rank-pill-link" :class="{top: m.rank <= 20}"
                              @click.stop title="Open full rankings for this map">
                      #{{ m.rank }} / {{ m.total_rated }}
                    </NuxtLink>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="num">{{ fmtNum(m.matches) }}</td>
                  <td>
                    <div class="wr-bar" :class="{bad: (m.win_rate || 0) < 0.5}">
                      <div class="track"><div class="fill" :style="{width: ((m.win_rate || 0) * 100) + '%'}" /></div>
                      <span class="pct">{{ fmtPct(m.win_rate) }}</span>
                    </div>
                  </td>
                  <td class="num diff" :class="(m.avg_frag_diff || 0) >= 0 ? 'pos' : 'neg'">{{ fmtDec(m.avg_frag_diff) }}</td>
                  <td class="num">{{ fmtPct(m.lg_accuracy) }}</td>
                  <td class="num">{{ fmtPct(m.rl_accuracy) }}</td>
                </tr>
                <tr class="detail-row" :class="{open: openMap === m.bucket}">
                  <td colspan="8">
                    <div class="detail-inner">
                      <div class="detail-pad" v-if="openMap === m.bucket">
                        <div class="detail-head">
                          <div>
                            <div class="name">{{ m.bucket }}</div>
                            <div class="sub">1on1 · {{ windowKey === 'all' ? 'all time' : windowKey + 'd' }}</div>
                          </div>
                          <div v-if="m.rank" class="rank-pill top mono">#{{ m.rank }} of {{ m.total_rated }} rated</div>
                        </div>

                        <div v-if="m.rating != null" class="detail-rating">
                          <div class="big">{{ Math.round(m.rating) }}</div>
                          <div class="meta">
                            <span class="label">Per-map ELO</span>
                            μ {{ Math.round(m.mu) }} · σ {{ Math.round(m.sigma) }}
                          </div>
                        </div>
                        <div v-else class="detail-rating">
                          <div class="big muted">—</div>
                          <div class="meta">
                            <span class="label">Per-map ELO</span>
                            Need ≥5 matches on this map to rate
                          </div>
                        </div>

                        <div class="detail-stats">
                          <div class="detail-stat"><span class="l">Matches</span><span class="v">{{ fmtNum(m.matches) }}</span></div>
                          <div class="detail-stat"><span class="l">W – L</span><span class="v">{{ m.wins }} – {{ m.losses }}</span></div>
                          <div class="detail-stat"><span class="l">Win rate</span><span class="v">{{ fmtPct(m.win_rate) }}</span></div>
                          <div class="detail-stat"><span class="l">Δ frag</span><span class="v" :class="(m.avg_frag_diff || 0) >= 0 ? 'pos' : 'neg'">{{ fmtDec(m.avg_frag_diff) }}</span></div>
                          <div class="detail-stat"><span class="l">Avg frags</span><span class="v">{{ fmtDec(m.avg_frags) }}</span></div>
                          <div class="detail-stat"><span class="l">LG acc</span><span class="v">{{ fmtPct(m.lg_accuracy) }}</span></div>
                          <div class="detail-stat"><span class="l">RL acc</span><span class="v">{{ fmtPct(m.rl_accuracy) }}</span></div>
                          <div class="detail-stat"><span class="l">Last played</span><span class="v sm">{{ fmtDate(m.last_played) }}</span></div>
                        </div>

                        <div class="detail-extra">
                          <div class="detail-card">
                            <h4>Top opponents on {{ m.bucket }}</h4>
                            <div v-if="mapOpponentsLoading[m.bucket]" class="muted" style="font-size:12px;">Loading…</div>
                            <template v-else>
                              <div v-for="o in opponentsForMap(m.bucket)" :key="o.opponent" class="opp-row">
                                <NuxtLink v-if="o.opponent_canonical_id"
                                          :to="`/p/${encodeURIComponent(o.opponent_canonical_id)}`"
                                          class="opp-name opp-name-link" @click.stop>{{ o.opponent }}</NuxtLink>
                                <span v-else class="opp-name">{{ o.opponent }}</span>
                                <span class="opp-rec">{{ o.wins }} – {{ o.losses }}</span>
                                <span class="opp-wr" :class="(o.win_rate || 0) >= 0.5 ? 'pos' : 'neg'">{{ Math.round((o.win_rate || 0) * 100) }}%</span>
                              </div>
                              <div v-if="!opponentsForMap(m.bucket).length" class="muted" style="font-size:12px;">No opponent data</div>
                            </template>
                          </div>
                          <div class="detail-card placeholder-card">
                            <h4>AI insight</h4>
                            <div class="ai-placeholder">
                              <div class="ai-icon">AI</div>
                              <div>Coaching insights for this map are coming soon. Will analyze your demos to surface map-specific RA cycles, spawn control, and weapon timing patterns vs top players.</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="!sorted.length">
                <td colspan="8" class="empty">No maps in this window.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <aside class="side">
          <div v-if="summary" class="summary-box">
            <h3>Summary</h3>
            <div class="summary-row"><span class="k">Maps rated</span><span class="v">{{ summary.count }}</span></div>
            <div class="summary-row"><span class="k">Avg rating</span><span class="v">{{ summary.avg }}</span></div>
            <div class="summary-row"><span class="k">Best</span><span class="v">{{ summary.best.bucket }} {{ Math.round(summary.best.rating) }}</span></div>
            <div class="summary-row"><span class="k">Worst</span><span class="v">{{ summary.worst.bucket }} {{ Math.round(summary.worst.rating) }}</span></div>
            <div class="summary-row"><span class="k">Spread</span><span class="v">{{ summary.spread }}</span></div>
          </div>
          <div class="ai-card">
            <div class="ai-icon">AI</div>
            <div>
              <div class="ai-label">Coming soon</div>
              <div class="ai-text">Per-map coaching insights — where to grind, which maps you're underrated on, and which to drop from your pool.</div>
            </div>
          </div>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1400px; margin: 0 auto; padding: 32px 40px 80px; }
.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
.muted { color: var(--fg-3); }
.mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }

.hero { margin-bottom: 18px; }
.hero .back {
  color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600;
  display: inline-block; margin-bottom: 8px;
}
.hero .back:hover { color: var(--accent); }
.hero h1 { margin: 0; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.hero .sub { color: var(--fg-3); font-size: 13px; margin-top: 4px; }

.controls { display: flex; gap: 12px; align-items: center; margin-bottom: 18px; flex-wrap: wrap; }
.ctl-label { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
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

.grid { display: grid; grid-template-columns: 1fr 300px; gap: 16px; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }

.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.table-controls {
  display: flex; align-items: center; gap: 10px; padding: 12px 16px;
  border-bottom: 1px solid var(--border); background: var(--panel-2);
  flex-wrap: wrap;
}
.table-controls input {
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  color: var(--fg); padding: 6px 10px; font-size: 13px; width: 200px;
  font-family: inherit;
}
.table-controls input::placeholder { color: var(--fg-3); }
.table-controls .hint { color: var(--fg-3); font-size: 12px; }
.table-controls .sort-btn {
  background: transparent; border: 0; color: var(--fg-3); font-size: 12px;
  padding: 4px 10px; border-radius: 5px; cursor: pointer; font-family: inherit; font-weight: 600;
}
.table-controls .sort-btn:hover { color: var(--fg); }
.table-controls .sort-btn.active { color: var(--accent); background: rgba(20,230,192,0.08); }

table { width: 100%; border-collapse: collapse; }
thead th {
  text-align: left; font-size: 10px; font-weight: 600; color: var(--fg-3);
  letter-spacing: 1px; text-transform: uppercase;
  padding: 10px 14px; border-bottom: 1px solid var(--border); user-select: none;
}
thead th.num { text-align: right; }

tbody td {
  padding: 11px 14px; border-bottom: 1px solid var(--border);
  font-size: 13px; vertical-align: middle;
}
tbody td.num { text-align: right; font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
tbody tr.map-row { cursor: pointer; transition: background 0.12s; }
tbody tr.map-row:hover { background: var(--panel-2); }
tbody tr.map-row.open { background: var(--panel-2); }
tbody tr.map-row.open td { border-bottom-color: transparent; }
tbody tr.map-row.open td:first-child { border-left: 2px solid var(--accent); padding-left: 12px; }

.chev { display: inline-block; transition: transform 0.18s; color: var(--fg-3); font-size: 10px; margin-right: 6px; }
.map-row.open .chev { transform: rotate(90deg); color: var(--accent); }

.map-cell { display: flex; align-items: center; gap: 8px; }
.map-thumb {
  width: 28px; height: 28px; border-radius: 6px; background: var(--panel-3);
  color: var(--fg-3); display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 11px; font-family: 'JetBrains Mono', monospace;
}
.map-name { font-weight: 600; }

.rating-cell { display: inline-flex; align-items: baseline; gap: 6px; justify-content: flex-end; }
.rating-cell .v { color: var(--accent); font-weight: 700; }
.rating-cell .s { color: var(--fg-3); font-size: 10px; }

.rank-pill {
  display: inline-block; padding: 2px 7px; border-radius: 999px;
  font-family: 'JetBrains Mono', monospace; font-size: 10px;
  background: var(--panel-3); color: var(--fg-2);
}
.rank-pill.top { background: rgba(245,158,11,0.14); color: var(--draw); }
.rank-pill-link { text-decoration: none; cursor: pointer; transition: opacity 0.12s; display: inline-block; }
.rank-pill-link:hover { opacity: 0.75; text-decoration: underline; }

.wr-bar { display: inline-flex; align-items: center; gap: 8px; min-width: 110px; }
.wr-bar .track { width: 60px; height: 6px; background: var(--panel-3); border-radius: 3px; overflow: hidden; }
.wr-bar .fill { height: 100%; background: var(--accent); }
.wr-bar.bad .fill { background: var(--loss); }
.wr-bar .pct { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg-2); }

.diff.pos { color: var(--win); }
.diff.neg { color: var(--loss); }

tr.detail-row td { padding: 0; border-bottom: 1px solid var(--border); background: var(--panel-2); }
.detail-row.open td { border-left: 2px solid var(--accent); }
.detail-inner { max-height: 0; overflow: hidden; transition: max-height 0.25s ease; }
.detail-row.open .detail-inner { max-height: 800px; }
.detail-pad { padding: 18px 22px 20px; }

.detail-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.detail-head .name { font-size: 20px; font-weight: 700; }
.detail-head .sub { color: var(--fg-3); font-size: 11px; margin-top: 3px; font-family: 'JetBrains Mono', monospace; }

.detail-rating { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.detail-rating .big {
  font-family: 'JetBrains Mono', monospace; font-size: 38px; font-weight: 700;
  color: var(--accent); line-height: 1;
}
.detail-rating .big.muted { color: var(--fg-3); }
.detail-rating .meta { color: var(--fg-2); font-size: 12px; }
.detail-rating .meta .label {
  color: var(--fg-3); font-size: 9px; letter-spacing: 1px; text-transform: uppercase;
  display: block; margin-bottom: 2px;
}

.detail-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 14px; }
.detail-stat {
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 12px; display: flex; flex-direction: column; gap: 3px;
}
.detail-stat .l { font-size: 9px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 1px; }
.detail-stat .v { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; }
.detail-stat .v.sm { font-size: 13px; }
.detail-stat .v.pos { color: var(--win); }
.detail-stat .v.neg { color: var(--loss); }

.detail-extra { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.detail-card {
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 14px;
}
.detail-card h4 {
  margin: 0 0 8px; font-size: 10px; letter-spacing: 1px;
  text-transform: uppercase; color: var(--fg-3); font-weight: 600;
}
.opp-row {
  display: grid; grid-template-columns: 1fr auto auto; gap: 10px;
  padding: 4px 0; font-size: 12px; align-items: center;
}
.opp-row .opp-name { color: var(--fg); }
.opp-row .opp-name-link {
  text-decoration: none; color: var(--fg); cursor: pointer;
  border-bottom: 1px dotted transparent; transition: border-color 0.12s, color 0.12s;
}
.opp-row .opp-name-link:hover { color: var(--accent); border-bottom-color: var(--accent); }
.opp-row .opp-rec { font-family: 'JetBrains Mono', monospace; color: var(--fg-3); font-size: 11px; }
.opp-row .opp-wr {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  padding: 1px 6px; border-radius: 4px; min-width: 38px; text-align: center;
}
.opp-row .opp-wr.pos { background: rgba(34,197,94,0.12); color: var(--win); }
.opp-row .opp-wr.neg { background: rgba(239,68,68,0.12); color: var(--loss); }

.ai-placeholder {
  display: flex; gap: 10px; align-items: flex-start;
  font-size: 12px; color: var(--fg-2); line-height: 1.5;
}
.ai-placeholder .ai-icon {
  width: 26px; height: 26px; border-radius: 6px; background: rgba(20,230,192,0.12);
  color: var(--accent); display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 800; flex: 0 0 26px;
}

.side { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 24px; align-self: flex-start; }
.summary-box { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.summary-box h3 { margin: 0 0 10px 0; font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: var(--fg-3); }
.summary-row { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 0; font-size: 12px; }
.summary-row .k { color: var(--fg-2); }
.summary-row .v { font-family: 'JetBrains Mono', monospace; color: var(--fg); }

.ai-card {
  background: linear-gradient(135deg, rgba(20,230,192,0.06), rgba(6,182,212,0.04));
  border: 1px solid rgba(20,230,192,0.18);
  border-radius: 10px; padding: 14px 16px;
  display: flex; gap: 12px; align-items: flex-start;
}
.ai-card .ai-icon {
  width: 28px; height: 28px; border-radius: 7px; background: rgba(20,230,192,0.12);
  color: var(--accent); display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 800; flex: 0 0 28px;
}
.ai-card .ai-label { color: var(--accent); font-size: 10px; letter-spacing: 1px; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }
.ai-card .ai-text { color: var(--fg-2); font-size: 12px; line-height: 1.5; }

.empty { text-align: center; color: var(--fg-3); padding: 30px; font-style: italic; }
</style>

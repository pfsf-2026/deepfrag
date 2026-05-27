<script setup>
const df = useDeepFrag()
const servers = ref([])
const pending = ref(true)
const sortKey = ref('games')      // games | avg_rating | last_match | region
const filter = ref('')
const regionFilter = ref('')
const showInactive = ref(false)    // default OFF: only servers live in hub or active in last 90d
const openServer = ref(null)        // hostname
const detailCache = ref({})         // hostname → detail JSON
const detailLoading = ref({})       // hostname → bool

async function loadServers() {
  pending.value = true
  try {
    const base = (useRuntimeConfig().public.apiBase) || ''
    const params = new URLSearchParams()
    if (regionFilter.value) params.set('region', regionFilter.value)
    params.set('active', showInactive.value ? 'false' : 'true')
    const url = `${base}/api/servers?${params}`
    const r = await fetch(url)
    const data = await r.json()
    servers.value = data.servers || []
  } catch {
    servers.value = []
  } finally {
    pending.value = false
  }
}
// Auto-refresh server list every 60s so the live indicator + current map stay fresh.
// Browser tab visibility check: only poll when tab is active to avoid burning quota.
let refreshInterval = null
onMounted(() => {
  loadServers()
  refreshInterval = setInterval(() => {
    if (typeof document !== 'undefined' && !document.hidden) loadServers()
  }, 60_000)
})
onBeforeUnmount(() => { if (refreshInterval) clearInterval(refreshInterval) })
watch([regionFilter, showInactive], loadServers)

const filtered = computed(() => {
  const f = filter.value.trim().toLowerCase()
  let list = servers.value
  if (f) {
    list = list.filter(s => (s.hostname || '').toLowerCase().includes(f)
                         || (s.city || '').toLowerCase().includes(f)
                         || (s.country || '').toLowerCase().includes(f))
  }
  // Sort
  const sort = sortKey.value
  return [...list].sort((a, b) => {
    if (sort === 'games') return (b.games || 0) - (a.games || 0)
    if (sort === 'last_match') return (b.last_match || '').localeCompare(a.last_match || '')
    if (sort === 'region') return (a.region || 'zz').localeCompare(b.region || 'zz')
    return 0
  })
})

async function ensureDetail(hostname) {
  if (detailCache.value[hostname] || detailLoading.value[hostname]) return
  detailLoading.value[hostname] = true
  try {
    const base = (useRuntimeConfig().public.apiBase) || ''
    const r = await fetch(`${base}/api/servers/${encodeURIComponent(hostname)}/detail`)
    if (r.ok) detailCache.value[hostname] = await r.json()
  } catch { /* swallow */ } finally {
    detailLoading.value[hostname] = false
  }
}

function toggleOpen(hostname) {
  openServer.value = openServer.value === hostname ? null : hostname
  if (openServer.value) ensureDetail(openServer.value)
}

// ISO country code (US, SE, DE) → flag emoji. Falls back to globe if unmapped.
function flagEmoji(cc) {
  if (!cc || cc.length !== 2) return '🌐'
  try {
    return cc.toUpperCase().split('').map(c => String.fromCodePoint(c.charCodeAt(0) - 65 + 0x1F1E6)).join('')
  } catch { return '🌐' }
}

function modePct(s) {
  const total = (s.g_1on1 || 0) + (s.g_2on2 || 0) + (s.g_4on4 || 0)
  if (!total) return { p1: 0, p2: 0, p4: 0 }
  return {
    p1: Math.round((s.g_1on1 || 0) / total * 100),
    p2: Math.round((s.g_2on2 || 0) / total * 100),
    p4: Math.round((s.g_4on4 || 0) / total * 100)
  }
}

function fmtAgo(iso) {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso).getTime()
  const days = Math.floor(ms / 86400000)
  if (days < 1) return Math.floor(ms / 3600000) + 'h ago'
  if (days < 30) return days + 'd ago'
  if (days < 365) return Math.floor(days / 30) + 'mo ago'
  return Math.floor(days / 365) + 'y ago'
}

useHead({ title: 'Servers · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="head">
      <h1>Servers</h1>
      <p class="sub">
        Every QuakeWorld server we've seen matches on, geolocated. Click a row to dig in —
        top players, mode mix, activity over time.
      </p>
    </div>

    <div class="controls">
      <input v-model="filter" placeholder="Filter hostname, city, country…" class="search">
      <span class="label">Region</span>
      <div class="pill-group">
        <button :class="{active: regionFilter === ''}" @click="regionFilter = ''">All</button>
        <button v-for="r in ['EU','NA','SA','OC','AS','AF']" :key="r"
                :class="{active: regionFilter === r}" @click="regionFilter = r">{{ r }}</button>
      </div>
      <span class="label">Sort</span>
      <div class="pill-group">
        <button :class="{active: sortKey === 'games'}" @click="sortKey = 'games'">Most games</button>
        <button :class="{active: sortKey === 'last_match'}" @click="sortKey = 'last_match'">Recently active</button>
        <button :class="{active: sortKey === 'region'}" @click="sortKey = 'region'">Region</button>
      </div>
      <label class="toggle">
        <input type="checkbox" v-model="showInactive">
        <span>Show inactive</span>
      </label>
      <button class="refresh-btn" @click="loadServers" title="Refetch from API now">↻</button>
      <span class="count">{{ filtered.length }} servers</span>
    </div>

    <div v-if="pending" class="placeholder">Loading servers…</div>
    <div v-else-if="!filtered.length" class="placeholder">No servers match.</div>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Server</th>
            <th>Region</th>
            <th class="num">Total games</th>
            <th>
              Mode mix
              <span class="mode-legend">
                <span class="dot d-1"></span>1on1
                <span class="dot d-2"></span>2on2
                <span class="dot d-4"></span>4on4
              </span>
            </th>
            <th class="num">Players</th>
            <th class="num">Last match</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="s in filtered" :key="s.hostname">
            <tr class="server-row" :class="{open: openServer === s.hostname}" @click="toggleOpen(s.hostname)">
              <td>
                <div class="server-cell">
                  <span class="chev">▶</span>
                  <span class="flag">{{ flagEmoji(s.country) }}</span>
                  <div>
                    <div class="server-name">
                      <span v-if="s.is_live" class="live-pulse" title="Server is online right now">●</span>
                      {{ s.hostname }}
                      <span v-if="s.port_count > 1" class="port-count" :title="`Ports: ${s.ports}`">{{ s.port_count }} ports</span>
                    </div>
                    <div class="server-meta">{{ s.city || '—' }}{{ s.country ? ', ' + s.country : '' }}</div>
                  </div>
                </div>
              </td>
              <td><span class="region-pill">{{ s.region || '?' }}</span></td>
              <td class="num">{{ (s.games || 0).toLocaleString() }}</td>
              <td>
                <div class="mode-bar" :title="`1on1 ${modePct(s).p1}% · 2on2 ${modePct(s).p2}% · 4on4 ${modePct(s).p4}%`">
                  <span :style="{ width: modePct(s).p1 + '%', height: '100%', background: '#14e6c0', display: 'block' }"></span>
                  <span :style="{ width: modePct(s).p2 + '%', height: '100%', background: '#f59e0b', display: 'block' }"></span>
                  <span :style="{ width: modePct(s).p4 + '%', height: '100%', background: '#22c55e', display: 'block' }"></span>
                </div>
              </td>
              <td class="num">{{ s.players || 0 }}</td>
              <td class="num">{{ fmtAgo(s.last_match) }}</td>
            </tr>
            <tr class="detail-row" :class="{open: openServer === s.hostname}">
              <td colspan="6">
                <div class="detail-inner">
                  <div v-if="openServer === s.hostname" class="detail-pad">

                    <div v-if="detailLoading[s.hostname] && !detailCache[s.hostname]" class="muted center">Loading detail…</div>

                    <template v-else-if="detailCache[s.hostname]">
                      <!-- 6 hero stats: totals + weekly rate -->
                      <div class="bigs bigs-6">
                        <div class="big"><div class="v">{{ (detailCache[s.hostname].stats.games || 0).toLocaleString() }}</div><div class="l">Games</div></div>
                        <div class="big"><div class="v">{{ detailCache[s.hostname].stats.players || 0 }}</div><div class="l">Unique players</div></div>
                        <div class="big"><div class="v">{{ Math.round(detailCache[s.hostname].stats.avg_ping || 0) }}<span class="unit">ms</span></div><div class="l">Avg ping</div></div>
                        <div class="big"><div class="v">{{ fmtAgo(detailCache[s.hostname].stats.first_match) }}</div><div class="l">Active since</div></div>
                        <div class="big"><div class="v">{{ (detailCache[s.hostname].stats.avg_games_per_week_3mo || 0).toFixed(0) }}<span class="unit">/wk</span></div><div class="l">Avg games · 3mo</div></div>
                        <div class="big"><div class="v">{{ (detailCache[s.hostname].stats.avg_games_per_week_12mo || 0).toFixed(0) }}<span class="unit">/wk</span></div><div class="l">Avg games · 12mo</div></div>
                      </div>
                      <div v-if="detailCache[s.hostname].stats.port_count > 1" class="ports-note">
                        <strong>{{ detailCache[s.hostname].stats.port_count }} game servers</strong> on this host:
                        <span class="mono">{{ detailCache[s.hostname].stats.ports }}</span>
                      </div>

                      <!-- Per-port live state. One card per game-server port.
                           Each port shows its own map / mode / player list — no
                           more aggregating across The-Den:28501/28502/etc. -->
                      <div v-if="detailCache[s.hostname].ports?.length" class="ports-grid">
                        <div v-for="p in detailCache[s.hostname].ports" :key="p.hostname" class="port-card" :class="{live: p.is_live}">
                          <div class="port-head">
                            <div class="port-id">
                              <span v-if="p.is_live" class="port-live-dot">●</span>
                              <span class="port-num mono">:{{ p.port }}</span>
                              <span v-if="p.current_mode" class="port-mode mono">{{ p.current_mode }}</span>
                              <span v-if="p.current_map" class="port-map">{{ p.current_map }}</span>
                            </div>
                            <div class="port-meta">
                              <span class="mono">{{ (p.players?.filter(c => !c.is_bot)?.length) || p.current_players || 0 }}/{{ p.max_clients || '?' }}</span>
                              <a v-if="p.qtv_stream_url" :href="p.qtv_stream_url" target="_blank" class="qtv-mini" @click.stop>QTV</a>
                            </div>
                          </div>
                          <div v-if="p.players?.length" class="port-players">
                            <div v-for="(c, i) in p.players" :key="c.name + i" class="port-player" :class="{ bot: c.is_bot, spec: !c.frags && c.frags !== 0 }">
                              <span class="pp-name">{{ c.name || '?' }}</span>
                              <span v-if="c.team" class="pp-team mono">[{{ c.team }}]</span>
                              <span v-if="c.frags != null" class="pp-frags mono">{{ c.frags }}</span>
                              <span v-if="c.ping != null" class="pp-ping mono">{{ c.ping }}ms</span>
                              <span v-if="c.is_bot" class="pp-flag">BOT</span>
                            </div>
                          </div>
                          <div v-else-if="!p.is_live" class="port-empty muted">offline (last seen {{ fmtAgo(p.last_seen_live) }})</div>
                          <div v-else class="port-empty muted">empty</div>
                        </div>
                      </div>

                      <!-- Activity heatmap — span auto-adjusts to server age (up to 3 years) -->
                      <div class="detail-card">
                        <h4>
                          Activity · {{ detailCache[s.hostname].weekly_activity.length }} weeks
                          <span v-if="detailCache[s.hostname].weekly_activity.length > 60" class="muted small" style="font-weight:400">(full history)</span>
                        </h4>
                        <ActivityHeatmap :weekly="detailCache[s.hostname].weekly_activity" />
                      </div>

                      <!-- Top players: two columns -->
                      <div class="top-split">
                        <div class="detail-card">
                          <h4>Top players by match count</h4>
                          <div v-for="(p, i) in detailCache[s.hostname].top_by_matches" :key="p.canonical_id" class="top-row">
                            <span class="rank">#{{ i + 1 }}</span>
                            <NuxtLink :to="`/p/${encodeURIComponent(p.canonical_id)}`" class="name" @click.stop>{{ p.display }}</NuxtLink>
                            <span class="val">{{ p.games }}m</span>
                          </div>
                        </div>
                        <div class="detail-card">
                          <h4>Top 1on1 ratings (10+ games here)</h4>
                          <div v-for="(p, i) in detailCache[s.hostname].top_by_rating" :key="p.canonical_id" class="top-row">
                            <span class="rank">#{{ i + 1 }}</span>
                            <NuxtLink :to="`/p/${encodeURIComponent(p.canonical_id)}`" class="name" @click.stop>{{ p.display }}</NuxtLink>
                            <span v-if="p.tier" class="tier" :style="{ color: p.tier.color, borderColor: p.tier.color, background: p.tier.color + '14' }">{{ p.tier.name }}</span>
                            <span class="val">{{ Math.round(p.conservative) }}</span>
                          </div>
                          <div v-if="!detailCache[s.hostname].top_by_rating.length" class="muted small">No rated players with ≥10 games here.</div>
                        </div>
                      </div>

                      <!-- Top maps + mode breakdown -->
                      <div class="top-split">
                        <div class="detail-card">
                          <h4>Most-played maps</h4>
                          <div v-for="m in detailCache[s.hostname].top_maps" :key="m.match_map" class="top-row">
                            <NuxtLink :to="`/rankings/maps/${encodeURIComponent(m.match_map)}`" class="name" @click.stop>{{ m.match_map }}</NuxtLink>
                            <span class="val">{{ (m.games || 0).toLocaleString() }} games</span>
                          </div>
                        </div>
                        <div class="detail-card">
                          <h4>Mode breakdown</h4>
                          <div class="mode-detail">
                            <div class="md-row"><span class="dot d-1"></span>1on1<span class="md-val">{{ (detailCache[s.hostname].stats.g_1on1 || 0).toLocaleString() }}</span></div>
                            <div class="md-row"><span class="dot d-2"></span>2on2<span class="md-val">{{ (detailCache[s.hostname].stats.g_2on2 || 0).toLocaleString() }}</span></div>
                            <div class="md-row"><span class="dot d-4"></span>4on4<span class="md-val">{{ (detailCache[s.hostname].stats.g_4on4 || 0).toLocaleString() }}</span></div>
                            <div class="md-row" style="margin-top:6px;padding-top:8px;border-top:1px solid var(--border);">
                              <span style="color:var(--fg-3)">Avg games · 3mo</span>
                              <span class="md-val">{{ (detailCache[s.hostname].stats.avg_games_per_week_3mo || 0).toFixed(1) }}/wk</span>
                            </div>
                            <div class="md-row">
                              <span style="color:var(--fg-3)">Avg games · 12mo</span>
                              <span class="md-val">{{ (detailCache[s.hostname].stats.avg_games_per_week_12mo || 0).toFixed(1) }}/wk</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </template>

                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1320px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 20px; }
.head h1 { margin: 0 0 6px; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; }
.muted { color: var(--fg-3); }
.center { text-align: center; padding: 30px; }
.small { font-size: 12px; }

.controls { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }
.controls .label { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
.search { background: var(--panel); border: 1px solid var(--border); color: var(--fg); padding: 8px 14px; border-radius: 8px; font-size: 13px; min-width: 240px; font-family: inherit; }
.pill-group { display: inline-flex; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 3px; gap: 2px; }
.pill-group button { background: transparent; border: 0; color: var(--fg-2); padding: 6px 14px; border-radius: 5px; cursor: pointer; font-family: inherit; font-size: 12px; font-weight: 600; }
.pill-group button:hover { color: var(--fg); background: var(--panel-2); }
.pill-group button.active { background: var(--accent); color: var(--bg); }
.count { color: var(--fg-3); font-size: 12px; margin-left: auto; }

.table-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
thead th { text-align: left; font-size: 10px; font-weight: 600; color: var(--fg-3); letter-spacing: 1px; text-transform: uppercase; padding: 10px 14px; border-bottom: 1px solid var(--border); }
thead th.num { text-align: right; }

.mode-legend { display: inline-flex; gap: 8px; margin-left: 12px; font-size: 9px; color: var(--fg-3); font-weight: 600; }
.mode-legend .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }
.dot.d-1 { background: #14e6c0; }
.dot.d-2 { background: #f59e0b; }
.dot.d-4 { background: #22c55e; }

tbody td { padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
tbody td.num { text-align: right; font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
tbody tr.server-row { cursor: pointer; transition: background 0.12s; }
tbody tr.server-row:hover, tbody tr.server-row.open { background: var(--panel-2); }
tbody tr.server-row.open td { border-bottom-color: transparent; }
tbody tr.server-row.open td:first-child { border-left: 2px solid var(--accent); padding-left: 12px; }

.chev { display: inline-block; transition: transform 0.18s; color: var(--fg-3); font-size: 10px; margin-right: 8px; }
.server-row.open .chev { transform: rotate(90deg); color: var(--accent); }
.server-cell { display: flex; align-items: center; gap: 8px; }
.flag { font-size: 18px; }
.server-name { font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.port-count {
  font-size: 10px; font-weight: 600; padding: 1px 6px;
  border-radius: 4px; background: var(--panel-3); color: var(--fg-3);
  letter-spacing: 0.04em; cursor: help;
}
.live-pulse {
  color: var(--win); font-size: 10px; cursor: help;
  animation: pulse-row 2s infinite ease-in-out;
}
@keyframes pulse-row { 0%, 100% { opacity: 1 } 50% { opacity: 0.35 } }

.toggle {
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  color: var(--fg-2); font-size: 12px; font-weight: 600;
}
.toggle input { accent-color: var(--accent); cursor: pointer; }

.refresh-btn {
  background: var(--panel); border: 1px solid var(--border); color: var(--fg-2);
  width: 32px; height: 32px; border-radius: 8px; cursor: pointer;
  font-size: 16px; font-weight: 700; font-family: inherit;
  transition: all 0.12s;
}
.refresh-btn:hover { color: var(--accent); border-color: var(--accent); transform: rotate(180deg); }
.server-meta { color: var(--fg-3); font-size: 11px; }
.region-pill { display: inline-block; padding: 3px 8px; border-radius: 999px; background: var(--panel-3); color: var(--fg-2); font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }

.mode-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; background: var(--panel-3); min-width: 140px; }
.mode-bar > span { display: block; height: 100%; }
.m-1 { background: #14e6c0; }
.m-2 { background: #f59e0b; }
.m-4 { background: #22c55e; }

/* expand */
tr.detail-row td { padding: 0; background: var(--panel-2); }
.detail-row.open td { border-left: 2px solid var(--accent); }
.detail-inner { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
.detail-row.open .detail-inner { max-height: 1400px; }
.detail-pad { padding: 20px 24px 24px; display: flex; flex-direction: column; gap: 14px; }

.bigs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.bigs-6 { grid-template-columns: repeat(6, 1fr); }
@media (max-width: 900px) { .bigs-6 { grid-template-columns: repeat(3, 1fr); } }
.ports-note {
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 14px; font-size: 12px; color: var(--fg-2);
}
.ports-note strong { color: var(--accent); }
.ports-note .mono { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg-3); margin-left: 6px; }

.live-now {
  display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
  background: linear-gradient(90deg, rgba(34,197,94,0.10), rgba(34,197,94,0.04));
  border: 1px solid rgba(34,197,94,0.35); border-radius: 8px; padding: 10px 14px;
  font-size: 12px; color: var(--fg-2);
}
.live-now strong { color: var(--win); letter-spacing: 0.08em; }
.live-now .live-dot {
  color: var(--win); font-size: 12px;
  animation: pulse 2s infinite ease-in-out;
}
.live-now .mono { font-family: 'JetBrains Mono', monospace; }
.live-now .qtv-link { color: var(--accent); text-decoration: none; font-weight: 600; }
.live-now .qtv-link:hover { text-decoration: underline; }
@keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.4 } }
.big { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
.big .v { font-family: 'JetBrains Mono', monospace; font-size: 22px; font-weight: 700; color: var(--accent); line-height: 1; }
.big .v .unit { font-size: 14px; color: var(--fg-3); margin-left: 2px; }
.big .l { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }

.detail-card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
.detail-card h4 { margin: 0 0 10px; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; color: var(--fg-3); font-weight: 600; }

.top-split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* Per-port live cards — one tile per (host:port). Live ports have a green
   left rail; offline ports show muted. Each lists current players (with
   frags / ping) for the active match on that specific port. */
.ports-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}
.port-card {
  background: var(--bg); border: 1px solid var(--border); border-left: 3px solid var(--border);
  border-radius: 8px; padding: 10px 12px; transition: border-color 0.12s;
}
.port-card.live { border-left-color: var(--win); background: linear-gradient(90deg, rgba(34,197,94,0.04), var(--bg) 30%); }
.port-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
.port-id { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.port-live-dot { color: var(--win); font-size: 10px; animation: pulse 2s infinite ease-in-out; }
.port-num { font-size: 12px; font-weight: 700; color: var(--fg); }
.port-mode {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: var(--panel-3); color: var(--fg-2); font-weight: 700; letter-spacing: 0.04em;
}
.port-map { font-size: 11px; color: var(--fg-2); font-weight: 600; }
.port-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--fg-3); }
.port-meta .qtv-mini { color: var(--accent); text-decoration: none; font-weight: 700; font-size: 10px; padding: 1px 6px; border: 1px solid var(--accent); border-radius: 3px; }
.port-meta .qtv-mini:hover { background: var(--accent); color: var(--bg); }

.port-players { display: flex; flex-direction: column; gap: 3px; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.port-player {
  display: grid; grid-template-columns: 1fr auto auto auto auto; gap: 6px; align-items: center;
  font-size: 12px; padding: 3px 0;
}
.port-player.bot { opacity: 0.6; }
.port-player.spec { opacity: 0.5; font-style: italic; }
.port-player .pp-name { color: var(--fg); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.port-player .pp-team { color: var(--fg-3); font-size: 10px; font-family: 'JetBrains Mono', monospace; }
.port-player .pp-frags { color: var(--accent); font-weight: 700; font-family: 'JetBrains Mono', monospace; min-width: 28px; text-align: right; }
.port-player .pp-ping { color: var(--fg-3); font-size: 10px; font-family: 'JetBrains Mono', monospace; min-width: 38px; text-align: right; }
.port-player .pp-flag { color: var(--fg-3); font-size: 9px; background: var(--panel-3); padding: 1px 4px; border-radius: 3px; font-weight: 700; letter-spacing: 0.06em; }
.port-empty { padding: 6px 0; font-size: 11px; text-align: center; }

.top-row { display: grid; grid-template-columns: 28px 1fr auto auto; gap: 8px; padding: 5px 0; font-size: 12px; align-items: center; }
.top-row .rank { color: var(--fg-3); font-family: 'JetBrains Mono', monospace; font-size: 10px; }
.top-row .name { font-weight: 600; color: var(--fg); text-decoration: none; border-bottom: 1px dotted transparent; }
.top-row .name:hover { color: var(--accent); border-bottom-color: var(--accent); }
.top-row .val { color: var(--fg-3); font-family: 'JetBrains Mono', monospace; font-size: 11px; min-width: 50px; text-align: right; }
.top-row .tier { padding: 1px 6px; border-radius: 999px; border: 1px solid; font-size: 9px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }

.mode-detail { display: flex; flex-direction: column; gap: 8px; }
.md-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.md-row .md-val { margin-left: auto; font-family: 'JetBrains Mono', monospace; color: var(--fg-2); }

.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
</style>

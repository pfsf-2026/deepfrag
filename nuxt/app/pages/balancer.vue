<script setup>
// Balancer — pick a live server, confirm the 8, get the most even 4v4 splits
// with win probabilities. Data: /api/balancer/servers (per-minute live rosters,
// names resolved to canonical ids) + /api/balance (validated split math).
const config = useRuntimeConfig()
const isBrowser = typeof window !== 'undefined'
const apiBase = isBrowser ? '' : (config.public.apiBase || '')

useHead({ title: 'Team Balancer · DeepFrag' })

const servers = ref([])
const loading = ref(true)
const picked = ref(null)            // selected server object
const sel = ref(new Set())          // selected cids
const extra = ref([])               // manually-added players {cid, display, mu}
const results = ref(null)
const balancing = ref(false)
const err = ref('')
const useMap = ref(true)

// manual add — autocomplete over the rated population
const allPlayers = ref([])
const addSearch = ref('')
const addMatch = computed(() => {
  const q = addSearch.value.trim().toLowerCase()
  if (q.length < 2) return []
  const taken = new Set(chosen.value.map(p => p.cid))
  return allPlayers.value
    .filter(x => !taken.has(x.canonical_id)
      && (x.display || x.canonical_id).toLowerCase().includes(q))
    .slice(0, 8)
})

async function load() {
  loading.value = true
  try {
    const r = await $fetch(`${apiBase}/api/balancer/servers`)
    servers.value = r.servers || []
  } catch (e) { console.error('[balancer] servers failed', e) }
  finally { loading.value = false }
  try {
    const r = await $fetch(`${apiBase}/api/players?limit=5000`)
    allPlayers.value = (r.players || [])
  } catch (e) {}
}

const roster = ref([])              // local mutable copy — identify edits it
const idFor = ref(null)             // raw name currently being identified
const idSearch = ref('')
function pick(s) {
  picked.value = s
  results.value = null
  err.value = ''
  extra.value = []
  roster.value = s.players.map(p => ({ ...p }))
  idFor.value = null
  const resolved = roster.value.filter(p => p.resolved)
  sel.value = new Set(resolved.slice(0, 8).map(p => p.cid))
}
const MAPS_4ON4 = ['dm2', 'dm3', 'e1m2', 'schloss', 'bravado', 'nova', 'catalyst', 'shifter']
const customMap = ref('')
function pickCustom() {
  picked.value = { hostname: 'What-if lobby', map: '', city: '', custom: true, players: [] }
  roster.value = []
  extra.value = []
  sel.value = new Set()
  results.value = null
  err.value = ''
  idFor.value = null
}
const idMatch = computed(() => {
  const q = idSearch.value.trim().toLowerCase()
  if (q.length < 2) return []
  const taken = new Set(chosen.value.map(p => p.cid))
  return allPlayers.value
    .filter(x => !taken.has(x.canonical_id)
      && (x.display || x.canonical_id).toLowerCase().includes(q))
    .slice(0, 8)
})
function identify(p, x) {
  p.cid = x.canonical_id
  p.display = (x.display || x.canonical_id) + '';
  p.resolved = true
  p.identified = true
  p.mu = null
  const n = new Set(sel.value); n.add(p.cid); sel.value = n
  idFor.value = null; idSearch.value = ''
  results.value = null
  // fire-and-forget: file the alias suggestion for admin review
  $fetch(`${apiBase}/api/balancer/identify`, {
    method: 'POST', body: { raw_name: p.name, canonical_id: p.cid }
  }).catch(() => {})
}
function toggle(cid) {
  if (!cid) return
  const n = new Set(sel.value)
  n.has(cid) ? n.delete(cid) : n.add(cid)
  sel.value = n
  results.value = null
}
function addExtra(x) {
  extra.value = [...extra.value, { cid: x.canonical_id, display: x.display || x.canonical_id, resolved: true }]
  const n = new Set(sel.value); n.add(x.canonical_id); sel.value = n
  addSearch.value = ''
  results.value = null
}
const chosen = computed(() => {
  const fromSrv = roster.value.filter(p => p.resolved && sel.value.has(p.cid))
  const fromExtra = extra.value.filter(p => sel.value.has(p.cid))
  const seen = new Set(); const out = []
  for (const p of [...fromSrv, ...fromExtra]) {
    if (!seen.has(p.cid)) { seen.add(p.cid); out.push(p) }
  }
  return out
})

async function balance() {
  err.value = ''
  const ids = chosen.value.map(p => p.cid)
  if (ids.length !== 8) { err.value = `Need exactly 8 players — ${ids.length} selected.`; return }
  balancing.value = true
  try {
    const q = new URLSearchParams({ players: ids.join(','), mode: '4on4' })
    const mp = (picked.value?.custom ? customMap.value : (picked.value?.map || '')).toLowerCase()
    if (useMap.value && mp) q.set('map', mp)
    results.value = await $fetch(`${apiBase}/api/balance?${q}`)
  } catch (e) {
    err.value = e?.data?.detail || 'Balance failed'
  } finally { balancing.value = false }
}

const splits = computed(() => {
  if (!results.value) return []
  return [results.value.best, ...(results.value.alternatives || []).slice(0, 2)]
})
function name(cid) {
  const p = (results.value?.players || []).find(x => x.cid === cid)
  return p?.display || cid
}
function mu(cid) {
  const p = (results.value?.players || []).find(x => x.cid === cid)
  return p ? Math.round(p.mu) : ''
}
function pct(p) { return `${(p * 100).toFixed(1)}%` }

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="head">
      <h1>Team Balancer</h1>
      <p class="sub">Pick a live server, confirm the eight, get the fairest 4v4 splits —
      powered by the same ratings engine as the ladder. Historic pickup games averaged 67/33;
      the best available split of the same lobby averages 52/48.</p>
    </div>

    <!-- STEP 1: pick a server -->
    <template v-if="!picked">
      <div v-if="loading" class="placeholder">Scanning live servers…</div>
      <div v-else-if="!servers.length" class="placeholder">
        No servers with players on them right now — but you can still
        <a href="#" @click.prevent="pickCustom()">build a what-if lobby</a> with any 8 players.
      </div>
      <div v-else class="srv-grid">
        <button class="srv-card whatif" @click="pickCustom()">
          <div class="srv-name">⚗ What-if lobby</div>
          <div class="srv-meta"><span>no server needed</span></div>
          <div class="srv-count">Pick any 8 players and see the splits</div>
        </button>
        <button v-for="s in servers" :key="s.hostname" class="srv-card" @click="pick(s)">
          <div class="srv-name">{{ s.hostname }}</div>
          <div class="srv-meta">
            <span v-if="s.map" class="map-pill">{{ s.map }}</span>
            <span>{{ s.city || s.region || '' }}</span>
          </div>
          <div class="srv-count">
            <strong>{{ s.humans }}</strong> player{{ s.humans === 1 ? '' : 's' }} on
            · {{ s.players.filter(p => p.resolved).length }} rated
          </div>
        </button>
      </div>
      <p class="refresh-note">Rosters refresh every minute. <a href="#" @click.prevent="load">Refresh now ↺</a></p>
    </template>

    <!-- STEP 2: confirm the 8 -->
    <template v-else>
      <div class="picked-bar">
        <div>
          <div class="picked-name">{{ picked.hostname }}</div>
          <div class="picked-meta">{{ picked.custom ? 'hypothetical — pick any 8' : `${picked.map} · ${picked.city || picked.region || ''}` }}</div>
        </div>
        <button class="change" @click="picked = null; results = null">↺ different server</button>
      </div>

      <div class="roster">
        <div v-for="p in roster" :key="p.name" class="pl-wrap">
          <label class="pl" :class="{ off: !p.resolved || !sel.has(p.cid), un: !p.resolved }">
            <input type="checkbox" :disabled="!p.resolved" :checked="p.resolved && sel.has(p.cid)" @change="toggle(p.cid)">
            <span class="pl-name">{{ p.display }}<span v-if="p.identified" class="pl-was"> was "{{ p.name }}"</span></span>
            <span v-if="p.resolved && p.mu != null" class="pl-mu">{{ Math.round(p.mu) }}<span v-if="!p.rated" class="pl-note" title="No 4on4 rating yet — blank prior used">?</span></span>
            <span v-else-if="p.identified" class="pl-note">identified</span>
            <button v-else class="who" @click.prevent="idFor = (idFor === p.name ? null : p.name); idSearch = ''">who is this?</button>
          </label>
          <div v-if="idFor === p.name" class="idbox">
            <input v-model="idSearch" :placeholder="`Who is '${p.name}'?`" autofocus>
            <div v-if="idMatch.length" class="dropdown">
              <a v-for="x in idMatch" :key="x.canonical_id" href="#" @click.prevent="identify(p, x)">
                {{ x.display || x.canonical_id }}
              </a>
            </div>
          </div>
        </div>
        <label v-for="p in extra" :key="p.cid" class="pl" :class="{ off: !sel.has(p.cid) }">
          <input type="checkbox" :checked="sel.has(p.cid)" @change="toggle(p.cid)">
          <span class="pl-name">{{ p.display }}</span>
          <span class="pl-note">added</span>
        </label>
      </div>

      <div class="controls">
        <div class="addbox">
          <input v-model="addSearch" placeholder="Add a player…">
          <div v-if="addMatch.length" class="dropdown">
            <a v-for="x in addMatch" :key="x.canonical_id" href="#" @click.prevent="addExtra(x)">
              {{ x.display || x.canonical_id }}
            </a>
          </div>
        </div>
        <label class="mapopt" v-if="picked.custom">
          <select v-model="customMap" class="mapsel">
            <option value="">overall ratings</option>
            <option v-for="m in MAPS_4ON4" :key="m" :value="m">{{ m }} map ratings</option>
          </select>
        </label>
        <label class="mapopt" v-else-if="picked.map">
          <input type="checkbox" v-model="useMap"> use {{ picked.map }} map ratings
        </label>
        <button class="go" :disabled="balancing || chosen.length !== 8" @click="balance">
          {{ balancing ? 'Balancing…' : `Balance ${chosen.length}/8` }}
        </button>
      </div>
      <p v-if="err" class="err">{{ err }}</p>

      <!-- STEP 3: results -->
      <div v-if="results" class="results">
        <div v-for="(sp, i) in splits" :key="i" class="split" :class="{ best: i === 0 }">
          <div class="split-head">
            <span class="split-tag">{{ i === 0 ? 'MOST EVEN' : `ALTERNATIVE ${i}` }}</span>
            <span class="split-odds">
              <b class="a">{{ pct(sp.p_team_a) }}</b> vs <b class="b">{{ pct(1 - sp.p_team_a) }}</b>
            </span>
          </div>
          <div class="odds-bar"><div class="fill" :style="{ width: (sp.p_team_a * 100) + '%' }"></div></div>
          <div v-if="sp.p_by_map" class="map-strip">
            <span v-for="(pv, m) in sp.p_by_map" :key="m" class="mp"
                  :class="{ afav: pv >= 0.55, bfav: pv <= 0.45 }">
              {{ m }} <b>{{ Math.round(pv * 100) }}%</b>
            </span>
          </div>
          <div class="teams">
            <div class="team">
              <div class="team-h a">TEAM A</div>
              <div v-for="c in sp.team_a" :key="c" class="tp"><span>{{ name(c) }}</span><span class="tmu">{{ mu(c) }}</span></div>
            </div>
            <div class="team">
              <div class="team-h b">TEAM B</div>
              <div v-for="c in sp.team_b" :key="c" class="tp"><span>{{ name(c) }}</span><span class="tmu">{{ mu(c) }}</span></div>
            </div>
          </div>
        </div>
        <p v-if="results.unrated && results.unrated.length" class="warn">
          No 4on4 rating yet (blank 1500 prior used): {{ results.unrated.join(', ') }} — their placement is the least certain.
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 28px 20px 80px; }
.head h1 { font-size: 30px; margin: 0; }
.sub { color: var(--fg-2); font-size: 14.5px; margin-top: 8px; max-width: 640px; }
.placeholder { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 26px; color: var(--fg-2); margin-top: 24px; }
.srv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; margin-top: 26px; }
.srv-card { text-align: left; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 18px; cursor: pointer; color: var(--fg-1); font-family: inherit; transition: border-color 0.15s; }
.srv-card:hover { border-color: var(--accent); }
.srv-card.whatif { border-style: dashed; }
.mapsel { background: var(--bg); border: 1px solid var(--border); border-radius: 9px; color: var(--fg-1); padding: 9px 12px; font-size: 13.5px; font-family: inherit; }
.srv-name { font-weight: 700; font-size: 14.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.srv-meta { display: flex; gap: 8px; align-items: center; color: var(--fg-3); font-size: 12.5px; margin-top: 6px; }
.map-pill { border: 1px solid var(--border); border-radius: 999px; padding: 1px 9px; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.srv-count { margin-top: 10px; color: var(--fg-2); font-size: 13px; }
.srv-count strong { color: var(--accent); font-size: 16px; }
.refresh-note { color: var(--fg-3); font-size: 13px; margin-top: 18px; }
.picked-bar { display: flex; justify-content: space-between; align-items: center; gap: 14px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-top: 24px; }
.picked-name { font-weight: 700; }
.picked-meta { color: var(--fg-3); font-size: 13px; font-family: 'JetBrains Mono', monospace; }
.change { background: none; border: 1px solid var(--border); color: var(--fg-2); border-radius: 8px; padding: 8px 14px; cursor: pointer; font-family: inherit; font-size: 13px; }
.roster { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; margin-top: 14px; }
.pl { display: flex; align-items: center; gap: 9px; background: var(--panel); border: 1px solid var(--border); border-radius: 9px; padding: 10px 12px; cursor: pointer; font-size: 14px; }
.pl.off { opacity: 0.55; }
.pl.un { cursor: not-allowed; }
.pl-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-mu { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--fg-2); }
.pl-note { margin-left: auto; color: var(--draw); font-size: 11px; }
.pl-wrap { position: relative; }
.pl-was { color: var(--fg-3); font-size: 11.5px; font-style: italic; }
.who { margin-left: auto; background: none; border: 1px solid var(--border); color: var(--draw);
  border-radius: 999px; padding: 3px 10px; font-size: 11px; cursor: pointer; font-family: inherit; white-space: nowrap; }
.who:hover { border-color: var(--draw); }
.idbox { position: absolute; top: 100%; left: 0; right: 0; z-index: 30; margin-top: 4px; }
.idbox input { width: 100%; background: var(--bg); border: 1px solid var(--accent); border-radius: 9px;
  color: var(--fg-1); padding: 9px 12px; font-size: 13.5px; }
.controls { display: flex; gap: 14px; align-items: center; margin-top: 16px; flex-wrap: wrap; }
.addbox { position: relative; }
.addbox input { background: var(--bg); border: 1px solid var(--border); border-radius: 9px; color: var(--fg-1); padding: 10px 14px; font-size: 14px; min-width: 200px; }
.dropdown { position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; background: var(--panel); border: 1px solid var(--border); border-radius: 9px; z-index: 20; max-height: 260px; overflow-y: auto; }
.dropdown a { display: block; padding: 8px 14px; color: var(--fg-1); font-size: 13.5px; border-bottom: 1px solid var(--border); }
.dropdown a:last-child { border-bottom: 0; }
.dropdown a:hover { background: var(--panel-3, rgba(255,255,255,0.04)); }
.mapopt { display: flex; gap: 7px; align-items: center; color: var(--fg-2); font-size: 13.5px; }
.go { margin-left: auto; background: var(--accent); color: var(--bg); border: 0; border-radius: 9px; padding: 12px 26px; font-weight: 700; font-size: 14.5px; cursor: pointer; font-family: inherit; }
.go:disabled { opacity: 0.5; cursor: not-allowed; }
.err { color: var(--loss); font-size: 13.5px; margin-top: 10px; }
.warn { color: var(--draw); font-size: 13px; margin-top: 12px; }
.results { margin-top: 28px; display: flex; flex-direction: column; gap: 16px; }
.split { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; }
.split.best { border-color: var(--accent); }
.split-head { display: flex; justify-content: space-between; align-items: baseline; }
.split-tag { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.14em; color: var(--fg-3); }
.split.best .split-tag { color: var(--accent); }
.split-odds { font-family: 'JetBrains Mono', monospace; font-size: 15px; }
.split-odds .a { color: var(--accent); } .split-odds .b { color: var(--loss); }
.odds-bar { height: 6px; border-radius: 3px; background: var(--loss); margin: 10px 0 16px; overflow: hidden; }
.odds-bar .fill { height: 100%; background: var(--accent); }
.map-strip { display: flex; gap: 14px; flex-wrap: wrap; margin: -6px 0 14px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--fg-3); }
.map-strip b { color: var(--fg-2); font-weight: 600; }
.map-strip .afav b { color: var(--accent); }
.map-strip .bfav b { color: var(--loss); }
.teams { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.team-h { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.14em; margin-bottom: 8px; }
.team-h.a { color: var(--accent); } .team-h.b { color: var(--loss); }
.tp { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid color-mix(in srgb, var(--border) 45%, transparent); font-size: 14px; }
.tp:last-child { border-bottom: 0; }
.tmu { font-family: 'JetBrains Mono', monospace; color: var(--fg-3); font-size: 13px; }
@media (max-width: 640px) { .teams { grid-template-columns: 1fr; } .go { margin-left: 0; width: 100%; } }
</style>

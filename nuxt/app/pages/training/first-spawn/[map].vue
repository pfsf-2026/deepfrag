<script setup>
// First-Spawn Optimization — replay how the top-5 players on a map convert each
// random spawn off the opening, conditioned on the enemy's spawn. Renders the
// stored 13ms path on the map geometry with an enemy "ghost" + a health/armor
// stack tracker, every run labeled by the 2-dim outcome (items × opening result).
// Reuses the renderer approach from the standalone spawn-playback tool.
const route = useRoute()
const router = useRouter()
const df = useDeepFrag()

const WINDOW_MS = 13
const ITEM_LABEL = {
  full_start: 'Full Start (RA+MH)', ra: 'Red Armor', mh_only: 'Mega only',
  ya_ga: 'YA / GA', nothing: 'nothing',
}

const mapName = computed(() => String(route.params.map || ''))

const geo = ref(null)            // map_annotations payload (geometry + spawns)
const spawns = ref([])           // spawn loc labels for this map
const players = ref([])          // [{player, display, rank_on_map, runs, spawns_covered}]
const groups = ref([])           // current player's runs grouped by own spawn
const allMaps = ref([])

const currentPlayer = ref('')
const currentSpawn = ref('')
const enemyFilter = ref(null)    // null = all enemy spawns
const activeRun = ref(null)      // {own, enemy, items, result, trace, enemy_trace, ...}
const activeKey = ref('')        // game_id|player of selected run
const loading = ref(true)
const loadingPath = ref(false)

// playback state (non-reactive bits live in module-ish refs to avoid rAF churn)
const playbackOffset = ref(0)
const isPlaying = ref(false)
const speed = ref(1)
let lastFrameTime = null
let animFrame = null
const mapCanvas = ref(null)

// ── data loading ────────────────────────────────────────────────────────────
async function loadMaps() {
  const url = df.mapListUrl('1on1')
  if (!url) return
  try { allMaps.value = (await (await fetch(url)).json()).maps || [] } catch { /* ignore */ }
}

async function loadMap() {
  loading.value = true
  activeRun.value = null
  try {
    const gUrl = df.mapAnnotationsUrl(mapName.value)
    const pUrl = df.spawnRunPlayersUrl(mapName.value)
    if (!gUrl || !pUrl) { loading.value = false; return }
    const [g, p] = await Promise.all([
      fetch(gUrl).then(r => r.ok ? r.json() : null),
      fetch(pUrl).then(r => r.ok ? r.json() : null),
    ])
    geo.value = g
    players.value = p?.players || []
    spawns.value = p?.spawns || (g?.spawns || []).map(s => s.loc)
    if (players.value.length) {
      currentPlayer.value = players.value[0].player
      currentSpawn.value = spawns.value[0] || ''
      enemyFilter.value = null
      await loadPlayer()
    }
  } finally {
    loading.value = false
  }
}

async function loadPlayer() {
  const url = df.spawnRunsUrl(mapName.value, currentPlayer.value, 4)
  if (!url) return
  const data = await fetch(url).then(r => r.ok ? r.json() : { groups: [] })
  groups.value = data.groups || []
  if (!spawns.value.length) spawns.value = data.spawns || []
  if (!groups.value.find(g => g.spawn === currentSpawn.value)) {
    currentSpawn.value = groups.value[0]?.spawn || currentSpawn.value
  }
  enemyFilter.value = null
  selectFirstRun()
}

const currentGroup = computed(() => groups.value.find(g => g.spawn === currentSpawn.value) || null)

const enemyOptions = computed(() => {
  const runs = currentGroup.value?.runs || []
  return [...new Set(runs.map(r => r.enemy_spawn).filter(Boolean))].sort()
})

const shownRuns = computed(() => {
  const runs = currentGroup.value?.runs || []
  return enemyFilter.value === null ? runs : runs.filter(r => r.enemy_spawn === enemyFilter.value)
})

function spawnCount(sp) {
  return (groups.value.find(g => g.spawn === sp)?.runs || []).length
}

// ── run selection + path fetch ──────────────────────────────────────────────
async function selectRun(run) {
  stopPlay()
  playbackOffset.value = 0
  activeKey.value = `${run.game_id}|${run.player}`
  loadingPath.value = true
  try {
    const url = df.spawnRunPathUrl(mapName.value, run.player, run.game_id)
    const full = await fetch(url).then(r => r.ok ? r.json() : null)
    if (!full) return
    activeRun.value = {
      own: full.own_spawn, enemy: full.enemy_spawn,
      items: full.items_outcome, result: full.opening_result,
      kill_ms: full.first_kill_ms, death_ms: full.first_death_ms,
      dur: full.duration_s, player: full.player,
      trace: full.path, enemy_trace: full.enemy_path,
    }
    await nextTick()
    drawAll()
  } finally {
    loadingPath.value = false
  }
}

function selectFirstRun() {
  const r = shownRuns.value[0]
  if (r) selectRun(r); else { activeRun.value = null }
}

// ── playback loop ───────────────────────────────────────────────────────────
function startPlay() {
  const ar = activeRun.value
  if (!ar || !ar.trace?.length) return
  if (playbackOffset.value >= ar.trace.length - 1) playbackOffset.value = 0
  isPlaying.value = true
  lastFrameTime = performance.now()
  if (animFrame) cancelAnimationFrame(animFrame)
  animFrame = requestAnimationFrame(tick)
}
function stopPlay() {
  isPlaying.value = false
  if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null }
}
function togglePlay() { isPlaying.value ? stopPlay() : startPlay() }
function restart() { playbackOffset.value = 0; drawAll() }
function tick(now) {
  const ar = activeRun.value
  if (!isPlaying.value || !ar) return
  const dt = now - (lastFrameTime || now); lastFrameTime = now
  playbackOffset.value += (dt * speed.value) / WINDOW_MS
  if (playbackOffset.value >= ar.trace.length - 1) {
    playbackOffset.value = ar.trace.length - 1; drawAll(); stopPlay(); return
  }
  drawAll()
  animFrame = requestAnimationFrame(tick)
}
function onScrub(e) { playbackOffset.value = parseFloat(e.target.value); drawAll() }

// ── rendering (ported from the standalone playback tool) ─────────────────────
const STATE_COLOR = { 0: 'rgba(251,146,60,', 1: 'rgba(96,165,250,', 2: 'rgba(234,179,8,', 3: 'rgba(34,197,94,' }

function drawMap(ctx, w, h) {
  const mg = geo.value?.geometry
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h)
  if (!mg?.bounds) return null
  const b = mg.bounds, pad = 12
  const s = Math.min((w - pad * 2) / Math.max(b.maxX - b.minX, 1), (h - pad * 2) / Math.max(b.maxY - b.minY, 1))
  const ox = pad + ((w - pad * 2) - (b.maxX - b.minX) * s) / 2
  const oy = pad + ((h - pad * 2) - (b.maxY - b.minY) * s) / 2
  const toX = wx => ox + (wx - b.minX) * s
  const toY = wy => h - (oy + (wy - b.minY) * s)
  const locs = (mg.locs || []).slice().sort((a, b) => (a.z || 0) - (b.z || 0))
  for (const loc of locs) {
    const t = loc.tris || []; ctx.beginPath()
    for (let i = 0; i + 5 < t.length; i += 6) {
      ctx.moveTo(toX(t[i]), toY(t[i + 1])); ctx.lineTo(toX(t[i + 2]), toY(t[i + 3])); ctx.lineTo(toX(t[i + 4]), toY(t[i + 5])); ctx.closePath()
    }
    ctx.fillStyle = 'rgba(40,50,70,0.85)'; ctx.fill()
    ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 0.4; ctx.stroke()
  }
  ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.font = 'bold 11px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  for (const loc of locs) {
    if (!/^(RA|YA|GA|MH|MEGA|QUAD|PENT|RING|LG|RL|GL|SNG|low|high|big|water|yard|air)/i.test(loc.name || '')) continue
    const t = loc.tris || []; let cx = 0, cy = 0, n = 0
    for (let i = 0; i + 1 < t.length; i += 2) { cx += t[i]; cy += t[i + 1]; n++ }
    if (n) ctx.fillText((loc.name || '').slice(0, 10), toX(cx / n), toY(cy / n))
  }
  return { toX, toY }
}

function drawAll() {
  const cv = mapCanvas.value
  if (!cv) return
  const ctx = cv.getContext('2d')
  const tf = drawMap(ctx, cv.width, cv.height)
  const ar = activeRun.value
  if (!tf || !ar || !ar.trace?.length) return
  const { toX, toY } = tf
  const trace = ar.trace
  const off = Math.max(0, Math.min(trace.length - 1, Math.floor(playbackOffset.value)))
  const TELE = 1000, segD = (a, b) => Math.hypot(b.x - a.x, b.y - a.y)
  // enemy ghost
  const en = ar.enemy_trace
  if (en) {
    ctx.strokeStyle = 'rgba(167,139,250,0.30)'; ctx.lineWidth = 1.4; ctx.beginPath(); let started = false
    for (let i = 1; i <= off && i < en.length; i++) {
      const a = en[i - 1], b = en[i]
      if (!a || !b || segD(a, b) > TELE) { started = false; continue }
      if (!started) { ctx.moveTo(toX(a.x), toY(a.y)); started = true }
      ctx.lineTo(toX(b.x), toY(b.y))
    }
    ctx.stroke()
    const ec = en[off]
    if (ec) { ctx.fillStyle = 'rgba(167,139,250,0.95)'; ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(toX(ec.x), toY(ec.y), 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke() }
  }
  // your past path
  for (let i = 1; i <= off && i < trace.length; i++) {
    const a = trace[i - 1], b = trace[i]; if (segD(a, b) > TELE) continue
    ctx.strokeStyle = (STATE_COLOR[a.state] || STATE_COLOR[0]) + '0.9)'; ctx.lineWidth = 2.6
    ctx.beginPath(); ctx.moveTo(toX(a.x), toY(a.y)); ctx.lineTo(toX(b.x), toY(b.y)); ctx.stroke()
  }
  // future faint
  for (let i = off + 1; i < trace.length; i++) {
    const a = trace[i - 1], b = trace[i]; if (segD(a, b) > TELE) continue
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(toX(a.x), toY(a.y)); ctx.lineTo(toX(b.x), toY(b.y)); ctx.stroke()
  }
  // spawn marker
  const st = trace[0]
  ctx.fillStyle = 'rgba(20,230,192,0.7)'; ctx.strokeStyle = 'rgba(20,230,192,1)'; ctx.lineWidth = 2
  ctx.beginPath(); ctx.arc(toX(st.x), toY(st.y), 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
  // death marker
  if (ar.death_ms != null) {
    const di = Math.round(ar.death_ms / WINDOW_MS)
    if (di <= off && di < trace.length) {
      const dp = trace[Math.min(di, trace.length - 1)]
      ctx.fillStyle = '#ef4444'; ctx.font = 'bold 20px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      ctx.fillText('✕', toX(dp.x), toY(dp.y))
    }
  }
  // current dot
  const cur = trace[off]
  ctx.fillStyle = 'rgba(255,255,255,0.30)'; ctx.beginPath(); ctx.arc(toX(cur.x), toY(cur.y), 14, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = (STATE_COLOR[cur.state] || STATE_COLOR[0]) + '1)'; ctx.strokeStyle = 'rgba(255,255,255,0.95)'; ctx.lineWidth = 2.5
  ctx.beginPath(); ctx.arc(toX(cur.x), toY(cur.y), 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
}

// stack tracker (SVG string)
const stackSvg = computed(() => {
  const ar = activeRun.value
  if (!ar || !ar.trace?.length) return ''
  const trace = ar.trace, W = 800, H = 240, padL = 36, padR = 10, padT = 16, padB = 24
  const plotW = W - padL - padR, plotH = H - padT - padB, n = trace.length
  const off = Math.max(0, Math.min(n - 1, Math.floor(playbackOffset.value))), yMax = 300
  const toX = i => padL + (i / Math.max(n - 1, 1)) * plotW
  const toY = v => padT + plotH - (Math.min(v, yMax) / yMax) * plotH
  const matchSec = (n - 1) * WINDOW_MS / 1000, AT = { ra: '#ef4444', ya: '#eab308', ga: '#22c55e' }
  let out = ''
  for (const tk of [100, 200, 300]) {
    out += `<line x1="${padL}" y1="${toY(tk)}" x2="${W - padR}" y2="${toY(tk)}" stroke="rgba(255,255,255,0.08)" stroke-width="0.5"/><text x="${padL - 4}" y="${toY(tk) + 3}" fill="rgba(255,255,255,0.4)" font-size="10" text-anchor="end" font-family="monospace">${tk}</text>`
  }
  for (const f of [0, .25, .5, .75, 1]) {
    out += `<text x="${padL + f * plotW}" y="${H - 6}" fill="rgba(255,255,255,0.4)" font-size="10" text-anchor="middle" font-family="monospace">+${(matchSec * f).toFixed(1)}s</text>`
  }
  for (const atype of ['ra', 'ya', 'ga']) {
    const color = AT[atype]; let seg = -1
    const close = e => {
      let d = `M ${toX(seg)} ${toY(trace[seg].h)} `
      for (let i = seg; i <= e; i++) d += `L ${toX(i)} ${toY((trace[i].h || 0) + (trace[i].a || 0))} `
      for (let i = e; i >= seg; i--) d += `L ${toX(i)} ${toY(trace[i].h || 0)} `
      d += 'Z'; out += `<path d="${d}" fill="${color}" fill-opacity="0.35"/>`
    }
    for (let i = 0; i < n; i++) {
      const m = trace[i].at === atype && (trace[i].a || 0) > 0
      if (m && seg === -1) seg = i; else if (!m && seg !== -1) { close(i - 1); seg = -1 }
    }
    if (seg !== -1) close(n - 1)
  }
  let hp = ''
  for (let i = 0; i < n; i++) if ((trace[i].h || 0) > 0) hp += (i === 0 ? 'M ' : 'L ') + toX(i) + ' ' + toY(trace[i].h) + ' '
  out += `<path d="${hp}" fill="none" stroke="#14e6c0" stroke-width="1.6" opacity="0.95"/>`
  const px = toX(off)
  out += `<line x1="${px}" y1="${padT - 4}" x2="${px}" y2="${H - padB + 4}" stroke="#14e6c0" stroke-width="2" opacity="0.85"/><circle cx="${px}" cy="${toY((trace[off].h || 0) + (trace[off].a || 0))}" r="4" fill="#14e6c0"/>`
  return out
})

// ── derived display ─────────────────────────────────────────────────────────
const tSec = computed(() => (playbackOffset.value * WINDOW_MS / 1000).toFixed(1))
const totalSec = computed(() => ((activeRun.value?.trace?.length || 0) * WINDOW_MS / 1000).toFixed(1))
const curState = computed(() => activeRun.value?.trace?.[Math.floor(playbackOffset.value)] || { h: '—', a: '—', at: '' })
const maxOffset = computed(() => Math.max(0, (activeRun.value?.trace?.length || 1) - 1))

function pickPlayer(p) { currentPlayer.value = p; loadPlayer() }
function pickSpawn(sp) { currentSpawn.value = sp; enemyFilter.value = null; selectFirstRun() }
function pickEnemy(e) { enemyFilter.value = e; selectFirstRun() }
function pickMap(m) { router.push(`/training/first-spawn/${encodeURIComponent(m)}`) }
function fmtMs(ms) { return ms == null ? '—' : (ms / 1000).toFixed(1) + 's' }

watch(shownRuns, () => { if (!shownRuns.value.find(r => `${r.game_id}|${r.player}` === activeKey.value)) selectFirstRun() })
watch(mapName, () => loadMap())

onMounted(() => { loadMap(); loadMaps() })
onBeforeUnmount(() => stopPlay())

useHead({ title: () => `${mapName.value} first-spawn training · DeepFrag` })
</script>

<template>
  <div class="page">
    <div class="head">
      <NuxtLink :to="`/rankings/maps/${encodeURIComponent(mapName)}`" class="back">← {{ mapName }} rankings</NuxtLink>
      <h1>First-Spawn Optimization <span class="map-chip">{{ mapName }}</span></h1>
      <p class="sub">How the top-5 players convert each random spawn off the opening — conditioned on the enemy's spawn. Every run is labeled by what they secured and how the opening ended. Pick a player, your spawn, and (optionally) the enemy spawn.</p>
    </div>

    <div class="controls">
      <span class="label">Map</span>
      <select :value="mapName" class="search" @change="pickMap($event.target.value)">
        <option v-for="m in allMaps" :key="m.map" :value="m.map">{{ m.map }}</option>
      </select>
      <span class="label">Player</span>
      <div class="pill-group">
        <button v-for="p in players" :key="p.player" :class="{ active: currentPlayer === p.player }" @click="pickPlayer(p.player)">
          <span class="rk">#{{ p.rank_on_map || '?' }}</span> {{ p.display || p.player }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="placeholder">Loading {{ mapName }} first-spawn data…</div>
    <div v-else-if="!players.length" class="placeholder">
      No first-spawn training data for <code>{{ mapName }}</code> yet.
    </div>

    <template v-else>
      <div class="filters">
        <div class="filt-row">
          <span class="label">Your spawn</span>
          <button v-for="sp in spawns" :key="sp" class="pill" :class="{ active: currentSpawn === sp }" @click="pickSpawn(sp)">
            {{ sp }} <span class="n">{{ spawnCount(sp) }}</span>
          </button>
        </div>
        <div class="filt-row">
          <span class="label">Enemy spawn</span>
          <button class="pill enemy" :class="{ active: enemyFilter === null }" @click="pickEnemy(null)">all</button>
          <button v-for="e in enemyOptions" :key="e" class="pill enemy" :class="{ active: enemyFilter === e }" @click="pickEnemy(e)">{{ e }}</button>
        </div>
      </div>

      <div class="viewer">
        <div class="panel">
          <h3>Map · your path <span class="ghost">+ enemy ghost</span> <span class="now">T+{{ tSec }}s</span></h3>
          <canvas ref="mapCanvas" width="1000" height="625" class="map-canvas" />
          <div class="legend">
            <span class="lg you">you</span><span class="lg enemy">enemy</span>
            <span class="lg naked">naked</span><span class="lg arm">armored</span><span class="lg stk">stacked</span>
          </div>
        </div>
        <div class="panel">
          <h3>Stack tracker · health + armor <span class="now">T+{{ tSec }}s</span></h3>
          <svg viewBox="0 0 800 240" class="stack-svg" v-html="stackSvg" />
          <div class="statbar">
            <div><span class="l">Your spawn</span><span class="v">{{ activeRun?.own || '—' }}</span></div>
            <div><span class="l">Enemy</span><span class="v">{{ activeRun?.enemy || '—' }}</span></div>
            <div><span class="l">Health</span><span class="v">{{ curState.h }}</span></div>
            <div><span class="l">Armor</span><span class="v" :class="curState.at">{{ curState.a }}</span></div>
          </div>
        </div>
      </div>

      <div class="playback">
        <button class="btn primary" @click="togglePlay">{{ isPlaying ? '⏸ Pause' : '▶ Play' }}</button>
        <button class="btn" @click="restart">⟲ Restart</button>
        <div class="speed">
          <button v-for="s in [0.25, 0.5, 1, 2, 4]" :key="s" :class="{ active: speed === s }" @click="speed = s">{{ s }}×</button>
        </div>
        <input type="range" min="0" :max="maxOffset" :value="playbackOffset" step="1" class="scrub" @input="onScrub">
        <span class="time">{{ tSec }} / {{ totalSec }}s</span>
        <span v-if="loadingPath" class="time">loading run…</span>
      </div>

      <table class="runs">
        <thead><tr>
          <th>#</th><th>Enemy spawn</th><th>Items secured</th><th>Opening</th>
          <th class="num">First kill</th><th class="num">First death</th><th class="num">Length</th>
        </tr></thead>
        <tbody>
          <tr v-for="(r, i) in shownRuns" :key="r.game_id + '|' + r.player"
              :class="{ active: activeKey === r.game_id + '|' + r.player }" @click="selectRun(r)">
            <td class="dim">{{ i + 1 }}</td>
            <td><strong>{{ r.enemy_spawn || '?' }}</strong></td>
            <td><span class="chip" :class="'it-' + r.items_outcome">{{ ITEM_LABEL[r.items_outcome] || r.items_outcome }}</span></td>
            <td><span class="res" :class="'r-' + r.opening_result">{{ r.opening_result }}</span></td>
            <td class="num">{{ fmtMs(r.first_kill_ms) }}</td>
            <td class="num">{{ fmtMs(r.first_death_ms) }}</td>
            <td class="num">{{ (r.duration_s || 0).toFixed(1) }}s</td>
          </tr>
          <tr v-if="!shownRuns.length"><td colspan="7" class="dim" style="text-align:center;padding:20px">No runs for this spawn/enemy combination.</td></tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1280px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 18px; }
.head .back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; display: inline-block; margin-bottom: 8px; }
.head .back:hover { color: var(--accent); }
.head h1 { margin: 0 0 6px; font-size: 30px; font-weight: 800; letter-spacing: -0.02em; display: flex; align-items: center; gap: 12px; }
.map-chip { font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px; background: rgba(20,230,192,0.12); color: var(--accent); text-transform: uppercase; letter-spacing: 0.06em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; max-width: 760px; }

.controls, .filt-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.controls { margin-bottom: 14px; }
.filters { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.label { color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; }
.pill-group { display: inline-flex; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 3px; gap: 2px; flex-wrap: wrap; }
.pill-group button { background: transparent; border: 0; color: var(--fg-2); padding: 6px 12px; border-radius: 5px; cursor: pointer; font: inherit; font-size: 12px; font-weight: 600; }
.pill-group button:hover { color: var(--fg); }
.pill-group button.active { background: var(--accent); color: var(--bg); }
.pill-group .rk { opacity: 0.6; font-size: 10px; }
.pill { background: var(--panel); border: 1px solid var(--border); color: var(--fg-2); border-radius: 999px; padding: 6px 13px; font-size: 13px; cursor: pointer; }
.pill:hover { color: var(--fg); }
.pill.active { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 700; }
.pill.enemy.active { background: var(--panel-2, #1e2636); color: var(--fg); border-color: var(--accent); }
.pill .n { opacity: 0.55; font-size: 11px; }
.search { background: var(--panel); border: 1px solid var(--border); color: var(--fg); padding: 8px 14px; border-radius: 8px; font-size: 13px; font-family: inherit; }

.viewer { display: grid; grid-template-columns: 1.5fr 1fr; gap: 14px; margin-bottom: 12px; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
.panel h3 { margin: 0 0 8px; font-size: 13px; color: var(--fg-2); font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
.panel h3 .ghost { color: #a78bfa; font-weight: 500; }
.now { color: var(--accent); font-variant-numeric: tabular-nums; }
.map-canvas { width: 100%; height: auto; border-radius: 6px; background: #000; display: block; }
.stack-svg { width: 100%; height: auto; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; color: var(--fg-3); font-size: 11px; margin-top: 6px; }
.legend .lg::before { content: ''; display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }
.legend .you::before { background: var(--accent); }
.legend .enemy::before { background: #a78bfa; }
.legend .naked::before { background: #fb923c; }
.legend .arm::before { background: #60a5fa; }
.legend .stk::before { background: #22c55e; }
.statbar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; }
.statbar div { display: flex; flex-direction: column; }
.statbar .l { color: var(--fg-3); font-size: 11px; }
.statbar .v { font-size: 16px; font-weight: 700; font-variant-numeric: tabular-nums; }
.statbar .v.ra { color: #ef4444; } .statbar .v.ya { color: #eab308; } .statbar .v.ga { color: #22c55e; }

.playback { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { background: var(--panel); border: 1px solid var(--border); color: var(--fg); border-radius: 7px; padding: 8px 14px; font-size: 14px; cursor: pointer; }
.btn.primary { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 700; }
.speed { display: inline-flex; gap: 4px; }
.speed button { background: var(--panel); border: 1px solid var(--border); color: var(--fg-2); border-radius: 6px; padding: 5px 9px; font-size: 12px; cursor: pointer; }
.speed button.active { background: var(--panel-2, #1e2636); color: var(--fg); }
.scrub { flex: 1; min-width: 200px; }
.time { color: var(--fg-3); font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }

.runs { width: 100%; border-collapse: collapse; font-size: 13px; }
.runs th, .runs td { text-align: left; padding: 9px 11px; border-bottom: 1px solid var(--border); }
.runs th { color: var(--fg-3); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; }
.runs th.num, .runs td.num { text-align: right; font-variant-numeric: tabular-nums; }
.runs tbody tr { cursor: pointer; }
.runs tbody tr:hover { background: var(--panel); }
.runs tbody tr.active { background: var(--panel-2, #172033); }
.runs .dim { color: var(--fg-3); }
.chip { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.it-full_start { background: rgba(34,197,94,0.18); color: #4ade80; }
.it-ra { background: rgba(239,68,68,0.16); color: #f87171; }
.it-mh_only { background: rgba(96,165,250,0.16); color: #93c5fd; }
.it-ya_ga { background: rgba(234,179,8,0.16); color: #facc15; }
.it-nothing { background: rgba(95,113,134,0.18); color: #9fb0c3; }
.res { font-weight: 700; }
.r-won { color: #22c55e; } .r-traded { color: #eab308; } .r-lost { color: #ef4444; } .r-survived { color: #60a5fa; }
.placeholder { padding: 60px; text-align: center; color: var(--fg-3); }
</style>

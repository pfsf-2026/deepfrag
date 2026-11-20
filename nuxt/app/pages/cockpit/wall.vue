<script setup>
// Server wall (Peter, 2026-11-19): every live QuakeWorld server on one strip, for the Corsair Xeneon
// Edge (2560×720, touch) as an iCUE Web URL widget at 1/3, 2/3 or full width. Cards page sideways with
// the arrows (or the wheel) — NOT by swipe: a sideways swipe belongs to iCUE, it changes Edge screens
// (Peter, 2026-11-20; ?swipe=1 turns swipe-scrolling back on). Filter chips on top; Join / Watch / QTV open
// the game client; a tap anywhere else on a card opens the drill-down (matchup, ratings, advanced stats).
// Data: /api/servers/wall = the hub's live list with DeepFrag ratings, duel win chance and ladder badges.
// /cockpit/wall?me=cronus adds the side strip (next ladder match, last result) at full width, and blanks
// the card of a server the owner is playing on — nothing live about your own game goes on this screen.
useHead({ title: 'Server wall · DeepFrag' })

const route = useRoute()
const me = computed(() => String(route.query.me || '').toLowerCase())
const wall = ref(null)
const full = ref(null)
const ladders = ref([])
const now = ref(Date.now())
const filter = ref(String(route.query.show || 'all').toLowerCase())
const rail = ref(null)

const FILTERS = [['all', 'All'], ['1on1', '1on1'], ['2on2', '2on2'], ['4on4', '4on4'], ['other', 'FFA / other'],
                 ['ours', 'Ours'], ['na', 'NA']]
const TEAM_MODES = ['2on2', '3on3', '4on4', 'ctf', 'wipeout']
// QW shirt/pants palette (top row of the colour ramp), for the two-tone chip beside a name.
const QW = ['#8b8b8b', '#6b4f2f', '#7b7bb3', '#6b6b1f', '#7f0000', '#af8f33', '#ff9b5b', '#e3b38f', '#9b5b7b',
            '#ab7b6b', '#d7cfc3', '#4f8f7f', '#ffef27', '#2f2fff']

async function getJson(url) {
  try { const r = await fetch(url, { cache: 'no-store' }); return r.ok ? await r.json() : null } catch { return null }
}
async function loadWall() { const d = await getJson(`/api/servers/wall?t=${Date.now()}`); if (d) wall.value = d }
async function loadMe() {
  if (!me.value) return
  full.value = await getJson(`/api/players/${encodeURIComponent(me.value)}/full?t=${Date.now()}`)
  const out = []
  for (const lid of [2, 1]) { const d = await getJson(`/api/ladder/${lid}`); if (d) out.push(d) }
  ladders.value = out
}

// A widget is never reloaded by hand: when a new build of the site is out, reload ourselves.
let build = null
async function checkBuild() {
  const d = await getJson(`/_nuxt/builds/latest.json?t=${Date.now()}`)
  if (!d?.id) return
  if (build && d.id !== build) location.reload()
  build = d.id
}

const timers = []
onMounted(() => {
  loadWall(); loadMe(); checkBuild()
  timers.push(setInterval(checkBuild, 60_000), setInterval(loadWall, 5_000), setInterval(loadMe, 60_000),
              setInterval(() => { now.value = Date.now() }, 1_000))
})
onBeforeUnmount(() => timers.forEach(clearInterval))

const humans = s => s.players.filter(p => !p.is_bot)
const isMine = s => !!me.value && s.players.some(p => p.id === me.value)
const isHot = s => !!s.ladder || (s.mode === '1on1' && s.status === 'Started' && humans(s).length === 2 &&
  humans(s).every(p => ['div0', 'div1'].includes(p.tier?.slug)))

function passes(s) {
  const f = filter.value
  if (f === 'ours') return s.ours
  if (f === 'na') return s.region === 'North America'
  if (f === 'other') return !['1on1', '2on2', '4on4'].includes(s.mode)
  if (f === 'all') return true
  return s.mode === f
}
// Ladder games first, then matches under way, then servers with people on them, bots and empty ports last.
const rank = s => [s.ladder ? 0 : 1, humans(s).length ? 0 : 1, s.status === 'Started' && s.mode !== 'ffa' ? 0 : 1,
                   s.status === 'Started' ? 0 : 1, -humans(s).length]
const servers = computed(() => (wall.value?.servers || []).filter(passes).sort((a, b) => {
  const x = rank(a), y = rank(b)
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] - y[i]
  return a.address.localeCompare(b.address)
}))
const counts = computed(() => {
  const all = wall.value?.servers || []
  return { servers: all.filter(s => humans(s).length).length, players: all.reduce((n, s) => n + humans(s).length, 0) }
})

// One card's scoreboard: teams (team modes) or a single list, best frags first.
function board(s) {
  const by = (a, b) => (b.frags ?? -999) - (a.frags ?? -999)
  if (TEAM_MODES.includes(s.mode) && s.players.some(p => p.team)) {
    const teams = {}
    for (const p of s.players) (teams[p.team || '?'] ||= []).push(p)
    return Object.entries(teams).map(([name, ps]) => ({ name, frags: ps.reduce((n, p) => n + (p.frags || 0), 0), players: ps.sort(by) }))
      .sort((a, b) => b.frags - a.frags)
  }
  return [{ name: '', frags: null, players: [...s.players].sort(by) }]
}
const chip = p => p.colors ? { background: `linear-gradient(${QW[p.colors[0]] || QW[0]} 50%, ${QW[p.colors[1]] || QW[0]} 50%)` } : null
const shot = s => s.map ? { backgroundImage: `linear-gradient(rgba(10,8,6,.15), rgba(10,8,6,.92)), url(https://a.quake.world/mapshots/webp/lg/${encodeURIComponent(s.map)}.webp)` } : null
const free = s => s.slots?.total != null ? Math.max(0, s.slots.total - (s.slots.used || 0)) : null
const pct = v => `${Math.round(v * 100)}%`

const swipe = computed(() => route.query.swipe === '1')
const scroller = () => (openAddr.value ? drillEl.value : rail.value)
function scroll(dir) { const el = scroller(); el?.scrollBy({ left: dir * Math.max(410, el.clientWidth * 0.8), behavior: 'smooth' }) }
function wheel(e) { const el = scroller(); if (el && Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.target.closest('.board, .col')) { el.scrollLeft += e.deltaY; e.preventDefault() } }

// Drill-down: tap a card (anywhere but its buttons). The server keeps updating from the wall feed; the
// players' profiles, advanced duel stats and (for a duel) the head-to-head load once per open.
const openAddr = ref('')
const drillEl = ref(null)
const prof = reactive({})        // canonical id -> { full, adv }
const h2h = ref(null)
const open = computed(() => (wall.value?.servers || []).find(s => s.address === openAddr.value) || null)
const known = s => humans(s).filter(p => p.id)
async function drill(s) {
  if (isMine(s)) return
  openAddr.value = s.address; h2h.value = null
  const ps = known(s).slice(0, 8)
  for (const p of ps) {
    if (prof[p.id]) continue
    prof[p.id] = { full: null, adv: null }
    getJson(`/api/players/${encodeURIComponent(p.id)}/full`).then(d => { prof[p.id].full = d })
    getJson(`/api/players/${encodeURIComponent(p.id)}/advanced`).then(d => { prof[p.id].adv = d })
  }
  if (s.mode === '1on1' && ps.length === 2) {
    const d = await getJson(`/api/h2h?p1=${encodeURIComponent(ps[0].id)}&p2=${encodeURIComponent(ps[1].id)}`)
    if (openAddr.value === s.address) h2h.value = d
  }
}
function closeDrill() { openAddr.value = ''; h2h.value = null }
watch(open, s => { if (openAddr.value && (!s || isMine(s))) closeDrill() })

const rmode = s => ['1on1', '2on2', '4on4'].includes(s.mode) ? s.mode : '1on1'
const one = v => v == null ? '—' : v
const pc = v => v == null ? '—' : `${Math.round(v)}%`
const acc = v => v == null ? '—' : `${Math.round(v * 100)}%`
// One player's block: rating line, last-10 form, and the advanced 1on1 numbers (career + this map).
function sheet(p, s) {
  const d = prof[p.id] || {}
  const r = d.full?.ratings?.[rmode(s)] || null
  const games = (d.full?.recent_matches || []).filter(m => m.match_mode === rmode(s)).slice(0, 10)
  const avg = k => { const v = games.map(m => m[k]).filter(x => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }
  const c = d.adv?.career || null
  const m = (d.adv?.by_map || []).find(x => x.map === s.map) || null
  const rows = c ? [
    ['Win %', pc(c.win_pct), m && pc(m.win_pct)],
    ['Frags / min', one(c.frags_pm), m && one(m.frags_pm)],
    ['Damage / min', one(c.dmg_pm), m && one(m.dmg_pm)],
    ['Damage ratio', one(c.ddr), m && one(m.ddr)],
    ['Stacked damage ratio', one(c.sddr), m && one(m.sddr)],
    ['Even fights won', pc(c.even_win_pct), m && pc(m.even_win_pct)],
    ['Item-first spawns', pc(c.item_first_pct), m && pc(m.item_first_pct)],
    ['Chained deaths', pc(c.chained_real_pct), m && pc(m.chained_real_pct)],
    ['Spawn deaths', pc(c.spawn_death_pct), m && pc(m.spawn_death_pct)],
    ['Red armors / game', one(c.ra_pg), m && one(m.ra_pg)],
    ['Red armor on timer', pc(c.ra_on_timer_pct), m && pc(m.ra_on_timer_pct)],
  ] : []
  return { loading: !d.full, r, games, lg: acc(avg('lg_acc')), rl: acc(avg('rl_acc')), rows, mapGames: m?.games ?? null, advGames: c?.games ?? null }
}
// The duel block, from /api/h2h (rating blended with the pair's record), with the map being played.
const duel = computed(() => {
  const d = h2h.value, s = open.value
  if (!d || !s) return null
  const m = (d.maps || []).find(x => x.map === s.map) || null
  return { a: d.player_a, b: d.player_b, h: d.h2h || {}, win: d.overall_predict_win_a, m,
           recent: (d.recent_matches || []).slice(0, 8) }
})
const day = iso => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

// Side strip: the owner's next scheduled ladder match and last result.
const nextMatch = computed(() => {
  let best = null
  for (const d of ladders.value) {
    const mine = (d.teams || []).filter(t => (t.members || []).some(m => m.id === me.value)).map(t => t.id)
    for (const c of d.challenges || []) {
      if (c.status !== 'scheduled' || !c.agreed_at) continue
      if (!mine.includes(c.challenger_id) && !mine.includes(c.challenged_id)) continue
      const at = new Date(c.agreed_at).getTime()
      if (at < now.value - 3600e3) continue
      if (!best || at < best.at) best = { at, id: c.id, opp: mine.includes(c.challenger_id) ? c.challenged : c.challenger, ladder: d.ladder?.name }
    }
  }
  return best
})
function countdown(at) {
  const s = Math.round((at - now.value) / 1000)
  if (s <= 0) return 'now'
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60)
  return d ? `${d}d ${h}h` : h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}:${String(s % 60).padStart(2, '0')}`
}
const last = computed(() => (full.value?.recent_matches || []).find(m => ['1on1', '2on2', '4on4'].includes(m.match_mode)) || null)
const clock = computed(() => new Date(now.value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }))
const fmtWhen = at => new Date(at).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
</script>

<template>
  <div class="wall">
    <header class="bar">
      <span class="title">Live servers</span>
      <span class="count"><b>{{ counts.players }}</b> players on <b>{{ counts.servers }}</b> servers</span>
      <div class="chips">
        <button v-for="[k, label] in FILTERS" :key="k" class="chipb" :class="{ on: filter === k }" @click="filter = k">{{ label }}</button>
      </div>
      <span v-if="wall?.hub_error" class="warn">hub list unavailable — showing our servers only</span>
      <span class="grow" />
      <button class="arrow" aria-label="Scroll left" @click="scroll(-1)">‹</button>
      <button class="arrow" aria-label="Scroll right" @click="scroll(1)">›</button>
      <span class="clock">{{ clock }}</span>
    </header>

    <div class="body">
      <div v-show="!open" ref="rail" class="rail" :class="{ swipe }" @wheel="wheel">
        <article v-for="s in servers" :key="s.address" class="card" :class="{ hot: isHot(s), ours: s.ours, idle: !humans(s).length }" @click="drill(s)">
          <div class="shot" :style="shot(s)">
            <div class="tags">
              <span class="tag mode">{{ s.mode || '—' }}</span>
              <span v-if="s.ladder" class="tag ladder">Ladder · {{ s.ladder.ladder }}</span>
              <span v-if="s.ours" class="tag ours">DeepFrag</span>
              <span class="grow" />
              <span class="tag where">{{ [s.city, s.cc].filter(Boolean).join(' · ') }}</span>
            </div>
            <div class="map">{{ s.map || '—' }}</div>
            <div class="status" :class="{ live: s.status === 'Started' }">
              <span class="dot" />{{ s.status === 'Started' ? (s.status_text || 'In progress') : (s.status_text || s.status) }}
            </div>
          </div>

          <div v-if="isMine(s)" class="mine">You're playing here.<br><span class="dim">Nothing live about your own game is shown on this screen.</span></div>
          <template v-else>
            <div class="board">
              <template v-for="t in board(s)" :key="t.name">
                <div v-if="t.name" class="team"><span class="tn">{{ t.name }}</span><b>{{ t.frags }}</b></div>
                <div v-for="p in t.players" :key="p.name" class="pl" :class="{ bot: p.is_bot }">
                  <span class="sw" :style="chip(p)" />
                  <span class="pn">{{ p.name }}</span>
                  <span v-if="p.tier" class="tier" :style="{ background: p.tier.color }">{{ p.tier.name }}</span>
                  <span class="mu">{{ p.mu ?? '' }}</span>
                  <span class="ping">{{ p.is_bot ? 'bot' : (p.ping != null ? p.ping + 'ms' : '') }}</span>
                  <b class="fr">{{ p.frags ?? '' }}</b>
                </div>
              </template>
              <div v-if="!s.players.length" class="dim none">Empty — {{ s.slots?.total ?? '?' }} slots</div>
            </div>
            <div v-if="s.win_a != null" class="odds" title="Win chance from ratings">
              <div class="fa" :style="{ width: (s.win_a * 100) + '%' }">{{ humans(s)[0].name }} {{ pct(s.win_a) }}</div>
              <div class="fb">{{ pct(1 - s.win_a) }} {{ humans(s)[1].name }}</div>
            </div>
          </template>

          <footer class="acts">
            <span class="specs">{{ s.spectators || 0 }} watching</span>
            <span class="grow" />
            <a v-if="free(s) !== 0" class="act join" :href="`qw://${s.address}/`" @click.stop>Join<small v-if="free(s)"> · {{ free(s) }} free</small></a>
            <a class="act" :href="`qw://${s.address}/observe`" @click.stop>Watch</a>
            <a v-if="s.qtv" class="act" :href="`qw://${s.qtv}/qtvplay`" @click.stop>QTV</a>
          </footer>
        </article>
        <div v-if="wall && !servers.length" class="empty">No servers match this filter right now.</div>
        <div v-if="!wall" class="empty">Loading servers…</div>
      </div>

      <!-- DRILL-DOWN: one server — live scoreboard, the matchup (duels), a stats sheet per known player -->
      <div v-if="open" ref="drillEl" class="rail drill" :class="{ swipe }" @wheel="wheel">
        <section class="col srv">
          <div class="shot" :style="shot(open)">
            <div class="tags">
              <button class="back" @click="closeDrill">‹ All servers</button>
              <span class="grow" />
              <span class="tag mode">{{ open.mode || '—' }}</span>
              <span v-if="open.ladder" class="tag ladder">Ladder</span>
            </div>
            <div class="map">{{ open.map || '—' }}</div>
            <div class="status" :class="{ live: open.status === 'Started' }"><span class="dot" />{{ open.status_text || open.status }} · {{ [open.city, open.cc].filter(Boolean).join(' · ') }}</div>
          </div>
          <div class="board">
            <template v-for="t in board(open)" :key="t.name">
              <div v-if="t.name" class="team"><span class="tn">{{ t.name }}</span><b>{{ t.frags }}</b></div>
              <div v-for="p in t.players" :key="p.name" class="pl" :class="{ bot: p.is_bot }">
                <span class="sw" :style="chip(p)" /><span class="pn">{{ p.name }}</span>
                <span v-if="p.tier" class="tier" :style="{ background: p.tier.color }">{{ p.tier.name }}</span>
                <span class="mu">{{ p.mu ?? '' }}</span><span class="ping">{{ p.is_bot ? 'bot' : (p.ping != null ? p.ping + 'ms' : '') }}</span>
                <b class="fr">{{ p.frags ?? '' }}</b>
              </div>
            </template>
          </div>
          <footer class="acts">
            <span class="specs">{{ open.spectators || 0 }} watching</span><span class="grow" />
            <a v-if="free(open) !== 0" class="act join" :href="`qw://${open.address}/`">Join</a>
            <a class="act" :href="`qw://${open.address}/observe`">Watch</a>
            <a v-if="open.qtv" class="act" :href="`qw://${open.qtv}/qtvplay`">QTV</a>
          </footer>
        </section>

        <section v-if="duel" class="col matchup">
          <h3>Matchup</h3>
          <div class="h2h"><span>{{ duel.a.display }}</span><b>{{ duel.h.wins_a ?? 0 }} – {{ duel.h.wins_b ?? 0 }}</b><span>{{ duel.b.display }}</span></div>
          <div v-if="duel.win != null" class="odds wide"><div class="fa" :style="{ width: (duel.win * 100) + '%' }">{{ pct(duel.win) }}</div><div class="fb">{{ pct(1 - duel.win) }}</div></div>
          <div class="cap">win chance · rating and head-to-head record</div>
          <template v-if="duel.m">
            <h3 class="gap">On {{ duel.m.map }}</h3>
            <div class="h2h"><span>{{ duel.m.rating_a?.wins ?? 0 }}–{{ duel.m.rating_a?.losses ?? 0 }} overall</span><b>{{ duel.m.h2h_wins_a }} – {{ duel.m.h2h_wins_b }}</b><span>{{ duel.m.rating_b?.wins ?? 0 }}–{{ duel.m.rating_b?.losses ?? 0 }} overall</span></div>
            <div v-if="duel.m.predict_win_a != null" class="odds wide"><div class="fa" :style="{ width: (duel.m.predict_win_a * 100) + '%' }">{{ pct(duel.m.predict_win_a) }}</div><div class="fb">{{ pct(1 - duel.m.predict_win_a) }}</div></div>
            <div class="cap">win chance on this map</div>
          </template>
          <h3 class="gap">Recent meetings</h3>
          <div v-for="(g, i) in duel.recent" :key="i" class="meet"><span class="dim">{{ day(g.date) }}</span><span>{{ g.map }}</span><b :class="g.frags_a > g.frags_b ? 'up' : 'down'">{{ g.frags_a }}–{{ g.frags_b }}</b></div>
          <div v-if="!duel.recent.length" class="dim">They have not met in a rated duel.</div>
        </section>

        <section v-for="p in known(open).slice(0, 8)" :key="p.id" class="col sheet">
          <template v-for="sh in [sheet(p, open)]" :key="p.id">
            <div class="who">
              <NuxtLink :to="`/p/${p.id}`" class="nm">{{ p.name }}</NuxtLink>
              <span v-if="sh.r?.tier" class="tier" :style="{ background: sh.r.tier.color }">{{ sh.r.tier.name }}</span>
            </div>
            <div v-if="sh.loading" class="dim">Loading…</div>
            <template v-else>
              <div class="nums">
                <div><b>{{ sh.r ? Math.round(sh.r.mu) : '—' }}</b><span>{{ rmode(open) }} rating</span></div>
                <div v-if="sh.r?.rank"><b>#{{ sh.r.rank }}</b><span>of {{ sh.r.total_rated }}</span></div>
                <div v-if="sh.r"><b>{{ sh.r.wins }}–{{ sh.r.losses }}</b><span>record</span></div>
                <div><b>{{ sh.lg }}</b><span>LG last 10</span></div>
                <div><b>{{ sh.rl }}</b><span>RL last 10</span></div>
              </div>
              <div v-if="rmode(open) === '1on1' && sh.games.length" class="form"><span v-for="g in sh.games" :key="g.match_id" class="fd" :class="g.outcome" /></div>
              <template v-if="sh.rows.length">
                <div class="srow head"><span>Duels, last year ({{ sh.advGames }})</span><span>all maps</span><span>{{ sh.mapGames ? open.map : '' }}</span></div>
                <div v-for="r in sh.rows" :key="r[0]" class="srow"><span>{{ r[0] }}</span><b>{{ r[1] }}</b><b class="dim">{{ r[2] || '' }}</b></div>
              </template>
              <div v-else class="dim small">No advanced duel stats on file.</div>
            </template>
          </template>
        </section>
        <div v-if="!known(open).length" class="empty">No DeepFrag profiles match the players on this server.</div>
      </div>

      <aside v-if="me" class="side">
        <section>
          <h3>Next ladder match</h3>
          <template v-if="nextMatch">
            <div class="big">{{ countdown(nextMatch.at) }}</div>
            <div class="l">vs <b>{{ nextMatch.opp }}</b></div>
            <div class="dim">{{ fmtWhen(nextMatch.at) }} · {{ nextMatch.ladder }}</div>
          </template>
          <div v-else class="dim">Nothing scheduled.</div>
        </section>
        <section>
          <h3>Last game</h3>
          <template v-if="last">
            <div class="big" :class="last.outcome">{{ last.player_frags ?? "—" }}–{{ last.opponent_frags ?? "—" }}</div>
            <div class="l">{{ last.outcome }} vs <b>{{ last.opponent_name }}</b></div>
            <div class="dim">{{ last.match_map }} · {{ last.match_mode }}</div>
          </template>
          <div v-else class="dim">No games yet.</div>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.wall { height: 100vh; display: flex; flex-direction: column; background: var(--bg); color: var(--fg);
        font-variant-numeric: tabular-nums; overflow: hidden; user-select: none; }
.grow { flex: 1; }
.dim { color: var(--fg-3); }

.bar { display: flex; align-items: center; gap: 14px; padding: 8px 12px; min-height: 56px; box-sizing: border-box; }
.title { font-size: 18px; font-weight: 900; text-transform: uppercase; letter-spacing: .08em; color: var(--accent); white-space: nowrap; }
.count { font-size: 14px; color: var(--fg-2); white-space: nowrap; }
.chips { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; }
.chipb, .arrow { font: inherit; color: var(--fg-2); background: var(--panel-2); border: 1px solid var(--border); border-radius: 999px;
                 padding: 0 16px; height: 40px; font-size: 15px; font-weight: 700; white-space: nowrap; cursor: pointer; }
.chipb.on { background: var(--accent); border-color: var(--accent); color: #111; }
.arrow { width: 72px; height: 44px; padding: 0; font-size: 30px; line-height: 1; color: var(--fg); }
.arrow:active, .chipb:active, .act:active { transform: scale(.96); }
.clock { font-size: 22px; font-weight: 800; white-space: nowrap; }
.warn { font-size: 13px; color: #ffb454; white-space: nowrap; }

.body { flex: 1; min-height: 0; display: flex; gap: 10px; padding: 0 12px 12px; }
.rail { flex: 1; min-width: 0; display: flex; gap: 10px; overflow: hidden; }
/* sideways swipes are iCUE's (they change Edge screens): the page takes vertical pans only */
.wall { touch-action: pan-y; }
.rail.swipe { overflow-x: auto; scroll-snap-type: x proximity; scrollbar-width: thin; touch-action: auto; }
.card { cursor: pointer; flex: 0 0 400px; scroll-snap-align: start; display: flex; flex-direction: column; min-height: 0;
        background: var(--panel); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.card.ours { border-color: rgba(255,122,26,.45); }
.card.idle { opacity: .6; }
.card.hot { border-color: var(--accent); animation: pulse 1.8s ease-in-out infinite; }
@keyframes pulse { 50% { box-shadow: inset 0 0 0 2px var(--accent), 0 0 22px rgba(255,122,26,.45); } }

.shot { padding: 10px 12px 10px; background: var(--panel-2) center / cover no-repeat; min-height: 128px; box-sizing: border-box;
        display: flex; flex-direction: column; }
.tags { display: flex; gap: 6px; align-items: center; }
.tag { font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .05em; padding: 3px 8px; border-radius: 6px;
       background: rgba(0,0,0,.6); color: #f2ead9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tag.mode { background: #f2ead9; color: #111; }
.tag.ladder { background: var(--accent); color: #111; }
.tag.ours { color: var(--accent); }
.map { margin-top: auto; font-size: 34px; font-weight: 900; line-height: 1.1; color: #fff; text-shadow: 0 2px 8px #000; }
.status { font-size: 15px; color: #d9cfbf; display: flex; align-items: center; gap: 7px; text-shadow: 0 1px 4px #000; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #7d7264; }
.status.live .dot { background: #4ade80; }

.board { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 12px; scrollbar-width: thin; }
.team { display: flex; justify-content: space-between; align-items: baseline; margin-top: 6px; padding: 2px 0;
        border-bottom: 1px solid var(--border); font-size: 15px; color: var(--fg-2); text-transform: uppercase; letter-spacing: .05em; }
.team b { font-size: 24px; color: var(--fg); }
.pl { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto 44px 52px 40px; gap: 8px; align-items: center; padding: 5px 0; font-size: 18px; }
.pl.bot { color: var(--fg-3); }
.sw { width: 12px; height: 20px; border-radius: 3px; background: var(--panel-3); }
.pn { font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tier { font-size: 11px; font-weight: 800; color: #111; padding: 2px 6px; border-radius: 5px; text-transform: uppercase; white-space: nowrap; }
.mu, .ping { font-size: 14px; color: var(--fg-2); text-align: right; }
.ping { color: var(--fg-3); }
.fr { text-align: right; font-size: 20px; }
.none { padding: 12px 0; font-size: 15px; }
.mine { flex: 1; padding: 18px 14px; font-size: 18px; font-weight: 700; }
.mine .dim { font-size: 14px; font-weight: 400; }

.odds { display: flex; height: 24px; margin: 0 12px 8px; border-radius: 7px; overflow: hidden; font-size: 13px; font-weight: 800; }
.fa { background: var(--accent); color: #111; display: flex; align-items: center; padding-left: 8px; min-width: 30%; max-width: 70%; white-space: nowrap; overflow: hidden; box-sizing: border-box; }
.fb { flex: 1; background: var(--panel-3); display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; min-width: 44px; }

.acts { display: flex; align-items: center; gap: 8px; padding: 8px 12px 10px; border-top: 1px solid var(--border); }
.specs { font-size: 13px; color: var(--fg-3); white-space: nowrap; }
.act { display: inline-flex; align-items: center; height: 44px; padding: 0 16px; border-radius: 10px; background: var(--panel-2);
       border: 1px solid var(--border); color: var(--fg); font-size: 16px; font-weight: 800; text-decoration: none; white-space: nowrap; }
.act.join { background: var(--accent); border-color: var(--accent); color: #111; }
.act small { font-weight: 600; font-size: 12px; }
.empty { align-self: center; margin: 0 auto; color: var(--fg-3); font-size: 18px; }

.side { flex: 0 0 300px; display: none; flex-direction: column; gap: 10px; }
.side section { flex: 1; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px; }
.side h3 { margin: 0 0 8px; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-3); }
.side .big { font-size: 52px; font-weight: 900; line-height: 1.1; }
.side .big.win { color: #4ade80; } .side .big.loss { color: #ff5d6c; }
.side .l { font-size: 18px; text-transform: capitalize; }
/* the side strip only at full width; at 1/3 (≈853px) two cards fill the frame exactly */
@media (min-width: 2000px) { .side { display: flex; } }
.col { flex: 0 0 400px; min-height: 0; overflow-y: auto; scrollbar-width: thin; box-sizing: border-box;
       background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 12px 14px; }
.col.srv { padding: 0; display: flex; flex-direction: column; overflow: hidden; }
.col h3 { margin: 0 0 8px; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-3); }
.col h3.gap { margin-top: 16px; }
.back { font: inherit; font-size: 15px; font-weight: 800; height: 40px; padding: 0 14px; border-radius: 10px; cursor: pointer;
        background: var(--accent); border: 0; color: #111; }
.h2h { display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: baseline; font-size: 16px; }
.h2h b { font-size: 30px; font-weight: 900; }
.h2h span:last-child { text-align: right; }
.odds.wide { margin: 8px 0 4px; height: 28px; font-size: 14px; }
.cap { font-size: 12px; color: var(--fg-3); }
.meet { display: grid; grid-template-columns: 64px 1fr auto; gap: 8px; font-size: 15px; padding: 3px 0; }
.up { color: #4ade80; } .down { color: #ff5d6c; }
.who { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.nm { font-size: 26px; font-weight: 900; color: var(--fg); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nums { display: flex; flex-wrap: wrap; gap: 6px 18px; }
.nums div { display: flex; flex-direction: column; }
.nums b { font-size: 22px; }
.nums span { font-size: 11px; color: var(--fg-3); text-transform: uppercase; letter-spacing: .06em; }
.form { display: flex; gap: 5px; margin-top: 10px; }
.fd { width: 16px; height: 16px; border-radius: 4px; background: var(--panel-3); }
.fd.win { background: #4ade80; } .fd.loss { background: #ff5d6c; }
.srow { display: grid; grid-template-columns: 1fr 64px 64px; gap: 8px; font-size: 15px; padding: 4px 0; border-bottom: 1px solid var(--border); }
.srow b { text-align: right; }
.srow.head { margin-top: 12px; font-size: 11px; color: var(--fg-3); text-transform: uppercase; letter-spacing: .06em; }
.srow.head span + span { text-align: right; }
.small { font-size: 13px; margin-top: 10px; }
@media (max-width: 900px) {
  .card, .col { flex-basis: calc(50% - 5px); }
  .count, .clock { display: none; }
}
@media (max-width: 620px) { .card, .col { flex-basis: 100%; } }
</style>

<script setup>
// Cockpit (Peter, 2026-11-13): a strip of live panels for a second screen — sized for the
// Corsair Xeneon Edge (2560×720, touch) but fluid on anything. Last game, recent form,
// our servers (tap to connect), open ladder challenges and the KovaaK's prep block.
// No live opponent info here: this page is meant to stay up while the owner plays.
// /cockpit → the signed-in player; /cockpit/{id} → anyone.
useHead({ title: 'Cockpit · DeepFrag' })

const route = useRoute()
const { user, fetchMe } = useAuth()
const id = computed(() => String(route.params.id || user.value?.canonical_id || '').toLowerCase())

const full = ref(null)
const fleet = ref(null)
const ladders = ref([])
const kv = ref(null)
const now = ref(Date.now())

async function getJson(url) {
  try { const r = await fetch(url, { cache: 'no-store' }); return r.ok ? await r.json() : null } catch { return null }
}
async function loadPlayer() { if (id.value) full.value = await getJson(`/api/players/${encodeURIComponent(id.value)}/full?t=${Date.now()}`) }
async function loadFleet() { fleet.value = await getJson('/api/fleet/live') }
async function loadLadders() {
  const out = []
  for (const lid of [2, 1]) { const d = await getJson(`/api/ladder/${lid}`); if (d) out.push(d) }
  ladders.value = out
}
async function loadKv() { if (id.value) kv.value = await getJson(`/api/players/${encodeURIComponent(id.value)}/kovaaks`) }

const timers = []
onMounted(async () => {
  await fetchMe()
  loadPlayer(); loadFleet(); loadLadders(); loadKv()
  timers.push(setInterval(loadFleet, 10_000), setInterval(loadPlayer, 60_000),
              setInterval(loadLadders, 60_000), setInterval(loadKv, 600_000),
              setInterval(() => { now.value = Date.now() }, 30_000))
})
onBeforeUnmount(() => timers.forEach(clearInterval))
watch(id, () => { loadPlayer(); loadKv() })

const games = computed(() => (full.value?.recent_matches || []).filter(m => m.match_mode === '1on1' || m.match_mode === '2on2' || m.match_mode === '4on4'))
const last = computed(() => games.value[0] || null)
const form = computed(() => games.value.filter(m => m.match_mode === '1on1').slice(0, 12))
const ratingNow = computed(() => form.value.find(m => m.rating_after != null)?.rating_after ?? null)
const ratingDay = computed(() => {
  const cut = Date.now() - 24 * 3600e3
  return form.value.filter(m => new Date(m.match_date).getTime() >= cut && m.rating_delta != null)
    .reduce((s, m) => s + m.rating_delta, 0)
})

function ago(iso) {
  const s = Math.max(0, (now.value - new Date(iso).getTime()) / 1000)
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}
const pct = v => v == null ? '—' : `${Math.round(v * 100)}%`
const signed = v => v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`

// Servers: one tile per port; busy ports first, then by city.
const ports = computed(() => [...(fleet.value?.servers || [])].sort((a, b) =>
  (b.players?.length || 0) - (a.players?.length || 0) || a.city.localeCompare(b.city) || a.port - b.port))

// Ladder: open/scheduled challenges the player's team is in.
const myChallenges = computed(() => {
  const out = []
  for (const d of ladders.value) {
    const mine = (d.teams || []).filter(t => (t.members || []).some(m => m.id === id.value)).map(t => t.id)
    for (const c of d.challenges || []) {
      if (!mine.includes(c.challenger_id) && !mine.includes(c.challenged_id)) continue
      const meChallenger = mine.includes(c.challenger_id)
      const myTeam = meChallenger ? c.challenger_id : c.challenged_id
      const turn = c.status === 'scheduled' ? null : (!c.proposed?.length ? c.challenger_id : (c.proposed_by === c.challenger_id ? c.challenged_id : c.challenger_id))
      const future = (c.proposed || []).filter(t => new Date(t).getTime() > Date.now())
      out.push({ ...c, ladder: d.ladder?.name || `Ladder ${d.ladder?.id}`, opp: meChallenger ? c.challenged : c.challenger,
                 myTurn: turn === myTeam, future })
    }
  }
  return out
})
const fmtWhen = iso => new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
</script>

<template>
  <div class="cockpit">
    <div v-if="!id" class="empty-all">Sign in, or open <code>/cockpit/your-id</code>.</div>
    <template v-else>
      <!-- LAST GAME -->
      <section class="panel last">
        <h3>Last game <span v-if="last" class="sub">{{ ago(last.match_date) }}</span></h3>
        <template v-if="last">
          <div class="vs">
            <span class="result" :class="last.outcome || 'team'">{{ last.outcome || last.match_mode }}</span>
            <span class="opp">{{ last.match_mode === '1on1' ? 'vs ' + (last.opponent_name || '?') : last.match_mode }}</span>
          </div>
          <div class="score">{{ last.player_frags ?? '—' }}<span v-if="last.opponent_frags != null" class="dim"> – {{ last.opponent_frags }}</span></div>
          <div class="meta">{{ last.match_map }} · {{ last.server_hostname || '' }}</div>
          <div class="nums">
            <div><b>{{ pct(last.lg_acc) }}</b><span>LG</span></div>
            <div><b>{{ pct(last.rl_acc) }}</b><span>RL</span></div>
            <div><b :class="last.rating_delta >= 0 ? 'up' : 'down'">{{ signed(last.rating_delta) }}</b><span>rating</span></div>
          </div>
        </template>
        <div v-else class="empty">No games yet.</div>
      </section>

      <!-- FORM -->
      <section class="panel form">
        <h3>1on1 form <span class="sub" v-if="ratingNow != null">rating {{ Math.round(ratingNow) }} · 24h <b :class="ratingDay >= 0 ? 'up' : 'down'">{{ signed(ratingDay) }}</b></span></h3>
        <div class="strip">
          <div v-for="m in form" :key="m.match_id" class="g" :class="m.outcome">
            <span class="o">{{ m.outcome === 'win' ? 'W' : m.outcome === 'loss' ? 'L' : 'D' }}</span>
            <span class="n">{{ m.opponent_name }}</span>
            <span class="d" :class="m.rating_delta >= 0 ? 'up' : 'down'">{{ signed(m.rating_delta) }}</span>
          </div>
          <div v-if="!form.length" class="empty">No duels yet.</div>
        </div>
      </section>

      <!-- SERVERS -->
      <section class="panel servers">
        <h3>Our servers <span class="sub">{{ fleet ? 'live' : 'checking…' }}</span></h3>
        <div class="ports">
          <a v-for="s in ports" :key="s.address" class="port" :class="{ down: !s.up, busy: s.players?.length }"
             :href="`qw://${s.address}`" :title="`Connect to ${s.address}`">
            <span class="where">{{ s.city }} {{ s.slot }}</span>
            <template v-if="s.up">
              <span class="who">{{ s.players?.length ? s.players.map(p => p.name).join(' · ') : 'empty' }}</span>
              <span class="st">{{ s.map }} · {{ s.status }}<template v-if="s.spectators?.length"> · {{ s.spectators.length }} spec</template></span>
            </template>
            <span v-else class="who">no answer</span>
          </a>
        </div>
      </section>

      <!-- LADDER -->
      <section class="panel ladder">
        <h3>Ladder</h3>
        <div v-for="c in myChallenges" :key="c.id" class="ch" :class="{ turn: c.myTurn }">
          <div class="l1"><b>vs {{ c.opp }}</b> <span class="dim">{{ c.ladder }}</span></div>
          <div v-if="c.status === 'scheduled'" class="l2">Scheduled {{ c.agreed_at ? fmtWhen(c.agreed_at) : '' }}</div>
          <div v-else-if="c.myTurn" class="l2 act">Your move — {{ c.future.length ? 'pick a time' : 'offer times' }}</div>
          <div v-else class="l2">Waiting on {{ c.opp }}</div>
          <div class="l3 dim">play by {{ fmtWhen(c.deadline) }}</div>
          <NuxtLink v-if="c.myTurn" to="/ladder" class="go">Open</NuxtLink>
        </div>
        <div v-if="!myChallenges.length" class="empty">No open challenges.</div>
      </section>

      <!-- PREP -->
      <section class="panel prep">
        <h3>KovaaK's <span v-if="kv?.user" class="sub">{{ kv.user }} · target {{ kv.sens_cm360 ?? '?' }} cm</span></h3>
        <template v-if="kv?.scenarios?.length">
          <div v-for="r in kv.scenarios.slice(0, 7)" :key="r.scenario" class="kv">
            <span class="sn">{{ r.scenario }}</span>
            <span class="pl dim">{{ r.plays }}×</span>
            <span class="bs">{{ Math.round(r.best) }}</span>
            <span class="cm" :class="r.sens_match === false ? 'bad' : 'ok'" :title="r.sens_match === false ? 'Best run was at a different sens than your QW sens' : 'At your QW sens'">{{ r.cm360 }} cm</span>
          </div>
        </template>
        <div v-else class="empty">Add <code>kovaaks</code> to your config profile to track it here.</div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cockpit {
  --gap: 12px;
  min-height: 100vh; box-sizing: border-box; padding: var(--gap);
  display: grid; gap: var(--gap);
  grid-template-columns: 1.1fr 1.2fr 1.6fr 1fr 1.2fr;
  background: var(--bg); color: var(--fg);
  font-variant-numeric: tabular-nums;
}
@media (max-width: 1400px) { .cockpit { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .cockpit { grid-template-columns: 1fr; padding: 16px; } }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; min-width: 0; overflow: hidden; }
h3 { margin: 0 0 10px; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--fg-3); display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.sub { text-transform: none; letter-spacing: 0; color: var(--fg-3); font-weight: 400; }
.dim { color: var(--fg-3); }
.up { color: #4ade80; } .down { color: #ff5d6c; }
.empty, .empty-all { color: var(--fg-3); font-size: 14px; }
.empty-all { grid-column: 1 / -1; text-align: center; padding: 40px; }

.vs { display: flex; gap: 10px; align-items: center; }
.result { font-weight: 800; text-transform: uppercase; font-size: 13px; padding: 3px 8px; border-radius: 6px; background: var(--panel-3); }
.result.win { background: rgba(74,222,128,.15); color: #4ade80; }
.result.loss { background: rgba(255,93,108,.15); color: #ff5d6c; }
.opp { font-size: 20px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.score { font-size: 56px; font-weight: 900; line-height: 1.05; margin: 8px 0 2px; }
.meta { color: var(--fg-2); font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nums { display: flex; gap: 22px; margin-top: 14px; }
.nums div { display: flex; flex-direction: column; }
.nums b { font-size: 26px; }
.nums span { font-size: 12px; color: var(--fg-3); text-transform: uppercase; letter-spacing: .06em; }

.strip { display: flex; flex-direction: column; gap: 4px; }
.g { display: grid; grid-template-columns: 22px 1fr auto; gap: 8px; font-size: 15px; padding: 3px 6px; border-radius: 6px; }
.g .o { font-weight: 800; }
.g.win .o { color: #4ade80; } .g.loss .o { color: #ff5d6c; }
.g .n { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ports { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.port { display: flex; flex-direction: column; gap: 2px; padding: 10px; border-radius: 10px; background: var(--panel-2);
        border: 1px solid var(--border); color: var(--fg); text-decoration: none; min-height: 64px; }
.port:active { transform: scale(.98); }
.port.busy { border-color: var(--accent); background: rgba(255,122,26,.08); }
.port.down { opacity: .5; }
.where { font-weight: 700; font-size: 14px; }
.who { font-size: 13px; color: var(--fg-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st { font-size: 11px; color: var(--fg-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ch { padding: 8px 10px; border-radius: 8px; background: var(--panel-2); margin-bottom: 8px; position: relative; }
.ch.turn { border: 1px solid var(--accent); }
.l1 { font-size: 15px; } .l2 { font-size: 13px; color: var(--fg-2); } .l2.act { color: var(--accent); font-weight: 700; }
.l3 { font-size: 12px; }
.go { position: absolute; right: 10px; top: 10px; font-size: 13px; color: var(--accent); }

.kv { display: grid; grid-template-columns: 1fr auto auto auto; gap: 10px; font-size: 13px; padding: 3px 0; border-bottom: 1px solid var(--border); }
.kv .sn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cm.ok { color: #4ade80; } .cm.bad { color: #ff5d6c; }
code { background: var(--panel-3); padding: 1px 5px; border-radius: 4px; }
</style>

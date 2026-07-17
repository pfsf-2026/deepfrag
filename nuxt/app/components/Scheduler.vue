<script setup>
// Doodle-style match scheduler for one challenge.
//  - Challenger: check every slot your team can play over the next 7 days → save.
//  - Challenged: pick one of the proposed slots + confirm the server → scheduled.
// Slots are stored as UTC ISO strings; each side sees them in their LOCAL time.
const props = defineProps({
  challenge: { type: Object, required: true },
  userTeamId: { type: Number, default: null }
})
const emit = defineEmits(['done', 'saved', 'close'])
const { user, authHeader } = useAuth()
const showSettings = useState('show-settings', () => false)
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

// Display zone: preferred tz → state-derived → ET fallback (with a nudge link).
const tz = computed(() => resolveTz(user.value))
const tzIsGuess = computed(() => !tzKnown(user.value))

const c = props.challenge
const scheduled = computed(() => !!c.agreed_at)
const isAdmin = computed(() => !!user.value?.is_admin)
const proposedByLocal = ref(c.proposed_by ?? null)
const countering = ref(false)   // turn team chose "suggest different times"

function teamName(id) { return id === c.challenger_id ? c.challenger : (id === c.challenged_id ? c.challenged : `#${id}`) }
// Whose turn: no slots → EITHER team may open (null = both; challenger-only
// until 2026-07-15 — it let a stalling challenger trap the challenged team,
// whose deadline clock kept running). Else the team that did NOT post the
// current slots picks/counters.
const turnTeamId = computed(() => {
  if (!proposedLocal.value.length) return null
  return proposedByLocal.value === c.challenger_id ? c.challenged_id : c.challenger_id
})
const onEitherTeam = computed(() =>
  props.userTeamId === c.challenger_id || props.userTeamId === c.challenged_id)
const isMyTurn = computed(() => isAdmin.value ||
  (turnTeamId.value === null ? onEitherTeam.value : props.userTeamId === turnTeamId.value))
const proposerName = computed(() => proposedByLocal.value ? teamName(proposedByLocal.value) : c.challenger)

// ── availability grid — ET-anchored prime time (NA ladder) ─────────────────
// 7pm → 2am ET, hourly. The 12/1/2am slots belong to the SAME evening (they roll
// to the next ET calendar day). Slots stored as UTC ISO; labelled in ET.
const HOURS_ET = [19, 20, 21, 22, 23, 0, 1, 2]
// 30-min granularity: each prime hour split into :00 and :30 (16 slots/evening).
const SLOTS_ET = HOURS_ET.flatMap((h) => [h, h + 0.5])
const ET = 'America/New_York'
// UTC instant for wall-clock h:00 ET on (y, mo, d), DST-correct AND independent
// of the viewer's browser timezone. We get ET's offset by formatting the same
// instant in ET and in UTC, parsing both as local time — the browser's own zone
// cancels in the difference, leaving ET's true offset. (The previous version
// subtracted only the ET-parsed value, so it silently baked in the browser's
// offset and mis-placed every slot for non-UTC users.)
function etToUtcISO(y, mo, d, h, mi) {
  const asUTC = Date.UTC(y, mo, d, h, mi || 0, 0)
  const inst = new Date(asUTC)
  const etMs = new Date(inst.toLocaleString('en-US', { timeZone: ET })).getTime()
  const utcMs = new Date(inst.toLocaleString('en-US', { timeZone: 'UTC' })).getTime()
  return new Date(asUTC + (utcMs - etMs)).toISOString()
}
const proposedLocal = ref([...(c.proposed || [])])   // updates in-place after save
const selected = ref(new Set(c.proposed || []))
const days = computed(() => {
  const out = []
  // "today" in ET
  const nowET = new Date(new Date().toLocaleString('en-US', { timeZone: ET }))
  for (let off = 0; off < 7; off++) {
    const base = new Date(nowET); base.setDate(nowET.getDate() + off)
    const y = base.getFullYear(), mo = base.getMonth(), d = base.getDate()
    const slots = SLOTS_ET.map((hf) => {
      const h = Math.floor(hf), mi = (hf - h) * 60
      const dd = h < 7 ? d + 1 : d   // 12/1/2am ET roll to next ET day
      const iso = etToUtcISO(y, mo, dd, h, mi)
      // Anchored to ET, labelled in the viewer's zone. Compact: "7pm" / "7:30pm".
      const label = new Date(iso).toLocaleTimeString('en-US', { timeZone: tz.value, hour: 'numeric', minute: '2-digit' }).replace(':00', '').replace(' ', '').toLowerCase()
      return { iso, label, past: new Date(iso).getTime() < Date.now() }
    })
    // Row date = that evening's first (7pm ET) slot, in the viewer's zone.
    out.push({ label: new Date(slots[0].iso).toLocaleDateString('en-US', { timeZone: tz.value, weekday: 'short', month: 'short', day: 'numeric' }), slots })
  }
  return out
})
function toggle(iso) { selected.value.has(iso) ? selected.value.delete(iso) : selected.value.add(iso); selected.value = new Set(selected.value) }

const saving = ref(false)
const err = ref('')
async function saveAvailability() {
  if (selected.value.size === 0) { err.value = 'Pick at least one slot'; return }
  saving.value = true; err.value = ''
  try {
    await $fetch(`${base}/api/ladder/challenge/${c.id}/availability`, {
      method: 'POST', headers: authHeader(), body: { slots: [...selected.value] }
    })
    // Advance in-place instead of closing. The proposer is whoever's turn it
    // was — for the opening proposal (turn=null, either team) it's MY team,
    // falling back to challenger for a pure admin.
    const justBy = turnTeamId.value ?? (onEitherTeam.value ? props.userTeamId : c.challenger_id)
    proposedLocal.value = [...selected.value]
    proposedByLocal.value = justBy
    countering.value = false
    pick.value = ''
    emit('saved')                 // background board refresh, keep modal open
    if (view.value === 'act') loadSuggestions()
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not save' } finally { saving.value = false }
}

// ── per-individual picks (challenged team) ──────────────────────────────────
// Each challenged player selects ALL offered slots they can play; when both have
// submitted, the backend auto-schedules at the earliest common slot.
const amChallenged = computed(() => props.userTeamId && props.userTeamId === c.challenged_id)
const myCanon = computed(() => user.value?.canonical_id)
const myPicks = ref(new Set((c.picks && myCanon.value && c.picks[myCanon.value]) || []))
const picksStatus = ref('')
function toggleMyPick(iso) {
  myPicks.value.has(iso) ? myPicks.value.delete(iso) : myPicks.value.add(iso)
  myPicks.value = new Set(myPicks.value)
}
async function submitMyPicks() {
  if (!myPicks.value.size) { err.value = 'Pick at least one time you can play'; return }
  saving.value = true; err.value = ''
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/my-picks`, {
      method: 'POST', headers: authHeader(), body: { slots: [...myPicks.value] }
    })
    emit('saved')
    if (r.scheduled) { emit('done') }                       // both picked → auto-scheduled
    else if (r.no_common) { picksStatus.value = '⚠️ Submitted — but you and your teammate have no overlapping time. Coordinate, or suggest different times below.' }
    else { picksStatus.value = '✓ Submitted — waiting on your teammate to pick their times.' }
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not submit your times' } finally { saving.value = false }
}

// ── pick a slot (challenger, after a counter) ───────────────────────────────
const pick = ref('')
const server = ref(c.server || user.value?.favorite_server || '')
// Server suggestions from both teams' real ping history.
const suggestions = ref([])
const sugLoading = ref(false)
async function loadSuggestions() {
  sugLoading.value = true
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/server-suggestion`)
    suggestions.value = r.suggestions || []
    if (!server.value && suggestions.value[0]) server.value = suggestions.value[0].host
  } catch { suggestions.value = [] } finally { sugLoading.value = false }
}
function fmtLocal(iso) {
  // Viewer's resolved zone (with the zone abbreviation so it's unambiguous).
  return new Date(iso).toLocaleString('en-US', { timeZone: tz.value, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}

// ── general-availability overlay ────────────────────────────────────────────
// Each involved player's general weekly availability (in their OWN tz). For a
// given slot we convert the instant into each player's tz, then check whether
// that weekday/hour falls in their free hours — so a slot shows "2 usually free".
const ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const overlayPlayers = ref([])   // flat list, each tagged with its team
const overlayMeta = ref({ total: 0, withAvail: 0 })
async function loadOverlay() {
  try {
    const r = await $fetch(`${base}/api/ladder/challenge/${c.id}/availability`)
    const teams = r.teams || []
    overlayPlayers.value = teams.flatMap(t => (t.players || []).map(p => ({ ...p, team: t.name, teamId: t.id })))
    overlayMeta.value = { total: r.total_players || 0, withAvail: r.with_availability || 0 }
  } catch { overlayPlayers.value = [] }
}
function partsInTz(iso, ptz) {
  const fmt = new Intl.DateTimeFormat('en-US', { timeZone: ptz || ET, weekday: 'short', hour: '2-digit', hourCycle: 'h23' })
  let wd = '', hr = 0
  for (const p of fmt.formatToParts(new Date(iso))) {
    if (p.type === 'weekday') wd = p.value.toLowerCase()
    if (p.type === 'hour') hr = parseInt(p.value, 10) % 24
  }
  return { wd, hr }
}
function playerFree(pl, wd, hr) {
  const s = pl.slots || {}
  if ((s[wd] || []).includes(hr)) return true
  if (hr <= 2) {                                  // late-night wrap (free until 1/2am the night before)
    const prev = ORDER[(ORDER.indexOf(wd) - 1 + 7) % 7]
    if ((s[prev] || []).includes(hr + 24)) return true
  }
  return false
}
function freeAt(iso) {
  const out = []
  for (const pl of overlayPlayers.value) {
    const { wd, hr } = partsInTz(iso, pl.tz)
    if (playerFree(pl, wd, hr)) out.push(pl)
  }
  return out
}
function freeCount(iso) { return freeAt(iso).length }
// Free players grouped by team → [{team, names:[...]}], so the overlay shows
// WHO from WHICH team is usually around at that time.
function freeGroups(iso) {
  const byTeam = new Map()
  for (const p of freeAt(iso)) {
    if (!byTeam.has(p.team)) byTeam.set(p.team, [])
    byTeam.get(p.team).push(p.name)
  }
  return [...byTeam.entries()].map(([team, names]) => ({ team, names }))
}
function freeTitle(iso) {
  const g = freeGroups(iso)
  return g.length ? `Usually free — ${g.map(x => `${x.team}: ${x.names.join(', ')}`).join(' · ')}` : ''
}
const hasOverlay = computed(() => overlayMeta.value.withAvail > 0)
async function confirmSlot() {
  if (!pick.value) { err.value = 'Pick a time'; return }
  saving.value = true; err.value = ''
  try {
    await $fetch(`${base}/api/ladder/challenge/${c.id}/schedule`, {
      method: 'POST', headers: authHeader(), body: { slot: pick.value, server: server.value }
    })
    emit('done')
  } catch (e) { err.value = e?.data?.detail || e?.message || 'Could not schedule' } finally { saving.value = false }
}

// Which view: scheduled summary > challenger-fills (no proposed yet, or editing) >
// challenged-picks (proposed exist) > waiting.
const view = computed(() => {
  if (scheduled.value) return 'done'
  const has = proposedLocal.value.length > 0
  if (!has) return isMyTurn.value ? 'fill' : 'waiting-fill'  // challenger proposes first
  if (isMyTurn.value) return countering.value ? 'fill' : 'act'  // pick OR suggest different
  return 'waiting-pick'                                       // I proposed; opponent's move
})

onMounted(() => { loadOverlay(); if (view.value === 'act') loadSuggestions() })
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal" :class="{ wide: view === 'fill' }">
      <div class="m-head">
        <h3>Schedule · {{ c.challenger }} vs {{ c.challenged }}</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>

      <!-- already scheduled -->
      <div v-if="view === 'done'" class="done">
        <div class="big">📅 {{ fmtLocal(c.agreed_at) }}</div>
        <div v-if="c.server" class="muted">Server: <strong>{{ c.server }}</strong></div>
        <div class="muted small" style="margin-top:8px;">Shown in your local time. Good luck!</div>
      </div>

      <!-- propose / counter-propose availability -->
      <template v-else-if="view === 'fill'">
        <p class="lede">
          Check every slot <strong>your team</strong> can play over the next 7 days — the other team picks one (or suggests different times).
        </p>
        <div class="tz-note">
          🕒 Times shown in <strong>{{ tz }}</strong>. Prime time is 7pm–2am ET.
          <a v-if="tzIsGuess" class="tz-link" @click="showSettings = true">Showing Eastern — set your time zone →</a>
        </div>
        <button v-if="countering" class="link-btn" @click="countering = false">← back to {{ proposerName }}'s times</button>
        <p v-if="hasOverlay" class="legend"><span class="fdot">2</span> = players (either team) whose general availability covers that time — hover a slot to see who. Set yours from the ladder page.</p>
        <div class="grid-scroll">
          <div class="grid">
            <div v-for="day in days" :key="day.label" class="day">
              <div class="day-lbl">{{ day.label }}</div>
              <div class="slots">
                <button v-for="s in day.slots" :key="s.iso" class="slot"
                        :class="{ on: selected.has(s.iso), past: s.past }" :disabled="s.past"
                        :title="freeTitle(s.iso)" @click="toggle(s.iso)">{{ s.label }}<span
                        v-if="freeCount(s.iso)" class="fdot" :class="{ allfree: freeCount(s.iso) === overlayMeta.withAvail }">{{ freeCount(s.iso) }}</span></button>
              </div>
            </div>
          </div>
        </div>
        <p v-if="err" class="err">{{ err }}</p>
        <div class="m-actions">
          <button class="btn ghost" @click="emit('close')">Cancel</button>
          <button class="btn" :disabled="saving" @click="saveAvailability">{{ saving ? 'Saving…' : `Save ${selected.size} slot${selected.size === 1 ? '' : 's'}` }}</button>
        </div>
      </template>

      <!-- pick a slot (or counter with different times) -->
      <template v-else-if="view === 'act'">
        <!-- per-individual: each challenged player ticks every offered slot they can play -->
        <template v-if="amChallenged">
          <p class="lede"><strong>{{ proposerName }}</strong> offered these times — tick <strong>every slot you can play</strong>. When both teammates submit, the match auto-schedules at your earliest common time.</p>
          <div class="tz-note">🕒 Times in <strong>{{ tz }}</strong>.</div>
          <div class="picklist">
            <label v-for="iso in proposedLocal" :key="iso" class="pickrow" :class="{ on: myPicks.has(iso) }">
              <input type="checkbox" :checked="myPicks.has(iso)" @change="toggleMyPick(iso)">
              <span class="pl-time">{{ fmtLocal(iso) }}</span>
              <span v-if="freeCount(iso)" class="pl-free"><span class="fdot" :class="{ allfree: freeCount(iso) === overlayMeta.withAvail }">{{ freeCount(iso) }}</span></span>
            </label>
          </div>
          <button class="link-btn" @click="countering = true">None of these work — suggest different times →</button>
          <p v-if="picksStatus" class="muted small">{{ picksStatus }}</p>
          <p v-if="err" class="err">{{ err }}</p>
          <div class="m-actions">
            <button class="btn ghost" @click="emit('close')">Cancel</button>
            <button class="btn" :disabled="saving || !myPicks.size" @click="submitMyPicks">{{ saving ? 'Submitting…' : `Submit my ${myPicks.size} time${myPicks.size === 1 ? '' : 's'}` }}</button>
          </div>
        </template>
        <template v-else>
        <p class="lede"><strong>{{ proposerName }}</strong> proposed these times — pick one, or suggest different times.</p>
        <div class="tz-note">
          🕒 Times in <strong>{{ tz }}</strong>.
          <a v-if="tzIsGuess" class="tz-link" @click="showSettings = true">Showing Eastern — set your time zone →</a>
        </div>
        <div class="picklist">
          <label v-for="iso in proposedLocal" :key="iso" class="pickrow" :class="{ on: pick === iso }">
            <input type="radio" :value="iso" v-model="pick">
            <span class="pl-time">{{ fmtLocal(iso) }}</span>
            <span v-if="freeCount(iso)" class="pl-free">
              <span class="fdot" :class="{ allfree: freeCount(iso) === overlayMeta.withAvail }">{{ freeCount(iso) }}</span>
              <span v-for="g in freeGroups(iso)" :key="g.team" class="ftag">{{ g.team }}: {{ g.names.join(', ') }}</span>
            </span>
          </label>
        </div>
        <button class="link-btn" @click="countering = true">None of these work — suggest different times →</button>
        <div class="fld">
          <span>Server <span class="muted">— suggested from both teams' ping history</span></span>
          <div v-if="sugLoading" class="muted small">Crunching pings…</div>
          <div v-else-if="suggestions.length" class="sug-list">
            <button v-for="(s, i) in suggestions" :key="s.host" class="sug" :class="{ on: server === s.host }" @click="server = s.host">
              <div class="sug-head">
                <span v-if="i === 0" class="best">BEST</span>
                <strong>{{ s.host }}</strong>
                <span class="muted">{{ s.city || s.country || 'NA' }}</span>
                <span class="sug-ping">worst {{ s.max_ping }}ms · avg {{ s.avg_ping }}ms</span>
              </div>
              <div class="sug-pings">
                <span v-for="p in s.pings" :key="p.player" :class="{ est: p.est, none: p.ping == null }">
                  {{ p.name }}: {{ p.ping == null ? '—' : p.ping + (p.est ? '*' : '') }}
                </span>
              </div>
            </button>
            <div class="muted small">* estimated from location (no ping history yet)</div>
          </div>
          <div v-else class="muted small">No ping history yet — enter a server manually.</div>
          <input v-model="server" placeholder="server hostname" style="margin-top:8px;">
        </div>
        <p v-if="err" class="err">{{ err }}</p>
        <div class="m-actions">
          <button class="btn ghost" @click="emit('close')">Cancel</button>
          <button class="btn" :disabled="saving" @click="confirmSlot">{{ saving ? 'Scheduling…' : 'Confirm match' }}</button>
        </div>
        </template>
      </template>

      <!-- waiting states -->
      <div v-else class="done">
        <p v-if="view === 'waiting-pick'" class="muted">✓ You proposed {{ proposedLocal.length }} time{{ proposedLocal.length === 1 ? '' : 's' }}. Waiting for <strong>{{ teamName(turnTeamId) }}</strong> to pick one or suggest different times.</p>
        <p v-else class="muted">No times posted yet — either team can post availability. (Log in as a player on <strong>{{ c.challenger }}</strong> or <strong>{{ c.challenged }}</strong> to post yours.)</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 22px 24px; width: 100%; max-width: 560px; max-height: 90vh; overflow-y: auto; }
/* The propose grid needs room for all 8 slots on one line per day. */
.modal.wide { max-width: 780px; }
.m-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.m-head h3 { margin: 0; font-size: 17px; font-weight: 800; }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.lede { color: var(--fg-2); font-size: 13px; margin: 6px 0 16px; }
.grid-scroll { overflow-x: auto; }
.grid { display: flex; flex-direction: column; gap: 8px; min-width: 560px; }
.day { display: grid; grid-template-columns: 92px 1fr; gap: 10px; align-items: center; }
.day-lbl { font-size: 12px; color: var(--fg-2); font-weight: 700; white-space: nowrap; }
/* 16 half-hour slots -> 2 rows of 8 (the grid-scroll wrapper handles tiny screens). */
.slots { display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px; }
.slot { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg-2); border-radius: 6px; padding: 5px 3px; font-size: 11px; cursor: pointer; font-family: 'JetBrains Mono', monospace; white-space: nowrap; text-align: center; position: relative; }
.slot.on { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 700; }
.slot.past { opacity: 0.3; cursor: not-allowed; }
.slot:not(.past):hover { border-color: var(--accent); }
.picklist { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.pickrow { display: flex; align-items: center; gap: 10px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; cursor: pointer; font-size: 14px; }
.pickrow.on { border-color: var(--accent); background: rgba(20,230,192,0.08); }
.fld { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.fld > span { font-size: 12px; color: var(--fg-3); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
.muted { color: var(--fg-3); font-weight: 400; text-transform: none; }
.fld input { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 10px 12px; border-radius: 8px; font-family: inherit; font-size: 14px; }
.fld input:focus { outline: none; border-color: var(--accent); }
.sug-list { display: flex; flex-direction: column; gap: 6px; }
.sug { text-align: left; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; cursor: pointer; font-family: inherit; }
.sug.on { border-color: var(--accent); background: rgba(20,230,192,0.08); }
.sug-head { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--fg); flex-wrap: wrap; }
.sug-head .best { background: var(--accent); color: var(--bg); font-size: 9px; font-weight: 800; padding: 1px 6px; border-radius: 4px; }
.sug-head .sug-ping { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg-2); }
.sug-pings { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; font-size: 11px; color: var(--fg-3); font-family: 'JetBrains Mono', monospace; }
.sug-pings .est { color: var(--draw); }
.sug-pings .none { opacity: 0.5; }
.small { font-size: 11px; }
.done { text-align: center; padding: 20px 0; }
.done .big { font-size: 20px; font-weight: 800; margin-bottom: 6px; }
.small { font-size: 12px; }
.m-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 10px 16px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
.btn:disabled { opacity: 0.6; cursor: wait; }
.err { color: var(--loss); font-size: 13px; margin: 4px 0 8px; }
.tz-note { font-size: 12px; color: var(--fg-3); margin: -8px 0 12px; }
.tz-note strong { color: var(--fg-2); }
.tz-link { color: var(--accent); cursor: pointer; margin-left: 6px; }
.tz-link:hover { text-decoration: underline; }
.link-btn { background: none; border: 0; color: var(--accent); font-size: 12px; cursor: pointer; padding: 4px 0 10px; font-family: inherit; }
.link-btn:hover { text-decoration: underline; }
/* general-availability overlay */
.slot { position: relative; }
.fdot { display: inline-flex; align-items: center; justify-content: center; min-width: 14px; height: 14px; padding: 0 3px; margin-left: 5px; border-radius: 7px; background: var(--draw); color: var(--bg); font-size: 9px; font-weight: 800; vertical-align: middle; }
.fdot.allfree { background: var(--win); }
.slot .fdot { position: absolute; top: -6px; right: -6px; margin: 0; border: 1px solid var(--panel); }
.legend { font-size: 11px; color: var(--fg-3); margin: -4px 0 12px; display: flex; align-items: center; gap: 6px; }
.legend .fdot { position: static; }
.pickrow { flex-wrap: wrap; }
.pl-free { margin-left: auto; font-size: 11px; color: var(--fg-3); display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.pl-free .fdot { position: static; }
.ftag { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 1px 7px; }
.ftag strong { color: var(--fg-2); }
</style>

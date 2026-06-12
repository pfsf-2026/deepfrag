<script setup>
// Player Rating Cards (Decision & Skill Framework, R1). Renders the admin
// player-cards payload: 4 grouped tables (Top-20 overall + top-10 Div 1/2/3),
// each row scored on 8 Tier-A attributes (0-99). Click a name → card modal.
const props = defineProps({
  apiBase: { type: String, default: '' },
  headers: { type: Object, default: () => ({}) },
})

const pending = ref(true)
const err = ref('')
const data = ref(null)
const sortKey = ref('ovr')
const sortDir = ref('desc')      // 'desc' | 'asc'
const selected = ref(null)        // the player object for the modal

async function load() {
  pending.value = true; err.value = ''
  try {
    data.value = await $fetch(`${props.apiBase}/api/admin/player-cards?mode=1on1`, { headers: props.headers })
  } catch (e) {
    err.value = e?.data?.detail || e?.message || 'Failed to load cards'
  } finally {
    pending.value = false
  }
}
onMounted(load)

const attrs = computed(() => data.value?.attributes || [])

function setSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  else { sortKey.value = key; sortDir.value = 'desc' }
}
function attrVal(p, key) {
  if (key === 'ovr') return p.ovr
  if (key === 'rank') return p.rank
  return p.attrs?.find(a => a.key === key)?.value
}
function sortedPlayers(players) {
  const dir = sortDir.value === 'desc' ? -1 : 1
  return [...players].sort((a, b) => {
    const av = attrVal(a, sortKey.value), bv = attrVal(b, sortKey.value)
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return (av - bv) * dir
  })
}

// Madden-style colour ramp for a 0-99 rating.
function ratingColor(v) {
  if (v == null) return 'var(--fg-3, #64748b)'
  if (v >= 90) return '#fbbf24'
  if (v >= 80) return '#22c55e'
  if (v >= 68) return '#84cc16'
  if (v >= 55) return '#eab308'
  if (v >= 42) return '#f59e0b'
  return '#ef4444'
}
function ovrText(v) { return v == null ? '—' : v }
function confColor(c) { return c === 'low' ? '#ef4444' : c === 'provisional' ? '#eab308' : '#22c55e' }
function confTitle(p) {
  const m = p.stat_matches ?? 0
  if (p.confidence === 'low') return `Only ${m} games — ratings heavily regressed to the mean (low confidence)`
  if (p.confidence === 'provisional') return `${m} games — provisional, partially regressed toward the mean`
  return `${m} games — established`
}
</script>

<template>
  <div class="prc">
    <div v-if="pending" class="muted pad">Loading cards…</div>
    <div v-else-if="err" class="err pad">{{ err }}</div>
    <template v-else>
      <p class="sub">
        8 Tier-A attributes · each a 0–99 percentile within the rated 1on1 population
        (<strong>{{ data.population }}</strong> players). Click a name for the card.
      </p>

      <section v-for="sec in data.sections" :key="sec.key" class="sec">
        <h3 class="sec-h">{{ sec.label }} <span class="cnt">{{ sec.players.length }}</span></h3>
        <div v-if="!sec.players.length" class="muted small pad">No players in this bucket.</div>
        <div v-else class="tbl-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th class="num sortable" @click="setSort('rank')">#</th>
                <th class="lcell">Player</th>
                <th class="num" title="Games played (1on1). Few games → ratings regress to the mean.">GP</th>
                <th class="num sortable" :class="{ on: sortKey === 'ovr' }" @click="setSort('ovr')">OVR</th>
                <th v-for="a in attrs" :key="a.key" class="num sortable" :class="{ on: sortKey === a.key }"
                    :title="a.pillar" @click="setSort(a.key)">{{ a.label.slice(0, 4) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in sortedPlayers(sec.players)" :key="p.canonical_id">
                <td class="num dim">{{ p.rank }}</td>
                <td class="lcell">
                  <button class="namebtn" @click="selected = p">{{ p.display }}</button>
                  <span v-if="p.confidence && p.confidence !== 'established'" class="conf"
                        :style="{ color: confColor(p.confidence) }" :title="confTitle(p)">●</span>
                  <span v-if="p.tier" class="tierpill" :style="{ color: p.tier.color, borderColor: p.tier.color }">{{ p.tier.name }}</span>
                </td>
                <td class="num dim" :title="confTitle(p)">{{ p.stat_matches ?? '—' }}</td>
                <td class="num ovr" :style="{ color: ratingColor(p.ovr) }">{{ ovrText(p.ovr) }}</td>
                <td v-for="a in attrs" :key="a.key" class="num rt"
                    :style="{ color: ratingColor(attrVal(p, a.key)) }">{{ ovrText(attrVal(p, a.key)) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <!-- Player card modal -->
    <Teleport to="body">
      <div v-if="selected" class="modal-back" @click.self="selected = null">
        <div class="card">
          <button class="x" @click="selected = null">✕</button>
          <div class="card-top">
            <div class="portrait">
              <span class="ph">🎮</span>
              <span class="ph-l">image</span>
            </div>
            <div class="who">
              <div class="ovr-big" :style="{ color: ratingColor(selected.ovr) }">{{ ovrText(selected.ovr) }}</div>
              <div class="ovr-lbl">OVR</div>
              <h2 class="name">{{ selected.display }}</h2>
              <div class="meta">
                <span v-if="selected.tier" class="tierpill" :style="{ color: selected.tier.color, borderColor: selected.tier.color }">{{ selected.tier.name }}</span>
                <span v-if="selected.region" class="region">{{ selected.region }}</span>
                <span class="dim">#{{ selected.rank }} · {{ selected.stat_matches ?? selected.matches }} games</span>
              </div>
              <div v-if="selected.confidence && selected.confidence !== 'established'" class="conf-note"
                   :style="{ color: confColor(selected.confidence) }">
                ● {{ selected.confidence }} — few games, ratings regressed toward the mean
              </div>
            </div>
          </div>
          <div class="ratings">
            <div v-for="a in selected.attrs" :key="a.key" class="rrow">
              <span class="rname">{{ a.label }}</span>
              <span class="rpill">{{ a.pillar }}</span>
              <div class="bar"><div class="fill" :style="{ width: (a.value ?? 0) + '%', background: ratingColor(a.value) }" /></div>
              <span class="rval" :style="{ color: ratingColor(a.value) }">{{ ovrText(a.value) }}</span>
            </div>
          </div>
          <p class="foot">R1 · Tier-A attributes only. The full 6-pillar card lands as we ship R2–R3.</p>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.prc { --fg: #e8edf5; --fg-2: #9fb0c5; --fg-3: #64748b; --panel: #131a26; --panel-2: #1a2433; --border: #2b3445; --accent: #14e6c0; color: var(--fg); }
.pad { padding: 16px; } .small { font-size: 12px; } .muted { color: var(--fg-3); } .err { color: #ef4444; }
.sub { color: var(--fg-2); font-size: 13px; margin: 0 0 18px; } .sub strong { color: var(--accent); }

.sec { margin-bottom: 26px; }
.sec-h { font-size: 14px; font-weight: 800; letter-spacing: -0.01em; margin: 0 0 10px; display: flex; align-items: center; gap: 8px; }
.sec-h .cnt { font-size: 11px; color: var(--fg-3); background: var(--panel-2); border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px; font-weight: 700; }

.tbl-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; background: var(--panel); }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; padding: 9px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--fg-3); font-weight: 700; border-bottom: 1px solid var(--border); white-space: nowrap; background: var(--panel-2); }
.tbl th.num { text-align: right; } .tbl th.sortable { cursor: pointer; user-select: none; } .tbl th.sortable:hover { color: var(--fg); } .tbl th.on { color: var(--accent); }
.tbl td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.tbl tr:last-child td { border-bottom: 0; }
.tbl tr:hover td { background: rgba(20,230,192,0.03); }
.num { text-align: right; font-variant-numeric: tabular-nums; font-family: 'JetBrains Mono', monospace; }
.dim { color: var(--fg-3); } .lcell { white-space: nowrap; }
.rt { font-weight: 700; } .ovr { font-weight: 800; }
.namebtn { background: none; border: 0; color: var(--fg); font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; padding: 0; }
.namebtn:hover { color: var(--accent); text-decoration: underline; }
.conf { font-size: 9px; margin-left: 6px; vertical-align: middle; }
.conf-note { font-size: 11px; font-weight: 700; margin-top: 6px; text-transform: capitalize; }
.tierpill { display: inline-block; margin-left: 8px; font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; border: 1px solid; border-radius: 4px; padding: 1px 5px; }

/* Modal card */
.modal-back { position: fixed; inset: 0; background: rgba(2,6,14,0.72); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
.card { width: 100%; max-width: 420px; background: linear-gradient(160deg, #18222f, #0f1620); border: 1px solid var(--border); border-radius: 16px; padding: 22px; position: relative; box-shadow: 0 24px 60px rgba(0,0,0,0.5); }
.x { position: absolute; top: 12px; right: 12px; background: var(--panel-2); border: 1px solid var(--border); color: var(--fg-2); width: 28px; height: 28px; border-radius: 8px; cursor: pointer; font-size: 12px; }
.x:hover { color: var(--fg); }
.card-top { display: flex; gap: 16px; align-items: center; margin-bottom: 18px; }
.portrait { width: 92px; height: 110px; flex-shrink: 0; border-radius: 12px; border: 1px dashed var(--border); background: var(--panel-2); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; }
.portrait .ph { font-size: 30px; opacity: 0.5; } .portrait .ph-l { font-size: 9px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.08em; }
.who { min-width: 0; }
.ovr-big { font-size: 46px; font-weight: 900; line-height: 1; letter-spacing: -0.03em; }
.ovr-lbl { font-size: 10px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; margin-top: -2px; }
.name { margin: 8px 0 6px; font-size: 22px; font-weight: 800; letter-spacing: -0.02em; word-break: break-word; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 11px; color: var(--fg-2); }
.meta .region { background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; font-weight: 700; }
.ratings { display: flex; flex-direction: column; gap: 9px; }
.rrow { display: grid; grid-template-columns: 92px 78px 1fr 30px; gap: 10px; align-items: center; }
.rname { font-size: 12px; font-weight: 700; }
.rpill { font-size: 9px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.04em; text-align: right; }
.bar { height: 7px; background: var(--panel-2); border-radius: 4px; overflow: hidden; }
.bar .fill { height: 100%; border-radius: 4px; }
.rval { font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 13px; text-align: right; }
.foot { margin: 16px 0 0; font-size: 10px; color: var(--fg-3); text-align: center; }

@media (max-width: 480px) {
  .rrow { grid-template-columns: 80px 1fr 28px; }
  .rrow .rpill { display: none; }
  .card-top { flex-direction: column; text-align: center; align-items: center; }
}
</style>

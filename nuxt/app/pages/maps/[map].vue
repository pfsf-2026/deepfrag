<script setup>
// /maps/{map} — the map overview (2026-10-21, Peter: "map overview pages, that include item counts,
// locations, travel times for typical paths"): a top-down picture from the analyzer's room meshes with
// every key item and spawn, the item list with respawn times, the named spawns with how often a locked
// spawn chains, key routes to the key items (the ways actually run, fast / typical), the full travel
// table, and Peter's control notes for the map. Data: composables/mapOverview.json, mapRoutes.json,
// travelTimes.json (built from the demos; see docs/map_travel_times.md and docs/coaching_doctrine.md).
import overview from '~/composables/mapOverview.json'
import routes from '~/composables/mapRoutes.json'
import travelTimes from '~/composables/travelTimes.json'
const route = useRoute()
const map = computed(() => String(route.params.map || ''))
const MAPS = ['dm3', 'dm2', 'e1m2', 'schloss']
const ov = computed(() => overview[map.value] || null)
const rt = computed(() => routes[map.value] || [])
const tt = computed(() => travelTimes[map.value] || null)
const others = computed(() => MAPS.filter(m => m !== map.value))
useHead({ title: () => `${map.value} · map overview · DeepFrag` })
const KIND = { quad: 'Quad', pent: 'Pent', ring: 'Ring', ra: 'Red', ya: 'Yellow', ga: 'Green', mh: 'Mega', rl: 'RL', lg: 'LG', gl: 'GL', sng: 'SNG', ng: 'NG', ssg: 'SSG' }
function ttCell(c) { if (!c) return '·'; if (c.fast != null) return `${c.fast} / ${c.typical}`; if (c.est != null) return `~${Math.round(c.est)}`; return '' }
const via = w => (w.via && w.via.length ? 'via ' + w.via.join(' → ') : 'straight')
</script>

<template>
  <div class="page">
    <div class="crumbs"><NuxtLink to="/coach" class="back">← AI Coach</NuxtLink><span class="sep">·</span><span class="muted">maps:</span><NuxtLink v-for="m in MAPS" :key="m" :to="`/maps/${m}`" class="mlink" :class="{ on: m === map }">{{ m }}</NuxtLink></div>
    <div v-if="!ov" class="empty">No overview for "{{ map }}". Pick a map above.</div>
    <template v-else>
      <header class="head">
        <h1>{{ map }} <span class="long">{{ ov.name }}</span></h1>
        <p class="lede">{{ ov.control }}</p>
      </header>

      <section class="sec">
        <div class="stitle">The map</div>
        <div class="mapwrap"><img :src="`/maps/${map}.svg`" :alt="`${map} top-down with items and spawns`" class="mapimg"></div>
        <p class="dnote">Top-down from the analyzer's room meshes. Circles are items (quad green, red armor red, yellow gold, mega blue, RL orange, LG purple); diamonds are the named spawn points.</p>
      </section>

      <section class="sec">
        <div class="stitle">Items</div>
        <div class="counts"><span v-for="(n, k) in ov.counts" :key="k" class="chip">{{ n }} × {{ KIND[k] || k }}</span><span class="chip muted">ammo: {{ ov.ammo.rockets }} rockets · {{ ov.ammo.cells }} cells · {{ ov.ammo.nails }} nails · {{ ov.ammo.shells }} shells · {{ ov.ammo.h25 + ov.ammo.h15 }} small health</span></div>
        <div class="tblwrap"><table class="tbl">
          <thead><tr><th>Item</th><th>Room</th><th>Respawn</th></tr></thead>
          <tbody><tr v-for="(i, idx) in ov.items" :key="idx"><td><b>{{ i.name }}</b></td><td>{{ i.room }}</td><td class="muted">{{ i.respawn }}</td></tr></tbody>
        </table></div>
        <p class="dnote">{{ ov.reds }}; {{ ov.megas }}. Quad is entered by {{ ov.quad_entries }}.</p>
      </section>

      <section class="sec">
        <div class="stitle">Spawn points <span class="muted small">and how often a spawn under a lock chains inside 14 s</span></div>
        <div class="spawns"><span v-for="s in ov.spawns" :key="s.name" class="chip"><b>{{ s.name }}</b><template v-if="s.chained_locked != null"> · {{ Math.round(s.chained_locked * 100) }}%</template></span></div>
        <p class="dnote">The names are the ones players use (confirmed by Peter). The percentage is from 60 one-second games: the share of spawns there, with the team locked, that ended inside 14 s. Which way to go off a spawn is an item-timer decision, not a fixed room; the Game Report shows the clock for every moment.</p>
      </section>

      <section v-if="rt.length" class="sec">
        <div class="stitle">Key routes <span class="muted small">the ways actually run, fast / typical seconds</span></div>
        <div v-for="dest in rt" :key="dest.to" class="dest">
          <div class="dhead">To <b>{{ dest.to_name }}</b></div>
          <div class="tblwrap"><table class="tbl">
            <thead><tr><th>from</th><th>way</th><th>fast</th><th>typical</th><th>runs</th></tr></thead>
            <tbody>
              <template v-for="f in dest.from" :key="f.from">
                <tr v-for="(w, wi) in f.ways" :key="wi"><td :class="{ muted: wi > 0 }">{{ wi === 0 ? f.from_name : '' }}</td><td class="way">{{ via(w) }}</td><td><b>{{ w.fast }}</b></td><td>{{ w.typical }}</td><td class="muted">{{ w.n }}</td></tr>
              </template>
            </tbody>
          </table></div>
        </div>
        <p class="dnote">Fast is the 10th percentile of the runs that took that way (25th when under 15 runs), typical the median. Enemies on the way only slow you down: pick the way that is clear, and count the item against the fast number.</p>
      </section>

      <section v-if="tt" class="sec">
        <div class="stitle">Travel times between key rooms <span class="muted small">fast / typical</span></div>
        <div class="tblwrap"><table class="tbl tt">
          <thead><tr><th>from \ to</th><th v-for="r in tt.rooms" :key="r">{{ r }}</th></tr></thead>
          <tbody><tr v-for="(row, i) in tt.cells" :key="i"><th>{{ tt.rooms[i] }}</th><td v-for="(c, j) in row" :key="j" :class="{ est: c && c.est != null, self: !c }">{{ ttCell(c) }}</td></tr></tbody>
        </table></div>
      </section>

      <section class="sec">
        <div class="stitle">Getting out of a lock</div>
        <p class="body">{{ ov.breaks }}</p>
      </section>

      <div class="more"><NuxtLink :to="`/coach/quad/${map}`" class="mlink">quad playbook for {{ map }}</NuxtLink><span class="muted small">other maps:</span> <NuxtLink v-for="m in others" :key="m" :to="`/maps/${m}`" class="mlink">{{ m }}</NuxtLink></div>
      <p class="foot muted small">Items and geometry from the demos and the analyzer's map data; travel and route times from 64 recent NA fours; spawn names and the control notes from Peter (docs/coaching_doctrine.md).</p>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; padding: 20px 16px 90px; display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.crumbs { display: flex; gap: 8px; align-items: baseline; font-size: 13px; flex-wrap: wrap; }
.back { color: var(--fg-2); text-decoration: none; font-weight: 600; } .back:hover { color: var(--accent); }
.sep { color: var(--fg-3); }
.mlink { color: var(--fg-2); text-decoration: none; font-weight: 700; padding: 4px 8px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--border); }
.mlink.on, .mlink:hover { color: var(--accent); border-color: var(--accent); }
.head { display: flex; flex-direction: column; gap: 8px; }
h1 { font-size: clamp(28px, 6vw, 40px); font-weight: 900; margin: 0; letter-spacing: -0.01em; line-height: 1.05; }
.long { font-size: 0.5em; color: var(--fg-2); font-weight: 600; margin-left: 8px; }
.lede, .body { margin: 0; font-size: 15px; line-height: 1.6; color: var(--fg-2); max-width: 75ch; }
.sec { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.stitle { font-weight: 800; font-size: 15px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.muted { color: var(--fg-2); } .small { font-size: 12px; }
.mapwrap { background: #0d0a07; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.mapimg { display: block; width: 100%; height: auto; }
.counts, .spawns { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: 13px; border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px; background: var(--panel); }
.tblwrap { overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--border); border-radius: 10px; background: var(--panel); }
.tbl { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
.tbl th, .tbl td { padding: 6px 9px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
.tbl thead th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--fg-2); }
.tbl td.way { white-space: normal; overflow-wrap: anywhere; color: var(--fg-2); }
.tbl.tt { min-width: 720px; font-size: 12px; } .tbl.tt th, .tbl.tt td { text-align: right; } .tbl.tt tbody th { text-align: left; position: sticky; left: 0; background: var(--panel); }
.tbl.tt td.est { color: var(--fg-3); font-style: italic; } .tbl.tt td.self { color: var(--fg-3); }
.dest { display: flex; flex-direction: column; gap: 6px; }
.dhead { font-weight: 700; font-size: 14px; }
.dnote { margin: 0; font-size: 12px; color: var(--fg-2); line-height: 1.5; }
.more { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.foot { margin: 0; line-height: 1.5; }
.empty { padding: 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); }
@media (min-width: 720px) { .page { padding: 24px 32px 100px; } }
</style>

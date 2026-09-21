<script setup>
// One map's own coach tab (2026-09-21, Peter: "each map has its own tab", then "make it
// clear what each thing IS"). Reads the per-map card from the shared 4on4 report. The
// work-on card leads with the ask in words (glossary headline), says what the stat is in
// plain English, shows only YOU vs TARGET with a bar, and links every stat to /glossary.
// The mode dropdown switches 4on4 / 1on1; 1on1 per-map coaching is not built yet.
const props = defineProps({ cid: { type: String, required: true }, map: { type: String, required: true }, mode: { type: String, default: '4on4' } })
const emit = defineEmits(['mode'])
const { report, loading, err, level, mapCard } = useFoursCoach(toRef(props, 'cid'))
const card = computed(() => mapCard(props.map))
const lvl = computed(() => level.value || null)
const levelColor = computed(() => LEVEL_COLORS[lvl.value?.level] || 'var(--fg-3)')
const nextLevel = computed(() => Math.min((lvl.value?.level || 1) + 1, 5))
// the top lever carries the raw numbers the work-on card needs for its bar
const top = computed(() => card.value?.levers?.[0] || null)
const rest = computed(() => (card.value?.levers || []).slice(1))
const chips = computed(() => invChips(card.value?.items))
const g = computed(() => gloss(card.value?.work_on?.key))
const pct = computed(() => progressPct(top.value?.you_raw, top.value?.target_raw, top.value?.higher_better !== false))
const QUAD_KEYS = new Set(['quad_pg', 'quad_contests_pg', 'quad_conversion', 'quad_died_pct', 'quad_frags_per_full', 'quad_contest_died_pg'])
const MAP_BLURB = {
  dm3: 'One red on a 20-second cycle in the LG room. Whoever owns that room owns dm3.',
  dm2: 'Two reds, three yellows, quad in the water room. The stack map: nobody should fight naked here.',
  e1m2: 'No red. One yellow, one green, a quad next to the GL room. Armor discipline and the quad decide it.',
  schloss: 'One red in the cellar, quad seconds away from it. The red count is the story of your night here.',
}
</script>

<template>
  <div class="cm">
    <div class="mhead">
      <div class="mtitle">
        <span class="mname">{{ map }}</span>
        <label class="modesel">
          <span class="sr">Mode</span>
          <select :value="mode" @change="emit('mode', $event.target.value)">
            <option value="4on4">4on4</option>
            <option value="1on1">1on1</option>
          </select>
        </label>
      </div>
      <div class="chips"><span v-for="c in chips" :key="c" class="chip">{{ c }}</span></div>
      <p class="blurb">{{ MAP_BLURB[map] }} <NuxtLink :to="`/coach/quad/${map}`" class="qpb">Quad playbook for {{ map }} →</NuxtLink></p>
    </div>

    <!-- 1on1 per-map coaching: not built yet -->
    <div v-if="mode === '1on1'" class="card soon">
      <div class="stitle">1on1 coaching for {{ map }} is next</div>
      <p>The duel side of the coach reads your last 15 rated demos and does not split by map yet. Until it does, use the 1on1 coach on the <NuxtLink :to="{ query: { mode: '1on1' } }">Overview tab</NuxtLink>. Map-by-map duel advice will land here.</p>
    </div>

    <template v-else>
      <div v-if="loading && !report" class="loadbox">Reading your last 40 fours… The first look each day also writes your coach's read, which takes about 15 seconds.</div>
      <div v-else-if="err" class="empty err">{{ err }}</div>
      <div v-else-if="report && !lvl?.placed" class="empty">A level needs 15 scored fours. Play a few more pickup nights and the map coach opens up.</div>
      <div v-else-if="card && card.thin" class="empty">
        <strong>{{ card.games }} of {{ card.min_games }}</strong> fours on {{ map }} in your last 40. The map coach needs {{ card.min_games }} games here to say something you can trust.
      </div>

      <template v-else-if="card">
        <!-- record strip -->
        <div class="rec" :style="{ '--lc': levelColor }">
          <div class="ri"><span class="n">{{ card.wins }}–{{ card.losses }}</span><span class="l">wins–losses, your last {{ card.games }} here</span></div>
          <div class="ri"><span class="n" :class="card.above_avg_pg > 0 ? 'pos' : 'neg'">{{ signed(card.above_avg_pg) }}</span><span class="l">frags a game vs an average player in your spot <NuxtLink :to="glossHref('above_avg')" class="q">?</NuxtLink></span></div>
          <div class="ri"><span class="n lv">L{{ card.plays_like || lvl.level }}</span><span class="l">{{ card.plays_like && card.plays_like !== lvl.level ? `here you play like L${card.plays_like} (you are L${lvl.level} overall)` : 'here you play like your level' }} <NuxtLink :to="glossHref('plays_like')" class="q">?</NuxtLink></span></div>
          <div class="ri"><span class="n small">{{ card.per_map_baseline ? 'map' : 'pooled' }}</span><span class="l">{{ card.per_map_baseline ? 'targets from players who play this map' : 'not enough players here yet; targets from all maps' }} <NuxtLink :to="glossHref('map_baseline')" class="q">?</NuxtLink></span></div>
        </div>

        <!-- the one thing on this map -->
        <section v-if="card.work_on" class="sec">
          <div class="sectitle">🎯 Work on this on {{ map }}</div>
          <div class="card focus">
            <div class="fhead">
              <h3 class="fheadline">{{ g?.headline || card.work_on.label }}</h3>
              <div class="fstat"><span class="statname">{{ card.work_on.label }}</span><span v-if="card.work_on.is_gate" class="gtag">gate to L{{ nextLevel }}</span><NuxtLink :to="glossHref(card.work_on.key)" class="what">what is this? →</NuxtLink></div>
            </div>
            <p v-if="g?.plain" class="plain" v-html="linkTerms(g.plain)" />
            <div class="cmp">
              <div class="item you"><span class="n">{{ card.work_on.you }}</span>you, on {{ map }}</div>
              <div class="item tgt"><span class="n">{{ card.work_on.target }}</span>target to play like L{{ nextLevel }}</div>
            </div>
            <div v-if="pct != null" class="bar" :title="`${pct}% of the way to the target`"><i :style="{ width: pct + '%' }" /><span class="barlbl">{{ pct >= 100 ? 'at the target' : pct + '% of the way there' }}</span></div>
            <div class="more muted small">Players at your level do <b>{{ card.work_on.level_median }}</b> here<template v-if="card.work_on.win && card.work_on.loss"> · you do <b>{{ card.work_on.win }}</b> in your wins and <b>{{ card.work_on.loss }}</b> in your losses</template>.</div>
            <p class="why"><b>Why on {{ map }}:</b> <span v-html="linkTerms(card.work_on.map_note || card.work_on.why)" /></p>
            <p class="drill"><b>Do this:</b> <span v-html="linkTerms(card.work_on.drill)" /></p>
            <NuxtLink v-if="QUAD_KEYS.has(card.work_on.key)" :to="`/coach/quad/${map}`" class="qbtn">Open the {{ map }} quad page: the ways in, which converts, how early →</NuxtLink>
          </div>
        </section>

        <!-- the rest of the syllabus here -->
        <section v-if="rest.length" class="sec">
          <div class="sectitle">📐 After that, on {{ map }}</div>
          <div class="rows">
            <div v-for="l in rest" :key="l.key" class="row">
              <div class="rl">
                <span class="rhead">{{ gloss(l.key)?.headline || l.label }}</span>
                <span class="rlabel muted small">{{ l.label }}<span v-if="l.is_gate" class="gtag">gate</span></span>
              </div>
              <div class="rn">you <b>{{ l.you }}</b> · target <b class="acc">{{ l.target }}</b> <span class="muted">· your level does {{ l.level_median }}</span> <NuxtLink :to="glossHref(l.key)" class="q">?</NuxtLink></div>
              <p v-if="l.map_note || gloss(l.key)?.plain" class="rnote" v-html="linkTerms(l.map_note || gloss(l.key)?.plain)" />
            </div>
          </div>
        </section>

        <!-- last games here -->
        <section v-if="card.games_cards?.length" class="sec">
          <div class="sectitle">🎮 Your last games on {{ map }}</div>
          <div class="gcards">
            <div v-for="gm in card.games_cards" :key="gm.hub_game_id" class="gcard" :class="{ w: gm.win, l: !gm.win }">
              <div class="ghead"><span class="gres">{{ gm.win ? 'Win' : 'Loss' }}</span><span class="muted small">{{ fmtCoachDate(gm.played_at) }} · {{ gm.frags }} frags / {{ gm.deaths }} deaths</span></div>
              <div class="gscore"><b>{{ signed(gm.above_avg) }}</b> above average <span class="muted">· impact {{ gm.agi }}</span></div>
              <div class="gex"><span v-for="e in gm.explain" :key="e.key" class="ex" :class="{ good: e.good, bad: !e.good }">{{ e.good ? '▲' : '▼' }} {{ e.label }} {{ e.value }}</span></div>
            </div>
          </div>
          <div class="muted small">The two chips on each game are the stats that stood out most from your usual, up or down.</div>
        </section>
        <div class="muted small">Targets are {{ map }}'s promotion line when enough players have a baseline here, else the pooled line. Item levers are shares of what the whole game took. <NuxtLink to="/glossary">every stat explained →</NuxtLink></div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.cm { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.mhead { display: flex; flex-direction: column; gap: 8px; }
.mtitle { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.mname { font-size: 28px; font-weight: 900; letter-spacing: -0.01em; line-height: 1; }
.modesel select { background: var(--panel); border: 1px solid var(--border-2); color: var(--fg); border-radius: 8px; padding: 7px 10px; font-size: 13px; font-weight: 700; font-family: inherit; min-height: 36px; }
.modesel select:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--fg-2); background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 2px 7px; }
.blurb { margin: 0; font-size: 14px; color: var(--fg-2); line-height: 1.5; max-width: 70ch; }
.qpb { color: var(--accent); font-weight: 700; text-decoration: none; white-space: nowrap; }
.loadbox, .empty { padding: 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; color: var(--fg-2); font-size: 14px; line-height: 1.5; }
.empty.err { color: #fca5a5; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.soon { border-style: dashed; } .soon p { margin: 6px 0 0; font-size: 14px; line-height: 1.55; color: var(--fg-2); }
.soon a { color: var(--accent); }
.stitle { font-weight: 800; font-size: 15px; }
.q { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--border-2); color: var(--fg-3); font-size: 11px; font-weight: 700; text-decoration: none; vertical-align: middle; margin-left: 2px; }
.q:hover { color: var(--accent); border-color: var(--accent); }
:deep(a.term) { color: inherit; text-decoration: underline dotted var(--accent); text-underline-offset: 3px; }
:deep(a.term:hover) { color: var(--accent); }
.rec { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--lc); border-radius: 12px; padding: 12px 14px; }
.ri { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ri .n { font-size: 20px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1.1; }
.ri .n.small { font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--fg-2); padding-top: 4px; }
.ri .n.lv { color: var(--lc); }
.ri .l { font-size: 11px; color: var(--fg-3); line-height: 1.35; }
.pos { color: #34d67a; } .neg { color: #ff5d6c; }
.sec { display: flex; flex-direction: column; gap: 8px; }
.sectitle { font-weight: 800; font-size: 14px; letter-spacing: 0.02em; }
.focus { border-color: var(--accent); }
.fhead { display: flex; flex-direction: column; gap: 4px; }
.fheadline { margin: 0; font-size: 24px; font-weight: 900; line-height: 1.1; letter-spacing: -0.01em; text-wrap: balance; }
.fstat { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: baseline; font-size: 13px; color: var(--fg-2); }
.statname { font-weight: 700; color: var(--fg); }
.what { color: var(--accent); font-weight: 700; text-decoration: none; }
.gtag { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }
.plain { margin: 8px 0 0; font-size: 14px; line-height: 1.55; color: var(--fg-2); max-width: 70ch; }
.cmp { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 12px 0 8px; }
.item { background: var(--panel-2); border-radius: 10px; padding: 10px 12px; font-size: 12px; color: var(--fg-2); display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.item .n { font-size: 26px; font-weight: 900; color: var(--fg); font-variant-numeric: tabular-nums; line-height: 1.1; }
.item.tgt .n { color: var(--accent); }
.bar { position: relative; height: 10px; background: var(--panel-3); border-radius: 999px; overflow: hidden; margin: 2px 0 6px; }
.bar i { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
.barlbl { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.more { line-height: 1.5; }
.why, .drill { margin: 8px 0 0; font-size: 14px; line-height: 1.5; }
.qbtn { display: inline-flex; align-items: center; margin-top: 12px; min-height: 40px; padding: 8px 14px; border-radius: 9px; background: var(--accent); color: #140a03; font-weight: 800; font-size: 13px; text-decoration: none; }
.qbtn:hover { filter: brightness(1.08); }
.drill { color: var(--fg); }
.rows { display: flex; flex-direction: column; gap: 8px; }
.row { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px 12px; }
.rl { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.rhead { font-weight: 800; font-size: 15px; }
.rlabel .gtag { margin-left: 6px; }
.rn { font-size: 13px; font-variant-numeric: tabular-nums; color: var(--fg-2); }
.rn .acc { color: var(--accent); }
.rnote { margin: 0; font-size: 13px; line-height: 1.5; color: var(--fg-2); grid-column: 1 / -1; max-width: 75ch; }
.muted { color: var(--fg-3); } .small { font-size: 12px; }
.gcards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 210px), 1fr)); gap: 10px; }
.gcard { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.gcard.w { border-top: 3px solid #34d67a; } .gcard.l { border-top: 3px solid #ff5d6c; }
.ghead { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.gres { font-weight: 800; font-size: 13px; }
.gcard.w .gres { color: #34d67a; } .gcard.l .gres { color: #ff5d6c; }
.gscore { font-size: 13px; font-variant-numeric: tabular-nums; }
.gex { display: flex; flex-wrap: wrap; gap: 4px; }
.ex { font-size: 11px; border-radius: 6px; padding: 2px 7px; background: var(--panel-2); }
.ex.good { color: #34d67a; } .ex.bad { color: #ff5d6c; }
@media (min-width: 640px) {
  .rec { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .cmp { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 520px; }
  .row { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
  .fheadline { font-size: 28px; }
}
</style>

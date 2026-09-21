<script setup>
// /glossary — every number on DeepFrag explained in plain English, in Quake terms
// (2026-09-21, Peter). Content lives in composables/useGlossary.ts so the coach pages
// link straight to an entry (/glossary#quad_pg). Live level medians for the coached
// levers come from /api/coaching/fours/levels so "what good looks like" has real numbers.
const q = ref('')
const pool = ref(null)     // { levels: {1: {n, median{}}, ...}, levers: {key: {fmt, ...}} }
onMounted(async () => {
  try {
    const r = await fetch('/api/coaching/fours/levels')
    if (r.ok) { const d = await r.json(); pool.value = { levels: d.pool?.levels || {}, levers: d.levers || {} } }
  } catch { /* the words stand without the numbers */ }
  // deep link: scroll the entry into view once the page is up
  if (location.hash) nextTick(() => document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: 'start' }))
})
function fmt(v, kind) {
  if (v == null) return '—'
  if (kind === 'pct') return Math.round(v * 100) + '%'
  if (kind === 'num0') return Math.round(v).toString()
  if (kind === 'num1') return Number(v).toFixed(1)
  return Number(v).toFixed(2)
}
// "L1 0.7 · L2 1.9 · …" for a coached lever, when the pool has it
function medians(key) {
  const lv = pool.value?.levers?.[key]
  if (!lv) return []
  return [1, 2, 3, 4, 5].map(n => ({ n, v: pool.value.levels?.[n]?.median?.[key] })).filter(x => x.v != null).map(x => ({ n: x.n, s: fmt(x.v, lv.fmt) }))
}
const needle = computed(() => q.value.trim().toLowerCase())
function hit(e) {
  if (!needle.value) return true
  return [e.name, e.headline, e.plain, e.count, e.good, e.move].filter(Boolean).join(' ').toLowerCase().includes(needle.value)
}
const groups = computed(() => GLOSS_GROUPS.map(g => ({ ...g, entries: GLOSSARY.filter(e => e.group === g.key && hit(e)) })).filter(g => g.entries.length))
useSeoMeta({ title: 'What the numbers mean · DeepFrag', description: 'Every DeepFrag stat explained in plain English, in Quake terms: frags, stack, reds, quad, the coach levels and targets.' })
</script>

<template>
  <div class="page">
    <NuxtLink to="/coach" class="back">← AI Coach</NuxtLink>
    <h1>What the numbers mean</h1>
    <p class="intro">Every stat on DeepFrag, in plain words. No formulas unless you want them. If a word on your coach page confused you, it is on this page.</p>

    <div class="legend">
      <div class="lg"><b>you</b><span>your last 40 fours</span></div>
      <div class="lg"><b>target</b><span>the promotion line: what a player just moving up to the next level does</span></div>
      <div class="lg"><b>L3 does</b><span>the middle player at your level</span></div>
    </div>

    <label class="search">
      <span class="sr">Search the glossary</span>
      <input v-model="q" type="search" placeholder="Search a stat… (quad, red, stack, deaths)" autocomplete="off" spellcheck="false">
    </label>

    <nav v-if="!needle" class="toc">
      <a v-for="g in GLOSS_GROUPS" :key="g.key" :href="'#' + g.key">{{ g.title.replace(/:.*$/, '') }}</a>
    </nav>

    <section v-for="g in groups" :id="g.key" :key="g.key" class="grp">
      <h2>{{ g.title }}</h2>
      <p class="gblurb">{{ g.blurb }}</p>
      <article v-for="e in g.entries" :id="e.key" :key="e.key" class="entry">
        <div class="ehead">
          <h3>{{ e.name }}</h3>
          <span v-if="e.headline" class="says">coach says: {{ e.headline }}</span>
          <a :href="'#' + e.key" class="anchor" title="link to this entry">#</a>
        </div>
        <p class="plain" v-html="linkTerms(e.plain, e.key)" />
        <dl v-if="e.count || e.good || e.move || medians(e.key).length" class="rows">
          <template v-if="e.count"><dt>How we count it</dt><dd v-html="linkTerms(e.count, e.key)" /></template>
          <template v-if="e.good"><dt>What good looks like</dt><dd v-html="linkTerms(e.good, e.key)" /></template>
          <template v-if="medians(e.key).length"><dt>By level right now</dt><dd class="meds"><span v-for="m in medians(e.key)" :key="m.n" class="med"><i>L{{ m.n }}</i>{{ m.s }}</span></dd></template>
          <template v-if="e.move"><dt>How to move it</dt><dd v-html="linkTerms(e.move, e.key)" /></template>
          <template v-if="e.links?.length"><dt>Go deeper</dt><dd class="elinks"><NuxtLink v-for="[l, h] in e.links" :key="h" :to="h" class="elink">{{ l }} →</NuxtLink></dd></template>
        </dl>
      </article>
    </section>
    <p v-if="!groups.length" class="none">Nothing matches "{{ q }}". Try a shorter word.</p>

    <p class="foot">Numbers by level come from the current pool of active players (15 or more fours in the last year). <NuxtLink to="/levels">How the levels work →</NuxtLink></p>
  </div>
</template>

<style scoped>
.page { max-width: 820px; margin: 0 auto; padding: 20px 16px 90px; }
.back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; }
.back:hover { color: var(--accent); }
h1 { font-size: clamp(26px, 6vw, 36px); font-weight: 900; margin: 10px 0 8px; letter-spacing: -0.01em; text-wrap: balance; }
.intro { color: var(--fg-2); font-size: 15px; line-height: 1.6; max-width: 65ch; margin: 0 0 16px; }
.legend { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 12px; padding: 12px 14px; margin-bottom: 16px; }
.lg { display: grid; grid-template-columns: 74px minmax(0, 1fr); gap: 10px; font-size: 13px; color: var(--fg-2); line-height: 1.45; align-items: baseline; }
.lg b { color: var(--accent); font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.search { display: block; margin-bottom: 14px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.search input { width: 100%; box-sizing: border-box; background: var(--panel); border: 1px solid var(--border-2); color: var(--fg); border-radius: 10px; padding: 12px 14px; font-size: 16px; font-family: inherit; min-height: 44px; }
.search input:focus { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
.toc { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 22px; }
.toc a { font-size: 12px; font-weight: 700; color: var(--fg-2); background: var(--panel-2); border: 1px solid var(--border); border-radius: 999px; padding: 7px 11px; text-decoration: none; min-height: 32px; display: inline-flex; align-items: center; }
.toc a:hover { color: var(--accent); border-color: var(--accent); }
.grp { margin-bottom: 30px; scroll-margin-top: 80px; }
h2 { font-size: 20px; font-weight: 800; margin: 0 0 4px; letter-spacing: -0.01em; }
.gblurb { margin: 0 0 12px; color: var(--fg-3); font-size: 13px; line-height: 1.5; }
.entry { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; scroll-margin-top: 80px; }
.entry:target { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
.ehead { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: baseline; }
h3 { font-size: 16px; font-weight: 800; margin: 0; }
.says { font-size: 12px; color: var(--accent); font-weight: 700; }
.anchor { margin-left: auto; color: var(--fg-3); text-decoration: none; font-size: 13px; }
.anchor:hover { color: var(--accent); }
.plain { margin: 6px 0 0; font-size: 15px; line-height: 1.6; color: var(--fg); max-width: 70ch; }
.rows { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px 14px; margin: 10px 0 0; font-size: 13.5px; line-height: 1.55; }
.rows dt { color: var(--fg-3); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; font-weight: 700; padding-top: 6px; }
.rows dd { margin: 0; color: var(--fg-2); max-width: 70ch; }
.meds { display: flex; flex-wrap: wrap; gap: 6px; }
.elinks { display: flex; flex-wrap: wrap; gap: 6px; }
.elink { font-size: 12px; font-weight: 700; color: var(--accent); background: var(--panel-2); border: 1px solid var(--border); border-radius: 999px; padding: 6px 11px; text-decoration: none; min-height: 32px; display: inline-flex; align-items: center; }
.elink:hover { border-color: var(--accent); }
.med { font-family: 'JetBrains Mono', monospace; font-size: 12px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 3px 8px; color: var(--fg); font-variant-numeric: tabular-nums; }
.med i { font-style: normal; color: var(--fg-3); margin-right: 6px; }
.none { color: var(--fg-2); }
:deep(a.term) { color: inherit; text-decoration: underline dotted var(--accent); text-underline-offset: 3px; }
:deep(a.term:hover) { color: var(--accent); }
.foot { margin-top: 24px; color: var(--fg-3); font-size: 13px; line-height: 1.5; }
.foot a { color: var(--accent); }
@media (min-width: 720px) {
  .page { padding: 32px 32px 100px; }
  .legend { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .lg { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .rows { grid-template-columns: 150px minmax(0, 1fr); }
  .rows dt { padding-top: 2px; }
}
</style>

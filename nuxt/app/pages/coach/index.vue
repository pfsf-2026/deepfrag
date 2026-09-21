<script setup>
// /coach — the top-nav entry to the AI coach (2026-09-21, Peter: "promote it to the
// top line"). A signed-in player with a linked profile goes straight to their own
// coach; everyone else gets the pitch, the five levels, a Discord sign-in and a
// player search that opens any player's coach. Prerendered shell; hydrates client-side.
const { user, ready, loggedIn, login } = useAuth()
watch([ready, () => user.value?.canonical_id], ([r, cid]) => {
  if (r && cid) navigateTo(`/p/${encodeURIComponent(cid)}/coach`, { replace: true })
}, { immediate: true })

const levels = ref([])
onMounted(async () => {
  try {
    const r = await fetch('/api/coaching/fours/levels')
    if (r.ok) { const d = await r.json(); levels.value = Array.isArray(d.levels) ? d.levels : [] }
  } catch { /* the page stands without them */ }
})

const q = ref('')
const hits = ref([])
let timer = null
watch(q, v => {
  clearTimeout(timer)
  const s = (v || '').trim()
  if (s.length < 2) { hits.value = []; return }
  timer = setTimeout(async () => {
    try { const r = await $fetch('/api/search', { params: { q: s, limit: 10 } }); hits.value = r.results || [] } catch { hits.value = [] }
  }, 200)
})
const enc = s => encodeURIComponent(s)
const STEPS = [
  ['A level from your last 40 fours', 'Above-average per game — your impact once your teammates and opponents are accounted for — places you in one of five levels, L1 Survive to L5 Carry.'],
  ['One thing to work on', 'The coach picks the single lever that separates you from the promotion line and holds it for ten games before grading it. Not a list. One thing.'],
  ['A coach for every map', 'dm3, dm2, e1m2 and schloss each get their own tab: your record there, what to work on there, and your last games on it.'],
]
useSeoMeta({ title: 'Coach · DeepFrag', description: 'Your 4on4 coach: a level from your last 40 fours, one thing to work on, and a coach for every map.' })
</script>

<template>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">DeepFrag coach</div>
      <h1>Your 4on4 coach.</h1>
      <p class="lede">A level from your last 40 fours, one thing to work on at a time, and a coach for every map. Read from the demos, not the scoreboard.</p>
      <div class="cta">
        <button v-if="ready && !loggedIn" class="btn" @click="login">Sign in with Discord</button>
        <p v-else-if="ready && loggedIn && !user?.canonical_id" class="note">You are signed in, but no player is linked to your account yet. Open your player page and claim it, then come back here.</p>
        <p v-else-if="!ready" class="note">Checking your sign-in…</p>
        <NuxtLink to="/levels" class="ghost">How the levels work →</NuxtLink>
      </div>
    </section>

    <section class="find">
      <label class="lbl" for="coach-q">Or open any player's coach</label>
      <input id="coach-q" v-model="q" class="q" type="search" placeholder="Search a player…" autocomplete="off" spellcheck="false">
      <ul v-if="hits.length" class="hits">
        <li v-for="h in hits" :key="h.canonical_id">
          <NuxtLink :to="`/p/${enc(h.canonical_id)}/coach`" class="hit"><span class="hn">{{ h.display }}</span><span class="hm">{{ h.matches }} games</span></NuxtLink>
        </li>
      </ul>
    </section>

    <section class="how">
      <h2>How it works</h2>
      <ol class="steps">
        <li v-for="([t, d], i) in STEPS" :key="i"><b>{{ t }}</b><span>{{ d }}</span></li>
      </ol>
    </section>

    <section v-if="levels.length" class="lv">
      <h2>Five levels</h2>
      <div class="lgrid">
        <div v-for="l in levels" :key="l.level" class="lcard" :style="{ '--lc': LEVEL_COLORS[l.level] }">
          <span class="ln">L{{ l.level }}</span><span class="lname">{{ l.name }}</span>
          <p>{{ l.blurb }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { max-width: 880px; margin: 0 auto; padding: 24px 16px 80px; display: flex; flex-direction: column; gap: 28px; }
.hero { display: flex; flex-direction: column; gap: 10px; }
.eyebrow { font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent); font-weight: 700; }
h1 { font-size: clamp(30px, 7vw, 48px); font-weight: 900; line-height: 1.02; letter-spacing: -0.02em; margin: 0; text-wrap: balance; }
h2 { font-size: 16px; font-weight: 800; margin: 0 0 10px; }
.lede { margin: 0; font-size: 16px; line-height: 1.55; color: var(--fg-2); max-width: 60ch; }
.cta { display: flex; flex-wrap: wrap; gap: 12px 18px; align-items: center; margin-top: 6px; }
.btn { background: var(--accent); color: #140a03; border: 0; padding: 12px 18px; border-radius: 9px; font-weight: 800; font-size: 14px; cursor: pointer; min-height: 44px; font-family: inherit; }
.btn:hover { filter: brightness(1.08); }
.ghost { color: var(--accent); font-weight: 700; font-size: 14px; text-decoration: none; min-height: 44px; display: inline-flex; align-items: center; }
.note { margin: 0; font-size: 14px; color: var(--fg-2); line-height: 1.5; max-width: 60ch; }
.find { display: flex; flex-direction: column; gap: 8px; }
.lbl { font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-3); font-weight: 700; }
.q { width: 100%; box-sizing: border-box; background: var(--panel); border: 1px solid var(--border-2); color: var(--fg); border-radius: 10px; padding: 12px 14px; font-size: 16px; font-family: inherit; min-height: 44px; }
.q:focus { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
.hits { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.hit { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; background: var(--panel); border: 1px solid var(--border); border-radius: 9px; padding: 11px 14px; color: inherit; text-decoration: none; min-height: 44px; }
.hit:hover { border-color: var(--accent); }
.hn { font-weight: 700; } .hm { font-size: 12px; color: var(--fg-3); white-space: nowrap; }
.steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; counter-reset: s; }
.steps li { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; font-size: 14px; line-height: 1.5; color: var(--fg-2); counter-increment: s; }
.steps li b { color: var(--fg); font-size: 15px; }
.steps li b::before { content: counter(s) '  '; color: var(--accent); font-variant-numeric: tabular-nums; }
.lgrid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.lcard { background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--lc); border-radius: 10px; padding: 10px 14px; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 2px 12px; align-items: baseline; }
.ln { font-size: 22px; font-weight: 900; color: var(--lc); font-variant-numeric: tabular-nums; }
.lname { font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--fg-2); font-weight: 700; }
.lcard p { margin: 0; grid-column: 2; font-size: 13px; line-height: 1.5; color: var(--fg-2); }
@media (min-width: 720px) {
  .page { padding: 40px 32px 100px; }
  .steps { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>

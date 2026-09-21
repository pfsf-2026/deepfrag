<script setup>
// /coach/p/{id} — a player's coach as its own full page under the top-nav Coach entry
// (2026-09-21, Peter: "take it out of the profile sub-tabs, leave it as a full page in the
// main nav"). The body is CoachTab (Overview + one tab per map, 4on4/1on1 in the URL).
// SPA-only: served by the prerendered /coach shell via _redirects.
const route = useRoute()
const id = computed(() => String(route.params.id || ''))
const { report, level } = useFoursCoach(id)
const display = computed(() => report.value?.display || id.value)
const LEVEL_COLORS_ = LEVEL_COLORS
useHead({ title: () => `${display.value} · coach · DeepFrag` })
</script>

<template>
  <div class="page">
    <div class="head">
      <div class="crumbs"><NuxtLink to="/coach" class="back">← coach</NuxtLink><span class="sep">·</span><NuxtLink :to="`/p/${encodeURIComponent(id)}`" class="back">{{ display }}'s profile</NuxtLink></div>
      <div class="who">
        <h1>{{ display }}</h1>
        <span v-if="level?.placed" class="lvl" :style="{ '--lc': LEVEL_COLORS_[level.level] }" :title="`4on4 level · ${level.above_avg_pg > 0 ? '+' : ''}${level.above_avg_pg} above average per game over the last ${level.games} fours`">L{{ level.level }} · {{ level.name }}</span>
      </div>
    </div>
    <CoachTab :cid="id" />
  </div>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; padding: 18px 16px 90px; }
.head { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.crumbs { display: flex; gap: 8px; align-items: baseline; font-size: 13px; flex-wrap: wrap; }
.back { color: var(--fg-2); text-decoration: none; font-weight: 600; }
.back:hover { color: var(--accent); }
.sep { color: var(--fg-3); }
.who { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
h1 { font-size: clamp(24px, 5vw, 32px); font-weight: 900; margin: 0; letter-spacing: -0.01em; line-height: 1.1; }
.lvl { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--lc); border: 1px solid var(--lc); border-radius: 999px; padding: 4px 10px; }
@media (min-width: 720px) { .page { padding: 24px 32px 100px; } }
</style>

<script setup>
// /maps — the four TB4 maps; each has an overview page (items, spawns, routes, travel times, control notes)
import overview from '~/composables/mapOverview.json'
const MAPS = ['dm3', 'dm2', 'e1m2', 'schloss']
useHead({ title: 'Map overviews · DeepFrag' })
</script>
<template>
  <div class="page">
    <h1>Map overviews</h1>
    <p class="lede">Every key item and where it is, the named spawn points, the ways players actually run between rooms with fast and typical times, and how each map is taken, held and broken.</p>
    <div class="grid">
      <NuxtLink v-for="m in MAPS" :key="m" :to="`/maps/${m}`" class="card">
        <img :src="`/maps/${m}.svg`" :alt="m" class="thumb">
        <div class="cname">{{ m }} <span class="muted">{{ overview[m]?.name }}</span></div>
      </NuxtLink>
    </div>
  </div>
</template>
<style scoped>
.page { max-width: 1000px; margin: 0 auto; padding: 20px 16px 90px; display: flex; flex-direction: column; gap: 16px; }
h1 { font-size: clamp(28px, 6vw, 40px); font-weight: 900; margin: 0; }
.lede { margin: 0; color: var(--fg-2); line-height: 1.6; max-width: 70ch; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr)); gap: 12px; }
.card { display: flex; flex-direction: column; gap: 8px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 10px; text-decoration: none; color: inherit; }
.card:hover { border-color: var(--accent); }
.thumb { width: 100%; height: auto; border-radius: 8px; background: #0d0a07; }
.cname { font-weight: 800; } .muted { color: var(--fg-2); font-weight: 500; font-size: 12px; margin-left: 6px; }
@media (min-width: 720px) { .page { padding: 24px 32px 100px; } }
</style>

<script setup>
// Landing page for First-Spawn Optimization training: pick a map. Also serves as
// the prerendered SPA shell that /training/first-spawn/* falls back to (see
// public/_redirects), so direct links to /training/first-spawn/{map} return 200.
const MAPS = ['aerowalk', 'bravado', 'ztndm3', 'dm4', 'dm2', 'dm6', 'skull', 'metron', 'pocket']
useHead({ title: 'First-Spawn Optimization · DeepFrag' })
</script>

<template>
  <div class="page">
    <div class="head">
      <NuxtLink to="/rankings/maps" class="back">← Maps</NuxtLink>
      <h1>First-Spawn Optimization</h1>
      <p class="sub">
        Replay how the top-5 players on each map open from every random spawn —
        conditioned on the enemy's spawn, labeled by what they secured and how the
        opening ended. Pick a map.
      </p>
    </div>
    <div class="grid">
      <NuxtLink v-for="m in MAPS" :key="m" :to="`/training/first-spawn/${m}`" class="tile">
        <span class="name">{{ m }}</span>
        <span class="go">🎯 replay openings →</span>
      </NuxtLink>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; padding: 32px 40px 80px; }
.head { margin-bottom: 22px; }
.head .back { color: var(--fg-2); text-decoration: none; font-size: 13px; font-weight: 600; display: inline-block; margin-bottom: 8px; }
.head .back:hover { color: var(--accent); }
.head h1 { margin: 0 0 6px; font-size: 30px; font-weight: 800; letter-spacing: -0.02em; }
.head .sub { color: var(--fg-2); margin: 0; font-size: 13px; max-width: 700px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.tile { display: flex; flex-direction: column; gap: 6px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 18px; text-decoration: none; color: inherit; transition: all 0.12s; }
.tile:hover { border-color: var(--accent); transform: translateY(-2px); }
.tile .name { font-size: 19px; font-weight: 800; letter-spacing: -0.01em; }
.tile .go { color: var(--accent); font-size: 12px; font-weight: 600; }
</style>

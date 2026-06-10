<script setup>
// Shareable standalone stats page — renders the same <LadderStats> used by the
// ladder's Stats tab.
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
const ladderId = ref(null)
const ready = ref(false)
onMounted(async () => {
  try {
    const list = await $fetch(`${base}/api/ladder`, { query: { _: Date.now() } })
    ladderId.value = (list.ladders || [])[0]?.id || null
  } catch { /* ignore */ } finally { ready.value = true }
})
useHead({ title: 'KOTH Stats · DeepFrag' })
</script>

<template>
  <div class="wrap">
    <header class="head">
      <div><h1>KOTH — Stats</h1><p class="sub">Per-map averages &amp; map analytics from reported ladder matches.</p></div>
      <NuxtLink to="/ladder#stats" class="back">← Ladder</NuxtLink>
    </header>
    <ClientOnly>
      <div v-if="!ready" class="muted pad">Loading…</div>
      <div v-else-if="!ladderId" class="muted pad">No ladder yet.</div>
      <LadderStats v-else :ladder-id="ladderId" />
    </ClientOnly>
  </div>
</template>

<style scoped>
.wrap { max-width: 1080px; margin: 0 auto; padding: 28px 20px 80px; }
.head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 22px; }
h1 { font-size: 24px; font-weight: 900; margin: 0; } .sub { color: var(--fg-3); font-size: 13px; margin: 4px 0 0; }
.back { color: var(--accent); text-decoration: none; font-size: 13px; }
.muted { color: var(--fg-3); } .pad { padding: 40px 0; text-align: center; }
</style>

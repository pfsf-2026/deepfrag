<script setup>
// Old address of a player's coach (/coach/p/{id}). It lived here for an hour while the
// Cloudflare rewrite was wrong, and browsers cache a wrong 308 for a long time, so the
// page moved to /coach/player/{id}; this only forwards anyone with the old link.
const route = useRoute()
onMounted(() => { navigateTo({ path: `/coach/player/${encodeURIComponent(String(route.params.id || ''))}`, query: route.query }, { replace: true }) })
</script>
<template><div class="fwd">Opening the coach…</div></template>
<style scoped>.fwd { padding: 40px 16px; color: var(--fg-3); }</style>

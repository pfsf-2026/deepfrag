<script setup>
// /r/{hub_game_id}/{player} — public share link for one Game Report (2026-10-17, Peter: "separate
// ones that we can share with anyone else"). SPA-only; _redirects serves the coach shell for /r/*.
const route = useRoute()
const cid = computed(() => String(route.params.cid || ''))
const gid = computed(() => String(route.params.gid || ''))
</script>

<template>
  <GameReportView :cid="cid" :gid="gid" />
</template>

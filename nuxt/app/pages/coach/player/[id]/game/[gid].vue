<script setup>
// /coach/player/{id}/game/{hub_game_id} — a player's Game Report inside the coach. The same view is
// public at /r/{gid}/{id} for sharing (components/GameReportView.vue).
const route = useRoute()
const id = computed(() => String(route.params.id || ''))
const gid = computed(() => String(route.params.gid || ''))
</script>

<template>
  <GameReportView :cid="id" :gid="gid" />
</template>

<script setup>
// Per-match deep-dive: per-map scoreline + per-player KTX stats. Reused by the
// Stats tab's reports list and the Standings "Recent results" card.
const props = defineProps({ matchId: { type: [Number, String], required: true } })
const emit = defineEmits(['close'])
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const detail = ref(null)
const loading = ref(true)
function logoUrl(id) { return `${base}/api/ladder/team/${id}/logo` }
// Orient the whole modal WINNER-first (match winner's team on the left, their
// score/frags first on every map) so it reads "winner X–Y loser" consistently.
const flip = computed(() => detail.value && detail.value.winner_id != null && detail.value.winner_id === detail.value.b_id)
function wf(mp) { return flip.value ? mp.b_frags : mp.a_frags }   // winner-side frags
function lf(mp) { return flip.value ? mp.a_frags : mp.b_frags }   // loser-side frags
function mapWonByWinner(mp) { return (wf(mp) ?? 0) > (lf(mp) ?? 0) }  // did the match-winner take this map?
onMounted(async () => {
  try { detail.value = await $fetch(`${base}/api/ladder/match/${props.matchId}`) }
  catch { /* ignore */ } finally { loading.value = false }
})
</script>

<template>
  <div class="modal-bg" @click.self="emit('close')">
    <div class="modal">
      <div v-if="loading" class="muted pad">Loading match…</div>
      <div v-else-if="!detail" class="muted pad">Match not found.</div>
      <template v-else>
        <div class="md-head">
          <span class="md-team"><img v-if="flip ? detail.b_logo : detail.a_logo" :src="logoUrl(flip ? detail.b_id : detail.a_id)" class="lg" alt=""> {{ flip ? detail.b_name : detail.a_name }}</span>
          <span class="md-sc"><b class="w">{{ flip ? detail.score_b : detail.score_a }}</b> – <b>{{ flip ? detail.score_a : detail.score_b }}</b></span>
          <span class="md-team right">{{ flip ? detail.a_name : detail.b_name }} <img v-if="flip ? detail.a_logo : detail.b_logo" :src="logoUrl(flip ? detail.a_id : detail.b_id)" class="lg" alt=""></span>
          <button class="x" @click="emit('close')">✕</button>
        </div>
        <div class="md-maps">
          <span v-for="(mp, i) in detail.maps" :key="i" class="m" :class="{ w: mapWonByWinner(mp) }">{{ mp.map }} <b>{{ wf(mp) }}–{{ lf(mp) }}</b></span>
        </div>
        <div v-for="(mp, i) in detail.maps" :key="'t'+i" class="md-block">
          <div class="md-map-h">{{ mp.map }} <span class="muted small">{{ wf(mp) }}–{{ lf(mp) }}</span></div>
          <div v-if="!mp.players.length" class="muted small">No per-player stats linked.</div>
          <table v-else class="pl">
            <thead><tr><th class="l">Player</th><th>F</th><th>D</th><th>Eff</th><th>RL%</th><th>LG%</th><th>RA</th><th>Q</th><th>Dmg</th></tr></thead>
            <tbody>
              <tr v-for="p in mp.players" :key="p.canonical_id || p.name">
                <td class="l">{{ p.name }}</td><td>{{ p.frags }}</td><td>{{ p.deaths }}</td><td>{{ p.eff }}%</td>
                <td>{{ p.rl }}%</td><td>{{ p.lg }}%</td><td>{{ p.ra }}</td><td>{{ p.quad }}</td>
                <td>{{ p.dmg >= 1000 ? (p.dmg/1000).toFixed(1)+'k' : p.dmg }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.7); display: flex; align-items: center; justify-content: center; z-index: 110; padding: 20px; }
.modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 20px 22px; width: 100%; max-width: 640px; max-height: 90vh; overflow-y: auto; }
.muted { color: var(--fg-3); } .small { font-size: 12px; } .pad { padding: 30px 0; text-align: center; }
.md-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.md-team { display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 16px; flex: 1; }
.md-team.right { justify-content: flex-end; }
.lg { width: 26px; height: 26px; border-radius: 6px; object-fit: cover; }
.md-sc { font-family: 'JetBrains Mono', monospace; font-size: 21px; font-weight: 800; }
.md-sc b { color: var(--fg-3); } .md-sc b.w { color: var(--accent); }
.x { background: none; border: 0; color: var(--fg-3); font-size: 18px; cursor: pointer; }
.md-maps { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.md-maps .m { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 4px 9px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--border); }
.md-maps .m.w { border-color: var(--accent); color: var(--accent); }
.md-block { margin-bottom: 14px; }
.md-map-h { font-family: 'JetBrains Mono', monospace; font-weight: 700; margin-bottom: 6px; }
table.pl { border-collapse: collapse; width: 100%; font-size: 12px; }
table.pl th { font-size: 10px; color: var(--fg-3); text-transform: uppercase; text-align: right; padding: 5px 7px; border-bottom: 1px solid var(--border); }
table.pl th.l, table.pl td.l { text-align: left; }
table.pl td { font-family: 'JetBrains Mono', monospace; text-align: right; padding: 6px 7px; border-bottom: 1px solid rgba(43,54,80,.4); }
table.pl td.l { font-family: system-ui, sans-serif; font-weight: 700; }
</style>

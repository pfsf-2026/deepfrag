// Multi-ladder picker shared by every /ladder page (2026-09-17).
//
// /api/ladder returns every active ladder (2v2 teams, 1v1 duels, …). Pages used
// to take ladders[0]; now the current ladder is chosen by the `l` query param
// (a slug like `1v1` / `2v2`, or a numeric id), else the viewer's last choice
// (localStorage), else the first ladder. `words` carries the vocabulary the
// templates need so a duel ladder says "player" where the 2v2 says "team".
const SLUG_BY_SIZE: Record<number, string> = { 1: '1v1', 2: '2v2', 4: '4v4' }

export function ladderSlug(l: any): string {
  if (!l) return ''
  return SLUG_BY_SIZE[Number(l.team_size)] || String(l.id ?? '')
}

export function useLadders() {
  const route = useRoute()
  const router = useRouter()
  const isBrowser = typeof window !== 'undefined'
  const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
  const ladders = useState<any[]>('ladders-list', () => [])
  const current = useState<any | null>('ladders-current', () => null)

  function pick() {
    const want = String(route.query.l || '')
    let stored = ''
    try { stored = localStorage.getItem('df-ladder') || '' } catch { /* private mode etc. */ }
    const key = want || stored
    const found = ladders.value.find((l: any) => ladderSlug(l) === key || String(l.id) === key)
    current.value = found || ladders.value[0] || null
    return current.value
  }
  async function loadList(bust = true) {
    const list: any = await $fetch(`${base}/api/ladder`, { query: bust ? { _: Date.now() } : {} })
    ladders.value = list.ladders || []
    return pick()
  }
  function switchTo(l: any) {
    current.value = l
    try { localStorage.setItem('df-ladder', ladderSlug(l)) } catch { /* ignore */ }
    router.replace({ query: { ...route.query, l: ladderSlug(l) }, hash: route.hash })
  }
  const isDuel = computed(() => Number(current.value?.team_size || 2) === 1)
  const words = computed(() => isDuel.value
    ? { team: 'player', Team: 'Player', teams: 'players', Teams: 'Players', mode: '1on1', short: '1v1',
        title: 'KOTH 1v1 Ladder', join: '+ Join the ladder', settings: 'Ladder entry', unit: 'you' }
    : { team: 'team', Team: 'Team', teams: 'teams', Teams: 'Teams', mode: '2on2', short: '2v2',
        title: 'KOTH 2v2 Ladder', join: '+ Add your team', settings: 'Team settings', unit: 'your team' })
  return { ladders, current, loadList, pick, switchTo, isDuel, words, ladderSlug }
}

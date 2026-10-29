// Build a Game Report on click (2026-10-28, Peter): the first open of a game reads the demo
// (~20-40 s), so the coach's game lists start the build in place and swap the button for a
// small arrow link to the report once it exists. Shared by CoachRecentGames and the games table.
type BuildState = { busy?: boolean, err?: string }

export function useReportBuild(cid: Ref<string>) {
  const isBrowser = typeof window !== 'undefined'
  const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')
  const state = ref<Record<string, BuildState>>({})

  function reportPath(gid: string | number) {
    return `/coach/player/${encodeURIComponent(cid.value)}/game/${gid}`
  }

  // g is a recent-games row; has_report flips to true when the build lands
  async function build(g: { hub_game_id: number, has_report?: boolean, report_summary?: Record<string, any> | null }) {
    const k = String(g.hub_game_id)
    if (state.value[k]?.busy) return
    state.value = { ...state.value, [k]: { busy: true } }
    try {
      const r = await fetch(`${base}/api/players/${encodeURIComponent(cid.value)}/games/${k}/report`)
      if (!r.ok) {
        let msg = `report ${r.status}`
        try { msg = (await r.json()).detail || msg } catch { /* not json */ }
        throw new Error(msg)
      }
      const rep = await r.json()
      const rows = rep.table || []
      const i = rows.findIndex((x: any) => x.me)
      g.has_report = true
      // the same summary the games API gives a game with a current report
      if (i >= 0) {
        const me = rows[i]
        g.report_summary = { compare: rep.compare, rank: i + 1, of: rows.length, impact: me.impact, adj: me.adj, dmg_pm: me.dmg_pm, sddr: me.sddr, deaths: me.deaths, quads: me.quads, pents: me.pents, ra: me.ra, mm2: me.mm2 }
      }
      state.value = { ...state.value, [k]: {} }
    } catch (e: any) {
      state.value = { ...state.value, [k]: { err: String(e?.message || e) } }
    }
  }

  return { state, build, reportPath }
}

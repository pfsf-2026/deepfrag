/**
 * useDeepFrag — single source of truth for "where do I fetch X from?"
 *
 * When `NUXT_PUBLIC_API_BASE` is set (production: https://api.deepfrag…), the
 * helpers hit the live FastAPI backend on Cloud Run. When it's empty (legacy
 * static deploys, or initial dev), they fall back to the prerendered JSON
 * files in /public. This lets us flip every page to the API by toggling one
 * Pages env var, with no per-page code changes.
 */
export function useDeepFrag() {
  const config = useRuntimeConfig()
  // On the client we use relative /api paths so the Cloudflare Pages Function
  // (functions/api/[[path]].js) intercepts and serves from CF's edge cache.
  // On SSR/prerender there is no Function yet — fall back to the configured
  // origin URL so prerender can still bake data into the HTML shell.
  const isBrowser = typeof window !== 'undefined'
  const base = isBrowser ? '' : ((config.public.apiBase as string) || '')
  const useApi = isBrowser || !!base

  return {
    useApi,

    rankingsUrl(mode: string = '1on1', region: string = ''): string {
      // 500 covers every realistic min-matches filter the UI exposes; smaller
      // payload + CDN cache make this fast even on the first uncached hit.
      const params = new URLSearchParams({ mode, min_matches: '10', limit: '500' })
      if (region) params.set('region', region)
      return useApi ? `${base}/api/rankings?${params}` : '/rankings.json'
    },

    profileUrl(id: string): string {
      return useApi ? `${base}/api/players/${encodeURIComponent(id)}` : `/profiles/${id}.json`
    },

    mapsUrl(id: string): string {
      return useApi ? `${base}/api/players/${encodeURIComponent(id)}/maps?min_matches=5` : `/profiles/${id}.json`
    },

    indexUrl(): string {
      return useApi ? `${base}/api/players` : '/profiles/index.json'
    },

    configUrl(id: string): string | null {
      // Player hardware/config profile (sens, mouse, binds, geo). API-only.
      return useApi ? `${base}/api/players/${encodeURIComponent(id)}/config` : null
    },

    playerMapUrl(): string | null {
      return useApi ? `${base}/api/players/map` : null
    },

    mapRankingsUrl(map: string, mode: string = '1on1'): string | null {
      return useApi
        ? `${base}/api/rankings/maps/${encodeURIComponent(map)}?mode=${mode}&min_matches=5&limit=500`
        : null
    },

    mapListUrl(mode: string = '1on1'): string | null {
      return useApi ? `${base}/api/maps?mode=${mode}&min_players=5` : null
    },

    ratingHistoryUrl(id: string, mode: string = '1on1', map: string = ''): string | null {
      // No static fallback — rating history was never baked into the static JSON.
      return useApi
        ? `${base}/api/players/${encodeURIComponent(id)}/rating-history?mode=${mode}${map ? '&map=' + encodeURIComponent(map) : ''}`
        : null
    },

    mapOpponentsUrl(id: string, map: string): string | null {
      // Per-map H2H is API-only — static profile JSON never had this field.
      return useApi
        ? `${base}/api/players/${encodeURIComponent(id)}/maps/${encodeURIComponent(map)}/opponents?limit=8`
        : null
    },

    h2hUrl(p1: string, p2: string, mode: string = '1on1'): string | null {
      return useApi
        ? `${base}/api/h2h?p1=${encodeURIComponent(p1)}&p2=${encodeURIComponent(p2)}&mode=${mode}`
        : null
    }
  }
}

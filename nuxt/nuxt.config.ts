// https://nuxt.com/docs/api/configuration/nuxt-config
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

// Read the player index at build time and emit a /p/[id] prerender route per player
// so `nuxi generate` produces a static HTML shell for each profile.
function loadPrerenderRoutes(): string[] {
  const idxPath = resolve(process.cwd(), 'public/profiles/index.json')
  if (!existsSync(idxPath)) return []
  const idx = JSON.parse(readFileSync(idxPath, 'utf8'))
  // Only the main profile page gets prerendered — the deep-dive routes
  // (/p/[id]/maps, etc.) all hydrate from the same profile.json client-side
  // and don't need a per-player HTML shell. Halves the build + deploy time.
  return (idx.players || []).map((p: any) => `/p/${p.canonical_id}`)
}

export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui'
  ],

  // Runtime config exposed to the client. Default = live Cloud Run API for
  // prerender, local dev, and prod. The legacy static-JSON fallback (set
  // apiBase: '') is dead — all data lives in Postgres now and the rate.py
  // run is what updates it. NUXT_PUBLIC_API_BASE env override still works
  // if we ever need to point a deploy at a staging API.
  runtimeConfig: {
    public: {
      apiBase: 'https://deepfrag-api-751658372467.us-central1.run.app'
    }
  },

  devtools: {
    enabled: true
  },

  css: ['~/assets/css/main.css'],

  routeRules: {
    '/': { prerender: true },
    '/players': { prerender: true },
    '/p/*': { prerender: true },
    // Deep-dive sub-routes hydrate from the same JSON — leave them as SPA-only.
    '/p/*/**': { prerender: false, ssr: false },
    // Map rankings: prerender the index, leave per-map pages as SPA
    // (the _redirects file falls back to /rankings/maps for any /rankings/maps/*).
    '/rankings/maps': { prerender: true },
    '/rankings/maps/**': { prerender: false, ssr: false },
    '/servers': { prerender: true },
    '/stats': { prerender: true },
    '/h2h': { prerender: true }
  },

  nitro: {
    prerender: {
      routes: loadPrerenderRoutes(),
      // crawlLinks would otherwise follow NuxtLinks to /p/[id]/maps and
      // re-prerender them, defeating the point of dropping them above.
      crawlLinks: false
    }
  },

  compatibilityDate: '2025-01-15',

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})

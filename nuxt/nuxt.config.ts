// https://nuxt.com/docs/api/configuration/nuxt-config
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

// Read the player index at build time and emit a /p/[id] prerender route per player
// so `nuxi generate` produces a static HTML shell for each profile.
// ALWAYS emits /p/_fallback — a bare shell the _redirects rule
// (/p/* -> /p/_fallback 200) serves for any profile NOT prerendered (a new
// player, or a CI build where the index fetch failed). The shell hydrates
// client-side from the URL, so profiles never hard-404. Safety net that turns
// "prerender produced nothing" from an outage into graceful SPA mode.
// The CI build command is `npm run generate`, which fetches a fresh
// public/profiles/index.json BEFORE this runs (index.json is gitignored, so a
// plain `nuxi generate` in CI would otherwise see no players → 0 profiles).
function loadPrerenderRoutes(): string[] {
  const idxPath = resolve(process.cwd(), 'public/profiles/index.json')
  const always = ['/p/_fallback']
  if (!existsSync(idxPath)) return always
  const idx = JSON.parse(readFileSync(idxPath, 'utf8'))
  // Only the main profile page gets prerendered — the deep-dive routes
  // (/p/[id]/maps, etc.) all hydrate from the same profile.json client-side
  // and don't need a per-player HTML shell. Halves the build + deploy time.
  return [...always, ...(idx.players || []).map((p: any) => `/p/${p.canonical_id}`)]
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
    '/map': { prerender: true },
    '/p/*': { prerender: true },
    // Deep-dive sub-routes hydrate from the same JSON — leave them as SPA-only.
    '/p/*/**': { prerender: false, ssr: false },
    // Map rankings: prerender the index, leave per-map pages as SPA
    // (the _redirects file falls back to /rankings/maps for any /rankings/maps/*).
    '/rankings/maps': { prerender: true },
    '/rankings/maps/**': { prerender: false, ssr: false },
    // First-spawn training: prerender the landing/index (it's the SPA shell that
    // /training/first-spawn/* falls back to), per-map replay pages are SPA-only.
    '/training/first-spawn': { prerender: true },
    '/training/first-spawn/**': { prerender: false, ssr: false },
    '/servers': { prerender: true },
    '/stats': { prerender: true },
    '/h2h': { prerender: true },
    '/admin': { prerender: true }
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

// Prebuild step: refresh public/profiles/index.json from the live API before
// `nuxi generate` reads it to decide which /p/{id} player pages to prerender.
//
// Without this, the committed index.json is a stale snapshot and the build
// prerenders an out-of-date player set (the exact class of bug that had the
// /players page frozen). Runs as part of `npm run generate`. Network failure
// is non-fatal — we fall back to the committed file so a build never breaks
// just because the API is briefly unreachable.

import { writeFile, readFile, mkdir } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const API = process.env.NUXT_PUBLIC_API_BASE
  || 'https://deepfrag-api-751658372467.us-central1.run.app'
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../public/profiles/index.json')

try {
  const res = await fetch(`${API}/api/players`, { signal: AbortSignal.timeout(30000) })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  if (!data?.players?.length) throw new Error('empty player list')
  // public/profiles/ is gitignored, so it doesn't exist in a clean CI checkout.
  // Create it before writing — otherwise writeFile ENOENTs and the build
  // prerenders ZERO /p/{id} pages (every profile then serves the bare SPA
  // shell). This was the bug that hid the AI Coach card from the live site.
  await mkdir(dirname(OUT), { recursive: true })
  await writeFile(OUT, JSON.stringify(data))
  console.log(`[prerender-index] refreshed: ${data.count} players from ${API}`)
} catch (e) {
  // Fall back to a committed snapshot only if one exists; otherwise FAIL the
  // build loudly — shipping with no index means no prerendered profiles, which
  // is worse (and silent) than a failed build.
  let fallback = null
  try { fallback = JSON.parse(await readFile(OUT, 'utf8')) } catch {}
  if (fallback?.players?.length) {
    console.warn(`[prerender-index] refresh failed (${e.message}); using committed file (${fallback.count} players)`)
  } else {
    console.error(`[prerender-index] FATAL: refresh failed (${e.message}) and no usable committed index — profiles would not prerender.`)
    process.exit(1)
  }
}

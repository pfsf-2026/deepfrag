// Edge cache proxy for the Cloud Run API. Runs as a Cloudflare Pages Function
// at /api/* — first visitor pays origin latency, every other visitor worldwide
// hits CF edge cache instead. Public read endpoints get cached aggressively
// (sync only writes every 2h); admin + write paths bypass entirely.

const ORIGIN = 'https://deepfrag-api-751658372467.us-central1.run.app';

// Endpoints that change rarely (only when rate.py / sync runs) — cache hard.
// Patterns are tested against `url.pathname` AFTER /api stripping happens at
// Cloudflare's level; here pathname still includes /api/.
const CACHEABLE_PREFIXES = [
  '/api/rankings',           // rankings, rankings/maps/*
  '/api/players',            // index + individual profile + /full + /maps + /rating-history
  '/api/divisions/',         // div avg stats
  '/api/stats/',             // leaderboards, maps
  '/api/servers',            // server list + per-server detail
  '/api/maps',
  '/api/h2h',
  '/api/search',
  '/api/health',
];

function isCacheable(pathname, request) {
  // Never cache anything with an auth header — admin endpoints + future tokens
  if (request.headers.get('Authorization')) return false;
  // Only GET
  if (request.method !== 'GET') return false;
  // Admin paths never
  if (pathname.startsWith('/api/admin')) return false;
  return CACHEABLE_PREFIXES.some(p => pathname.startsWith(p));
}

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  const originUrl = ORIGIN + url.pathname + url.search;

  const cacheable = isCacheable(url.pathname, request);
  const cache = caches.default;
  const cacheKey = new Request(originUrl, { method: 'GET' });

  if (cacheable) {
    const cached = await cache.match(cacheKey);
    if (cached) {
      const r = new Response(cached.body, cached);
      r.headers.set('X-Cache', 'HIT');
      return r;
    }
  }

  // Forward request to Cloud Run. Copy method/headers/body verbatim.
  // redirect:'manual' is critical for the OAuth flow: the backend's
  // /api/auth/discord/login returns a 307 to discord.com. Without 'manual'
  // the Worker's fetch FOLLOWS that redirect and fetches discord.com itself
  // (returning Discord's page to the browser as a blank/200), so the browser
  // never navigates. 'manual' hands the 307 straight back to the browser.
  const originResp = await fetch(originUrl, {
    method: request.method,
    headers: request.headers,
    body: request.method === 'GET' || request.method === 'HEAD' ? null : request.body,
    redirect: 'manual',
  });

  if (!cacheable || !originResp.ok) {
    // Pass 3xx redirects (OAuth) and everything else through untouched. A
    // 'manual' redirect response is immutable, so rebuild it to be safe.
    if (originResp.status >= 300 && originResp.status < 400) {
      return new Response(null, {
        status: originResp.status,
        headers: { Location: originResp.headers.get('Location') || '' },
      });
    }
    return originResp;
  }

  // Override the origin's Cache-Control so CF caches longer than the browser.
  // s-maxage targets the edge; max-age targets the browser. Sync runs every 2h
  // so 7200s edge cache is safe; 60s browser cache keeps profile-tab clicks
  // snappy without holding stale data when the user explicitly refreshes.
  const response = new Response(originResp.body, originResp);
  response.headers.set('Cache-Control', 'public, max-age=60, s-maxage=7200, stale-while-revalidate=86400');
  response.headers.set('X-Cache', 'MISS');
  // Strip the origin's narrower cache header if present.
  response.headers.delete('Vary');

  context.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

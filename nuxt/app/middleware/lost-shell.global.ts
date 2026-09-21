// A browser that cached the wrong Cloudflare 308 (/coach/p/* -> /200, 2026-09-21) lands on
// /200 with nothing to render. Send it to the coach landing instead of a 404.
export default defineNuxtRouteMiddleware((to) => {
  if (to.path === '/200' || to.path === '/200.html') return navigateTo('/coach', { replace: true })
})

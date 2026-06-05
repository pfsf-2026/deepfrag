<script setup>
// OAuth landing: the Discord callback redirects here with ?token=<jwt>. Capture
// it, store the session, then bounce to the ladder.
// The token arrives in the URL *fragment* (#token=<jwt>), not the query string.
// Why: the callback redirect is same-zone (deepfrag.pages.dev), and Cloudflare
// Pages' path normalization (trailing-slash 308) strips query strings on that
// hop — but URL fragments are reattached client-side across redirects and never
// touch the server/normalizer, so they survive intact. (Standard OAuth
// implicit-flow convention.) Fall back to ?token= for safety.
const router = useRouter()
const { setToken, fetchMe } = useAuth()
const msg = ref('Signing you in…')

onMounted(async () => {
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
  const t = new URLSearchParams(hash).get('token')
        || new URLSearchParams(window.location.search).get('token')
  if (!t) { msg.value = 'No sign-in token — try again.'; setTimeout(() => router.replace('/'), 1500); return }
  setToken(t)
  await fetchMe()
  router.replace('/ladder')  // ladder is the destination; falls back fine if not yet built
})

useHead({ title: 'Signing in · DeepFrag' })
</script>

<template>
  <div class="auth-page">
    <div class="spinner" />
    <p>{{ msg }}</p>
  </div>
</template>

<style scoped>
.auth-page { max-width: 420px; margin: 80px auto; text-align: center; color: var(--fg-2); }
.spinner { width: 28px; height: 28px; margin: 0 auto 14px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>

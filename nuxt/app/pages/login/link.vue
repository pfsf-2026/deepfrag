<script setup>
// Sign-in link landing (2026-09-27): an admin issues /login/link#t=<token> for a player
// who won't use Discord. The token rides in the URL fragment (never sent to the server,
// survives Cloudflare's path normalisation). We exchange it for the same session JWT the
// Discord flow stores, then bounce to the ladder.
const router = useRouter()
const { setToken, fetchMe } = useAuth()
const msg = ref('Signing you in…')
const failed = ref(false)

onMounted(async () => {
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
  const t = new URLSearchParams(hash).get('t') || new URLSearchParams(window.location.search).get('t')
  if (!t) { failed.value = true; msg.value = 'This sign-in link is incomplete. Ask an admin for a new one.'; return }
  try {
    const r = await fetch('/api/auth/link', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: t }) })
    if (!r.ok) {
      let detail = 'This sign-in link didn\'t work.'
      try { detail = (await r.json()).detail || detail } catch {}
      failed.value = true; msg.value = detail; return
    }
    const d = await r.json()
    setToken(d.token)
    await fetchMe()
    history.replaceState(null, '', '/login/link')   // drop the token from the address bar / history
    msg.value = `Signed in as ${d.display}. Taking you to the ladder…`
    setTimeout(() => router.replace('/ladder?l=1v1'), 600)
  } catch {
    failed.value = true; msg.value = 'Could not reach DeepFrag. Try the link again in a moment.'
  }
})

useHead({ title: 'Sign in · DeepFrag' })
</script>

<template>
  <div class="auth-page">
    <div v-if="!failed" class="spinner" />
    <div v-else class="x">✕</div>
    <p>{{ msg }}</p>
    <p v-if="failed" class="muted">You can also <NuxtLink to="/ladder">sign in with Discord</NuxtLink>.</p>
  </div>
</template>

<style scoped>
.auth-page { max-width: 420px; margin: 80px auto; text-align: center; color: var(--fg-2); padding: 0 16px; }
.spinner { width: 28px; height: 28px; margin: 0 auto 14px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
.x { font-size: 28px; color: var(--loss); margin-bottom: 8px; }
.muted { color: var(--fg-3); font-size: 13px; }
.muted a { color: var(--accent); }
@keyframes spin { to { transform: rotate(360deg); } }
</style>

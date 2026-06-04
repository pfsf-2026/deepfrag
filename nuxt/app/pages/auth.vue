<script setup>
// OAuth landing: the Discord callback redirects here with ?token=<jwt>. Capture
// it, store the session, then bounce to the ladder.
const route = useRoute()
const router = useRouter()
const { setToken, fetchMe } = useAuth()
const msg = ref('Signing you in…')

onMounted(async () => {
  const t = route.query.token
  if (!t) { msg.value = 'No sign-in token — try again.'; setTimeout(() => router.replace('/'), 1500); return }
  setToken(String(t))
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

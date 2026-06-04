// Discord-OAuth session for the SPA. Token-based: the JWT lives in localStorage
// and is sent as `Authorization: Bearer` (the /api proxy forwards it). Login
// bounces to the backend OAuth route; the /auth page captures the returned token.
const TOKEN_KEY = 'df_token'

export function useAuth() {
  const user = useState<any>('auth-user', () => null)
  const ready = useState<boolean>('auth-ready', () => false)

  const token = () => (import.meta.client ? localStorage.getItem(TOKEN_KEY) : null)
  function setToken(t: string) { if (import.meta.client) localStorage.setItem(TOKEN_KEY, t) }
  function authHeader(): Record<string, string> {
    const t = token()
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  async function fetchMe() {
    const t = token()
    if (!t) { user.value = null; ready.value = true; return null }
    try {
      const r = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
      if (r.ok) {
        user.value = await r.json()
      } else {
        user.value = null
        if (import.meta.client) localStorage.removeItem(TOKEN_KEY) // expired/invalid
      }
    } catch {
      user.value = null
    } finally {
      ready.value = true
    }
    return user.value
  }

  function login() { if (import.meta.client) window.location.href = '/api/auth/discord/login' }
  function logout() {
    if (import.meta.client) localStorage.removeItem(TOKEN_KEY)
    user.value = null
  }

  const loggedIn = computed(() => !!user.value)
  return { user, loggedIn, ready, token, setToken, authHeader, fetchMe, login, logout }
}

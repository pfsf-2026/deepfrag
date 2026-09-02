<script setup>
const { user, loggedIn, ready, fetchMe, login, logout } = useAuth()

// Canonical home is app.deepfrag.gg (2026-08-30 cutover). pages.dev stays the
// origin and keeps serving as a fallback, but visitors get moved to the brand
// domain with their path/query intact.
if (typeof window !== 'undefined' && window.location.hostname === 'deepfrag.pages.dev') {
  window.location.replace('https://app.deepfrag.gg' + window.location.pathname + window.location.search + window.location.hash)
}
const menuOpen = ref(false)
// Shared so the KOTH "set your location" prompt can open the same modal.
const showSettings = useState('show-settings', () => false)
const showAvail = useState('show-availability', () => false)
const openTeamSettings = useState('open-team-settings', () => false)
const showSupport = ref(false)
onMounted(() => { fetchMe() })
function closeMenu() { menuOpen.value = false }
function openSettings() { menuOpen.value = false; showSettings.value = true }
function openAvail() { menuOpen.value = false; showAvail.value = true }
async function teamSettings() {
  menuOpen.value = false
  await navigateTo('/ladder')
  openTeamSettings.value = true   // ladder page watches this; resets after opening
}

useHead({
  meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
  script: [
    // GA4 (same property as deepfrag.gg; Site Kit owns the WP side). Config
    // only fires on the brand host so pages.dev fallback + localhost stay out
    // of the reports — same guard pattern as sage-frontend. SPA route changes
    // are covered by the stream's enhanced measurement (history events).
    { src: 'https://www.googletagmanager.com/gtag/js?id=G-ZZZJ1C0TV2', async: true },
    { innerHTML: "window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('js',new Date());if(location.hostname==='app.deepfrag.gg'){gtag('config','G-ZZZJ1C0TV2');}" }
  ],
  link: [
    { rel: 'canonical', href: 'https://app.deepfrag.gg' },
    { rel: 'icon', href: '/favicon.ico', sizes: '32x32' },
    { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
    { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32.png' },
    { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500&family=Big+Shoulders+Display:wght@900&display=swap' }
  ],
  htmlAttrs: { lang: 'en', class: 'dark' }
})

useSeoMeta({
  title: 'DeepFrag',
  description: 'QuakeWorld player ratings, demos, and AI coaching.'
})
</script>

<template>
  <UApp>
    <header class="topbar">
      <a href="https://deepfrag.gg" class="brand" title="DeepFrag home">
        <img src="/favicon.svg" alt="" class="brand-mark">
        <span class="brand-word">Deep<em>Frag</em></span>
      </a>
      <nav class="nav">
        <NuxtLink to="/">Rankings</NuxtLink>
        <NuxtLink to="/players">Players</NuxtLink>
        <NuxtLink to="/map">Map</NuxtLink>
        <NuxtLink to="/servers">Servers</NuxtLink>
        <NuxtLink to="/stats">Stats</NuxtLink>
        <NuxtLink to="/h2h">H2H</NuxtLink>
        <NuxtLink to="/balancer">Balancer</NuxtLink>
        <NuxtLink to="/ladder">Ladder</NuxtLink>
      </nav>
      <span class="spacer" />
      <ClientOnly>
        <div v-if="ready" class="auth">
          <div v-if="loggedIn" class="who" @click.stop="menuOpen = !menuOpen">
            <img v-if="user?.avatar" :src="`https://cdn.discordapp.com/avatars/${user.discord_id}/${user.avatar}.png?size=32`" class="avatar" alt="">
            <span class="name">{{ user?.global_name || user?.username }}</span>
            <span class="caret">▾</span>
            <div v-if="menuOpen" class="menu" @click.stop>
              <NuxtLink v-if="user?.canonical_id" :to="`/p/${user.canonical_id}`" class="mi" @click="closeMenu">My profile</NuxtLink>
              <button v-if="user?.team" class="mi" @click="teamSettings">Team settings</button>
              <NuxtLink v-else to="/ladder" class="mi" @click="closeMenu">Join the ladder</NuxtLink>
              <button v-if="user?.canonical_id" class="mi" @click="openAvail">My availability</button>
              <button class="mi" @click="openSettings">Personal settings</button>
              <NuxtLink v-if="user?.is_admin" to="/ladder/admin" class="mi" @click="closeMenu">Ladder admin</NuxtLink>
              <button class="mi danger" @click="logout(); closeMenu()">Sign out</button>
            </div>
          </div>
          <button v-else class="discord-btn" @click="login">
            <svg width="16" height="16" viewBox="0 0 127 96" fill="currentColor"><path d="M107.7 8.1A105 105 0 0 0 81.5 0c-1.2 2-2.5 4.8-3.4 7a97.5 97.5 0 0 0-29.2 0c-1-2.2-2.3-5-3.5-7a105 105 0 0 0-26.2 8.1C2.6 33 .3 57.1 1.4 80.9A106 106 0 0 0 33.7 96c2.6-3.5 4.9-7.3 6.9-11.2-3.8-1.4-7.4-3.2-10.8-5.3.9-.7 1.8-1.4 2.6-2.1a75.6 75.6 0 0 0 64.6 0c.9.8 1.8 1.5 2.6 2.1-3.4 2-7 3.9-10.8 5.3 2 4 4.3 7.7 6.9 11.2a106 106 0 0 0 32.3-15.1c1.4-27.6-2.3-51.5-19.9-72.8ZM42.5 66.3c-6.3 0-11.5-5.8-11.5-13 0-7.1 5.1-13 11.5-13s11.6 5.9 11.5 13c0 7.2-5.1 13-11.5 13Zm42.5 0c-6.3 0-11.5-5.8-11.5-13 0-7.1 5-13 11.5-13s11.6 5.9 11.5 13c0 7.2-5.1 13-11.5 13Z"/></svg>
            <span>Sign in</span>
          </button>
        </div>
      </ClientOnly>
      <div v-if="menuOpen" class="menu-backdrop" @click="closeMenu" />
    </header>
    <NuxtPage />
    <ClientOnly>
      <PersonalSettings v-if="showSettings" @close="showSettings = false" />
      <AvailabilityEditor v-if="showAvail" @close="showAvail = false" />
    </ClientOnly>

    <!-- Report a problem — global, subtle floating button -->
    <button class="report-fab" title="Report a problem" @click="showSupport = true">
      <span class="q">?</span><span class="lbl">Report a problem</span>
    </button>
    <ClientOnly>
      <SupportTicket v-if="showSupport" @close="showSupport = false" />
    </ClientOnly>
  </UApp>
</template>

<style>
:root {
  --bg: #070605;
  --panel: #14100c;
  --panel-2: #1c1610;
  --panel-3: #262017;
  --border: #2a2018;
  --border-2: #3a2f22;
  --fg: #f2ead9;
  --fg-2: #c9bca9;
  --fg-3: #988977;
  --accent: #ff7a1a;
  --accent-2: #e0a33c;
  --accent-glow: rgba(255, 122, 26, 0.25);
  --win: #22c55e;
  --loss: #ef4444;
  --draw: #f59e0b;
}
html, body, #__nuxt { background: var(--bg); color: var(--fg); margin: 0; }
body {
  font-family: 'Inter', -apple-system, system-ui, sans-serif;
  font-size: 14px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }

.topbar {
  background: rgba(7, 6, 5, 0.85); backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 14px 40px;
  display: flex; align-items: center; gap: 32px;
  position: sticky; top: 0; z-index: 50;
}
.topbar::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 1px;
  background: linear-gradient(90deg, transparent 5%, rgba(255, 122, 26, 0.5) 50%, transparent 95%);
  pointer-events: none;
}
.topbar .brand {
  display: flex; align-items: center; gap: 10px;
  color: var(--fg); text-decoration: none;
}
.topbar .brand-mark { width: 26px; height: 26px; border-radius: 6px; }
.topbar .brand-word {
  font-family: 'Big Shoulders Display', sans-serif; font-weight: 900;
  font-size: 22px; letter-spacing: 0.04em; text-transform: uppercase; line-height: 1;
}
.topbar .brand-word em {
  font-style: normal;
  background: linear-gradient(135deg, #ffb347 0%, #ff7a1a 45%, #e5330f 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.topbar .nav { display: flex; gap: 4px; }
.topbar .nav a {
  color: var(--fg-2); text-decoration: none;
  padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 500;
  transition: all 0.15s;
}
.topbar .nav a:hover { background: var(--panel-2); color: var(--fg); }
.topbar .nav a.router-link-active { background: var(--panel-2); color: var(--fg); }
.topbar .spacer { flex: 1; }
.topbar .meta {
  color: var(--fg-3); font-size: 12px; font-family: 'JetBrains Mono', monospace;
}
.topbar .auth { display: flex; align-items: center; }
.topbar .who { display: flex; align-items: center; gap: 8px; cursor: pointer; position: relative; padding: 4px 6px; border-radius: 8px; }
.topbar .who:hover { background: var(--panel-2); }
.topbar .who .avatar { width: 24px; height: 24px; border-radius: 50%; }
.topbar .who .name { font-size: 13px; font-weight: 600; color: var(--fg); }
.topbar .who .caret { color: var(--fg-3); font-size: 10px; }
.topbar .menu { position: absolute; top: calc(100% + 8px); right: 0; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 6px; min-width: 180px; box-shadow: 0 12px 32px rgba(0,0,0,0.5); z-index: 60; display: flex; flex-direction: column; }
.topbar .menu .mi { display: block; text-align: left; background: none; border: 0; color: var(--fg-2); font-size: 13px; font-weight: 500; padding: 9px 12px; border-radius: 7px; cursor: pointer; text-decoration: none; font-family: inherit; }
.topbar .menu .mi:hover { background: var(--panel-2); color: var(--fg); }
.topbar .menu .mi.danger { color: var(--fg-3); border-top: 1px solid var(--border); margin-top: 4px; padding-top: 11px; }
.topbar .menu .mi.danger:hover { color: var(--loss); }
.menu-backdrop { position: fixed; inset: 0; z-index: 55; }

/* Report-a-problem floating button — present everywhere, subtle until hover */
.report-fab {
  position: fixed; right: 18px; bottom: 18px; z-index: 90;
  display: flex; align-items: center; gap: 8px;
  background: var(--panel-2); color: var(--fg);
  border: 1px solid var(--accent); border-radius: 999px;
  height: 42px; padding: 0 16px; cursor: pointer; font-family: inherit;
  box-shadow: 0 6px 20px rgba(0,0,0,0.4); transition: all 0.18s;
}
.report-fab .q { font-weight: 900; font-size: 17px; color: var(--accent); }
.report-fab .lbl { white-space: nowrap; font-size: 13px; font-weight: 600; }
.report-fab:hover { background: var(--panel-3); }
.topbar .discord-btn {
  display: flex; align-items: center; gap: 7px;
  background: #5865f2; color: #fff; border: none;
  padding: 7px 14px; border-radius: 7px; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: background 0.15s;
}
.topbar .discord-btn:hover { background: #4752c4; }

/* ── Mobile app shell ───────────────────────────────────────────────────── */
@media (max-width: 760px) {
  .topbar { padding: 10px 14px; gap: 10px 12px; flex-wrap: wrap; }
  .topbar .brand { font-size: 16px; }
  .topbar .spacer { flex: 1; }
  /* nav drops to its own full-width scrollable strip below brand + auth */
  .topbar .nav {
    order: 5; flex-basis: 100%; overflow-x: auto; gap: 2px;
    -webkit-overflow-scrolling: touch; scrollbar-width: none;
    margin: 2px -14px -4px; padding: 0 14px 2px;
  }
  .topbar .nav::-webkit-scrollbar { display: none; }
  .topbar .nav a { flex: 0 0 auto; padding: 7px 11px; white-space: nowrap; font-size: 13px; }
  .topbar .who .name { display: none; }        /* avatar-only to save room */
  .topbar .discord-btn span { display: none; } /* icon-only sign-in */
  .topbar .discord-btn { padding: 8px 10px; }
  .report-fab { right: 12px; bottom: 12px; height: 38px; padding: 0 13px; }
}
</style>

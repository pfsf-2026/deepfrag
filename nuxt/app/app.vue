<script setup>
useHead({
  meta: [{ name: 'viewport', content: 'width=device-width, initial-scale=1' }],
  link: [
    { rel: 'icon', type: 'image/webp', href: '/favicon.webp' },
    { rel: 'apple-touch-icon', href: '/favicon.webp' },
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500&display=swap' }
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
      <NuxtLink to="/" class="brand">
        <span class="dot" />
        <span>DeepFrag</span>
      </NuxtLink>
      <nav class="nav">
        <NuxtLink to="/">Rankings</NuxtLink>
        <NuxtLink to="/players">Players</NuxtLink>
        <NuxtLink to="/servers">Servers</NuxtLink>
        <NuxtLink to="/stats">Stats</NuxtLink>
        <NuxtLink to="/h2h">H2H</NuxtLink>
      </nav>
      <span class="spacer" />
      <span class="meta">Beta</span>
    </header>
    <NuxtPage />
  </UApp>
</template>

<style>
:root {
  --bg: #0a0d12;
  --panel: #131820;
  --panel-2: #1c2330;
  --panel-3: #252e3d;
  --border: #2b3445;
  --border-2: #3a4458;
  --fg: #f1f5f9;
  --fg-2: #94a3b8;
  --fg-3: #64748b;
  --accent: #14e6c0;
  --accent-2: #06b6d4;
  --accent-glow: rgba(20, 230, 192, 0.25);
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
  background: rgba(10, 13, 18, 0.85); backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 14px 40px;
  display: flex; align-items: center; gap: 32px;
  position: sticky; top: 0; z-index: 50;
}
.topbar .brand {
  display: flex; align-items: center; gap: 10px;
  font-weight: 800; font-size: 17px; letter-spacing: -0.02em;
  color: var(--fg); text-decoration: none;
}
.topbar .brand .dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 12px var(--accent-glow);
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
</style>

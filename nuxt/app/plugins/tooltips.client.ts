/**
 * Tooltip directives — ported from sage-frontend (Vue 2) to Vue 3 + Nuxt 4.
 *
 *   v-tip  = CSS-only pill ("DDR: damage given / taken")
 *   v-rtip = rich hover card with title + body + optional docs link
 *
 * Both run client-side only; SSR has no hover state to apply.
 */

import type { Directive, DirectiveBinding } from 'vue'

// ─── v-tip ─────────────────────────────────────────────────────────────
// Lightweight tooltip via data-tip + data-tip-pos attributes; CSS in
// assets/css/main.css renders the pill on :hover.
const tipDirective: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) { applyTip(el, binding) },
  updated(el: HTMLElement, binding: DirectiveBinding) { applyTip(el, binding) },
  unmounted(el: HTMLElement) {
    el.removeAttribute('data-tip')
    el.removeAttribute('data-tip-pos')
    el.removeAttribute('aria-label')
  }
}

function applyTip(el: HTMLElement, binding: DirectiveBinding) {
  const text = binding.value == null ? '' : String(binding.value)
  if (!text) {
    el.removeAttribute('data-tip')
    el.removeAttribute('data-tip-pos')
    el.removeAttribute('aria-label')
    return
  }
  el.setAttribute('data-tip', text)
  el.setAttribute('aria-label', text)
  let pos = 'above'
  if (binding.modifiers.below) pos = 'below'
  else if (binding.modifiers.left) pos = 'left'
  else if (binding.modifiers.right) pos = 'right'
  el.setAttribute('data-tip-pos', pos)
}

// ─── v-rtip ────────────────────────────────────────────────────────────
// Rich tooltip — pass { title, body?, docs?, docsLabel? }. Positioned
// in viewport coordinates (position:fixed) so it escapes overflow:hidden
// ancestors. Smart-flips above/below + left/right based on viewport fit.
const rtipDirective: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding) {
    applyRichTip(el, binding)
    attachFlipListener(el)
  },
  updated(el: HTMLElement, binding: DirectiveBinding) {
    const old = el.querySelector(':scope > .df-rtip-card')
    if (old) old.remove()
    applyRichTip(el, binding)
  },
  unmounted(el: HTMLElement) {
    const card = el.querySelector(':scope > .df-rtip-card')
    if (card) card.remove()
    el.classList.remove('df-rtip', 'df-rtip-above')
    const enter = (el as any)._rtipEnter
    if (enter) { el.removeEventListener('mouseenter', enter); delete (el as any)._rtipEnter }
    const scroll = (el as any)._rtipScroll
    if (scroll) {
      window.removeEventListener('scroll', scroll, true)
      window.removeEventListener('resize', scroll)
      delete (el as any)._rtipScroll
    }
  }
}

function attachFlipListener(el: HTMLElement) {
  const handler = () => {
    const card = el.querySelector(':scope > .df-rtip-card') as HTMLElement | null
    if (!card) return
    // Force-measure with visibility hidden so first-hover dimensions are right
    card.style.visibility = 'hidden'
    card.style.opacity = '1'
    const cardW = card.offsetWidth || 300
    const cardH = card.offsetHeight || 120
    card.style.visibility = ''
    card.style.opacity = ''

    const trig = el.getBoundingClientRect()
    const gap = 10, margin = 8

    const fitsBelow = trig.bottom + cardH + gap + margin <= window.innerHeight
    const top = fitsBelow ? trig.bottom + gap : Math.max(margin, trig.top - cardH - gap)

    const fitsLeft = trig.left + cardW + margin <= window.innerWidth
    let left = fitsLeft ? trig.left : Math.max(margin, trig.right - cardW)
    left = Math.max(margin, Math.min(left, window.innerWidth - cardW - margin))

    card.style.top = top + 'px'
    card.style.left = left + 'px'
    el.classList.toggle('df-rtip-above', !fitsBelow)
  }
  ;(el as any)._rtipEnter = handler
  el.addEventListener('mouseenter', handler)
  const onScroll = () => { if (el.matches(':hover')) handler() }
  ;(el as any)._rtipScroll = onScroll
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onScroll)
}

function applyRichTip(el: HTMLElement, binding: DirectiveBinding) {
  const v = binding.value
  if (!v || typeof v !== 'object' || !v.title) return

  el.classList.add('df-rtip')

  const card = document.createElement('div')
  card.className = 'df-rtip-card'

  const h = document.createElement('h4')
  h.textContent = String(v.title)
  card.appendChild(h)

  if (v.body) {
    const p = document.createElement('p')
    p.textContent = String(v.body)
    card.appendChild(p)
  }

  if (v.docs) {
    const foot = document.createElement('div')
    foot.className = 'df-rtip-foot'
    foot.appendChild(document.createElement('span'))
    const a = document.createElement('a')
    a.href = String(v.docs)
    a.target = '_blank'
    a.rel = 'noopener'
    a.textContent = v.docsLabel || 'Docs →'
    a.addEventListener('click', (e) => e.stopPropagation())
    foot.appendChild(a)
    card.appendChild(foot)
  }

  el.appendChild(card)
}

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.directive('tip', tipDirective)
  nuxtApp.vueApp.directive('rtip', rtipDirective)
})

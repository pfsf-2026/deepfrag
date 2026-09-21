// One loader for the 4on4 coach report (/api/players/{id}/coaching/fours) shared by
// the Overview and the per-map tabs, so switching tabs never refetches. Cached per
// player for the session in useState. Framework: docs/coaching_4on4.md.
export const COACH_MAPS = ['dm3', 'dm2', 'e1m2', 'schloss']
export const LEVEL_COLORS: Record<number, string> = { 1: '#ff5d6c', 2: '#e0a33c', 3: '#c9a66b', 4: '#38bdf8', 5: '#34d67a' }
const INV: Record<string, string> = { ra: 'RA', ya: 'YA', ga: 'GA', mh: 'MH', quad: 'Q', pent: 'P', ring: 'R', rl: 'RL', lg: 'LG' }

export function invChips(items: Record<string, number> | null | undefined): string[] {
  return Object.entries(items || {}).filter(([k, v]) => v && INV[k]).map(([k, v]) => `${v}×${INV[k]}`)
}
export function fmtCoachDate(d: string | null | undefined): string {
  return d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''
}
// minimal markdown for narration: **bold**, _italic_, paragraphs
export function coachMd(t: string | null | undefined): string {
  if (!t) return ''
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc(t).split(/\n{2,}/).map(p => '<p>' + p.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/_(.+?)_/g, '<em>$1</em>').replace(/\n/g, '<br>') + '</p>').join('')
}
export function signed(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—'
  return (v > 0 ? '+' : '') + Number(v).toFixed(digits)
}

const INFLIGHT: Record<string, Promise<any> | undefined> = {}

export function useFoursCoach(cid: Ref<string>) {
  const isBrowser = typeof window !== 'undefined'
  const base = isBrowser ? '' : ((useRuntimeConfig().public.apiBase as string) || '')
  const cache = useState<Record<string, any>>('fours-coach-cache', () => ({}))
  const loading = ref(false)
  const err = ref('')
  const report = computed(() => cache.value[cid.value] || null)

  async function load(force = false) {
    const key = cid.value
    if (!force && cache.value[key]) return cache.value[key]
    loading.value = true; err.value = ''
    try {
      // three components mount together (strip, overview/map tab); share one request
      if (!INFLIGHT[key]) {
        INFLIGHT[key] = fetch(`${base}/api/players/${encodeURIComponent(key)}/coaching/fours`)
          .then(async r => { if (!r.ok) throw new Error(`coach ${r.status}`); return r.json() })
          .finally(() => { delete INFLIGHT[key] })
      }
      const data = await INFLIGHT[key]
      cache.value = { ...cache.value, [key]: data }
    } catch (e: any) { err.value = String(e?.message || e) } finally { loading.value = false }
    return cache.value[key]
  }
  onMounted(() => { load() })
  watch(cid, () => { load() })

  const level = computed(() => report.value?.level || null)
  const maps = computed<any[]>(() => report.value?.maps || [])
  const mapCard = (m: string) => maps.value.find((c: any) => c.map === m) || null
  return { report, loading, err, load, level, maps, mapCard }
}

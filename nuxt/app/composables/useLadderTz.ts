// Timezone resolution for the ladder scheduler. Priority:
//   1. user's explicit preferred timezone (Personal settings)
//   2. derived from their state (US/CA)
//   3. fall back to Eastern (NA ladder) — and the UI nudges them to set it.

// US states + DC + CA provinces → primary IANA zone.
export const STATE_TZ: Record<string, string> = {
  // Eastern
  ME: 'America/New_York', NH: 'America/New_York', VT: 'America/New_York', MA: 'America/New_York',
  RI: 'America/New_York', CT: 'America/New_York', NY: 'America/New_York', NJ: 'America/New_York',
  PA: 'America/New_York', DE: 'America/New_York', MD: 'America/New_York', DC: 'America/New_York',
  VA: 'America/New_York', WV: 'America/New_York', NC: 'America/New_York', SC: 'America/New_York',
  GA: 'America/New_York', FL: 'America/New_York', OH: 'America/New_York', MI: 'America/New_York',
  IN: 'America/New_York', KY: 'America/New_York', ON: 'America/Toronto', QC: 'America/Toronto',
  // Central
  IL: 'America/Chicago', WI: 'America/Chicago', MN: 'America/Chicago', IA: 'America/Chicago',
  MO: 'America/Chicago', AR: 'America/Chicago', LA: 'America/Chicago', MS: 'America/Chicago',
  AL: 'America/Chicago', TN: 'America/Chicago', OK: 'America/Chicago', KS: 'America/Chicago',
  NE: 'America/Chicago', SD: 'America/Chicago', ND: 'America/Chicago', TX: 'America/Chicago',
  MB: 'America/Winnipeg',
  // Mountain
  MT: 'America/Denver', WY: 'America/Denver', CO: 'America/Denver', NM: 'America/Denver',
  ID: 'America/Denver', UT: 'America/Denver', AZ: 'America/Phoenix', AB: 'America/Edmonton',
  // Pacific
  WA: 'America/Los_Angeles', OR: 'America/Los_Angeles', CA: 'America/Los_Angeles',
  NV: 'America/Los_Angeles', BC: 'America/Vancouver',
  // Other
  AK: 'America/Anchorage', HI: 'Pacific/Honolulu'
}

// Dropdown options for Personal settings.
export const TZ_OPTIONS: Array<[string, string]> = [
  ['America/New_York', 'Eastern (ET)'],
  ['America/Chicago', 'Central (CT)'],
  ['America/Denver', 'Mountain (MT)'],
  ['America/Phoenix', 'Arizona (no DST)'],
  ['America/Los_Angeles', 'Pacific (PT)'],
  ['America/Anchorage', 'Alaska'],
  ['Pacific/Honolulu', 'Hawaii'],
  ['America/Sao_Paulo', 'Brazil — São Paulo'],
  ['America/Argentina/Buenos_Aires', 'Argentina'],
  ['Europe/London', 'UK / Ireland'],
  ['Europe/Stockholm', 'Nordics / Central Europe'],
  ['Europe/Helsinki', 'Finland / Eastern Europe'],
  ['Australia/Sydney', 'Australia (Sydney)']
]

const FALLBACK = 'America/New_York'

export function resolveTz(user: any): string {
  return user?.timezone || STATE_TZ[user?.state] || FALLBACK
}
// True when we actually know the zone (vs falling back to ET).
export function tzKnown(user: any): boolean {
  return !!(user?.timezone || STATE_TZ[user?.state])
}

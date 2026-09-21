// Per-map quad playbooks (2026-09-21, Peter: "converting quad is a whole new page for each
// map"). The words (geography, the ways in, what to do) are written from Peter's map knowledge;
// the numbers come from the corpus pass tools/mvd_features/quad_approach_pass.py +
// quad_approach_report.py --json, which writes quadPlaybookData.json (share of contests,
// conversion, taker stack and arrival time per named spot, plus what decides the quad
// regardless of the way in). Regenerate the JSON after a corpus refresh; the text stays.
import data from './quadPlaybookData.json'

export interface QuadWay { name: string; locs: string[]; how: string }
export interface QuadPlaybookText { map: string; title: string; geography: string; ways: QuadWay[]; play: string[]; late?: { locs: string[]; note: string } }
export interface SpotStat { loc: string; n: number; share: number; conv: number; taker_eff: number | null; died_pre_pct: number; taker_enter_s: number | null }
export interface Bucket { bucket: string; n: number; conv: number }
export interface QuadMapData { contests: number; spawns_contested_by_2plus: number; closest_at_minus2_takes_pct: number | null; most_stacked_takes_pct: number | null; by_eff: Bucket[]; by_d2: Bucket[]; spots: SpotStat[] }

export const QUAD_TEXT: Record<string, QuadPlaybookText> = {
  dm3: {
    map: 'dm3', title: 'Quad on dm3',
    geography: 'Quad sits above mound. There is no door. You get to it by jumping across the gap from either side, by coming down from high YA (through the area above YA), or through the pent window off high bridge. A rocket jump up from mound happens, but rarely. The RL room is far: up the stairs from low bridge to high bridge and across through the window, or round through YA, so a player who is still at the RL when it spawns is not getting it.',
    ways: [
      { name: 'Already on the platform', locs: ['Quad', 'lifts', 'lifts.below'], how: 'Standing on or under the platform when it spawns. The player who is here with stack takes it more than anyone; this is what "be there first" means on dm3.' },
      { name: 'Through the pent window, off high bridge', locs: ['window', 'window.Quad', 'Pent', 'bridge.high'], how: 'Across high bridge and through the window. The best-converting way in that is not already being there: you arrive with stack and the platform in front of you.' },
      { name: 'The gap jump, either side', locs: ['Ring', 'SNG.tele', 'hill'], how: 'From ring, the SNG tele or the hill you jump the gap onto the platform. You are in the air for a moment where a stacked player already up there gets a free rocket on you.' },
      { name: 'Down from high YA', locs: ['YA', 'YA.box'], how: 'Through the area above YA and down, with the yellow already on. Fewer players use it than the gap, and it converts about the same.' },
    ],
    late: { locs: ['RL', 'bridge.low', 'water', 'RA.tunnel', 'RA', 'GL', 'RA.low'], note: 'still at the RL, low bridge, water or the red 5 seconds before' },
    play: [
      'Be on the platform before it spawns, not jumping onto it as it spawns. The jump is where you die.',
      'Come through the window or down from YA with the yellow on. The takers on dm3 arrive with a stack of about 200; the players who miss arrive with 100.',
      'If a teammate is already on the platform, do not jump the gap too. Hold the window instead so nobody surprises him.',
      'Do not leave the RL for a quad that is 10 seconds out. Take the red, and be early for the next one.',
    ],
  },
  dm2: {
    map: 'dm2', title: 'Quad on dm2',
    geography: 'Quad is in the water room next to big, and there is no door. Players come down the quad path from high RL, rocket-jump up from big (all the time), and in from the water side out of secret, the stairs or the tele. On dm2 the quad also sits a second or two before anyone takes it, so the quad time drifts later a little faster here.',
    ways: [
      { name: 'The quad path from high RL', locs: ['high.RL', 'Quad.way', 'path'], how: 'The stacked way in. You come with the RL and usually a yellow. Whoever holds the top of this path controls the room.' },
      { name: 'Rocket jump up from big', locs: ['big', 'big.stairs'], how: 'Fast and loud. You arrive on a rocket jump with less health than you left with, and everyone in the room heard it.' },
      { name: 'The water side', locs: ['secret', 'tele', 'tele.high', 'tele.entry', 'tele.YA', 'Quad.low'], how: 'Out of secret, the stairs or the tele. Slow, and usually the second player into the room. This is where the free kills come from for whoever holds the path.' },
      { name: 'Already in the room', locs: ['Quad'], how: 'Standing in the quad room when it spawns. Nobody converts like the player who is already there with stack.' },
      { name: 'Late from NG, low RL and the red', locs: ['NG', 'low.RL', 'RA.MH'], how: 'If you are still at low RL or the red 5 seconds before, you are not getting this quad. Take the red instead and be early for the next one.' },
    ],
    play: [
      'Come down the quad path from high RL 10 seconds before it is due, with a yellow on, and stop at the top of the path.',
      'Fire down at the players coming up from big and out of the water. They are the ones without armor.',
      'The second player holds big: if the enemy rocket-jumps up, he lands in front of you, not behind your teammate.',
    ],
  },
  e1m2: {
    map: 'e1m2', title: 'Quad on e1m2',
    geography: 'Quad is next to the GL room and is the strongest item on the map. There are two ways in: from the GL side, and from the stairs up from mid room. There is no red on e1m2, so stack here means the yellow or a mega.',
    ways: [
      { name: 'The GL side', locs: ['GL', 'GL.Quad', 'GL.stairs'], how: 'The main way in and the busiest. Most takes come from here, and most of the deaths before the spawn happen here too.' },
      { name: 'The stairs from mid', locs: ['Quad.stairs', 'cross', 'MH.low'], how: 'The second door. A player here sees the GL side coming and gets the first rocket.' },
      { name: 'Already there', locs: ['Quad', 'Quad.box'], how: 'On the pad or in the box when it spawns.' },
      { name: 'From YA and the RL, the long way', locs: ['YA', 'RL', 'door', 'bridge'], how: 'Coming from the yellow or the RL you arrive through one of the two doors, but late. Good stack, bad timing.' },
    ],
    play: [
      'Two doors, two players. One on the GL side, one on the stairs. Solo, you are guessing.',
      'Bring the yellow or the mega. Naked players convert one spawn in seven here; stacked players convert more than half.',
      'If you must come solo, take the stairs: you see the GL door and the GL door does not see you first.',
    ],
  },
  schloss: {
    map: 'schloss', title: 'Quad on schloss',
    geography: 'Three ways to the schloss quad: the door at floor level, the drop-down from above it, and the path in from cathedral rocket. It is two to three seconds from the red area at speed, which is why the red and the quad are the same fight on schloss.',
    ways: [
      { name: 'The drop-down from above quad', locs: ['Quad.high', 'Quad.ledge'], how: 'The way the takers come. You are above the pad with a yellow on and drop onto it as it spawns; whoever is at the door has to look up.' },
      { name: 'The door from the red side', locs: ['RA', 'RA.low', 'RA.cellar', 'RA.window', 'yard', 'yard.tunnel', 'yard.Pent', 'yard.roof', 'cemetary', 'cemetary.tele', 'cemetary.Ring'], how: 'You leave the red with a rocket loaded and arrive at the door with armor on. This is where the fight is, more than where the quad is.' },
      { name: 'The path from cathedral rocket', locs: ['cathedral', 'cathedral.YA', 'cathedral.SSG'], how: 'You take the cathedral RL and come along the path with the cathedral yellow on. Good stack, but you arrive after the players above have settled.' },
      { name: 'From tower', locs: ['tower', 'tower.RL', 'tower.entry'], how: 'Down from the tower with the RL. Quick if you leave early; late if you wait for the fight up there to finish.' },
      { name: 'Already in the room', locs: ['Quad', 'Quad.low'], how: 'On the pad or low in the room when it spawns. Fine with stack; naked down here you are the target for the drop-down.' },
    ],
    play: [
      'Come from above. The players who take schloss quad most often were above it 5 seconds before, with a yellow on, not at the door.',
      'The door is where the fight is; the drop-down is where the quad is. If a teammate holds the door, be the one above.',
      'Leave red or tower 8 seconds before it is due. Off the cathedral rocket, take the path early or take the yellow and hold the red instead: on schloss the two items respawn into the same fight.',
    ],
  },
}

export const QUAD_DATA = data as Record<string, QuadMapData>
export function quadPlaybook(map: string) {
  const text = QUAD_TEXT[map]; const d = QUAD_DATA[map]
  if (!text) return null
  // roll the named spots up into the ways the text describes
  const ways = text.ways.map(w => {
    const spots = (d?.spots || []).filter(s => w.locs.includes(s.loc))
    const n = spots.reduce((a, s) => a + s.n, 0)
    const takes = spots.reduce((a, s) => a + s.n * s.conv / 100, 0)
    const eff = spots.filter(s => s.taker_eff != null && s.n).sort((a, b) => b.n - a.n)[0]?.taker_eff ?? null
    const enter = spots.filter(s => s.taker_enter_s != null).sort((a, b) => b.n - a.n)[0]?.taker_enter_s ?? null
    const died = n ? spots.reduce((a, s) => a + s.n * s.died_pre_pct / 100, 0) / n * 100 : null
    return { ...w, n, share: d?.contests ? Math.round(100 * n / d.contests) : null, conv: n ? Math.round(100 * takes / n) : null, takerEff: eff, enterS: enter, diedPre: died != null ? Math.round(died) : null }
  })
  let late = null
  if (text.late && d) {
    const spots = d.spots.filter(s => text.late!.locs.includes(s.loc))
    const n = spots.reduce((a, s) => a + s.n, 0); const takes = spots.reduce((a, s) => a + s.n * s.conv / 100, 0)
    late = { note: text.late.note, n, share: d.contests ? Math.round(100 * n / d.contests) : null, conv: n ? Math.round(10 * 100 * takes / n) / 10 : null }
  }
  return { ...text, ways, late, data: d || null }
}

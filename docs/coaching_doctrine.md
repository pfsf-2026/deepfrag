# Coaching doctrine — what Peter has taught the coach

**Read this before writing any coaching, analysis or strategy text.** It exists because long sessions get
summarised and the game knowledge Peter taught in passing was the first thing lost (red armor written as
+150 and "footsteps" cited as a cue, both on 2026-10-16). Everything here is a standing rule until Peter
changes it. When he corrects something, add it to §7 the same day, with the date.

## 1. Game facts (QuakeWorld, KTX, the TB4 maps)
- Armor: **red +200 (absorbs 80%), yellow +150 (60%), green +100 (30%)**. Mega: **+100 health up to 250**,
  decays back to 100. A fresh spawn is 100/0. Our `eff` (effective HP) shows a spawn with red as ~300, with
  yellow ~250. Fight-winning weapons: RL and LG; the shotgun is the spawn weapon ("boomstick").
- Respawns: armors 20 s after the take; mega 20 s after the holder is back at 100; weapons 30 s; quad 60 s
  ("quad spawns every 60 s and is never missed on dm3": a 20-minute game has at least 19); pent 5 min.
- **There are no footstep sounds.** Running is silent. Everything else is audible and passes through walls:
  jumps and landings, every item and weapon pickup, teleporters, lifts, doors, water, gunfire, pain. Plus
  the kill feed. Good players rebuild the enemy's position, route and stack from sound.
- 4on4 pickups are 20-minute games. NA teams talk on voice (mm3); mm2 is rare on the NA side, common in EU.
- There is no quad in 1on1. There is no +/- in a duel: it is the score.
- Red armors per map: **schloss 1, dm3 1, dm2 2, e1m2 0** — every item stat must be read per map.
- LG exists only on dm3 among the TDM maps; RL matters more than LG there; LG ammo is scarce (weight it by
  cells). RL quality is direct hits AND splash efficiency.
- Quad rooms and how you reach them (Peter, 2026-09-21):
  - **dm3**: quad is above the mound; you come in by jumping the gap from either side, from high YA, or
    through the (pent) window; rocket-jumping up from the mound is rare. "RL side" is meaningless for dm3
    quad — RL room to quad is low bridge → stairs → high bridge → window, far too long. Quad and the RL/water
    area are separated by many walls: never count a player in RL/water as "near quad".
  - **dm2**: no door; people come from everywhere — high RL, the quad path from high RL, rocket-jumping up
    from big (happens all the time), and the water side from secret, stairs or tele.
  - **e1m2**: two ways in — the GL side and the stairs from the mid room.
  - **schloss**: a door at floor level, a drop-down from above, the path from cathedral rocket.
- "Near quad" = **inside the quad room** (per-map room list in `tools/mvd_features/quad_rooms.json`), not a
  straight-line radius; a player who died in the room within 10 s of the spawn counts as having been there.

- **Spawn points per map** (clustered from demo positions in 60 TB4 games, 2026-10-17; names confirmed by
  Peter the same day: keep "mega (SNG low)" with the qualifier — there are two SNG spawns on dm3, one facing
  tele and one facing into the SNG room, and both usually turn and run to tele on the first spawn; "lifts"
  not "lifts top"). A "spawn" in any table means one of these, never an
  area name from the `.loc` files. dm3 (6): RL (1520,431,-88), YA (1472,-928,-24), tele (-631,-679,-16),
  mega/SNG low (-880,-232,-16), lifts (513,768,216), RA tunnel (192,-208,-176). dm2 (9): quad/big (1712,-504,24;
  .loc quad.low, below the quad), low RL (2576,-1328,24), big stairs (2048,-1352,136), water (2624,-487,32),
  RA/MH (2704,-2048,128), tele button (2248,-16,-136; the low tele), low button (2176,-2176,84; next to the
  RA/mega room, stairs down to low RL), tele/ya (2543,-31,-64), NG (2560,-192,32). e1m2 (10): start
  (1496,1328,200), crossing (168,-480,320), door (792,-208,320), GL (936,-1216,432; .loc gl.quad, the GL
  side), quad/GL (792,-992,440; .loc gl.quad), MH low (-415,-144,320), quad healthpaks (408,-752,432), RL
  (784,808,200), YA (1080,-720,312), spikes (1935,-135,312). schloss (8): tower RL (-240,-2184,440), Cat SSG
  (968,-3416,408), cemetery tele (1168,-1984,312), RA/cemetery (696,-3184,184; .loc cemetery, 505 u from the
  RA), tower entry (136,-2471,440), mid (-249,-2361,312; .loc quad.low by the yard tunnel, 640 u from pent),
  quad/Cat high (424,-3240,600; .loc quad.high), quad/Cat low (455,-3032,440; .loc quad, 445 u from the RA,
  740 u from the quad). Names are Peter's (2026-10-17; "mid" and "quad/Cat high" confirmed by him the same
  day); "Cat" is the word for cathedral in all coaching text.
- **Rockets are ammo, the launcher is not a weapon without them.** Any state that says "has the RL" must say
  how many rockets; an RL with none is a shotgun. On schloss rockets are scarce: the packs are in the
  trench, at the tower tele exit and at the top of the Cat SSG stairs (Peter, 2026-10-21).
- **Location vocabularies differ.** `player_state10s.loc` and the analyzer's `locs` use the `.loc` files
  (`mvd-analytics/loc/data/<map>.loc`: dm3 has water, water.LG, water.GL, water.rox …); the map JSONs
  (`mvd-web/static/maps/<map>.json`) use different names (dm3: bridge.low, hill, RL …). Say which one a
  table uses. `loc` is filled for dead players too (the death spot).

## 2. How fours is actually played (the context the coach must model)
- Teams **flood** strategic zones under a lock — YA on e1m2, tele or low RL on dm2 — and start many fights as a
  boomstick on purpose, to flood an area or to support quad, or because they spawned with no choice. Stats
  like "fights started from behind" and "chained deaths" are meaningless without this context (Peter
  2026-09-11, 2026-09-22). Coaching those as individual flaws is wrong.
- Locks are real: "I can't even spawn" is a team state, not a player state. The pool chains ~65% of deaths
  inside 14 s even when not locked. Coach the difference from survivors in the same state, never the
  pool-wide number (2026-10-16).
- Spawn frags are a skill: knowing the spawn points and putting rockets/grenades on them the moment you frag.
  Waiting to respawn does not change where you land, only how fast you can be killed (2026-09-08). BD:
  "farming spawns better is a sign of a good player"; DDR alone is not the stat.
- Quad: attendance is common (80-85% of spawns for everyone); the levers are arriving stacked, arriving with
  the RL, and **conversion**, not attendance. A naked quad steal is a 30-second deny, not a fight: its value is
  survival. Prepared takes (RL + 150) are what separate players; BD takes the most quads and uses them like
  an average player; war and chris use them best (2026-10-06/07). Powerup efficacy (swing from runs) is a
  first-class stat; pent counts too.
- Team damage: Omicron hates it; its impact on win probability was checked (2026-09-15) — treat it as real.
- Ping matters (dusty 12 ms vs yeti 142 in the same game); game scores need a ping adjustment.
- Map specialists exist (bogojoker on schloss, chris on dm3); ratings should reward playing all four maps.

- **Comms.** NA teams run on voice; EU teams use MM2 (team say) far more and better. Peter wants NA players
  trained back toward effective MM2. Any in-the-moment coaching ("rewind") should assume no voice, show what
  the team's MM2 would have told the player, and suggest the MM2 line the player should have sent.

- **Per-map control doctrine (Peter, 2026-10-17, his words condensed).** The map section of any coaching text
  starts from these, and the data is read against them:
  - **dm3**: rarely flooded. Getting control back when out of control is stealing a quad and killing someone
    who drops a weapon, or having a weapon and getting the quad over the enemies, then killing 1–2 key enemy
    weapons and taking RA control back. Three megas: SNG (low, by the SNG/MH), hill (under the ring/quad),
    Pent side (RL/pent room) — always say which one. What the data says about getting out (2,196 dm3 locks that ended): in the
    half-minute before a locked team got out, it had almost always done two things — someone took a yellow
    (two breaks in three) and someone got a rocket launcher (two in three). A red is in one break in three and
    a quad in one in eight: they come after you are already out. Of the three megas the one that is part of a
    break is the hill mega (one in three), more than the Pent side (one in four) or SNG (one in five). Killing a
    stacked enemy is in only one break in eight. So on dm3 a lock does not end with a hero frag; it ends with a
    yellow and a rocket in your team's hands, then the red.
  - **dm2**: a lot easier to lock. The lock positions: (1) one at the bottom of the tele stairs covering the two
    spawns and the tele to high RL; (2) one running quad and secret; (3) one running the back room red/mega and
    low RL; (4) one floating where help is needed. Floods when locked: hit tele hard, or get at least one
    teammate with an RL at low RL and send the rest to flood low RL between quads. Low RL is very hard to hold
    against a quad coming from path or big — open question for the data. What the data says about getting out (2,471 dm2
    locks that ended): the way out is the yellow at big first (three breaks in four have it), then the back-room
    red (two in three). Low RL and the secret red are in about half, the high RL in four of ten, the megas
    less, quad one in eight. Sequence: big yellow, then the red behind position (3)'s room.
  - **e1m2**: the flood is usually the YA room, the only real armor. GA helps but does not stand up to a
    stacked-on-stacked fight. Flooding quad early matters. What the data says about getting out (1,727 e1m2 locks that
    ended): a rocket launcher is in two breaks of three, the yellow in four of ten, the mega in one of three,
    quad one in seven. No red to race for on this map: the RL is the whole lever, the yellow second.
  - **schloss**: floods happen at Cat RL or tower RL, or at quad during quad times. Quad and pent are
    almost always flooded — not because of a lock, to flip control with powerups. Hard to lock; back and forth.
    What the data says about getting out (1,771 schloss locks that ended): a yellow (the tower one in six breaks
    of ten, the cathedral one in five) and one of the two RLs (tower RL or Cat RL, each in half the
    breaks), then the red (half). Those two RL rooms are exactly where Peter says the floods happen; the data
    says that is also where the recovery is built. Caveat for all four: a lock is measured in stack and rockets,
    so a break always shows up as items gained — what these add is which item, in what order, and that frags of
    stacked enemies are not how it happens.
  - **Plan**: a deep dive per map — taking control, holding control, breaking control, controlling powerups,
    controlling key areas/items — before more generic lock advice.

## 3. How duels are played (what the coach must model)
- Movement is at least half the game and leads every piece of advice; then timing items, being early,
  stack before fights, sound, weapons; map geometry last; aim is trained, never assumed
  (`docs/sage_writer_prompt.md`).
- Mega timing (within 3 s) predicts the winner better than mega count; efficient timing is the skill. Red
  share: whoever takes more reds wins 3 in 4; megas 75%.
- The move Peter wants coached: from "fight first" to methodical stack building (2026-09-08).
- Good duelists have ~90% certainty of the opponent's stack from sound and fight length; the coach cannot
  assume a player has it — it has to teach it as a skill and never say "leave at −60" as if the number were on
  the HUD (2026-10-14 Discord: Bance, infiniti).

## 4. Measurement rules
- Everything per map. Reds, quads, chained deaths, levels and "work on this" are per map or they are wrong.
- Quad attendance by room (see §1). Lock state from team stack + RL + red counts, per-map thresholds.
- Chained death = died within 14 s of spawning; must be read against the team's lock state and floods.
- Adjusted kills split a frag by damage share (finisher keeps 40%). WAR = wins above replacement, cumulative
  and per game; expected vs actual +/- given teammates and opponents is what should move a 4on4 rating,
  compared with the teammates' expected vs actual (2026-09-23).
- Aliases are folded (george/whodat/igor/datnigga/fok/allufok/tardface = war; anton = sane). No ratings for
  alias accounts; no 4on4 rating without a duel rating.
- Forecast duel odds from margins (frag diff, DDR against known opponents), not from mu alone (Yeti bet).

## 5. Coaching rules
- Framework: **perception** (what the player could know) → **decision** → **execution**. Tag every finding.
- Coach a *difference*: the player vs survivors in the same state, same map. Never a pool-wide truth.
- Condition the advice on state (locked / not, cue heard / none, alone / paired, item due) and give the
  alternative as a place and an action with its number ("the red side lives 53% here, quad side 19%").
- Real cues only (no footsteps). Numbers only from the data or §1, never from memory.
- Each map is its own tab and its own game. Plain English, 5th-grade clear, every stat in the glossary with
  "units" defined. One focus at a time. Levels are public on profiles.
- Moments over aggregates: 3-5 timestamps per player per night, ranked by win-probability cost, with the hub
  link, so a player can review 30 seconds instead of a demo. Nexus's analyzer already emits powerup runs,
  frag streaks and airgibs as Key Moments — use them as the frame.
- Speak plainly about strong players too: say "takes the most" when the data says volume, "best" only when it
  says efficiency (2026-10-06).

- **Story, not "top players do X" (Peter, 2026-10-17).** A coaching text is a sequence of situations the player
  is actually in ("you just spawned and your team is locked", "you heard them take red", "you have 150 and no
  gun"), the decision available there, and what players who make that decision get next — the item, then the
  damage they did with it; the shotgun damage before dying off a locked spawn. Numbers sit under the story as
  evidence. "TOP vs FIELD" describes who is better; it is never the advice.

- **The first move off a spawn is an item-timer decision (Peter, 2026-10-17).** "If you spawn RL and RL time is
  soon, stay and fight for it; if RL was just taken, leave for LG or YA now. Don't sit in the RL room 25 s
  waiting." No table of "best first room" without the item state at that second; every rewind shows what was
  up, what was coming and when, and who took it. Knowing item times is the core of the coaching.
- **Voice comes from the stream.** Many NA players stream (Peter: twitch.tv/cronus1976). Moments carry the
  wall-clock time so the player can find them in the VOD with voice comms; the report links there when the
  stream is known.

- **The Why chain (Peter, 2026-10-21).** Every finding is coached from the bottom of a chain of whys: the
  measured difference → the behaviour that produces it → the decision behind the behaviour → the skill or
  knowledge behind the decision → what to train (aim and movement on POVs and dmm4 duels, sound recognition,
  timing items closely and arriving early, the spawn-to-gun-to-stack routes, reading MM2 and the kill feed,
  when to leave a fight, the MM2 habit). The chains are written in `docs/coaching_why_chains.md`, verified
  by Peter, and every coaching text (reveals, the coach's read, levers, narration) speaks from the chain's
  lower rungs. A number is never the lesson; it is where the chain starts.

## 6. Process
- Read this file before any coaching text. Re-read §1 before quoting any value or timer.
- A correction from Peter goes into §7 immediately, then into the relevant section.
- Memory (`~/.claude/projects/-Users-peteryeargin/memory/`) points here; it is not a substitute for this file.

## 7. Corrections log (dated, verbatim where it matters)
- 2026-06-14 "dont' restart without checking with me first, from now on" (players were on the servers).
- 2026-08-31 "there is no quad in 1on1. you know that."
- 2026-09-11 Quad spawns every 60 s and is never missed on dm3 — the pass had missed several.
- 2026-09-12 "in 4on4, RL is usually more important than LG on dm3 … add LG cell count into your weight."
- 2026-09-20 Reds per map: schloss 1, dm3 1, dm2 2 — measure per map, coach per map.
- 2026-09-21 Quad entries per map as in §1; "RL side" is meaningless on dm3.
- 2026-09-22 "we start lots of fights as a boomstick, to flood certain areas, or to support quad … or we spawn
  and have no choice" — fights-from-behind training is not a lever without context.
- 2026-10-05 "remember there is no +/- in duel."
- 2026-10-06 "Quad and RL rooms are separated by many walls. You keep considering people in RL/water area
  close to quad" — room rule replaces the radius.
- 2026-10-16 "RA is +200 armor. You should know this." Red +200, yellow +150, green +100, mega +100.
- 2026-10-16 (infiniti, confirmed) there are no footstep sounds in QuakeWorld.
- 2026-10-16 "two-thirds of your deaths inside 14 s" is true of the whole pool; never present it as a flaw.
- 2026-10-17 "Those aren't spawns. you know where the spawns are. you don't spawn in water gl, you spawn at RL"
  — a table of "area at the first 10 s tick after a spawn" was labelled as spawn points. It also mixed death
  spots into the "die" column (dead rows carry `loc`). Spawn tables use the real spawn points in §1, and the
  first move is measured as the first room entered from that spawn.
- 2026-10-17 "we rarely flood 'mega' on dm3. There are also 3 megas, so which are you talking about?" — an item
  take before a lock break is not a flood, and a mega on dm3 must be named (SNG / hill / Pent side).
- 2026-10-17 "this is not actionable. We need more of a story approach to this rather than 'top players do
  this'. That's crap … make this narrative with data, and not data focused." — §5 rule above; the research
  doc's coaching section and the Game Report wording were rewritten in that voice the same day.
- 2026-10-17 "if you spawn RL, and you know RL time is soon, you should stay and fight for it … Knowing item
  times is going to be key" — the first-move paragraph was rewritten as an item-timer decision; rewinds show
  item state at the spawn second.

- 2026-10-21 "this is bad advice" (schloss quad rewind, 0:52): the report called a launcher with no rockets
  "the RL", sent the player to a red a teammate was taking that was not on the way, and ignored that a
  stacked teammate with rockets was already placed for the quad. Rules above; rockets, teammates' states
  and on-path armors are now in every rewind, and the coach's read is told to trust the player's stated
  ammo and never to call an item "on the way" unless it is.

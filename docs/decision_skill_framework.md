# Player Rating & Bot Decision/Skill Framework

Status: living document. Internal — the ratings feature is gated until launch.

DeepFrag turns MVDs into **player ratings**. This document defines those ratings as a structured **Player Card** (≈29 attributes, 0–99) and shows how the *same* numbers double as **bot emulation profiles** for the Komodobots project. One MVD pass → a player's public bragging-rights rating **and** their bot card.

## Repository split & data flow

| Repo | Owns | Role |
|---|---|---|
| **DeepFrag** (`pfsf-2026/deepfrag`, this repo) | the MVD parser, the rating math, the 0–99 Player Cards, the Cards API | **source of truth** for ratings/profiles |
| **Komodobots** (`Xerialen/komodobots`, private) | the bot, movement controller, decision dials | **consumer** — pulls Cards from DeepFrag's API, turns them into bot dials |

```
MVDs ──► DeepFrag parser ──► Player Card (0–99) ──┬──► public player rating (bragging rights; gated until launch)
                                                  └──► Cards API ──► Komodobots/KTX ──► bot dial settings (emulation)
```

The decision *spec* below is shared; the **rating/profiling half is implemented here in DeepFrag**, the **bot-dial/decision half is implemented in the bot code (KTX/Komodobots)** and pulls Cards as needed. We can move the decision modules into the bot code incrementally.

Two engine seams on the bot side (for reference; implemented in the Komodobots/KTX tree, not here):

| Layer | Owns | KTX seam |
|---|---|---|
| Movement (Xerial) | bunnyhop, air-strafe, route execution | `BotSetCommand()` (`src/bot_movement.c`) |
| Decision & Skill (this framework) | wants, target choice, item/economy/team choices, and *how good* they are | goal/desire + target + teammate-help (`src/bot_botgoals.c`, `src/bot_botenemy.c`, `src/bot_bothelp.c`) |

The guiding constraint: **no theoretical ratings.** Every attribute reduces to a formula over signals we actually have, with an honest confidence tier. Where we can only proxy, we say so.

---

## 1. The model

- **Player Card** — a player (real or synthetic) as **~29 Attributes, each 0–99.**
- **Pillars** — the 6 attribute groups (below).
- **Dials** — bot-side parameters (frogbot cvars / new cvars) an attribute drives.
- **Presets** — canned cards for difficulty levels.
- **OVR** — a context-weighted overall (Duel weighting ≠ Team weighting); show the radar, quote the OVR.

Two ways to fill a card:

- **Profile a real player** from their MVDs → their Card → public rating + emulation.
- **Pick a difficulty** → an archetypal Card → skill level.

### Rating scale (locked)

- **All attributes 0–99.** Madden-style; no separate 1–20 axis.
- An attribute = the player's **percentile within the population on the measured signal**, mapped to 0–99. "Tracking 85" = better LG control than 85% of the population.
- **Anchor population is per-mode** (duel skill ≠ team skill): duel cards percentile against the 1on1 population; 4on4 cards against the 4on4 population. (Corpus today: ~1,961 indexed players; 6,409-demo 4on4 corpus + hub.)
- **Confidence band** travels with every attribute: few demos → wide band. A low-confidence Card renders with error bars, not false precision.

### Difficulty model (locked)

- **Emulation mode:** load a real player's 0–99 Card → an exact bot.
- **Difficulty mode:** choose a **Level** → a synthetic Card clustered around a target 0–99 band *with believable internal variance* (a real archetype, not a flat vector — a "rusher" has high Aggression/Movement, lower Game Sense).
- **Legacy 1–20 maps onto 0–99:** Level `n` → band centered near `5n − 2` (Level 1 ≈ 3, Level 10 ≈ 48, Level 20 ≈ 98). Backward-compatible with frogbot's 1–20 selector; any single attribute can be overridden (for coaching).

---

## 2. Data tiers and measurement confidence

Two independent axes describe how trustworthy an attribute is.

**Data tier — where the signal lives:**

- **[MVD]** — server-side state, ~77 Hz / ~13 ms per frame: position → velocity, **view-angles**, health/armor/weapon, powerups, item & weapon pickups, damage events, frag events, region occupancy. Available for **all ~1,961 players** across the corpus. The workhorse.
- **[POV]** — exact inputs (`forwardmove`/`sidemove`/`upmove`/buttons/angles) from first-person `.qwd` demos. Limited to players with POV demos. Needed only to *clone* movement at high fidelity — **not** to rate.

Because the [MVD] stream carries **position + velocity + view-angle together**, a player's policy is inferable from their trajectory; we don't need keystrokes to rate. POV is a *fidelity tier* for the Movement pillar, not a prerequisite.

Caveat: angle-dependent metrics (Coupling, Reaction, backstab Threat Detection) require the recording to carry view-angles. Modern KTX MVDs do; partial recordings may not — those samples are dropped, not guessed.

**Confidence tier — how solid the estimator is:**

- **A — live or trivial:** already computed by the DeepFrag parser, or a one-line derivation.
- **B — real signal, estimator to be built + validated** against known cases before it rates anyone.
- **C — proxy only:** measurable in principle but noisy; ships with wide bands, validated hardest, or held until a better signal exists.

---

## 3. The six pillars

Each row: Attribute — definition — **[MVD]/[POV]** signal & formula — confidence (A/B/C).

### AIM — "Gunskill"
| Attribute | Definition | Signal & formula | Tier |
|---|---|---|---|
| Tracking | sustained LG | LG hits ÷ attempts **[MVD]** | A |
| Snap | flick acquisition | SG hit% + median Δt(target enters view → first damage) **[MVD]** | B |
| Prediction | leading RL/GL | RL direct-hit ratio / RL% (virtual) **[MVD]** | A |
| Weapon Discipline | right gun for range | weapon-used vs engagement-range fit **[MVD]** | B |

### MOVEMENT — "Athleticism"
| Attribute | Definition | Signal & formula | Tier |
|---|---|---|---|
| Top Speed | air-strafe ceiling | p95 horizontal velocity **[MVD]** | A |
| Air-Strafe Eff. | speed manufactured in air | Δspeed per airborne segment, in-air speed **[MVD]** | A |
| Coupling | aim↔move human-ness (vs "joystick") | corr(view-yaw rate, velocity-heading rate) while airborne **[MVD]** — fidelity ↑ with **[POV]** | B |
| Rocket Jump | mobility tech | self-splash damage event → vertical displacement, RJ height **[MVD]** | B |
| Efficiency | fast clean lines | path length ÷ net displacement; speed kept through turns **[MVD]** | A |

### AWARENESS — "Perception"
| Attribute | Definition | Signal & formula | Tier |
|---|---|---|---|
| Reaction | threat → response | median Δt(enemy enters LOS → angle-snap onset) **[MVD]** (LOS confound → wide band) | B/C |
| Target Switching | re-prioritizing | re-aim latency to a higher-threat target **[MVD]** | B |
| Threat Detection | catching flanks/spawns | spawnfrags-taken **[MVD, live]** + deaths-from-behind (killer angle vs victim facing) **[MVD]** | A/B |
| Map Knowledge | layout/route coverage | route/zone coverage entropy (bot-side competence) | C |

### GAME SENSE — "IQ"
| Attribute | Definition | Signal & formula | Tier |
|---|---|---|---|
| Item Timing | tracking respawn clocks | distribution of \|pickup_time − respawn_due\| per item **[MVD]** (needs per-item/map respawn model) | B |
| Economy | stack/ammo advantage | RA/YA/MH control% + DDR **[MVD, live]** + die-with-stack rate **[MVD]** | A |
| Map Control | holding key zones | time in high-value zones + per-zone frag win-rate **[MVD]** | B |
| Planning | chaining items/plays | predictability of next pickup in the route chain **[MVD]** | C |
| Risk Assessment | force vs retreat correctly | fight-initiation rate split by stack-advantage × outcome **[MVD]** | B |

### TEAMPLAY — "Synergy" (team modes)
| Attribute | Definition | Signal & formula | Tier |
|---|---|---|---|
| Courtesy | take vs leave for mate | pass-over-item rate when mate is closer/weaker **[MVD]** | B |
| Denial | deny enemy vs yield to mate | contest item near an approaching enemy **[MVD]** | B |
| Role Discipline | point/stack/support stability | zone-occupancy stability vs teammates **[MVD]** | C |
| Spacing | not over-stacking, trading | mean inter-teammate distance + refrag latency **[MVD]** | B |
| Sacrifice | body-block, feed weapon | low-stack body between enemy rocket & stacked mate **[MVD]** | C |
| Comms | callouts | synchronized-action proxy / chat prints **[MVD, weak]** | C |

### TEMPERAMENT — "Composure" (the intangibles)
| Attribute | Definition | Signal & formula | Tier |
|---|---|---|---|
| Aggression | baseline fight-seeking | engagement rate + forward positioning + dmg-given posture **[MVD]** | A |
| Consistency | game-to-game variance | cross-game variance of own metrics **[MVD]** | B |
| Composure | holding up when behind | Δ(aim%, decision quality) at low-stack/losing vs baseline **[MVD]** | B |
| Clutch | decisive-moment lift | performance when last-alive / in close games **[MVD]** | B |
| Discipline | not tilting / repeating mistakes | repeated greedy-death signature **[MVD]** | C |
| Risk Appetite | high-variance plays | RJ-for-item / deep-overcommit rate **[MVD]** | B |

**Tally:** ~8 Tier-A (solid now), ~13 Tier-B (buildable + validate), ~6 Tier-C (proxy). Temperament is the pillar most projects skip and the one that makes emulation feel like a *person*; it also houses the deliberate-imperfection dials that make low difficulty believable.

---

## 4. Profiling → rating → dial calibration

The loop that makes ratings and bots the same math:

1. **Measure** each attribute's raw signal across the per-mode population **[MVD]**.
2. **Percentile-map** a player's signal → 0–99 rating (+ confidence band from sample size). This is the public DeepFrag rating.
3. **Calibrate the dial:** in the Komodobots lab, sweep the bot dial across its range and measure the *same metric* on bot MVDs; fit a curve so **"dial set to percentile X" reproduces "measured behaviour at percentile X."** Validated with the existing movement/plausibility harness extended with decision metrics.
4. **Emulate:** load a Card → every attribute drives its calibrated dial → a bot that reproduces the player's measured tendencies.

Calibration is per-attribute and falsifiable: if a dial can't reproduce the human metric in the lab, that attribute is *not yet* emulatable and stays diagnostic.

---

## 5. The decision engine (how Cards drive behaviour)

Frogbot already does **weighted-utility goal scoring** (`goal_entity->fb.desire(self, goal)` with lookahead in `src/bot_botgoals.c`). We generalize it into one decision core reused by 1on1 and teamplay:

```
action* = argmax over candidate actions of  Σ w_i(card) · factor_i(state, map, team)
                                                       − noise(card) − latency(card)
```

The Card modulates four things — this is how skill changes *decisions*, not just aim:

- **which factors are considered** (low Game Sense ignores item-timing & teammate factors entirely),
- **input accuracy** (Item Timing, enemy-stack estimate, Threat Detection get noisier at low rating),
- **noise + reaction latency** (Reaction, Consistency, Temperament),
- **lookahead depth** (Planning extends frogbot's existing `lookahead_time`).

### Teamplay modules (extend existing frogbot scaffolding)
Frogbot already has `GoalLeaveForTeammate()` + `FROGBOT_CHANCE_HELP_TEAMMATE` (a flat 0.25), `HelpTeammate()`/`HELP_TEAMMATE` state, `SameTeam()`, `CouldHurtNearbyTeammate()`, marker `tp_flags`, and a `// FIXME: shout COMING` left unbuilt. Replace the random chance with Card-weighted decisions:

- **Courtesy** → take-vs-leave (extends `GoalLeaveForTeammate`) + COMING call.
- **Denial** → deny enemy low-RL/weapon vs yield to a mate.
- **Sacrifice** → body-block rockets / feed a weapon when low-stack.
- **Role Discipline / Spacing** → who holds point, who carries stack, who runs quad; don't over-stack; refrag timing.

### 1on1 modules (same engine)
The duel beat: `losing stack → reset/run timing` · `winning stack → force/deny` · `key item due → pre-position` · `else → map-control pressure`. Card scales Item Timing knowledge, Planning lookahead, Risk Assessment thresholds vs the real stack math, map-specific play, and Discipline/mistake rate.

---

## 6. Build ladder (R-series; one stage = one PR)

| Stage | Deliverable | Repo | Gate |
|---|---|---|---|
| **R0** | Decision-logging seam: additive cvar-gated `FBDECIDE_*` instrumentation on the goal/target/help layer (observe, don't change) | bot | bot behaviour unchanged; rows parse |
| **R1** | Score the Tier-A attributes from existing DeepFrag/MVD output → first partial Cards | DeepFrag | A-attributes reproduce known leaders |
| **R2** | Build + validate Tier-B estimators (Coupling, Reaction, Item Timing, …) | DeepFrag | each estimator sanity-checked vs known cases |
| **R3** | Per-mode percentile → 0–99 Cards + confidence bands + Cards API | DeepFrag | Card for a known player matches reputation |
| **R4** | Dial calibration loop (profile→dial curves) | both | a dialed bot reproduces the human metric in-lab |
| **R5** | Difficulty presets (Level→archetype) + 1–20↔0–99 mapping | both | level ladder feels monotonic + believable |
| **R6** | Decision modules (teamplay then 1on1) behind calibrated dials | bot | decisions match human-reference rates |

Non-goals (now): full ML behaviour cloning; solving Comms; perfect Tier-C attributes; movement-controller work (Xerial's track).

## Launch / privacy

The public player-facing **ratings UI is gated** until we choose to launch (bragging-rights moment). The Cards API can serve Komodobots before the public surface ships. This doc lives in a public repo — keep the *methodology* general here; keep any exploit-able exact thresholds or anti-gaming details in a private note.

## Open questions

- Per-item respawn-clock model: derive from map entities + observed pickup cadence, or hard-code QW item timers? (Item Timing, R2.)
- LOS/visibility estimator fidelity for Reaction (BSP trace vs proxy).
- Confidence-band rendering on the public rating vs the internal bot Card.

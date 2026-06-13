# mvd_analyzer capability map — our KTX source of truth

> Built 2026-06-13 from a full read of `~/Projects/mvd_analyzer`
> (RELEASE_NOTES, RESULT_SCHEMA, fields.go, API.md, READMEs, git log/branches)
> + live verification against the deployed `deepfrag-mvd-api` (`/v1/version` →
> tag `dev`). **Refresh this whenever Nexus pushes** (new schema bump / branch)
> using the capability-audit prompt. Verify every field claim with a real curl
> before recording — no guessing.

## The two northstars everything is judged against
1. **Better coaching AI** — what insight does this give a player about how to improve?
2. **Smarter / more-human / more-tunable bot** — what frogbot cvar does it drive (transmutability)?

Every capability is judged against both. But each one is really a **triple** — the
same measurement is simultaneously:
- a **coaching insight** (what to fix),
- a **frogbot cvar** (transmutability — set the bot to it),
- a **player rating** (0–99, percentile-anchored vs established players, empirical-
  Bayes shrinkage K≈150 — bragging rights).

A capability that serves none of the three is noise.

---

## 🎖️ Player Rating Catalog — the ~30 sub-dials
Each is a 0–99 rating AND a bot cvar AND a coaching axis. Scoring: percentile vs
established players (≥50 games), shrunk toward population mean (K≈150), map-
normalized where map-dependent. `built` = live in our endpoints; `gap` = data
exists, not yet computed.

**AIM (7)**
| rating | data source | bot cvar | status |
|---|---|---|---|
| **strafe_aim** | `/damage` events × `vel` (dmg landed while \|v\|>320) | aim-while-mobile model | **built** — the "fly in & frag at speed" elite skill; pairs with coupling + reaction |
| lg_accuracy | `/damage` byWeapon lg + time-held | `accuracy` (lg) | built |
| rl_accuracy | `/damage` byWeapon rl, direct hits | `accuracy` (rl) | built |
| **aim_under_fire** | `/damage` `ewep` / given | `prediction_error` | **gap #1 (building now)** |
| **reaction_v2** | `vya` × enemy `pos`, FOV-gated (default 120) → spot-to-crosshair | `reaction_time` | **built** — true target acquisition; v1 (counter-fire from `/damage` ts) also available |
| airshot_aim | rl hits on `hgt`>0 victims | rl-vs-airborne | gap |
| vertical_aim | `view` `vp` tracking | aim pitch | gap |
| tracking_consistency | lg sustained dmg variance | aim steadiness | gap |

**MOVEMENT (5)**
| speed_ceiling | `vel` p95/p99 | air-accel | built |
| bunnyhop_sustain | `vel` %>320 | air-strafe | built |
| coupling | `vel` heading vs `view` yaw | movement-vs-facing tie | built |
| air_control | `hgt` airborne % + efficiency | air control | built |
| rocketjump_usage | `hgt` jumps + self-dmg | `use_rocketjumps` | gap |

**ECONOMY / CONTROL (7)**
| stack_discipline | match_metrics kill vs death stack | risk model | built |
| ra_control | item_control ra share | item desire (ra) | built |
| mh_control | item_control mh share | item desire (mh) | built |
| mega_timing | mh latency | item timing | built |
| restack_speed | restack sec | recovery | built |
| ammo_economy | `sh/nl/rk/cl` | ammo discipline | gap |
| pack_denial | `/backpacks` RL/LG drops taken | greed/denial | gap |

**POWERUP (2)**
| quad_control | `q` intervals + `/items` | powerup desire | gap |
| quad_efficiency | frags-per-quad (`q` × `/frags`) | powerup aggression | gap |

**POSITION / DECISION (5)**
| map_control | `/region-control` | territory | partial |
| route_efficiency | `/loc-graph` transitions | navigation | gap |
| item_cycle_timing | `/items` + `/map-entities` | `lookahead_time` | gap |
| aggression | region + dmg-output cadence | aggression dials | gap |
| spawn_control | `sp` + frag positions | spawn pressure | gap |

**WEAPON / COMBAT (4)**
| weapon_preference | `/weapon-pickups` rl vs lg | `rl_preference`/`lg_preference` | gap |
| weapon_efficiency | `/weapon-pickups` kills-before-death | weapon choice | gap |
| frag_efficiency | `/frags` K/D adjusted | skill scalar | built |
| damage_efficiency | `/damage` given/taken | survivability | **gap #1 (building now)** |

= **30 ratings.** ~10 built, ~20 in the GAPS pipeline below.

---

## 🔴 GAPS — available in the parser, NOT yet used by us (priority by northstar value)

| # | Capability | Endpoint/field | Coaching use | Bot cvar | Why it matters |
|---|---|---|---|---|---|
| 1 | **Per-hit damage + EWep buckets** | `/damage` (`enemyVsSg/Mid/Lg/Rl/Both`, `ewep`, `byWeapon`, attacker→victim `matrix`) | aim-under-fire; how much dmg you land on **armed** enemies (ewep = vs RL/LG holders) vs farming unarmed | `accuracy`, `prediction_error`, per-weapon accuracy | **Biggest miss.** Real combat skill = damage on dangerous opponents, not box-score. Live + verified. |
| 2 | **View PITCH (`vp`)** | `buckets?fields=view` → `vp` | vertical aim, airshot tracking, up/down flick | aim pitch model | We use `vya` (yaw) for coupling; `vp` is untouched — vertical aim is half of aim. |
| 3 | **Reaction time** (derive) | `view` onset vs `/damage`/`frag` timing | how fast you snap to a threat | `reaction_time` | Not built. Combine view-angle change onset with first-damage timestamp. |
| 4 | **Weapon efficiency / preference** | `/weapon-pickups` (kills-before-next-death per slot), `/backpacks` | RL vs LG usage, frags per pickup, pack greed | `lg_preference`, `rl_preference`, `use_rocketjumps` | Direct map to the bot's weapon-choice dials. |
| 5 | **Powerup timing & usage** | `q`/`pe`/`r` intervals; `/items` | quad/pent/ring control + frags-per-quad | powerup desire weights | Powerup rounds decide games; untracked. |
| 6 | **Airgibs (airshots)** | airgib Key Moment (v25/29/30); `hgt` of victim above shooter | RL aim on airborne targets — the spectacular highlight | `rl` aim vs airborne | Great coaching highlight + elite-aim signal. Needs the airgib stream surfaced. |
| 7 | **Decision / routing** | `/loc-graph` (combat-posture transitions), `/map-entities` (teleporters, item layout) | route efficiency, item-cycle pathing, teleporter usage | navigation, item-desire weights, `lookahead_time` | The whole "decision tree by map awareness" northstar for bots. |
| 8 | **Region / map control** | `/region-control` | % of map controlled over time | aggression/territory dials | We use RA/MH control share but not full region control. |
| 9 | **Liquid state (`lq`)** | `buckets?fields=lq` | water/slime/lava fights & damage | env-awareness | Rare but a clean situational dial. |
| 10 | **Telefrags / stomps** | `/damage` `telefrags`/`stomps`, `/events?types=telefrag,stomp` | movement/positional kills | movement aggression | Niche but human-flavor. |

---

## Per-frame field codes (buckets / stream-slice / state-at)
**Always query at `windowMs=13` (native, full data). 50ms+ is lossy aggregation (drops ~3/4 frames).** `pos`/`view`/`hgt`/`lq`/`vel` are **opt-in** — request by code; default query omits them.

| code | columns | units / decode | gated? | coaching use | bot cvar | used? |
|---|---|---|---|---|---|---|
| `pos` | x,y,z (+alive) | qu | no | position, routing | — | ✅ |
| `vel` | vx,vy,vz | qu/sec, central-diff (respawn/teleport-aware) | no | **speed, bunnyhop, heading** | movement/air-strafe | ✅ |
| `view` | vp,vya | angle16, `uint16(v)*360/65536`°, pitch>180=up | no | aim (yaw **& pitch**), coupling | aim model, `prediction_error` | ⚠️ yaw only |
| `hgt` | h | qu above floor (feet=0) | **BSP** | airborne %, airshots | `use_rocketjumps` | ✅ |
| `lq` | lq | `(type<<2)\|level` submersion | **BSP** | water fights | env-awareness | ❌ |
| `h`/`a`/`at` | health/armor/armor-type | hp / points | no | survival, stack | — | ✅ (via match_metrics) |
| `li` | loc index/name | — | (vis) | positioning | navigation | partial |
| `rl`/`lg`/`gl`/`ssg`/`sng` | weapon held (intervals) | bool | no | arsenal | weapon dials | partial |
| `q`/`pe`/`r` | quad/pent/ring (intervals) | bool | no | powerup control | powerup desire | ❌ |
| `sh`/`nl`/`rk`/`cl` | shells/nails/rockets/cells | count | no | ammo economy | — | ❌ |
| `sp`/`d` | spawns/deaths | event ts | no | lifecycle | — | ✅ |

## Endpoints (mvd-api) — all verified live on our `dev` revision
Addressed by **hub gameId** (`gameId:N`; use `hub_game_id`, never `match_id`).

| endpoint | gives | northstar use | used? |
|---|---|---|---|
| `/buckets` `?windowMs=&layout=column&fields=` | per-frame columnar state | everything movement/aim | ✅ |
| `/stream-slice` `?from=&to=&fields=` | raw native-rate track | replay, fine analysis | — |
| `/state-at` `?time=&fields=` | snapshot at T | scrubber | — |
| `/damage` `?players=&weapon=` | **per-hit log, matrix, EWep, telefrag/stomp, scoreboard xcheck** | aim-under-fire, accuracy | ❌ **gap #1** |
| `/frags` | kill log + obituaries | K/D, matchups | ✅ |
| `/weapon-pickups` `?players=&weapon=&source=` | acquisitions + kills-before-death | weapon efficiency/preference | ❌ gap #4 |
| `/backpacks` `?players=&weapon=` | RL/LG drops | pack denial/greed | ❌ |
| `/items` `?items=&players=&kinds=` | pickup/respawn timeline | item economy, powerup timing | partial |
| `/map-entities` `?types=&kinds=` | static layout (spawns/items/teleporters/buttons/doors + bounds) | routing, teleporter links | ❌ gap #7 |
| `/loc-graph` | loc adjacency + combat-posture transitions | decision/movement patterns | ❌ gap #7 |
| `/region-control` `?windowMs=` | territory over time | map control | partial |
| `/events` `?types=&from=&to=&players=&loc=` | merged log (default frag,powerup,streak,spawn,death,weapon,item,chat; opt-in health,armor,loc,damage,telefrag,stomp) | timelines, reaction | partial |
| `/overview` | scoreboard, teams, hasRegionControl, errors | match summary | ✅ |
| `/loc-trails`, `/loc-table`, `/chat`, `/demoinfo`, `/metadata` | trails, loc table, chat, header | misc | — |
| `/v1/maps/{map}/entities`, `/geometry` | per-map static data (geometry OFF — no --maps-dir) | map rendering | entities ✅ / geom ❌ |
| `/v1/version`, `/healthz` | build tag, health | ops | ✅ |

## Schema version history (what each added)
v6 GL+ammo+region-control · v7 streams canonical · v8 int32-ms times · v9–10 visibility-aware loc (BSP PVS) · v11 columnar buckets · v14 static map-entity corpus + map endpoints · v19 corrected scoreboard (kills-based) · **v20 per-hit damage + EWep** · v23 wall-clock timing · **v24–v30 floor height / airgibs / movers / liquids** · **v31 view direction (vp/vya)** · **v32 velocity (vx/vy/vz, central diff)**.

## Deployed status (2026-06-13)
- Built from branch **`dev`** (`/v1/version` tag `dev`), schema **v32**. Revision `deepfrag-mvd-api-00007-jzq`.
- **31 BSPs baked** (chmod a+rX — see [[feedback_file_perms_size_baseline]]); height/liquid live on the competitive pool.
- Open branch `read-dmg` exists but damage (v20) is already merged to main/dev.
- Everything in the endpoint table above returns 200 with real data on our revision.

## What we use TODAY (coverage)
Movement (vel: speed/bhop/coupling) · airborne % (hgt) · economy/stack + RA/MH control (match_metrics) · LG/RL accuracy (player-cards). **Everything in the 🔴 GAPS table is unbuilt** — that's the backlog, ranked by northstar value.

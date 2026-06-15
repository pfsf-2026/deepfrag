# DeepFrag Player Dials & Bot Calibration

**Audience:** anyone working on QuakeWorld bot code (frogbot/KTX tweaks, komodobot, Xerial/Volpe bots) or coaching/rating features.
**Purpose:** explain every metric ("dial") we extract from demos, *why* each exists, what we're trying to accomplish, and exactly how your repo can compute and use them.

Last updated 2026-06-15.

---

## 1. Why this exists — the two northstars

Everything here serves two goals:

1. **Better coaching AI** — tell a human player *specifically* what to improve (e.g. "your air-strafe damage is 13%, elite duelers are 40%+").
2. **A smarter, more human-like, more *tunable* bot** — close the gap between bot behavior and human behavior, and know which knob moves which behavior.

**The discipline:** every dial must map to all three of —
- a **coaching insight** (what a human learns from it),
- a **bot parameter** (which cvar / code path produces it), and
- a **0–99 player rating** (a sub-dial of the overall skill rating).

If a metric can't serve those, we don't build it.

---

## 2. Data foundation (read this before computing anything)

All dials are derived from MVD demo parsing via **`mvd_analyzer`** (`github.com/QW-Group`'s `galfthan/mvd_analyzer`), schema **v33** (positions / velocity / height are `float32` — true sub-unit precision; older int-quantized schemas add noise to coupling/speed).

### 2.1 The 13ms rule (do not violate)
Frame data comes in **buckets**. **Always use `windowMs=13`** — that's the native frame cadence (~77 fps server). `50ms` and higher are *lossy aggregations* that drop ~3 of every 4 frames and destroy turn-rate signals like coupling. Never silently switch window size.

### 2.2 Two ways to get the data

**A. Local file (any `.mvd`, no hub needed)** — use this for bot demos that aren't uploaded to the hub:
```bash
# build once (Go required):
git clone https://github.com/QW-Group/ktx        # (bot source, see §6)
cd mvd_analyzer && go build -o qw-analyze ./mvd-analytics/cmd/qw-analyze

# BSPs are needed for height/liquid dials:
bash scripts/fetch-bsps.sh ./bsps
export MVDA_BSP_DIR=$PWD/bsps

# per-frame data (13ms native):
qw-analyze -view buckets -bucket 13ms -fields pos,view,vel,hgt <demo.mvd>
# everything else (damage events, KTX accuracy, ping, health streams):
qw-analyze -view full <demo.mvd>
```

**B. HTTP (hub-registered demos)** — DeepFrag's deployed parser:
```
GET {MVD_API}/v1/demos/gameId:<N>/buckets?windowMs=13&layout=column&fields=pos,view,vel,hgt,lq
GET {MVD_API}/v1/demos/gameId:<N>/damage
GET {MVD_API}/v1/demos/gameId:<N>/demoinfo
```
Resolves a demo by its hub `gameId`. (Bot practice demos are usually **not** on the hub — use path A for those.)

### 2.3 Field reference
| field | meaning | units |
|---|---|---|
| `pos` | x, y, z | quake units (qu) |
| `vel` | vx, vy, vz — **central-difference, respawn/teleport-aware** (QW doesn't transmit other-player velocity, so this is reconstructed) | qu/s |
| `view` | `[vp, vya]` (view pitch, view yaw) as **angle16** — decode: `deg = raw * 360 / 65536`; pitch > 180 means looking up | degrees |
| `hgt` | height above BSP floor (needs a BSP) — `NoFloor` sentinel is a large negative (~-2.1e9), filter it | qu |
| `lq` | in-liquid flag | bool |

> **Always prefer `vel` over hand-rolled position differencing.** At 13ms, coupling from `vel` ≈ 0.27 vs ≈ 0.02 from position deltas — position differencing is dominated by quantization noise.

Reference implementation of the full dial battery: `api.py :: _metric_card_for_games` (DeepFrag backend), and the standalone local versions `/tmp/coupling.py`, `/tmp/skill_curve.py` referenced in this repo's history.

---

## 3. The dials

For each dial: **what it measures · how it's computed · coaching use · bot knob · human band vs frogbot baseline.**

### 3.1 Coupling — *the bot detector* 🤖
- **What:** how strongly the player's **view yaw** turns *with* their **movement heading** during an air-strafe. Humans gain speed by turning the view in sync with strafe keys (the air-accel technique); bots don't.
- **How:** during air-strafe frames (`|vel| > 320` qu/s), take the turn-rate of heading (`atan2(vy,vx)`) and of view-yaw over a stride K, then Pearson-correlate them. Report **K=1 (13ms)** and **K=4 (~52ms)**.
- **Coaching:** mostly a low-level authenticity marker, not a coaching lever.
- **Bot knob:** **NONE EXISTS.** There is no KTX cvar that ties view-yaw to strafe heading (see §6). This is structural.
- **Bands:** human **0.29–0.47**; **frogbot ~0.03** (flat at every skill 0–20). ~8× separation, dead clean.
- **→ Use this as your primary human-likeness gate.** If your bot's coupling is ~0, it moves like a frogbot regardless of how good its aim is.

### 3.2 Speed
- **What / how:** median & mean horizontal speed `hypot(vx,vy)` over alive frames (gate out teleport spikes `>2500`). KTX also reports `speed.avg`/`speed.max`.
- **Bands:** human median ~340; frogbot ~330–365. *Not* discriminating on its own — bots move at normal speed, they just don't *couple*.

### 3.3 Airborne %
- **What / how:** fraction of alive frames with `hgt > 20` (clearly off the floor).
- **Coaching/bot:** mobility & dodging. **Bot knob:** `movement_skill`, `combatjump_chance` (weak effect).
- **Bands:** human ~29%; frogbot ~22–26%.

### 3.4 Strafe-aim (combat-while-moving)
- **What:** of the damage the player *deals*, how much lands while they're moving fast — the "fly in and frag at speed" skill.
- **How:** join each outgoing damage event (ms) to the player's velocity at that frame; bucket damage by speed band (`<320 / 320–450 / 450–600 / 600+`); report **% of damage dealt above 450 qu/s**.
- **Coaching:** elite duelers deal a large share of damage at speed; weaker players stop to shoot.
- **Bot knob:** `movement_skill`.
- **Bands:** frogbot **~13%** at >450 (87% of its damage is dealt slow/stationary).

### 3.5 Reaction (target acquisition)
- **What:** ms from an enemy entering the player's view to the crosshair landing on them (`<5°` off), confirmed by an actual hit within 1s.
- **How:** clock starts when the angle between view-yaw and direction-to-enemy first drops below the **FOV half-cone**, clock stops at `<5°`. Also report **ping-adjusted** (minus RTT + one tick).
- **FOV note (important):** FOV is a client cvar **not present in the MVD**, so we can't know each player's exact FOV. We gate at **FOV 100 → 50° half-cone** — the floor of the player base (nobody runs below 100). At 50° off-axis *every* real FOV (100–130) already has the enemy on screen, so no one is charged "dead time" for frames they couldn't see. Trust tiers, not sub-30ms gaps.
- **Bot knob:** `reaction_time` (awareness/fire delay), aim `multiplier`/`scale`, `volatility`.
- **Bands:** frogbot acq ~208ms (skill 10); human ping-adjusted 156–233ms.

### 3.6 Airshots (RL/GL on airborne victims)
- **What / how:** RL or GL hits where the **victim's** `hgt > 45` (and below the NoFloor sentinel) at hit time — the spectacular mid-air frag.
- **Coaching:** high-end RL skill. **Bot knob:** `opp_midair_volatility` (the bot's aim penalty against airborne targets).
- **Bands:** frogbot skill-10 ~10% of RL hits are airshots; at skill 20 `opp_midair_volatility → 0` → near-perfect airborne tracking.
- *(GL airshots are tracked but noisy/luck-ish — don't over-weight.)*

### 3.7 Rocket-jump usage
- **What:** real RL self-boosts for mobility (not splash knockback).
- **How:** a self-RL hit (`attacker == victim`, weapon `rl`) **followed by a genuine liftoff** — height peaks `>60` and stays airborne (`>20`) for ≥6 of the next ~15 ticks (~200ms). This filters mere splash bumps.
- **Coaching:** map mobility / control routes. **Bot knob:** `USE_ROCKETJUMPS` (**off in default skill mode** — that's why bots barely RJ).
- **Bands:** frogbot ~0.14/min; strong humans **1–2/min** (e.g. sane 1.78/min).

### 3.8 Weapon accuracy — SG% / LG% / RL% / NG%
- **What / how:** per-weapon hit rate. Most reliable source is **KTX-native stats** (`demoInfo.players[].weapons[w].acc = {attacks, hits}`), not a re-derivation.
- **Coaching:** tracking discipline; which weapons a player is reliable with.
- **Bot knob:** aim error band + volatility (set by skill — see §6).
- **Bands (skill-10 frogbot vs strong human duel opponents):** SG **37% vs 14%**, LG **35% vs 25%**, RL **13% vs 7%**. The frogbot **out-aims strong humans on every hitscan weapon** — its hands are superhuman; only its legs give it away.
- **SG% special note:** in 1on1 it's confounded (saturates/inverts); it's primarily a **4on4 dial**. Your tunable bands for bots: **elite SG 50–60%, mediocre 35–45%**.

### 3.9 Damage efficiency
- **What / how:** `damage_given / damage_taken`.
- **Bands:** frogbot **0.91**; strong humans **1.10** — i.e. humans *beat* the skill-10 bot despite worse aim, purely on movement & positioning.

### 3.10 Economy / item control (duel) & map control (4on4)
- **Duel:** item-control sophistication — controlling RA, then MH, then cycling RA/YA while holding MH. (Zone/region control is **not** a duel concept.)
- **4on4-only:** region/map control %, EWep (aim-under-fire vs *armed* opponents), pack-denial, powerup control. These **saturate or invert in 1on1** — don't apply them there.

### 3.11 Mode bucketing
All cards split by **1on1 / 2on2 / 4on4**. Duel specialists and 4on4 mains differ enormously — even LG%/SG% must break out by mode. Always tag a card with its mode.

**Dropped dials (for the record):** vertical-aim (replaced by airshots); weapon-selection-IQ (LG is also close-range, so it carried no signal).

---

## 4. The frogbot baseline (calibration anchor)

We pulled real KTX frogbot duel demos off the Denver server (filenames `duel_<human>_vs_bro[map]...mvd`; the bot is the player named **`/ bro`**) and ran the full battery. **Confirmed it's a bot via coupling: ~0.03 vs human 0.3+.**

**Skill-10 (mid-tier) frogbot, pooled, duel maps (aerowalk + bravado):**

| dial | frogbot (skill 10) | strong-human band |
|---|---|---|
| coupling @52ms | **0.035** | 0.29–0.47 |
| SG% / LG% / RL% | **37 / 35 / 13** | 14 / 25 / 7 |
| airborne % | **22–26** | ~29 |
| rocket-jumps/min | **0.14** | 1–2 |
| strafe-aim >450 | **13%** | higher |
| reaction acq | **208 ms** | — |
| dmg efficiency | **0.91** | 1.10 |

**The profile in one line: aim demon, robot legs.** Superhuman hitscan, mechanical movement.

---

## 5. The 0–99 scale anchors

| dial | skill 0 (floor) | skill 10 (measured mid) | skill 20 (ceiling, extrapolated) |
|---|---|---|---|
| coupling | ~0.05 | 0.035 | ~0.03–0.05 (flat) |
| SG% | ~25 | 37 | ~52–58 |
| LG% | ~18 | 32 | ~46–52 |
| RL% | ~8 | 11 | ~16–20 |
| reaction acq | ~260ms | 208ms | ~175–190ms |
| airshots | low | ~10% of RL | ~2× (perfect tracking) |
| rocket-jumps/min | ~0.05 | 0.14 | ~0.14 (flat) |

Skill 0–10 are **measured**; skill 20 is **extrapolated from source** (effective aim error ≈ aim-band × volatility, which roughly halves from skill 10→20). We deliberately don't need skill-20 demos — the code is deterministic.

---

## 6. KTX skill: the ground-truth knob table

Source: `KTX/src/bot_botimp.c :: setSkillAttributes(skill, aimskill)` (default mode; `setSkillAttributesEasySkillMode` exists but is an off-by-default cvar). Constants in `include/fb_globals.h`: skill range **0–20**.

**It is not a discrete table — every parameter is a linear interpolation** `value = min + (skill/20) * (max - min)`:

| cvar / param | skill 0 | skill 10 | skill 20 | drives which dial |
|---|---|---|---|---|
| yaw/pitch aim error (min–max°) | 1.5–4.5 | 1.25–3.75 | 1.0–3.0 | accuracy, reaction |
| `initial_volatility` | 3.0 | 2.2 | 1.4 | accuracy (aim jitter) |
| `reaction_time` (s) | 0.75 | 0.53 | 0.30 | reaction / fire delay |
| `opp_midair_volatility` | 1.0 | 0.50 | **0.0** | airshots / airborne tracking |
| `LG_preference` | 0.2 | 0.6 | 1.0 | LG usage |
| `visibility` (FOV) | 90° | 120° | 120° (caps @10) | what it can see |
| `movement_skill` | 0.3 | 0.65 | 1.0 | pathing/dodge competence |
| `combatjump_chance` | 0.03 | 0.07 | 0.10 | airborne % |
| `attack_respawns` | off | off | **on (≥15)** | spawn pressure |
| `dmm4_wiggle` | off | off | **on (>10)** | dmm4 strafe-dodge |
| `USE_ROCKETJUMPS` | *(not set in default mode → stays low)* | | | rocket-jump usage |
| **view↔strafe coupling** | **— none —** | **— none —** | **— none —** | coupling (= permanent bot-tell) |

**Two conclusions that scope all bot work:**
1. **Aim is a solved, fully tunable dial** — just set skill. Skill-20 = superhuman.
2. **Movement is the entire human-likeness frontier.** No cvar produces air-strafe coupling, human-grade rocket-jump mobility, or air control. Making a bot human-like requires **new movement code**, not higher skill — and **coupling will detect any unmodified frogbot at any skill, forever.**

---

## 7. How your repo uses this

### 7.1 Validate human-likeness (the loop)
```
build/tune your bot  →  record a duel demo (vs a human or another bot)
  →  qw-analyze -view buckets -bucket 13ms -fields pos,view,vel,hgt  (+ -view full)
  →  compute the dials (use §3 formulas; api.py::_metric_card_for_games is the reference)
  →  compare to the human bands in §3 / baseline in §4
  →  iterate
```

### 7.2 What to target, in priority order
1. **Coupling → 0.30+** (currently ~0). This is the #1 tell and has no cvar — it's where new movement code earns the most. Get the view to turn *with* the strafe during air-accel.
2. **Rocket-jump mobility → ~1.5/min** (currently ~0.14). Enable + actually use RJ for map movement, not just combat.
3. **Air control / strafe-aim → deal more damage at speed** (currently 13% >450). Fight while moving.
4. **Aim: leave it alone or dial it *down*.** A skill-10 bot already out-aims strong humans. If you want realism, set skill to match the *human* accuracy band (SG ~14, LG ~25, RL ~7 for strong duelers), not max.

### 7.3 Coaching consumers
The same numbers, inverted: tell humans to chase the bot's **tracking discipline** (LG/SG accuracy) while keeping their **movement edge** (coupling, RJ, air control) — the things the bot can't do.

### 7.4 Reproducibility
- Bot demos & scripts live with the DeepFrag maintainer (`~/Downloads/bro_demos/`, `qw-analyze` build, the per-skill curve script).
- Anchors and the skill table are deterministic from the KTX source — re-derive any time from §6.
- Questions / new dial requests → DeepFrag backend (`api.py`), and see `docs/mvd_capability_map.md` for the full parser field/endpoint surface.

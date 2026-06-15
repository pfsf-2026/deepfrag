# FragBot

Our QuakeWorld bot — a **human-likeness-first** frogbot, tuned and tracked against the
DeepFrag dial battery. Kept deliberately separate from Xerial's `komodobots` and Xantam's
4on4 work; it *reuses* their substrate but optimizes a different objective.

## Why FragBot exists (and how it differs)

The frogbot is an **aim demon with robot legs** (see `qw-stats/docs/bot_dials_and_calibration.md`):
superhuman hitscan, mechanical movement. We proved from the KTX source that **no skill level
fixes the movement** — there is no cvar that ties view-yaw to strafe heading, so a frogbot's
`coupling` is ~0 at every skill 0–20, forever.

- **komodo** optimizes *raw bunnyhop speed* (`route_metrics.time_weighted_speed`).
- **Xantam's tracker** reports *KTX combat stats* (frags/eff/damage).
- **FragBot** optimizes and tracks **human-likeness** — the full dial battery: coupling,
  rocket-jump mobility, airborne %, strafe-aim, and accuracy *dialed down* to human bands.

Aim is a solved, tunable dial (just set skill). **Movement is the entire frontier**, and
human-likeness is the objective neither of the other tracks measures. That's FragBot's job.

## What's here

| file | what |
|---|---|
| `dials.py` | the dial battery as a library — `compute_card(demo, player, mode)` + `humanlikeness(card)`. Exact definitions from the validated frogbot baseline. |
| `score_bot.py` | the tracker: demos → qw-analyze → dials → `runs/ledger.json` (deltas vs previous run) → `out/<run_id>.html` evidence table (Xantam-style, our dials). |
| `knobs.json` | the tunable knob schema — every knob mapped to the cvar that sets it, the dial it moves, and the human band to hit. `exists:false` knobs = new movement code FragBot must add. |
| `qw-analyze` | vendored parser binary (v33). Gitignored — rebuild from `~/Projects/mvd_analyzer` if missing. |
| `runs/`, `out/` | ledger + rendered evidence (gitignored). |

## The tuning loop

```
pick a knob set (knobs.json)  →  run FragBot vs frogbot-skill-N on a fixed map
  →  record MVD (komodo harness: scripts/run_frobodm2_lab.py / run_4v4_validation_lab.py)
  →  score_bot.py score --demo <mvd> --mode 1on1 --roster roster.json --label "fragbot-v2 @ fb10"
  →  read the evidence table: did coupling/RJ/strafe-aim move toward the human band?
  →  adjust knobs, iterate
```

**Hold the opponent fixed.** Always pit FragBot against the *same* frogbot skill across
iterations — accuracy dials are confounded by opponent strength (a weak opponent inflates
hit%). Vary *our* knobs, keep the frogbot constant, and the deltas are clean.

### Scoring a run

```bash
export MVDA_BSP_DIR=/path/to/bsps          # height/RJ/airborne dials need BSPs
./score_bot.py score \
  --demo run1.mvd [--demo run2.mvd ...] \  # multiple demos pool into one run card
  --mode 1on1 \                            # 1on1 | 2on2 | 4on4
  --roster roster.json \                   # optional; without it, every bot is tracked
  --label "fragbot-v2 @ frogbot-10" \
  --run-id 20260615T1700Z
```

`roster.json` maps demo player-name → metadata:
```json
{
  "fragbot":  {"label":"fragbot-v2","build":"coupling_gain=0.3","skill":null,"team":"blue","tracked":true},
  "/ bro":    {"label":"frogbot-10","build":"frogbot","skill":10,"team":"red","tracked":true}
}
```

Output: a printed summary, an updated `runs/ledger.json`, and `out/<run_id>.html` — a table
with each bot's dials, a **Human%** score (0 = stock frogbot, 99 = squarely human), and
**deltas vs the previous run of the same label**.

## Human% scoring

`humanlikeness()` scores each dial 0–99 by closeness to the human band, weighted (coupling ×3,
RJ/strafe-aim ×2, the rest ×1), then averages. Bands live in `dials.BANDS`:

| dial | frogbot | human band | direction |
|---|---|---|---|
| coupling@52ms | 0.04 | 0.29–0.47 | up |
| rocketjumps/min | 0.14 | 1.0–2.0 | up |
| strafe-aim >450 | 13% | 25–45% | up |
| airborne % | 24% | 28–34% | up |
| LG% | 35% | 20–30% | **down** (bot over-aims) |
| SG% | 38% | 10–18% | **down** |

A stock frogbot scores ~7. The goal is to move FragBot up *without* making it obviously
worse — the deltas tell you which knob did what.

## Status & gaps (player metrics)

- **1on1: complete** — full battery works today.
- **4on4: movement + combat + accuracy work now** (coupling/speed/airborne/RJ/eff in any mode;
  KTX combat stats free). **Phase-2 gaps:** reaction & airshots assume one opponent (need
  nearest-enemy logic for 4on4); 4on4-tactical dials (map/region control exists in the DeepFrag
  backend; pack-denial / powerup-denial not yet built).

## Substrate (reused, not rebuilt)

- **Movement brain:** `komodobots/experiments/ktx_moveprobe/frogbot-moveprobe.patch` (modes 0–25).
- **Aim brain:** KTX `src/bot_botimp.c::setSkillAttributes` (linear skill/20 table).
- **Sweep harness:** `komodobots/scripts/mode23_sweep.py` + `mode23_sim.py` — fork the LawParams
  to sweep FragBot knobs; score with `score_bot.py` instead of route speed.
- **Match harness:** `komodobots/scripts/run_frobodm2_lab.py` / `run_4v4_validation_lab.py`.

## Reference
- `qw-stats/docs/bot_dials_and_calibration.md` — full dial definitions + frogbot baseline + KTX skill table.
- Validated frogbot baseline: coupling ~0.04, SG 37/LG 35/RL 13 (skill 10 vs strong humans).

# The 4on4 coach — levels, gates, levers, one focus at a time

Agreed with Peter 2026-09-18. Engine: `coaching_fours.py` (pure functions, tests in
`tests/test_coaching_fours.py`). Data: `fours_advanced_stats` (per player per fours game,
pushed from the demo corpus by `tools/mvd_features/push_fours_adv.py`). API:
`GET /api/players/{id}/coaching/fours`; the level also rides on `/api/players/{id}/full`
as `level` and is shown on the profile header. Narration: `coaching_narrate.narrate_fours`.
Metric definitions: [advanced_metrics.md](./advanced_metrics.md).

## Why scaffold

The old coach was a duel coach: every player was compared with three elite anchors, so
everyone got "fight from stack, control red." The corpus says the thing that separates each
level from the next is different at every step, so advice has to be pitched at the level.
Bands of mean above-average +/- per game over the last 40 fours, 38 active players (15+
games in the last year), medians per band:

| level | above avg / g | n | deaths/min | even-fight win | sDDR | RA / g | quads / g | adj K / min | dmg / min |
|---|---|---|---|---|---|---|---|---|---|
| L1 Survive | under −30 | 5 | 3.6 | 34% | 0.76 | 2.5 | 0.7 | 1.2 | 230 |
| L2 Stack | −30 to −10 | 10 | 3.2 | 44% | 1.11 | 5.0 | 1.9 | 1.9 | 360 |
| L3 Fight | −10 to +15 | 12 | 2.8 | 53% | 1.35 | 5.9 | 2.0 | 2.3 | 422 |
| L4 Control | +15 to +40 | 9 | 2.7 | 58% | 1.61 | 7.8 | 3.4 | 2.6 | 489 |
| L5 Carry | +40 and up | 2 | 2.4 | 65% | 2.09 | 8.9 | 4.0 | 3.6 | 647 |

Strongest separator between adjacent bands (median gap in pool SDs): L1→L2 reds and
damage per minute; L2→L3 even-fight win rate and deaths per minute; L3→L4 quads and reds;
L4→L5 adjusted kills, damage and stacked DDR. Levels are public on profiles (Peter,
2026-09-18; can be made private later). A player needs 15 scored fours to be placed.

## Gates

Two metrics per level, judged over the same 40 games. Target = the **promotion line**: the
lever's typical value for a player right at the next band's lower edge, from an OLS fit of the
lever on above-average across the active pool, clamped to be no easier than the player's own
level median and no harder than the next level's median (`pool_baselines` → `levels[L]["line"]`).
Changed 2026-09-19 from "median of the level above": at the median 0 of 36 placed players passed
both gates and half of the players already in the next level failed theirs. At the line, 8-10%
of next-level players fail the gates they crossed, and some players at each level are within
reach. Passing both shows "ready to move up"; the level itself still comes from above-average.

| from | gates |
|---|---|
| L1 | red armors per game, damage per minute |
| L2 | deaths per minute, even-fight win rate |
| L3 | quads per game, red armors per game |
| L4 | adjusted kills per minute, stacked DDR |

## Lever library

Each lever carries direction, the levels it is coached at, a Quake drill and a one-line
why. The coach ranks only the levers active at the player's level plus that level's gates.
Reds and red timing are computed without e1m2 games.

| lever | coached at | note |
|---|---|---|
| deaths per minute | L1–L3 | +1 SD deaths/min within a player = −21 above average per game |
| damage per minute | L1–L2 | |
| red armors per game | L1–L4 | count separates players; timing does not |
| yellow armors per game | L1–L3 | |
| reds on the timer | L3–L5 | |
| stacked damage ratio | L3–L5 | |
| adjusted kills per minute | L3–L5 | |
| even-fight win rate | L2–L5 | the aim-and-movement number; needs 30+ even fights |
| fights started from behind | L2–L4 | 28% at L1 down to 21% at L5; needs 30+ fights started |
| quads per game | L3–L4 | |
| died holding quad, frags per full run | L4–L5 | needs 8+ runs |
| damage per rocket | L4–L5 | |
| chained deaths | display only | see below |
| teamkills per game | display only | see below |

### Tested and demoted (2026-09-18)

- **Chained deaths** are 45% of deaths in a player's wins and 48% in his losses, and once
  deaths per minute is held constant a game with more chaining is not a worse game
  (+3.7 above average per SD, i.e. nothing). In fours deaths come in clusters because of
  the mode, so the share that chains is the same at every level. Deaths per minute is the
  lever; chained stays on the profile as a habit stat. It remains a lever in duels.
- **Teamkills per game rise with level** (1.2 at L1, 3.5 at L5): the stacked players are
  the ones in the pack with rockets. They are charged per event in +/- and shown as a
  habit, never ranked as a lever.

## Baselines, focus, follow-up

- Three baselines per lever: the player's own wins vs losses (needs 5 of each), his level's
  median, and the next level's median (the target). Ranking = how far short of the target
  in pool SDs, plus a quarter of the own win/loss split (capped at 2 SD, because the split
  is partly game state: you start more fights from behind when you are losing), plus 0.5
  for the level's gates.
- Exactly one focus at a time: lever, the player's number, the target, a 10-game window.
  The prescription is stored in `coaching_runs` (mode `4on4`, `levers.focus`). While the
  window is open the focus stays; once 10 games have been played after it was issued the
  next report grades it (hit, improved = moved a quarter of the gap, flat, worse = moved a
  tenth the wrong way) and picks the next focus, which may be the same lever again.
- Game cards: the last 8 games with Game Impact Score, above average, and the two levers
  that most explain the game against the player's own 40-game norm.
- Narration: level-registered (L1–L2 three plain rules, L3 fight selection, L4–L5
  leverage), opens with the previous prescription's result, uses only the numbers given.
  Template fallback when no model key is configured.

## Operating it

```bash
# refresh the corpus (extract → state → items → swing → score → powerups → war → fights), then
SYNC_SECRET=… python tools/mvd_features/push_fours_adv.py            # all rows, or --since 2026-09-01
```

The push is manual until the nightly incremental extraction job exists. The pool medians
are cached 10 minutes per API instance.

## Validation plan

After a month: for every graded prescription, did the player's above average move in the
same direction as the lever? Levers whose "hit" prescriptions do not carry above average
with them get demoted to display-only, the way chained deaths already was.

## Player-facing explainer (2026-09-19)

`/levels` in the app renders the level system from `GET /api/coaching/fours/levels`, which serves
`LEVELS`, `GATES`, the lever library and the live pool medians straight from `coaching_fours.py`,
so the page cannot drift from the engine. Linked from the gates block on the Coach tab.

## Maps are not the same game (2026-09-20)

Peter: schloss and dm3 have one red, dm2 has two, e1m2 none, so raw item counts are not comparable
across maps and the pooled level medians were unfair to one-red maps.

- **Inventory** (`MAP_ITEMS`, counted from demos): dm3 1 RA / 1 YA / 3 MH / LG; dm2 2 RA / 3 YA / 2 MH;
  schloss 1 RA / 2 YA / 2 MH; e1m2 0 RA / 1 YA / 1 GA / 1 MH. Nearly every spawn is taken (47/47 reds
  on dm3, 97/98 on dm2), so a share of the game's takes is a share of the spawns.
- **Item levers are shares.** `ra_share` = your reds / all reds taken in that game (e1m2 excluded),
  `ya_share` likewise; an even split of eight is 12.5%. The red share separates levels as cleanly as
  the count did (L1 5% → L5 17%) and is now the L1 and L3 red gate; `ra_pg` / `ya_pg` stay as display.
  Needs `game_ra/game_ya/game_mh/game_quad` on `fours_advanced_stats` (per-game totals, pushed by the loader).
- **Per-map baselines.** `pool_baselines` also computes medians and promotion lines per map, from each
  player's last 40 games on that map (8-game minimum, 6 players minimum per map). The coach's
  **per-map cards** (`map_cards`) rank the player's levers against that map's line when the map has
  ≥4 players at his level, else the pooled line, and show one "work on this" per map with a
  map-specific note (`MAP_NOTES`) where one exists. The overall focus stays single; the cards are
  the syllabus as it looks on each map. `plays_like` is the level band of the player's per-map
  above-average, for context only.
- Per-map medians and L3 lines are on `/levels` (map picker) and `GET /api/coaching/fours/levels` (`pool.maps`).

## Quad attendance (2026-09-20)

Peter's rule: a player **contested** a quad spawn if he was within ~400 u of the quad at any point
from 10 s before it spawned up to the spawn, including the times he died there before it spawned
("you're attacking quad and die before it spawns"). Single-game analyses use exact demo positions.
The corpus carries a 10-second named-zone proxy (`tools/mvd_features/quad_contest_pass.py` ->
`player_quad`; zones per map in `quad_zones.json` = named spots within 450 u of the quad entity),
which agrees with the exact count to about ±2 spawns a game. Lever `quad_contests_pg` (L3-L4)
is the attendance behind `quads per game`; `quad_conversion` = takes / contests.

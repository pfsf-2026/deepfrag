# MVD feature extraction (AGI / stack-adjusted stats POC, 2026-09-11)

`extract.py <manifest.json> <modes> <workers> [limit]` — for each hub game in the manifest
(id, timestamp, map, mode, server_hostname, demo_sha256): download the demo from
`https://d.quake.world/{sha[:3]}/{sha}.mvd.gz`, run `qw-analyze -view full -include positions`
(galfthan mvd_analyzer, ../qw-analyze relative to the working dir), and write compact rows to
`features.sqlite`:

- `games` — id, ts, map, mode, server, duration, teams, scores
- `players` — per player per game: frags, kills, deaths, KTX-capped damage given/taken,
  stacked/naked damage, spawn deaths (life <= 3s), KTX spawnfrags (victim < 2s), chained deaths
  (< 14s since previous death), multi-kills (2 frags <= 8s), alive seconds, RA seconds, avg
  effective HP, item takes (ra/ya/ga/mh/quad/pent/ring)
- `events` — every damage and frag event with both players' health/armor/type/effective HP,
  RL/LG possession, power-up flag, time since spawn, distance, team frag diff and time left at
  that instant. `dmg` is the raw hit from the demo, `dmg_cap` is KTX's stats-page number
  (health portion capped at the victim's remaining health — KTX combat.c `dmg_dealt`).
- `state10s` — team state every 10s (frag diff, time left, alive, stack sum, power-up, RL/LG
  counts, RA holders) — training rows for the map win-probability model (swing).

`agi_v0.py <full.json>...` — hand scorer for a game: stack-adjusted kills (0.5 / P(win) from
`fight_table_4on4.json`, edge measured at FIRST CONTACT between killer and victim, power-up
state as its own dimension, cap 3; credit = 15% finisher + 85% damage share over the victim's
last 10s), stacked-DDR (damage given while effective HP >= 150 / taken while >= 150), spawn and
chained deaths, multi-kills, item takes, and an AGI v0 composite normalized to the game mean.

`fight_table_4on4.json` — P(win | stack edge, power-up state) fitted on 716 Den/LA fours
(299,745 enemy frags). Duels differ (12/30/50/70/88 with no power-up); fit separately.

Scope of the first corpus: The-Den + la.quake.world fours, plus Mom's Basement and ny.quake.world
duels, all time in the hub (from 2023-09). The sqlite lives in data/ (gitignored).

## Swing (2026-09-11, v0)

`winprob_4on4.json` — logistic map win-probability model fitted on 591k 10-second team-state
samples from 2,443 Den/LA fours (held out by game: log-loss 0.401, AUC 0.894, well calibrated).
Features: frag diff (with time interactions), stack diff (effective HP), alive diff, power-up,
RL/LG counts, RA holders, fraction of time left. At even score with 10 min left: +300 stack
= 0.58, quad = 0.52, +2 RL = 0.58; -20 frags = 0.31 with 10 min left, 0.06 with 1 min left.

`swing_v0.py` — per-player swing, HLTV-style: only kill events move it. A kill = +1 frag diff
plus the victim's remaining stack, weapons and power-up removed (alive count held constant,
respawn is near-instant). Credit 15% finisher + 85% damage share over the victim's last 10s;
victim debited in full. Zero-sum between teams (winner nets ~+100 pp per map; the rest of the
0.5 -> 1.0 move is time drift, unattributed). Report as pp per minute. NOT included: damage
without a kill, item pickups, respawns — those inflate totals and are covered by stacked-DDR
and the items term in AGI. Scripts expect to run from the scratchpad root with f4/ paths;
adjust paths when productionizing.

## Corpus as built 2026-09-11 (`data/mvd_features.sqlite`, 1.25 GB, gitignored)

| | games | span |
|---|---|---|
| 4on4, The-Den + la.quake.world | 2,485 | 2023-09-26 to 2026-09-11 |
| 1on1, The-Den + LA + Mom's Basement + ny.quake.world | 14,028 | 2024-03-11 to 2026-09-11 |

12.26M events, 47,751 player-game rows, 592,652 team-state samples, 12 unparseable games
(aborted matches with <2 players in the streams). Extraction cost: ~0.2 s per duel, ~0.7 s per
fours game with 6 workers, demos streamed from d.quake.world and discarded.

`fight_table_1on1.json` — duel fight odds on 13,417 duels / 609,678 frags: 12/30/50/70/88 by
stack edge with no power-up (fours: 6/20/50/80/94). Power-up cells are thin in duels (n~100).

## Corpus scoring (2026-09-12)

Pipeline order: `extract.py` (games/players/events/state10s) -> `player_state_pass.py` (one row per
player per 10s incl. ammo + zone; `player_shots` rocket/LG efficiency) -> `items_pass.py`
(`item_takes`, `powerups` intervals) -> `swing_corpus.py` (`player_swing`) -> `score_corpus.py`
(`player_agi` per player-game, `player_career` aggregates).

Findings that shaped the model (all held-out by game):
- Alive-count term dropped: it proxies "who just lost the last fight"; removing it costs 0.002 log-loss.
- LG ammo / RL rockets add nothing to win probability (dm3 log-loss 0.4003 base vs 0.4009 with cells);
  LG carriers on dm3 are <15 cells 38% of the time and still the gun is the signal (territory).
- Zone possession (players in zone, yours minus theirs) adds <0.001 once stack + launchers are in
  (`winprob_4on4_zones.json` keeps the per-map fit for reference). The anchor's value flows via stack.
- Per map: dm3 RL +0.19 vs LG +0.13 per launcher; LG only exists on dm3 among Den/LA maps.
- Swing is 57% frag differential (R²); the rest is leverage. Split-half reliability of a player's
  swing/min across games = 0.95 (as stable as frag rate). Swing residual is NEGATIVELY correlated
  with winning (garbage-time discount) -> use AGI for "who played well", swing for "who decided it";
  never sit someone for low swing after a blowout win.

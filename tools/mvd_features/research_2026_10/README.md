# Research scripts and outputs, October 2026 (top NA fours players)

Durable copies of the session scratchpad behind `docs/research_top_na_fours_2026-10.md`.

- `select_games.py` — TOP / FIELD rosters and the 60-game one-second sample.
- `compact.py` — analyzer full view (`full_<gid>.json`, from `qw-analyze -view full -include positions`) →
  `compact_<gid>.json`: 1 s tables, room entries, 100 ms spawn tracks.
- `spawn_defs.py` — real spawn points per TB4 map (clustered from demo positions); `spawn_points.py` —
  survival by spawn point and first room entered under a lock (`spawn_points_out.txt`).
- `spawn_item_timing.py` — first-move outcomes by the key items' timer state at the spawn second
  (`spawn_item_timing_out.txt`). Peter's rule: RL up soon → stay; RL just taken → leave for LG/YA.
- `lock_spawn.py` — the 10 s lock/spawn study on the local sqlite; `lock_breaks_loc.py` — the same with
  item takes before lock breaks split by location (`lock_breaks_loc_out.txt`: which dm3 mega, etc.).
- `research_*.md` — the five agent reports (fight entry, death value, perception, spawn/lock, floods).

Inputs (`compact_*.json`, `full_*.json`, `data/mvd_features.sqlite`) are not in git. Production uses
`spawn_rooms.py` at the repo root, generated from `spawn_points_out.json`.

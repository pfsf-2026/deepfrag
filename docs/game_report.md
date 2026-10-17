# Game Report (coaching page)

*Added 2026-10-17 (Peter: "game reports for players, with key moments, their highlights, their
lowlights, time blocks, even hub links direct to those moments… 2-3 quiz questions… have them type
in what they should have thought at that moment… suggestions around using MM2").*

## What it is
On `/coach/player/{id}` the Overview shows **Last 10 games** (4on4 / 1on1 switch,
`components/CoachRecentGames.vue`). Every fours game has a **Game Report →** link to
`/coach/player/{id}/game/{hub_game_id}` (`pages/coach/player/[id]/game/[gid].vue`):

- summary chips (frags/deaths, share of alive time armed, empty lives, locked spawns and how many
  chained, first-hit share, stacked-without-a-gun deaths, MM2 lines sent vs the team);
- **rewinds** (2–3): a locked spawn that lasted ≥2 s and died inside 14 s where a better first room
  (`spawn_rooms.ROOM_SURVIVAL`) or an item on time existed. The player reads the team's MM2 from the
  20 s before, types what they should have thought and where to go (no voice), then checks: what
  they did, the answer, the MM2 line to send, and a hub link at that second;
- two-minute blocks (frags/deaths, damage dealt/taken bars, major items, seconds locked), each a hub
  link; highlights (powerup runs, streaks, streaks ended, big lives, red/mega/quad under lock) and
  lowlights (died with quad, stacked without a gun, alone into 2+, clusters of empty lives);
- an MM2 section: own count and rate vs teammates.

## Where the data comes from
Nothing is stored from the demo pipeline. `game_report.py` builds a report from the Cloud Run
demo parser (`deepfrag-mvd-api`, `_MVD_API`) in ten calls: overview, the player's full-resolution
stream (`stream-slice … fields=pos,h,a,at,sp,d,rl,lg,q&players=<name>`), 1 s `buckets` for all
players (`pos,h,a,at,rl,lg`), frags, damage, items, weapon-pickups, `chat?types=teamsay` (the MM2
record — MVDs carry team messages), `events?types=powerup,streak`, loc-table. ~20 s, ~3.5 MB.

Hub deep links: `https://hub.quakeworld.nu/games/?gameId={id}&from={s}&to={s}&track={userId}` with
`from/to` = match seconds + `overview.timing.demoOffset/1000` and `track` = `overview.playerUserIDs[name]`.

Spawn points, lock thresholds and first-room survival tables are literals in `spawn_rooms.py`
(from the 60-game one-second study, `docs/research_top_na_fours_2026-10.md` finding 7). The lock
margin here is the per-second one (no RA term).

## API
- `GET /api/players/{id}/recent-games?mode=4on4|1on1&limit=10` — last games with team score, W/L,
  teammates/opponents, `has_report`, `report_available` (4on4 only for now).
- `GET /api/players/{id}/games/{hub_game_id}/report` — builds on first call (slow work outside
  `pg()`), caches in `game_reports (hub_game_id, canonical_id, version, report JSONB)`. `?fresh=1`
  rebuilds. Bump `game_report.VERSION` when the report shape or rules change: old rows are ignored.
- `POST/GET /api/players/{id}/games/{hub_game_id}/report/answers` — rewind answers, per Discord
  user when signed in (`game_report_answers`); the page also keeps them in localStorage.

The Cloudflare `/api/*` proxy caches any 2xx under `/api/players` for two hours, so a report that
failed to build is never cached (non-2xx) and a built one is served from the edge after the first
open.

## Not yet
- Duel reports (lowlight rules differ; the duel coach has its own Deep Analyze).
- Precomputing reports in the ladder tick (`_stats_catchup`); today the first open builds.
- Grading the typed answers; they are only stored.
- Airgibs (not exposed by the parser over HTTP).

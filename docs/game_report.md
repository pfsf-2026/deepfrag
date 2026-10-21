# Game Report (coaching page)

*Added 2026-10-17 (Peter: "game reports for players, with key moments, their highlights, their
lowlights, time blocks, even hub links direct to those moments… 2-3 quiz questions… have them type
in what they should have thought at that moment… suggestions around using MM2").*

## What it is
On `/coach/player/{id}` the Overview shows **Last 10 games** (4on4 / 1on1 switch,
`components/CoachRecentGames.vue`). Every fours game has a **Game Report →** link to
`/coach/player/{id}/game/{hub_game_id}`. The same view (`components/GameReportView.vue`) is public at
**`/r/{hub_game_id}/{player}`** — the share link ("Share this report" copies it). Reports are built only
when someone opens one (no precompute, no model tokens: it is arithmetic on the parsed demo).

- summary chips (frags/deaths, share of alive time armed, empty lives, locked spawns and how many
  chained, first-hit share, stacked-without-a-gun deaths, MM2 lines sent vs the team);
- **rewinds** (up to 6): locked spawns that lasted ≥3 s and died inside 14 s where a better first room
  (`spawn_rooms.ROOM_SURVIVAL`) or an item on time existed, and quad spawns the player was alive and
  within reach for while an enemy took it (or took it on a spawn stack and died). Each shows the key
  items' state at that second (up / in N s / taken N s ago by whom — Peter: the first move is an
  item-timer decision), the team's MM2 just before, and asks what the player should have thought and
  where to go (no voice); then: what they did, the answer (timer read first, then rooms and items), the
  MM2 line to send, a hub link, and the wall-clock time;
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

Wall clock: `match_start_wall_ms = demoStartUnixMs + demoOffset`; every moment carries `wall_ms`, so a
streamer can find it in a VOD with voice comms (Peter streams at twitch.tv/cronus1976).

## Twitch VOD links
`GET /api/players/{id}/games/{gid}/vod?channel=<twitch login>` finds the archive VOD that covers the
match and returns `offset_s` (match start inside the VOD); the page then links each moment to
`<vod url>?t=XhYmZs` (8 s early). It needs a Twitch application (dev.twitch.tv → Your Console →
Register Your Application, category "Analytics Tool", any redirect URL) and its client id + secret in
the Cloud Run env:

```bash
gcloud run services update deepfrag-api --region us-central1 --update-env-vars TWITCH_CLIENT_ID=…,TWITCH_CLIENT_SECRET=…
```

Until then the endpoint answers 503 and the page offers the manual box: paste the VOD link and the
stream start time (from the VOD page), and the links are computed from the match's wall clock.

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
- Precomputing is deliberately off (Peter: only after someone clicks).
- Grading the typed answers; they are only stored.
- Airgibs (not exposed by the parser over HTTP).

## v19 (2026-10-21): stacks as health/armor, the 100 floor, numbers on quad

- Every stack is read as health/armor the way the team overlay shows it (`42/0`, `100/150y`), never one
  number (`stk()` in game_report.py; `stack_hp` on each rewind, `stk` on every teammate/enemy entry).
- `QUAD_MIN_STACK = 100`: with the RL and under 100 effective the line is "restack first, keep the launcher",
  and a teammate under it is not "taking it". `mates_at()` now also runs for enemies (`foes_at`), uses the
  route table for seconds to the item, and drops anyone dying that second (negative health).
- `numbers` on the quad rewind: who is in reach of the room (ours / theirs, with health/armor and rockets),
  who is ready (RL + rockets + 100), the enemy launchers. The decision branches on it: go together (one on
  each entrance), alone against two launchers = hold your entrance and call a second gun, thin = restack,
  no rockets = rockets first and the second entrance.
- When this quad is not ours, "perfect timing" is the line to the next quad (70 s horizon); a step may hold
  a room up to 15 s for its spawn and names the enemy there.
- The coach's read (`REWIND_COACH_SYSTEM`) gets `stack_hp`, `foes_at`, `numbers`, `quad_min` and the rules.

# King of the Hill ladders — rules and engine

Living doc for the KOTH ladders (2v2 teams since June 2026; 1v1 duels added 2026-09-17).
The player-facing rule text lives in the Rules tab of `nuxt/app/pages/ladder/index.vue`; this
file is the engineering source of truth and must change in the same commit as `ladder.py`,
the ladder routes in `api.py`, or the rules JSON on a `ladders` row.

## One engine, many ladders

Every ladder table is keyed by `ladder_id` and a "team" is a roster of `team_size` canonical
ids (`ladder_teams.members`). The 2v2 ladder is `{team_size: 2, mode: '2on2'}`; the 1v1 ladder
is `{team_size: 1, mode: '1on1'}` on the same tables and the same movement code. Nothing is
forked: a duel entry is a one-player team.

| Ladder row field | Meaning |
|---|---|
| `team_size` | players per roster (1, 2 or 4). Roster gates use it. |
| `mode` | hub `match_mode` the auto-resolver searches (`1on1`, `2on2`, `4on4`). Backfilled from `team_size` for old rows. |
| `map_pool` | list shown on the Rules tab (falls back to the 2v2 pool when empty). |
| `rules` | JSON tunables (below). |

Creating the duel ladder (ladder-admin, `SYNC_SECRET` or an `is_admin` Discord user):

```bash
curl -s -X POST https://app.deepfrag.gg/api/admin/ladder/create \
  -H "Authorization: Bearer $SYNC_SECRET" -H "Content-Type: application/json" \
  -d '{"name":"King of the Hill 1v1","season":"Fall 2026","team_size":1,
       "map_pool":["aerowalk","bravado","dm2","dm4","dm6","metron","pocket","skull","ztndm3"],
       "rules":{"best_of":3,"timelimit":10,"forfeit_days":7,"short_window_days":3,
                "loss_cooldown_days":3,"min_offer_hours":48,"auto_resolve":true,"auto_forfeit":false}}'
```

Then `POST /api/admin/ladder/{id}/open {"open": true}` once seeded. The pool above is the
Fall 2026 1v1 pool (9 maps, alphabetical, settled 2026-09-24: the poll's top 7 plus metron
and pocket). Change a live ladder's pool without a deploy: `POST /api/admin/ladder/{id}/maps
{"map_pool": [...]}` (lowercase names, order kept, min 3). The rules tab derives the Bo3
toss sequence from the pool size (9 maps → B, A, B, A, B, A).

## Discord channels per ladder (2026-09-24)

Every ladder post goes through `notify.send()`, which picks the webhook from a per-request
route: handlers call `api._notify_route(cur, ladder_id=… | challenge_id=… | team_id=…)` once
they know the ladder, and the tick sets it per row. `notify.ROUTES` maps a ladder mode to an
env var: `1on1` → `DISCORD_WEBHOOK_URL_1V1` (the KOTH 1v1 channel). 1v1 posts never fall
back to the 2v2 channel: while that var is unset they are dropped. Other modes use
`DISCORD_WEBHOOK_URL` (the 2v2 channel). Set the 1v1 webhook on
Cloud Run (env vars survive Cloud Build deploys):
`gcloud run services update deepfrag-api --region us-central1 --project deepfrag-prod --update-env-vars DISCORD_WEBHOOK_URL_1V1='<webhook url>'`.
The daily digest posts one block per active ladder to that ladder's channel.

## Sign-in links (log in without Discord, 2026-09-27)

For players who won't use Discord (Awup was the first). An admin picks the player on
`/ladder/admin` → "Sign-in link" → the API issues `https://app.deepfrag.gg/login/link#t=<token>`
(shown once; the token rides in the URL fragment so it never hits the server or Cloudflare's
path normaliser). Opening it POSTs `/api/auth/link` → same session JWT as the Discord flow,
bound to the synthetic user `link:<canonical_id>` (already linked + verified) → bounce to
`/ladder?l=1v1`. Links last 180 days, are reusable across devices, and are revoked per player
(`POST /api/admin/players/{id}/login-link/revoke`; list at `GET /api/admin/login-links`). Only
the SHA-256 of a token is stored (`login_links`). Sessions minted from a revoked link expire
on their own (30 days). Endpoints take ladder-admin auth (SYNC_SECRET or an is_admin Discord user).

## 1v1 rule set (2026-09-28)

`rung_jump` 3 (challenge 1-3 rungs up; the 2v2 ladder stays at 2) and `forfeit_days` 5: a
challenge must be scheduled AND played within 5 days of issuance without an admin. The API
drops offered times past the deadline (opening offer and re-posts) and the scheduler calendar
stops at the window. Longer needs an admin: `POST /api/admin/ladder/challenge/{id}/extend
{"days": N}` (1-14, adds to the deadline, posts "Extension approved" to the channel) — the
Extend button on `/ladder/admin`. The rules tab derives its numbers from `ladder.rules`.
Discord posts: `notify.send()` uses `wait=true` and keeps the message id
(`notify.last_message_id()`, returned by `/api/admin/notify`); `POST /api/admin/notify/edit`
edits an earlier post.

## Rules JSON (allowlist in `api.py` `admin_ladder_rules`)

| key | default | effect |
|---|---|---|
| `best_of` | 3 | series length; the resolver walks games chronologically to first-to-`(best_of+1)//2` |
| `timelimit` | 10 | minutes per map (display only) |
| `rung_jump` | 2 | how many rungs up a challenge may reach (UI enforces 1–2) |
| `forfeit_days` | 7 | play-by window when the offer covers ≥2 distinct evenings |
| `short_window_days` | 3 | window for a 1-evening offer; expiry = no movement |
| `min_offer_hours` | 48 | an offer must have been on the table this long before the deadline for a forfeit to stand (challenge 71 post-mortem, 2026-09-06) |
| `loss_cooldown_days` | 3 | loser can't issue challenges; winning a defence lifts it |
| `auto_resolve` | true | tick records a series when every decisive game matched all `team_size` players per side |
| `auto_forfeit` | false | tick applies forfeits unattended (otherwise admins are notified) |
| `open` | false | players may challenge; set via `/open` |

## Movement (both ladders)

- Challenge 1 or 2 rungs up. A win at either distance is a straight two-team swap; nothing in
  between moves.
- Forfeit: the challenged side drops by the challenge span, swapping with the side below
  (normally the challenger). `apply_forfeit` clamps to the bottom when there are not enough
  rungs below.
- New entries land at the bottom (`place_new_team`). Archiving compacts every rung below up one.
- King of the Hill = rung 1; weeks held come from the newest `ladder_movements` row with
  `to_rung = 1`.

## Walkovers (2026-10-09)

A walkover is a result where one side could not or would not play. Peter's rule: it must never read
as a loss or a 2-0 defeat; it counts simply as a walkover.

- `ladder_matches.walkover` (BOOLEAN) marks the row; score and maps are empty, `hub_game_ids` is `[]`.
- Movement is the normal result movement (challenger wins by walkover → the two-team swap; challenged
  wins → ranks unchanged, challenger takes the loss cooldown). The 5-day forfeit (`/forfeit`) still drops
  the challenged team by the challenge span, and now also writes a walkover match row for the challenger.
- Records: `match_w` / `match_l` exclude walkovers; `wo_w` / `wo_l` count them (team list, team page). The
  site shows **W/O** in place of a score (ladder results, Stats tab, team page, match modal) and leaves
  walkovers out of the form string on the match preview.
- Recording one: `POST /api/admin/ladder/challenge/{id}/result` with `{"winner_id": N, "walkover": true}`,
  or `POST /api/admin/ladder/challenge/{id}/walkover` with `{"winner_id": N}` (also closes an old forfeit
  that has no match row). `POST /api/admin/ladder/match/{id}/walkover` turns a match entered as 2-0 into
  a walkover after the fact. The Discord post reads "**A** def. **B** — **walkover**".

## Result matching

`_detect_bo3` (auto-resolve, admin candidate view) and `_try_report_games` (player reports)
query `matches JOIN players` for games in the ladder's `mode` where at least one rostered
player from each side appears. The auto-resolve search window (`ladder.search_window`) runs
from the moment the challenge was issued to 7 days after the scheduled slot, or the deadline if
later (rule set 2026-09-18 after WoD/Habs played challenge 78 three days before its slot and
the old slot-centred window never saw it); never-scheduled challenges search creation to
deadline. The matcher then sums frags per roster and walks the games in time order to the
first side with `wins_needed` map wins. A game is `full` only when `team_size` distinct
rostered players matched on each side; auto-resolve refuses anything less and posts a review
notice. On the 1v1 ladder that means both players' in-game names must canonicalise to their
profile ids.

## Seeding the 1v1 ladder

Players join from the ladder page (`?l=1v1`) with one click (2026-09-23, Peter: "if I'm
logged in, register me immediately"). The entry IS the linked profile: name = the profile's
display name (already validated by the profile claim), no tag, logo, or teammate, and no
approval step. The API registers the player ACTIVE at the bottom rung right away, so the
board fills in sign-up order; admins drag-reorder the rungs from `/ladder/admin` before
opening. Suggested initial order: the 1on1 rating list for active NA players, top rung to
bottom. The 2v2 flow is unchanged (form + pending approval). Because a duel entry has
nothing to edit, the ✎ button and the topbar "Team settings" item are hidden for it
(`/api/auth/me` `team` = a 2v2+ team only; `teams` still lists every entry).

Launch flow (Peter, 2026-09-23): a **3-day sign-up window**, then admins seed, then
challenges open; anyone who joins after seeding starts at the bottom rung. The window end
lives in `rules.signup_until` (ISO UTC; set via `POST /api/admin/ladder/{id}/rules
{"patch": {"signup_until": "..."}}`, null clears it). While the ladder is closed the board
banner reads "Sign-ups are open — join by <day>" during the window and "Seeding the ladder"
after it; without `signup_until` it falls back to the "opens at 10 seeded" banner. Fall 2026
1v1: window through Sat Sep 26 (23:59 ET, `2026-09-27T03:59:59Z`), seed Sun Sep 27, then `/open`.

## Not yet done (2026-09-17)

- Discord templates still say "team" in a few places (`notify.py`) and link to `/ladder`
  without the `?l=` slug.
- `LadderStats` per-team aggregates work for one-player teams but the copy says "team".
- `/api/admin/ladder/movements` defaults to `ladder_id=1`.

## Scheduling a time both sides already agreed on (2026-09-30)

Players usually settle a time in DMs first, so the scheduler lets either side set it directly:

- **Creating a challenge:** "Schedule now" issues it already scheduled (`agreed_at` on create).
- **Open challenge:** the scheduler shows "Already agreed on a time with X?" → pick date + ET time → scheduled on the spot.
- **Scheduled match → Reschedule:** opens the same picker, prefilled with the current time. "Move match · confirmed" moves it in one step. "Take it off the schedule and re-pick" is the old clear-and-renegotiate path, kept for when there is no new time yet.

All three go through `POST /api/ladder/challenge/{id}/reschedule` with `{agreed_at}` (no body = clear and re-pick). The time must be in the future and inside the play-by deadline; past the deadline needs an admin extension first. Either side can set it (trust-based, same as create); the Discord post pings both, so a wrong time gets caught.

Discord wording rules (Peter, 2026-09-30 — the old posts confused players about which time was live):
- One time per post. A moved match says `New time: … (was …)`. A pre-agreed challenge does not also print the play-by deadline.
- A re-pick after a reschedule says "offered new times — nothing is locked in yet"; it never re-announces "X challenged Y".
- Deadlines print in ET like every other time, never as a bare ISO date.
- The scheduled post starts with "✅ Scheduled:".
- **Keep them short (Peter, 2026-10-02: "way too verbose").** One header line. Offered times print one line per evening in ET via `notify.fmt_slots` (12am–6am rides with the night before; 3+ half-hour slots collapse to a range), never one bullet per slot. No trailing instructions, no "both players are free again" filler. Second mentions use `notify._name(label)` so nobody is pinged twice. Deadlines are a day ("play by Sat Oct 3"), not a minute.

## Schedule tab layout (2026-10-02)

Upcoming matches first, soonest to latest, grouped by day ("Today · Fri, Oct 2") with a start-in chip inside 24h. Scheduled matches more than 2h past their time drop to an "Awaiting result" group at the bottom of that card. Open challenges (no time yet) sit in their own card below, soonest deadline first, each saying who owes the pick. "Your match" with its action buttons lives in the side rail, and moves to the top on phones when you have one.

## Stats tab on the 1v1 ladder (2026-10-05)

A duel ladder has no teams, so its Stats tab has two views instead of three: **Advanced Metrics** (opens
first) and **Standard Metrics** (the end-of-match numbers, without the team-kill and quad columns). The
2v2 ladder is unchanged (Team Stats / Player Stats / Enhanced).

Advanced Metrics is `LadderDuelStats.vue` on `GET /api/ladder/{id}/duel-stats`: one row per active ladder
player, in ladder order. Columns, in Peter's wording (2026-10-05): Even, Stacked, Dmg/min | Behind |
RA %, RA Timing, Mega Timing, Mega Control, Mega % | Top 10% Speed, Avg Speed. No +/-. Definitions and
the evidence behind each one: `docs/advanced_metrics.md`; the player-facing glossary is
`/ladder/advanced-guide` (one anchor per term).

- **Games.** "Ladder Matches" (default whenever the ladder has scored maps) counts only maps played in
  ladder matches. "Last 90 Days Overall" (`DUEL_LENS_DAYS`) counts every duel a ladder player finished.
- **Opponent rating.** A second switch cuts either set by the rating gap going into each game (global
  1on1 mu before the game, from `rating_history`): All / Evenly matched (within `DUEL_OPP_GAP` = 200) /
  Higher rated (opponent 200+ above) / Lower rated (200+ below). 200 is measured, not picked: inside it
  the higher-rated player wins 60%; at 200-250, 74%; 300-400, 82%; 500+, 95%. A game with no rating row
  yet counts under All only.
- **Timing columns** use one window, `ITEM_ON_TIME_MS` = 3 s after the item comes back, opening item
  excluded. **Avg Speed** is KTX's end-of-match average (`players.player_speed_avg`); **Top 10% Speed**
  is `speed_p90` from the demo track.
- **Tooltips.** Each header carries an (i); hovering the header shows the definition after 0.25 s
  (`TIP_DELAY`), tapping the (i) shows it at once without sorting. Leader cards link to their glossary
  term, not to the player.
- **Floors.** A number shows a dash until it has enough behind it (5 decided even fights, 5 megas,
  30 hops, ...). A row with under 5 games (2 in the ladder set) is dimmed and cannot lead a column or
  appear in the leader cards.
- **Staying current.** The ladder tick (`_stats_catchup`) scores up to three new duels and three
  movement games every five minutes, newest first. A ladder match shows up in the tab a few minutes
  after its games are in the database.
- **Tale of the tape.** On a 1v1 match preview (`/ladder/match/{challenge}`) the tape is the two
  players' rows from the 90-day set, all opponents.

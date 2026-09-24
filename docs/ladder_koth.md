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
env var: `1on1` → `DISCORD_WEBHOOK_URL_1V1` (the KOTH 1v1 channel); anything else, or an
unset var, falls back to `DISCORD_WEBHOOK_URL` (the 2v2 channel). Set the 1v1 webhook on
Cloud Run (env vars survive Cloud Build deploys):
`gcloud run services update deepfrag-api --region us-central1 --project deepfrag-prod --update-env-vars DISCORD_WEBHOOK_URL_1V1='<webhook url>'`.
The daily digest posts one block per active ladder to that ladder's channel.

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

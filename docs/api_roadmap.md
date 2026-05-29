---
title: DeepFrag API Surface — Audit & Roadmap
---

# DeepFrag API — Surface Audit & Roadmap

Living tracker for the HTTP API: what's shipped, what we *could* build from
data we already have, and known quality/security debt. Update the checkboxes
as items land. For consumer-facing usage docs see [api.md](./api.md).

_Last full audit: 2026-05-29 (deployed `version 0.1`, 24 public paths)._

---

## Part A — Shipped (public read surface)

All `GET`, all edge-cached via the Cloudflare Pages Function except where
noted. Consumer docs in [api.md](./api.md).

**Rankings**
- [x] `/api/rankings` — global leaderboard
- [x] `/api/rankings/maps/{map}` — per-map leaderboard
- [x] `/api/maps` — maps with rated-player counts

**Players**
- [x] `/api/players` — full player index *(added 2026-05-29; replaced stale `/profiles/index.json`)*
- [x] `/api/players/{cid}` — lite profile
- [x] `/api/players/{cid}/full` — complete profile + windows + recent matches
- [x] `/api/players/{cid}/maps` — per-map breakdown
- [x] `/api/players/{cid}/maps/{map}/opponents` — top opponents on a map *(not cached)*
- [x] `/api/players/{cid}/rating-history` — rating trajectory
- [x] `/api/search` — name → canonical_id

**H2H & stats**
- [x] `/api/h2h` — head-to-head + per-map + win prediction
- [x] `/api/stats/leaderboards` — mechanical-skill leaderboards
- [x] `/api/stats/maps` — active maps

**Servers**
- [x] `/api/servers` — server list
- [x] `/api/servers/{host}/detail` — server deep-dive

**Map annotations (annotator)**
- [x] `/api/maps/annotations` — index (counts + lock status)
- [x] `/api/maps/{map}/annotations` — full payload (geometry + spawns + teles)
- [x] `PUT /api/maps/{map}/annotations` — admin write (409 if locked)
- [x] `POST /api/admin/maps/{map}/lock` — admin lock toggle
- [x] `POST /api/admin/maps/seed-geometry` — idempotent table-create + geometry seed

**Meta**
- [x] `/api/health`
- [x] `/api/divisions/avg-stats` — per-division avg + radar scales

**Admin (bearer-gated, not public)**
- [x] `/api/admin/status`, `/players/{cid}`, `/deploys`, `/activity`, `/matches/by-region`
- [x] `POST /api/admin/scheduler/{action}`, `/sync`, `/sync-live`, `/rerate`

---

## Part B — Could build (data exists, no schema work)

Ordered roughly by value. Each is backed by existing tables/columns.

- [ ] **`GET /api/matches/{id}`** — single match detail (all players, stats,
  frags, demo URL, server). **Highest leverage.** Unlocks linkable match
  pages, demo download, and lets the 4on4 sandbox tools embed match
  deep-dives in the main UI instead of `/tmp/*.html`.
- [ ] **`GET /api/mvd/{match_id}/buckets`** (+ `/frags`, `/items`, etc.) —
  thin proxy to the `deepfrag-mvd-api` Cloud Run service so the 500ms
  time-series is reachable from the main UI without exposing the raw mvd-api
  hostname. Enables in-app spawn/stack playback.
- [ ] `GET /api/players/{cid}/matches?days=90&limit=100` — paginated match
  history (today capped at 50 inside `/full`).
- [ ] `GET /api/servers/{host}/matches?days=90` — per-server match feed.
- [ ] `GET /api/h2h/{p1}/{p2}/weapons` — weapon-specific H2H breakdown
  (LG/RL/SG dominance per matchup).
- [ ] `GET /api/players/{cid}/region-history` — geolocation drift over time
  (migration / alt-account signal).
- [ ] `GET /api/divisions/{div}/roster?mode=1on1` — "all Div 1 players"
  without client-side tier computation.
- [ ] `GET /api/h2h/{p1}/{p2}/trajectories` — side-by-side rating chart
  payload (both players' histories pre-aligned).
- [ ] `GET /api/servers/{host}/uptime?days=365` — reliability graph
  *(requires logging probe history first — minor schema add)*.
- [ ] Expose `demo_url` + `demo_sha256` on match detail — linkable/downloadable demos.

---

## Part C — Quality & security debt

**Medium**
- [ ] **Async admin sync + status endpoint.** `/api/admin/sync` and `/rerate`
  block the request 5–20 min with no polling; if the connection drops the
  admin UI has no feedback. Add `GET /api/admin/sync/status`
  `{state, started_at, last_log_line}`.
- [ ] **Split the admin token.** A single `SYNC_SECRET` is all-powerful
  (pause / sync / rerate / read admin profiles), with no rotation, scoping,
  or audit log. Minimum: separate read-token vs write-token; ideally
  per-action scopes + an audit table.

**Low**
- [ ] Pagination on `/api/rankings` and `/api/servers` (both capped at 2000;
  fine until ~5k+ players, then payloads bloat — add cursor/offset).
- [ ] Align response shapes between `/api/players/{cid}` (lite) and `/full`
  so clients share one unpacking path.
- [ ] `/api/h2h` internal inconsistency: top-level `overall_predict_win_a/b`
  but per-map `predict_win_a/b` (no prefix). Cosmetic; trips up clients.
- [ ] Cache `_get_tier_cutoffs()` — recomputed per request across 5+
  endpoints (cheap query, but redundant; an N+1 across per-map ranking loops).
- [ ] No read-side rate limiting (relies on Cloudflare DDoS + 2h edge cache).
- [ ] `/api/servers/{host}/detail` fires 9 separate queries; could batch.

---

## Top recommendations

1. **Ship `GET /api/matches/{id}`** — most downstream features per unit of
   effort (linkable matches, demo download, sandbox embedding), no schema work.
2. **Async admin sync + `/sync/status`** — closes the recurring "did the sync
   actually finish?" UX hole.

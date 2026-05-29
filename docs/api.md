---
title: DeepFrag Public API Reference
---

# DeepFrag Public API

The DeepFrag backend is a read-only public JSON API over QuakeWorld match
data (1on1 ratings, per-map ratings, head-to-head, mechanical-skill
leaderboards, servers). Anyone can call it — **no API key required** for the
read endpoints documented here.

> **Interactive docs:** the FastAPI app also serves auto-generated Swagger UI
> at [`/docs`](https://deepfrag-api-751658372467.us-central1.run.app/docs) and
> the raw schema at
> [`/openapi.json`](https://deepfrag-api-751658372467.us-central1.run.app/openapi.json).
> Those list *every* route including admin ones; this page documents only the
> stable, public, read-only surface meant for outside consumers.

## Base URLs

| Use case | Base URL |
|---|---|
| Direct (origin) | `https://deepfrag-api-751658372467.us-central1.run.app` |
| Via deepfrag.pages.dev (edge-cached) | `https://deepfrag.pages.dev/api/...` |

Prefer the `deepfrag.pages.dev/api/` form for browser apps — a Cloudflare
Pages Function caches every public GET at the edge (2-hour TTL between data
syncs), so you get global low-latency responses and we get protected origin
load. The two are byte-identical otherwise.

## Conventions

- **Method:** all public endpoints are `GET`.
- **Format:** JSON. Responses ≥ 1 KB are gzip-compressed.
- **CORS:** open (`*`) — callable from any browser origin.
- **`mode`:** one of `1on1`, `2on2`, `4on4`. Only `1on1` is fully populated
  today; team modes return empty sets until those rating pipelines ship.
- **`canonical_id`:** the stable lowercase identity key for a player across
  all aliases. Resolve a display name → `canonical_id` with `/api/search`.
- **Rating scale:** μ (mean skill) and σ (uncertainty) on a ~1500-centered
  scale. The publicly-sorted number is **`conservative` = μ − 3σ**. Ratings
  use OpenSkill (Weng-Lin); see [1on1_methodology.md](./1on1_methodology.md).
- **Freshness:** data refreshes every 2 hours. `last_seen` / `match_date`
  fields tell you how current a given record is.

---

## Rankings

### `GET /api/rankings`
Global leaderboard for a mode.

| Param | Type | Default | Notes |
|---|---|---|---|
| `mode` | string | `1on1` | `1on1` \| `2on2` \| `4on4` |
| `min_matches` | int | `10` | hide players with fewer rated matches (5–10000) |
| `active` | bool | `false` | only players active recently |
| `region` | string | – | filter by region code (e.g. `EU`, `NA`) |
| `limit` | int | `500` | max rows (1–2000) |

```bash
curl "https://deepfrag.pages.dev/api/rankings?mode=1on1&min_matches=20&limit=50"
```

### `GET /api/rankings/maps/{map}`
Per-map leaderboard.

| Param | Type | Default |
|---|---|---|
| `mode` | string | `1on1` |
| `min_matches` | int | `5` |
| `limit` | int | `500` |

```bash
curl "https://deepfrag.pages.dev/api/rankings/maps/dm2?mode=1on1"
```

### `GET /api/maps`
List maps that have ratings in a mode, with rated-player counts (powers the
map dropdown).

| Param | Type | Default |
|---|---|---|
| `mode` | string | `1on1` |
| `min_players` | int | `5` |

---

## Map annotations (spawns + teleports)

Spawn points and teleport pairs per map, plus cached loc/triangle geometry —
backs the spawn/tele annotator. Reads are public; writes are admin-only.

### `GET /api/maps/annotations`
Index of every map with cached geometry: spawn/tele counts, loc count, lock
status. Powers the annotator's map picker.

### `GET /api/maps/{map}/annotations`
Full payload for one map: `{map, spawns, teles, geometry, locked, updated_by,
updated_at}`. `geometry` is `{bounds, locs:[{name,z,tris}]}`; `spawns` is
`[{x,y,z,loc}]`; `teles` is `[{from:{x,y,z,loc}, to:{...}, bidir}]`.

### `PUT /api/maps/{map}/annotations` *(admin)*
Replace a map's spawns + teles. Bearer-auth; returns `409` if the map is
`locked`. Body: `{spawns:[...], teles:[...]}`.

### `POST /api/admin/maps/{map}/lock?locked=true|false` *(admin)*
Set/clear the lock flag. Locked maps reject `PUT` (read-only).

---

## Player configs + map

Hardware/config profiles (sens, mouse, binds, geo), seeded from the community
config sheet and per-user editable (admin-gated for now).

### `GET /api/players/{id}/config`
A player's config profile: `{canonical_id, nick, nationality, lat, lon, config,
source, updated_at}`. `config` is a free-form bag (sens_cm360, dpi, grip, hand,
movement, mouse, mousepad, fov, resolution, refresh, binds, …). Returns
`{config: null}` if none on file.

### `PUT /api/players/{id}/config` *(admin)*
Edit a config profile. Body: `{config:{...}, nationality?, lat?, lon?}`.
Marks `source='admin'` so the sheet re-seed won't clobber it.

### `GET /api/players/map`
All players with geo data (precise lat/lon where known, else nationality for
country-level placement) — powers the player map.

### `POST /api/admin/configs/seed-from-sheet` *(admin)*
Idempotent table-create + import of the community config sheet (~104 players).
Never clobbers user/admin-edited rows.

---

## Players

### `GET /api/players`
Full player index — every canonical player meeting a lifetime **or** recent
activity threshold. This is the dataset behind the "All Players" browse page.

| Param | Type | Default | Notes |
|---|---|---|---|
| `threshold` | int | `10` | min lifetime matches |
| `recent_min` | int | `5` | OR: min matches in the recent window |
| `recent_window_days` | int | `90` | size of that window |

```json
{
  "generated_at": "2026-05-29T...",
  "count": 1841,
  "players": [
    {"canonical_id": "cronus", "display": "Cronus", "matches": 6818,
     "first_seen": "2024-04-11T...", "last_seen": "2026-05-28T..."}
  ]
}
```

### `GET /api/search`
Resolve a display name (or partial) to canonical players.

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | **required** | 1–64 chars, case-insensitive substring |
| `limit` | int | `20` | 1–100 |

```bash
curl "https://deepfrag.pages.dev/api/search?q=cron&limit=5"
```

### `GET /api/players/{canonical_id}`
Lightweight profile: identity, region, per-mode ratings.

### `GET /api/players/{canonical_id}/full`
Complete profile — windowed stat blocks + recent matches. Heavier; use the
lite endpoint when you only need ratings.

| Param | Type | Default | Notes |
|---|---|---|---|
| `window` | string | `all` | `7` \| `30` \| `90` \| `365` \| `all` (days) |

### `GET /api/players/{canonical_id}/maps`
Per-map W/L + per-map rating breakdown.

| Param | Type | Default |
|---|---|---|
| `min_matches` | int | `5` |

### `GET /api/players/{canonical_id}/maps/{map}/opponents`
Top opponents faced on a specific map.

| Param | Type | Default |
|---|---|---|
| `limit` | int | `8` |

### `GET /api/players/{canonical_id}/rating-history`
Match-by-match rating trajectory (for charts).

| Param | Type | Default | Notes |
|---|---|---|---|
| `mode` | string | `1on1` | |
| `map` | string | `""` | empty = overall; else per-map history |
| `limit` | int | `20000` | 1–50000 |

---

## Head-to-head & stats

### `GET /api/h2h`
Head-to-head record + per-map breakdown + win prediction between two players.

| Param | Type | Default | Notes |
|---|---|---|---|
| `p1` | string | **required** | canonical_id |
| `p2` | string | **required** | canonical_id |
| `mode` | string | `1on1` | |
| `recent_limit` | int | – | recent matches to include |
| `since_days` | int | – | restrict to a recent window |

```bash
curl "https://deepfrag.pages.dev/api/h2h?p1=cronus&p2=milton&mode=1on1"
```

### `GET /api/stats/leaderboards`
Mechanical-skill leaderboards (LG%, RL%, DDR, item control) — *how* you play,
separate from rating (*who* you beat).

| Param | Type | Default |
|---|---|---|
| `mode` | string | `1on1` |
| `map` | string | `all` |
| `region` | string | – |
| `min_matches` | int | `100` |
| `top` | int | `50` (1–100) |

### `GET /api/stats/maps`
Maps with enough activity to appear in the stats dropdown.

| Param | Type | Default |
|---|---|---|
| `mode` | string | `1on1` |
| `min_games` | int | `1` |

### `GET /api/divisions/avg-stats`
Per-division average stats + radar-chart scales (reference rings on profiles).

| Param | Type | Default |
|---|---|---|
| `mode` | string | `1on1` |
| `since_days` | int | – |

---

## Servers

### `GET /api/servers`
Server list with aggregated match/player counts.

| Param | Type | Default |
|---|---|---|
| `region` | string | – |
| `active` | bool | `false` |
| `limit` | int | `500` (1–2000) |

### `GET /api/servers/{host_root}/detail`
Deep-dive for one server: stats, maps, top players, activity heatmap, live
ports. `host_root` is a path segment (may contain dots).

---

## Meta

### `GET /api/health`
Liveness + total match count.

```json
{"ok": true, "matches": 158337, "now": "2026-05-29T..."}
```

---

## Admin endpoints (not public)

Routes under `/api/admin/*` (sync, rerate, scheduler control, deploy feed,
deep player inspection) require a bearer token (`SYNC_SECRET`) and are **not**
part of the public contract. They appear in the Swagger UI but will return
`401`/`503` without the token. Don't build against them.

---

*See [api_roadmap.md](./api_roadmap.md) for the full surface audit and the list
of endpoints we could add next.*

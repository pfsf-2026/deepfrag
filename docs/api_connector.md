# DeepFrag API — Data Connector Guide

Written for article-writing tools (SageSEO connectors) and anyone integrating
DeepFrag data. The OpenAPI spec lists every route and its query params, but the
endpoints return untyped JSON, so the spec's response schemas are empty — **this
file is the response-shape documentation.** Share both together.

- **Base URL:** `https://deepfrag-api-751658372467.us-central1.run.app`
- **Spec (machine-readable):** `{base}/openapi.json` · **Swagger UI:** `{base}/docs`
- **Auth:** none for everything below. Routes under `/api/admin/*` are
  bearer-gated and return 401 — ignore them.
- **IDs:** players are keyed by `canonical_id` (lowercase slug, e.g. `cronus`,
  `bogojoker`). Display names usually match; resolve them case-insensitively
  against `/api/rankings` when unsure. Profile URLs: `https://app.deepfrag.gg/p/{canonical_id}`.
- **Modes:** `1on1`, `2on2`, `4on4`. **Ratings:** `mu` is the headline rating
  (best guess); `conservative` = mu − 3σ (floor); rows with `provisional: true`
  have unstable ratings — do not quote them as established.
- **Freshness:** data syncs continuously; live-server data every minute. Numbers
  in articles should be date-stamped ("as of <date>") since they move daily.

## Endpoints that matter for content

### Rankings — `GET /api/rankings`
Params: `mode` (1on1|2on2|4on4), `region` (NA/EU/SA/OC/AS/AF, optional),
`min_matches` (default 10), `limit`. Sorted by `mu` desc, `rank` included.

```json
{"players": [{
  "canonical_id": "locust", "display": "Locust", "region": "EU",
  "mu": 2666.5, "sigma": 81.7, "conservative": 2421.5,
  "matches": 715, "wins": 698, "losses": 17, "win_rate": 0.976,
  "provisional": false, "active_90d": true, "avg_ddr": 1.63,
  "avg_frag_diff": 32.0, "last_match": "2026-08-10T18:29:38+00:00",
  "tier": {"slug": "div0", "name": "Div 0", "color": "#fbbf24"}, "rank": 1}]}
```

### Head-to-head — `GET /api/h2h?p1={id}&p2={id}&mode=1on1`
Also takes `since_days`. Returns both player cards, the shared-match record,
and a calibrated win prediction.

```json
{"player_a": {"canonical_id": "sane", "mu": 2249.6, "tier": {...},
   "weapon_shape": {"lg_accuracy": 0.349, "avg_ddr": 1.71, ...}},
 "player_b": {...},
 "h2h": {"matches": 44, "wins_a": 23, "wins_b": 21, "draws": 0,
         "ddr_a": 0.93, "ddr_b": 1.07},
 "overall_predict_win_a": 0.497, "overall_predict_win_b": 0.503,
 "maps": [...], "recent_matches": [...]}
```

### Team-mode comparison — `GET /api/h2h/team-split?p1={id}&p2={id}&mode=4on4&days=60`
Two players across the team games they shared, split `together` vs `against`.
Optional `exclude=id1,id2` drops matches where those players appear on either
side. Per split, per player:

```json
{"splits": [{"split": "against", "cid": "cronus", "games": 12,
  "wins": 4, "losses": 8, "frags_pg": 45.4, "deaths_pg": 56.4,
  "fragdiff_pg": -11.0, "dmg_given_pg": 8180, "ddr": 0.94,
  "lg_acc": 0.275, "rl_acc": 0.609, "quads_pg": 1.6, "ra_pg": 6.1, ...}],
 "maps_by_split": {...}}
```

### Stat leaderboards — `GET /api/stats/leaderboards?mode=1on1&top=10`
Params: `map`, `region`, `window` (30d/90d/6mo/1yr/all), `min_matches`.
1on1 only. Keys: `lg_pct, rl_pct, frag_diff, ddr, net_dmg, dmg_given,
dmg_taken, ra_pct, mh_pct, ya_pct, avg_frags, avg_speed`, each:

```json
{"display": "LG accuracy", "direction": "desc",
 "top": [{"rank": 1, "canonical_id": "asdf", "display": "asdf",
          "value": 0.4119, "formatted": "41.2%", "matches": 31}]}
```

### Per-map rankings — `GET /api/rankings/maps/{map}?mode=4on4`
Map-specific ratings (schloss specialists ≠ dm2 specialists). Same row shape
as `/api/rankings`.

### Player profile — `GET /api/players/{canonical_id}`
`{canonical_id, display, login, career, ratings}` — per-mode ratings and
career aggregates. Rating timeline: `GET /api/players/{id}/rating-history?mode=1on1`
→ `points: [{match_date, opponent_cid, outcome, mu, delta}]`.

### Live servers — `GET /api/balancer/servers`
Occupied, bot-filtered servers with resolved player identities and ratings.
`{servers: [{hostname, mode, map, humans, city, region, players: [...]}]}`.
Full tracked list (with last-activity): `GET /api/servers`.

### Map activity — `GET /api/stats/maps?mode=4on4`
`{maps: [{"map": "dm2", "games": 5888}, ...]}` — corpus size per map.

### Team balancer — `GET /api/balance?ids=id1,...,id8&mode=4on4[&map=dm2]`
Exactly 8 canonical ids → most even 4v4 splits with win probabilities and
per-map projections (`p_by_map` over dm2/dm3/e1m2/schloss).

## Sage connector protocol (machine ingestion)

For Sage SEO's Customer Data Connector, the API also implements the provider
protocol under `GET /api/v1/connector/*` — bearer-key authenticated
(`Authorization: Bearer <key>`), wire-format-v1 envelope
(`{format, version, generated_at, params, data}`). Datasets:

- `meta` — inventory + freshness: total bot-free matches, `data_through`,
  established rated-player counts per mode, dataset list.
- `rankings-1on1`, `rankings-4on4` (`?top=50`) — established players (≥10
  rated games, σ≤150) ranked by rating μ, with region, W-L, damage ratio
  (DDR), and average frag differential. μ ~1500 = median, Div 0 starts around
  the top 5%.
- `map-activity` — games per map per mode across the whole corpus. The "big
  four" 4on4 maps are dm2, dm3, schloss, e1m2.
- `activity-trends` (`?weeks=26`) — games and distinct active players per ISO
  week per mode: the community-health / seasonality signal.
- `live-servers` — servers with humans on them right now (hostname, city,
  region, map, mode, player count).

Vocabulary: "duel" = 1on1; "fours"/"4on4" = the team mode; a match's
"margin" is the team frag differential; "quad" (Quad Damage) and "RA" (red
armor) are the contested map resources; KTX is the competitive server mod;
ratings are OpenSkill-based (μ = best-guess skill, σ = uncertainty;
provisional until ~10 rated games).

Article angles this data uniquely supports: weekly/seasonal activity trends;
map meta pieces (pace, margins, item control from the match DB); rankings
movement and divisional cutoffs; "who's playing right now" regional server
coverage; team-balance fairness (the calibrated 4on4 predictor described
above).

## Writing rules for generated articles

1. Never invent numbers — every stat must come from one of these endpoints
   (or be explicitly sourced elsewhere).
2. Skip `provisional: true` players in "top N" claims.
3. Date-stamp mutable claims; ratings move daily.
4. Deep-link players (`app.deepfrag.gg/p/{id}`), rankings (`app.deepfrag.gg/`),
   h2h (`app.deepfrag.gg/h2h?p1=&p2=&mode=`), balancer (`app.deepfrag.gg/balancer`).
5. Posts on deepfrag.gg can embed LIVE data instead of quoting static numbers —
   theme shortcodes `[df_top]`, `[df_player]`, `[df_h2h]`, `[df_servers]`
   (see the theme's functions.php header for attributes). Prefer an embed over
   a hardcoded table when showing current standings.

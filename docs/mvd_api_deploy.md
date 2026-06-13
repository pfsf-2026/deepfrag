# DeepFrag mvd-api — how it works, how it's built, how to change it

The **mvd-api** is the HTTP demo-parser service DeepFrag's backend calls to turn
QuakeWorld `.mvd` demos into per-frame state, events, and stats. It's the engine
behind the coaching tab, spawn-runs/FSO, and the new bot/player-rating frame
metrics (movement, view angles).

> This is a **DeepFrag deploy runbook** for a service whose *source* lives in a
> separate repo (Nexus's `galfthan/mvd_analyzer`). We don't own the parser; we
> build + deploy our own instance of its `mvd-api` component.

---

## 1. Architecture (what calls what)

```
.mvd demos (hub)  ──►  deepfrag-mvd-api (Cloud Run, Go)  ──►  DeepFrag backend (coaching.py / extract_spawn_runs.py)
                        │  parses demos, exposes HTTP        │  MVD_API_BASE = the service URL
                        └─ consumes mvd-analytics packages   └─ coaching metrics, spawn runs, frame ratings
```

- **Source repo:** `galfthan/mvd_analyzer` — a **Go workspace (`go.work`)** with 5 modules:
  `mvd-reader` (wire parser) · `mvd-analytics` (analysis + the `view` query API) ·
  **`mvd-api`** (the HTTP server we deploy) · `mvd-mcp` · `mvd-web` (WASM).
  Local clone: `~/Projects/mvd_analyzer`.
- **mvd-api is a thin HTTP layer over `mvd-analytics/view`.** It does almost no
  logic itself — it parses params and calls the analytics packages. So **new
  analytics features (new bucket fields, schema bumps) appear in the API just by
  rebuilding the image** — no api code change needed. (Nexus's point: "api is a
  separate consumer of the analytics packages, exposing the go stuff over http.")

## 2. The deployed service (recovered from the live config, 2026-06-13)

| | |
|---|---|
| Cloud Run service | **`deepfrag-mvd-api`** |
| GCP project | **`deepfrag-prod`** (project number `751658372467`) |
| Region | `us-central1` |
| URL | `https://deepfrag-mvd-api-751658372467.us-central1.run.app` |
| Image | `us-central1-docker.pkg.dev/deepfrag-prod/deepfrag/mvd-api` (Artifact Registry) |
| Resources | **2 CPU, 2Gi, maxScale 4**, startup-cpu-boost |
| Container cmd | none on the service → the **image ENTRYPOINT** runs `mvd-api serve --addr :8080` |
| `--maps-dir` | **not set** (the `/v1/maps/{map}/geometry` endpoint is OFF; DeepFrag geometry comes from elsewhere) |
| Deploy account | `peter@sageseo.ai` (gcloud configured to `deepfrag-prod`) |

## 3. Endpoints DeepFrag actually uses

Addressed by **hub gameId** (`gameId:NNN`). **Critical:** for recent matches our
`matches.match_id` == hub gameId, but for old/migrated rows it does NOT — always
use `hub_game_id`, never `match_id`, to reach a demo. (See `project_deepfrag_two_epoch_data`.)

- `GET /v1/demos/gameId:{id}/buckets?windowMs=50&layout=column[&fields=...]`
  — per-frame columnar state. Default fields: `h a at li pos rl lg gl ssg sng q pe r sh nl rk cl sp d`.
  Player object: `x y z` (pos), `a`(armor) `h`(health) `at`(armor type) `alive`, weapon/ammo flags.
  **`fields=pos,view`** adds **`vp`/`vya`** (view pitch/yaw) — *only on schema v31+*.
- `GET /v1/demos/gameId:{id}/frags` — kill log (time, killer, victim, weapon).
- `GET /v1/demos/gameId:{id}/items` — item pickups (phases, takenBy).
- `GET /v1/demos/gameId:{id}/events` — chat/weapon/death/frag/spawn/item/powerup/streak.
- `GET /v1/demos/gameId:{id}/stream-slice?from=..&to=..` — raw `PositionTrack` (`t,x,y,z`[,`vp,vya` on v31]).

## 4. View angles (the schema-v31 unlock)

Branch **`add-view-direction`** = `CurrentSchemaVersion = 31`. The parser reads
view pitch/yaw into `PositionTrack.VP`/`VYa` (raw angle16). Decode:
`degrees = uint16(v) * 360 / 65536`, range [0,360); for pitch, `>180` = looking up.
Exposed per 13ms frame via `buckets?fields=pos,view` (→ `vp`/`vya` columns) or
`stream-slice` `pos`. This is what unlocks Coupling / Reaction / Aim-under-fire /
Aim-vs-airborne for the bot/player cards. **Requires the image rebuilt from this branch.**

## 5. Build & deploy (the only two commands)

From `~/Projects/mvd_analyzer` on the desired branch (e.g. `add-view-direction`),
with the `Dockerfile` at repo root (committed-to-DeepFrag copy is in §7):

```bash
# 1) build the image (Cloud Build) into the SAME Artifact Registry repo
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/deepfrag-prod/deepfrag/mvd-api \
  --project deepfrag-prod .

# 2) deploy it to the existing service, matching the recovered resources
gcloud run deploy deepfrag-mvd-api \
  --image us-central1-docker.pkg.dev/deepfrag-prod/deepfrag/mvd-api \
  --region us-central1 --project deepfrag-prod \
  --cpu 2 --memory 2Gi --max-instances 4 --allow-unauthenticated
```

No local Docker needed — Cloud Build builds the `Dockerfile` remotely. The
`go.work` build pulls `mvd-analytics`/`mvd-reader` from the local tree, so the
deployed binary matches whatever branch you built from.

## 6. Verify after deploy

```bash
API=https://deepfrag-mvd-api-751658372467.us-central1.run.app
# schema version + view angles present?
curl -s "$API/v1/demos/gameId:221218/buckets?windowMs=13&layout=column&fields=pos,view" \
  | python3 -c "import sys,json;p=json.load(sys.stdin)['players'];k=next(iter(p));print('view keys:',[x for x in p[k] if x in('vp','vya')])"
# should print: view keys: ['vp', 'vya']   (pre-v31 errors: "unknown field code view")
# sanity: existing endpoints still work
curl -s -o /dev/null -w "buckets:%{http_code} frags:" "$API/v1/demos/gameId:221218/buckets?windowMs=50&layout=column"
curl -s -o /dev/null -w "%{http_code}\n" "$API/v1/demos/gameId:221218/frags"
```

## 7. The Dockerfile (kept here so it's never lost again)

It lives at `mvd_analyzer/Dockerfile` (local, uncommitted to Nexus's repo). Verbatim:

```dockerfile
FROM golang:1.25 AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /out/mvd-api ./mvd-api

FROM gcr.io/distroless/base-debian12:nonroot
COPY --from=build /out/mvd-api /mvd-api
ENTRYPOINT ["/mvd-api", "serve", "--addr", ":8080"]
```

## 8. How to modify

- **Pick up a new parser/analytics feature** (e.g. view angles, a new bucket
  field): just rebuild from the branch that has it (§5). The api auto-exposes it.
- **Add `make bsps`** (loc/visibility accuracy — an open follow-up; I skipped it
  on 2026-05-28 and Nexus flagged it): add a `RUN ./scripts/fetch-bsps.sh /src/bsps`
  step in the build stage, copy `bsps/` into the runtime image, and confirm the
  **bsp runtime path** with Nexus (there's no `--bsp-dir` flag — locvis loads them
  from a default location). Do NOT silently skip it again.
- **Enable map geometry** (`/v1/maps/{map}/geometry`): generate the per-map JSON
  (mapgen) and add `--maps-dir /app/maps` to the ENTRYPOINT + copy the JSON in.
- **Change resources**: edit the `--cpu/--memory/--max-instances` on the deploy.

## 9. Gotchas

- **gcloud auth expires between sessions** → `gcloud builds/run/logging` fail with
  "Reauthentication failed"; `gcloud config list` still works. Fix: `gcloud auth login`.
- **The deployed binary lags the analytics package.** "Unknown field code X" / a
  missing field almost always means the image was built from an older schema —
  rebuild. (This is exactly what blocked view angles: package had v31, image was older.)
- **`match_id` ≠ `hub_game_id`** for old rows — always address demos by hub gameId.
- **CORS:** the service allows browser callers; DeepFrag's backend calls it server-side.

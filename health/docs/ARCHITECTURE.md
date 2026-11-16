# Architecture

One owner, all of their health data, one assistant that knows it. This document
records the decisions behind the current code and the roadmap toward "full
native, proactive, connected to everything".

## 1. Shape

```
 iPhone / Android / browser            your server (Mac now, container later)
 ┌──────────────────────┐              ┌─────────────────────────────────────┐
 │ Expo app (app/)      │  HTTPS JSON  │ FastAPI (api/)                      │
 │  Today · Log · Chat  │ ───────────▶ │  routers ─▶ repo ─▶ Postgres        │
 │  Records · Settings  │ ◀─────────── │  ai/assistant  (tool runner, SSE)   │
 │  HealthKit (native)  │   SSE text   │  ai/ingest     (document → records) │
 └──────────────────────┘              │  ai/briefing   (daily insights)     │
                                       │  apple_health  (export importer)    │
                                       └──────────────┬──────────────────────┘
                                                      │ Anthropic SDK
                                                      ▼
                                                 Claude (Messages API)
```

- **One Postgres database is the record.** Everything the assistant knows comes
  from it; everything the assistant does writes to it. No vector store, no second
  copy. Documents are stored as files beside it (local dir now, object storage later).
- **The API is the only thing that talks to Claude.** Keys stay on the server;
  the app only ever holds a bearer token for the API.
- **The app is a thin client** that renders what the API returns. Business
  logic, units, and prompts all live server-side so web and native stay identical.

## 2. Data model

Tables (see `api/migrations/0001_init.sql`):

| Table | What it is |
|---|---|
| `users`, `profiles` | one owner today; profile holds birth date, sex, height, timezone, goals, preferences |
| `observations` | **the time series**: every measurement with a `kind` code, value, unit, time, source. Vitals, body, labs, activity, sleep, mood. One table so the assistant queries everything the same way |
| `meals` | description, item list with per-item macros, totals |
| `workouts` | kind, duration, distance, calories, HR |
| `medications`, `medication_logs` | the list, and taken/skipped events |
| `conditions`, `allergies`, `providers`, `encounters` | the medical-history side |
| `documents` | uploaded files + status + model extraction (`extracted jsonb`) + summary |
| `chat_threads`, `chat_messages` | conversations; `content` is the raw Anthropic content array |
| `insights` | what the proactive layer produces: briefing, nudge, anomaly, anticipation, reminder, question |

Design choices:

- **`observations.kind` is a short code** (`weight`, `bp_systolic`, `ldl`); the
  catalog in `api/app/observations.py` carries label, canonical unit, category and
  LOINC. Values are converted to the canonical unit on write (`lb` → `kg`). Labs
  the catalog doesn't know are stored as `lab:<name>` so nothing is dropped.
- **`source` + unique index make imports idempotent.** Re-importing an Apple
  Health export or re-processing a document upserts instead of duplicating.
- **`meta jsonb` everywhere** for the long tail (reference ranges, flags, device
  names) so a new wearable field is not a migration.
- **Chat content is stored verbatim** so thinking blocks and tool blocks are
  replayed unchanged, which the API requires for preserved thinking.

## 3. AI layer

Three uses of Claude, all through the official Python SDK (`anthropic`):

1. **Assistant** (`ai/assistant.py`): `client.beta.messages.tool_runner(..., stream=True)`
   with ~18 tools from `ai/tools.py` (read profile, query/summarize observations,
   log meal/workout/measurement, medications, documents, insights) plus Anthropic's
   server-side `web_search`. Tools are built per request bound to the user id, so
   the model can't reach another user's rows (there is only one user today, but the
   pattern is what makes multi-user a config change). Text streams to the client as
   SSE; tool calls show as a status line. The system prompt is cached.
2. **Document ingestion** (`ai/ingest.py`): one `client.messages.parse` call with
   the PDF/image as a document block and `ExtractedDocument` (Pydantic) as the
   output format. The typed result fans out to observations (labs/vitals),
   medications, conditions and an encounter, all tagged with the document id so a
   reprocess replaces cleanly.
3. **Daily briefing** (`ai/briefing.py`): a JSON snapshot of the last 14 days goes
   to `messages.parse` with a `Briefing` schema; items land in `insights`. Trigger
   with `POST /api/insights/run` from any scheduler.

Model: `claude-opus-5-5` by default (`HEALTH_MODEL`). Extraction can use a cheaper
model via `HEALTH_FAST_MODEL`. Adaptive thinking is on by default on these models;
effort is left at the default for now and is the first knob to tune once there is
real usage.

What the assistant is told (see `ai/prompts.py`): ground everything in tool
results, log things mentioned in passing, be proactive, explain results plainly,
recommend a doctor when warranted, never refuse to discuss the owner's own data.

## 4. Security and privacy posture

- Single owner, bearer token (`HEALTH_APP_TOKEN`) over HTTPS. Unset token means
  open API, acceptable only on localhost; the server logs a warning.
- Authorization is centralized in `repo.py`: every function scopes by `user_id`.
- No analytics, no third-party SDKs in the app, no logging of record values.
- Anthropic API: data sent for inference is subject to Anthropic's retention
  policy for API customers; nothing is used for training. If you want zero data
  retention, ask Anthropic for ZDR on the org (note some models require 30-day
  retention; check the model's row in the claude-api skill before switching).
- Backups: Postgres dump + the documents directory. Encrypt at rest where it lives.

Next steps here: Sign in with Apple / passkeys replacing the shared token;
per-device tokens that can be revoked; audit log of assistant writes.

## 5. Integrations roadmap

Ordered by value per effort for a personal system:

1. **Apple Health export** (done): bulk history import from export.zip.
2. **HealthKit live sync (native, next):** a React Native HealthKit module with an
   Expo config plugin, run in a dev build. Background delivery for steps, HR, HRV,
   sleep, workouts, weight; write back meals/water the assistant logs. Requires
   the `com.apple.developer.healthkit` entitlement and a privacy string in
   `app.json`. Android equivalent: Health Connect.
3. **Health Records (FHIR) via HealthKit clinical records**: if your providers
   support Apple Health Records, labs, meds, conditions and immunizations arrive
   as FHIR resources on device. Map them into the same tables. This replaces a
   lot of PDF uploading for US providers on Epic/Cerner.
4. **Nutrition lookups**: USDA FoodData Central (free key) for the assistant to
   check macros instead of estimating; photo-of-plate logging via Claude vision
   (just send the image in the chat; the API already accepts images in content).
5. **Strava / Garmin / Oura / Whoop**: OAuth connectors writing into
   `observations` and `workouts` with their own `source`. Each is a small module
   like `apple_health.py`.
6. **Patient portal PDFs**: many portals email a PDF or let you download one;
   until FHIR is available, the upload path handles them.
7. **Calendar**: push `anticipation` and `reminder` insights into Google Calendar
   (the API already sees due dates).
8. **Notifications**: Expo push for `attention`/`urgent` insights after a briefing run.

## 6. Native plan

The app is Expo Router with native bottom tabs on iOS/Android and a web tab bar
on the web, from one codebase. Path to "full native":

- **Now**: `npx expo start` → web; iOS simulator works with Expo Go for everything
  that doesn't need HealthKit.
- **Dev build**: `eas build --profile development` the moment HealthKit is added;
  Expo Go cannot load custom native modules.
- **Ship**: EAS Build + EAS Submit to TestFlight / Play internal testing. OTA
  updates with EAS Update for JS-only changes.
- **Where native code is genuinely needed**: HealthKit/Health Connect sync,
  background delivery, Live Activities / widgets later. Everything else stays in
  TypeScript.

## 7. Deploy

Mirror the deepfrag setup you already run:

- **API**: `api/Dockerfile` → Cloud Run (or Fly, Railway, a VPS). Postgres on
  Cloud SQL or managed Postgres. Env: `HEALTH_PG_URL`, `HEALTH_APP_TOKEN`,
  `ANTHROPIC_API_KEY`, `HEALTH_DATA_DIR` on a mounted volume or swap the local
  file writes for GCS (one function in `routers/documents.py`).
- **Scheduler**: Cloud Scheduler (or cron) → `POST /api/insights/run` daily with
  the bearer token.
- **Web app**: `npx expo export --platform web` → static files → Cloudflare Pages.
- **Home option**: everything on the iMac behind Tailscale. Zero cloud, data never
  leaves the house except for inference. Good fit for a personal system.

## 8. What's deliberately not here yet

- Multi-user and sharing (with a spouse, a doctor): the data model supports it,
  auth does not.
- Charts: the API has `/api/observations/summary` with daily series; the Today
  screen shows latest values only. Add charts once the data is flowing.
- Offline mode on the phone.
- Medication reminders as push notifications (the data exists in `medication_logs`).

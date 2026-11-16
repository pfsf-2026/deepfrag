# Health

A personal health system: every record you have (doctor documents, labs, vitals,
meals, workouts, medications, wearable data) in one private store, with a Claude
assistant that reads and writes it, and a daily proactive briefing.

Two parts, one repo:

| Part | Stack | Where it runs |
|---|---|---|
| `api/` | Python 3.12, FastAPI, Postgres 16, Anthropic SDK | your machine now; a container (Cloud Run or similar) later |
| `app/` | Expo (React Native + Expo Router), TypeScript | web in a browser now; iOS and Android as native builds via EAS |

Read `docs/ARCHITECTURE.md` for the design and the roadmap. `CLAUDE.md` is the
working brief for coding sessions.

## Run it locally (MacBook)

Prerequisites: Docker Desktop, Python 3.12+, Node 22+, an Anthropic API key.

```bash
cd health
cp .env.example .env            # then edit: set HEALTH_APP_TOKEN and ANTHROPIC_API_KEY
source .env
make setup                      # python venv + npm install
make db                         # postgres in docker
make api                        # http://localhost:8000  (migrations run on start)
```

In a second terminal:

```bash
cd health && source .env
make app                        # Expo dev server; press w for web, i for the iOS simulator
```

Open the web app, go to **Settings**, set API URL `http://localhost:8000` and
paste your `HEALTH_APP_TOKEN`, then "Save and test".

Tests (need Postgres; the default URL matches `make db`):

```bash
make test
```

## First useful things to do

1. **Settings → Profile**: birth date, sex, height, timezone. The assistant uses these for ranges and screening schedules.
2. **Settings → Import Apple Health export**: iPhone Health app → your picture → Export All Health Data → AirDrop the zip to the Mac → pick it. Steps, heart rate, HRV, SpO₂, sleep, weight, workouts land as observations.
3. **Records → Upload**: PDFs of lab reports and visit notes. Each is read once by Claude and filed as labs, medications, diagnoses and a visit summary.
4. **Assistant**: talk. "What did my last lipid panel say and what changed?", "I had a chicken burrito", "ran 5k in 26 min".
5. **Today → Refresh briefing**: generates the proactive items. Wire this to a daily schedule once you like it (`POST /api/insights/run`).

## Phones and the API URL

A phone can't reach `localhost` on your Mac. For development, run the API on
your LAN IP (`uvicorn ... --host 0.0.0.0`) and put `http://<mac-ip>:8000` in the
app's Settings, or expose it with Tailscale. For real use, deploy the API behind
HTTPS (see the deploy section of `docs/ARCHITECTURE.md`).

## Native builds

Expo Go can't load native modules the app will need (HealthKit). Use a
development build:

```bash
cd app
npx eas-cli@latest build --profile development --platform ios
```

See `docs/ARCHITECTURE.md` → "Native" for HealthKit and the rest of the native plan.

## Moving this into its own repository

It started inside the deepfrag repo. Everything it needs is under `health/`:

```bash
git subtree split --prefix=health -b health-only
mkdir ../health && cd ../health && git init && git pull ../deepfrag health-only
```

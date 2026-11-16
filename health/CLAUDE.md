# Health: working brief for coding sessions

Personal health system for one owner. API in `api/` (FastAPI + Postgres + Anthropic SDK),
app in `app/` (Expo / React Native / Expo Router, TypeScript, web + iOS + Android).
Design and roadmap: `docs/ARCHITECTURE.md`. Local run: `README.md`.

## Rules that matter here

- **Authorization lives in `api/app/repo.py`.** Every query there takes `user_id` and
  puts it in the WHERE. Routers and AI tools both call repo; never write SQL in a router
  or a tool. The AI tools are built per request by `build_tools(user_id)`.
- **Schema changes are new files** in `api/migrations/NNNN_name.sql`. Never edit an
  applied migration. Prefer a `meta jsonb` field over a new column for one-off attributes.
- **Observation kinds** are catalogued in `api/app/observations.py`. Add a kind there
  (with its canonical unit and LOINC if known) rather than inventing codes in callers.
- **Prompts** are in `api/app/ai/prompts.py` and are cached as a prefix. Edit deliberately.
- **Model calls** go through the Anthropic SDK only (`client.messages.parse` for typed
  extraction, `client.beta.messages.tool_runner` for the agent). Default model is
  `claude-opus-5-5`, overridable with `HEALTH_MODEL`. Load the `claude-api` skill
  before touching anything under `api/app/ai/`.
- **Secrets never in the repo.** `.env` is ignored; `.env.example` shows the shape.
- **Health data is sensitive.** Don't add telemetry, third-party SDKs, or logging of
  record contents. Log ids and counts, not values.
- **Expo:** follow `app/AGENTS.md` (fetch versioned Expo docs; don't trust memory).
  `npx expo install` needs network to the Expo API; where that is blocked, read the
  version from `app/node_modules/expo/bundledNativeModules.json` and `npm install` it.

## Verify before finishing

```bash
cd api && ../.venv/bin/python -m pytest -q         # needs Postgres (see tests/conftest.py)
cd app && npx tsc --noEmit && npx eslint src
```

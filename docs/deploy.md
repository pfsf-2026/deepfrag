---
title: DeepFrag Deploy Pipeline
---

# DeepFrag Deploy Pipeline

Two independent halves:

| Component | Repo path | Host | Auto-deploy? |
|---|---|---|---|
| **Frontend** (Nuxt) | `nuxt/` | Cloudflare Pages | ✅ Yes — CF Pages is git-connected; every push to `main` rebuilds. |
| **Backend** (FastAPI) | repo root (`api.py`, etc.) | Cloud Run `deepfrag-api` (project `deepfrag-prod`, us-central1) | ✅ Yes, via the Cloud Build trigger below (set up 2026-05-29). |

Before 2026-05-29 the backend had **no** auto-deploy — revisions were built by
hand with `gcloud run deploy --source`. That's why code could sit pushed-but-
not-live (e.g. the `/api/players` endpoint 404'd for ~20 min after its commit).
The trigger fixes that.

## Backend auto-deploy (Cloud Build trigger)

[cloudbuild.yaml](../cloudbuild.yaml) defines build → push → deploy. It runs
only when **backend files** change (path filter on the trigger), so a
frontend- or docs-only push doesn't rebuild the container.

### One-time setup

The only step that can't be scripted headless is authorizing Cloud Build to
read the GitHub repo (a browser OAuth flow).

1. **Connect the repo** (browser):
   GCP Console → Cloud Build → Triggers → **Connect Repository** →
   GitHub (Cloud Build GitHub App) → authorize → pick `pfsf-2026/deepfrag`.
   Project: `deepfrag-prod`, region: **global** (1st-gen triggers).

2. **Create the trigger** (CLI, after the connection exists):

   ```bash
   gcloud builds triggers create github \
     --project=deepfrag-prod \
     --name=deepfrag-api-deploy \
     --repo-owner=pfsf-2026 \
     --repo-name=deepfrag \
     --branch-pattern='^main$' \
     --build-config=cloudbuild.yaml \
     --included-files='api.py;*.py;Dockerfile;requirements-api.txt;cloudbuild.yaml;tests/**;aliases.yaml'
   ```

   The `--included-files` glob is the backend-only filter. Add a path here if a
   new backend file should trigger deploys.

3. **Grant the Cloud Build SA deploy permission** (once):

   ```bash
   PROJECT_NUMBER=751658372467
   for role in roles/run.admin roles/iam.serviceAccountUser; do
     gcloud projects add-iam-policy-binding deepfrag-prod \
       --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
       --role="$role"
   done
   ```

   (`run.admin` to deploy; `serviceAccountUser` to deploy *as* the runtime SA
   `751658372467-compute@developer.gserviceaccount.com`.)

### Verify

Push a trivial backend change and watch:

```bash
gcloud builds list --project=deepfrag-prod --limit=3
# new build with TRIGGER_NAME=deepfrag-api-deploy should appear, then:
curl -s https://deepfrag-api-751658372467.us-central1.run.app/api/health
```

## Manual deploy (fallback)

Still works any time (what we did before the trigger):

```bash
cd ~/Projects/qw-stats
gcloud run deploy deepfrag-api --source . --region us-central1 --project deepfrag-prod
```

## Env vars & secrets

`DEEPFRAG_PG_URL`, `SYNC_SECRET`, and friends live **on the Cloud Run service**
and persist across deploys. Neither cloudbuild.yaml nor a `--source` deploy
touches them. To change one:

```bash
gcloud run services update deepfrag-api --region us-central1 \
  --update-secrets SYNC_SECRET=deepfrag-sync-secret:latest   # example
```

Never put secret *values* in cloudbuild.yaml or any committed file — the repo
is public.

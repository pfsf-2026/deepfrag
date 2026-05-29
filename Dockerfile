# DeepFrag API — slim Python image for Cloud Run.
# uvicorn binds to $PORT (default 8080 on Cloud Run) per platform contract.
FROM python:3.12-slim

WORKDIR /app

# Build-time deps for psycopg2 source compile, then remove. Using -binary
# avoids that, but we keep -dev around for any future native deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy what the API needs PLUS the periodic-sync scripts the admin endpoint
# spawns (sync_all_recent, canonicalize, rate, regions, live servers) AND the
# invariants test that runs as the last step of every sync.
COPY api.py tiers.py export_rankings.py profile_pg.py stats_pg.py \
     db.py sync.py canonicalize.py name_canon.py rate.py \
     assign_player_regions.py sync_live_servers.py geolocate_servers.py \
     seed_map_geometry.py aliases.yaml ./
COPY tests/ ./tests/

ENV PORT=8080
EXPOSE 8080

# Single worker is fine for a hobby load; Cloud Run scales horizontally per concurrency.
CMD exec uvicorn api:app --host 0.0.0.0 --port "${PORT}" --workers 1

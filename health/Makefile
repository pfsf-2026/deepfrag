# Everyday commands. Assumes `source .env` has been done (see .env.example).
PY ?= .venv/bin/python
API_DIR = api
APP_DIR = app

.PHONY: setup db api test app app-ios typecheck migrate briefing docker

setup:            ## create the Python venv and install both projects' dependencies
	python3 -m venv .venv && $(PY) -m pip install -q -r $(API_DIR)/requirements-dev.txt
	cd $(APP_DIR) && npm install

db:               ## start Postgres in Docker
	docker compose up -d db

migrate:          ## apply pending SQL migrations
	cd $(API_DIR) && ../$(PY) -m app.db

api:              ## run the API with reload on :8000
	cd $(API_DIR) && ../$(PY) -m uvicorn app.main:app --reload --port 8000

test:             ## run the API tests (needs Postgres; HEALTH_TEST_PG_URL overrides the default)
	cd $(API_DIR) && ../$(PY) -m pytest -q

app:              ## Expo dev server (press w for web, i for iOS simulator)
	cd $(APP_DIR) && npx expo start

typecheck:        ## typecheck the Expo app
	cd $(APP_DIR) && npx tsc --noEmit

briefing:         ## generate today's briefing now (what the daily scheduler does)
	curl -s -X POST -H "Authorization: Bearer $$HEALTH_APP_TOKEN" http://localhost:8000/api/insights/run | head -c 2000; echo

docker:           ## build the API container
	docker build -t health-api $(API_DIR)

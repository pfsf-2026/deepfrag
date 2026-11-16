-- Health: initial schema.
-- Conventions: every user-owned row carries user_id; times are timestamptz;
-- free-form extras go in a `meta` jsonb column so the schema can grow without
-- a migration for every new wearable field.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    email         text UNIQUE,
    display_name  text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- One row per user: static-ish facts the assistant should always know.
CREATE TABLE profiles (
    user_id      bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    birth_date   date,
    sex          text,                 -- 'male' | 'female' | 'other' | null
    height_cm    numeric(5,1),
    timezone     text NOT NULL DEFAULT 'UTC',
    goals        jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{"kind":"weight","target":80,"unit":"kg","by":"2027-03-01"}]
    preferences  jsonb NOT NULL DEFAULT '{}'::jsonb,   -- units, diet style, tone, quiet hours...
    notes        text,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Generic time series: weight, blood pressure, glucose, labs, steps, sleep, HR...
-- `kind` is a short snake_case code (see app/observations.py for the catalog).
CREATE TABLE observations (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         text NOT NULL,
    value        numeric,
    unit         text,
    value_text   text,                 -- for qualitative results ("negative", "trace")
    observed_at  timestamptz NOT NULL,
    source       text NOT NULL DEFAULT 'manual',  -- manual | apple_health | document | assistant | import:<name>
    document_id  bigint,               -- set when extracted from an uploaded record
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"loinc":"2093-3","reference_range":"<200","flag":"H"}
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX observations_user_kind_time ON observations (user_id, kind, observed_at DESC);
-- Imports re-run safely: same user/kind/time/source is one reading.
CREATE UNIQUE INDEX observations_dedupe ON observations (user_id, kind, observed_at, source)
    WHERE source <> 'manual';

CREATE TABLE meals (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    eaten_at     timestamptz NOT NULL,
    description  text NOT NULL,
    items        jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{"name":"oatmeal","qty":"1 cup","calories":150,...}]
    calories     numeric,
    protein_g    numeric,
    carbs_g      numeric,
    fat_g        numeric,
    fiber_g      numeric,
    source       text NOT NULL DEFAULT 'manual',
    photo_key    text,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX meals_user_time ON meals (user_id, eaten_at DESC);

CREATE TABLE workouts (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at    timestamptz NOT NULL,
    duration_min  numeric,
    kind          text NOT NULL,       -- run | walk | cycle | strength | swim | hiit | yoga | other
    distance_km   numeric,
    calories      numeric,
    avg_hr        numeric,
    notes         text,
    source        text NOT NULL DEFAULT 'manual',
    meta          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX workouts_user_time ON workouts (user_id, started_at DESC);
CREATE UNIQUE INDEX workouts_dedupe ON workouts (user_id, started_at, source) WHERE source <> 'manual';

CREATE TABLE medications (
    id           bigserial PRIMARY KEY,
    user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         text NOT NULL,
    dose         text,                 -- "10 mg"
    route        text,                 -- oral | topical | injection | inhaled | ...
    frequency    text,                 -- "once daily, morning"
    reason       text,
    prescriber   text,
    started_on   date,
    stopped_on   date,
    active       boolean NOT NULL DEFAULT true,
    document_id  bigint,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"rxnorm":"...","refills_left":2}
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX medications_user ON medications (user_id, active);

CREATE TABLE medication_logs (
    id             bigserial PRIMARY KEY,
    medication_id  bigint NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
    taken_at       timestamptz NOT NULL DEFAULT now(),
    skipped        boolean NOT NULL DEFAULT false,
    note           text
);

CREATE TABLE conditions (
    id             bigserial PRIMARY KEY,
    user_id        bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           text NOT NULL,
    status         text NOT NULL DEFAULT 'active',  -- active | resolved | monitoring | family_history
    onset_date     date,
    resolved_date  date,
    notes          text,
    document_id    bigint,
    meta           jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {"icd10":"E78.5"}
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE allergies (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    substance  text NOT NULL,
    reaction   text,
    severity   text,                   -- mild | moderate | severe
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE providers (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    specialty  text,
    practice   text,
    phone      text,
    portal_url text,
    notes      text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Uploaded records: lab reports, visit notes, imaging, prescriptions.
CREATE TABLE documents (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename      text NOT NULL,
    media_type    text NOT NULL,
    storage_key   text NOT NULL,       -- path under HEALTH_DATA_DIR (local) or a GCS object key
    sha256        text NOT NULL,
    size_bytes    bigint NOT NULL,
    kind          text,                -- lab_report | visit_note | imaging | prescription | discharge | insurance | other
    document_date date,
    provider_name text,
    status        text NOT NULL DEFAULT 'pending',  -- pending | processing | processed | failed
    summary       text,
    extracted     jsonb,               -- full structured extraction from the model
    error         text,
    uploaded_at   timestamptz NOT NULL DEFAULT now(),
    processed_at  timestamptz,
    UNIQUE (user_id, sha256)
);
ALTER TABLE observations ADD CONSTRAINT observations_document_fk
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL;
ALTER TABLE medications ADD CONSTRAINT medications_document_fk
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL;
ALTER TABLE conditions ADD CONSTRAINT conditions_document_fk
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL;

-- A visit / appointment / hospital stay, usually created from a document.
CREATE TABLE encounters (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id   bigint REFERENCES providers(id) ON DELETE SET NULL,
    provider_name text,
    occurred_at   timestamptz NOT NULL,
    kind          text,                -- office_visit | lab_draw | imaging | er | telehealth | procedure
    summary       text,
    follow_ups    jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{"what":"repeat lipid panel","due":"2027-02-01"}]
    document_id   bigint REFERENCES documents(id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Assistant conversations. `content` is the raw Anthropic content array so
-- thinking/tool blocks are replayed unchanged.
CREATE TABLE chat_threads (
    id         bigserial PRIMARY KEY,
    user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE chat_messages (
    id         bigserial PRIMARY KEY,
    thread_id  bigint NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role       text NOT NULL,          -- user | assistant
    content    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chat_messages_thread ON chat_messages (thread_id, id);

-- The proactive layer writes here: nudges, anomalies, upcoming items, reminders.
CREATE TABLE insights (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            text NOT NULL,     -- briefing | nudge | anomaly | anticipation | reminder | question
    severity        text NOT NULL DEFAULT 'info',  -- info | attention | urgent
    title           text NOT NULL,
    body            text NOT NULL,
    due_at          timestamptz,
    data            jsonb NOT NULL DEFAULT '{}'::jsonb,  -- supporting numbers, source ids
    run_id          text,              -- groups insights produced by one briefing run
    created_at      timestamptz NOT NULL DEFAULT now(),
    acknowledged_at timestamptz,
    dismissed_at    timestamptz
);
CREATE INDEX insights_user_open ON insights (user_id, created_at DESC) WHERE dismissed_at IS NULL;

-- Single-user bootstrap. Auth maps the app token to user 1 until real sign-in lands.
INSERT INTO users (id, display_name) VALUES (1, 'Owner') ON CONFLICT DO NOTHING;
INSERT INTO profiles (user_id) VALUES (1) ON CONFLICT DO NOTHING;
SELECT setval('users_id_seq', (SELECT max(id) FROM users));

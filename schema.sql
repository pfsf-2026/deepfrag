-- One row per match Cronus participated in.
CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY,
    match_date TEXT NOT NULL,
    match_mode TEXT NOT NULL,            -- '1on1', '2on2', '4on4', etc. (from hub)
    match_map TEXT NOT NULL,
    match_tag TEXT,
    server_hostname TEXT,                -- 'The-Den:28502', "Mom's Basement:28501", etc.
    server_port INTEGER,
    match_dmm INTEGER,                   -- deathmatch mode (1-5); 4 is "all stays"
    match_tp INTEGER,                    -- teamplay mode
    match_time_limit_mins INTEGER,
    match_duration_secs INTEGER,
    match_demo_sha256 TEXT,
    demo_source_url TEXT,
    has_bots INTEGER DEFAULT 0,          -- 1 if any player is_bot=true
    ktx_fetched INTEGER DEFAULT 0        -- 1 once we've pulled KTX stats
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_mode ON matches(match_mode);
CREATE INDEX IF NOT EXISTS idx_matches_map ON matches(match_map);
CREATE INDEX IF NOT EXISTS idx_matches_server ON matches(server_hostname);
CREATE INDEX IF NOT EXISTS idx_matches_dmm ON matches(match_dmm);

-- One row per (match, player). Full KTX-style stats for every player in every match.
CREATE TABLE IF NOT EXISTS players (
    match_id INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    player_login TEXT,
    player_team TEXT,
    player_is_bot INTEGER DEFAULT 0,
    player_top_color INTEGER,
    player_bottom_color INTEGER,
    player_ping INTEGER,
    player_frags INTEGER,
    player_deaths INTEGER,
    player_teamkills INTEGER,
    player_spawnfrags INTEGER,
    player_suicides INTEGER,
    player_damage_taken INTEGER,
    player_damage_given INTEGER,
    player_damage_team INTEGER,
    player_damage_self INTEGER,
    player_damage_team_weapons INTEGER,
    player_damage_enemy_weapons INTEGER,
    player_damage_to_die INTEGER,
    player_spree_frag INTEGER,
    player_spree_quad INTEGER,
    player_speed_max REAL,
    player_speed_avg REAL,
    player_sg_attacks INTEGER,
    player_sg_hits INTEGER,
    player_sg_damage_enemy INTEGER,
    player_sg_damage_team INTEGER,
    player_ssg_attacks INTEGER,
    player_ssg_hits INTEGER,
    player_ssg_damage_enemy INTEGER,
    player_ssg_damage_team INTEGER,
    player_gl_attacks INTEGER,
    player_gl_directs INTEGER,
    player_gl_virtual INTEGER,
    player_rl_attacks INTEGER,
    player_rl_directs INTEGER,
    player_rl_virtual INTEGER,
    player_rl_dropped INTEGER,
    player_rl_taken INTEGER,
    player_rl_transfer INTEGER,
    player_rl_damage_enemy INTEGER,
    player_rl_damage_team INTEGER,
    player_rl_kills_enemy INTEGER,
    player_rl_kills_team INTEGER,
    player_lg_attacks INTEGER,
    player_lg_hits INTEGER,
    player_lg_dropped INTEGER,
    player_lg_taken INTEGER,
    player_lg_transfer INTEGER,
    player_lg_damage_enemy INTEGER,
    player_lg_damage_team INTEGER,
    player_lg_kills_enemy INTEGER,
    player_lg_kills_team INTEGER,
    player_health15_taken INTEGER,
    player_health25_taken INTEGER,
    player_health100_taken INTEGER,
    player_ga_taken INTEGER,
    player_ya_taken INTEGER,
    player_ra_taken INTEGER,
    player_quad_taken INTEGER,
    player_quad_time INTEGER,
    player_pent_taken INTEGER,
    player_ring_taken INTEGER,
    player_ring_time INTEGER,
    PRIMARY KEY (match_id, player_name)
);

CREATE INDEX IF NOT EXISTS idx_players_name ON players(player_name);

-- Canonical player identities. One row per real human player. Populated from
-- aliases.yaml + auto-generated entries from canonicalize.py.
CREATE TABLE IF NOT EXISTS players_canonical (
    canonical_id TEXT PRIMARY KEY,     -- slug, e.g. "cronus"
    display_name TEXT NOT NULL,        -- e.g. "Cronus" (best capitalization)
    login TEXT,                        -- hub account login (if known)
    created_at TEXT NOT NULL,          -- when this canonical first appeared
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_players_canonical_login ON players_canonical(login);

-- Every raw in-game name we've ever seen, mapped to its canonical identity.
-- Maintained by canonicalize.py — read-only at runtime by sync/export.
CREATE TABLE IF NOT EXISTS player_name_map (
    raw_name TEXT PRIMARY KEY,         -- exact bytes as stored in matches
    canonical_id TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'login' | 'manual' | 'auto' | 'fuzzy' | 'new' | 'review'
    confidence REAL,                   -- fuzzy ratio (1.0 for exact matches)
    created_at TEXT NOT NULL,
    FOREIGN KEY (canonical_id) REFERENCES players_canonical(canonical_id)
);
CREATE INDEX IF NOT EXISTS idx_player_name_map_canonical ON player_name_map(canonical_id);

-- Denormalized canonical_id on every player row, for fast joins. Backfilled by
-- canonicalize.py and maintained going forward by sync.py on insert.
-- (SQLite doesn't support IF NOT EXISTS on ALTER TABLE; canonicalize.py handles add safely.)

-- Lifetime totals scraped from stats.quakeworld.nu (one row per player, updated each sync).
CREATE TABLE IF NOT EXISTS career_totals (
    player_name TEXT PRIMARY KEY,
    total_matches INTEGER,
    total_4on4 INTEGER,
    total_2on2 INTEGER,
    total_1on1 INTEGER,
    total_time_mins INTEGER,
    total_frags INTEGER,
    fpm REAL,
    scraped_at TEXT NOT NULL
);

-- Community-sourced spawn points + teleport pairs per map, plus a cached copy
-- of the map's loc/triangle geometry (from the mvd_analyzer maps endpoint) so
-- the annotator UI can render without hitting an external preview URL at
-- runtime. One row per map.
--   spawns:   [{x,y,z,loc}]
--   teles:    [{from:{x,y,z,loc}, to:{x,y,z,loc}, bidir:bool}]
--   geometry: {map,version,bounds,locs:[{name,z,tris:[...]}]}  (cached, read-only)
--   locked:   when true, the annotator serves read-only — set once spawn+tele
--             data for a map is confirmed complete (gates community editing).
CREATE TABLE IF NOT EXISTS map_annotations (
    map         TEXT PRIMARY KEY,
    spawns      JSONB NOT NULL DEFAULT '[]'::jsonb,
    teles       JSONB NOT NULL DEFAULT '[]'::jsonb,
    geometry    JSONB,
    locked      BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Player hardware/config profiles (sens, mouse, binds, etc.) + geo for the
-- player map. Seeded from the community Google Sheet (104 players), then
-- per-user editable. `canonical_id` links to a known player when the sheet
-- nick matched; otherwise null and we keep the raw nick for later linking.
-- `config` is a free-form JSONB bag so we can add fields without migrations
-- (sens_cm360, dpi, grip, hand, movement, accel, mouse, mousepad, fov,
--  resolution, refresh, binds{rl,lg,gl,...}, etc.).
CREATE TABLE IF NOT EXISTS player_configs (
    canonical_id  TEXT,
    nick          TEXT NOT NULL,
    nationality   TEXT,          -- 2-letter-ish code from the sheet (PL, SE, ...)
    lat           DOUBLE PRECISION,
    lon           DOUBLE PRECISION,
    config        JSONB NOT NULL DEFAULT '{}'::jsonb,
    source        TEXT,          -- 'sheet' | 'user' | 'admin'
    updated_by    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_player_configs_cid
    ON player_configs(canonical_id) WHERE canonical_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_player_configs_nick ON player_configs(LOWER(nick));

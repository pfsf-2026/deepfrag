#!/usr/bin/env python3
"""Speakeasy 2v2 ladder — schema + movement engine.

Rungs are integer positions, 1 = top. Rules (locked w/ Peter 2026-06-04):
  - Challenge 1 or 2 rungs up.
  - Win (1- OR 2-rung challenge) → straight FULL SWAP: the winning lower team and
    the losing higher team exchange rungs; nothing in between moves (rung 5 beats
    rung 3 → 5↔3, rung 4 untouched).
  - Forfeit (challenged doesn't play within the window) → challenged drops 1 rung
    (swaps with the team directly below), regardless of 1- or 2-rung challenge.
  - Loser waits 1 week before re-challenging; winner may re-challenge immediately.
King of the Hill = current rung-1 team; weeks-held derived from ladder_movements.

Multi-ladder (a 4s ladder drops in later via a separate ladders row + team_size).
DB-backed (psycopg2 cursor passed in), mirrors the rest of the codebase.
"""
from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS ladders (
  id           BIGSERIAL PRIMARY KEY,
  name         TEXT NOT NULL,
  season       TEXT,
  team_size    INT  NOT NULL DEFAULT 2,
  map_pool     JSONB NOT NULL DEFAULT '[]',   -- ["aerowalk","ztndm3",...]
  rules        JSONB NOT NULL DEFAULT '{}',   -- {rung_jump:2, forfeit_days:7, best_of:3, ping_cap:null}
  status       TEXT NOT NULL DEFAULT 'active', -- active | archived
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ladder_teams (
  id           BIGSERIAL PRIMARY KEY,
  ladder_id    BIGINT NOT NULL REFERENCES ladders(id),
  name         TEXT NOT NULL,
  members      JSONB NOT NULL DEFAULT '[]',   -- [canonical_id, ...] (synced from Discord/captain)
  rung         INT,                            -- 1 = top; NULL while pending placement (bottom)
  active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT now(),
  disbanded_at TIMESTAMPTZ,
  UNIQUE (ladder_id, name)
);
CREATE INDEX IF NOT EXISTS ladder_teams_rung ON ladder_teams (ladder_id, rung);

CREATE TABLE IF NOT EXISTS ladder_challenges (
  id            BIGSERIAL PRIMARY KEY,
  ladder_id     BIGINT NOT NULL REFERENCES ladders(id),
  challenger_id BIGINT NOT NULL REFERENCES ladder_teams(id),
  challenged_id BIGINT NOT NULL REFERENCES ladder_teams(id),
  rungs_up      INT,                            -- 1 or 2 (snapshot at challenge time)
  status        TEXT NOT NULL DEFAULT 'open',   -- open|scheduled|played|forfeited|expired|cancelled
  proposed      JSONB DEFAULT '[]',             -- date/time negotiation log
  agreed_at     TIMESTAMPTZ,
  deadline      TIMESTAMPTZ,                    -- play-by-or-forfeit
  created_at    TIMESTAMPTZ DEFAULT now(),
  resolved_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ladder_challenges_open ON ladder_challenges (ladder_id, status);

CREATE TABLE IF NOT EXISTS ladder_matches (
  id            BIGSERIAL PRIMARY KEY,
  ladder_id     BIGINT NOT NULL REFERENCES ladders(id),
  challenge_id  BIGINT REFERENCES ladder_challenges(id),
  team_a_id     BIGINT NOT NULL REFERENCES ladder_teams(id),
  team_b_id     BIGINT NOT NULL REFERENCES ladder_teams(id),
  maps          JSONB DEFAULT '[]',            -- [{map, a_frags, b_frags, hub_game_id}]
  score_a       INT, score_b INT,              -- maps won (bo3)
  winner_id     BIGINT REFERENCES ladder_teams(id),
  hub_game_ids  JSONB DEFAULT '[]',
  played_at     TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ladder_movements (
  id          BIGSERIAL PRIMARY KEY,
  ladder_id   BIGINT NOT NULL REFERENCES ladders(id),
  team_id     BIGINT NOT NULL REFERENCES ladder_teams(id),
  from_rung   INT, to_rung INT,
  reason      TEXT,                             -- win | loss | forfeit | seed | join
  match_id    BIGINT REFERENCES ladder_matches(id),
  at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ladder_movements_koth ON ladder_movements (ladder_id, to_rung, at);
"""


def ensure_schema(cur):
    cur.execute(DDL)
    # Self-serve team signup additions (idempotent). Teams created by captains
    # start status='pending' + active=false (hidden from the board) until an
    # admin approves; logo stored in-DB (small ladder, no bucket needed).
    cur.execute("""
        ALTER TABLE ladder_teams ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
        ALTER TABLE ladder_teams ADD COLUMN IF NOT EXISTS logo BYTEA;
        ALTER TABLE ladder_teams ADD COLUMN IF NOT EXISTS logo_type TEXT;
        ALTER TABLE ladder_teams ADD COLUMN IF NOT EXISTS created_by TEXT;
        ALTER TABLE ladder_teams ADD COLUMN IF NOT EXISTS tag TEXT;
    """)
    # Scheduler: teams propose availability slots (proposed JSONB) back and forth;
    # proposed_by = team that posted the current slots (the OTHER team picks or
    # counter-proposes). agreed_at + server recorded once a slot is picked.
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS server TEXT")
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS proposed_by BIGINT")
    # Reminder + forfeit-clock bookkeeping (fired-once flags, set by the cron tick).
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS reminded_24h BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS reminded_soon BOOLEAN NOT NULL DEFAULT FALSE")  # ~1h
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS reminded_10m BOOLEAN NOT NULL DEFAULT FALSE")   # ~10m
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS overdue_flagged BOOLEAN NOT NULL DEFAULT FALSE")
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS reminded_unsched_3d BOOLEAN NOT NULL DEFAULT FALSE")
    # Set when auto-resolve found a complete Bo3 but not all 4 players matched
    # (roster id mismatch) — posts a manual-review warning once, never resolves.
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS flagged_review BOOLEAN NOT NULL DEFAULT FALSE")
    # Per-individual scheduling: each CHALLENGED player picks the offered slots they
    # can do -> {canonical_id: [iso, ...]}. When both have picked, the match
    # auto-schedules at the earliest slot common to both.
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS picks JSONB NOT NULL DEFAULT '{}'::jsonb")


def standings(cur, ladder_id):
    cur.execute("""SELECT id, name, tag, members, rung, active, (logo IS NOT NULL) AS has_logo
                   FROM ladder_teams
                   WHERE ladder_id=%s AND active ORDER BY rung NULLS LAST, id""", (ladder_id,))
    return cur.fetchall()


def _team(cur, team_id):
    cur.execute("SELECT id, ladder_id, rung FROM ladder_teams WHERE id=%s", (team_id,))
    return cur.fetchone()


def _set_rung(cur, team_id, rung, ladder_id, reason, match_id=None, from_rung=None):
    cur.execute("UPDATE ladder_teams SET rung=%s WHERE id=%s", (rung, team_id))
    cur.execute("""INSERT INTO ladder_movements (ladder_id, team_id, from_rung, to_rung, reason, match_id)
                   VALUES (%s,%s,%s,%s,%s,%s)""", (ladder_id, team_id, from_rung, rung, reason, match_id))


def apply_win(cur, ladder_id, challenger_id, challenged_id, match_id=None):
    """Challenger (lower rung number is higher; challenger is BELOW = larger rung)
    beat the challenged team → a STRAIGHT FULL SWAP between exactly the two teams
    that played. The winning lower team takes the challenged team's rung and the
    losing higher team takes the challenger's old rung; NO other team moves,
    regardless of a 1- or 2-rung gap (e.g. rung 5 beats rung 3 → 5↔3, rung 4
    untouched). Inactive / NULL-rung teams are never disturbed. Returns the
    affected {team_id: new_rung}."""
    cr = _team(cur, challenger_id)["rung"]
    hr = _team(cur, challenged_id)["rung"]
    # Straight two-team swap: winner (challenger) takes the challenged rung,
    # loser (challenged) takes the challenger's old rung. Nothing in between moves.
    _set_rung(cur, challenger_id, hr, ladder_id, "win", match_id, cr)
    _set_rung(cur, challenged_id, cr, ladder_id, "loss", match_id, hr)
    return {challenger_id: hr, challenged_id: cr}


def apply_forfeit(cur, ladder_id, challenged_id, drop=1, match_id=None):
    """Challenged team failed to play in time → it drops by the challenge span:
    1 rung for a 1-rung challenge, 2 for a 2-rung one. It swaps with the team
    `drop` rungs below (normally the challenger), so that team climbs into the
    vacated rung — the same swap model as a challenger win. If there aren't
    `drop` teams below, it falls to the bottom (drops as far as it can)."""
    drop = max(1, int(drop or 1))
    hr = _team(cur, challenged_id)["rung"]
    cur.execute("""SELECT id, rung FROM ladder_teams WHERE ladder_id=%s AND active AND rung=%s""",
                (ladder_id, hr + drop))
    below = cur.fetchone()
    if not below:  # not enough teams below to drop the full span — clamp to the bottom
        cur.execute("""SELECT id, rung FROM ladder_teams WHERE ladder_id=%s AND active AND rung>%s
                       ORDER BY rung DESC LIMIT 1""", (ladder_id, hr))
        below = cur.fetchone()
    if not below:
        return {}  # already at the bottom; nowhere to drop
    _set_rung(cur, challenged_id, below["rung"], ladder_id, "forfeit", match_id, hr)
    _set_rung(cur, below["id"], hr, ladder_id, "win", match_id, below["rung"])
    return {challenged_id: below["rung"], below["id"]: hr}


def place_new_team(cur, ladder_id, team_id):
    """New team enters at the bottom rung."""
    cur.execute("SELECT COALESCE(MAX(rung), 0) m FROM ladder_teams WHERE ladder_id=%s AND active", (ladder_id,))
    bottom = cur.fetchone()["m"] + 1
    _set_rung(cur, team_id, bottom, ladder_id, "join")
    return bottom

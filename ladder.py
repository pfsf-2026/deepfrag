#!/usr/bin/env python3
"""Speakeasy 2v2 ladder — schema + movement engine.

Rungs are integer positions, 1 = top. Rules (locked w/ Peter 2026-06-04):
  - Challenge 1 or 2 rungs up.
  - Win, 1-rung challenge  → straight SWAP with the challenged team.
  - Win, 2-rung challenge  → challenger moves UP 2 (takes challenged's rung); the
    two teams it passed each drop 1.
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
    beat the challenged team. 1-rung gap → swap. 2-rung gap → challenger up 2,
    the two passed teams each drop 1. Returns the affected {team_id: new_rung}."""
    cr = _team(cur, challenger_id)["rung"]
    hr = _team(cur, challenged_id)["rung"]
    gap = cr - hr  # positive: challenger is that many rungs below the challenged
    moves = {}
    if gap <= 1:
        # straight swap
        _set_rung(cur, challenger_id, hr, ladder_id, "win", match_id, cr)
        _set_rung(cur, challenged_id, cr, ladder_id, "loss", match_id, hr)
        moves = {challenger_id: hr, challenged_id: cr}
    else:
        # 2-rung jump: challenger takes hr; teams currently at hr..cr-1 each +1.
        cur.execute("""SELECT id, rung FROM ladder_teams
                       WHERE ladder_id=%s AND active AND rung >= %s AND rung < %s
                       ORDER BY rung""", (ladder_id, hr, cr))
        passed = cur.fetchall()  # includes the challenged team at hr
        for t in passed:
            _set_rung(cur, t["id"], t["rung"] + 1, ladder_id,
                      "loss" if t["id"] == challenged_id else "shift", match_id, t["rung"])
            moves[t["id"]] = t["rung"] + 1
        _set_rung(cur, challenger_id, hr, ladder_id, "win", match_id, cr)
        moves[challenger_id] = hr
    return moves


def apply_forfeit(cur, ladder_id, challenged_id, match_id=None):
    """Challenged team failed to play in time → drops 1 rung (swaps with the team
    directly below it), regardless of whether it was a 1- or 2-rung challenge."""
    hr = _team(cur, challenged_id)["rung"]
    cur.execute("""SELECT id, rung FROM ladder_teams WHERE ladder_id=%s AND active AND rung=%s""",
                (ladder_id, hr + 1))
    below = cur.fetchone()
    if not below:
        return {}  # already at the bottom; nowhere to drop
    _set_rung(cur, challenged_id, hr + 1, ladder_id, "forfeit", match_id, hr)
    _set_rung(cur, below["id"], hr, ladder_id, "win", match_id, hr + 1)
    return {challenged_id: hr + 1, below["id"]: hr}


def place_new_team(cur, ladder_id, team_id):
    """New team enters at the bottom rung."""
    cur.execute("SELECT COALESCE(MAX(rung), 0) m FROM ladder_teams WHERE ladder_id=%s AND active", (ladder_id,))
    bottom = cur.fetchone()["m"] + 1
    _set_rung(cur, team_id, bottom, ladder_id, "join")
    return bottom

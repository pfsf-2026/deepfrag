#!/usr/bin/env python3
"""DeepFrag King-of-the-Hill ladders — schema + movement engine.

One engine, many ladders: every table is keyed by ladder_id and a "team" is a
roster of `team_size` canonical ids (2 for the 2v2 ladder, 1 for the 1v1 duel
ladder added 2026-09-17). `ladders.mode` ('2on2' | '1on1' | '4on4') is the hub
match_mode the auto-resolver searches for that ladder's games.

Rungs are integer positions, 1 = top. Rules (locked w/ Peter 2026-06-04):
  - Challenge 1 or 2 rungs up.
  - Win (1- OR 2-rung challenge) → straight FULL SWAP: the winning lower team and
    the losing higher team exchange rungs; nothing in between moves (rung 5 beats
    rung 3 → 5↔3, rung 4 untouched).
  - Forfeit (challenged doesn't play within the window) → challenged drops 1 rung
    (swaps with the team directly below), regardless of 1- or 2-rung challenge.
  - Loser waits 1 week before re-challenging; winner may re-challenge immediately.
King of the Hill = current rung-1 team; weeks-held derived from ladder_movements.

DB-backed (psycopg2 cursor passed in), mirrors the rest of the codebase.
"""
from __future__ import annotations

MODE_BY_SIZE = {1: "1on1", 2: "2on2", 4: "4on4"}


def mode_for_size(team_size) -> str:
    """Hub match_mode for a roster size (1 → '1on1', 2 → '2on2', 4 → '4on4')."""
    n = int(team_size or 2)
    return MODE_BY_SIZE.get(n, f"{n}on{n}")


def search_window(agreed_at, deadline=None, created_at=None, now=None):
    """(lo, hi) datetimes the game matcher searches for a challenge's games.

    Scheduled through the site (agreed_at set): from the moment the challenge
    was ISSUED (created_at) to 7 days after the agreed slot, stretched to the
    deadline when that is later. Rule set by Peter 2026-09-18 after ch78
    (WoD/Habs) was played three days BEFORE its scheduled slot and the old
    slot-centred window (-18h/+30h) never saw the games. Never scheduled on
    the site: creation to deadline. Nothing known: the last 3 days. The
    full-roster gate and the one-game-one-match reuse guard are what keep a
    wide window safe.
    """
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    if agreed_at:
        lo = agreed_at - timedelta(hours=18)
        if created_at and created_at < lo:
            lo = created_at
        hi = agreed_at + timedelta(days=7)
        if deadline is not None and deadline > hi:
            hi = deadline
        return lo, hi
    if created_at:
        return created_at, (deadline or (now + timedelta(hours=1)))
    return now - timedelta(days=3), now + timedelta(hours=1)


def shape(cur, ladder_id):
    """{mode, team_size, wins_needed, rules} for a ladder — what the game matcher
    and the roster gates need. Defaults to the 2v2 shape when the ladder is
    unknown (legacy callers)."""
    if ladder_id is not None:
        cur.execute("SELECT mode, team_size, rules FROM ladders WHERE id=%s", (ladder_id,))
        row = cur.fetchone()
        if row:
            size = int(row["team_size"] or 2)
            rules = row["rules"] or {}
            best_of = int(rules.get("best_of") or 3)
            return {"mode": row["mode"] or mode_for_size(size), "team_size": size,
                    "wins_needed": max(1, (best_of + 1) // 2), "rules": rules}
    return {"mode": "2on2", "team_size": 2, "wins_needed": 2, "rules": {}}

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
    # 2026-09-17: multi-ladder. mode = the hub match_mode this ladder's games are
    # played in; backfilled from team_size for rows created before the column.
    cur.execute("ALTER TABLE ladders ADD COLUMN IF NOT EXISTS mode TEXT")
    cur.execute("""UPDATE ladders SET mode = CASE team_size WHEN 1 THEN '1on1' WHEN 2 THEN '2on2' WHEN 4 THEN '4on4'
                                                ELSE team_size::text || 'on' || team_size::text END
                   WHERE mode IS NULL""")
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS server TEXT")
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS proposed_by BIGINT")
    # 2026-09-06: when the CURRENT offer was posted + the full proposal history
    # ({at, by, slots} per post). The forfeit clock needs proposed_at — a
    # challenger who ignores the challenged team's offer for days and then
    # re-posts hours before the deadline must not flip the blame (ch71).
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS proposed_at TIMESTAMPTZ")
    cur.execute("ALTER TABLE ladder_challenges ADD COLUMN IF NOT EXISTS proposal_log JSONB NOT NULL DEFAULT '[]'::jsonb")
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
    # Player-submitted match reports (2026-08-02): "we played it, it didn't
    # record" self-service. Validated through the same gates as auto-resolve;
    # pending = submitted before the games were ingested (tick retries).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ladder_match_reports (
          id           BIGSERIAL PRIMARY KEY,
          challenge_id BIGINT NOT NULL REFERENCES ladder_challenges(id),
          reporter     TEXT,                              -- canonical_id (or discord username)
          game_ids     JSONB NOT NULL,                    -- [hub_game_id, ...] as submitted
          status       TEXT NOT NULL DEFAULT 'pending',   -- pending | recorded | flagged | cancelled
          note         TEXT,
          created_at   TIMESTAMPTZ DEFAULT now(),
          resolved_at  TIMESTAMPTZ
        )
    """)


def standings(cur, ladder_id):
    cur.execute("""SELECT id, name, tag, members, rung, active, (logo IS NOT NULL) AS has_logo
                   FROM ladder_teams
                   WHERE ladder_id=%s AND active ORDER BY rung NULLS LAST, id""", (ladder_id,))
    return cur.fetchall()


def archive_team(cur, team_id):
    """Retire a team from the board: drop it from standings, close its rung
    gap, cancel its open/scheduled challenges. Stats and match history stay
    intact — the team page still resolves by id; the team just stops
    occupying a rung. Idempotent (archiving an archived team is a no-op)."""
    cur.execute("SELECT id, ladder_id, rung, status FROM ladder_teams WHERE id=%s", (team_id,))
    t = cur.fetchone()
    if not t or t["status"] == "archived":
        return None
    ladder_id, old_rung = t["ladder_id"], t["rung"]
    cur.execute("""UPDATE ladder_challenges SET status='cancelled'
                   WHERE (challenger_id=%s OR challenged_id=%s)
                     AND status IN ('open','scheduled')
                   RETURNING id""", (team_id, team_id))
    cancelled = [r["id"] for r in cur.fetchall()]
    cur.execute("UPDATE ladder_teams SET status='archived', active=FALSE, rung=NULL WHERE id=%s", (team_id,))
    cur.execute("""INSERT INTO ladder_movements (ladder_id, team_id, from_rung, to_rung, reason)
                   VALUES (%s,%s,%s,NULL,'archived')""", (ladder_id, team_id, old_rung))
    if old_rung is not None:
        cur.execute("""SELECT id, rung FROM ladder_teams
                       WHERE ladder_id=%s AND active AND rung > %s ORDER BY rung""",
                    (ladder_id, old_rung))
        for r in cur.fetchall():
            _set_rung(cur, r["id"], r["rung"] - 1, ladder_id, "compact-archived", from_rung=r["rung"])
    return {"cancelled_challenges": cancelled, "from_rung": old_rung}


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

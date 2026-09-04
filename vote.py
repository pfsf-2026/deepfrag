"""Community polls — standalone vote pages on the app.

First poll (Nin's request, 2026-08-31): the upcoming KOTH **duel** league.
Two questions in one ballot:
  1. Map-pool size for a bo5 format — 5 / 7 / 9 / 11 maps.
  2. Which maps belong in the pool, clicked in preference order (ranked).

Voting is deliberately low-friction (Nin: "don't want too many hurdles"):
no login — you vote as your in-game handle. "No randoms" is enforced by the
handle having to resolve to a KNOWN DeepFrag player (someone with rated
games in the corpus). One ballot per canonical player; re-submitting
updates it. Honor-system caveat, accepted knowingly: without auth, someone
could vote as a player they are not — this is a community map poll, not an
election, and the tradeoff was chosen explicitly.

Candidate maps = the 16 most-played duel maps in the DeepFrag corpus at poll
creation. Map scoring is Borda-style: rank 1 earns MAX_RANKED points, each
rank below one fewer — plus first-choice and times-picked counts so the raw
preference signal survives the aggregation.
"""

import json

from fastapi import APIRouter, Body, Header, HTTPException, Response

router = APIRouter()

POLL_ID = "duel-league-2026"
POOL_SIZES = [5, 7, 9, 11]
# Top-16 duel maps by distinct rated players, mined 2026-08-31.
CANDIDATE_MAPS = [
    "aerowalk", "ztndm3", "dm4", "bravado", "dm6", "dm2", "skull", "pocket",
    "metron", "shifter", "katt", "catalyst", "toxicity", "tron", "zite", "sabbath",
    "nova",  # added 2026-08-31 by request
    "ultrav",  # added 2026-09-04 by request
]
MAX_RANKED = 11  # matches the largest pool option


def _deps():
    # Lazy import: api.py includes this router at module bottom, so importing
    # back at call time is safe (same pattern as connector.py).
    from api import pg, _current_user
    return pg, _current_user


def _ensure(cur):
    # v2 table (poll_ballots): keyed on canonical player id, not discord id —
    # Nin's no-auth revision. The v1 poll_votes table was created but never
    # collected a ballot; left in place, unused.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS poll_ballots (
          poll_id     TEXT NOT NULL,
          voter_id    TEXT NOT NULL,
          handle      TEXT,
          pool_size   INT,
          map_ranking JSONB NOT NULL DEFAULT '[]',
          updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (poll_id, voter_id)
        )""")


def _results(cur):
    cur.execute("SELECT pool_size, map_ranking FROM poll_ballots WHERE poll_id=%s", (POLL_ID,))
    rows = cur.fetchall()
    sizes = {str(s): 0 for s in POOL_SIZES}
    maps = {m: {"points": 0, "first": 0, "picks": 0} for m in CANDIDATE_MAPS}
    for r in rows:
        if r["pool_size"] in POOL_SIZES:
            sizes[str(r["pool_size"])] += 1
        for i, m in enumerate(r["map_ranking"] or []):
            if m in maps and i < MAX_RANKED:
                maps[m]["points"] += MAX_RANKED - i
                maps[m]["picks"] += 1
                if i == 0:
                    maps[m]["first"] += 1
    board = sorted(({"map": m, **v} for m, v in maps.items()),
                   key=lambda x: (-x["points"], -x["picks"], x["map"]))
    return {"votes": len(rows), "pool_size": sizes, "maps": board}


def _my_vote(cur, voter_id):
    cur.execute("""SELECT handle, pool_size, map_ranking, updated_at FROM poll_ballots
                   WHERE poll_id=%s AND voter_id=%s""", (POLL_ID, voter_id))
    r = cur.fetchone()
    return ({"handle": r["handle"], "pool_size": r["pool_size"], "map_ranking": r["map_ranking"],
             "updated_at": str(r["updated_at"])} if r else None)


@router.get("/api/vote/duel-league")
def vote_get(response: Response, player: str | None = None):
    """Poll config + results. `player` (canonical_id) returns that player's
    stored ballot so a returning voter sees their own picks prefilled."""
    pg, _ = _deps()
    response.headers["Cache-Control"] = "no-store"
    with pg() as conn:
        cur = conn.cursor()
        _ensure(cur)
        my = _my_vote(cur, player.strip().lower()) if player else None
        out = {
            "poll_id": POLL_ID,
            "question_1": {"label": "Total map pool for the bo5 format", "options": POOL_SIZES},
            "question_2": {"label": "Click the maps you want in the pool, in ranking order",
                           "candidates": CANDIDATE_MAPS, "max_ranked": MAX_RANKED},
            "my_vote": my,
            "results": _results(cur),
        }
        conn.commit()
    return out


@router.post("/api/vote/duel-league")
def vote_post(body: dict = Body(...)):
    pg, _ = _deps()
    # "No randoms": the handle must resolve to a known player in the corpus.
    handle = (body.get("handle") or "").strip()
    if not handle:
        raise HTTPException(400, "handle required — vote as your in-game name")

    pool_size = body.get("pool_size")
    if pool_size not in POOL_SIZES:
        raise HTTPException(400, f"pool_size must be one of {POOL_SIZES}")
    ranking = body.get("map_ranking")
    if not isinstance(ranking, list) or not ranking:
        raise HTTPException(400, "map_ranking must be a non-empty list of maps in preference order")
    if len(ranking) != len(set(ranking)):
        raise HTTPException(400, "map_ranking has duplicate maps")
    if len(ranking) > MAX_RANKED:
        raise HTTPException(400, f"rank at most {MAX_RANKED} maps")
    bad = [m for m in ranking if m not in CANDIDATE_MAPS]
    if bad:
        raise HTTPException(400, f"not on the ballot: {bad}")

    with pg() as conn:
        cur = conn.cursor()
        _ensure(cur)
        # Resolve handle -> canonical player (exact canonical_id, or exact
        # display-name match, case-insensitive). Must exist in the corpus.
        cur.execute("""SELECT pc.canonical_id, COALESCE(pc.display_name, pc.canonical_id) AS display
                       FROM players_canonical pc
                       WHERE pc.canonical_id = %(h)s OR LOWER(pc.display_name) = LOWER(%(h)s)
                       LIMIT 1""", {"h": handle.lower()})
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "handle not found — use the in-game name DeepFrag knows you by")
        voter_id, display = row["canonical_id"], row["display"]
        cur.execute("""
            INSERT INTO poll_ballots (poll_id, voter_id, handle, pool_size, map_ranking, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (poll_id, voter_id) DO UPDATE
              SET pool_size=EXCLUDED.pool_size, map_ranking=EXCLUDED.map_ranking,
                  handle=EXCLUDED.handle, updated_at=now()
        """, (POLL_ID, voter_id, display, pool_size, json.dumps(ranking)))
        my = _my_vote(cur, voter_id)
        results = _results(cur)
        conn.commit()
    return {"ok": True, "voter_id": voter_id, "my_vote": my, "results": results}

"""Community polls — standalone vote pages on the app.

First poll (Nin's request, 2026-08-31): the upcoming KOTH **duel** league.
Two questions in one ballot:
  1. Map-pool size for a bo3 format — 5 / 7 / 9 / 11 maps.
  2. Which maps belong in the pool, clicked in preference order (ranked).

Voting requires Discord auth (the app's existing OAuth) — deliberately NOT
gated on 2v2 ladder membership: this is the wider community's league to shape.
One ballot per Discord account, re-submitting updates it. Results are shown
only after you have voted (admins can always see them).

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
]
MAX_RANKED = 11  # matches the largest pool option


def _deps():
    # Lazy import: api.py includes this router at module bottom, so importing
    # back at call time is safe (same pattern as connector.py).
    from api import pg, _current_user
    return pg, _current_user


def _ensure(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS poll_votes (
          poll_id     TEXT NOT NULL,
          discord_id  TEXT NOT NULL,
          username    TEXT,
          pool_size   INT,
          map_ranking JSONB NOT NULL DEFAULT '[]',
          updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (poll_id, discord_id)
        )""")


def _results(cur):
    cur.execute("SELECT pool_size, map_ranking FROM poll_votes WHERE poll_id=%s", (POLL_ID,))
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


def _my_vote(cur, discord_id):
    cur.execute("""SELECT pool_size, map_ranking, updated_at FROM poll_votes
                   WHERE poll_id=%s AND discord_id=%s""", (POLL_ID, discord_id))
    r = cur.fetchone()
    return ({"pool_size": r["pool_size"], "map_ranking": r["map_ranking"],
             "updated_at": str(r["updated_at"])} if r else None)


@router.get("/api/vote/duel-league")
def vote_get(response: Response, authorization: str | None = Header(default=None)):
    pg, current_user = _deps()
    response.headers["Cache-Control"] = "no-store"
    user = current_user(authorization, required=False)
    with pg() as conn:
        cur = conn.cursor()
        _ensure(cur)
        my = _my_vote(cur, user["discord_id"]) if user else None
        show_results = bool(my) or bool(user and user.get("is_admin"))
        out = {
            "poll_id": POLL_ID,
            "question_1": {"label": "Total map pool for the bo3 format", "options": POOL_SIZES},
            "question_2": {"label": "Click the maps you want in the pool, in ranking order",
                           "candidates": CANDIDATE_MAPS, "max_ranked": MAX_RANKED},
            "logged_in": bool(user),
            "my_vote": my,
            "results": _results(cur) if show_results else None,
        }
        conn.commit()
    return out


@router.post("/api/vote/duel-league")
def vote_post(body: dict = Body(...), authorization: str | None = Header(default=None)):
    pg, current_user = _deps()
    user = current_user(authorization, required=True)

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
        cur.execute("""
            INSERT INTO poll_votes (poll_id, discord_id, username, pool_size, map_ranking, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (poll_id, discord_id) DO UPDATE
              SET pool_size=EXCLUDED.pool_size, map_ranking=EXCLUDED.map_ranking,
                  username=EXCLUDED.username, updated_at=now()
        """, (POLL_ID, user["discord_id"], user.get("global_name") or user.get("username"),
              pool_size, json.dumps(ranking)))
        my = _my_vote(cur, user["discord_id"])
        results = _results(cur)
        conn.commit()
    return {"ok": True, "my_vote": my, "results": results}

#!/usr/bin/env python3
"""Scheduling rules on the challenge endpoints (api.py), against a fake cursor.
Regressions from 2026-11-11 (Cronus vs BLooD): a counter-offer re-sent the old,
already-past slots; a time after the play-by deadline was dropped without a word;
an admin playing the match could act in the opponent's turn under their name.
Needs fastapi + psycopg2 importable (no database). Run: python tests/test_ladder_scheduling.py"""
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api  # noqa: E402
import ladder  # noqa: E402
import notify  # noqa: E402
from fastapi import HTTPException  # noqa: E402

CL, CD = 22, 35      # challenger (cronus), challenged (blood)
NOW = datetime.now(timezone.utc)


def iso(h):
    return (NOW + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class FakeCursor:
    def __init__(self, ch):
        self.ch = ch
        self.teams = {CL: ["cronus"], CD: ["blood"]}
        self._rows = []
        self.updates = []

    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        self._rows = []
        if q.startswith("SELECT c.challenger_id"):
            self._rows = [dict(self.ch, challenger="Cronus", challenged="BLooD")]
        elif q.startswith("SELECT id, members FROM ladder_teams WHERE id = ANY"):
            self._rows = [{"id": i, "members": self.teams[i]} for i in params[0]]
        elif q.startswith("SELECT members FROM ladder_teams WHERE id=%s"):
            self._rows = [{"members": self.teams[params[0]]}]
        elif q.startswith("UPDATE ladder_challenges SET proposed=%s"):
            self.updates.append(params)
            self.ch["proposed"] = json.loads(params[0])
            self.ch["proposed_by"] = params[1]
        elif q.startswith("UPDATE ladder_challenges SET agreed_at=%s"):
            self.updates.append(params)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur

    def commit(self):
        pass


def setup(ch, user):
    cur = FakeCursor(ch)

    @contextmanager
    def pg():
        yield FakeConn(cur)
    api.pg = pg
    api._current_user = lambda *a, **k: user
    api._notify_route = lambda *a, **k: None
    api._team_label = lambda c, tid: {CL: "Cronus", CD: "BLooD"}[tid]
    api._team_np = lambda c, tid: ("x", "")
    ladder.ensure_schema = lambda c: None
    sent = []
    notify.match_proposal = lambda *a, **k: sent.append((a, k))
    notify.game_scheduled = lambda *a, **k: sent.append(a)
    return cur, sent


def challenge(**kw):
    ch = {"challenger_id": CL, "challenged_id": CD, "proposed": [], "proposed_by": None, "status": "open",
          "rungs_up": 2, "deadline": NOW + timedelta(days=2), "proposal_log": [],
          "agreed_at": None, "picks": {}}
    ch.update(kw)
    return ch


def raises(fn, code):
    try:
        fn()
    except HTTPException as e:
        assert e.status_code == code, (e.status_code, e.detail)
        return e.detail
    raise AssertionError(f"expected HTTP {code}")


CASES = []


def check(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


BLOOD = {"canonical_id": "blood", "is_admin": True}      # an admin who plays in the match
CRONUS = {"canonical_id": "cronus", "is_admin": False}
STAFF = {"canonical_id": "nin", "is_admin": True}        # an admin not in it


@check("counter-offer drops past slots and never re-sends them as new times")
def _():
    old = [iso(-60), iso(-36)]
    cur, sent = setup(challenge(proposed=old, proposed_by=CL, proposal_log=[{}]), BLOOD)
    r = api.ladder_challenge_availability(1, None, slots=old + [iso(30)])
    assert r["slots"] == [iso(30)], r
    assert sent and sent[0][0][2] == [iso(30)]


@check("only past slots → 400, nothing posted")
def _():
    cur, sent = setup(challenge(proposed=[iso(-60)], proposed_by=CL, proposal_log=[{}]), BLOOD)
    raises(lambda: api.ladder_challenge_availability(1, None, slots=[iso(-60), iso(-30)]), 400)
    assert not cur.updates and not sent


@check("a slot after the deadline is refused, not dropped")
def _():
    cur, sent = setup(challenge(proposed=[iso(-60)], proposed_by=CL, proposal_log=[{}]), BLOOD)
    d = raises(lambda: api.ladder_challenge_availability(1, None, slots=[iso(10), iso(24 * 3)]), 400)
    assert "deadline" in d and not cur.updates


@check("re-posting the offer you were given → 400 (pick it instead)")
def _():
    offer = [iso(10), iso(20)]
    cur, sent = setup(challenge(proposed=offer, proposed_by=CL, proposal_log=[{}]), BLOOD)
    raises(lambda: api.ladder_challenge_availability(1, None, slots=list(offer)), 400)


@check("an admin who plays cannot post in the opponent's turn")
def _():
    cur, sent = setup(challenge(proposed=[iso(10)], proposed_by=CD, proposal_log=[{}]), BLOOD)
    raises(lambda: api.ladder_challenge_availability(1, None, slots=[iso(20)]), 403)


@check("an admin not in the match may post for the turn side")
def _():
    cur, sent = setup(challenge(proposed=[iso(10)], proposed_by=CD, proposal_log=[{}]), STAFF)
    r = api.ladder_challenge_availability(1, None, slots=[iso(20)])
    assert r["proposed_by"] == CL


@check("opening offer by an admin who plays is posted as their own side")
def _():
    cur, sent = setup(challenge(), BLOOD)
    r = api.ladder_challenge_availability(1, None, slots=[iso(10), iso(34)])
    assert r["proposed_by"] == CD


@check("an admin who plays cannot pick their own offer")
def _():
    cur, sent = setup(challenge(proposed=[iso(10)], proposed_by=CD), BLOOD)
    raises(lambda: api.ladder_challenge_schedule(1, None, slot=iso(10), server=None), 403)


@check("the other player picks the offer → scheduled")
def _():
    cur, sent = setup(challenge(proposed=[iso(10)], proposed_by=CD), CRONUS)
    r = api.ladder_challenge_schedule(1, None, slot=iso(10), server=None)
    assert r["status"] == "scheduled"


def main():
    ok = 0
    for name, fn in CASES:
        try:
            fn()
            ok += 1
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {name}: {e!r}")
    print(f"{ok}/{len(CASES)} passed")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())

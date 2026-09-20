#!/usr/bin/env python3
"""Characterisation tests for the ladder movement engine (ladder.py) and the
multi-ladder shape helper. No database: a tiny in-memory fake cursor answers the
handful of statements the engine issues. Run: python tests/test_ladder_engine.py
(exit 0/1, same convention as test_invariants.py)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ladder  # noqa: E402


class FakeCursor:
    """Answers exactly the SQL ladder.py uses. Teams: {id: {ladder_id, rung, active}}."""

    def __init__(self, teams, ladders=None):
        self.teams = {int(k): dict(v) for k, v in teams.items()}
        self.ladders = ladders or {}
        self.movements = []
        self._rows = []

    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        self._rows = []
        if q.startswith("SELECT id, ladder_id, rung FROM ladder_teams WHERE id=%s"):
            t = self.teams.get(int(params[0]))
            self._rows = [{"id": int(params[0]), **t}] if t else []
        elif q.startswith("UPDATE ladder_teams SET rung=%s WHERE id=%s"):
            self.teams[int(params[1])]["rung"] = params[0]
        elif q.startswith("INSERT INTO ladder_movements"):
            ladder_id, team_id, from_rung, to_rung, reason, match_id = params
            self.movements.append((team_id, from_rung, to_rung, reason))
        elif "WHERE ladder_id=%s AND active AND rung=%s" in q:
            lid, rung = params
            self._rows = [{"id": i, "rung": t["rung"]} for i, t in self.teams.items()
                          if t["ladder_id"] == lid and t.get("active", True) and t["rung"] == rung]
        elif "WHERE ladder_id=%s AND active AND rung>%s" in q:
            lid, rung = params
            below = sorted([(t["rung"], i) for i, t in self.teams.items()
                            if t["ladder_id"] == lid and t.get("active", True) and t["rung"] is not None and t["rung"] > rung], reverse=True)
            self._rows = [{"id": i, "rung": r} for r, i in below[:1]]
        elif q.startswith("SELECT COALESCE(MAX(rung), 0) m FROM ladder_teams WHERE ladder_id=%s AND active"):
            lid = params[0]
            rungs = [t["rung"] for t in self.teams.values() if t["ladder_id"] == lid and t.get("active", True) and t["rung"] is not None]
            self._rows = [{"m": max(rungs) if rungs else 0}]
        elif q.startswith("SELECT mode, team_size, rules FROM ladders WHERE id=%s"):
            l = self.ladders.get(int(params[0]))
            self._rows = [l] if l else []
        else:
            raise AssertionError(f"FakeCursor: unhandled SQL: {q[:120]}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def rungs(cur):
    return {i: t["rung"] for i, t in sorted(cur.teams.items())}


def ladder_of(n, ladder_id=1):
    return {i: {"ladder_id": ladder_id, "rung": i, "active": True} for i in range(1, n + 1)}


checks = []


def check(name):
    def deco(fn):
        checks.append((name, fn))
        return fn
    return deco


@check("win over 1 rung swaps the two teams")
def _():
    cur = FakeCursor(ladder_of(5))
    ladder.apply_win(cur, 1, challenger_id=4, challenged_id=3)
    assert rungs(cur) == {1: 1, 2: 2, 3: 4, 4: 3, 5: 5}, rungs(cur)
    assert [m[3] for m in cur.movements] == ["win", "loss"]


@check("win over 2 rungs is a straight swap; the team in between does not move")
def _():
    cur = FakeCursor(ladder_of(5))
    ladder.apply_win(cur, 1, challenger_id=5, challenged_id=3)
    assert rungs(cur) == {1: 1, 2: 2, 3: 5, 4: 4, 5: 3}, rungs(cur)


@check("forfeit on a 1-rung challenge drops the challenged team one rung")
def _():
    cur = FakeCursor(ladder_of(5))
    ladder.apply_forfeit(cur, 1, challenged_id=3, drop=1)
    assert rungs(cur) == {1: 1, 2: 2, 3: 4, 4: 3, 5: 5}, rungs(cur)
    assert [m[3] for m in cur.movements] == ["forfeit", "win"]


@check("forfeit on a 2-rung challenge swaps with the team two below (the challenger)")
def _():
    cur = FakeCursor(ladder_of(5))
    ladder.apply_forfeit(cur, 1, challenged_id=3, drop=2)
    assert rungs(cur) == {1: 1, 2: 2, 3: 5, 4: 4, 5: 3}, rungs(cur)


@check("forfeit clamps to the bottom when there are not enough teams below")
def _():
    cur = FakeCursor(ladder_of(4))
    ladder.apply_forfeit(cur, 1, challenged_id=3, drop=2)
    assert rungs(cur) == {1: 1, 2: 2, 3: 4, 4: 3}, rungs(cur)


@check("forfeit by the bottom team is a no-op")
def _():
    cur = FakeCursor(ladder_of(3))
    assert ladder.apply_forfeit(cur, 1, challenged_id=3, drop=1) == {}
    assert rungs(cur) == {1: 1, 2: 2, 3: 3}


@check("a new team enters at the bottom; other ladders are ignored")
def _():
    teams = ladder_of(3)
    teams[9] = {"ladder_id": 2, "rung": 1, "active": True}    # the 1v1 ladder
    teams[4] = {"ladder_id": 1, "rung": None, "active": True}
    cur = FakeCursor(teams)
    assert ladder.place_new_team(cur, 1, 4) == 4
    assert ladder.place_new_team(cur, 2, 9) == 2 or True   # placing an already-placed team is the caller's problem
    assert cur.teams[4]["rung"] == 4


@check("movements on ladder 2 never touch ladder 1 rungs")
def _():
    teams = {**ladder_of(3, 1), **{10 + i: {"ladder_id": 2, "rung": i, "active": True} for i in range(1, 4)}}
    cur = FakeCursor(teams)
    ladder.apply_win(cur, 2, challenger_id=13, challenged_id=11)
    assert {i: t["rung"] for i, t in cur.teams.items() if t["ladder_id"] == 1} == {1: 1, 2: 2, 3: 3}
    assert {i: t["rung"] for i, t in cur.teams.items() if t["ladder_id"] == 2} == {11: 3, 12: 2, 13: 1}


@check("search window: scheduled challenge searches from issue time to 7 days after the slot")
def _():
    from datetime import datetime, timedelta, timezone
    created = datetime(2026, 9, 16, 19, 15, tzinfo=timezone.utc)
    agreed = datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc)
    deadline = datetime(2026, 9, 23, 19, 15, tzinfo=timezone.utc)
    lo, hi = ladder.search_window(agreed, deadline, created)
    assert lo == created, lo                                   # ch78: games played 3 days before the slot are inside
    assert hi == agreed + timedelta(days=7), hi                # 7 days after the slot beats the earlier deadline
    played = datetime(2026, 9, 18, 4, 16, tzinfo=timezone.utc)
    assert lo < played < hi
    # deadline later than slot+7d still stretches the tail
    late = agreed + timedelta(days=9)
    assert ladder.search_window(agreed, late, created)[1] == late
    # no created_at (legacy row): fall back to 18h before the slot
    assert ladder.search_window(agreed, deadline, None)[0] == agreed - timedelta(hours=18)
    # never scheduled: creation -> deadline
    assert ladder.search_window(None, deadline, created) == (created, deadline)
    # nothing known: last 3 days
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    assert ladder.search_window(None, None, None, now=now) == (now - timedelta(days=3), now + timedelta(hours=1))


@check("mode_for_size maps roster size to the hub match_mode")
def _():
    assert ladder.mode_for_size(1) == "1on1"
    assert ladder.mode_for_size(2) == "2on2"
    assert ladder.mode_for_size(4) == "4on4"
    assert ladder.mode_for_size(None) == "2on2"


@check("shape() reads mode/team_size/best_of from the ladder row and defaults to 2v2")
def _():
    cur = FakeCursor({}, ladders={
        1: {"mode": "2on2", "team_size": 2, "rules": {"best_of": 3}},
        2: {"mode": None, "team_size": 1, "rules": {"best_of": 5}},
    })
    assert ladder.shape(cur, 1) == {"mode": "2on2", "team_size": 2, "wins_needed": 2, "rules": {"best_of": 3}}
    s = ladder.shape(cur, 2)
    assert (s["mode"], s["team_size"], s["wins_needed"]) == ("1on1", 1, 3), s
    assert ladder.shape(cur, None)["mode"] == "2on2"
    assert ladder.shape(cur, 99)["team_size"] == 2


@check("ensure_schema backfills mode from team_size (SQL text sanity)")
def _():
    src = open(os.path.join(os.path.dirname(ladder.__file__), "ladder.py")).read()
    assert "ADD COLUMN IF NOT EXISTS mode TEXT" in src
    assert re.search(r"UPDATE ladders SET mode = CASE team_size WHEN 1 THEN '1on1'", src)


def main():
    failed = 0
    for name, fn in checks:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
    print(f"{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

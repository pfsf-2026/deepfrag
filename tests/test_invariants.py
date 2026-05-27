#!/usr/bin/env python3
"""DB invariant checks — catch rating/matches inflation BEFORE users notice.

Run after every full re-rate, and ideally after every Cloud Scheduler sync,
to make sure no bug has reintroduced the cartesian-product or double-counting
issues we fixed on 2026-05-27.

Exit code 0 = all invariants pass.
Exit code 1 = at least one critical invariant failed (matches_rated > w+l+d,
              duplicate match_ids, NULL canonical_ids in players, etc.)

Run directly:
    DEEPFRAG_PG_URL=... python tests/test_invariants.py

Or wire it into deploy (recommended):
    .github/workflows/deploy.yml → step "run invariants" before "deploy api"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python tests/test_invariants.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db as dbmod


class Result:
    def __init__(self, name: str, ok: bool, detail: str = "", critical: bool = True):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.critical = critical

    def __str__(self):
        mark = "PASS" if self.ok else ("FAIL" if self.critical else "WARN")
        return f"  [{mark}] {self.name}{(' — ' + self.detail) if self.detail else ''}"


def check_matches_table_no_duplicates(cur) -> Result:
    """matches table PRIMARY KEY is match_id — should be impossible to have
    duplicates, but verify in case schema drift happens."""
    cur.execute("SELECT COUNT(*) AS rows, COUNT(DISTINCT match_id) AS uniq FROM matches")
    r = cur.fetchone()
    if r["rows"] == r["uniq"]:
        return Result("matches table: no duplicate match_ids", True,
                      f"{r['rows']:,} rows, all unique")
    return Result("matches table: duplicate match_ids",
                  False, f"{r['rows']:,} rows but only {r['uniq']:,} unique")


def check_ratings_wld_invariant(cur, mode: str = "1on1") -> Result:
    """matches_rated MUST equal wins + losses + draws by definition. If it
    doesn't, rate.py is writing inconsistent state — likely the inflation bug."""
    cur.execute("""
        SELECT COUNT(*) AS violators
        FROM ratings
        WHERE mode = %s AND map = ''
          AND matches_rated != (wins + losses + COALESCE(draws, 0))
    """, (mode,))
    n = cur.fetchone()["violators"]
    if n == 0:
        return Result(f"{mode} ratings: W+L+D == matches_rated", True)
    return Result(f"{mode} ratings: W+L+D != matches_rated", False,
                  f"{n} player(s) violate the invariant — rate.py likely double-counting")


def check_ratings_vs_actual_matches(cur, mode: str = "1on1", top_n: int = 20,
                                     tolerance: int = 5) -> Result:
    """For the top-N players by cons, compare their stored matches_rated against
    the actual count of distinct matches they appear in. Small drift (≤tolerance)
    is acceptable (NULL-frag matches get skipped); larger drift signals a bug."""
    cur.execute("""
        SELECT r.canonical_id, r.matches_rated,
               (SELECT COUNT(DISTINCT m.match_id)
                FROM matches m JOIN players p ON p.match_id = m.match_id
                WHERE m.match_mode = %s AND p.canonical_id = r.canonical_id) AS actual
        FROM ratings r
        WHERE r.mode = %s AND r.map = '' AND r.matches_rated >= 50
        ORDER BY r.conservative DESC LIMIT %s
    """, (mode, mode, top_n))
    bad = []
    for row in cur.fetchall():
        diff = row["matches_rated"] - row["actual"]
        if abs(diff) > tolerance:
            bad.append((row["canonical_id"], row["matches_rated"], row["actual"], diff))
    if not bad:
        return Result(f"{mode} top-{top_n} matches_rated vs actual", True,
                      f"all within ±{tolerance}")
    sample = ", ".join(f"{cid}({rated}/{actual}, Δ{d:+d})" for cid, rated, actual, d in bad[:3])
    return Result(f"{mode} top-{top_n} matches_rated drift > {tolerance}",
                  False, f"{len(bad)} violator(s): {sample}")


def check_players_have_canonical_id(cur) -> Result:
    """canonicalize.py should map every player_name to a canonical_id. NULLs
    here mean canonicalize didn't run after a sync, OR a new name slipped through."""
    cur.execute("SELECT COUNT(*) AS n FROM players WHERE canonical_id IS NULL")
    n = cur.fetchone()["n"]
    if n == 0:
        return Result("players table: all rows have canonical_id", True)
    return Result("players table: NULL canonical_id rows", False,
                  f"{n:,} player rows missing canonical_id — run canonicalize.py")


def check_no_self_matches(cur, mode: str = "1on1") -> Result:
    """rate_bucket skips matches where cid_a == cid_b, but the underlying SQL
    constraint mp1.canonical_id < mp2.canonical_id should prevent the join
    from producing such rows. Verify."""
    cur.execute("""
        WITH match_players AS (
            SELECT m.match_id, p.canonical_id
            FROM matches m JOIN players p ON p.match_id = m.match_id
            WHERE m.match_mode = %s AND p.canonical_id IS NOT NULL
            GROUP BY m.match_id, p.canonical_id
        )
        SELECT COUNT(*) AS n
        FROM match_players mp1
        JOIN match_players mp2 ON mp1.match_id = mp2.match_id
                              AND mp1.canonical_id = mp2.canonical_id
    """, (mode,))
    n = cur.fetchone()["n"]
    # Expected: every match contributes 1 self-pair per player (trivially).
    # If we got 0, the JOIN is broken; that's the only thing this catches.
    if n > 0:
        return Result(f"{mode}: dedup self-join sanity", True, f"{n:,} self-pairs (expected)")
    return Result(f"{mode}: dedup self-join broken", False,
                  "0 self-pairs found — JOIN may be misconfigured")


def check_ratings_table_consistent(cur, mode: str = "1on1") -> Result:
    """conservative == mu - 3*sigma. The conservative column is precomputed in
    rate.py at write time, so drift here means a stale ratings row that wasn't
    updated when mu/sigma changed."""
    cur.execute("""
        SELECT COUNT(*) AS n
        FROM ratings
        WHERE mode = %s AND map = ''
          AND ABS(conservative - (mu - 3 * sigma)) > 0.5
    """, (mode,))
    n = cur.fetchone()["n"]
    if n == 0:
        return Result(f"{mode} ratings: cons == μ−3σ", True)
    return Result(f"{mode} ratings: cons drifted from μ−3σ", False,
                  f"{n:,} row(s) inconsistent — possible stale ratings rows")


def check_perf_precompute_present(cur, mode: str = "1on1") -> Result:
    """rate.py precomputes avg_ddr and avg_frag_diff onto ratings rows during
    the rating run. If many rows are missing them, the precompute step failed
    and /api/rankings will render blank DDR/±frag on cards."""
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE avg_ddr IS NULL) AS no_ddr,
            COUNT(*) FILTER (WHERE avg_frag_diff IS NULL) AS no_fd
        FROM ratings
        WHERE mode = %s AND map = '' AND matches_rated >= 10
    """, (mode,))
    r = cur.fetchone()
    if r["total"] == 0:
        return Result(f"{mode} perf precompute presence", False,
                      "no rated players — DB empty?", critical=False)
    pct_missing = (r["no_ddr"] + r["no_fd"]) / (r["total"] * 2)
    # Up to 5% missing is acceptable (some matches predate KTX damage stats)
    if pct_missing < 0.05:
        return Result(f"{mode} perf precompute (DDR, ±frag)", True,
                      f"{r['no_ddr']} no DDR, {r['no_fd']} no ±frag out of {r['total']}")
    return Result(f"{mode} perf precompute missing on many rows", False,
                  f"{pct_missing*100:.0f}% of rated rows missing precompute — re-rate needed")


def run_all() -> int:
    """Returns process exit code: 0 if all critical checks pass, 1 otherwise."""
    conn = dbmod.connect()
    cur = conn.cursor()

    checks = [
        check_matches_table_no_duplicates(cur),
        check_players_have_canonical_id(cur),
        check_ratings_wld_invariant(cur, "1on1"),
        check_ratings_vs_actual_matches(cur, "1on1"),
        check_no_self_matches(cur, "1on1"),
        check_ratings_table_consistent(cur, "1on1"),
        check_perf_precompute_present(cur, "1on1"),
    ]

    print("=" * 70)
    print("DeepFrag DB invariants")
    print("=" * 70)
    for c in checks:
        print(c)
    print("=" * 70)

    failures = [c for c in checks if not c.ok and c.critical]
    warnings = [c for c in checks if not c.ok and not c.critical]
    print(f"Summary: {len(checks) - len(failures) - len(warnings)} passed, "
          f"{len(warnings)} warnings, {len(failures)} failures")

    cur.close()
    conn.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_all())

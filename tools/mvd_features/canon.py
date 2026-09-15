"""Canonical player ids for the demo corpus (data/mvd_features.sqlite).

The corpus keys everything on the raw in-game name, so one human shows up as
several rows in player_career / career_war — war 958 games, george 271,
[george] 43, War/george 8, georges 13, george? 3 ... all the same player
(aliases.yaml: george, whodat, igor, pikachu, fok, tardface ... -> war).

This builds `name_canon(name, canonical_id, decision)` from every distinct
players.name with the SAME resolver production uses (name_canon.py +
aliases.yaml: explicit alias -> colour-code/decoration normalize -> fuzzy),
so score_corpus.py / war.py can aggregate per canonical_id instead of per
raw name. Nothing is written back to the repo (no review-queue save).

Usage:
  python tools/mvd_features/canon.py [db]      # (re)build name_canon
  then re-run score_corpus.py and war.py so player_agi / player_career /
  player_war / career_war pick up the mapping.
"""
import collections
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from name_canon import Canonicalizer  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mvd_features.sqlite"


def build(con):
    """Resolve every distinct raw name in `players` and (re)write name_canon."""
    c = Canonicalizer.load()
    names = [r[0] for r in con.execute(
        "SELECT DISTINCT name FROM players WHERE name IS NOT NULL ORDER BY name")]
    rows = [(n, *c.resolve(n, None)) for n in names]
    con.executescript("""
        DROP TABLE IF EXISTS name_canon;
        CREATE TABLE name_canon(name TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, decision TEXT);
        CREATE INDEX nc_cid ON name_canon(canonical_id);
    """)
    con.executemany("INSERT INTO name_canon VALUES (?,?,?)", rows)
    con.commit()
    return rows


def load(con):
    """{raw name: canonical_id}. Builds the table on first use so the scoring
    scripts never silently fall back to raw names."""
    have = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='name_canon'").fetchone()
    if not have:
        build(con)
    return dict(con.execute("SELECT name, canonical_id FROM name_canon"))


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_DB)
    con = sqlite3.connect(db, timeout=120)
    rows = build(con)
    dec = collections.Counter(d for _, _, d in rows)
    print(f"{len(rows)} raw names -> {len({cid for _, cid, _ in rows})} canonical ids; "
          f"decisions {dict(dec)}")
    for cid in ("war", "cronus", "blood_dog_d_p", "sane", "powerzord"):
        print(f"  {cid}: {[n for n, c, _ in rows if c == cid]}")

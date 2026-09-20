"""Fours re-pass: fight selection + team damage per player per game -> `player_fights`.

A fight is a run of damage between one pair of players with no gap over 4 s; the
starter is whoever landed the first hit and the edge is starter eff HP minus victim
eff HP at that first hit (the same first-contact rule the fight table and adjusted
kills use). Records are kept for fights that ended in a frag between the pair.
Team damage: hits/frags with teamd=1 (self-damage excluded), plus teamkills of an
RL/LG carrier — Omicron's lever.

Columns: game_id, name, fights, started, started_behind (edge <= -60), started_ahead (>= 60),
even_w, even_n, behind_w, behind_n, ahead_w, ahead_n, teamkills, tk_launcher, team_dmg.
"""
import sqlite3, sys, time, collections
DB = sys.argv[1] if len(sys.argv) > 1 else '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
con = sqlite3.connect(DB, timeout=300)
con.executescript("""DROP TABLE IF EXISTS player_fights;
CREATE TABLE player_fights(game_id INT, name TEXT, fights INT, started INT, started_behind INT, started_ahead INT,
  even_w INT, even_n INT, behind_w INT, behind_n INT, ahead_w INT, ahead_n INT,
  teamkills INT, tk_launcher INT, team_dmg INT);""")
games = [r[0] for r in con.execute("SELECT id FROM games WHERE mode='4on4' ORDER BY id")]
print('fours', len(games), flush=True)
out = []; t0 = time.time()
for gi, gid in enumerate(games):
    names = [r[0] for r in con.execute("SELECT name FROM players WHERE game_id=?", (gid,))]
    S = {n: collections.Counter() for n in names}
    # team damage
    for att, kind, dmg, vrl, vlg in con.execute("SELECT att, kind, dmg_cap, vic_rl, vic_lg FROM events WHERE game_id=? AND teamd=1 AND selfd=0", (gid,)):
        if att not in S: continue
        if kind == 'frag':
            S[att]['teamkills'] += 1
            if vrl or vlg: S[att]['tk_launcher'] += 1
        else:
            S[att]['team_dmg'] += int(dmg or 0)
    # pairwise fights
    ev = con.execute("SELECT t, kind, att, vic, att_eff, vic_eff FROM events WHERE game_id=? AND selfd=0 AND teamd=0 ORDER BY t", (gid,)).fetchall()
    cur = {}   # pair -> [first_event, last_t, frag_event]
    def close(pair):
        first, last_t, frag = cur.pop(pair)
        starter, other, edge = first[2], first[3], (first[4] or 0) - (first[5] or 0)
        for n in (starter, other):
            if n in S: S[n]['fights'] += 1
        if starter in S:
            S[starter]['started'] += 1
            if edge <= -60: S[starter]['started_behind'] += 1
            if edge >= 60: S[starter]['started_ahead'] += 1
        if frag:
            k, v = frag[2], frag[3]
            for n in (k, v):
                if n not in S: continue
                e = edge if n == starter else -edge
                b = 'even' if abs(e) < 60 else ('behind' if e < 0 else 'ahead')
                S[n][b + '_n'] += 1
                if n == k: S[n][b + '_w'] += 1
    for r in ev:
        pair = frozenset((r[2], r[3]))
        if pair in cur and r[0] - cur[pair][1] > 4000: close(pair)
        if pair not in cur: cur[pair] = [r, r[0], None]
        cur[pair][1] = r[0]
        if r[1] == 'frag' and cur[pair][2] is None: cur[pair][2] = r
    for pair in list(cur): close(pair)
    for n in names:
        s = S[n]
        out.append((gid, n, s['fights'], s['started'], s['started_behind'], s['started_ahead'], s['even_w'], s['even_n'],
                    s['behind_w'], s['behind_n'], s['ahead_w'], s['ahead_n'], s['teamkills'], s['tk_launcher'], s['team_dmg']))
    if gi % 250 == 0: print(f'{gi}/{len(games)} {time.time()-t0:.0f}s', flush=True)
con.executemany("INSERT INTO player_fights VALUES (" + ",".join("?" * 15) + ")", out); con.commit()
print('player_fights rows', len(out), flush=True)

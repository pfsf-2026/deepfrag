"""Quake WAR v0: +/- above expected. Expected +/- per minute for a player-game is fitted from the player's own
strength (leave-one-game-out career mean +/- per minute), his teammates' mean strength, the opponents' mean
strength and the map. Residual = actual - expected (above average). Above replacement adds what an average
player would have earned over a replacement-level player (25th percentile of the active pool) in that slot.
Writes player_war (per player-game) and career_war."""
import sqlite3, sys, collections, numpy as np
DB=sys.argv[1] if len(sys.argv)>1 else '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
con=sqlite3.connect(DB, timeout=120)
# keyed by canonical_id (player_agi.cid, from canon.py / aliases.yaml) so george + [george] + War/george all count as war
rows=con.execute("SELECT game_id, ts, map, cid, team, minutes, plus_minus, win FROM player_agi").fetchall()
tot=collections.defaultdict(float); mins=collections.defaultdict(float); n=collections.defaultdict(int)
for gid,ts,mp,name,team,m,pm,win in rows: tot[name]+=pm; mins[name]+=m; n[name]+=1
def loo(name,m,pm):  # strength without this game, per minute; shrink toward 0 for thin histories
    tm=mins[name]-m; tp=tot[name]-pm
    return (tp/(tm+60)) if tm>0 else 0.0      # +60 min of zero as a prior
by=collections.defaultdict(list)
for r in rows: by[r[0]].append(r)
maps=sorted({r[2] for r in rows}); mi={m:i for i,m in enumerate(maps)}
X=[];y=[];meta=[]
for gid,L in by.items():
    if len(L)<6: continue
    S={r[3]:loo(r[3],r[5],r[6]) for r in L}
    for gid_,ts,mp,name,team,m,pm,win in L:
        mates=[S[x[3]] for x in L if x[4]==team and x[3]!=name]; opps=[S[x[3]] for x in L if x[4]!=team]
        if not mates or not opps: continue
        f=[S[name],np.mean(mates),np.mean(opps)]+[1.0 if mp==k else 0.0 for k in maps]
        X.append(f); y.append(pm/m); meta.append((gid,ts,mp,name,team,m,pm,win,S[name]))
X=np.array(X); y=np.array(y)
A=np.c_[np.ones(len(y)),X]; beta=np.linalg.lstsq(A,y,rcond=None)[0]; pred=A@beta; res=y-pred
r2=1-res.var()/y.var()
print(f"expected +/- model: R² {r2:.3f} | own strength {beta[1]:+.3f}, teammates' strength {beta[2]:+.3f}, opponents' strength {beta[3]:+.3f} (per point of strength)")
# replacement level: 25th percentile of strength among players with 15+ games in the last 12 months
last=max(r[1] for r in rows)[:4]
act=[name for name in n if n[name]>=15 and any(r[3]==name and r[1]>='2025-09-12' for r in rows)]
strength={name:tot[name]/(mins[name]+60) for name in n}
repl=np.percentile([strength[a] for a in act],25); avg=np.mean([strength[a] for a in act])
print(f"active players {len(act)}: replacement strength (p25) {repl:+.3f} /min, average {avg:+.3f} /min")
con.executescript("DROP TABLE IF EXISTS player_war; CREATE TABLE player_war(game_id INT, ts TEXT, map TEXT, canonical_id TEXT, team TEXT, minutes REAL, plus_minus REAL, expected REAL, above_avg REAL, above_repl REAL, win INT);")
# wins per +/- point: linear-probability slope of team win on the team's +/- total per game
tp=collections.defaultdict(float); tw={}
for gid,ts,mp,name,team,m,pm,win in rows: tp[(gid,team)]+=pm; tw[(gid,team)]=win
xs=np.array([tp[k] for k in tp]); ws=np.array([tw[k] for k in tp]); k_win=np.cov(xs,ws)[0,1]/xs.var()
print(f"wins per +/- point (team-level slope): {k_win:.4f}  -> {1/k_win:.0f} points ≈ 1 win")
out=[]
for (gid,ts,mp,name,team,m,pm,win,s),p,r in zip(meta,pred,res):
    above_self=r*m
    above_repl=above_self+(s-repl)*beta[1]*m      # actual minus what a replacement-level player would post in this slot
    above_avg=above_self+(s-avg)*beta[1]*m        # actual minus what an average active player would post in this slot
    out.append((gid,ts,mp,name,team,m,pm,round(p*m,2),round(above_avg,2),round(above_repl,2),win))
con.executemany("INSERT INTO player_war VALUES (?,?,?,?,?,?,?,?,?,?,?)",out)
con.executescript(("""DROP TABLE IF EXISTS career_war;
CREATE TABLE career_war AS SELECT canonical_id,
  (SELECT b.name FROM player_agi b WHERE b.cid=w.canonical_id GROUP BY b.name ORDER BY COUNT(*) DESC, b.name LIMIT 1) AS name,
  COUNT(*) games, ROUND(SUM(minutes),0) minutes, ROUND(AVG(win)*100,1) win_pct,
  ROUND(SUM(plus_minus),0) plus_minus_total, ROUND(SUM(plus_minus)/COUNT(*),1) plus_minus_pg,
  ROUND(SUM(above_avg),0) above_avg_total, ROUND(SUM(above_avg)/COUNT(*),1) above_avg_pg,
  ROUND(SUM(above_repl),0) above_repl_total, ROUND(SUM(above_repl)/COUNT(*),1) above_repl_pg,
  ROUND(SUM(above_repl)*%.6f,1) wins_above_repl, MAX(ts) last_game FROM player_war w GROUP BY canonical_id;""") % k_win)
con.commit()
print("\n== career, 100+ games: +/- total | above average per game | above replacement total | Wins Above Replacement (points x fitted wins-per-point) ==")
for r in con.execute("SELECT name, games, win_pct, plus_minus_total, plus_minus_pg, above_avg_pg, above_repl_total, wins_above_repl FROM career_war WHERE games>=100 ORDER BY above_repl_total DESC LIMIT 15"):
    print(f"  {r[0]:16s} g={r[1]:5d} win {r[2]:4.0f}% | +/- {r[3]:+8.0f} ({r[4]:+5.1f}/g) | above avg {r[5]:+5.1f}/g | above repl {r[6]:+8.0f} | WAR {r[7]:+6.1f}")
print("\n== above average per game, 30+ games (the rating input) ==")
for r in con.execute("SELECT name, games, win_pct, plus_minus_pg, above_avg_pg FROM career_war WHERE games>=30 ORDER BY above_avg_pg DESC LIMIT 12"):
    print(f"  {r[0]:16s} g={r[1]:5d} win {r[2]:4.0f}% | +/- {r[3]:+5.1f}/g | above avg {r[4]:+5.1f}/g")
print("  regulars:")
for r in con.execute("SELECT name, games, win_pct, plus_minus_pg, above_avg_pg, above_repl_pg, wins_above_repl FROM career_war WHERE canonical_id IN ('cronus','blood_dog_d_p','omicron','war','pred','sane','yeti','dusty','bogojoker','evalcat','schotty','namtsui','powerzord') ORDER BY above_avg_pg DESC"):
    print(f"  {r[0]:16s} g={r[1]:5d} win {r[2]:4.0f}% | +/- {r[3]:+5.1f}/g | above avg {r[4]:+5.1f}/g | above repl {r[5]:+5.1f}/g | WAR {r[6]:+6.1f}")

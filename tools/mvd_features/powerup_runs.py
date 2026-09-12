"""powerup_runs: one row per quad/pent/ring run (from `powerups` intervals) with what happened during it.
ra_timing: per player per game, red-armor pickups and how long after spawn they were taken."""
import sqlite3, sys, collections, math, json
DB=sys.argv[1] if len(sys.argv)>1 else '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
HERE=__file__.rsplit('/',1)[0]
con=sqlite3.connect(DB, timeout=120)
M=json.load(open(f'{HERE}/winprob_4on4.json'))['models']
def pwin(m,fd,frac,sd,pw,rl,lg):
    x=[fd,fd*frac,fd/(frac+0.05),sd/100,pw,rl,lg,frac]; z=m['intercept']+sum(c*v for c,v in zip(m['coef'],x)); return 1/(1+math.exp(-z))
con.executescript("""
DROP TABLE IF EXISTS powerup_runs;
CREATE TABLE powerup_runs(game_id INT, map TEXT, holder TEXT, team TEXT, kind TEXT, s INT, e INT, dur_s REAL,
  holder_frags INT, team_frags INT, enemy_frags INT, holder_dmg INT, holder_died INT, died_after_s REAL, team_deaths INT,
  fragdiff_change INT, p_before REAL, p_after REAL, wasted INT);
DROP TABLE IF EXISTS ra_timing;
CREATE TABLE ra_timing(game_id INT, name TEXT, team TEXT, ra_takes INT, ra_median_wait_s REAL, ra_on_timer INT, ya_takes INT, mh_takes INT, quad_takes INT);
""")
games={r[0]:r for r in con.execute("SELECT id,map,team_a,team_b,score_a,score_b,dur_ms FROM games WHERE mode='4on4' AND dur_ms>=540000")}
runs=[]; timing=[]
for gid,g in games.items():
    mp=g[1]; m=M.get(mp,M['pooled']); END=g[6]
    pws=con.execute("SELECT name,team,kind,s,e FROM powerups WHERE game_id=? AND s>=0 ORDER BY s",(gid,)).fetchall()
    if not pws and not con.execute("SELECT 1 FROM item_takes WHERE game_id=? LIMIT 1",(gid,)).fetchone(): continue
    frags=con.execute("SELECT t,att,vic FROM events WHERE game_id=? AND kind='frag' AND selfd=0 AND teamd=0 ORDER BY t",(gid,)).fetchall()
    dmg=con.execute("SELECT t,att,dmg_cap FROM events WHERE game_id=? AND kind='dmg' AND selfd=0 AND teamd=0",(gid,)).fetchall()
    pteam={n:t for n,t in con.execute("SELECT name,team FROM players WHERE game_id=?",(gid,))}
    deaths=collections.defaultdict(list)
    for t,a,v in frags: deaths[v].append(t)
    for t,v in con.execute("SELECT e.t, e.vic FROM events e WHERE e.game_id=? AND e.kind='frag' AND (e.selfd=1 OR e.teamd=1)",(gid,)): deaths[v].append(t)
    st={(t,team):(fd,ss,pw,rl,lg) for t,team,fd,ss,pw,rl,lg in con.execute("SELECT t,team,frag_diff,stack_sum,powerup,rl_n,lg_n FROM state10s WHERE game_id=?",(gid,))}
    teams=sorted(set(pteam.values()))
    def P(side,t):
        ts=(t//10000)*10000; a=st.get((ts,side)); o=[x for x in teams if x!=side]
        b=st.get((ts,o[0])) if o else None
        if not a or not b: return None
        return pwin(m,a[0],(END-t)/1000/1200,a[1]-b[1],a[2]-b[2],a[3]-b[3],a[4]-b[4])
    for n,team,kind,s,e in pws:
        if n not in pteam: continue
        hf=sum(1 for t,a,v in frags if a==n and s<=t<=e); tf=sum(1 for t,a,v in frags if pteam.get(a)==team and a!=n and s<=t<=e)
        ef=sum(1 for t,a,v in frags if pteam.get(a)!=team and s<=t<=e)
        hd=sum(d for t,a,d in dmg if a==n and s<=t<=e)
        died=[t for t in deaths.get(n,[]) if s<=t<=e+100]; td=sum(1 for mname,tm in pteam.items() if tm==team for t in deaths.get(mname,[]) if s<=t<=e)
        fd0=st.get(((s//10000)*10000,team),(None,))[0]; fd1=st.get(((e//10000)*10000,team),(None,))[0]
        pb=P(team,s); pa=P(team,min(e,END-1))
        dur=(e-s)/1000; wasted=int((died and (died[0]-s)<10000) or (dur>=25 and hf==0))
        runs.append((gid,mp,n,team,kind,s,e,round(dur,1),hf,tf,ef,hd,int(bool(died)),round((died[0]-s)/1000,1) if died else None,td,
                     (fd1-fd0) if (fd0 is not None and fd1 is not None) else None,round(pb,4) if pb is not None else None,round(pa,4) if pa is not None else None,wasted))
    # RA timing per player
    takes=con.execute("SELECT name,kind,wait_ms FROM item_takes WHERE game_id=?",(gid,)).fetchall()
    per=collections.defaultdict(lambda: collections.defaultdict(list))
    for n,kind,w in takes: per[n][kind].append(w)
    for n,d in per.items():
        if n not in pteam: continue
        ra=d.get('ra',[]); ra_w=sorted(ra)
        timing.append((gid,n,pteam[n],len(ra),round(ra_w[len(ra_w)//2]/1000,1) if ra_w else None,sum(1 for w in ra if w<=3000),len(d.get('ya',[])),len(d.get('mh',[])),len(d.get('quad',[]))))
con.executemany("INSERT INTO powerup_runs VALUES ("+",".join("?"*19)+")",runs)
con.executemany("INSERT INTO ra_timing VALUES (?,?,?,?,?,?,?,?,?)",timing)
con.commit()
print('powerup_runs',len(runs),' ra_timing rows',len(timing))

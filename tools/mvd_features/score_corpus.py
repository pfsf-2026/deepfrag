"""Build player_agi (one row per player per fours game: AGI v0 components, swing, rocket efficiency) and
player_career (per-player aggregates) from the extracted corpus. Run after extract.py, swing_corpus, state_v2, items_pass."""
import sqlite3, sys, statistics, collections
DB=sys.argv[1] if len(sys.argv)>1 else '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
con=sqlite3.connect(DB, timeout=120)
con.executescript("""
DROP TABLE IF EXISTS player_agi;
CREATE TABLE player_agi(game_id INT, ts TEXT, map TEXT, name TEXT, team TEXT, win INT, minutes REAL,
  frags INT, kills INT, deaths INT, adj_kills REAL, dmg INT, taken INT, sddr REAL, ddr REAL,
  spawn_deaths INT, chained INT, chained_real INT, multi INT, items REAL, take_ra INT, take_quad INT, take_pent INT,
  plus_minus REAL, plus_minus_pm REAL, rockets_fired INT, rl_direct_hits INT, rl_dmg INT, rl_dmg_per_rocket REAL, rl_connect_pct REAL,
  cells_fired INT, lg_dmg INT, agi REAL, agi_sw REAL);
""")
rows=con.execute("""SELECT p.game_id, g.ts, g.map, p.name, p.team, g.team_a, g.team_b, g.score_a, g.score_b, g.dur_ms,
                           p.frags, p.kills, p.deaths, p.dmg_given, p.dmg_taken, p.stacked_given, p.stacked_taken, p.spawn_deaths, p.chained, p.multi,
                           p.take_ra, p.take_ya, p.take_mh, p.take_quad, p.take_pent,
                           s.swing, s.adj_kills, sh.rockets_fired, sh.rl_direct_hits, sh.rl_direct_dmg, sh.rl_splash_dmg, sh.rockets_with_damage, sh.cells_fired, sh.lg_dmg
                    FROM players p JOIN games g ON g.id=p.game_id
                    LEFT JOIN player_swing s ON s.game_id=p.game_id AND s.name=p.name
                    LEFT JOIN player_shots sh ON sh.game_id=p.game_id AND sh.name=p.name
                    WHERE g.mode='4on4' AND g.dur_ms>=540000 AND g.score_a IS NOT NULL""").fetchall()
by=collections.defaultdict(list)
for r in rows:
    (gid,ts,mp,n,team,ta,tb,sa,sb,dur,fr,k,d,dg,dt,sg,st,spd,ch,mu,ra,ya,mh,q,pe,sw,adj,rk,rdh,rdd,rsd,rwd,cl,lgd)=r
    if sw is None: continue
    win=1 if (team==ta and sa>sb) or (team==tb and sb>sa) else 0; mins=dur/60000
    items=ra+0.6*ya+0.8*mh+2*q+2*pe
    by[gid].append(dict(gid=gid,ts=ts,map=mp,name=n,team=team,win=win,minutes=mins,frags=fr,kills=k,deaths=d,adj=adj,dmg=dg,taken=dt,
        sddr=sg/max(1,st),ddr=dg/max(1,dt),spawn=spd,chained=ch,chained_real=max(0,ch-spd),multi=mu,items=items,ra=ra,q=q,pe=pe,
        swing=sw*100,swing_pm=sw*100/mins,rk=rk or 0,rdh=rdh or 0,rl_dmg=(rdd or 0)+(rsd or 0),
        rl_dpr=((rdd or 0)+(rsd or 0))/max(1,rk or 0),rl_conn=(rwd or 0)/max(1,rk or 0)*100,cl=cl or 0,lg_dmg=lgd or 0))
out=[]
for gid,L in by.items():
    if len(L)<6: continue
    def nm(key,inv=False):
        m=statistics.mean(x[key] for x in L) or 1
        return {x['name']:(m/max(0.5,x[key]) if inv else x[key]/m) for x in L}
    A=nm('adj');D=nm('dmg');S=nm('sddr');De=nm('deaths',True);I=nm('items');Mu=nm('multi')
    for x in L: x['agi']=0.30*A[x['name']]+0.15*D[x['name']]+0.15*S[x['name']]+0.15*De[x['name']]+0.05*min(2,Mu[x['name']])+0.20*I[x['name']]
    m=statistics.mean(x['agi'] for x in L)
    for x in L: x['agi']/=m; x['agi_sw']=0.8*x['agi']+0.2*max(0.2,1+x['swing_pm']/10)
    m2=statistics.mean(x['agi_sw'] for x in L)
    for x in L:
        x['agi_sw']/=m2
        out.append((x['gid'],x['ts'],x['map'],x['name'],x['team'],x['win'],round(x['minutes'],2),x['frags'],x['kills'],x['deaths'],round(x['adj'],2),x['dmg'],x['taken'],round(x['sddr'],3),round(x['ddr'],3),
                    x['spawn'],x['chained'],x['chained_real'],x['multi'],round(x['items'],1),x['ra'],x['q'],x['pe'],round(x['swing'],2),round(x['swing_pm'],3),x['rk'],x['rdh'],x['rl_dmg'],round(x['rl_dpr'],1),round(x['rl_conn'],1),x['cl'],x['lg_dmg'],round(x['agi'],3),round(x['agi_sw'],3)))
con.executemany("INSERT INTO player_agi VALUES ("+",".join("?"*34)+")",out)
con.executescript("""
DROP TABLE IF EXISTS player_career;
CREATE TABLE player_career AS
SELECT name, COUNT(*) AS games, ROUND(SUM(minutes),0) AS minutes, ROUND(AVG(win)*100,1) AS win_pct,
  ROUND(SUM(frags)/SUM(minutes),3) AS frags_pm, ROUND(SUM(deaths)/SUM(minutes),3) AS deaths_pm, ROUND(SUM(adj_kills)/SUM(minutes),3) AS adj_kills_pm,
  ROUND(SUM(dmg)/SUM(minutes),0) AS dmg_pm, ROUND(SUM(dmg)*1.0/MAX(1,SUM(taken)),3) AS ddr, ROUND(AVG(sddr),3) AS sddr,
  ROUND(SUM(spawn_deaths)*100.0/MAX(1,SUM(deaths)),1) AS spawn_death_pct, ROUND(SUM(chained_real)*100.0/MAX(1,SUM(deaths)),1) AS chained_real_pct,
  ROUND(SUM(items)/SUM(minutes),3) AS items_pm, ROUND(SUM(take_ra)/SUM(minutes),3) AS ra_pm, ROUND(SUM(take_quad)*1.0/COUNT(*),2) AS quads_pg,
  ROUND(SUM(plus_minus)/SUM(minutes),3) AS plus_minus_pm, ROUND(SUM(rl_dmg)*1.0/MAX(1,SUM(rockets_fired)),1) AS rl_dmg_per_rocket,
  ROUND(SUM(rl_direct_hits)*100.0/MAX(1,SUM(rockets_fired)),1) AS rl_direct_pct, ROUND(SUM(lg_dmg)*1.0/MAX(1,SUM(cells_fired)),2) AS lg_dmg_per_cell,
  ROUND(AVG(agi),3) AS agi, ROUND(AVG(agi_sw),3) AS agi_sw, MAX(ts) AS last_game
FROM player_agi GROUP BY name;
CREATE INDEX IF NOT EXISTS pa_n ON player_agi(name); CREATE INDEX IF NOT EXISTS pa_g ON player_agi(game_id);
""")
con.commit()
print('player_agi rows', con.execute("SELECT count(*) FROM player_agi").fetchone()[0], ' careers', con.execute("SELECT count(*) FROM player_career").fetchone()[0])

"""Corpus-wide kill-only swing + stack-adjusted kill points for every player-game (writes player_swing).
Uses winprob_4on4.json (per-map model, pooled fallback), fight_table_4on4.json, the events table (frags + damage
with both players' state) and state10s (team stack/weapon/power-up sums at the nearest 10s sample)."""
import sqlite3, json, math, collections, bisect, sys, time
DB=sys.argv[1] if len(sys.argv)>1 else '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
HERE=__file__.rsplit('/',1)[0]
con=sqlite3.connect(DB, timeout=120)
M=json.load(open(f'{HERE}/winprob_4on4.json'))['models']
def pwin(m,fd,frac,sd,pw,rl,lg):
    x=[fd,fd*frac,fd/(frac+0.05),sd/100,pw,rl,lg,frac]; z=m['intercept']+sum(c*v for c,v in zip(m['coef'],x)); return 1/(1+math.exp(-z))
T=json.load(open(f'{HERE}/fight_table_4on4.json'))['table']; FIN=json.load(open(f'{HERE}/fight_table_4on4.json')).get('finisher_share',0.15)
def pfight(edge,state):
    pts=T.get(state,T['no powerup'])
    if edge<=pts[0][0]: return pts[0][1]
    if edge>=pts[-1][0]: return pts[-1][1]
    for (x0,y0),(x1,y1) in zip(pts,pts[1:]):
        if x0<=edge<=x1: return y0+(y1-y0)*(edge-x0)/(x1-x0)
games=con.execute("SELECT id,map,team_a,team_b,score_a,score_b,dur_ms FROM games WHERE mode='4on4' AND dur_ms>=540000 AND score_a IS NOT NULL").fetchall()
con.execute("DROP TABLE IF EXISTS player_swing"); con.execute("CREATE TABLE player_swing(game_id INT, name TEXT, team TEXT, swing REAL, swing_kill REAL, swing_death REAL, adj_kills REAL, kills INT)")
out=[]; t0=time.time()
for gi,(gid,mp,ta,tb,sa,sb,dur) in enumerate(games):
    m=M.get(mp,M['pooled'])
    st={(t,team):(ss,pw,rl,lg) for t,team,ss,pw,rl,lg in con.execute("SELECT t,team,stack_sum,powerup,rl_n,lg_n FROM state10s WHERE game_id=?",(gid,))}
    ev=con.execute("SELECT t,kind,att,vic,dmg_cap,att_eff,vic_eff,att_pw,vic_pw,vic_rl,vic_lg,frag_diff,time_left FROM events WHERE game_id=? AND selfd=0 AND teamd=0 ORDER BY t",(gid,)).fetchall()
    pteam={n:team for n,team in con.execute("SELECT name,team FROM players WHERE game_id=?",(gid,))}
    dmg_by_v=collections.defaultdict(list); pair=collections.defaultdict(list)
    for r in ev:
        if r[1]=='dmg': dmg_by_v[r[3]].append(r); pair[frozenset((r[2],r[3]))].append(r)
    SW=collections.defaultdict(collections.Counter)
    for r in ev:
        if r[1]!='frag': continue
        t,_,k,v,_,ae,ve,pa,pv,vrl,vlg,fd,tl=r; side=pteam.get(k); other=pteam.get(v)
        if side is None or other is None or side==other: continue
        ts=(t//10000)*10000; a=st.get((ts,side)); b=st.get((ts,other))
        if not a or not b: continue
        frac=tl/1000/1200; sd=a[0]-b[0]; pwd=a[1]-b[1]; rld=a[2]-b[2]; lgd=a[3]-b[3]
        dp=pwin(m,fd+1,frac,sd+ve,pwd+(1 if pv else 0),rld+vrl,lgd+vlg)-pwin(m,fd,frac,sd,pwd,rld,lgd)
        lst=pair[frozenset((k,v))]; i=bisect.bisect_right([x[0] for x in lst],t)-1; first=None; tt=t
        while i>=0 and tt-lst[i][0]<=4000: first=lst[i]; tt=lst[i][0]; i-=1
        if first is None: ke,ve2,kp,vp=ae,ve,pa,pv
        else: ke,ve2,kp,vp=(first[5],first[6],first[7],first[8]) if first[2]==k else (first[6],first[5],first[8],first[7])
        state='both' if kp and vp else ('has powerup' if kp else ('vs powerup' if vp else 'no powerup'))
        kpts=min(3.0,0.5/max(0.05,pfight(ke-ve2,state)))
        contrib=collections.Counter()
        for e in dmg_by_v[v]:
            if t-10000<=e[0]<=t and pteam.get(e[2])==side: contrib[e[2]]+=e[4]
        tot=sum(contrib.values())
        if tot<=0: SW[k]['kill']+=dp; SW[k]['adj']+=kpts
        else:
            for a_,dm in contrib.items(): SW[a_]['kill']+=dp*(FIN*(a_==k)+(1-FIN)*dm/tot); SW[a_]['adj']+=kpts*(FIN*(a_==k)+(1-FIN)*dm/tot)
        SW[v]['death']-=dp; SW[k]['n']+=1
    for n,team in pteam.items():
        s=SW[n]; out.append((gid,n,team,s['kill']+s['death'],s['kill'],s['death'],s['adj'],s['n']))
    if gi%500==0: print(f'{gi}/{len(games)} {time.time()-t0:.0f}s',flush=True)
con.executemany("INSERT INTO player_swing VALUES (?,?,?,?,?,?,?,?)",out); con.commit(); print('player_swing rows',len(out))

"""Duel (1on1) advanced metrics from the demo corpus.

Step 1 fits a duel win-probability model on state samples rebuilt from the events (duels carry no state10s rows;
the pre-hit state of both players is recorded on every event), one sample per 10-s bucket, mirrored and writes `winprob_1on1.json` (pooled + per-map, held out by game).
Step 2 scores every duel per player into `player_duel` and aggregates `player_duel_career`:

  adj_kills      stack-adjusted kills: 0.5 / P(win fight | edge at FIRST CONTACT, power-up state) from
                 fight_table_1on1.json, capped at 3. No credit split in a duel.
  plus_minus     leverage-weighted frag differential (+/-): per kill, P(win) after minus before, using the
                 map model; the victim's remaining stack, launchers and power-up are removed. Killer +, victim -.
                 Unit = frag-equivalents (1.0 = a frag at even score with half the game left).
  ddr / sddr     damage given/taken (KTX-capped) and the same restricted to exchanges fought at >= 150 eff HP.
  fights         a fight = damage between the two players with no gap > 4 s. starter = first hit.
                 started_behind = fights you started while >= 60 eff HP behind at first contact.
                 even_w / even_n = fights decided by a frag where |edge| < 60 at first contact (your record).
                 behind_w/behind_n, ahead_w/ahead_n likewise for edge <= -60 / >= 60.
  spawn_deaths   killed within 3 s of spawning (KTX spawn-frag stat uses 2 s; kept as spawnfrags_vs).
  chained_real   killed within 14 s of your previous death after living > 3 s.
  item_first     after a death, you took an armor or mega before the next damage exchange (share of deaths).
  ra/ya/mh       takes per game and RA on-timer share (<= 3 s after it spawned). Needs item_takes (items_pass.py 1on1).

Usage: duel_corpus.py [db] [--fit-only|--score-only]
"""
import sqlite3, sys, json, math, time, bisect, collections, os
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
DB=next((a for a in sys.argv[1:] if not a.startswith('--')), '/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite')
con=sqlite3.connect(DB, timeout=300)
GAMES=con.execute("""SELECT id,ts,map,team_a,team_b,score_a,score_b,dur_ms FROM games
                     WHERE mode='1on1' AND n_players=2 AND score_a IS NOT NULL AND dur_ms>=240000""").fetchall()
print(f'duels {len(GAMES)}', flush=True)

def feats(fd,frac,sd,pw,rl,lg): return [fd,fd*frac,fd/(frac+0.05),sd/100,pw,rl,lg,frac]

def fit():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss, roc_auc_score
    gmeta={g[0]:g for g in GAMES if g[5]!=g[6]}
    # Duels have no state10s rows: build state samples from the events themselves (the recorded pre-hit
    # state of both players), one per 10-second bucket per game, mirrored for both players so the fit is symmetric.
    X=[];y=[];gid_=[];mp_=[]
    for gid,g in gmeta.items():
        dur=g[7]; last={}
        for t,kind,att,vic,ae,ve,pa,pv,arl,alg,vrl,vlg,fd,tl in con.execute(
            "SELECT t,kind,att,vic,att_eff,vic_eff,att_pw,vic_pw,att_rl,att_lg,vic_rl,vic_lg,frag_diff,time_left FROM events WHERE game_id=? AND selfd=0 AND teamd=0 ORDER BY t",(gid,)):
            if tl is None or tl<0 or tl>dur: continue
            fdp=fd-1 if kind=='frag' else fd   # frag_diff is recorded after the kill
            last[t//10000]=(att,fdp,tl/dur,ae-ve,(1 if pa else 0)-(1 if pv else 0),arl-vrl,alg-vlg)
        for att,fdp,frac,sd,pw,rl,lg in last.values():
            win=1 if (att==g[3] and g[5]>g[6]) or (att==g[4] and g[6]>g[5]) else 0
            X.append(feats(fdp,frac,sd,pw,rl,lg)); y.append(win); gid_.append(gid); mp_.append(g[2])
            X.append(feats(-fdp,frac,-sd,-pw,-rl,-lg)); y.append(1-win); gid_.append(gid); mp_.append(g[2])
    X=np.array(X); y=np.array(y); gid_=np.array(gid_); mp_=np.array(mp_)
    print(f'state samples {len(X)} from {len(set(gid_))} decided duels', flush=True)
    hold=(gid_%5==0)
    clf=LogisticRegression(C=1.0,max_iter=3000,fit_intercept=False).fit(X[~hold],y[~hold])
    p=clf.predict_proba(X[hold])[:,1]
    ll=log_loss(y[hold],p); auc=roc_auc_score(y[hold],p)
    print(f'pooled held-out: log-loss {ll:.4f} AUC {auc:.4f}', flush=True)
    for lo,hi in [(0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.01)]:
        s=(p>=lo)&(p<hi)
        if s.sum(): print(f'   pred {lo:.1f}-{hi:.1f}: n={s.sum():6d} actual {y[hold][s].mean():.3f}')
    clf=LogisticRegression(C=1.0,max_iter=3000,fit_intercept=False).fit(X,y)
    models={'pooled':{'coef':clf.coef_[0].tolist(),'intercept':0.0,'games':int(len(set(gid_))),'heldout_logloss':round(ll,4),'heldout_auc':round(auc,4)}}
    for mp in sorted(set(mp_)):
        s=mp_==mp
        if len(set(gid_[s]))<300: continue
        c=LogisticRegression(C=1.0,max_iter=3000,fit_intercept=False).fit(X[s&~hold],y[s&~hold])
        pm=c.predict_proba(X[s&hold])[:,1]; llm=log_loss(y[s&hold],pm); pp=clf.predict_proba(X[s&hold])[:,1]; llp=log_loss(y[s&hold],pp)
        c=LogisticRegression(C=1.0,max_iter=3000,fit_intercept=False).fit(X[s],y[s])
        models[mp]={'coef':c.coef_[0].tolist(),'intercept':0.0,'games':int(len(set(gid_[s]))),'heldout_logloss':round(llm,4),'pooled_on_map_logloss':round(llp,4)}
        print(f'   {mp:10s} games {models[mp]["games"]:5d} held-out log-loss {llm:.4f} (pooled model on this map {llp:.4f})', flush=True)
    m=models['pooled']['coef']
    def pw(fd,frac,sd=0,pw_=0,rl=0,lg=0):
        z=sum(c*v for c,v in zip(m,feats(fd,frac,sd,pw_,rl,lg))); return 1/(1+math.exp(-z))
    print('sanity: +1 frag at even, half left %.3f | +5 frags half left %.3f | +5 frags 1 min left (10-min duel) %.3f | +100 stack even %.3f | +RL even %.3f | +LG even %.3f'%(
        pw(1,.5),pw(5,.5),pw(5,.1),pw(0,.5,100),pw(0,.5,0,0,1),pw(0,.5,0,0,0,1)))
    json.dump({'features':['frag_diff','frag_diff*frac_left','frag_diff/(frac_left+.05)','stack_diff/100','powerup_diff','rl_diff','lg_diff','frac_left'],
               'note':'duel win probability v1; frac_left = time_left/duration; no intercept (symmetric); stack in effective HP',
               'models':models},open(f'{HERE}/winprob_1on1.json','w'),indent=1)

def score():
    M=json.load(open(f'{HERE}/winprob_1on1.json'))['models']
    def pwin(m,fd,frac,sd,pw,rl,lg):
        z=m['intercept']+sum(c*v for c,v in zip(m['coef'],feats(fd,frac,sd,pw,rl,lg))); return 1/(1+math.exp(-z))
    FT=json.load(open(f'{HERE}/fight_table_1on1.json'))['table']
    def pfight(edge,state):
        pts=FT.get(state,FT['no powerup'])
        if edge<=pts[0][0]: return pts[0][1]
        if edge>=pts[-1][0]: return pts[-1][1]
        for (x0,y0),(x1,y1) in zip(pts,pts[1:]):
            if x0<=edge<=x1: return y0+(y1-y0)*(edge-x0)/(x1-x0)
    con.executescript("""
    DROP TABLE IF EXISTS player_duel;
    CREATE TABLE player_duel(game_id INT, ts TEXT, map TEXT, name TEXT, opp TEXT, win INT, minutes REAL,
      frags INT, kills INT, deaths INT, adj_kills REAL, dmg INT, taken INT, ddr REAL, sddr REAL,
      spawn_deaths INT, spawnfrags_vs INT, chained_real INT,
      fights INT, started INT, started_behind INT, started_ahead INT,
      even_w INT, even_n INT, behind_w INT, behind_n INT, ahead_w INT, ahead_n INT,
      item_first INT, ra INT, ra_on_timer INT, ya INT, mh INT,
      plus_minus REAL, plus_minus_pm REAL);
    """)
    # +/- unit = frag-equivalents: one frag at even score with half the duel left (pooled model), ~7 pp in a duel.
    FE=pwin(M['pooled'],1,0.5,0,0,0,0)-0.5
    print('1 frag-equivalent = %.1f pp of win probability'%(100*FE), flush=True)
    have_items=con.execute("SELECT 1 FROM item_takes it JOIN games g ON g.id=it.game_id WHERE g.mode='1on1' LIMIT 1").fetchone() is not None
    print('item_takes for duels:',have_items, flush=True)
    out=[]; t0=time.time()
    for gi,(gid,ts,mp,ta,tb,sa,sb,dur) in enumerate(GAMES):
        m=M.get(mp,M['pooled'])
        pl={n:(fr,k,d,dg,dt,sg,st_,spf) for n,fr,k,d,dg,dt,sg,st_,spf in con.execute(
            "SELECT name,frags,kills,deaths,dmg_given,dmg_taken,stacked_given,stacked_taken,spawnfrags FROM players WHERE game_id=?",(gid,))}
        if len(pl)!=2: continue
        A,B=list(pl)
        ev=con.execute("""SELECT t,kind,att,vic,dmg_cap,att_eff,vic_eff,att_pw,vic_pw,att_rl,att_lg,vic_rl,vic_lg,vic_tss,frag_diff,time_left
                          FROM events WHERE game_id=? AND selfd=0 AND teamd=0 ORDER BY t""",(gid,)).fetchall()
        takes=collections.defaultdict(list)
        if have_items:
            for t,n,kind,wait in con.execute("SELECT t,name,kind,wait_ms FROM item_takes WHERE game_id=? ORDER BY t",(gid,)): takes[n].append((t,kind,wait))
        S={n:collections.Counter() for n in pl}
        # fights: cluster with gap <= 4 s
        fights=[]; cur=[]
        for r in ev:
            if cur and r[0]-cur[-1][0]>4000: fights.append(cur); cur=[]
            cur.append(r)
        if cur: fights.append(cur)
        last_death={}
        for f in fights:
            first=f[0]; starter=first[2]; other=first[3]; edge=first[5]-first[6]  # starter's eff minus other's, at first contact
            kp,vp=first[7],first[8]
            for n,e in ((starter,edge),(other,-edge)):
                S[n]['fights']+=1
            S[starter]['started']+=1
            if edge<=-60: S[starter]['started_behind']+=1
            if edge>=60: S[starter]['started_ahead']+=1
            frags=[r for r in f if r[1]=='frag']
            if frags:
                k,v=frags[0][2],frags[0][3]
                for n,e in ((k,edge if k==starter else -edge),(v,edge if v==starter else -edge)):
                    b='even' if abs(e)<60 else ('behind' if e<0 else 'ahead')
                    S[n][b+'_n']+=1
                    if n==k: S[n][b+'_w']+=1
                # adjusted kill at first contact
                ke,ve_=(first[5],first[6]) if first[2]==k else (first[6],first[5]); kpw,vpw=(first[7],first[8]) if first[2]==k else (first[8],first[7])
                state='both' if kpw and vpw else ('has powerup' if kpw else ('vs powerup' if vpw else 'no powerup'))
                S[k]['adj']+=min(3.0,0.5/max(0.05,pfight(ke-ve_,state)))
            for r in frags:
                t,_,k,v,_,ae,ve,pa,pv,arl,alg,vrl,vlg,vtss,fd,tl=r
                frac=max(0.0,min(1.0,tl/dur))
                pre=pwin(m,fd-1,frac,ae-ve,(1 if pa else 0)-(1 if pv else 0),arl-vrl,alg-vlg)
                post=pwin(m,fd,frac,ae,(1 if pa else 0),arl,alg)
                dp=post-pre; S[k]['pm']+=dp; S[v]['pm']-=dp; S[k]['kills']+=1
                if vtss is not None and vtss<=3000: S[v]['spawn_deaths']+=1
                elif v in last_death and t-last_death[v]<=14000: S[v]['chained_real']+=1
                last_death[v]=t
                # item-first: did the victim take armor/mega before his next damage exchange?
                if have_items:
                    nxt=next((x[0] for x in ev if x[0]>t and (x[2]==v or x[3]==v)),None)
                    tk=[x for x in takes[v] if x[0]>t and (nxt is None or x[0]<nxt) and x[1] in ('ra','ya','ga','mh')]
                    if tk: S[v]['item_first']+=1
        for n in pl:
            o=B if n==A else A; fr,k,d,dg,dt,sg,st_,spf=pl[n]; s=S[n]
            win=1 if (n==ta and sa>sb) or (n==tb and sb>sa) else 0
            mins=dur/60000
            tks=takes.get(n,[])
            ra=sum(1 for x in tks if x[1]=='ra'); ra_t=sum(1 for x in tks if x[1]=='ra' and (x[2] or 0)<=3000)
            ya=sum(1 for x in tks if x[1]=='ya'); mh=sum(1 for x in tks if x[1]=='mh')
            out.append((gid,ts,mp,n,o,win,round(mins,2),fr,s['kills'],d,round(s['adj'],2),dg,dt,round(dg/max(dt,1),3),round(sg/max(st_,1),3),
                        s['spawn_deaths'],pl[o][7],s['chained_real'],s['fights'],s['started'],s['started_behind'],s['started_ahead'],
                        s['even_w'],s['even_n'],s['behind_w'],s['behind_n'],s['ahead_w'],s['ahead_n'],
                        s['item_first'] if have_items else None, ra if have_items else None, ra_t if have_items else None, ya if have_items else None, mh if have_items else None,
                        round(s['pm']/FE,2),round(s['pm']/FE/mins,3)))
        if gi%2000==0: print(f'{gi}/{len(GAMES)} {time.time()-t0:.0f}s',flush=True)
    con.executemany("INSERT INTO player_duel VALUES ("+",".join("?"*35)+")",out); con.commit()
    print('player_duel rows',len(out), flush=True)
    con.executescript("""
    DROP TABLE IF EXISTS player_duel_career;
    CREATE TABLE player_duel_career AS
    SELECT name, COUNT(*) games, ROUND(AVG(win)*100,1) win_pct, ROUND(SUM(minutes),0) minutes,
      ROUND(SUM(frags)*1.0/SUM(minutes),2) frags_pm, ROUND(SUM(deaths)*1.0/SUM(minutes),2) deaths_pm,
      ROUND(SUM(adj_kills)*1.0/SUM(minutes),2) adj_kills_pm, ROUND(SUM(dmg)*1.0/SUM(minutes),0) dmg_pm,
      ROUND(SUM(dmg)*1.0/MAX(SUM(taken),1),3) ddr,
      ROUND(SUM(sddr*taken)/MAX(SUM(taken),1),3) sddr_w,
      ROUND(100.0*SUM(spawn_deaths)/MAX(SUM(deaths),1),1) spawn_death_pct,
      ROUND(100.0*SUM(chained_real)/MAX(SUM(deaths),1),1) chained_real_pct,
      ROUND(100.0*SUM(started)/MAX(SUM(fights),1),1) started_pct,
      ROUND(100.0*SUM(started_behind)/MAX(SUM(started),1),1) started_behind_pct,
      ROUND(100.0*SUM(even_w)/MAX(SUM(even_n),1),1) even_win_pct, SUM(even_n) even_n,
      ROUND(100.0*SUM(behind_w)/MAX(SUM(behind_n),1),1) behind_win_pct, SUM(behind_n) behind_n,
      ROUND(100.0*SUM(ahead_w)/MAX(SUM(ahead_n),1),1) ahead_win_pct, SUM(ahead_n) ahead_n,
      ROUND(100.0*SUM(item_first)/MAX(SUM(deaths),1),1) item_first_pct,
      ROUND(AVG(ra),2) ra_pg, ROUND(100.0*SUM(ra_on_timer)/MAX(SUM(ra),1),1) ra_on_timer_pct, ROUND(AVG(ya),2) ya_pg, ROUND(AVG(mh),2) mh_pg,
      ROUND(SUM(plus_minus)/COUNT(*),2) plus_minus_pg, ROUND(SUM(plus_minus)/SUM(minutes),3) plus_minus_pm,
      MAX(ts) last_game
    FROM player_duel GROUP BY name;""")
    con.commit()
    print('\n== duel career, 100+ games, by +/- per game ==')
    for r in con.execute("SELECT name,games,win_pct,plus_minus_pg,adj_kills_pm,sddr_w,started_behind_pct,even_win_pct,item_first_pct,ra_pg FROM player_duel_career WHERE games>=100 ORDER BY plus_minus_pg DESC LIMIT 15"):
        print('  ',r)

if __name__=='__main__':
    if '--score-only' not in sys.argv: fit()
    if '--fit-only' not in sys.argv: score()

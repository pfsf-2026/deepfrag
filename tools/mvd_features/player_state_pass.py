"""Fours re-pass (v2): one row per PLAYER every 10s (health, armor, effective HP, weapons, ammo, power-ups, alive, zone)
plus per-player per-game shot stats: rockets/cells/shells/nails fired, RL direct hits, RL direct vs splash damage, rockets that did any damage."""
import json, sqlite3, subprocess, sys, os, time, bisect, collections, urllib.request, gzip, shutil, tempfile, math
from multiprocessing import Pool
ANALYZER=os.path.abspath('../qw-analyze'); DB='/Users/peteryeargin/Projects/qw-stats/data/mvd_features.sqlite'
RATIO={'ra':0.8,'ya':0.6,'ga':0.3,'':0.0}
def eff(h,a,at):
    r=RATIO.get(at,0)
    if h<=0: return 0
    return h/(1-r) if (r>0 and r*h/(1-r)<=a) else h+a
class S:
    def __init__(s,series,default=0): s.t=[e['t'] for e in series]; s.v=[e['v'] for e in series]; s.d=default
    def at(s,t):
        i=bisect.bisect_right(s.t,t)-1; return s.v[i] if i>=0 else s.d
def decs(series,step):
    out=[];prev=None
    for e in series:
        if prev is not None and e['v']-prev==-step: out.append(e['t'])
        prev=e['v']
    return out
def process(g):
    gid=g['id']; sha=g['demo_sha256']; tmp=tempfile.mkdtemp(prefix='mvd_')
    try:
        url=f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz"; gz=os.path.join(tmp,'d.mvd.gz'); mvd=os.path.join(tmp,'d.mvd')
        with urllib.request.urlopen(url,timeout=60) as r, open(gz,'wb') as f: shutil.copyfileobj(r,f)
        with gzip.open(gz,'rb') as fi, open(mvd,'wb') as fo: shutil.copyfileobj(fi,fo)
        out=subprocess.run([ANALYZER,'-view','full','-include','positions',mvd],capture_output=True,timeout=120)
        d=json.loads(out.stdout); END=d['streams']['global']['matchEnd']
        team={p['name']:p['team'] for p in d['match']['players']}
        for sp_ in d['streams']['players']:
            if sp_['name'] not in team and sp_.get('team'): team[sp_['name']]=sp_['team']
        P={p['name']:p for p in d['streams']['players'] if p['name'] in team and p.get('h') is not None}
        if len(P)<2: return {'id':gid,'rows':[],'shots':[]}
        H={n:S(P[n].get('h',[]),100) for n in P}; A={n:S(P[n].get('a',[]),0) for n in P}; AT={n:S(P[n].get('at',[]),'') for n in P}
        CL={n:S(P[n].get('cl',[]),0) for n in P}; RK={n:S(P[n].get('rk',[]),0) for n in P}; SH={n:S(P[n].get('sh',[]),0) for n in P}; NL={n:S(P[n].get('nl',[]),0) for n in P}
        IV={n:{k:[(iv['s'],iv['e']) for iv in P[n].get(k,[])] for k in ('rl','lg','gl','sng','ssg','ng','q','pe','r')} for n in P}
        loctab=d['timelineAnalysis'].get('locTable',[])
        def has(n,k,t): return any(s<=t<=e for s,e in IV[n][k])
        def alive(n,t):
            sp=P[n].get('sp',[]); i=bisect.bisect_right(sp,t)-1; s=sp[i] if i>=0 else 0
            dl=P[n].get('d',[]); j=bisect.bisect_right(dl,t)-1; return not (j>=0 and dl[j]>s)
        def loc(n,t):
            ps=P[n].get('pos')
            if not ps or not ps.get('t'): return ''
            i=max(0,bisect.bisect_right(ps['t'],t)-1); li=ps['li'][i]
            return loctab[li] if 0<=li<len(loctab) else ''
        rows=[]
        for t in range(0,END,10000):
            for n in P:
                al=int(alive(n,t)); h=H[n].at(t) if al else 0; a=A[n].at(t) if al else 0; at=AT[n].at(t) if al else ''
                rows.append((gid,t,n,team[n],al,h,a,at,round(eff(h,a,at)) if al else 0,
                             int(has(n,'rl',t)),int(has(n,'lg',t)),int(has(n,'gl',t)),int(has(n,'sng',t)),int(has(n,'ssg',t)),
                             CL[n].at(t),RK[n].at(t),SH[n].at(t),NL[n].at(t),int(has(n,'q',t)),int(has(n,'pe',t)),int(has(n,'r',t)),loc(n,t)))
        # shot stats: fired counts from ammo decrements; RL hit quality from damage events (capped damage, enemies only)
        def capped(e):
            v=e['victim']; t=e['time']; h0=H[v].at(t-1); a0=A[v].at(t-1); r=RATIO.get(AT[v].at(t-1),0)
            dm=e['damage']; save=min(a0, math.ceil(dm*r)); take=math.ceil(dm-save); return save+max(0,min(take,h0))
        dmg=[e for e in d['damage']['events'] if e['attacker'] in P and e['victim'] in P and e['attacker']!=e['victim'] and team[e['attacker']]!=team[e['victim']] and e['time']>=0]
        shots=[]
        for n in P:
            rk=len(decs(P[n].get('rk',[]),1)); cl=len(decs(P[n].get('cl',[]),1)); sh=len(decs(P[n].get('sh',[]),1))+len(decs(P[n].get('sh',[]),2)); nl=len(decs(P[n].get('nl',[]),1))+len(decs(P[n].get('nl',[]),2))
            mine=[e for e in dmg if e['attacker']==n and e['weapon']=='rl']
            direct=[e for e in mine if not e.get('isSplash')]; splash=[e for e in mine if e.get('isSplash')]
            # one rocket = all rl damage events by this player within a 60ms window
            impacts=0; last=-10**9
            for e in sorted(mine,key=lambda e:e['time']):
                if e['time']-last>60: impacts+=1
                last=e['time']
            lgd=sum(capped(e) for e in dmg if e['attacker']==n and e['weapon']=='lg')
            gld=sum(capped(e) for e in dmg if e['attacker']==n and e['weapon']=='gl')
            shots.append((gid,n,rk,cl,sh,nl,len(direct),sum(capped(e) for e in direct),sum(capped(e) for e in splash),impacts,lgd,gld))
        return {'id':gid,'rows':rows,'shots':shots}
    except Exception as e:
        return {'id':gid,'error':f'{type(e).__name__}: {str(e)[:120]}'}
    finally: shutil.rmtree(tmp,ignore_errors=True)
def main():
    con=sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS player_state10s(game_id INT, t INT, name TEXT, team TEXT, alive INT, h INT, a INT, at TEXT, eff INT,
                   rl INT, lg INT, gl INT, sng INT, ssg INT, cells INT, rockets INT, shells INT, nails INT, quad INT, pent INT, ring INT, loc TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS ps_g ON player_state10s(game_id)")
    con.execute("""CREATE TABLE IF NOT EXISTS player_shots(game_id INT, name TEXT, rockets_fired INT, cells_fired INT, shells_fired INT, nails_fired INT,
                   rl_direct_hits INT, rl_direct_dmg INT, rl_splash_dmg INT, rockets_with_damage INT, lg_dmg INT, gl_dmg INT)""")
    con.execute("CREATE INDEX IF NOT EXISTS sh_g ON player_shots(game_id)")
    con.commit()
    done={r[0] for r in con.execute("SELECT DISTINCT game_id FROM player_shots")}
    ids={r[0] for r in con.execute("SELECT id FROM games WHERE mode='4on4'")}
    games=[g for g in json.load(open('manifest_all.json')) if g['id'] in ids and g['id'] not in done]
    print(f'todo {len(games)} fours', flush=True); t0=time.time(); n=0; errs=0
    with Pool(6) as pool:
        for res in pool.imap_unordered(process, games, chunksize=2):
            n+=1
            if 'error' in res: errs+=1; print('ERR',res['id'],res['error'],flush=True)
            else:
                con.executemany("INSERT INTO player_state10s VALUES ("+",".join("?"*22)+")",res['rows'])
                con.executemany("INSERT INTO player_shots VALUES ("+",".join("?"*12)+")",res['shots'])
            if n%25==0: con.commit(); print(f'{n}/{len(games)} {errs} errors {time.time()-t0:.0f}s eta {(len(games)-n)*(time.time()-t0)/n/60:.0f} min', flush=True)
    con.commit(); print(f'FINISHED {n} {errs} errors {time.time()-t0:.0f}s', flush=True)
if __name__=='__main__': main()

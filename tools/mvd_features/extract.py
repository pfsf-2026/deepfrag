"""POC feature extraction: hub game -> demo -> qw-analyze -> compact rows in SQLite.
Tables: games, players, events (dmg+frag with both players' state), state10s (team state
samples for the win-probability model), player_game (derived per-player stats), errors."""
import json, sqlite3, subprocess, sys, os, time, math, bisect, collections, urllib.request, gzip, shutil, tempfile
from multiprocessing import Pool
ANALYZER=os.path.abspath('../qw-analyze'); DB='features.sqlite'
ALLOWED=("The-Den","la.quake.world","Mom's Basement","ny.quake.world")
RATIO={'ra':0.8,'ya':0.6,'ga':0.3,'':0.0}
def eff(h,a,at):
    r=RATIO.get(at,0)
    if h<=0: return 0
    return h/(1-r) if (r>0 and r*h/(1-r)<=a) else h+a
class S:
    __slots__=('t','v','d')
    def __init__(s,series,default=0): s.t=[e['t'] for e in series]; s.v=[e['v'] for e in series]; s.d=default
    def at(s,t):
        i=bisect.bisect_right(s.t,t)-1; return s.v[i] if i>=0 else s.d
def in_iv(ivs,t): return any(s<=t<=e for s,e in ivs)
def process(g):
    gid=g['id']; sha=g['demo_sha256']; tmp=tempfile.mkdtemp(prefix='mvd_')
    try:
        url=f"https://d.quake.world/{sha[:3]}/{sha}.mvd.gz"; gz=os.path.join(tmp,'d.mvd.gz'); mvd=os.path.join(tmp,'d.mvd')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url,timeout=60) as r, open(gz,'wb') as f: shutil.copyfileobj(r,f)
                break
            except Exception as e:
                if attempt==2: return {'id':gid,'error':f'download: {e}'}
                time.sleep(2)
        with gzip.open(gz,'rb') as fi, open(mvd,'wb') as fo: shutil.copyfileobj(fi,fo)
        out=subprocess.run([ANALYZER,'-view','full','-include','positions',mvd],capture_output=True,timeout=120)
        if not out.stdout.strip(): return {'id':gid,'error':f'analyzer: {out.stderr[-200:]!r}'}
        d=json.loads(out.stdout)
        return rows_for(g,d)
    except Exception as e:
        return {'id':gid,'error':f'{type(e).__name__}: {str(e)[:200]}'}
    finally:
        shutil.rmtree(tmp,ignore_errors=True)
def rows_for(g,d):
    gid=g['id']; END=d['streams']['global']['matchEnd']
    mp=d['match']['players']; team={p['name']:p['team'] for p in mp}; fr={p['name']:p['frags'] for p in mp}
    for sp_ in d['streams']['players']:   # players who left before the end are missing from match.players but have full streams
        if sp_['name'] not in team and sp_.get('team'):
            team[sp_['name']]=sp_['team']
            k=sum(1 for f in d['frags']['frags'] if f['killer']==sp_['name'] and f['victim']!=sp_['name'] and team.get(f['victim'])!=sp_['team'])
            fr[sp_['name']]=k-sum(1 for f in d['frags']['frags'] if f['killer']==sp_['name'] and (f['victim']==sp_['name'] or team.get(f['victim'])==sp_['team']))
    P={p['name']:p for p in d['streams']['players'] if p['name'] in team and p.get('pos') and p.get('h') is not None}
    for n in P:  # tolerate missing series (late joiners, ghosts)
        for k,dflt in (('h',[]),('a',[]),('at',[]),('sp',[]),('d',[]),('rk',[]),('cl',[]),('sh',[]),('nl',[])):
            if P[n].get(k) is None: P[n][k]=dflt
    team={n:team[n] for n in P}; fr={n:fr[n] for n in P}
    if len(P)<2: return {'id':gid,'error':'fewer than 2 players in streams'}
    if not d.get('items') or d['items'].get('items') is None: d['items']={'items':[]}
    if not d.get('damage') or d['damage'].get('events') is None: d['damage']={'events':[]}
    if not d.get('frags') or d['frags'].get('frags') is None: d['frags']={'frags':[]}
    H={n:S(P[n]['h'],100) for n in P}; A={n:S(P[n]['a'],0) for n in P}; AT={n:S(P[n]['at'],'') for n in P}
    Q={n:[(iv['s'],iv['e']) for iv in P[n].get('q',[])] for n in P}
    PE={n:[(iv['s'],iv['e']) for iv in P[n].get('pe',[])] for n in P}
    RL={n:[(iv['s'],iv['e']) for iv in P[n].get('rl',[])] for n in P}; LG={n:[(iv['s'],iv['e']) for iv in P[n].get('lg',[])] for n in P}
    POS={}
    for n in P:
        ps=P[n]['pos']; POS[n]=(ps['t'],ps['x'],ps['y'],ps['z'])
    def pos(n,t):
        pt,x,y,z=POS[n]; i=max(0,bisect.bisect_right(pt,t)-1); return (x[i],y[i],z[i])
    def tss(n,t):
        sp=P[n]['sp']; i=bisect.bisect_right(sp,t)-1; return (t-sp[i]) if i>=0 else t
    def alive(n,t):
        sp=P[n]['sp']; i=bisect.bisect_right(sp,t)-1; s=sp[i] if i>=0 else 0
        dl=P[n]['d']; j=bisect.bisect_right(dl,t)-1
        return not (j>=0 and dl[j]>s)
    def capped(e):
        v=e['victim']; t=e['time']; h0=H[v].at(t-1); a0=A[v].at(t-1); r=RATIO.get(AT[v].at(t-1),0)
        dmg=e['damage']; save=min(a0, math.ceil(dmg*r)); take=math.ceil(dmg-save)
        return save+max(0,min(take,h0))
    def state(n,t):
        h=H[n].at(t); a=A[n].at(t); at=AT[n].at(t)
        return h,a,at,eff(h,a,at),int(in_iv(RL[n],t)),int(in_iv(LG[n],t)),int(in_iv(Q[n],t) or in_iv(PE[n],t))
    teams=sorted(set(team.values())); is_team=len(teams)==2 and len(P)>2
    def enemy(a,b): return (team[a]!=team[b]) if is_team else (a!=b)
    # running team score for frag-diff-at-time
    frags=[f for f in d['frags']['frags'] if f['killer'] in P and f['victim'] in P and f['time']>=0]
    sc=collections.Counter(); sct=[]; scv=[]
    for f in sorted(frags,key=lambda f:f['time']):
        if enemy(f['killer'],f['victim']): sc[team[f['killer']] if is_team else f['killer']]+=1
        else: sc[team[f['victim']] if is_team else f['victim']]-=1
        sct.append(f['time']); scv.append(dict(sc))
    def diff_at(side,t):
        i=bisect.bisect_right(sct,t)-1; s=scv[i] if i>=0 else {}
        if is_team:
            other=[x for x in teams if x!=side][0]; return s.get(side,0)-s.get(other,0)
        others=[n for n in P if n!=side]; return s.get(side,0)-(s.get(others[0],0) if others else 0)
    side_of=(lambda n: team[n]) if is_team else (lambda n: n)
    ev=[]; PG={n:collections.Counter() for n in P}
    dmg=[e for e in d['damage']['events'] if e['attacker'] in P and e['victim'] in P and e['time']>=0 and e['attacker']!='world']
    for e in dmg:
        a,v,t=e['attacker'],e['victim'],e['time']; sa=state(a,t-30); sv=state(v,t-30)
        selfd=int(a==v); teamd=int((not selfd) and (not enemy(a,v)))
        dist=math.dist(pos(a,t),pos(v,t)) if not selfd else 0
        dc=capped(e)
        ev.append((gid,t,'dmg',a,v,e['weapon'],e['damage'],dc,int(bool(e.get('isSplash'))),selfd,teamd,
                   sa[0],sa[1],sa[2],round(sa[3]),sa[4],sa[5],sa[6],tss(a,t),sv[0],sv[1],sv[2],round(sv[3]),sv[4],sv[5],sv[6],tss(v,t),round(dist),diff_at(side_of(a),t),END-t))
        if not selfd and not teamd:
            PG[a]['dmg_given']+=dc; PG[v]['dmg_taken']+=dc
            if sa[3]>=150: PG[a]['stacked_given']+=dc
            if sa[3]<100: PG[a]['naked_given']+=dc
            if sv[3]>=150: PG[v]['stacked_taken']+=dc
    for f in frags:
        k,v,t=f['killer'],f['victim'],f['time']; sk=state(k,t-30); sv=state(v,t-30)
        selfd=int(k==v); teamd=int((not selfd) and (not enemy(k,v)))
        dist=math.dist(pos(k,t),pos(v,t)) if not selfd else 0
        ev.append((gid,t,'frag',k,v,f['weapon'],0,0,0,selfd,teamd,
                   sk[0],sk[1],sk[2],round(sk[3]),sk[4],sk[5],sk[6],tss(k,t),sv[0],sv[1],sv[2],round(sv[3]),sv[4],sv[5],sv[6],tss(v,t),round(dist),diff_at(side_of(k),t),END-t))
        if selfd: PG[v]['suicides']+=1
        elif teamd: PG[k]['teamkills']+=1
        else:
            PG[k]['kills']+=1
            if tss(v,t)<=3000: PG[v]['spawn_deaths']+=1
            if tss(v,t)<=2000: PG[k]['spawnfrags']+=1
    for n in P:
        dl=P[n]['d']; PG[n]['deaths']=len(dl); PG[n]['chained']=sum(1 for i in range(1,len(dl)) if dl[i]-dl[i-1]<14000)
        ks=sorted(f['time'] for f in frags if f['killer']==n and enemy(n,f['victim']))
        PG[n]['multi']=sum(1 for i in range(1,len(ks)) if ks[i]-ks[i-1]<=8000)
        ra=0; effsum=0; nsamp=0
        for t in range(0,END,1000):
            if not alive(n,t): continue
            nsamp+=1; s=state(n,t); effsum+=s[3]; ra+= (s[2]=='ra')
        PG[n]['alive_s']=nsamp; PG[n]['ra_s']=ra; PG[n]['avg_eff']=round(effsum/max(1,nsamp))
    for it in d['items']['items']:
        for ph in it['phases']:
            if ph.get('takenBy') in PG and ph.get('takenAt') is not None: PG[ph['takenBy']]['take_'+it['kind']]+=1
    st=[]
    if is_team:
        for t in range(0,END,10000):
            for side in teams:
                mem=[n for n in P if team[n]==side]; al=[n for n in mem if alive(n,t)]
                ss=[state(n,t) for n in al]
                st.append((gid,t,side,diff_at(side,t),END-t,len(al),round(sum(s[3] for s in ss)),int(any(s[6] for s in ss)),sum(s[4] for s in ss),sum(s[5] for s in ss),sum(1 for s in ss if s[2]=='ra')))
    tm=d['match'].get('teams') or []
    game=(gid,g['timestamp'],g['map'],g['mode'],g['server_hostname'],END,tm[0]['name'] if tm else None,tm[1]['name'] if len(tm)>1 else None,tm[0]['frags'] if tm else None,tm[1]['frags'] if len(tm)>1 else None,len(P))
    players=[(gid,n,team[n],fr[n],PG[n]['kills'],PG[n]['deaths'],PG[n]['suicides'],PG[n]['teamkills'],PG[n]['dmg_given'],PG[n]['dmg_taken'],PG[n]['stacked_given'],PG[n]['naked_given'],PG[n]['stacked_taken'],PG[n]['spawn_deaths'],PG[n]['spawnfrags'],PG[n]['chained'],PG[n]['multi'],PG[n]['alive_s'],PG[n]['ra_s'],PG[n]['avg_eff'],PG[n]['take_ra'],PG[n]['take_ya'],PG[n]['take_ga'],PG[n]['take_mh'],PG[n]['take_quad'],PG[n]['take_pent'],PG[n]['take_ring']) for n in P]
    return {'id':gid,'game':game,'players':players,'events':ev,'state':st}
DDL="""
CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY, ts TEXT, map TEXT, mode TEXT, server TEXT, dur_ms INT, team_a TEXT, team_b TEXT, score_a INT, score_b INT, n_players INT);
CREATE TABLE IF NOT EXISTS players(game_id INT, name TEXT, team TEXT, frags INT, kills INT, deaths INT, suicides INT, teamkills INT, dmg_given INT, dmg_taken INT, stacked_given INT, naked_given INT, stacked_taken INT, spawn_deaths INT, spawnfrags INT, chained INT, multi INT, alive_s INT, ra_s INT, avg_eff INT, take_ra INT, take_ya INT, take_ga INT, take_mh INT, take_quad INT, take_pent INT, take_ring INT);
CREATE TABLE IF NOT EXISTS events(game_id INT, t INT, kind TEXT, att TEXT, vic TEXT, weapon TEXT, dmg INT, dmg_cap INT, splash INT, selfd INT, teamd INT, att_h INT, att_a INT, att_at TEXT, att_eff INT, att_rl INT, att_lg INT, att_pw INT, att_tss INT, vic_h INT, vic_a INT, vic_at TEXT, vic_eff INT, vic_rl INT, vic_lg INT, vic_pw INT, vic_tss INT, dist INT, frag_diff INT, time_left INT);
CREATE TABLE IF NOT EXISTS state10s(game_id INT, t INT, team TEXT, frag_diff INT, time_left INT, n_alive INT, stack_sum INT, powerup INT, rl_n INT, lg_n INT, ra_n INT);
CREATE TABLE IF NOT EXISTS errors(game_id INTEGER PRIMARY KEY, msg TEXT);
CREATE INDEX IF NOT EXISTS ev_g ON events(game_id); CREATE INDEX IF NOT EXISTS pl_g ON players(game_id); CREATE INDEX IF NOT EXISTS pl_n ON players(name);
"""
def main():
    manifest=sys.argv[1]; modes=sys.argv[2].split(',') if len(sys.argv)>2 else ['4on4','1on1']; workers=int(sys.argv[3]) if len(sys.argv)>3 else 6; limit=int(sys.argv[4]) if len(sys.argv)>4 else 10**9
    con=sqlite3.connect(DB); con.executescript(DDL)
    done={r[0] for r in con.execute('SELECT id FROM games')}|{r[0] for r in con.execute('SELECT game_id FROM errors')}
    games=[g for g in json.load(open(manifest)) if g['mode'] in modes and g['id'] not in done and g['server_hostname'].startswith(ALLOWED)]
    games=games[:limit]
    print(f'todo {len(games)} games (modes {modes}), workers {workers}', flush=True)
    t0=time.time(); n=0; errs=0
    with Pool(workers) as pool:
        for res in pool.imap_unordered(process, games, chunksize=2):
            n+=1
            if 'error' in res:
                errs+=1; con.execute('INSERT OR REPLACE INTO errors VALUES (?,?)',(res['id'],res['error']))
            else:
                con.execute('INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?)',res['game'])
                con.executemany('INSERT INTO players VALUES ('+','.join('?'*27)+')',res['players'])
                con.executemany('INSERT INTO events VALUES ('+','.join('?'*30)+')',res['events'])
                con.executemany('INSERT INTO state10s VALUES (?,?,?,?,?,?,?,?,?,?,?)',res['state'])
            if n%10==0:
                con.commit(); el=time.time()-t0
                print(f'{n}/{len(games)} done, {errs} errors, {el:.0f}s elapsed, {el/n:.2f}s/game, eta {(len(games)-n)*el/n/60:.0f} min', flush=True)
    con.commit(); print(f'FINISHED {n} games, {errs} errors, {time.time()-t0:.0f}s', flush=True)
if __name__=='__main__': main()

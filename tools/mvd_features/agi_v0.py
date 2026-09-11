import json, math, bisect, collections, statistics, sys
RATIO={'ra':0.8,'ya':0.6,'ga':0.3,'':0.0}
def eff(h,a,at):
    r=RATIO.get(at,0)
    if h<=0: return 0
    return h/(1-r) if (r>0 and r*h/(1-r)<=a) else h+a
TABLE=json.load(open('f4/fight_table_4on4.json'))['table']
def pwin(edge,state='no powerup'):  # fitted on 716 fours: win rate by stack edge at first contact and power-up state
    pts=TABLE[state]
    if edge<=pts[0][0]: return pts[0][1]
    if edge>=pts[-1][0]: return pts[-1][1]
    for (x0,y0),(x1,y1) in zip(pts,pts[1:]):
        if x0<=edge<=x1: return y0+(y1-y0)*(edge-x0)/(x1-x0)
class S:
    def __init__(s,series,default=0):
        s.t=[e['t'] for e in series]; s.v=[e['v'] for e in series]; s.d=default
    def at(s,t):
        i=bisect.bisect_right(s.t,t)-1; return s.v[i] if i>=0 else s.d
def score(path):
    d=json.load(open(path)); END=d['streams']['global']['matchEnd']
    team={p['name']:p['team'] for p in d['match']['players']}; fr={p['name']:p['frags'] for p in d['match']['players']}
    P={p['name']:p for p in d['streams']['players']}
    H={n:S(P[n]['h'],100) for n in P}; A={n:S(P[n]['a'],0) for n in P}; AT={n:S(P[n]['at'],'') for n in P}
    Q={n:[(iv['s'],iv['e']) for iv in P[n].get('q',[])]+[(iv['s'],iv['e']) for iv in P[n].get('pe',[])] for n in P}
    def st(n,t): return eff(H[n].at(t),A[n].at(t),AT[n].at(t))
    def pw(n,t): return any(s<=t<=e_ for s,e_ in Q[n])
    def pwstate(k,v,t):
        a,b=pw(k,t),pw(v,t); return 'both' if a and b else ('has powerup' if a else ('vs powerup' if b else 'no powerup'))
    def capped(e):
        v=e['victim']; t=e['time']; h0=H[v].at(t-1); a0=A[v].at(t-1); r=RATIO.get(AT[v].at(t-1),0)
        dmg=e['damage']; save=min(a0, math.ceil(dmg*r)); take=math.ceil(dmg-save)
        return save+max(0,min(take,h0))
    def tss(n,t):
        sp=P[n]['sp']; i=bisect.bisect_right(sp,t)-1; return (t-sp[i]) if i>=0 else t
    dmg=[e for e in d['damage']['events'] if e['attacker']!='world' and e['attacker'] in team and e['victim'] in team and e['attacker']!=e['victim'] and team[e['attacker']]!=team[e['victim']] and e['time']>=0]
    frags=[f for f in d['frags']['frags'] if f['killer'] in team and f['victim'] in team and team[f['killer']]!=team[f['victim']] and f['time']>=0]
    R={n:collections.Counter() for n in P}
    for e in dmg:
        a,v,t=e['attacker'],e['victim'],e['time']; ea=st(a,t-30); ev=st(v,t-30); dm=capped(e)
        R[a]['dmg']+=dm; R[v]['taken']+=dm
        if ea>=150: R[a]['stk_given']+=dm
        if ev>=150: R[v]['stk_taken']+=dm
    dmg_by_v=collections.defaultdict(list)
    for e in dmg: dmg_by_v[e['victim']].append(e)
    for f in frags:
        k,v,t=f['killer'],f['victim'],f['time']; R[k]['kills']+=1; R[v]['deaths_e']+=1
        # edge at FIRST CONTACT between killer and victim (damage chain with gaps <= 4s), not at the kill shot
        chain=[e for e in dmg if {e['attacker'],e['victim']}=={k,v} and e['time']<=t]
        t0=t
        for e in reversed(chain):
            if t0-e['time']<=4000: t0=e['time']
            else: break
        edge=st(k,t0-30)-st(v,t0-30); kp=min(3.0, 0.5/pwin(edge,pwstate(k,v,t0-30)))
        # split kill points by damage share on the victim over the last 10s (killer's team only)
        contrib=collections.Counter()
        for e in dmg_by_v[v]:
            if t-10000<=e['time']<=t and team[e['attacker']]==team[k]: contrib[e['attacker']]+=capped(e)
        tot=sum(contrib.values())
        if tot<=0: R[k]['adj']+=kp
        else:
            for a,dm in contrib.items(): R[a]['adj']+=kp*(0.15*(a==k)+0.85*dm/tot)
        if tss(v,t)<=3000: R[v]['spawn_deaths']+=1
    for n in P:
        dl=P[n]['d']; R[n]['deaths']=len(dl); R[n]['chained']=sum(1 for i in range(1,len(dl)) if dl[i]-dl[i-1]<14000)
        ks=sorted(f['time'] for f in frags if f['killer']==n)
        R[n]['multi']=sum(1 for i in range(1,len(ks)) if ks[i]-ks[i-1]<=8000)
    for it in d['items']['items']:
        for ph in it['phases']:
            if ph.get('takenBy') in R and ph.get('takenAt') is not None:
                R[ph['takenBy']]['take_'+it['kind']]+=1
    rows=[]
    for n in P:
        r=R[n]; items=r['take_ra']*1.0+r['take_ya']*0.6+r['take_mh']*0.8+r['take_quad']*2.0+r['take_pent']*2.0
        rows.append(dict(name=n,team=team[n],frags=fr[n],kills=r['kills'],adj=r['adj'],dmg=r['dmg'],taken=r['taken'],sddr=(r['stk_given']/max(1,r['stk_taken'])),
                         deaths=r['deaths'],spawn=r['spawn_deaths'],chained=r['chained'],multi=r['multi'],items=items,quad=r['take_quad'],ra=r['take_ra']))
    def norm(key,inv=False):
        m=statistics.mean(x[key] for x in rows) or 1
        for x in rows: x['n_'+key]=(m/max(0.5,x[key])) if inv else (x[key]/m)
    for k in ('adj','dmg','multi','items'): norm(k)
    norm('deaths',inv=True); 
    m=statistics.mean(x['sddr'] for x in rows) or 1
    for x in rows: x['n_sddr']=x['sddr']/m
    for x in rows: x['AGI']=0.30*x['n_adj']+0.15*x['n_dmg']+0.15*x['n_sddr']+0.15*x['n_deaths']+0.05*min(2.0,x['n_multi'])+0.20*x['n_items']
    m=statistics.mean(x['AGI'] for x in rows)
    for x in rows: x['AGI']/=m
    print(f"\n=== {d['demoInfo']['map']}  {d['match']['teams'][0]['name']} {d['match']['teams'][0]['frags']} - {d['match']['teams'][1]['name']} {d['match']['teams'][1]['frags']} ===")
    print(f"{'player':16s} {'team':5s} {'frags':>5s} {'adjK':>6s} {'dmg':>6s} {'sDDR':>5s} {'D':>3s} {'spwD':>4s} {'chn':>3s} {'multi':>5s} {'RA':>3s} {'Q':>2s} {'items':>5s} | {'AGI':>5s}")
    for x in sorted(rows,key=lambda x:-x['AGI']):
        print(f"{x['name']:16s} {x['team']:5s} {x['frags']:5d} {x['adj']:6.1f} {x['dmg']:6d} {x['sddr']:5.2f} {x['deaths']:3d} {x['spawn']:4d} {x['chained']:3d} {x['multi']:5d} {x['ra']:3d} {x['quad']:2d} {x['items']:5.1f} | {x['AGI']:5.2f}")
for p in sys.argv[1:]: score(p)

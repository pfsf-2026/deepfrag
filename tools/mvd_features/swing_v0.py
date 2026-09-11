import json, math, bisect, collections, sys
RATIO={'ra':0.8,'ya':0.6,'ga':0.3,'':0.0}
def eff(h,a,at):
    r=RATIO.get(at,0)
    if h<=0: return 0
    return h/(1-r) if (r>0 and r*h/(1-r)<=a) else h+a
M=json.load(open('f4/winprob_4on4.json')); COEF=M['coef']; B0=M['intercept']
def pwin(fd,frac,sd,ad,pw,rl,lg,ra):
    x=[fd, fd*frac, fd/(frac+0.05), sd/100, ad, pw, rl, lg, ra, frac]
    z=B0+sum(c*v for c,v in zip(COEF,x)); return 1/(1+math.exp(-z))
class S:
    def __init__(s,series,default=0): s.t=[e['t'] for e in series]; s.v=[e['v'] for e in series]; s.d=default
    def at(s,t):
        i=bisect.bisect_right(s.t,t)-1; return s.v[i] if i>=0 else s.d
def compute(path):
    d=json.load(open(path)); END=d['streams']['global']['matchEnd']
    team={p['name']:p['team'] for p in d['match']['players']}; P={p['name']:p for p in d['streams']['players'] if p['name'] in team}
    teams=sorted(set(team.values()))
    H={n:S(P[n]['h'],100) for n in P}; A={n:S(P[n]['a'],0) for n in P}; AT={n:S(P[n]['at'],'') for n in P}
    IV={n:{k:[(iv['s'],iv['e']) for iv in P[n].get(k,[])] for k in ('q','pe','rl','lg')} for n in P}
    def has(n,k,t): return any(s<=t<=e for s,e in IV[n][k])
    def alive(n,t):
        sp=P[n]['sp']; i=bisect.bisect_right(sp,t)-1; s=sp[i] if i>=0 else 0
        dl=P[n]['d']; j=bisect.bisect_right(dl,t)-1; return not (j>=0 and dl[j]>s)
    def pstate(n,t):
        if not alive(n,t): return dict(eff=0,alive=0,pw=0,rl=0,lg=0,ra=0)
        return dict(eff=eff(H[n].at(t),A[n].at(t),AT[n].at(t)),alive=1,pw=int(has(n,'q',t) or has(n,'pe',t)),rl=int(has(n,'rl',t)),lg=int(has(n,'lg',t)),ra=int(AT[n].at(t)=='ra'))
    frags=[f for f in d['frags']['frags'] if f['killer'] in P and f['victim'] in P and f['time']>=0]
    sc_t=[];sc_v=[];sc=collections.Counter()
    for f in sorted(frags,key=lambda f:f['time']):
        if team[f['killer']]!=team[f['victim']]: sc[team[f['killer']]]+=1
        else: sc[team[f['victim']]]-=1
        sc_t.append(f['time']); sc_v.append(dict(sc))
    def fragdiff(side,t):
        i=bisect.bisect_right(sc_t,t)-1; s=sc_v[i] if i>=0 else {}; o=[x for x in teams if x!=side][0]; return s.get(side,0)-s.get(o,0)
    def teamP(side,t,override=None):
        o=[x for x in teams if x!=side][0]; st={n:pstate(n,t) for n in P}
        if override: st.update(override)
        def agg(s): 
            m=[st[n] for n in P if team[n]==s]; return dict(eff=sum(x['eff'] for x in m),alive=sum(x['alive'] for x in m),pw=int(any(x['pw'] for x in m)),rl=sum(x['rl'] for x in m),lg=sum(x['lg'] for x in m),ra=sum(x['ra'] for x in m))
        a,b=agg(side),agg(o); frac=(END-t)/1000/1200
        return pwin(fragdiff(side,t),frac,a['eff']-b['eff'],a['alive']-b['alive'],a['pw']-b['pw'],a['rl']-b['rl'],a['lg']-b['lg'],a['ra']-b['ra'])
    SW={n:collections.Counter() for n in P}
    dmg=[e for e in d['damage']['events'] if e['attacker'] in P and e['victim'] in P and e['attacker']!=e['victim'] and team[e['attacker']]!=team[e['victim']] and e['time']>=0]
    def capped(e):
        v=e['victim']; t=e['time']; h0=H[v].at(t-1); a0=A[v].at(t-1); r=RATIO.get(AT[v].at(t-1),0)
        dm=e['damage']; save=min(a0, math.ceil(dm*r)); take=math.ceil(dm-save); return save+max(0,min(take,h0))
    dmg_by_v=collections.defaultdict(list)
    for e in dmg: dmg_by_v[e['victim']].append(e)
    def agg(s,st):
        m=[st[n] for n in P if team[n]==s]; return dict(eff=sum(x['eff'] for x in m),alive=sum(x['alive'] for x in m),pw=int(any(x['pw'] for x in m)),rl=sum(x['rl'] for x in m),lg=sum(x['lg'] for x in m),ra=sum(x['ra'] for x in m))
    def Pside(side,fd,t,st):
        o=[x for x in teams if x!=side][0]; frac=(END-t)/1000/1200; a,b=agg(side,st),agg(o,st)
        return pwin(fd,frac,a['eff']-b['eff'],a['alive']-b['alive'],a['pw']-b['pw'],a['rl']-b['rl'],a['lg']-b['lg'],a['ra']-b['ra'])
    # HLTV-style: only kill events move swing. A kill = +1 frag diff and the victim loses whatever stack,
    # weapons and power-up he still had (alive count held constant: respawn is near-instant in QW).
    # Credit: 15% finisher + 85% by damage share over the victim's last 10s. Victim is debited in full.
    for f in frags:
        k,v,t=f['killer'],f['victim'],f['time']
        if team[k]==team[v]: continue
        side=team[k]; st={n:pstate(n,t-1) for n in P}
        fd=fragdiff(side,t-1); before=Pside(side,fd,t,st)
        st[v]=dict(st[v],eff=0,pw=0,rl=0,lg=0,ra=0); after=Pside(side,fd+1,t,st)
        dp=after-before
        contrib=collections.Counter()
        for e in dmg_by_v[v]:
            if t-10000<=e['time']<=t and team[e['attacker']]==side: contrib[e['attacker']]+=capped(e)
        tot=sum(contrib.values())
        if tot<=0: SW[k]['kill']+=dp
        else:
            for a_,dm in contrib.items(): SW[a_]['kill']+=dp*(0.15*(a_==k)+0.85*dm/tot)
        SW[v]['death']-=dp
        SW[k]['kills_n']+=1
    rows=[]
    for n in P:
        s=SW[n]; tot=s['kill']+s['death']
        rows.append((n,team[n],tot,s['kill'],s['death'],s['kill']/max(1,s['kills_n']),len(P[n]['d'])))
    return d, teams, rows
def run(path):
    d, teams, rows = compute(path)
    tm=d['match']['teams']
    print(f"\n=== {d['demoInfo']['map']} {tm[0]['name']} {tm[0]['frags']} - {tm[1]['name']} {tm[1]['frags']}: SWING (percentage points of map win probability) ===")
    print(f"{'player':16s} {'team':5s} {'SWING':>7s} {'from kills':>10s} {'from deaths':>11s} {'per kill':>8s} {'deaths':>6s}")
    for r in sorted(rows,key=lambda r:-r[2]):
        print(f"{r[0]:16s} {r[1]:5s} {r[2]*100:+7.1f} {r[3]*100:+10.1f} {r[4]*100:+11.1f} {r[5]*100:+8.2f} {r[6]:6d}")
    for s in teams: print(f"  team {s} total: {sum(r[2] for r in rows if r[1]==s)*100:+.1f}")
for p in sys.argv[1:]: run(p)

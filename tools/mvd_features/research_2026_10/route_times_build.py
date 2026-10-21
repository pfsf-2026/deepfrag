"""Build route_times.py — room-to-room travel times per TB4 map — from the mvd-api's loc-trails, with the
runs that used a rocket jump kept apart from the runs that did not.

    python3 route_times_build.py <out.py> <hub_game_id> [<hub_game_id> ...]

A run = entering room a, then room b, within 25 s and in one life (a respawn is not a path). Per map and
pair: [10th-percentile s, median s, runs, 25th-percentile s] for pairs with 8+ runs (no RJ) or 5+ (RJ).

Rocket jumps (Peter, 2026-10-21: "hill MH to quad straight in 0.9 s is not right unless you can RJ … analyze
how one would get there without an RJ, and with an RJ"): a run used an RJ when the player took their own
rocket or grenade splash during it — the damage view's events with attacker == victim, from 1 s before
entering a to 0.3 s after entering b. ROUTE_TIMES holds the runs without one (what a player on a thin stack
or with no rockets can do), ROUTE_TIMES_RJ the runs with one, and ROUTES lists both kinds of way with an
rj flag (1 = rocket-jumped).

Label flips across floors: the parser names rooms by the nearest .loc point with no idea of height, so a
player under the quad platform on the hill can be labelled "Quad" for a moment. Each room's floor height is
the median z of everyone labelled with it (1-second positions from the buckets view, all games). A step into
a room whose floor is more than 100 units from the previous room's, where the player's own height never
comes within 80 units of the new floor while labelled there, and with no rocket jump, lift or teleporter,
is that flip and is dropped. A real stair climb or a rocket jump does reach the new floor and is kept.
Segments under 0.4 s are flicker too. Deaths come from /events (type death)."""
import json, sys, urllib.request, collections, time, bisect, statistics
B = 'https://deepfrag-mvd-api-751658372467.us-central1.run.app/v1/demos/gameId:'
def get(p):
    with urllib.request.urlopen(B + p, timeout=170) as r: return json.loads(r.read())
out_path, gids = sys.argv[1], [int(x) for x in sys.argv[2:]]
LONG = {'The Abandoned Base': 'dm3', 'Claustrophobopolis': 'dm2', 'Castle of the Damned': 'e1m2', 'schloss': 'schloss', 'dm3': 'dm3', 'dm2': 'dm2', 'e1m2': 'e1m2'}
VERT = ('lift', 'tele')          # rooms where a vertical move in under a second is the map, not a label flip

# ── pass 1: fetch everything, keep what the passes need
GAMES = []; games = collections.Counter()
for gid in gids:
    try:
        t = time.time(); di = get(f'{gid}/demoinfo'); mp = (di.get('map') or '').lower()      # demoinfo carries the short map name
        mp = LONG.get(mp, mp)
        if mp not in ('dm3', 'dm2', 'e1m2', 'schloss'): print(gid, 'skip', di.get('map'), flush=True); continue
        tr = get(f'{gid}/loc-trails'); ev = get(f'{gid}/events?types=death')
        dm = get(f'{gid}/damage'); bk = get(f'{gid}/buckets?windowMs=1000&fields=pos')
    except Exception as e:
        print(gid, 'ERR', e, flush=True); continue
    deaths = collections.defaultdict(list)
    for e in ev.get('events', []):
        if e.get('type') == 'death': deaths[e.get('player')].append(e['t'])
    selfd = collections.defaultdict(list)
    for e in dm.get('events', []):
        if e.get('attacker') == e.get('victim') and e.get('weapon') in ('rl', 'gl'):
            selfd[e['victim']].append(e['time'] / 1000.0)
    for v in selfd.values(): v.sort()
    Z = {n: (p.get('z') or []) for n, p in (bk.get('players') or {}).items()}
    players = []
    for p in tr.get('players', []):
        raw = [x for x in p.get('sequence', []) if x.get('loc') and (x.get('e', 0) - x.get('s', 0)) >= 0.4]
        players.append(dict(name=p['name'], raw=raw, deaths=sorted(deaths.get(p['name'], [])), selfd=selfd.get(p['name']) or [], z=Z.get(p['name']) or []))
    GAMES.append((gid, mp, players)); games[mp] += 1
    print(gid, mp, f'{time.time()-t:.0f}s', flush=True)

def z_at(z, s):
    if not z: return None
    i = max(0, min(len(z) - 1, int(s)))
    return z[i]

# ── room floor heights per map: median z of everyone labelled with the room
zs = collections.defaultdict(list)
for gid, mp, players in GAMES:
    for p in players:
        for x in p['raw']:
            for s in range(int(x['s']), int(x['e']) + 1):
                z = z_at(p['z'], s)
                if z is not None: zs[(mp, x['loc'])].append(z)
ROOM_Z = {k: statistics.median(v) for k, v in zs.items() if len(v) >= 30}

# ── pass 2: flips dropped, runs split by rocket jump
obs = collections.defaultdict(lambda: collections.defaultdict(lambda: {False: [], True: []}))
routes = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
dropped = collections.Counter(); kept_climbs = collections.Counter()
for gid, mp, players in GAMES:
    for p in players:
        name, z = p['name'], p['z']
        def rj_in(t0, t1, v=p['selfd']):
            i = bisect.bisect_left(v, t0)
            return i < len(v) and v[i] <= t1
        seq = []
        for x in p['raw']:
            if seq:
                prev = seq[-1]
                za, zb = ROOM_Z.get((mp, prev['loc'])), ROOM_Z.get((mp, x['loc']))
                if (za is not None and zb is not None and abs(zb - za) > 100
                        and not any(k in (prev['loc'] + ' ' + x['loc']).lower() for k in VERT)):
                    samples = [z_at(z, s) for s in (x['s'], x['s'] + 0.5, x['s'] + 1.0, x['e'])]
                    reached = any(v is not None and abs(v - zb) < 80 for v in samples)
                    if not reached and not rj_in(prev['s'] - 1.0, x['s'] + 0.3):
                        dropped[(mp, prev['loc'], x['loc'])] += 1
                        continue
                    kept_climbs[(mp, prev['loc'], x['loc'])] += 1
            seq.append(x)
        seq = [(x['s'], x['loc']) for x in seq]
        dd = p['deaths']
        for i, (t0, a) in enumerate(seq):
            nd = next((x for x in dd if x > t0), None); seen = {a}
            for j in range(i + 1, len(seq)):
                t1, b = seq[j]
                if t1 - t0 > 25 or (nd is not None and t1 > nd): break
                if b in seen: continue
                seen.add(b)
                rj = rj_in(t0 - 1.0, t1 + 0.3)
                obs[mp][(a, b)][rj].append(t1 - t0)
                # the way taken: the rooms passed between a and b (consecutive repeats collapsed)
                via = []
                for _, r_ in seq[i + 1:j]:
                    if not via or via[-1] != r_: via.append(r_)
                routes[mp][(a, b)][(tuple(via), rj)].append(t1 - t0)

def stats(v):
    v = sorted(v)
    return [round(v[max(0, int(len(v) * 0.10))], 1), round(v[len(v) // 2], 1), len(v), round(v[max(0, int(len(v) * 0.25))], 1)]
out, out_rj = {}, {}
for mp, pairs in obs.items():
    out[mp] = {}; out_rj[mp] = {}
    for (a, b), by in pairs.items():
        if len(by[False]) >= 8: out[mp].setdefault(a, {})[b] = stats(by[False])
        if len(by[True]) >= 5: out_rj[mp].setdefault(a, {})[b] = stats(by[True])
hdr = ('"""Room-to-room travel times per TB4 map (built %s from %s games: %s).\nROUTE_TIMES[map][from_room][to_room] = [10th-percentile seconds, median seconds, runs, 25th-percentile seconds]: time from\nentering one room to entering the other within one life WITHOUT a rocket jump (teleporters and lifts included, deaths\nexcluded, pairs with 8+ runs). ROUTE_TIMES_RJ = the same for runs where the player rocket-jumped (own rocket or grenade\nsplash during the run; pairs with 5+ runs). The 10th percentile is "done well"; the median is what people take.\nROOM_Z[map][room] = the room\'s floor height (median z of players labelled with it).\nBuilt by tools/mvd_features/research_2026_10/route_times_build.py from the mvd-api loc-trails, damage and buckets."""\n'
       % (time.strftime('%Y-%m-%d'), sum(games.values()), dict(games)))
# ROUTES: for each pair, the distinct ways taken (5+ runs each), top 5 by use, each with its own fast/typical and rj flag
rt = {}
for mp, pairs in routes.items():
    rt[mp] = {}
    for (a, b), ways in pairs.items():
        ws = []
        for (via, rj), v in ways.items():
            if len(v) < 5: continue
            v.sort(); ws.append(dict(via=list(via), fast=round(v[max(0, int(len(v) * 0.10))] if len(v) >= 15 else v[max(0, int(len(v) * 0.25))], 1), typical=round(v[len(v) // 2], 1), n=len(v), rj=int(rj)))
        if ws:
            ws.sort(key=lambda w: -w['n']); rt[mp].setdefault(a, {})[b] = ws[:5]
room_z = {}
for (mp, room), v in ROOM_Z.items(): room_z.setdefault(mp, {})[room] = round(v)
open(out_path, 'w').write(hdr + 'ROUTE_TIMES = ' + json.dumps(out, separators=(',', ':')) + '\n'
                          + 'ROUTE_TIMES_RJ = ' + json.dumps(out_rj, separators=(',', ':')) + '\n'
                          + 'ROOM_Z = ' + json.dumps(room_z, separators=(',', ':')) + '\n'
                          + '# ROUTES[map][from][to] = the ways actually taken between the two rooms (5+ runs each), most used first:\n'
                          + '# {via: rooms passed between them, fast, typical, n, rj: 1 when the run used a rocket jump}.\n'
                          + 'ROUTES = ' + json.dumps(rt, separators=(',', ':')) + '\n')
print('written', out_path, {mp: sum(len(x) for x in out[mp].values()) for mp in out}, 'rj pairs', {mp: sum(len(x) for x in out_rj[mp].values()) for mp in out_rj}, flush=True)
print('floor flips dropped (top):', dropped.most_common(12), flush=True)
print('climbs kept (top):', kept_climbs.most_common(8), flush=True)

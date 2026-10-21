"""Build route_times.py — fast room-to-room travel times per TB4 map — from the mvd-api's loc-trails.

    python3 route_times_build.py <out.py> <hub_game_id> [<hub_game_id> ...]

For every player's room sequence in every game: for each ordered pair of rooms entered within 25 s of
each other in one life (a respawn is not a path), the seconds from entering the first to entering the
second. Per map and pair: [10th-percentile s, median s, n] for pairs with 8+ runs. The 10th percentile is
"done well" (teleporters count; the map's real stairs, lifts and jumps are in it); the median is what
people actually take. Deaths come from /events (type death)."""
import json, sys, urllib.request, collections, time
B = 'https://deepfrag-mvd-api-751658372467.us-central1.run.app/v1/demos/gameId:'
def get(p):
    with urllib.request.urlopen(B + p, timeout=170) as r: return json.loads(r.read())
out_path, gids = sys.argv[1], [int(x) for x in sys.argv[2:]]
obs = collections.defaultdict(lambda: collections.defaultdict(list)); games = collections.Counter()
LONG = {'The Abandoned Base': 'dm3', 'Claustrophobopolis': 'dm2', 'Castle of the Damned': 'e1m2', 'schloss': 'schloss', 'dm3': 'dm3', 'dm2': 'dm2', 'e1m2': 'e1m2'}
for gid in gids:
    try:
        t = time.time(); di = get(f'{gid}/demoinfo'); mp = (di.get('map') or '').lower()      # demoinfo carries the short map name
        mp = LONG.get(mp, mp)
        if mp not in ('dm3', 'dm2', 'e1m2', 'schloss'): print(gid, 'skip', di.get('map'), flush=True); continue
        tr = get(f'{gid}/loc-trails'); ev = get(f'{gid}/events?types=death')
    except Exception as e:
        print(gid, 'ERR', e, flush=True); continue
    deaths = collections.defaultdict(list)
    for e in ev.get('events', []):
        if e.get('type') == 'death': deaths[e.get('player')].append(e['t'])
    games[mp] += 1
    for p in tr.get('players', []):
        seq = [(x['s'], x['loc']) for x in p.get('sequence', []) if x.get('loc')]
        dd = sorted(deaths.get(p['name'], []))
        for i, (t0, a) in enumerate(seq):
            nd = next((x for x in dd if x > t0), None); seen = {a}
            for j in range(i + 1, len(seq)):
                t1, b = seq[j]
                if t1 - t0 > 25 or (nd is not None and t1 > nd): break
                if b in seen: continue
                seen.add(b); obs[mp][(a, b)].append(t1 - t0)
    print(gid, mp, f'{time.time()-t:.0f}s', flush=True)
out = {}
for mp, pairs in obs.items():
    out[mp] = {}
    for (a, b), v in pairs.items():
        if len(v) < 8: continue
        v.sort(); out[mp].setdefault(a, {})[b] = [round(v[max(0, int(len(v) * 0.10))], 1), round(v[len(v) // 2], 1), len(v)]
hdr = ('"""Fast room-to-room travel times per TB4 map (built %s from %s games: %s).\nROUTE_TIMES[map][from_room][to_room] = [10th-percentile seconds, median seconds, runs]: time from entering one\nroom to entering the other within one life (teleporters included, deaths excluded, pairs with 8+ runs). The 10th\npercentile is "done well" (the map\'s real stairs, lifts and jumps are in it); the median is what people take.\nBuilt by tools/mvd_features/research_2026_10/route_times_build.py from the mvd-api loc-trails."""\n'
       % (time.strftime('%Y-%m-%d'), sum(games.values()), dict(games)))
open(out_path, 'w').write(hdr + 'ROUTE_TIMES = ' + json.dumps(out, separators=(',', ':')) + '\n')
print('written', out_path, {mp: sum(len(x) for x in out[mp].values()) for mp in out}, flush=True)

"""Pick ~56 TB4-map 4on4 games with >=2 TOP-roster players: every game with >=4 TOP players, then the most recent to fill 14 per map."""
import json, re, collections
S = '/private/tmp/claude-501/-Users-peteryeargin/a7f17fb4-de1b-4afb-8c33-8756bc0a6385/scratchpad'
TOP = {'bogojoker', 'zorak', 'sane', 'chris', 'blaze', 'yeti', 'blood_dog_d_p', 'war', 'dusty', 'coj'}
FIELD = {'viag', 'nico', 'gflip', 'omicron', 'namtsui', 'cronus', 'pharm', 'pred', 'foobhar', 'phylter', 'stedanko', 'ledge', 'schotty', 'evalcat'}
ALIAS = {'george': 'war', 'georges': 'war', 'whodat': 'war', 'igor': 'war', 'tardface': 'war', 'pikachu': 'war', 'fok': 'war', 'notgeorge': 'war',
         'chr1s': 'chris', 'chris2pl': 'chris', 'eatmyass': 'chris', 'pierre': 'dusty', 'venator': 'nico', 'vyper': 'nico', 'notyeti': 'yeti',
         'enas': 'sane', 'anton': 'sane', 'ant0n': 'sane', 'bposane': 'sane', 'blze': 'blaze', 'omicron-4on4': 'omicron'}
def canon(n):
    n = n.strip().lower()
    n = re.sub(r'^\(\d+\)', '', n).strip()
    if n.startswith('blood_dog') or n.startswith('d_p)blood_dog'): return 'blood_dog_d_p'
    return ALIAS.get(n, n)
CACHED = [247257, 247260, 247264, 247266, 247085, 247088, 247090, 247091]
if __name__ == '__main__':
    d = json.load(open(f'{S}/fours_since_may.json'))
    rows = []
    for g in d:
        if len(g['players']) != 8 or not g.get('demo_sha256'): continue
        names = [canon(p['name']) for p in g['players']]
        ntop = sum(n in TOP for n in names)
        if ntop >= 2: rows.append((g['id'], g['timestamp'], g['map'], ntop, names))
    pick = {r[0]: r for r in rows if r[3] >= 4 or r[0] in CACHED}
    per_map = collections.Counter(r[2] for r in pick.values())
    for r in sorted(rows, key=lambda r: -r[0]):
        if r[0] in pick: continue
        if per_map[r[2]] < 14:
            pick[r[0]] = r; per_map[r[2]] += 1
    out = sorted(pick.values())
    print(len(out), per_map)
    json.dump([{'id': r[0], 'ts': r[1], 'map': r[2], 'ntop': r[3], 'names': r[4]} for r in out], open(f'{S}/selected_games.json', 'w'), indent=0)
    for r in out: print(r[0], r[1][:10], r[2], r[3], ' '.join(r[4]))

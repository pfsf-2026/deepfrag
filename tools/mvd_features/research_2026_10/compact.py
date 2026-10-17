"""Stage 1: full_<gid>.json (analyzer full view) -> compact_<gid>.json with 1-s tables, full-resolution room entries and 100 ms spawn tracks."""
import json, os, sys, bisect, math
sys.path.insert(0, '/Users/peteryeargin/Projects/qw-stats/tools/mvd_features')
import quad_night as QN
from select_games import canon, TOP, FIELD
S = '/private/tmp/claude-501/-Users-peteryeargin/a7f17fb4-de1b-4afb-8c33-8756bc0a6385/scratchpad'

def compact(gid):
    d = json.load(open(f'{S}/full_{gid}.json'))
    end = d["streams"]["global"]["matchEnd"]
    mp = (d.get("demoInfo") or {}).get("map") or d["match"]["map"]
    locs = (d.get("timelineAnalysis") or {}).get("locTable") or []
    N = end // 1000 + 1
    P = {}
    for p in d["streams"]["players"]:
        if not p.get("pos") or not p["pos"].get("t") or not p.get("team"):
            continue
        pt = p["pos"]; T = pt["t"]
        sp = sorted(p.get("sp") or []); dd = sorted(p.get("d") or [])
        H, A, AT = QN.step(p.get("h"), 100), QN.step(p.get("a"), 0), QN.step(p.get("at"), "")
        iv = {k: [(x["s"], x["e"]) for x in (p.get(k) or [])] for k in ("rl", "lg", "q", "pe")}
        def idx(t):
            i = bisect.bisect_left(T, t)
            if i >= len(T): i = len(T) - 1
            if i > 0 and abs(T[i - 1] - t) < abs(T[i] - t): i -= 1
            return i
        def alive(t):
            ls = sp[bisect.bisect_right(sp, t) - 1] if bisect.bisect_right(sp, t) else 0
            ld = dd[bisect.bisect_right(dd, t) - 1] if bisect.bisect_right(dd, t) else -1
            return ls >= ld
        def has(k, t): return any(s <= t <= e for s, e in iv[k])
        rows = {k: [] for k in ("alive", "x", "y", "z", "li", "eff", "h", "rl", "lg", "q")}
        for s in range(N):
            t = s * 1000; i = idx(t)
            rows["alive"].append(1 if alive(t) else 0)
            rows["x"].append(round(pt["x"][i])); rows["y"].append(round(pt["y"][i])); rows["z"].append(round(pt["z"][i]))
            rows["li"].append(pt["li"][i] if pt.get("li") else 0)
            h = H(t); rows["h"].append(h); rows["eff"].append(QN.eff_hp(h, A(t), AT(t)))
            rows["rl"].append(1 if has("rl", t) else 0); rows["lg"].append(1 if has("lg", t) else 0); rows["q"].append(1 if has("q", t) else 0)
        # full-resolution room transitions (t, new li); flag ones that coincide with a spawn (<=600 ms after)
        entries = []
        li = pt.get("li") or []
        if li:
            prev = li[0]
            for i in range(1, len(li)):
                if li[i] != prev:
                    t = T[i]
                    j = bisect.bisect_right(sp, t) - 1
                    at_spawn = j >= 0 and t - sp[j] <= 600
                    entries.append([t, li[i], 1 if at_spawn else 0])
                    prev = li[i]
        # 100 ms spawn tracks for 6 s after each spawn
        tracks = []
        for s0 in sp:
            if s0 >= end: continue
            nd = dd[bisect.bisect_right(dd, s0)] if bisect.bisect_right(dd, s0) < len(dd) else end
            tr = []
            for k in range(0, 61):
                t = s0 + k * 100
                if t > nd or t > end: break
                i = idx(t)
                tr.append([k, round(pt["x"][i]), round(pt["y"][i]), round(pt["z"][i]), pt["li"][i] if li else 0])
            tracks.append([s0, nd, tr])
        P[p["name"]] = {"team": p["team"], "canon": canon(p["name"]), **rows, "sp": sp, "d": dd, "entries": entries, "tracks": tracks,
                        "rl_iv": iv["rl"], "lg_iv": iv["lg"], "q_iv": iv["q"]}
    frags = [f for f in d["frags"]["frags"] if f.get("victim") in P and f["time"] >= 0]
    dmg = [{"time": e["time"], "attacker": e["attacker"], "victim": e["victim"], "damage": e["damage"]} for e in d["damage"]["events"]
           if e.get("attacker") in P and e.get("victim") in P and e["time"] >= 0]
    items = []
    for it in d["items"]["items"]:
        items.append({"kind": it["kind"], "loc": it.get("loc", ""), "x": it["x"], "y": it["y"], "z": it["z"],
                      "phases": [{"from": ph.get("availableFrom"), "takenAt": ph.get("takenAt"), "takenBy": ph.get("takenBy")} for ph in (it.get("phases") or [])]})
    teams = {}
    for n, p in P.items(): teams.setdefault(p["team"], []).append(n)
    out = {"gid": gid, "map": mp, "end": end, "locs": locs, "teams": teams, "P": P, "frags": frags, "dmg": dmg, "items": items}
    json.dump(out, open(f'{S}/compact_{gid}.json', 'w'))
    return out

if __name__ == '__main__':
    gids = [int(x) for x in sys.argv[1:]] or [g['id'] for g in json.load(open(f'{S}/selected_games.json'))]
    for g in gids:
        if os.path.exists(f'{S}/compact_{g}.json'): continue
        if not os.path.exists(f'{S}/full_{g}.json'): print('missing full', g); continue
        o = compact(g); print(g, o['map'], {t: len(v) for t, v in o['teams'].items()}, 'players', [(n, p['canon']) for n, p in o['P'].items()], flush=True)

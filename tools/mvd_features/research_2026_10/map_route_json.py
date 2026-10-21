"""Write the map pages' route data from route_times.py:

    python3 map_route_json.py [route_times.py path]

- nuxt/app/composables/travelTimes.json   {map: {rooms: [display…], cells: [[{fast, typical, n, rj?} | {est} | null]]}}
  rooms are the key rooms (items + spawns) in display words; a cell is the run WITHOUT a rocket jump (fast =
  10th percentile when 15+ runs, else 25th; typical = median), with `rj` = the same for runs that used one when
  there were 5+; a pair nobody ran directly gets {est} from the shortest chain of typical legs.
- nuxt/app/composables/mapRoutes.json     {map: [{to, to_name, from: [{from, from_name, ways: [{via, fast, typical, n, rj}]}]}]}
  the ways actually run to each item room from each key room (destinations and names kept from the previous file).
- docs/map_travel_times.md                the same travel tables as markdown.
"""
import json, sys, os, heapq, importlib.util, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RT_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "route_times.py")
spec = importlib.util.spec_from_file_location("route_times", RT_PATH); rt_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(rt_mod)
ROUTE_TIMES, ROUTE_TIMES_RJ, ROUTES = rt_mod.ROUTE_TIMES, getattr(rt_mod, "ROUTE_TIMES_RJ", {}), rt_mod.ROUTES

# display word → the parser's room label (recovered 2026-10-21 by matching the previous tables cell for cell)
DISPLAY = {
    "dm3": [("quad", "Quad"), ("red", "RA"), ("YA", "YA.box"), ("RL", "RL"), ("LG", "water.LG"), ("SNG mega", "SNG.MH"), ("hill mega", "hill"),
            ("Pent room", "Pent"), ("tele", "SNG.tele"), ("RA tunnel", "RA.tunnel"), ("lifts", "lifts")],
    "dm2": [("quad", "Quad"), ("back RA/mega", "RA.MH"), ("secret RA", "secret"), ("big YA", "big"), ("tele YA", "tele.YA"), ("high RL", "high.RL"),
            ("low RL", "low.RL"), ("GL mega", "GL"), ("tele", "tele"), ("NG", "NG"), ("water", "water")],
    "e1m2": [("quad", "Quad.box"), ("YA", "YA"), ("RL", "RL"), ("mega", "MH"), ("GA", "GA"), ("GL", "GL"), ("door", "door"), ("crossing", "cross"),
             ("start", "start"), ("spikes", "spikes")],
    "schloss": [("quad", "Quad"), ("pent", "yard.Pent"), ("red", "RA"), ("tower YA", "tower"), ("Cat YA", "cathedral.YA"), ("tower RL", "tower.RL"),
                ("Cat RL", "cathedral"), ("yard mega", "yard"), ("cemetery mega", "cemetary"), ("cemetery tele", "cemetary.tele"), ("Cat SSG", "cathedral.SSG")],
}

def fast_of(v):
    return v[0] if v[2] >= 15 else (v[3] if len(v) > 3 else v[1])

def est(RT, a, b):
    """Shortest chain of typical (median) legs, like game_report.travel()."""
    if a == b: return 0.0
    dist = {a: 0.0}; pq = [(0.0, a)]
    while pq:
        d0, u = heapq.heappop(pq)
        if u == b: return d0
        if d0 > dist.get(u, 1e9): continue
        for v, leg in (RT.get(u) or {}).items():
            nd = d0 + leg[1]
            if nd < dist.get(v, 1e9): dist[v] = nd; heapq.heappush(pq, (nd, v))
    return None

tt = {}; md = []
md.append("# Travel times between key rooms on the TB4 maps\n")
md.append("*Seconds from entering one room to entering the other, measured from recent NA fours through the demo parser's room trails, "
          "for runs **without a rocket jump**. Each cell is **fast / typical**: fast = the 10th percentile of runs that actually went from one room to the "
          "other in one life (done well; stairs, lifts and teleporters included), typical = the median. Where players also rocket-jump the pair, "
          "**RJ n** follows: the fast time with a rocket jump (the player's own rocket splash during the run). A cell in *italics* is an estimate for a pair "
          "nobody ran directly (shortest chain of typical legs). Built by `tools/mvd_features/research_2026_10/route_times_build.py` and written by "
          "`map_route_json.py` (%s); the Game Report uses the same table for its clocks and perfect-timing lines, RJ times only when the player has rockets and a stack.*\n" % time.strftime("%Y-%m-%d"))
for mp, rooms in DISPLAY.items():
    RT, RJ = ROUTE_TIMES.get(mp) or {}, ROUTE_TIMES_RJ.get(mp) or {}
    names = [d for d, _ in rooms]; raws = [r for _, r in rooms]
    cells = []
    for a in raws:
        row = []
        for b in raws:
            if a == b: row.append(None); continue
            v = (RT.get(a) or {}).get(b)
            if v:
                c = dict(fast=round(fast_of(v)), typical=round(v[1]), n=v[2])
                w = (RJ.get(a) or {}).get(b)
                if w: c["rj"] = dict(fast=round(fast_of(w)), typical=round(w[1]), n=w[2])
                row.append(c)
            else:
                e = est(RT, a, b); row.append(dict(est=round(e, 1)) if e is not None else None)
        cells.append(row)
    tt[mp] = dict(rooms=names, cells=cells)
    md.append(f"\n## {mp}\n")
    md.append("| from \\ to | " + " | ".join(names) + " |")
    md.append("|---|" + "---|" * len(names))
    for i, n in enumerate(names):
        out = []
        for c in cells[i]:
            if c is None: out.append("·")
            elif "fast" in c: out.append(f"{c['fast']} / {c['typical']}" + (f" (RJ {c['rj']['fast']})" if c.get("rj") else ""))
            else: out.append(f"*~{round(c['est'])}*")
        md.append(f"| **{n}** | " + " | ".join(out) + " |")

old = json.load(open(os.path.join(ROOT, "nuxt/app/composables/mapRoutes.json")))
mr = {}
for mp, dests in old.items():
    R = ROUTES.get(mp) or {}
    mr[mp] = []
    for d in dests:
        froms = []
        for f in d["from"]:
            ways = (R.get(f["from"]) or {}).get(d["to"]) or []
            ways = sorted(ways, key=lambda w: (w.get("rj", False), -w["n"]))[:5]       # walks first, then the rocket-jump ways
            if ways: froms.append(dict(from_=f["from"], from_name=f["from_name"], ways=[dict(via=w["via"], fast=w["fast"], typical=w["typical"], n=w["n"], rj=bool(w.get("rj"))) for w in ways]))
        froms = [dict((k.rstrip("_"), v) for k, v in x.items()) for x in froms]
        if froms: mr[mp].append(dict(to=d["to"], to_name=d["to_name"], **{"from": froms}))

json.dump(tt, open(os.path.join(ROOT, "nuxt/app/composables/travelTimes.json"), "w"), separators=(",", ":"))
json.dump(mr, open(os.path.join(ROOT, "nuxt/app/composables/mapRoutes.json"), "w"), separators=(",", ":"))
open(os.path.join(ROOT, "docs/map_travel_times.md"), "w").write("\n".join(md) + "\n")
print("written travelTimes.json, mapRoutes.json, docs/map_travel_times.md from", RT_PATH)
for mp in DISPLAY:
    n_rj = sum(1 for row in tt[mp]["cells"] for c in row if c and c.get("rj"))
    print(mp, "cells with an RJ time:", n_rj, "| routes with rj ways:", sum(1 for d in mr.get(mp, []) for f in d["from"] for w in f["ways"] if w["rj"]))

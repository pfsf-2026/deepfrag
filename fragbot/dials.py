"""
FragBot dial battery — the human-likeness metrics, computed from qw-analyze output.

This is the measurement backbone for FragBot tuning + tracking. It reuses the
exact dial definitions validated against the real frogbot baseline (see
qw-stats/docs/bot_dials_and_calibration.md). Input is qw-analyze JSON:
  - buckets:  qw-analyze -view buckets -bucket 13ms -fields pos,view,vel,hgt
  - full:     qw-analyze -view full

Works in any mode. 1on1 gets the full battery; 4on4 gets movement + combat +
accuracy now (reaction/airshots need nearest-enemy logic — flagged TODO).

13ms is the ONLY valid window (native frame cadence). Never aggregate.
"""
import json, math, bisect

WIN = 13  # ms per native frame

# --- human-likeness bands: frogbot floor -> human band. direction "up" means
#     higher = more human; "down" means lower = more human. Used to score 0-99.
#     Sources: docs/bot_dials_and_calibration.md (measured baseline + human bands).
BANDS = {
    "coupling_52ms":   {"frogbot": 0.04, "human_lo": 0.29, "human_hi": 0.47, "dir": "up",   "weight": 3, "fmt": "{:.3f}"},
    "airborne_pct":    {"frogbot": 24.0, "human_lo": 28.0, "human_hi": 34.0, "dir": "up",   "weight": 1, "fmt": "{:.1f}%"},
    "rocketjumps_min": {"frogbot": 0.14, "human_lo": 1.0,  "human_hi": 2.0,  "dir": "up",   "weight": 2, "fmt": "{:.2f}"},
    "strafe_aim_fast": {"frogbot": 13.0, "human_lo": 25.0, "human_hi": 45.0, "dir": "up",   "weight": 2, "fmt": "{:.1f}%"},
    # accuracy: bot is SUPERHUMAN — "human-like" means coming DOWN to the human band
    "lg_pct":          {"frogbot": 35.0, "human_lo": 20.0, "human_hi": 30.0, "dir": "down", "weight": 1, "fmt": "{:.1f}%"},
    "sg_pct":          {"frogbot": 38.0, "human_lo": 10.0, "human_hi": 18.0, "dir": "down", "weight": 1, "fmt": "{:.1f}%"},
}


def _angdiff(a, b):
    return (a - b + 180) % 360 - 180


def _pearson(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _median(v):
    return sorted(v)[len(v) // 2] if v else None


def load(buckets_path, full_path):
    """Load one demo's qw-analyze buckets + full JSON."""
    return {
        "buckets": json.load(open(buckets_path))["buckets"],
        "full": json.load(open(full_path)),
    }


def _series(buckets):
    """Build per-player aligned arrays (None where the player is absent that frame)."""
    names = set()
    for b in buckets:
        names.update(b.get("p", {}).keys())
    S = {nm: {"x": [], "y": [], "vx": [], "vy": [], "vya": [], "hgt": []} for nm in names}
    for b in buckets:
        p = b.get("p", {})
        for nm in names:
            e = p.get(nm)
            if e and e.get("pos") and e.get("vel") and e.get("view"):
                S[nm]["x"].append(e["pos"][0]); S[nm]["y"].append(e["pos"][1])
                S[nm]["vx"].append(e["vel"][0]); S[nm]["vy"].append(e["vel"][1])
                S[nm]["vya"].append(e["view"][1]); S[nm]["hgt"].append(e.get("hgt"))
            else:
                for k in S[nm]:
                    S[nm][k].append(None)
    return S


def compute_card(demo, player, mode="1on1"):
    """Full dial card for `player` in one demo. `mode` in {1on1,2on2,4on4}."""
    buckets, full = demo["buckets"], demo["full"]
    S = _series(buckets)
    if player not in S:
        return {"error": f"player {player!r} not in demo (have {sorted(S)})"}
    s = S[player]
    VX, VY, VYA, HG, MX, MY = s["vx"], s["vy"], s["vya"], s["hgt"], s["x"], s["y"]
    card = {"player": player, "mode": mode}

    # SPEED
    speeds = [math.hypot(VX[i], VY[i]) for i in range(len(VX))
              if VX[i] is not None and VY[i] is not None and math.hypot(VX[i], VY[i]) < 2500]
    card["speed_median"] = round(_median(speeds)) if speeds else None
    card["_speeds"] = speeds

    # COUPLING (air-strafe view<->heading correlation), K=1 (13ms) and K=4 (~52ms)
    for K, key in ((1, "coupling_13ms"), (4, "coupling_52ms")):
        hh, vv = [], []
        for i in range(K, len(VX)):
            if None in (VX[i], VY[i], VX[i - K], VY[i - K], VYA[i], VYA[i - K]):
                continue
            if math.hypot(VX[i], VY[i]) <= 320:
                continue
            hh.append(_angdiff(math.degrees(math.atan2(VY[i], VX[i])),
                               math.degrees(math.atan2(VY[i - K], VX[i - K]))))
            vv.append(_angdiff(VYA[i] * 360 / 65536, VYA[i - K] * 360 / 65536))
        r = _pearson(hh, vv)
        card[key] = round(r, 3) if r is not None else None
        card["_" + key] = (hh, vv)  # transient raw pairs for correct run-level pooling

    # AIRBORNE %
    alive = sum(1 for h in HG if h is not None)
    air = sum(1 for h in HG if h is not None and h > 20)
    card["airborne_pct"] = round(100 * air / alive, 1) if alive else None
    card["_air"] = (air, alive)

    # --- combat / accuracy from KTX-native stats + damage events ---
    di = {p["name"]: p for p in full.get("demoInfo", {}).get("players", [])}
    d = di.get(player, {})
    card["ping"] = d.get("ping")
    card["skill"] = (d.get("bot") or {}).get("skill")
    card["is_bot"] = bool(d.get("bot"))
    card["_acc"] = {}
    for w, key in (("sg", "sg_pct"), ("lg", "lg_pct"), ("rl", "rl_pct")):
        acc = ((d.get("weapons") or {}).get(w) or {}).get("acc") or {}
        a, h = acc.get("attacks", 0), acc.get("hits", 0)
        card[key] = round(100 * h / a, 1) if a else None
        card["_acc"][key] = (a, h)
    dd = d.get("dmg") or {}
    given, taken = dd.get("given", 0) or 0, dd.get("taken", 0) or 0
    card["dmg_given"], card["dmg_taken"] = given, taken
    card["dmg_eff"] = round(given / taken, 2) if taken else None
    st = d.get("stats") or {}
    card["frags"], card["deaths"] = st.get("frags"), st.get("deaths")

    # event-driven dials
    evs = full.get("damage", {}).get("events") or []
    HGb = s["hgt"]
    secs = sum(1 for h in HGb if h is not None) * WIN / 1000.0
    card["minutes"] = round(secs / 60.0, 2)

    # STRAFE-AIM: share of dealt damage while moving >450 qu/s
    sa_total = sa_fast = 0
    for ev in evs:
        if ev.get("attacker") != player or ev.get("victim") == player:
            continue
        dmg = ev.get("damage", 0) or 0
        if dmg <= 0:
            continue
        j = int(round((ev.get("time", 0) or 0) / WIN))
        if 0 <= j < len(VX) and VX[j] is not None:
            sa_total += dmg
            if math.hypot(VX[j], VY[j]) > 450:
                sa_fast += dmg
    card["strafe_aim_fast"] = round(100 * sa_fast / sa_total, 1) if sa_total else None
    card["_sa"] = (sa_fast, sa_total)

    # ROCKET-JUMP usage: self-RL hit + real liftoff
    rj = 0
    for ev in evs:
        if not (ev.get("weapon") == "rl" and ev.get("attacker") == player and ev.get("victim") == player):
            continue
        j = int(round((ev.get("time", 0) or 0) / WIN))
        w = [h for h in HGb[j:j + 15] if h is not None and -100 < h < 5000]
        if w and max(w) > 60 and sum(1 for h in w if h > 20) >= 6:
            rj += 1
    card["rocketjumps"] = rj
    card["rocketjumps_min"] = round(rj / (secs / 60.0), 2) if secs else None
    card["_rj"] = (rj, secs)

    # REACTION + AIRSHOTS — clean only in 1on1 (single opponent). 4on4 = TODO.
    others = [n for n in S if n != player]
    if mode == "1on1" and len(others) == 1:
        en = others[0]
        es = S[en]
        EX, EY, EH = es["x"], es["y"], es["hgt"]
        # reaction acq (FOV-100 floor => 50deg half-cone), engagement-confirmed
        hits = sorted(ev["time"] for ev in evs
                      if ev.get("attacker") == player and ev.get("victim") == en and (ev.get("damage", 0) or 0) > 0)
        acq_raw = []
        acqv, prev_in = None, False
        n = min(len(MX), len(EX), len(VYA))
        for i in range(n):
            if None in (MX[i], EX[i], MY[i], EY[i], VYA[i]):
                prev_in, acqv = False, None
                continue
            dxe, dye = EX[i] - MX[i], EY[i] - MY[i]
            off = abs(_angdiff(math.degrees(math.atan2(dye, dxe)), VYA[i] * 360 / 65536))
            in_eng = math.hypot(dxe, dye) < 1500 and off < 50.0
            if in_eng and not prev_in and off > 5:
                acqv = i
            if acqv is not None:
                if off < 5:
                    tc = i * WIN
                    k = bisect.bisect_left(hits, tc)
                    if k < len(hits) and hits[k] - tc <= 1000:
                        acq_raw.append((i - acqv) * WIN)
                    acqv = None
                elif (i - acqv) * WIN > 1000:
                    acqv = None
            prev_in = in_eng
        card["reaction_acq_ms"] = _median(acq_raw)
        card["reaction_samples"] = len(acq_raw)
        card["_react"] = acq_raw
        # airshots: RL hits while victim airborne
        air_hit = air_tot = 0
        for ev in evs:
            if ev.get("attacker") != player or ev.get("victim") != en or ev.get("weapon") != "rl":
                continue
            air_tot += 1
            j = int(round((ev.get("time", 0) or 0) / WIN))
            if 0 <= j < len(EH) and EH[j] is not None and 45 < EH[j] < 5000:
                air_hit += 1
        card["airshot_rl"] = f"{air_hit}/{air_tot}"
    else:
        card["reaction_acq_ms"] = None
        card["airshot_rl"] = None  # TODO: nearest-enemy logic for 4on4

    return card


def _score_dial(name, value):
    """Map a dial value to 0-99 human-likeness (99 = squarely in human band)."""
    if value is None or name not in BANDS:
        return None
    b = BANDS[name]
    lo, hi, fog = b["human_lo"], b["human_hi"], b["frogbot"]
    if b["dir"] == "up":
        if value >= lo:
            return 99 if value <= hi else 99
        # between frogbot floor and human_lo -> 0..99
        return max(0, round(99 * (value - fog) / (lo - fog))) if lo > fog else 0
    else:  # "down": human band is BELOW frogbot; closer to band = more human
        if value <= hi:
            return 99
        return max(0, round(99 * (fog - value) / (fog - hi))) if fog > hi else 0


def humanlikeness(card):
    """Per-dial 0-99 + weighted overall. Higher = more human, lower = more frogbot."""
    per = {}
    num = den = 0
    for name, b in BANDS.items():
        sc = _score_dial(name, card.get(name))
        if sc is None:
            continue
        per[name] = sc
        num += sc * b["weight"]
        den += b["weight"]
    overall = round(num / den) if den else None
    return {"per_dial": per, "overall": overall}

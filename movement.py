"""Movement report: per-hop air-strafe analysis from 13 ms demo tracks.

Input is one player's column track from the mvd-api
(`/v1/demos/gameId:{id}/buckets?windowMs=13&layout=column&fields=pos,view,vel,hgt`):
`alive`, `x/y/z`, `vx/vy/vz` (central difference of positions), `hgt` (height above the
floor from the BSP, ~0 when standing) and `vya` (view yaw, angle16).

QuakeWorld air acceleration adds speed along the direction the movement keys point, capped
at 30 ups of speed measured ALONG that direction. One air frame therefore adds at most
30^2 = 900 to speed^2, and only when that direction is exactly sideways to the velocity.
So for a hop of n frames taking off at v0:

    best possible landing speed = sqrt(v0^2 + 900 n)
    efficiency                  = (v_land^2 - v0^2) / (900 n)

Holding that perfectly needs a ~300 deg/s turn at 400 ups, so real players sit far below
100%; what they gain is set by how fast they turn while keeping the view in the narrow
window behind the velocity. Demos carry no key state, so the keys are inferred from where
the view sits relative to the heading: ~0 deg for strafe-only, ~45 deg for forward+strafe.

The same maths drives the in-game strafe coach (tools/ktx_strafecoach).
"""
from __future__ import annotations

import math
from statistics import median

FRAME_MS = 13
GROUND_HGT = 3.0          # at or below this height above the floor = standing on it
JUMP_VZ = 150.0           # an air segment that starts with this much upward speed is a jump
MIN_AIR, MAX_AIR = 20, 130            # frames; a flat jump is ~52
MIN_TAKEOFF = 250.0       # ups; slower than this is not a movement hop
WIDE = 4                  # speed + heading come from the path over +-4 frames (104 ms)
EDGE = 3                  # hop speeds are read this many frames inside takeoff / landing
BOOST_STEP = 60.0         # ups gained inside 6 frames = rocket / knockback / teleport, not strafing
BUMP_STEP = 45.0          # ups lost inside 6 frames = hit a wall, a ledge or a player
ZONE_MIN_EFF = 0.10       # a frame counts as "in sync" if it reaches this share of the best frame
AIR_WISH = 30.0
STEP_V2 = AIR_WISH * AIR_WISH        # best speed^2 one 77 fps air frame can add
CHAIN_GAP = 6             # ground frames (78 ms) or fewer between hops = still one bunny chain


def _angdiff(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def _pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * p))]


def _frame_eff(speed: float, lag_deg: float) -> float:
    """Share of the best possible frame, for a wish direction `lag_deg` short of sideways
    (negative = past sideways). Mirrors PM_AirAccelerate at 77 fps (accel cap 41.6)."""
    d = speed * math.sin(math.radians(lag_deg))
    a = max(0.0, min(41.6, AIR_WISH - d))
    return (2 * a * d + a * a) / STEP_V2


def analyze_track(me: dict) -> dict | None:
    """Hops + summary for one player in one game. None if the track is unusable."""
    alive = me.get("alive") or []
    X, Y, Z = me.get("x") or [], me.get("y") or [], me.get("z") or []
    H, VYA = me.get("hgt") or [], me.get("vya") or []
    N = min(len(alive), len(X), len(Y), len(Z), len(H), len(VYA))
    if N < 2000:
        return None

    # A player's physics runs once per client packet. About 4% of 13 ms buckets carry no new
    # packet for him: the position simply repeats and is NOT made up on the next frame. Those
    # buckets are not physics frames, and left in they make speed dip by half for one sample.
    # So work on the frames where he actually moved (plus the first frame of standing still).
    raw_ok = [bool(alive[i]) and None not in (X[i], Y[i], Z[i], H[i]) for i in range(N)]
    keep = []
    for i in range(N):
        if not raw_ok[i]:
            keep.append(i)              # keeps dead / missing stretches as breaks
            continue
        if not keep or not raw_ok[keep[-1]]:
            keep.append(i)
            continue
        j = keep[-1]
        if abs(X[i] - X[j]) + abs(Y[i] - Y[j]) + abs(Z[i] - Z[j]) > 0.01:
            keep.append(i)
    n = len(keep)
    ok = [raw_ok[i] for i in keep]
    px, py, pz = [X[i] for i in keep], [Y[i] for i in keep], [Z[i] for i in keep]
    hgt, vya = [H[i] for i in keep], [VYA[i] for i in keep]
    dt = FRAME_MS / 1000.0

    # Per-frame speed is too noisy to trust: positions are in 1/8 units and a client's frames
    # are 12, 13 or 14 ms long, so one step can be 15% off. Speed and heading are therefore
    # read from the path over +-WIDE frames. Air strafing changes speed by ~1 ups a frame and
    # heading by ~1 degree, so nothing real is lost.
    step = [0.0] * n                       # step[k] = distance from frame k-1 to k
    for k in range(1, n):
        if ok[k] and ok[k - 1]:
            d = math.hypot(px[k] - px[k - 1], py[k] - py[k - 1])
            step[k] = d if d < 60 else -1.0  # -1 = teleport / respawn: breaks any window over it
    spd, head, vz = [0.0] * n, [None] * n, [0.0] * n
    for k in range(WIDE, n - WIDE):
        if not ok[k]:
            continue
        lo, hi = k - WIDE, k + WIDE
        seg = step[lo + 1:hi + 1]
        if any(x < 0 for x in seg) or not all(ok[lo:hi + 1]):
            # near a spawn / death / teleport: fall back to the two-frame difference
            if ok[k - 1] and ok[k + 1] and step[k] >= 0 and step[k + 1] >= 0:
                spd[k] = math.hypot(px[k + 1] - px[k - 1], py[k + 1] - py[k - 1]) / (2 * dt)
            continue
        spd[k] = sum(seg) / (2 * WIDE * dt)
        dx, dy = px[hi] - px[lo], py[hi] - py[lo]
        if abs(dx) + abs(dy) > 1.0:
            head[k] = math.degrees(math.atan2(dy, dx))
    for k in range(1, n - 1):
        if ok[k - 1] and ok[k] and ok[k + 1] and step[k] >= 0 and step[k + 1] >= 0:
            vz[k] = (pz[k + 1] - pz[k - 1]) / (2 * dt)
    ground = [ok[k] and hgt[k] <= GROUND_HGT for k in range(n)]

    hops = []
    i = 1
    while i < n:
        if not (ok[i] and not ground[i] and ground[i - 1]):
            i += 1
            continue
        a = i                                  # first air frame; a-1 was on the ground
        j = a
        while j < n and ok[j] and not ground[j]:
            j += 1
        landed = j < n and ok[j] and ground[j]
        b = j                                  # first frame back on the ground (or end of segment)
        i = max(j, a + 1)
        length = b - a
        if not landed or not (MIN_AIR <= length <= MAX_AIR):
            continue
        if max(vz[a:a + 3]) < JUMP_VZ:         # walked off a ledge / fell, not a jump
            continue
        if length < 2 * EDGE + 8:
            continue
        ia, ib = a + EDGE, b - 1 - EDGE        # read speeds a little inside the hop
        v0, v1 = spd[ia], spd[ib]
        if v0 < MIN_TAKEOFF:
            continue
        span = ib - ia                         # physics frames between the two readings

        # Air strafing changes speed slowly. Anything abrupt is something else: a gain is a
        # rocket / knockback / teleport, a loss is a wall, ledge or player.
        steps6 = [spd[k + 6] - spd[k] for k in range(a, b - 6)]
        boosted = (max(steps6, default=0) > BOOST_STEP) or max(spd[a:b]) > 1400 or any(step[k] < 0 for k in range(a, b))
        bumped = (not boosted) and (min(steps6, default=0) < -BUMP_STEP)

        # heading + view through the hop
        turn = 0.0
        offs = []
        for k in range(ia + 1, ib + 1):
            if head[k] is None or head[k - 1] is None or spd[k] < 150:
                continue
            turn += _angdiff(head[k], head[k - 1])
            view = (vya[k] or 0) * 360.0 / 65536.0
            offs.append((_angdiff(view, head[k]), spd[k]))
        sign = 1.0 if turn >= 0 else -1.0        # +1 = turning left (yaw grows)
        dur = span * dt
        per_frame = abs(turn) / span if span else 0.0

        # Where the view sits relative to the heading says which keys are held: ~0 for
        # strafe-only, ~45 on the turn side for forward+strafe. "lag" is how far the wish
        # direction trails sideways-to-velocity (positive = behind the turn, negative = past it).
        # The move into a frame used that frame's view on the velocity it ENTERED with, half a
        # frame of turn behind the centred heading, hence the per_frame / 2 correction.
        style, lag_med, sync = None, None, None
        if len(offs) >= 10 and abs(turn) >= 3:
            lead = median(o * sign for o, _ in offs)
            style = "strafe" if lead < 22.5 else ("diagonal" if lead < 67.5 else "other")
            base = 0.0 if style == "strafe" else 45.0
            if style != "other":
                lags = [(base - o * sign - per_frame / 2, sp) for o, sp in offs]
                lag_med = median(l for l, _ in lags)
                sync = sum(1 for l, sp in lags if _frame_eff(sp, l) >= ZONE_MIN_EFF) / len(lags)

        hops.append({
            "f0": a, "f1": b, "frames": length, "v0": v0, "v1": v1,
            # gain is measured between the two inside readings and scaled to the whole hop
            "gain": (v1 - v0) * length / span,
            "eff": max(-1.0, min(1.5, (v1 * v1 - v0 * v0) / (STEP_V2 * span))),
            "turn_dps": abs(turn) / dur if dur else 0.0, "boosted": boosted, "bumped": bumped,
            "style": style, "lag": lag_med, "sync": sync,
        })

    # chains + what the ground contact between two hops costs
    clean = [h for h in hops if not h["boosted"] and not h["bumped"]]   # pure air-strafe hops
    unboosted = [h for h in hops if not h["boosted"]]
    chains, cur = [], []
    ground_frames, ground_loss = [], []
    for k, h in enumerate(hops):
        if cur and h["f0"] - cur[-1]["f1"] <= CHAIN_GAP:
            prev = cur[-1]
            ground_frames.append(h["f0"] - prev["f1"])
            if not prev["boosted"] and not h["boosted"]:
                ground_loss.append(prev["v1"] - h["v0"])          # + = speed lost touching down
            cur.append(h)
        else:
            if cur:
                chains.append(cur)
            cur = [h]
    if cur:
        chains.append(cur)
    chain_lens = [len(c) for c in chains]

    # Speed over time uses every alive bucket: a dropped bucket inside movement takes the
    # speed of the frame before it, a real standstill counts as 0.
    alive_spd, kp, run = [], 0, 0
    kept = set(keep)
    pos_of = {i: k for k, i in enumerate(keep)}
    last = 0.0
    for i in range(N):
        if not raw_ok[i]:
            run = 0
            continue
        if i in kept:
            last = spd[pos_of[i]]
            run = 0
            alive_spd.append(last if last < 2000 else 0.0)
        else:
            run += 1
            alive_spd.append(last if run <= 2 and last < 2000 else 0.0)
    if not alive_spd:
        return None
    minutes = len(alive_spd) * FRAME_MS / 60000.0
    r1 = lambda v: None if v is None else round(v, 1)
    styled = [h for h in clean if h["style"] in ("strafe", "diagonal")]
    summary = {
        "minutes": round(minutes, 2),
        "hops": len(unboosted),
        "hops_per_min": r1(len(unboosted) / minutes) if minutes else None,
        "clean_hops": len(clean),
        "bumped_pct": r1(100 * (len(unboosted) - len(clean)) / len(unboosted)) if unboosted else None,
        "gain_med": r1(median(h["gain"] for h in clean)) if clean else None,
        "gain_p75": r1(_pct([h["gain"] for h in clean], 0.75)),
        "eff_mean": r1(100 * sum(h["eff"] for h in clean) / len(clean)) if clean else None,
        "gaining_pct": r1(100 * sum(1 for h in clean if h["gain"] > 2) / len(clean)) if clean else None,
        "turn_med": r1(median(h["turn_dps"] for h in clean)) if clean else None,
        "lag_med": r1(median(h["lag"] for h in styled if h["lag"] is not None)) if styled else None,
        "sync_pct": r1(100 * sum(h["sync"] for h in styled if h["sync"] is not None) / len(styled)) if styled else None,
        "strafe_only_pct": r1(100 * sum(1 for h in styled if h["style"] == "strafe") / len(styled)) if styled else None,
        "ground_frames_med": median(ground_frames) if ground_frames else None,
        "ground_loss_med": r1(median(ground_loss)) if ground_loss else None,
        "chain_med": median(chain_lens) if chain_lens else None,
        "chain_p90": _pct(chain_lens, 0.9),
        "chain_max": max(chain_lens) if chain_lens else None,
        "speed_p50": r1(_pct(alive_spd, 0.5)), "speed_p90": r1(_pct(alive_spd, 0.9)),
        "speed_p99": r1(_pct(alive_spd, 0.99)),
        "over_320_pct": r1(100 * sum(1 for s in alive_spd if s > 320) / len(alive_spd)),
        "over_400_pct": r1(100 * sum(1 for s in alive_spd if s > 400) / len(alive_spd)),
        "boosted_hops": len(hops) - len(unboosted),
    }
    return {"summary": summary, "hops": hops, "chains": chain_lens}

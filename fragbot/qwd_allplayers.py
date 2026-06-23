#!/usr/bin/env python3
"""Extract EVERY player's trajectory from a client .qwd (not just the recorder).

Reuses qwd_rj's byte-exact svc parser but monkeypatches svc_playerinfo to record
all player slots, so we can see what the BOTS did (spawn height, did they float,
did they move, are they stacked). Reports per-slot: samples, first/last time,
spawn Z, Z range, XY travel, and a mid-air-spawn flag.
"""
import sys, math
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qwd_rj as Q

players = defaultdict(list)   # num -> [(t, x, y, z, have_vel, vz)]

def parse_playerinfo_all(r, st):
    num = r.read_byte()
    flags = r.read_ushort()
    if st.fte1 & Q.FTE_HAS_EXTRA_PF_MASK:
        if flags & Q.PF_EXTRA_PFS:
            flags |= r.read_byte() << 16
    else:
        flags = (flags & 0x3FFF) | ((flags & 0xC000) << 8)
    ox = r.read_player_coord(); oy = r.read_player_coord(); oz = r.read_player_coord()
    r.read_byte()  # frame
    if flags & Q.PF_MSEC:
        r.read_byte()
    vx = vy = vz = 0.0; have_vel = False
    if flags & Q.PF_COMMAND:
        Q.parse_delta_usercmd(r, st)
    for i in range(3):
        if flags & (Q.PF_VELOCITY1 << i):
            v = r.read_short()
            if i == 2: vz = float(v)
            elif i == 0: vx = float(v)
            else: vy = float(v)
            have_vel = True
    if flags & Q.PF_MODEL: r.read_byte()
    if flags & Q.PF_SKINNUM: r.read_byte()
    if flags & Q.PF_EFFECTS: r.read_byte()
    if flags & Q.PF_WEAPONFRAME:
        r.read_byte()
        if st.weapon_prediction:
            wp = r.read_byte()
            if wp:
                r.read_byte(); r.read_short(); r.read_float(); r.read_float()
                r.read_float(); r.read_byte(); r.read_byte(); r.read_byte()
                r.read_byte(); r.read_byte(); r.read_byte(); r.read_byte()
    if (flags & Q.PF_TRANS_Z) and (st.fte1 & Q.PEXT_TRANS):
        r.read_byte()
    if r.bad:
        return
    players[num].append((st.demotime, ox, oy, oz, have_vel, vz, bool(flags & Q.PF_DEAD) if hasattr(Q, "PF_DEAD") else False))

Q.parse_playerinfo = parse_playerinfo_all

data = Path(sys.argv[1]).read_bytes()
st = Q.parse_qwd(data)

print(f"# {sys.argv[1]}")
print(f"recorder self_player={st.self_player}  total player slots seen: {len(players)}\n")
for num in sorted(players):
    s = players[num]
    ts = [p[0] for p in s]; zs = [p[3] for p in s]
    xs = [p[1] for p in s]; ys = [p[2] for p in s]
    spawn_z = s[0][3]
    # mid-air at first sight: not on a floor and high vz / sustained descent
    travel = sum(math.hypot(s[i][1]-s[i-1][1], s[i][2]-s[i-1][2]) for i in range(1, len(s)))
    zrange = max(zs) - min(zs)
    # how much time is spent with big |z velocity| (falling/floating) early
    first10 = s[:10]
    falling0 = sum(1 for p in first10 if p[4] and p[5] < -50)
    tag = "<-- recorder" if num == st.self_player else "BOT?"
    print(f"slot {num:2d} {tag}: {len(s):3d} samples  t={ts[0]:.1f}..{ts[-1]:.1f}s")
    print(f"          spawn xyz=({xs[0]:.0f},{ys[0]:.0f},{spawn_z:.0f})  Zrange={zrange:.0f}  XYtravel={travel:.0f}")
    print(f"          Z min/max={min(zs):.0f}/{max(zs):.0f}  early-falling samples={falling0}/10")
    # show first 6 z to see spawn behaviour
    print(f"          first Z: {' '.join('%.0f'%p[3] for p in s[:8])}")
    print()

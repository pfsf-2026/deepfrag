#!/usr/bin/env python3
"""MVD (QuakeWorld MultiView Demo) movement parser + bot-realism "dials".

Reads a server-side mvdsv .mvd file, extracts per-player / per-frame movement
(origin + view angles), and computes movement dials used to tell humans from
bots.

USAGE
    python3 fragbot/mvd_movement.py <demo.mvd> [--player "name"]

Prints, per player (or just the named one), a JSON object and a markdown table
of dials. See the module docstring sections below for exactly how each dial is
derived.

------------------------------------------------------------------------------
ON-DISK FORMAT (verified against the mvdsv writer + mvdparser reader)
------------------------------------------------------------------------------
Ground truth:
  - mvdsv  src/sv_demo.c  -> SV_MVDWritePlayers (the *writer*)
  - mvdparser src/mvd_parser.c / netmsg_parser.c / net_msg.c (the *reader*)

An optional FTE extension prelude can precede the body: bytes "FTEX"+u32 flags
and/or "FTE2"+u32 flags, then "MVD1 " ... in this demo. We don't need those
flags up front -- the protocol/extension state is (re)established by the
svc_serverdata message inside the stream, which is where we learn whether
coordinates are "big" (float) coords. So we simply scan forward to the first
MVD demo block. A demo block is:

    1 byte   demo-time delta in milliseconds (added to running demo time)
    1 byte   command byte `c`; message type = c & 7 (low 3 bits)
             dem_cmd=0 (QWD only -> error), dem_read=1, dem_set=2,
             dem_multiple=3, dem_single=4, dem_stats=5, dem_all=7
      - dem_multiple: read 4-byte LE player bitmask, then fall through to read
      - dem_single / dem_stats: target player# = (c >> 3); fall through to read
      - dem_all: target = everyone; fall through to read
      - dem_set: read two 4-byte LE sequence numbers, no payload
    then for the "read" path:
    4 bytes  LE message length
    N bytes  a QW server->client message (a sequence of svc_* commands)

Within the payload we walk svc_* commands. The only one we care about for
movement is svc_playerinfo (42); but to stay byte-aligned we must fully
consume *every* svc command, so all of them are implemented as skips.

svc_playerinfo (the MVD on-disk variant, per sv_demo.c) -- NOTE this is NOT the
client-side PF_* usercmd form described in some docs; mvdsv writes a compact
delta form keyed on DF_* flags and carries NO velocity and NO usercmd:

    byte   playernum
    short  flags (DF_*)             DF_ORIGIN=1 (x), <<1 (y), <<2 (z),
                                     DF_ANGLES=1<<3 (pitch), <<1 (yaw), <<1 (roll),
                                     DF_EFFECTS=1<<6, DF_SKINNUM=1<<7,
                                     DF_DEAD=1<<8, DF_GIB=1<<9,
                                     DF_WEAPONFRAME=1<<10, DF_MODEL=1<<11
    byte   frame
    for j in 0..2: if flags & (DF_ORIGIN << j):  coord   (origin[j])
    for j in 0..2: if flags & (DF_ANGLES << j):  angle16 (viewangles[j])
    if DF_MODEL:       byte
    if DF_SKINNUM:     byte
    if DF_EFFECTS:     byte
    if DF_WEAPONFRAME: byte

Crucially, fields are *delta-encoded*: a coord/angle is only present when it
changed since that player's previous svc_playerinfo. So we carry forward the
last known origin/angles per player.

coord  = int16 / 8.0                  (quake units)        [unless big coords]
angle16= int16 * 360 / 65536          (degrees)            [unless big coords]
If svc_serverdata advertises FTE_PEXT_FLOATCOORDS, coords and angles are 32-bit
floats instead -- handled, though this demo uses the classic 16-bit form.

------------------------------------------------------------------------------
DIALS
------------------------------------------------------------------------------
Because the MVD carries position but NOT velocity, every kinematic dial is
derived by finite-differencing each player's origin/angle samples in demo time.

speed         horizontal speed |d(x,y)/dt| per frame, qu/s. mean/p50/p95/p99.
airborne_pct  fraction of frames the player is judged airborne. We have NO true
              ground-contact bit in this writer (PF_ONGROUND is a ZQuake/client
              extension not emitted here), so we APPROXIMATE: a frame is
              airborne if |vz| > AIRBORNE_VZ (default 40 qu/s) computed from the
              z finite difference. Documented approximation; see caveats.
jumps         rising-edge crossings of vz above JUMP_VZ (+200 qu/s).
pauses        contiguous runs where horizontal speed < PAUSE_SPEED (30 qu/s)
              lasting >= PAUSE_MIN_S (0.3 s). count + total seconds.
turn_rate     |d(yaw)/dt| in deg/s (shortest-arc), p50 and p95.
coupling      Pearson r between view-yaw angular velocity (deg/s) and the
              movement-heading angular velocity (deg/s). Movement heading =
              atan2(vy, vx); its time-derivative (shortest-arc) is how fast the
              direction of travel rotates. A human turns the view in lockstep
              with strafing/circle-jumping, so view-yaw-rate and
              heading-rate co-vary (r ~ 0.3+). A bot that snaps aim
              independently of its locomotion shows near-zero correlation
              (~0.03). Only frames where the player is actually moving
              (speed > COUPLING_MIN_SPEED) are included, since heading is
              undefined/noisy at rest.

Stdlib only (struct, math, json, argparse). No numpy/scipy.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Protocol constants (from mvdparser qw_protocol.h)
# --------------------------------------------------------------------------- #

# demo block message types (low 3 bits of command byte)
DEM_CMD = 0
DEM_READ = 1
DEM_SET = 2
DEM_MULTIPLE = 3
DEM_SINGLE = 4
DEM_STATS = 5
DEM_ALL = 6

# svc_* server->client commands
SVC_BAD = 0
SVC_NOP = 1
SVC_DISCONNECT = 2
SVC_UPDATESTAT = 3
SVC_SOUND = 6
NQ_SVC_TIME = 7
SVC_PRINT = 8
SVC_STUFFTEXT = 9
SVC_SETANGLE = 10
SVC_SERVERDATA = 11
SVC_LIGHTSTYLE = 12
SVC_UPDATEFRAGS = 14
SVC_STOPSOUND = 16
SVC_DAMAGE = 19
SVC_SPAWNSTATIC = 20
SVC_FTE_SPAWNSTATIC2 = 21
SVC_SPAWNBASELINE = 22
SVC_TEMP_ENTITY = 23
SVC_SETPAUSE = 24
SVC_CENTERPRINT = 26
SVC_KILLEDMONSTER = 27
SVC_FOUNDSECRET = 28
SVC_SPAWNSTATICSOUND = 29
SVC_INTERMISSION = 30
SVC_FINALE = 31
SVC_CDTRACK = 32
SVC_SELLSCREEN = 33
SVC_SMALLKICK = 34
SVC_BIGKICK = 35
SVC_UPDATEPING = 36
SVC_UPDATEENTERTIME = 37
SVC_UPDATESTATLONG = 38
SVC_MUZZLEFLASH = 39
SVC_UPDATEUSERINFO = 40
SVC_DOWNLOAD = 41
SVC_PLAYERINFO = 42
SVC_NAILS = 43
SVC_CHOKECOUNT = 44
SVC_MODELLIST = 45
SVC_SOUNDLIST = 46
SVC_PACKETENTITIES = 47
SVC_DELTAPACKETENTITIES = 48
SVC_MAXSPEED = 49
SVC_ENTGRAVITY = 50
SVC_SETINFO = 51
SVC_SERVERINFO = 52
SVC_UPDATEPL = 53
SVC_NAILS2 = 54
SVC_FTE_MODELLISTSHORT = 60
SVC_FTE_SPAWNBASELINE2 = 66
SVC_QIZMOVOICE = 83

# svc_playerinfo delta flags (DF_*)
DF_ORIGIN = 1          # x; <<1 y; <<2 z
DF_ANGLES = 1 << 3     # pitch; <<1 yaw; <<2 roll
DF_EFFECTS = 1 << 6
DF_SKINNUM = 1 << 7
DF_DEAD = 1 << 8
DF_GIB = 1 << 9
DF_WEAPONFRAME = 1 << 10
DF_MODEL = 1 << 11

# entity delta bits (svc_packetentities)
U_ORIGIN1 = 1 << 9
U_ORIGIN2 = 1 << 10
U_ORIGIN3 = 1 << 11
U_ANGLE2 = 1 << 12
U_FRAME = 1 << 13
U_REMOVE = 1 << 14
U_MOREBITS = 1 << 15
U_ANGLE1 = 1 << 0
U_ANGLE3 = 1 << 1
U_MODEL = 1 << 2
U_COLORMAP = 1 << 3
U_SKIN = 1 << 4
U_EFFECTS = 1 << 5
U_SOLID = 1 << 6
U_FTE_EVENMORE = 1 << 7
# fte "morebits"
U_FTE_TRANS = 1 << 1
U_FTE_MODELDBL = 1 << 3
U_FTE_ENTITYDBL = 1 << 5
U_FTE_ENTITYDBL2 = 1 << 6
U_FTE_YETMORE = 1 << 7
U_FTE_COLOURMOD = 1 << 10

# sound channel flags
SND_VOLUME = 1 << 15
SND_ATTENUATION = 1 << 14

# protocol magics
PROTOCOL_VERSION_FTE = struct.unpack("<I", b"FTEX")[0]
PROTOCOL_VERSION_FTE2 = struct.unpack("<I", b"FTE2")[0]
PROTOCOL_VERSION_MVD1 = struct.unpack("<I", b"MVD1")[0]
FTE_PEXT_FLOATCOORDS = 0x00008000

MAX_PLAYERS = 32

# --------------------------------------------------------------------------- #
# Dial thresholds (documented, tweakable)
# --------------------------------------------------------------------------- #
AIRBORNE_VZ = 40.0        # qu/s; |vz| above this -> treat frame as airborne
JUMP_VZ = 200.0           # qu/s; rising edge above this -> a jump
PAUSE_SPEED = 30.0        # qu/s; below this counts toward a "pause"
PAUSE_MIN_S = 0.30        # s; minimum contiguous pause duration
COUPLING_MIN_SPEED = 50.0  # qu/s; ignore near-stationary frames for coupling

# Reject absurd per-frame deltas (teleports / respawns / parse glitches) so a
# single 4000 qu jump in one frame doesn't poison the speed stats.
MAX_PLAUSIBLE_SPEED = 5000.0  # qu/s


class MvdParseError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Little message reader over a single net_message payload
# --------------------------------------------------------------------------- #
class MsgReader:
    """Reads QW primitives from a bytes payload, mirroring mvdparser net_msg.c."""

    def __init__(self, data: bytes, big_coords: bool = False):
        self.data = data
        self.pos = 0
        self.big_coords = big_coords
        self.bad = False

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def read_byte(self) -> int:
        if self.pos >= len(self.data):
            self.bad = True
            return -1
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_short(self) -> int:
        if self.pos + 2 > len(self.data):
            self.bad = True
            return -1
        v = struct.unpack_from("<h", self.data, self.pos)[0]  # signed
        self.pos += 2
        return v

    def read_long(self) -> int:
        if self.pos + 4 > len(self.data):
            self.bad = True
            return -1
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_float(self) -> float:
        if self.pos + 4 > len(self.data):
            self.bad = True
            return 0.0
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_coord(self) -> float:
        if self.big_coords:
            return self.read_float()
        return self.read_short() * (1.0 / 8.0)

    def read_angle(self) -> float:
        if self.big_coords:
            return self.read_angle16()
        return self.read_char() * (360.0 / 256.0)

    def read_char(self) -> int:
        if self.pos >= len(self.data):
            self.bad = True
            return -1
        v = struct.unpack_from("<b", self.data, self.pos)[0]  # signed
        self.pos += 1
        return v

    def read_angle16(self) -> float:
        return self.read_short() * (360.0 / 65536.0)

    def read_string(self) -> str:
        # mirrors MSG_ReadString: skip byte 255, stop at 0 / EOF
        out = bytearray()
        while True:
            c = self.read_byte()
            if c == 255:
                continue
            if c == -1 or c == 0:
                break
            out.append(c)
        return out.decode("latin-1", errors="replace")


# --------------------------------------------------------------------------- #
# Per-player accumulation
# --------------------------------------------------------------------------- #
@dataclass
class PlayerTrack:
    pnum: int
    name: str = ""
    is_spectator: bool = False
    # last known full state (delta carry-forward)
    origin: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    angles: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    have_origin: bool = False
    # samples: (demotime_s, x, y, z, yaw_deg)
    samples: list = field(default_factory=list)


@dataclass
class ParseState:
    big_coords: bool = False
    demotime: float = 0.0
    players: dict = field(default_factory=dict)  # pnum -> PlayerTrack
    lastto: int = 0
    lasttype: int = 0

    def player(self, pnum: int) -> PlayerTrack:
        p = self.players.get(pnum)
        if p is None:
            p = PlayerTrack(pnum=pnum)
            self.players[pnum] = p
        return p


# --------------------------------------------------------------------------- #
# net_message (svc command stream) parser
# --------------------------------------------------------------------------- #
def parse_entity_num(r: MsgReader):
    bits = r.read_short() & 0xFFFF
    entnum = bits & 0x1FF
    bits &= ~0x1FF
    morebits = 0
    if bits & U_MOREBITS:
        bits |= r.read_byte()
        if bits & U_FTE_EVENMORE:
            morebits = r.read_byte()
            if morebits & U_FTE_YETMORE:
                morebits |= r.read_byte() << 8
            if morebits & U_FTE_ENTITYDBL:
                entnum += 512
            if morebits & U_FTE_ENTITYDBL2:
                entnum += 1024
    return entnum, bits, morebits


def parse_entity_delta(r: MsgReader, bits: int, morebits: int):
    if bits & U_MODEL:
        r.read_byte()
    elif morebits & U_FTE_MODELDBL:
        r.read_short()
    if bits & U_FRAME:
        r.read_byte()
    if bits & U_COLORMAP:
        r.read_byte()
    if bits & U_SKIN:
        r.read_byte()
    if bits & U_EFFECTS:
        r.read_byte()
    if bits & U_ORIGIN1:
        r.read_coord()
    if bits & U_ORIGIN2:
        r.read_coord()
    if bits & U_ORIGIN3:
        r.read_coord()
    if bits & U_ANGLE1:
        r.read_angle()
    if bits & U_ANGLE2:
        r.read_angle()
    if bits & U_ANGLE3:
        r.read_angle()
    if morebits & U_FTE_TRANS:
        r.read_byte()
    if morebits & U_FTE_COLOURMOD:
        r.read_byte()
        r.read_byte()
        r.read_byte()


def parse_packet_entities(r: MsgReader, delta: bool):
    if delta:
        r.read_byte()  # delta-from frame
    while True:
        entnum, bits, morebits = parse_entity_num(r)
        if r.bad:
            return
        if not entnum:
            break
        parse_entity_delta(r, bits, morebits)


def parse_playerinfo(r: MsgReader, st: ParseState):
    num = r.read_byte()
    flags = r.read_short() & 0xFFFF
    frame = r.read_byte()  # noqa: F841 (consumed for alignment)
    p = st.player(num)

    for j in range(3):
        if flags & (DF_ORIGIN << j):
            p.origin[j] = r.read_coord()
    for j in range(3):
        if flags & (DF_ANGLES << j):
            p.angles[j] = r.read_angle16()
    if flags & DF_MODEL:
        r.read_byte()
    if flags & DF_SKINNUM:
        r.read_byte()
    if flags & DF_EFFECTS:
        r.read_byte()
    if flags & DF_WEAPONFRAME:
        r.read_byte()

    if r.bad:
        return

    # angles[1] is yaw. Record a movement sample at the current demo time.
    p.have_origin = True
    p.samples.append(
        (st.demotime, p.origin[0], p.origin[1], p.origin[2], p.angles[1])
    )


def parse_net_message(payload: bytes, st: ParseState):
    """Walk one length-prefixed net_message, dispatching svc commands."""
    r = MsgReader(payload, big_coords=st.big_coords)
    while not r.eof():
        cmd = r.read_byte()
        if cmd == -1:
            break

        if cmd == SVC_NOP or cmd == SVC_BAD:
            continue
        elif cmd == SVC_DISCONNECT:
            return
        elif cmd == NQ_SVC_TIME:
            r.read_float()
        elif cmd == SVC_PRINT:
            r.read_byte()
            r.read_string()
        elif cmd == SVC_CENTERPRINT:
            r.read_string()
        elif cmd == SVC_STUFFTEXT:
            r.read_string()
        elif cmd == SVC_DAMAGE:
            r.read_byte()
            r.read_byte()
            r.read_coord()
            r.read_coord()
            r.read_coord()
        elif cmd == SVC_SERVERDATA:
            parse_serverdata(r, st)
        elif cmd == SVC_CDTRACK:
            r.read_byte()
        elif cmd == SVC_PLAYERINFO:
            parse_playerinfo(r, st)
        elif cmd == SVC_MODELLIST:
            parse_stringlist(r, extended=False)
        elif cmd == SVC_FTE_MODELLISTSHORT:
            parse_stringlist(r, extended=True)
        elif cmd == SVC_SOUNDLIST:
            parse_stringlist(r, extended=False)
        elif cmd == SVC_SPAWNSTATICSOUND:
            for _ in range(3):
                r.read_coord()
            r.read_byte()
            r.read_byte()
            r.read_byte()
        elif cmd == SVC_SPAWNBASELINE:
            r.read_short()
            r.read_byte()
            r.read_byte()
            r.read_byte()
            r.read_byte()
            for _ in range(3):
                r.read_coord()
                r.read_angle()
        elif cmd == SVC_FTE_SPAWNBASELINE2:
            en, b, mb = parse_entity_num(r)
            parse_entity_delta(r, b, mb)
        elif cmd == SVC_UPDATEFRAGS:
            r.read_byte()
            r.read_short()
        elif cmd == SVC_UPDATEPING:
            r.read_byte()
            r.read_short()
        elif cmd == SVC_UPDATEPL:
            r.read_byte()
            r.read_byte()
        elif cmd == SVC_UPDATEENTERTIME:
            r.read_byte()
            r.read_float()
        elif cmd == SVC_UPDATEUSERINFO:
            parse_updateuserinfo(r, st)
        elif cmd == SVC_LIGHTSTYLE:
            r.read_byte()
            r.read_string()
        elif cmd == SVC_SERVERINFO:
            r.read_string()  # key
            r.read_string()  # value
        elif cmd == SVC_PACKETENTITIES:
            parse_packet_entities(r, delta=False)
        elif cmd == SVC_DELTAPACKETENTITIES:
            parse_packet_entities(r, delta=True)
        elif cmd == SVC_UPDATESTATLONG:
            r.read_byte()
            r.read_long()
        elif cmd == SVC_UPDATESTAT:
            r.read_byte()
            r.read_byte()
        elif cmd == SVC_SOUND:
            parse_sound(r)
        elif cmd == SVC_STOPSOUND:
            r.read_short()
        elif cmd == SVC_TEMP_ENTITY:
            parse_temp_entity(r)
        elif cmd == SVC_SETANGLE:
            r.read_byte()
            for _ in range(3):
                r.read_angle()
        elif cmd == SVC_SETINFO:
            r.read_byte()
            r.read_string()
            r.read_string()
        elif cmd == SVC_MUZZLEFLASH:
            r.read_short()
        elif cmd == SVC_SMALLKICK or cmd == SVC_BIGKICK:
            pass
        elif cmd == SVC_INTERMISSION:
            for _ in range(3):
                r.read_coord()
            for _ in range(3):
                r.read_angle()
        elif cmd == SVC_CHOKECOUNT:
            r.read_byte()
        elif cmd == SVC_SPAWNSTATIC:
            r.read_byte()
            r.read_byte()
            r.read_byte()
            r.read_byte()
            for _ in range(3):
                r.read_coord()
                r.read_angle()
        elif cmd == SVC_FTE_SPAWNSTATIC2:
            en, b, mb = parse_entity_num(r)
            parse_entity_delta(r, b, mb)
        elif cmd == SVC_FOUNDSECRET or cmd == SVC_KILLEDMONSTER:
            pass
        elif cmd == SVC_SETPAUSE:
            r.read_byte()
        elif cmd == SVC_MAXSPEED:
            r.read_float()
        elif cmd == SVC_ENTGRAVITY:
            r.read_float()
        elif cmd == SVC_NAILS:
            parse_nails(r, extended=False)
        elif cmd == SVC_NAILS2:
            parse_nails(r, extended=True)
        else:
            # Unknown command -> we can no longer trust alignment in this msg.
            raise MvdParseError(
                f"Unknown svc command {cmd} at byte {r.pos - 1} of net_message "
                f"(len {len(payload)})."
            )

        if r.bad:
            # Ran off the end of the payload mid-command; stop this message.
            break


def parse_serverdata(r: MsgReader, st: ParseState):
    while True:
        protocol = r.read_long() & 0xFFFFFFFF
        if protocol == PROTOCOL_VERSION_FTE:
            ext = r.read_long()
            if ext & FTE_PEXT_FLOATCOORDS:
                st.big_coords = True
                r.big_coords = True
        elif protocol == PROTOCOL_VERSION_FTE2:
            r.read_long()
        elif protocol == PROTOCOL_VERSION_MVD1:
            r.read_long()
        else:
            break
    r.read_long()            # servercount
    r.read_string()          # gamedir
    r.read_float()           # demotime
    r.read_string()          # mapname
    for _ in range(10):      # movevars
        r.read_float()


def parse_stringlist(r: MsgReader, extended: bool):
    if extended:
        r.read_short()
    else:
        r.read_byte()
    while True:
        s = r.read_string()
        if not s:
            break
    r.read_byte()  # next index / ignore


def parse_sound(r: MsgReader):
    channel = r.read_short() & 0xFFFF
    if channel & SND_VOLUME:
        r.read_byte()
    if channel & SND_ATTENUATION:
        r.read_byte()
    r.read_byte()  # soundnum
    for _ in range(3):
        r.read_coord()


def parse_temp_entity(r: MsgReader):
    TE_GUNSHOT, TE_BLOOD = 2, 12
    TE_LIGHTNING1, TE_LIGHTNING2, TE_LIGHTNING3 = 5, 6, 9
    t = r.read_byte()
    if t in (TE_GUNSHOT, TE_BLOOD):
        r.read_byte()
    if t in (TE_LIGHTNING1, TE_LIGHTNING2, TE_LIGHTNING3):
        r.read_short()
        for _ in range(3):
            r.read_coord()
    for _ in range(3):
        r.read_coord()


def parse_nails(r: MsgReader, extended: bool):
    n = r.read_byte()
    for _ in range(n):
        if extended:
            r.read_byte()  # projectile number
        for _ in range(6):
            r.read_byte()


def parse_updateuserinfo(r: MsgReader, st: ParseState):
    pnum = r.read_byte()
    r.read_long()  # userid
    userinfo = r.read_string()
    if pnum < 0:
        return
    p = st.player(pnum)
    name = info_value(userinfo, "name")
    if name:
        p.name = redtext_to_white(name)
    p.is_spectator = bool(info_value(userinfo, "*spectator"))


def info_value(s: str, key: str) -> str:
    """Mirror Info_ValueForKey for a '\\k\\v\\k\\v' info string."""
    if not s:
        return ""
    parts = s.split("\\")
    # leading empty element if string starts with backslash
    if parts and parts[0] == "":
        parts = parts[1:]
    for i in range(0, len(parts) - 1, 2):
        if parts[i] == key:
            return parts[i + 1]
    return ""


def redtext_to_white(s: str) -> str:
    """Map QuakeWorld 'red'/special charset bytes to plain ASCII."""
    out = []
    for ch in s:
        c = ord(ch) & 0x7F
        if c < 32:
            # control-range glyphs map roughly to brackets/punct; keep readable
            mapping = {16: "[", 17: "]", 18: "0", 19: "1", 20: "2", 21: "3",
                       22: "4", 23: "5", 24: "6", 25: "7", 26: "8", 27: "9",
                       28: ".", 29: "-", 30: "-", 31: "-"}
            out.append(mapping.get(c, ""))
        else:
            out.append(chr(c))
    return "".join(out).strip()


# --------------------------------------------------------------------------- #
# Top-level demo walk
# --------------------------------------------------------------------------- #
def find_mvd_start(data: bytes) -> int:
    """Skip any FTEX/FTE2 prelude; return offset of the first demo block.

    The prelude (when present) is: 'FTEX' u32, optional 'FTE2' u32, then 'MVD1 '
    followed by more header bytes, then the demo blocks. Rather than decode the
    prelude precisely (it varies), we locate the 'MVD1' magic; the very first
    demo block (a dem_set carrying sequence numbers) follows the serverdata
    setup. Simplest robust approach: if 'MVD1' is present we still must begin
    block parsing from byte 0 only if there's no prelude. mvdsv MVD files with
    the FTE prelude begin block parsing right after the prelude's 'MVD1 ' +
    extension u32. We detect the prelude and skip it; otherwise start at 0.
    """
    # No prelude: classic files start directly with demo blocks.
    if data[:4] not in (b"FTEX", b"FTE2", b"MVD1"):
        return 0
    pos = 0
    # FTEX u32
    if data[pos:pos + 4] == b"FTEX":
        pos += 8
    # FTE2 u32
    if data[pos:pos + 4] == b"FTE2":
        pos += 8
    # MVD1 + a trailing space + u32 extension flags (observed: 'MVD1 ' then u32)
    if data[pos:pos + 4] == b"MVD1":
        pos += 4
        # consume the optional space and the 4-byte extension flags
        if pos < len(data) and data[pos] == 0x20:  # ' '
            pos += 1
        pos += 4
    return pos


def parse_mvd(data: bytes) -> ParseState:
    st = ParseState()
    pos = find_mvd_start(data)
    n = len(data)

    while pos < n:
        # 1 byte demo-time delta (ms)
        mvd_time = data[pos]
        pos += 1
        if pos >= n:
            break
        st.demotime += mvd_time * 0.001

        c = data[pos]
        pos += 1
        mtype = c & 7

        if mtype == DEM_CMD:
            raise MvdParseError(
                f"dem_cmd at offset {pos - 1}: this is a QWD, not an MVD."
            )

        if DEM_MULTIPLE <= mtype <= DEM_ALL:
            if mtype == DEM_MULTIPLE:
                if pos + 4 > n:
                    break
                st.lastto = struct.unpack_from("<I", data, pos)[0]
                pos += 4
                st.lasttype = DEM_MULTIPLE
            elif mtype in (DEM_SINGLE, DEM_STATS):
                st.lastto = c >> 3
                st.lasttype = mtype
            elif mtype == DEM_ALL:
                st.lastto = 0
                st.lasttype = DEM_ALL
            else:
                raise MvdParseError(f"Unknown demo type {mtype} at {pos - 1}")
            mtype = DEM_READ  # fall through to read the payload

        if mtype == DEM_READ:
            if pos + 4 > n:
                break
            length = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            if length < 0 or pos + length > n:
                # truncated tail; stop cleanly
                break
            payload = data[pos:pos + length]
            pos += length
            # dem_multiple is only ever chat/etc in mvdsv; harmless to parse,
            # but mvdparser skips it. We parse everything except multiple to
            # match its semantics and avoid wasted work.
            if st.lasttype != DEM_MULTIPLE:
                parse_net_message(payload, st)
            continue

        if mtype == DEM_SET:
            if pos + 8 > n:
                break
            pos += 8
            continue

        raise MvdParseError(f"Unhandled demo message type {mtype} at {pos - 1}")

    return st


# --------------------------------------------------------------------------- #
# Dial computation
# --------------------------------------------------------------------------- #
def percentile(sorted_vals, q: float) -> float:
    """Linear-interpolated percentile (q in 0..1) of a pre-sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def shortest_arc(deg: float) -> float:
    """Wrap an angle difference into [-180, 180]."""
    while deg > 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


def pearson(xs, ys) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sxx = syy = 0.0
    for x, y in zip(xs, ys):
        dx = x - mx
        dy = y - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    denom = math.sqrt(sxx * syy)
    if denom == 0.0:
        return 0.0
    return sxy / denom


def compute_dials(track: PlayerTrack) -> dict:
    s = track.samples
    result = {
        "name": track.name or f"player{track.pnum}",
        "pnum": track.pnum,
        "frames": len(s),
    }
    if len(s) < 2:
        result.update({
            "duration_s": 0.0,
            "note": "insufficient samples",
        })
        return result

    t0 = s[0][0]
    t1 = s[-1][0]
    result["duration_s"] = round(t1 - t0, 3)

    speeds = []          # horizontal speed per interval, qu/s
    vzs = []             # vertical velocity per interval, qu/s
    yaw_rates = []       # |d yaw / dt|, deg/s  (per interval)
    # coupling series (only while moving):
    coup_view_rate = []  # d(view yaw)/dt, signed, deg/s
    coup_head_rate = []  # d(movement heading)/dt, signed, deg/s

    prev_heading = None
    # We attribute interval-derived velocity to the *later* sample's frame.
    per_frame_speed = []  # aligned with intervals; used for pauses too
    interval_dt = []

    for i in range(1, len(s)):
        t_prev, x0, y0, z0, yaw0 = s[i - 1]
        t_cur, x1, y1, z1, yaw1 = s[i]
        dt = t_cur - t_prev
        if dt <= 0:
            continue
        vx = (x1 - x0) / dt
        vy = (y1 - y0) / dt
        vz = (z1 - z0) / dt
        hspeed = math.hypot(vx, vy)

        # Drop implausible single-frame jumps (teleport / respawn / glitch).
        if hspeed > MAX_PLAUSIBLE_SPEED or abs(vz) > MAX_PLAUSIBLE_SPEED:
            prev_heading = None
            continue

        speeds.append(hspeed)
        vzs.append(vz)
        per_frame_speed.append(hspeed)
        interval_dt.append(dt)

        # turn rate from the view yaw
        dyaw = shortest_arc(yaw1 - yaw0)
        yaw_rate = dyaw / dt
        yaw_rates.append(abs(yaw_rate))

        # coupling: only when actually moving (heading is defined)
        if hspeed >= COUPLING_MIN_SPEED:
            heading = math.degrees(math.atan2(vy, vx))
            if prev_heading is not None:
                dhead = shortest_arc(heading - prev_heading)
                head_rate = dhead / dt
                coup_view_rate.append(yaw_rate)
                coup_head_rate.append(head_rate)
            prev_heading = heading
        else:
            prev_heading = None

    if not speeds:
        result.update({"note": "no valid movement intervals"})
        return result

    sp_sorted = sorted(speeds)
    result["speed"] = {
        "mean": round(sum(speeds) / len(speeds), 2),
        "p50": round(percentile(sp_sorted, 0.50), 2),
        "p95": round(percentile(sp_sorted, 0.95), 2),
        "p99": round(percentile(sp_sorted, 0.99), 2),
    }

    # airborne approximation: |vz| above threshold
    airborne = sum(1 for v in vzs if abs(v) > AIRBORNE_VZ)
    result["airborne_pct"] = round(100.0 * airborne / len(vzs), 1)

    # jumps: rising-edge crossings of vz above JUMP_VZ
    jumps = 0
    prev_above = False
    for v in vzs:
        above = v > JUMP_VZ
        if above and not prev_above:
            jumps += 1
        prev_above = above
    result["jumps"] = jumps

    # pauses: contiguous runs where hspeed < PAUSE_SPEED for >= PAUSE_MIN_S
    pause_count = 0
    pause_total = 0.0
    run_time = 0.0
    for spd, dt in zip(per_frame_speed, interval_dt):
        if spd < PAUSE_SPEED:
            run_time += dt
        else:
            if run_time >= PAUSE_MIN_S:
                pause_count += 1
                pause_total += run_time
            run_time = 0.0
    if run_time >= PAUSE_MIN_S:
        pause_count += 1
        pause_total += run_time
    result["pauses"] = {"count": pause_count, "total_seconds": round(pause_total, 2)}

    # turn rate percentiles
    yr_sorted = sorted(yaw_rates)
    result["turn_rate_deg_s"] = {
        "p50": round(percentile(yr_sorted, 0.50), 1),
        "p95": round(percentile(yr_sorted, 0.95), 1),
    }

    # coupling
    r = pearson(coup_view_rate, coup_head_rate)
    result["coupling"] = round(r, 3)
    result["coupling_samples"] = len(coup_view_rate)

    return result


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def dials_markdown(dials: dict) -> str:
    rows = []
    rows.append(f"### {dials.get('name')} (pnum {dials.get('pnum')})")
    rows.append("")
    rows.append("| dial | value |")
    rows.append("| --- | --- |")
    rows.append(f"| frames | {dials.get('frames')} |")
    rows.append(f"| duration_s | {dials.get('duration_s')} |")
    if "speed" in dials:
        sp = dials["speed"]
        rows.append(f"| speed mean | {sp['mean']} qu/s |")
        rows.append(f"| speed p50 | {sp['p50']} qu/s |")
        rows.append(f"| speed p95 | {sp['p95']} qu/s |")
        rows.append(f"| speed p99 | {sp['p99']} qu/s |")
        rows.append(f"| airborne_pct | {dials['airborne_pct']}% |")
        rows.append(f"| jumps | {dials['jumps']} |")
        rows.append(
            f"| pauses | {dials['pauses']['count']} "
            f"({dials['pauses']['total_seconds']}s) |"
        )
        tr = dials["turn_rate_deg_s"]
        rows.append(f"| turn_rate p50 | {tr['p50']} deg/s |")
        rows.append(f"| turn_rate p95 | {tr['p95']} deg/s |")
        rows.append(
            f"| coupling (view-yaw vs heading) | {dials['coupling']} "
            f"(n={dials['coupling_samples']}) |"
        )
    else:
        rows.append(f"| note | {dials.get('note', '')} |")
    rows.append("")
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Extract per-player movement dials from a QuakeWorld MVD."
    )
    ap.add_argument("demo", help="Path to a .mvd file")
    ap.add_argument("--player", help="Only report this player (substring match)")
    args = ap.parse_args(argv)

    with open(args.demo, "rb") as f:
        data = f.read()

    st = parse_mvd(data)

    # Build dials for every player that produced movement samples.
    tracks = [t for t in st.players.values() if t.samples]
    # Prefer real players (have a name, not spectators) but keep all.
    tracks.sort(key=lambda t: t.pnum)

    selected = tracks
    if args.player:
        q = args.player.lower()
        selected = [t for t in tracks
                    if q in (t.name or f"player{t.pnum}").lower()]
        if not selected:
            avail = ", ".join(repr(t.name or f"player{t.pnum}") for t in tracks)
            print(f"No player matching {args.player!r}. Available: {avail}",
                  file=sys.stderr)
            return 1

    all_dials = [compute_dials(t) for t in selected]

    print(json.dumps(all_dials if len(all_dials) > 1 else all_dials[0],
                     indent=2))
    print()
    for d in all_dials:
        print(dials_markdown(d))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

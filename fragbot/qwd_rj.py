#!/usr/bin/env python3
"""Rocket-jump analyzer for QuakeWorld CLIENT demos (.qwd).

Extracts the RECORDING player's per-frame position + velocity + STAT_AMMO from
a first-person .qwd, segments rocket-jump (RJ) attempts off the vertical-velocity
spike, and reports per-attempt self-damage and whether the player reached the
aerowalk Red Armor.

WHY STAT_AMMO IS THE DAMAGE SIGNAL
----------------------------------
These demos were recorded in KTX *pre-war*, where self-damage is NOT applied to
health. Instead KTX combat.c does:  targ->s.v.currentammo = 1000 + Q_rint(damage)
so the would-be self-damage shows up in the AMMO HUD (STAT_AMMO, stat index 3).
Therefore per-attempt self-damage = (peak STAT_AMMO during the jump) - 1000.
Health is constant and is NOT used for damage or segmentation.

DEMO FORMAT (the alignment-critical part)
-----------------------------------------
A client .qwd is a stream of blocks:
    float32  demo time (seconds, absolute)        [NOT the 1-byte ms MVD form]
    byte     command; message type = low 3 bits (dem_cmd=0, dem_read=1, ...)
  for dem_read (and single/stats/all/multiple), then:
    int32    payload length
    N bytes  payload = [8-byte netchan seq header][svc_* command stream]

The 8-byte seq header inside each dem_read payload is the QW netchan
(incoming/outgoing sequence) and MUST be skipped before the svc stream.

These are FTE/"ezcsqc" (dusty-qw mvdsv) demos. svc_serverdata advertises:
    EZPEXT1_FLOATENTCOORDS  -> player/entity origins are 32-bit floats
    PEXT_TRANS, PEXT_COLOURMOD -> playerinfo may carry alpha / colourmod bytes
    protocol_qw = 28        -> usercmd delta uses the >26 (short) form
We decode serverdata to learn these, then parse the client-POV svc_playerinfo
(svc 42) which carries the recorder's origin + velocity + a delta usercmd, plus
svc_updatestat / svc_updatestatlong for STAT_AMMO. Every other svc is fully
decoded so byte alignment is preserved through the CSQC native-setup + entity
stream (svc_fte_csqcentities) that follows spawn.

Stdlib only (struct, math, json, argparse). No numpy.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys

# --------------------------------------------------------------------------- #
# QWD block framing
# --------------------------------------------------------------------------- #
DEM_CMD = 0
DEM_READ = 1
DEM_SET = 2
DEM_MULTIPLE = 3
DEM_SINGLE = 4
DEM_STATS = 5
DEM_ALL = 6

# dem_cmd on-disk record (after the 5-byte float-time + type header):
# FTE writes `q1usercmd_t` (28 bytes incl. struct padding: byte msec; 3 pad;
# vec3_t angles as 3 floats; 3 short forward/side/upmove; byte buttons; byte
# impulse; trailing pad) followed by 3 float view angles (12 bytes).
# Measured empirically against rj_full_dmg.qwd: 40 bytes total. Using the
# q1usercmd_s C layout from FTE protocol.h, sizeof == 28 on a 4-byte-aligned
# build; 28 + 12 == 40.
DEM_CMD_USERCMD_SIZE = 28
DEM_CMD_VIEWANGLE_SIZE = 12

# --------------------------------------------------------------------------- #
# svc_* server->client commands (QW + FTE)
# --------------------------------------------------------------------------- #
SVC_BAD = 0
SVC_NOP = 1
SVC_DISCONNECT = 2
SVC_UPDATESTAT = 3
SVC_SETVIEW = 5
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
SVC_FTE_SOUNDLISTSHORT = 56
SVC_FTE_LIGHTSTYLECOL = 57
SVC_FTE_MODELLISTSHORT = 60
SVC_FTE_SPAWNBASELINE2 = 66
SVC_FTE_SPAWNSTATICSOUND2 = 67
SVC_FTE_EFFECT = 74
SVC_FTE_EFFECT2 = 75
SVC_FTE_CSQCENTITIES = 76
SVC_FTE_UPDATESTATSTRING = 78
SVC_FTE_UPDATESTATFLOAT = 79
SVC_FTE_TRAILPARTICLES = 80
SVC_FTE_POINTPARTICLES = 81
SVC_FTE_POINTPARTICLES1 = 82
SVC_FTE_CGAMEPACKET = 83
SVC_FTE_VOICECHAT = 84
SVC_FTE_SETINFOBLOB = 89
SVC_FTE_CGAMEPACKET_SIZED = 90
SVC_FTE_CSQCENTITIES_SIZED = 92
SVC_QIZMOVOICE = 83  # alias
SVC_PACKETSPROJECTILES = 100  # ezQuake MVD_PEXT1_SIMPLEPROJECTILE

# svc_particle family (rare in QW, present for safety)
SVC_PARTICLE = 13
SVC_FTE_PARTICLE2 = 70
SVC_FTE_PARTICLE3 = 71
SVC_FTE_PARTICLE4 = 72

# --------------------------------------------------------------------------- #
# Client svc_playerinfo flags (PF_*)
# --------------------------------------------------------------------------- #
PF_MSEC = 1 << 0
PF_COMMAND = 1 << 1
PF_VELOCITY1 = 1 << 2
PF_VELOCITY2 = 1 << 3
PF_VELOCITY3 = 1 << 4
PF_MODEL = 1 << 5
PF_SKINNUM = 1 << 6
PF_EFFECTS = 1 << 7
PF_WEAPONFRAME = 1 << 8
PF_DEAD = 1 << 9
PF_GIB = 1 << 10
PF_EXTRA_PFS = 1 << 15
PF_SCALE = 1 << 16
PF_TRANS = 1 << 17
PF_FATNESS = 1 << 18
PF_COLOURMOD = 1 << 19
PF_HULLSIZE_Z = 1 << 14

# usercmd delta flags (CM_*)
CM_ANGLE1 = 1 << 0
CM_ANGLE3 = 1 << 1
CM_FORWARD = 1 << 2
CM_SIDE = 1 << 3
CM_UP = 1 << 4
CM_BUTTONS = 1 << 5
CM_IMPULSE = 1 << 6
CM_ANGLE2 = 1 << 7

# entity delta bits (svc_packetentities, classic + FTE morebits)
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
U_FTE_TRANS = 1 << 1
U_FTE_MODELDBL = 1 << 3
U_FTE_ENTITYDBL = 1 << 5
U_FTE_ENTITYDBL2 = 1 << 6
U_FTE_YETMORE = 1 << 7
U_FTE_SCALE = 1 << 8
U_FTE_FATNESS = 1 << 9
U_FTE_DRAWFLAGS = 1 << 11
U_FTE_ABSLIGHT = 1 << 12
U_FTE_COLOURMOD = 1 << 10
U_FTE_DPFLAGS = 1 << 13
U_FTE_TAGINFO = 1 << 14
U_FTE_LIGHT = 1 << 15

# sound channel flags
SND_VOLUME = 1 << 15
SND_ATTENUATION = 1 << 14
SND_FTE_PITCHADJ = 1 << 11
SND_FTE_MOREFLAGS = 1 << 12

# protocol magics
PV_FTE1 = struct.unpack("<I", b"FTEX")[0]
PV_FTE2 = struct.unpack("<I", b"FTE2")[0]
PV_EZ1 = struct.unpack("<I", b"MVD1")[0]   # PROTOCOL_VERSION_EZQUAKE1 == 'MVD1'
PV_VARLENGTH = struct.unpack("<I", b"vlen")[0]
PROTOCOL_VERSION_QW = 28

PEXT_SCALE = 0x00000002
PEXT_TRANS = 0x00000008
PEXT_FATNESS = 0x00000100
PEXT_HULLSIZE = 0x00000800
PEXT_FLOATCOORDS = 0x00008000
PEXT_COLOURMOD = 0x00080000
FTE_HAS_EXTRA_PF_MASK = PEXT_HULLSIZE | PEXT_TRANS | PEXT_SCALE | PEXT_FATNESS

PEXT2_REPLACEMENTDELTAS = 0x00000008
PEXT2_MAXPLAYERS = 0x00000010
PEXT2_PREDINFO = 0x00000020

EZPEXT1_FLOATENTCOORDS = 0x00000001

# ezQuake/mvdsv MVD_PEXT1 extensions (carried in serverdata under the 'MVD1'
# protocol-version magic; ezQuake stores it in cls.mvdprotocolextensions1).
# These are what the dusty-qw "ezcsqc" recorder uses. FLOATCOORDS (0x1) is
# confirmed against the demo (player/entity origins are 32-bit floats);
# WEAPONPREDICTION (0x80) adds a per-player block after PF_WEAPONFRAME
# (verified to align exactly to the next svc boundary in rj_full_dmg.qwd).
MVD_PEXT1_FLOATCOORDS = 0x00000001
MVD_PEXT1_WEAPONPREDICTION = 0x00000080
PF_TRANS_Z = 1 << 17

STAT_HEALTH = 0
STAT_AMMO = 3
STAT_ARMOR = 4
AMMO_DAMAGE_BASE = 1000  # KTX pre-war: currentammo = 1000 + damage


class QwdRjError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Message reader over one net_message payload
# --------------------------------------------------------------------------- #
class MsgReader:
    def __init__(self, data: bytes, big_coords: bool, float_ent_coords: bool):
        self.data = data
        self.pos = 0
        self.big_coords = big_coords        # PEXT_FLOATCOORDS (all coords float)
        self.float_ent_coords = float_ent_coords  # EZPEXT1 (player/ent origins float)
        self.bad = False

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read_byte(self) -> int:
        if self.pos >= len(self.data):
            self.bad = True
            return -1
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_char(self) -> int:
        if self.pos >= len(self.data):
            self.bad = True
            return -1
        v = struct.unpack_from("<b", self.data, self.pos)[0]
        self.pos += 1
        return v

    def read_short(self) -> int:
        if self.pos + 2 > len(self.data):
            self.bad = True
            return -1
        v = struct.unpack_from("<h", self.data, self.pos)[0]
        self.pos += 2
        return v

    def read_ushort(self) -> int:
        if self.pos + 2 > len(self.data):
            self.bad = True
            return 0
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def read_long(self) -> int:
        if self.pos + 4 > len(self.data):
            self.bad = True
            return -1
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_ulong(self) -> int:
        if self.pos + 4 > len(self.data):
            self.bad = True
            return 0
        v = struct.unpack_from("<I", self.data, self.pos)[0]
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

    def read_player_coord(self) -> float:
        """Player/entity origin: float if EZPEXT1_FLOATENTCOORDS or FLOATCOORDS."""
        if self.float_ent_coords or self.big_coords:
            return self.read_float()
        return self.read_short() * (1.0 / 8.0)

    def read_angle(self) -> float:
        if self.big_coords:
            return self.read_angle16()
        return self.read_char() * (360.0 / 256.0)

    def read_angle16(self) -> float:
        return self.read_short() * (360.0 / 65536.0)

    def read_string(self) -> str:
        out = bytearray()
        while True:
            c = self.read_byte()
            if c == -1 or c == 0:
                break
            out.append(c)
        return out.decode("latin-1", errors="replace")


# --------------------------------------------------------------------------- #
# Parse state
# --------------------------------------------------------------------------- #
class ParseState:
    def __init__(self):
        self.big_coords = False
        self.float_ent_coords = False
        self.weapon_prediction = False
        self.fte1 = 0
        self.fte2 = 0
        self.ez1 = 0          # ezQuake MVD_PEXT1 set (carried under 'MVD1' magic)
        self.protocol_qw = PROTOCOL_VERSION_QW
        self.demotime = 0.0
        self.viewentity = None       # entity# of the recorder (svc_setview)
        self.self_player = None      # player slot of the recorder
        self.stats = {}              # current stat values (last seen)
        # most recent view angles decoded from the POV delta usercmd
        # (CM_ANGLE1 -> pitch, CM_ANGLE2 -> yaw), in degrees [-180,180].
        self.last_pitch = 0.0
        self.last_yaw = 0.0
        # time series for the recorder (POV) player:
        # list of (time, x, y, z, vx, vy, vz, have_vel, pitch, yaw)
        self.samples = []
        # stat events: list of (time, stat_index, value)
        self.stat_events = []
        # alignment diagnostics
        self.last_good_offset = 0


# --------------------------------------------------------------------------- #
# svc_serverdata
# --------------------------------------------------------------------------- #
def parse_serverdata(r: MsgReader, st: ParseState):
    st.fte1 = st.fte2 = st.ez1 = 0
    while True:
        protover = r.read_ulong()
        if protover == PV_FTE1:
            st.fte1 = r.read_ulong()
            continue
        if protover == PV_FTE2:
            st.fte2 = r.read_ulong()
            continue
        if protover == PV_EZ1:
            st.ez1 = r.read_ulong()
            continue
        if protover == PV_VARLENGTH:
            r.read_ulong()           # ident
            length = r.read_ulong()
            for _ in range(length):
                r.read_byte()
            continue
        # PROTOCOL_VERSION_QW (28) or legacy 24..28 ends the version block
        break
    st.protocol_qw = protover

    if st.fte1 & PEXT_FLOATCOORDS:
        st.big_coords = True
        r.big_coords = True
    # ezQuake carries MVD_PEXT1 under the 'MVD1' magic (== PROTOCOL_VERSION_EZQUAKE1).
    if st.ez1 & (EZPEXT1_FLOATENTCOORDS | MVD_PEXT1_FLOATCOORDS):
        st.float_ent_coords = True
        r.float_ent_coords = True
    if st.ez1 & MVD_PEXT1_WEAPONPREDICTION:
        st.weapon_prediction = True

    r.read_long()        # servercount
    r.read_string()      # gamedir

    if st.fte2 & PEXT2_MAXPLAYERS:
        r.read_byte()    # allocated_client_slots
        splits = r.read_byte() & ~128
        for _ in range(splits):
            r.read_byte()  # playernum per seat
    else:
        # classic: player slot, high bit = spectator (no splitscreen here)
        pnum = r.read_byte()
        st.self_player = pnum & ~128

    r.read_string()      # level name

    if st.protocol_qw >= 25:
        for _ in range(10):  # movevars: gravity, stopspeed, maxspeed,
            r.read_float()    # spectatormaxspeed, accel, airaccel, wateraccel,
                              # friction, waterfriction, entgravity


# --------------------------------------------------------------------------- #
# usercmd delta (protocol_qw > 26 form: shorts)
# --------------------------------------------------------------------------- #
def parse_delta_usercmd(r: MsgReader, st: ParseState):
    bits = r.read_byte()
    if st.protocol_qw <= 26:
        if bits & CM_ANGLE1:
            r.read_short()
        r.read_short()              # angle2 always
        if bits & CM_ANGLE3:
            r.read_short()
        if bits & CM_FORWARD:
            r.read_byte()
        if bits & CM_SIDE:
            r.read_byte()
        if bits & CM_UP:
            r.read_byte()
        if bits & CM_BUTTONS:
            r.read_byte()
        if bits & CM_IMPULSE:
            r.read_byte()
        if bits & CM_ANGLE2:
            r.read_byte()
    else:
        if bits & CM_ANGLE1:
            raw = r.read_short() & 0xffff
            ang = raw * 360.0 / 65536.0
            if ang >= 180.0:
                ang -= 360.0
            st.last_pitch = ang
        if bits & CM_ANGLE2:
            raw = r.read_short() & 0xffff
            ang = raw * 360.0 / 65536.0
            if ang >= 180.0:
                ang -= 360.0
            st.last_yaw = ang
        if bits & CM_ANGLE3:
            r.read_short()
        if bits & CM_FORWARD:
            r.read_short()
        if bits & CM_SIDE:
            r.read_short()
        if bits & CM_UP:
            r.read_short()
        if bits & CM_BUTTONS:
            r.read_byte()
        if bits & CM_IMPULSE:
            r.read_byte()
        r.read_byte()               # msec always


# --------------------------------------------------------------------------- #
# client-POV svc_playerinfo (svc 42) -- CLQW_ParsePlayerinfo, non-MVD branch
# --------------------------------------------------------------------------- #
def parse_playerinfo(r: MsgReader, st: ParseState):
    num = r.read_byte()
    flags = r.read_ushort()

    if st.fte1 & FTE_HAS_EXTRA_PF_MASK:
        if flags & PF_EXTRA_PFS:
            flags |= r.read_byte() << 16
    else:
        flags = (flags & 0x3FFF) | ((flags & 0xC000) << 8)

    # origin (3 coords, always present)
    ox = r.read_player_coord()
    oy = r.read_player_coord()
    oz = r.read_player_coord()

    r.read_byte()  # frame

    if flags & PF_MSEC:
        r.read_byte()

    have_vel = False
    vx = vy = vz = 0.0
    if flags & PF_COMMAND:
        parse_delta_usercmd(r, st)

    for i in range(3):
        if flags & (PF_VELOCITY1 << i):
            v = r.read_short()
            if i == 0:
                vx = float(v)
            elif i == 1:
                vy = float(v)
            else:
                vz = float(v)
            have_vel = True

    if flags & PF_MODEL:
        r.read_byte()
    if flags & PF_SKINNUM:
        r.read_byte()
    if flags & PF_EFFECTS:
        r.read_byte()
    if flags & PF_WEAPONFRAME:
        r.read_byte()
        # ezQuake MVD_PEXT1_WEAPONPREDICTION block (mirrors CL_ParsePlayerinfo):
        # a gate byte; if non-zero, a fixed per-player prediction payload.
        if st.weapon_prediction:
            wep_predict = r.read_byte()
            if wep_predict:
                r.read_byte()    # impulse
                r.read_short()   # weapon
                r.read_float()   # client_time
                r.read_float()   # attack_finished
                r.read_float()   # client_nextthink
                r.read_byte()    # client_thinkindex
                r.read_byte()    # client_ping
                r.read_byte()    # client_predflags
                r.read_byte()    # ammo_shells
                r.read_byte()    # ammo_nails
                r.read_byte()    # ammo_rockets
                r.read_byte()    # ammo_cells

    # ezQuake reads alpha only for PF_TRANS_Z when FTE_PEXT_TRANS negotiated.
    if (flags & PF_TRANS_Z) and (st.fte1 & PEXT_TRANS):
        r.read_byte()

    if r.bad:
        return

    # Record the recorder's POV. self_player is from serverdata; the POV
    # playerinfo carries velocity (PF_COMMAND/PF_VELOCITY) -- non-POV players
    # in a 1-player demo are absent, so we accept the self slot (or any slot
    # that carries velocity, which in these solo RJ demos is the recorder).
    is_self = (st.self_player is None) or (num == st.self_player)
    if is_self:
        st.samples.append(
            (st.demotime, ox, oy, oz, vx, vy, vz, have_vel,
             st.last_pitch, st.last_yaw)
        )


# --------------------------------------------------------------------------- #
# entity delta parsing (classic QW packetentities, with FTE morebits)
# --------------------------------------------------------------------------- #
def parse_entity_delta_from_word(r: MsgReader, word: int, st: ParseState):
    """Parse one entity delta given its first 16-bit word, mirroring ezQuake
    CL_ParseDelta. Entity origins are float coords under MVD_PEXT1_FLOATCOORDS;
    angles are 1 byte (MSG_ReadAngle)."""
    bits = word & ~0x1FF
    if bits & U_MOREBITS:
        bits |= r.read_byte()
    morebits = 0
    if bits & U_FTE_EVENMORE:
        morebits = r.read_byte()
        if morebits & U_FTE_YETMORE:
            morebits |= r.read_byte() << 8

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
        r.read_player_coord()
    if bits & U_ANGLE1:
        r.read_angle()
    if bits & U_ORIGIN2:
        r.read_player_coord()
    if bits & U_ANGLE2:
        r.read_angle()
    if bits & U_ORIGIN3:
        r.read_player_coord()
    if bits & U_ANGLE3:
        r.read_angle()
    # U_SOLID carries no bytes here. FTE morebits fields:
    if morebits & U_FTE_TRANS:
        r.read_byte()
    if morebits & U_FTE_COLOURMOD:
        r.read_byte()
        r.read_byte()
        r.read_byte()
    if morebits & U_FTE_SCALE:
        r.read_byte()
    if morebits & U_FTE_FATNESS:
        r.read_char()


# kept for svc_fte_spawnbaseline2 / spawnstatic2 (entity-delta-shaped messages)
def parse_entity_bits(r: MsgReader):
    word = r.read_ushort()
    return word & 0x1FF, word, 0, 0


def parse_entity_delta(r: MsgReader, entnum_unused, word, _ym, st: ParseState):
    parse_entity_delta_from_word(r, word, st)


def parse_packet_entities(r: MsgReader, delta: bool, st: ParseState):
    if delta:
        r.read_byte()  # delta-from frame number
    while True:
        if r.remaining() < 2:
            r.bad = True
            return
        word = r.read_ushort()
        if r.bad:
            return
        if word == 0:
            break  # terminator
        parse_entity_delta_from_word(r, word, st)


def parse_packet_projectiles(r: MsgReader, st: ParseState):
    """svc_packetsprojectiles (svc 100, MVD_PEXT1_SIMPLEPROJECTILE): a long
    frame number, then (entnum short, sendflags short, fields) triples until
    entnum==0. Mirrors CL_ParsePacketSimpleProjectiles."""
    r.read_long()  # frame number
    while True:
        if r.remaining() < 2:
            r.bad = True
            return
        word = r.read_ushort()
        if r.bad:
            return
        if word == 0:
            break
        if word & 0x8000:
            continue  # removal, no fields
        sendflags = r.read_ushort()
        if sendflags & U_ORIGIN1:
            for _ in range(6):   # origin[3] + velocity[3], all floats
                r.read_float()
        if sendflags & U_ANGLE1:
            for _ in range(3):
                r.read_angle()
        if sendflags & U_MODEL:
            r.read_short()  # modelindex
            r.read_short()  # owner
        if sendflags & U_ORIGIN3:
            r.read_byte()   # time_offset


# --------------------------------------------------------------------------- #
# sound / temp ent / nails / stringlists
# --------------------------------------------------------------------------- #
def parse_sound(r: MsgReader, st: ParseState):
    channel = r.read_ushort()
    if channel & SND_VOLUME:
        r.read_byte()
    if channel & SND_ATTENUATION:
        r.read_byte()
    # FTE sound doubles: with SOUNDDBL the soundnum can be a short; classic byte.
    r.read_byte()  # soundnum (classic)
    for _ in range(3):
        r.read_coord()


def parse_temp_entity(r: MsgReader, st: ParseState):
    TE_SPIKE = 0
    TE_SUPERSPIKE = 1
    TE_GUNSHOT = 2
    TE_EXPLOSION = 3
    TE_TAREXPLOSION = 4
    TE_LIGHTNING1 = 5
    TE_LIGHTNING2 = 6
    TE_WIZSPIKE = 7
    TE_KNIGHTSPIKE = 8
    TE_LIGHTNING3 = 9
    TE_LAVASPLASH = 10
    TE_TELEPORT = 11
    TE_BLOOD = 12
    TE_LIGHTNINGBLOOD = 13
    t = r.read_byte()
    if t in (TE_GUNSHOT, TE_BLOOD):
        r.read_byte()  # count
        for _ in range(3):
            r.read_coord()
    elif t in (TE_LIGHTNING1, TE_LIGHTNING2, TE_LIGHTNING3):
        r.read_short()  # entity
        for _ in range(6):
            r.read_coord()
    else:
        # spike/explosion/teleport/etc: just a position
        for _ in range(3):
            r.read_coord()


def parse_nails(r: MsgReader, extended: bool):
    n = r.read_byte()
    for _ in range(n):
        if extended:
            r.read_byte()  # projectile number
        for _ in range(6):
            r.read_byte()


def parse_stringlist(r: MsgReader, extended: bool):
    if extended:
        r.read_short()
    else:
        r.read_byte()
    while True:
        s = r.read_string()
        if not s:
            break
    r.read_byte()  # next index


# --------------------------------------------------------------------------- #
# FTE csqcentities (sized = per-entity short length; non-sized = needs CSQC)
# --------------------------------------------------------------------------- #
def parse_csqc_entities(r: MsgReader, sized: bool, st: ParseState):
    if not sized:
        # Non-sized csqcentities cannot be skipped without the CSQC progs
        # (per-entity payload length is determined by CSQC_Ent_Update QC).
        raise QwdRjError(
            "svc_fte_csqcentities (non-sized, svc 76) cannot be parsed without "
            "CSQC progs"
        )
    while True:
        if r.remaining() < 2:
            r.bad = True
            return
        word = r.read_ushort()
        removeflag = bool(word & 0x8000)
        if st.fte2 & PEXT2_REPLACEMENTDELTAS:
            if word & 0x4000:
                entnum = (word & 0x3FFF) | (r.read_byte() << 14)
            else:
                entnum = word & ~0x8000
        else:
            entnum = word & ~0x8000
        if entnum == 0 and not removeflag:
            break
        if removeflag:
            continue
        size = r.read_ushort()
        # skip the entity payload
        r.pos += size
        if r.pos > len(r.data):
            r.bad = True
            return


# --------------------------------------------------------------------------- #
# net_message dispatcher
# --------------------------------------------------------------------------- #
def parse_net_message(payload: bytes, st: ParseState, file_offset: int):
    r = MsgReader(payload, st.big_coords, st.float_ent_coords)
    while not r.eof():
        cmd = r.read_byte()
        if cmd == -1:
            break
        cmd_off = r.pos - 1

        if cmd in (SVC_NOP, SVC_BAD):
            continue
        elif cmd == SVC_DISCONNECT:
            return
        elif cmd == SVC_UPDATESTAT:
            stat = r.read_byte()
            val = r.read_byte()
            st.stats[stat] = val
            st.stat_events.append((st.demotime, stat, val))
        elif cmd == SVC_UPDATESTATLONG:
            stat = r.read_byte()
            val = r.read_long()
            st.stats[stat] = val
            st.stat_events.append((st.demotime, stat, val))
        elif cmd == SVC_FTE_UPDATESTATSTRING:
            r.read_byte()
            r.read_string()
        elif cmd == SVC_FTE_UPDATESTATFLOAT:
            r.read_byte()
            r.read_float()
        elif cmd == SVC_SETVIEW:
            st.viewentity = r.read_short()
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
            r.read_byte()   # armor
            r.read_byte()   # blood
            for _ in range(3):
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
        elif cmd == SVC_FTE_SOUNDLISTSHORT:
            parse_stringlist(r, extended=True)
        elif cmd == SVC_SPAWNSTATICSOUND:
            for _ in range(3):
                r.read_coord()
            r.read_byte()
            r.read_byte()
            r.read_byte()
        elif cmd == SVC_FTE_SPAWNSTATICSOUND2:
            for _ in range(3):
                r.read_coord()
            r.read_short()  # soundindex
            r.read_byte()
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
            en, b, mb, ym = parse_entity_bits(r)
            parse_entity_delta(r, b, mb, ym, st)
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
            en, b, mb, ym = parse_entity_bits(r)
            parse_entity_delta(r, b, mb, ym, st)
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
            r.read_byte()
            r.read_long()
            r.read_string()
        elif cmd == SVC_LIGHTSTYLE:
            r.read_byte()
            r.read_string()
        elif cmd == SVC_FTE_LIGHTSTYLECOL:
            r.read_byte()
            r.read_byte()   # colour bits
            r.read_string()
        elif cmd == SVC_SERVERINFO:
            r.read_string()
            r.read_string()
        elif cmd == SVC_SETINFO:
            r.read_byte()
            r.read_string()
            r.read_string()
        elif cmd == SVC_FTE_SETINFOBLOB:
            # [byte index][string key][long flags/offset][short size][data]
            r.read_byte()
            r.read_string()
            r.read_long()
            size = r.read_ushort()
            r.pos += size
        elif cmd == SVC_PACKETENTITIES:
            parse_packet_entities(r, delta=False, st=st)
        elif cmd == SVC_DELTAPACKETENTITIES:
            parse_packet_entities(r, delta=True, st=st)
        elif cmd == SVC_PACKETSPROJECTILES:
            parse_packet_projectiles(r, st)
        elif cmd == SVC_SOUND:
            parse_sound(r, st)
        elif cmd == SVC_STOPSOUND:
            r.read_short()
        elif cmd == SVC_TEMP_ENTITY:
            parse_temp_entity(r, st)
        elif cmd == SVC_SETANGLE:
            r.read_byte()
            for _ in range(3):
                r.read_angle()
        elif cmd == SVC_MUZZLEFLASH:
            r.read_short()
        elif cmd == SVC_SMALLKICK or cmd == SVC_BIGKICK:
            pass
        elif cmd == SVC_INTERMISSION:
            for _ in range(3):
                r.read_coord()
            for _ in range(3):
                r.read_angle()
        elif cmd == SVC_FINALE:
            r.read_string()
        elif cmd == SVC_SELLSCREEN:
            pass
        elif cmd == SVC_CHOKECOUNT:
            r.read_byte()
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
        elif cmd == SVC_DOWNLOAD:
            size = r.read_short()
            r.read_byte()  # percent
            if size > 0:
                r.pos += size
        elif cmd == SVC_FTE_EFFECT:
            for _ in range(3):
                r.read_coord()
            r.read_byte()  # modelindex
            r.read_byte()  # startframe
            r.read_byte()  # framecount
            r.read_byte()  # framerate
        elif cmd == SVC_FTE_EFFECT2:
            for _ in range(3):
                r.read_coord()
            r.read_short()  # modelindex
            r.read_short()  # startframe
            r.read_byte()
            r.read_byte()
        elif cmd == SVC_FTE_TRAILPARTICLES:
            r.read_short()  # entnum
            r.read_short()  # effectnum
            for _ in range(6):
                r.read_coord()
        elif cmd == SVC_FTE_POINTPARTICLES:
            r.read_short()  # effectnum
            for _ in range(3):
                r.read_coord()
            for _ in range(3):
                r.read_coord()
            r.read_short()  # count
        elif cmd == SVC_FTE_POINTPARTICLES1:
            r.read_short()
            for _ in range(3):
                r.read_coord()
        elif cmd == SVC_FTE_CSQCENTITIES:
            parse_csqc_entities(r, sized=False, st=st)
        elif cmd == SVC_FTE_CSQCENTITIES_SIZED:
            parse_csqc_entities(r, sized=True, st=st)
        elif cmd == SVC_FTE_CGAMEPACKET_SIZED:
            size = r.read_short()
            r.pos += size
        elif cmd == SVC_FTE_VOICECHAT:
            r.read_byte()   # sender
            r.read_byte()   # gen
            r.read_byte()   # seq
            length = r.read_short()
            r.pos += length
        else:
            raise QwdRjError(
                f"Unhandled svc command {cmd} at byte {cmd_off} of net_message "
                f"(payload len {len(payload)}, file_offset ~{file_offset})"
            )

        if r.bad:
            # Ran off the end of this payload mid-command; the next block
            # length-prefix re-syncs us, so stop this message cleanly.
            break


# --------------------------------------------------------------------------- #
# top-level QWD walk
# --------------------------------------------------------------------------- #
def parse_qwd(data: bytes) -> ParseState:
    st = ParseState()
    pos = 0
    n = len(data)
    while pos + 5 <= n:
        block_off = pos
        demotime = struct.unpack_from("<f", data, pos)[0]
        raw_type = data[pos + 4]
        pos += 5
        st.demotime = demotime
        mtype = raw_type & 7

        if mtype == DEM_CMD:
            need = DEM_CMD_USERCMD_SIZE + DEM_CMD_VIEWANGLE_SIZE
            if pos + need > n:
                break
            pos += need
            continue
        if mtype == DEM_SET:
            pos += 8
            continue
        if mtype == DEM_MULTIPLE:
            if pos + 4 > n:
                break
            pos += 4  # player bitmask
        # dem_read / single / stats / all / (multiple fell through): length + payload
        if pos + 4 > n:
            break
        length = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        if length < 0 or pos + length > n:
            break
        payload = data[pos:pos + length]
        pos += length
        st.last_good_offset = pos
        # payload = [8-byte netchan seq header][svc stream]
        if len(payload) >= 8:
            parse_net_message(payload[8:], st, file_offset=block_off)
    return st


# --------------------------------------------------------------------------- #
# RJ segmentation + reporting
# --------------------------------------------------------------------------- #
RA_POS = (-320.0, 480.0, 448.0)       # aerowalk Red Armor world position
RA_XY_RADIUS = 64.0
RA_Z_TOL = 40.0

LAUNCH_VZ = 250.0     # qu/s rising edge that marks an RJ launch
LAND_VZ = 30.0        # |vz| below this (with some hysteresis) -> landed
# Each pre-war rocket self-hit writes one STAT_AMMO spike, so we anchor one
# attempt per spike and locate its launch + apex in a window around it.
ATTEMPT_PRE = 0.35    # s; look this far before the ammo spike for takeoff
ATTEMPT_POST = 1.60   # s; track the flight this far after the spike for apex/RA
MIN_LAUNCH_VZ = 150.0  # qu/s; a real RJ launch peak; below this is a spawn/no-jump


def reached_ra(x, y, z):
    dxy = math.hypot(x - RA_POS[0], y - RA_POS[1])
    return dxy <= RA_XY_RADIUS and abs(z - RA_POS[2]) <= RA_Z_TOL


def derive_velocity(samples):
    """Return list of (t, x, y, z, vx, vy, vz) using sent velocity when present,
    else finite-differenced origin."""
    out = []
    for i, s in enumerate(samples):
        t, x, y, z, vx, vy, vz, have_vel = s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7]
        if not have_vel and i > 0:
            tp, xp, yp, zp = samples[i - 1][0], samples[i - 1][1], samples[i - 1][2], samples[i - 1][3]
            dt = t - tp
            if dt > 0:
                vx = (x - xp) / dt
                vy = (y - yp) / dt
                vz = (z - zp) / dt
        out.append((t, x, y, z, vx, vy, vz))
    return out


def segment_attempts(samples, stat_events):
    """Segment RJ attempts and report per-attempt self-damage.

    Each pre-war rocket self-hit produces exactly one STAT_AMMO spike
    (currentammo = 1000 + damage), so we anchor one attempt per spike. For each
    spike we scan the velocity track in a window around it to find the launch
    (vz rising edge) and the flight apex / RA pass-through. The spike value
    minus 1000 is the attempt's self-damage. Spikes whose window shows no real
    upward launch (peak vz < MIN_LAUNCH_VZ, e.g. the spawn-time ammo value) are
    dropped as non-jumps.
    """
    track = derive_velocity(samples)
    if len(track) < 3:
        return []

    times = [p[0] for p in track]

    # STAT_AMMO spikes (value >= 1000 -> pre-war damage display)
    ammo_spikes = sorted(
        (t, val - AMMO_DAMAGE_BASE)
        for (t, stat, val) in stat_events
        if stat == STAT_AMMO and val >= AMMO_DAMAGE_BASE
    )

    def window_slice(t0, t1):
        import bisect
        lo = bisect.bisect_left(times, t0)
        hi = bisect.bisect_right(times, t1)
        return track[lo:hi]

    attempts = []
    n = 0
    for (at, dmg) in ammo_spikes:
        seg = window_slice(at - ATTEMPT_PRE, at + ATTEMPT_POST)
        if not seg:
            continue

        # launch = peak vz in the early part of the window (takeoff phase)
        takeoff = window_slice(at - ATTEMPT_PRE, at + 0.5) or seg
        peak_vz = max(p[6] for p in takeoff)
        # locate the launch time (first sample at/above the peak in takeoff)
        t_launch = at
        for p in takeoff:
            if p[6] >= peak_vz - 1e-6:
                t_launch = p[0]
                break

        # apex height + RA pass-through across the full flight window
        max_z = max(p[3] for p in seg)
        ra_hit = any(reached_ra(p[1], p[2], p[3]) for p in seg)

        # drop non-jumps (spawn ammo value, idle hits): require a real launch.
        if peak_vz < MIN_LAUNCH_VZ:
            continue

        n += 1
        attempts.append({
            "attempt": n,
            "time_s": round(t_launch, 3),
            "self_damage": round(dmg),
            "max_z": round(max_z, 1),
            "reached_RA": bool(ra_hit),
            "peak_launch_vz": round(peak_vz, 1),
            "ammo_spike_t": round(at, 3),
        })
    return attempts


# --------------------------------------------------------------------------- #
# Trace export (successful RJ jump windows for the FragBot puppet seam)
# --------------------------------------------------------------------------- #
EXPORT_PRE = 0.3      # s before launch to start a trace
EXPORT_POST = 1.6     # s after launch to end a trace


def export_traces(st: ParseState, demo_label: str, name_prefix: str):
    """For each SUCCESSFUL attempt (reached_RA), slice the per-frame samples from
    (launch - 0.3s) to (launch + 1.6s) into a trace of
    [msec, ox,oy,oz, vx,vy,vz, pitch, yaw] frames. msec is the per-frame demo-time
    delta in ms; origins/velocities are the (velocity-derived) floats; angles deg.
    """
    import bisect

    attempts = segment_attempts(st.samples, st.stat_events)
    track = derive_velocity(st.samples)        # [(t,x,y,z,vx,vy,vz), ...]
    times = [p[0] for p in track]

    traces = []
    idx = 0
    for a in attempts:
        if not a["reached_RA"]:
            continue
        idx += 1
        t_launch = a["time_s"]
        lo = bisect.bisect_left(times, t_launch - EXPORT_PRE)
        hi = bisect.bisect_right(times, t_launch + EXPORT_POST)
        win = list(range(lo, hi))
        if not win:
            continue

        frames = []
        prev_t = None
        for si in win:
            t = track[si][0]
            x, y, z = track[si][1], track[si][2], track[si][3]
            vx, vy, vz = track[si][4], track[si][5], track[si][6]
            # angles live on the raw sample tuple at indices 8,9
            pitch = st.samples[si][8]
            yaw = st.samples[si][9]
            if prev_t is None:
                msec = 13     # nominal first-frame delta (~77Hz)
            else:
                msec = int(round((t - prev_t) * 1000.0))
                if msec <= 0:
                    msec = 1
            prev_t = t
            frames.append([
                msec,
                float(x), float(y), float(z),
                float(vx), float(vy), float(vz),
                float(pitch), float(yaw),
            ])

        traces.append({
            "name": f"{name_prefix}_{idx}",
            "demo": demo_label,
            "self_damage": a["self_damage"],
            "frames": frames,
        })
    return traces


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def report(path, st: ParseState):
    attempts = segment_attempts(st.samples, st.stat_events)
    n_ra = sum(1 for a in attempts if a["reached_RA"])
    dmgs = [a["self_damage"] for a in attempts if a["self_damage"] is not None]
    dmg_lo = min(dmgs) if dmgs else None
    dmg_hi = max(dmgs) if dmgs else None

    summary = {
        "file": path,
        "pov_samples": len(st.samples),
        "stat_ammo_events": sum(1 for (_, s, _) in st.stat_events if s == STAT_AMMO),
        "attempts": len(attempts),
        "reached_RA": n_ra,
        "damage_range": [dmg_lo, dmg_hi],
        "per_attempt": attempts,
        "float_ent_coords": st.float_ent_coords,
        "self_player": st.self_player,
    }

    md = []
    md.append(f"## {path}")
    md.append("")
    md.append(
        f"**{len(attempts)} attempts, {n_ra} reached RA, "
        f"damage range {dmg_lo}-{dmg_hi}** "
        f"(POV samples: {len(st.samples)}, ammo events: {summary['stat_ammo_events']})"
    )
    md.append("")
    md.append("| # | time (s) | self-dmg | max Z | reached RA | peak vz |")
    md.append("| --- | --- | --- | --- | --- | --- |")
    for a in attempts:
        md.append(
            f"| {a['attempt']} | {a['time_s']} | "
            f"{a['self_damage'] if a['self_damage'] is not None else '-'} | "
            f"{a['max_z']} | {'yes' if a['reached_RA'] else 'no'} | "
            f"{a['peak_launch_vz']} |"
        )
    md.append("")
    return "\n".join(md), summary


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Rocket-jump analyzer for QuakeWorld client .qwd demos."
    )
    ap.add_argument("demo", help="Path to a first-person QuakeWorld .qwd demo")
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    ap.add_argument(
        "--export", metavar="OUT.json",
        help="Export successful-RJ jump-window traces (puppet seam input) to JSON",
    )
    args = ap.parse_args(argv)

    with open(args.demo, "rb") as f:
        data = f.read()

    st = parse_qwd(data)

    if args.export:
        import os
        stem = os.path.splitext(os.path.basename(args.demo))[0]
        prefix = stem[3:] if stem.startswith("rj_") else stem
        traces = export_traces(st, demo_label=stem, name_prefix=prefix)
        with open(args.export, "w") as f:
            json.dump({"traces": traces}, f, indent=2)
        print(
            f"{args.demo}: exported {len(traces)} successful trace(s) -> "
            f"{args.export}"
        )
        return 0

    md, summary = report(args.demo, st)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(md)
        print()
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

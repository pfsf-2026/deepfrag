#!/usr/bin/env python3
"""FragBot REPLAY seam generator — PUPPET + armed/invuln + fire + jump sound,
STRINGING multiple human trick demos into one looping sequence.

Drives the bot along each human's exact recorded path (setorigin+vel+view per
frame; input-replay drifts). Concatenates several (.cmds,.qwd) routes — setorigin
teleports between them, so it performs trick after trick, then loops. Each frame:
gives all weapons + tops ammo + invuln (survives self-RL/fall), replays the human
attack + weapon impulse (RL/LG jumps fire), and plays the jump sound on the
human's jump-button rising edge (puppet skips the engine's jump, so we emit it).

Usage: gen_replay_seam.py <out_seam.c> <MODE_INT> <cmds1> <demo1> [<cmds2> <demo2> ...]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qwd"))
import qwd_usercmd as q

out_path, mode = sys.argv[1], int(sys.argv[2])
pairs = list(zip(sys.argv[3::2], sys.argv[4::2]))
def fl(x): return repr(float(x)) + "f"
rows = []
segs = []
for cmds_path, demo in pairs:
    cmds = [l.split() for l in open(cmds_path) if l.strip() and not l.startswith("#")]
    uc = q.parse_qwd_path(Path(demo)).commands
    n = min(len(cmds), len(uc))
    for i in range(n):
        c = cmds[i]; b = int(c[13])
        rows.append((c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8],
                     1 if b & 1 else 0, int(uc[i].impulse), 1 if b & 2 else 0))
    segs.append((Path(demo).stem, n))
N = len(rows)
arr = ",\n".join("  {%s,%d,%d,%d}" % (",".join(fl(v) for v in r[:8]), r[8], r[9], r[10]) for r in rows)
seglist = " + ".join(f"{name}({n})" for name, n in segs)

seam = f"""/* FragBot REPLAY seam (generated). Puppet playback of strung human .qwd tricks:
 * {seglist}. setorigin+vel+view each frame; teleports between routes; armed +
 * invuln; replays fire+impulse; emits jump sound on jump rising edge; loops. */

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_REPLAY_MODE {mode}
#define FRAGBOT_REPLAY_FRAMES {N}
/* per frame: ox oy oz vx vy vz pitch yaw  attack impulse jump */
static const float fragbot_replay[FRAGBOT_REPLAY_FRAMES][11] = {{
{arr}
}};
static int fragbot_rframe[MAX_CLIENTS];
static int fragbot_lastjump[MAX_CLIENTS];

static void FragBot_Replay(gedict_t *self, vec3_t direction, qbool *jumping,
                           qbool *firing, int *impulse_out)
{{
	int slot = NUM_FOR_EDICT(self) - 1;
	int f, jmp;
	vec3_t o, v;
	if (slot < 0 || slot >= MAX_CLIENTS) return;
	f = fragbot_rframe[slot];
	if (f < 0 || f >= FRAGBOT_REPLAY_FRAMES) {{ f = 0; fragbot_lastjump[slot] = 0; }}

	self->s.v.items = ((int) self->s.v.items) | 127;          /* all weapons */
	self->s.v.ammo_shells = 200; self->s.v.ammo_nails = 200;
	self->s.v.ammo_rockets = 100; self->s.v.ammo_cells = 200;
	self->s.v.health = 1000; self->s.v.takedamage = DAMAGE_NO; /* invulnerable */

	o[0] = fragbot_replay[f][0]; o[1] = fragbot_replay[f][1]; o[2] = fragbot_replay[f][2];
	v[0] = fragbot_replay[f][3]; v[1] = fragbot_replay[f][4]; v[2] = fragbot_replay[f][5];
	setorigin(self, PASSVEC3(o));
	VectorCopy(v, self->s.v.velocity);
	self->fb.desired_angle[PITCH] = fragbot_replay[f][6];
	self->fb.desired_angle[YAW]   = fragbot_replay[f][7];
	self->fb.desired_angle[ROLL]  = 0;

	jmp = (int) fragbot_replay[f][10];
	if (jmp && !fragbot_lastjump[slot])
		sound(self, CHAN_BODY, "player/plyrjmp8.wav", 1, ATTN_NORM);  /* jump sound */
	fragbot_lastjump[slot] = jmp;

	VectorClear(direction);
	*jumping = false;
	*firing  = (fragbot_replay[f][8] != 0.0f) ? true : false;
	*impulse_out = (int) fragbot_replay[f][9];
	fragbot_rframe[slot] = f + 1;
}}
/* ===== /FRAGBOT_BLOCK ===== */

/* ===== FRAGBOT_CALL ===== */
	if ((int) cvar("k_fb_fragbot_mode") == FRAGBOT_REPLAY_MODE && !ISDEAD(self)
	    && !(match_in_progress != 2 && cvar(FB_CVAR_FREEZE_PREWAR)))
	{{
		FragBot_Replay(self, direction, &jumping, &firing, &impulse);
	}}
/* ===== /FRAGBOT_CALL ===== */
"""
open(out_path, "w").write(seam)
print(f"wrote {out_path}: {N} frames | {seglist}")

#!/usr/bin/env python3
"""FragBot REPLAY seam generator (PUPPET + armed + invuln + fire).

Drives the bot along the human's exact recorded path (setorigin + velocity + view
each frame — open-loop input-replay drifts on chaotic air-strafe). Each frame it
also: gives ALL weapons + tops ammo + makes the bot invulnerable (so it survives
self-RL/fall damage and loops forever), and replays the human's ATTACK button +
weapon-select IMPULSE so the RL/LG jumps actually fire. Movement+weapon playback
of a human trace; no movement-brain logic.

Inputs: <in.cmds> (msec ox oy oz vx vy vz pitch yaw roll fwd side up buttons) and
the source <demo.qwd> (for per-frame impulse). Aligned 1:1 by index (verified).
Usage: gen_replay_seam.py <in.cmds> <out_seam.c> <MODE_INT> <demo.qwd>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qwd"))
import qwd_usercmd as q

cmds_path, out_path, mode, demo = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
cmds = [l.split() for l in open(cmds_path) if l.strip() and not l.startswith("#")]
uc = q.parse_qwd_path(Path(demo)).commands
n = min(len(cmds), len(uc))
def fl(x): return repr(float(x)) + "f"
rows = []
for i in range(n):
    c = cmds[i]
    ox, oy, oz = c[1:4]; vx, vy, vz = c[4:7]; pitch, yaw = c[7], c[8]
    attack = 1 if (int(c[13]) & 1) else 0
    impulse = int(uc[i].impulse)
    rows.append((ox, oy, oz, vx, vy, vz, pitch, yaw, attack, impulse))
arr = ",\n".join("  {%s,%d,%d}" % (",".join(fl(v) for v in r[:8]), r[8], r[9]) for r in rows)

seam = f"""/* FragBot REPLAY seam (generated — do not hand-edit). Puppet playback of a human
 * .qwd trace: setorigin+velocity+view to the human's exact path each frame; gives
 * all weapons + invuln so it survives + loops; replays attack+impulse so RL/LG
 * jumps fire. Movement + weapon playback only. */

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_REPLAY_MODE {mode}
#define FRAGBOT_REPLAY_FRAMES {n}
/* per frame: ox oy oz vx vy vz pitch yaw  attack(int) impulse(int) */
static const float fragbot_replay[FRAGBOT_REPLAY_FRAMES][10] = {{
{arr}
}};
static int fragbot_rframe[MAX_CLIENTS];

static void FragBot_Replay(gedict_t *self, vec3_t direction, qbool *jumping,
                           qbool *firing, int *impulse_out)
{{
	int slot = NUM_FOR_EDICT(self) - 1;
	int f;
	vec3_t o, v;
	if (slot < 0 || slot >= MAX_CLIENTS) return;
	f = fragbot_rframe[slot];
	if (f < 0 || f >= FRAGBOT_REPLAY_FRAMES) f = 0;   /* loop the trick */

	/* arm + make invulnerable every frame: all 7 weapons, full ammo, no damage,
	 * so self-RL / fall damage never kills it and it loops forever. */
	self->s.v.items = ((int) self->s.v.items) | 127;
	self->s.v.ammo_shells = 200; self->s.v.ammo_nails = 200;
	self->s.v.ammo_rockets = 100; self->s.v.ammo_cells = 200;
	self->s.v.health = 1000; self->s.v.takedamage = DAMAGE_NO;

	/* puppet to the human's exact path */
	o[0] = fragbot_replay[f][0]; o[1] = fragbot_replay[f][1]; o[2] = fragbot_replay[f][2];
	v[0] = fragbot_replay[f][3]; v[1] = fragbot_replay[f][4]; v[2] = fragbot_replay[f][5];
	setorigin(self, PASSVEC3(o));
	VectorCopy(v, self->s.v.velocity);
	self->fb.desired_angle[PITCH] = fragbot_replay[f][6];
	self->fb.desired_angle[YAW]   = fragbot_replay[f][7];
	self->fb.desired_angle[ROLL]  = 0;

	/* replay the human's fire + weapon-select so the RL/LG jumps actually fire */
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
print(f"wrote {out_path}: {n} frames (puppet + armed/invuln + fire/impulse)")

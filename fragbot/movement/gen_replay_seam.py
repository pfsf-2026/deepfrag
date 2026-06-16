#!/usr/bin/env python3
"""FragBot REPLAY seam generator — MULTI-MAP puppet playback.

Reads a JSON config {map: [[cmds, demo], ...]} and emits per-map trace arrays plus
a dispatch keyed on `mapname`, so the bot auto-plays the right map's tricks on map
load. Per map, several human .qwd routes are strung (setorigin teleports between).
Each frame the bot is puppeted to the human's exact origin+velocity+view, given all
weapons + ammo + invuln (loops forever), replays attack+weapon impulse (RL/LG jumps
fire), plays the jump sound on jump rising edge, and sets the model angles so the
body leans/faces correctly in 3rd person (not a stick figure).

Usage: gen_replay_seam.py <out_seam.c> <MODE_INT> <config.json>
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qwd"))
import qwd_usercmd as q

out_path, mode, cfg_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
cfg = json.load(open(cfg_path))
def fl(x): return repr(float(x)) + "f"

def build_rows(pairs):
    rows = []
    for cmds_path, demo in pairs:
        cmds = [l.split() for l in open(cmds_path) if l.strip() and not l.startswith("#")]
        uc = q.parse_qwd_path(Path(demo)).commands
        for i in range(min(len(cmds), len(uc))):
            c = cmds[i]; b = int(c[13])
            rows.append((c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8],
                         1 if b & 1 else 0, int(uc[i].impulse), 1 if b & 2 else 0))
    return rows

arrays, dispatch, summary = [], [], []
for mp, pairs in cfg.items():
    rows = build_rows(pairs)
    n = len(rows)
    arr = ",\n".join("  {%s,%d,%d,%d}" % (",".join(fl(v) for v in r[:8]), r[8], r[9], r[10]) for r in rows)
    arrays.append(f"#define FRAGBOT_N_{mp} {n}\nstatic const float fragbot_replay_{mp}[FRAGBOT_N_{mp}][11] = {{\n{arr}\n}};")
    dispatch.append(f'\tif (streq(mapname, "{mp}")) {{ *count = FRAGBOT_N_{mp}; return fragbot_replay_{mp}; }}')
    summary.append(f"{mp}({n})")

seam = f"""/* FragBot REPLAY seam (generated). Multi-map puppet playback: {' '.join(summary)}.
 * Auto-dispatches by mapname; puppets origin+vel+view; armed+invuln; replays
 * fire+impulse; jump sound; sets model angles for a non-stick-figure body. */

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_REPLAY_MODE {mode}
{chr(10).join(arrays)}
static int fragbot_rframe[MAX_CLIENTS];
static int fragbot_lastjump[MAX_CLIENTS];

static const float (*FragBot_TraceForMap(int *count))[11]
{{
{chr(10).join(dispatch)}
	*count = 0;
	return (const float (*)[11]) 0;
}}

static void FragBot_Replay(gedict_t *self, vec3_t direction, qbool *jumping,
                           qbool *firing, int *impulse_out)
{{
	int slot = NUM_FOR_EDICT(self) - 1;
	int f, count, jmp;
	const float (*tr)[11];
	vec3_t o, v;
	if (slot < 0 || slot >= MAX_CLIENTS) return;
	tr = FragBot_TraceForMap(&count);
	if (!tr || count <= 0) return;          /* no tricks for this map -> stock bot */
	f = fragbot_rframe[slot];
	if (f < 0 || f >= count) {{ f = 0; fragbot_lastjump[slot] = 0; }}

	self->s.v.items = ((int) self->s.v.items) | 127;
	self->s.v.ammo_shells = 200; self->s.v.ammo_nails = 200;
	self->s.v.ammo_rockets = 100; self->s.v.ammo_cells = 200;
	self->s.v.health = 1000; self->s.v.takedamage = DAMAGE_NO;

	o[0] = tr[f][0]; o[1] = tr[f][1]; o[2] = tr[f][2];
	v[0] = tr[f][3]; v[1] = tr[f][4]; v[2] = tr[f][5];
	setorigin(self, PASSVEC3(o));
	VectorCopy(v, self->s.v.velocity);
	/* cmd view (POV) */
	self->fb.desired_angle[PITCH] = tr[f][6];
	self->fb.desired_angle[YAW]   = tr[f][7];
	self->fb.desired_angle[ROLL]  = 0;
	/* model angles (3rd-person body lean/facing) */
	self->s.v.angles[0] = tr[f][6];
	self->s.v.angles[1] = tr[f][7];
	self->s.v.angles[2] = 0;

	jmp = (int) tr[f][10];
	if (jmp && !fragbot_lastjump[slot])
		sound(self, CHAN_BODY, "player/plyrjmp8.wav", 1, ATTN_NORM);
	fragbot_lastjump[slot] = jmp;

	VectorClear(direction);
	*jumping = false;
	*firing  = (tr[f][8] != 0.0f) ? true : false;
	*impulse_out = (int) tr[f][9];
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
print(f"wrote {out_path}: {' '.join(summary)}")

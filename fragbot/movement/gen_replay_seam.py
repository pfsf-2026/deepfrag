#!/usr/bin/env python3
"""FragBot REPLAY seam generator — multi-map puppet playback with auto-rotation.

JSON config {map: [[cmds,demo],...]} -> per-map trace arrays + a mapname dispatch.
Each frame the bot is puppeted to the human's exact origin+velocity+view, armed +
invuln, replays attack+weapon impulse (RL/LG fire), sets model angles (3rd-person
lean), and plays the jump sound on the actual upward LAUNCH (vz crossing positive,
so it's aligned with takeoff, not the button). Runs each map's tricks TWICE then
changelevels to the next map in the config order. Per-map state resets on load.

Usage: gen_replay_seam.py <out_seam.c> <MODE_INT> <config.json>
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qwd"))
import qwd_usercmd as q

out_path, mode, cfg_path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
cfg = json.load(open(cfg_path))
maps = list(cfg.keys())
def fl(x): return repr(float(x)) + "f"

def build_rows(pairs):
    rows = []
    for cmds_path, demo in pairs:
        cmds = [l.split() for l in open(cmds_path) if l.strip() and not l.startswith("#")]
        uc = q.parse_qwd_path(Path(demo)).commands
        for i in range(min(len(cmds), len(uc))):
            c = cmds[i]; b = int(c[13])
            rows.append((c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8],
                         1 if b & 1 else 0, int(uc[i].impulse)))
    return rows

arrays, dispatch, nextmap, summary = [], [], [], []
for idx, mp in enumerate(maps):
    rows = build_rows(cfg[mp]); n = len(rows)
    arr = ",\n".join("  {%s,%d,%d}" % (",".join(fl(v) for v in r[:8]), r[8], r[9]) for r in rows)
    arrays.append(f"#define FRAGBOT_N_{mp} {n}\nstatic const float fragbot_replay_{mp}[FRAGBOT_N_{mp}][10] = {{\n{arr}\n}};")
    dispatch.append(f'\tif (streq(mapname, "{mp}")) {{ *count = FRAGBOT_N_{mp}; return fragbot_replay_{mp}; }}')
    nextmap.append(f'\tif (streq(mapname, "{mp}")) return "{maps[(idx + 1) % len(maps)]}";')
    summary.append(f"{mp}({n})")

seam = f"""/* FragBot REPLAY seam (generated). Multi-map puppet playback w/ auto-rotation:
 * {' '.join(summary)}. Puppets origin+vel+view; armed+invuln; fire+impulse; jump
 * sound on launch; model lean; 2 loops per map then changelevels to the next. */

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_REPLAY_MODE {mode}
#define FRAGBOT_LOOPS_PER_MAP 2
{chr(10).join(arrays)}
static int   fragbot_rframe[MAX_CLIENTS];
static int   fragbot_loops[MAX_CLIENTS];
static float fragbot_lastvz[MAX_CLIENTS];
static char  fragbot_lastmap[64];

static const float (*FragBot_TraceForMap(int *count))[10]
{{
{chr(10).join(dispatch)}
	*count = 0; return (const float (*)[10]) 0;
}}
static char *FragBot_NextMap(void)
{{
{chr(10).join(nextmap)}
	return "{maps[0]}";
}}

static void FragBot_Replay(gedict_t *self, vec3_t direction, qbool *jumping,
                           qbool *firing, int *impulse_out)
{{
	int slot = NUM_FOR_EDICT(self) - 1;
	int f, count, k;
	float vz;
	const float (*tr)[10];
	vec3_t o, v;
	if (slot < 0 || slot >= MAX_CLIENTS) return;

	/* reset all per-slot replay state when the map changes */
	if (!streq(fragbot_lastmap, mapname)) {{
		for (k = 0; k < MAX_CLIENTS; k++) {{ fragbot_rframe[k] = 0; fragbot_loops[k] = 0; fragbot_lastvz[k] = 0; }}
		strlcpy(fragbot_lastmap, mapname, sizeof(fragbot_lastmap));
	}}
	tr = FragBot_TraceForMap(&count);
	if (!tr || count <= 0) return;
	if (fragbot_loops[slot] < 0) return;            /* map change pending */
	f = fragbot_rframe[slot];
	if (f >= count) {{                                /* finished a loop */
		fragbot_loops[slot] += 1;
		if (fragbot_loops[slot] >= FRAGBOT_LOOPS_PER_MAP) {{
			fragbot_loops[slot] = -1;
			changelevel(FragBot_NextMap());
			return;
		}}
		f = 0; fragbot_lastvz[slot] = 0;
	}}
	if (f < 0) f = 0;

	self->s.v.items = ((int) self->s.v.items) | 127;
	self->s.v.ammo_shells = 200; self->s.v.ammo_nails = 200;
	self->s.v.ammo_rockets = 100; self->s.v.ammo_cells = 200;
	self->s.v.health = 1000; self->s.v.takedamage = DAMAGE_NO;

	o[0] = tr[f][0]; o[1] = tr[f][1]; o[2] = tr[f][2];
	v[0] = tr[f][3]; v[1] = tr[f][4]; v[2] = tr[f][5];
	setorigin(self, PASSVEC3(o));
	VectorCopy(v, self->s.v.velocity);
	self->fb.desired_angle[PITCH] = tr[f][6];
	self->fb.desired_angle[YAW]   = tr[f][7];
	self->fb.desired_angle[ROLL]  = 0;
	self->s.v.angles[0] = tr[f][6];
	self->s.v.angles[1] = tr[f][7];
	self->s.v.angles[2] = 0;

	/* jump sound on the actual upward LAUNCH (aligned with takeoff) */
	vz = tr[f][5];
	if (vz > 150.0f && fragbot_lastvz[slot] <= 150.0f)
		sound(self, CHAN_BODY, "player/plyrjmp8.wav", 1, ATTN_NORM);
	fragbot_lastvz[slot] = vz;

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
print(f"wrote {out_path}: {' '.join(summary)} | rotate 2x/map")

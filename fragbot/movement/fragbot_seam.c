/* FragBot coupled air-strafe — deployable seam for the dusty-qw KTX fork.
 * Injected into src/bot_movement.c by deploy/inject_and_build.py:
 *   (A) FRAGBOT_BLOCK -> pasted before `void BotSetCommand` (state + function)
 *   (B) FRAGBOT_CALL  -> pasted right before
 *        `trap_makevectors(self->fb.desired_angle);` in BotSetCommand()
 *
 * DESIGN (v2 — navigation-preserving):
 * We set ONLY the view (a smooth triangle-wave weave around the frogbot's own
 * nav heading) and request a jump. We do NOT touch the move vector — the stock
 * code right after our hook projects the frogbot's wall-aware path (dir_move_)
 * into OUR weaving view frame, so the bot still follows the path / avoids walls,
 * but executes it as an air-strafe with a weaving view => view & heading rotate
 * together = human-like coupling. Smooth ramp (not a 2-position toggle) fixes the
 * snap-snap. Bunnyhop needs pm_ktjump 1 (auto-hop on held jump).
 * Self-contained; uses only stock KTX/frogbot fields. No komodo dependency. */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);
//
// Second injection: disable ezcsqc on this lab build so bots are VISIBLE. KTX
// 1.48 added a per-client CSQC handshake bots can't complete -> bots render
// invisible on ezcsqc servers. The lab only needs to watch movement, so advertise
// qwm_ezcsqc 0 -> standard rendering. (Fleet keeps stock ezcsqc.)
// FRAGBOT_FILE2: g_main.c
// FRAGBOT_ANCHOR2: sv_extensions = cvar("sv_mod_extensions");

/* ===== FRAGBOT_CALL2 ===== */
	cvar_set("qwm_ezcsqc", "0"); /* FragBot lab: standard rendering so bots are visible */
/* ===== /FRAGBOT_CALL2 ===== */

/* ===== FRAGBOT_BLOCK ===== */
static float fragbot_phase[MAX_CLIENTS];
static float fragbot_base[MAX_CLIENTS];      /* low-passed base heading (deg) */
static int   fragbot_base_init[MAX_CLIENTS];

static void FragBot_CoupledAirStrafe(gedict_t *self)
{
	int    slot = NUM_FOR_EDICT(self) - 1;
	vec3_t goal_dir, flat_vel;
	float  gain   = bound(0.0f, cvar("k_fb_fragbot_coupling_gain"), 1.0f);
	float  swing  = cvar("k_fb_fragbot_swing_deg");
	float  period = cvar("k_fb_fragbot_swing_period");
	float  raw_yaw, base_yaw, speed, cyc, tri, amp, d, jump_min;
	int    on_ground;

	if (slot < 0 || slot >= MAX_CLIENTS) return;
	if (swing <= 0)  swing  = 35.0f;
	if (period <= 0) period = 0.45f;

	/* raw base heading: nav heading if present, else velocity, else facing */
	VectorCopy(self->fb.dir_move_, goal_dir);
	goal_dir[2] = 0;
	VectorCopy(self->s.v.velocity, flat_vel);
	flat_vel[2] = 0;
	speed = VectorLength(flat_vel);
	if (VectorLength(goal_dir) >= 0.1f)      raw_yaw = vectoyaw(goal_dir);
	else if (speed > 50.0f)                  raw_yaw = vectoyaw(flat_vel);
	else                                     raw_yaw = self->s.v.angles[YAW];

	/* LOW-PASS the base heading so combat/stuck thrash doesn't whip the view */
	if (!fragbot_base_init[slot]) { fragbot_base[slot] = raw_yaw; fragbot_base_init[slot] = 1; }
	d = anglemod(raw_yaw - fragbot_base[slot] + 180.0f) - 180.0f;
	fragbot_base[slot] = anglemod(fragbot_base[slot] + 0.20f * d);
	base_yaw = fragbot_base[slot];

	on_ground = ((int)self->s.v.flags & FL_ONGROUND) ? 1 : 0;

	/* On the GROUND: run STRAIGHT (no weave) to build up to ~ground-max speed.
	 * In the AIR: weave to air-strafe. Air-strafe is an airborne technique, and
	 * weaving on the ground just bleeds the speed you need for a good hop. */
	fragbot_phase[slot] += g_globalvars.frametime / (2.0f * period);
	if (fragbot_phase[slot] >= 1.0f) fragbot_phase[slot] -= 1.0f;
	cyc = fragbot_phase[slot];
	tri = (cyc < 0.5f) ? (-1.0f + 4.0f * cyc) : (3.0f - 4.0f * cyc);
	amp = on_ground ? 0.0f : (swing * gain);

	self->fb.desired_angle[PITCH] = 0;
	self->fb.desired_angle[YAW]   = anglemod(base_yaw + amp * tri);
	self->fb.desired_angle[ROLL]  = 0;

	/* JUMP only once we've built near ground-max speed, so the hop carries real
	 * distance and can be chained into a bunnyhop. Jumping from a standstill =
	 * useless little hops. Release in the air -> fresh press on every landing. */
	jump_min = cvar("k_fb_fragbot_jump_speed");
	if (jump_min <= 0) jump_min = 300.0f;
	self->fb.jumping = (on_ground && speed >= jump_min) ? true : false;
	self->fb.firing  = false;  /* movement-only demonstrator */
}
/* ===== /FRAGBOT_BLOCK ===== */

/* ===== FRAGBOT_CALL ===== */
	if ((int)cvar("k_fb_fragbot_mode") == 30 && !ISDEAD(self)
	    && !(match_in_progress != 2 && cvar(FB_CVAR_FREEZE_PREWAR)))
	{
		FragBot_CoupledAirStrafe(self);
	}
/* ===== /FRAGBOT_CALL ===== */

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
	/* BUILD STAMP: deploy script rewrites @@FRAGBOT_BUILD@@ to a unique id per build,
	 * baked into THIS .so and advertised in serverinfo so we can query the LIVE
	 * server and confirm exactly which build is loaded (catches stale .so in mem). */
	localcmd("serverinfo fragbot_build \"@@FRAGBOT_BUILD@@\"\n");
/* ===== /FRAGBOT_CALL2 ===== */

/* ===== FRAGBOT_BLOCK ===== */
static float fragbot_phase[MAX_CLIENTS];
static float fragbot_base[MAX_CLIENTS];      /* low-passed base heading (deg) */
static int   fragbot_base_init[MAX_CLIENTS];
static int   fragbot_grounded[MAX_CLIENTS];  /* has touched ground at least once */
static int   fragbot_spawnf[MAX_CLIENTS];    /* frames since spawn (spawn telemetry) */

/* ---- mode 31 (human aim smoothing / anti-snap) per-bot state ---- */
static float fragbot_aim_yaw[MAX_CLIENTS];    /* current SMOOTHED yaw the bot is "looking" */
static float fragbot_aim_pitch[MAX_CLIENTS];  /* current SMOOTHED pitch */
static int   fragbot_aim_init[MAX_CLIENTS];   /* state initialised for this slot */
static float fragbot_aim_react[MAX_CLIENTS];  /* reaction-latency hold timer, seconds remaining */
static float fragbot_aim_lasttgt[MAX_CLIENTS];/* last target yaw seen (to detect big reacquire) */

/* MODE 31 — AIM SMOOTHING ONLY (anti-snap). Layered on top of native fighting +
 * native waypoint navigation. Native frogbot keeps doing target-selection,
 * waypoint nav, firing AND movement. This function ONLY filters the VIEW ANGLE:
 * native has already set self->fb.desired_angle to point at the current target
 * (we run right before trap_makevectors). We slew a smoothed yaw/pitch toward
 * that target at a capped human turn rate (shortest angular path) and write the
 * smoothed angles BACK into desired_angle so native's makevectors + firing use
 * the human-tracked aim instead of a 1-frame teleport-snap.
 *
 * It does NOT touch dir_move_, jumping, or firing -> movement/nav/trigger stay
 * 100% native. Because the body moves along native pathing while the view turns
 * smoothly toward enemies, aim/look stay coherent with movement (proper VYA),
 * with NO decoupled spinning and NO bunnyhop.
 *
 * Cvars (tune live):
 *   k_fb_aim_yaw_rate    deg/s, max yaw slew     (default 320; 180 flick ~0.56s)
 *   k_fb_aim_pitch_rate  deg/s, max pitch slew   (default 220)
 *   k_fb_aim_react_ms    ms hold on a big target jump (>~40 deg) before slewing
 *                        toward the new target  (default 120; 0 disables latency) */
static void FragBot_AimSmooth(gedict_t *self)
{
	int    slot = NUM_FOR_EDICT(self) - 1;
	float  yaw_rate, pitch_rate, react_s, ft;
	float  tgt_yaw, tgt_pitch, dy, dp, maxstep_yaw, maxstep_pitch, jump;

	if (slot < 0 || slot >= MAX_CLIENTS) return;

	ft = g_globalvars.frametime;
	if (ft <= 0.0f) return;                 /* nothing to slew this tick */

	yaw_rate = cvar("k_fb_aim_yaw_rate");
	if (yaw_rate <= 0.0f) yaw_rate = 320.0f;
	pitch_rate = cvar("k_fb_aim_pitch_rate");
	if (pitch_rate <= 0.0f) pitch_rate = 220.0f;
	react_s = cvar("k_fb_aim_react_ms") * 0.001f;   /* may be 0 -> latency off */

	/* native target angle (already aimed at the current enemy / nav heading) */
	tgt_yaw   = self->fb.desired_angle[YAW];
	tgt_pitch = self->fb.desired_angle[PITCH];

	/* init the smoothed aim to the current target on first run / after respawn */
	if (!fragbot_aim_init[slot]) {
		fragbot_aim_yaw[slot]     = tgt_yaw;
		fragbot_aim_pitch[slot]   = tgt_pitch;
		fragbot_aim_lasttgt[slot] = tgt_yaw;
		fragbot_aim_react[slot]   = 0.0f;
		fragbot_aim_init[slot]    = 1;
	}

	/* REACTION LATENCY: if the target yaw jumps a lot vs where we are looking
	 * (new enemy / big reacquire), hold for react_s before resuming the slew. */
	jump = anglemod(tgt_yaw - fragbot_aim_yaw[slot] + 180.0f) - 180.0f;  /* [-180,180] */
	if (react_s > 0.0f && fabs(jump) > 40.0f) {
		/* only (re)arm the timer when the target itself moved a lot since last
		 * tick -- i.e. a genuine switch, not us merely being mid-turn toward it */
		float tgtmove = anglemod(tgt_yaw - fragbot_aim_lasttgt[slot] + 180.0f) - 180.0f;
		if (fabs(tgtmove) > 40.0f)
			fragbot_aim_react[slot] = react_s;
	}
	fragbot_aim_lasttgt[slot] = tgt_yaw;

	if (fragbot_aim_react[slot] > 0.0f) {
		/* still reacting: don't move the aim, just count the timer down. Native
		 * firing may still trigger, but aim is off-target so it mostly won't hit
		 * -- a human-like "caught off guard" beat. */
		fragbot_aim_react[slot] -= ft;
		self->fb.desired_angle[YAW]   = fragbot_aim_yaw[slot];
		self->fb.desired_angle[PITCH] = fragbot_aim_pitch[slot];
		return;
	}

	maxstep_yaw   = yaw_rate   * ft;
	maxstep_pitch = pitch_rate * ft;

	/* YAW: slew toward target by at most maxstep, via shortest angular delta */
	dy = anglemod(tgt_yaw - fragbot_aim_yaw[slot] + 180.0f) - 180.0f;
	if (dy >  maxstep_yaw) dy =  maxstep_yaw;
	if (dy < -maxstep_yaw) dy = -maxstep_yaw;
	fragbot_aim_yaw[slot] = anglemod(fragbot_aim_yaw[slot] + dy);

	/* PITCH: pitch is naturally [-90,90]; treat as shortest delta too */
	dp = anglemod(tgt_pitch - fragbot_aim_pitch[slot] + 180.0f) - 180.0f;
	if (dp >  maxstep_pitch) dp =  maxstep_pitch;
	if (dp < -maxstep_pitch) dp = -maxstep_pitch;
	fragbot_aim_pitch[slot] = fragbot_aim_pitch[slot] + dp;

	/* write smoothed aim back so native makevectors + firing use it */
	self->fb.desired_angle[YAW]   = anglemod(fragbot_aim_yaw[slot]);
	self->fb.desired_angle[PITCH] = fragbot_aim_pitch[slot];
	/* ROLL left untouched (native) */

	/* DEBUG (k_fb_dbg): how far is the smoothed aim trailing the native target?
	 * Big native snaps show up as a large gap that our slew is closing. ~2x/s. */
	{
		static int aim_dbgtick[MAX_CLIENTS];
		if ((int) cvar("k_fb_dbg") && ++aim_dbgtick[slot] >= 38) {
			aim_dbgtick[slot] = 0;
			G_bprint(2, "AIM s%d tgtyaw%d aimyaw%d gap%d react%d\n", slot,
				(int) tgt_yaw, (int) fragbot_aim_yaw[slot], (int) jump,
				(int) (fragbot_aim_react[slot] * 1000));
		}
	}
}

static void FragBot_CoupledAirStrafe(gedict_t *self)
{
	int    slot = NUM_FOR_EDICT(self) - 1;
	vec3_t goal_dir, flat_vel;
	float  gain   = bound(0.0f, cvar("k_fb_fragbot_coupling_gain"), 1.0f);
	float  swing  = cvar("k_fb_fragbot_swing_deg");
	float  period = cvar("k_fb_fragbot_swing_period");
	float  raw_yaw, base_yaw, speed, cyc, tri, amp, d, jump_min;
	int    on_ground, fighting = 0;

	if (slot < 0 || slot >= MAX_CLIENTS) return;
	/* COMBAT-AWARE: when the bot has a player target it is aiming at the enemy
	 * (native sets desired_angle). We must NOT early-return here: KTX 1.48 leaves
	 * dir_move_ = 0 on its own, so OUR seam is the only thing moving the bot. If we
	 * bail the instant it acquires a target, the bot FREEZES on the spot -- and two
	 * bots see each other immediately, so BOTH freeze at spawn (the
	 * "botadds_messed_up" stuck-at-spawn bug). Instead: keep native AIM (skip only
	 * our view weave) but still DRIVE movement -- toward the enemy when fighting so
	 * it approaches/pressures, along nav otherwise -- and keep bunnyhopping. */
	fighting = (self->fb.look_object && self->fb.look_object->ct == ctPlayer);
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
	if (!fragbot_base_init[slot]) { fragbot_base[slot] = raw_yaw; fragbot_base_init[slot] = 1; fragbot_spawnf[slot] = 0; fragbot_grounded[slot] = 0; }
	d = anglemod(raw_yaw - fragbot_base[slot] + 180.0f) - 180.0f;
	fragbot_base[slot] = anglemod(fragbot_base[slot] + 0.20f * d);
	base_yaw = fragbot_base[slot];

	on_ground = ((int)self->s.v.flags & FL_ONGROUND) ? 1 : 0;
	if (on_ground) fragbot_grounded[slot] = 1;

	/* SPAWN TRACE (k_fb_dbg): unthrottled for the first ~2s so we SEE the spawn
	 * tick + whether it falls to ground. z is origin Z; gr=touched-ground-yet. */
	if (fragbot_spawnf[slot] < 150) {
		fragbot_spawnf[slot]++;
		if ((int) cvar("k_fb_dbg") && (fragbot_spawnf[slot] <= 6 || fragbot_spawnf[slot] % 10 == 0))
			G_bprint(2, "SPAWN s%d f%d og%d z%d gr%d\n", slot, fragbot_spawnf[slot],
				on_ground, (int) self->s.v.origin[2], fragbot_grounded[slot]);
	}

	/* On the GROUND: run STRAIGHT (no weave) to build up to ~ground-max speed.
	 * In the AIR: weave to air-strafe. Air-strafe is an airborne technique, and
	 * weaving on the ground just bleeds the speed you need for a good hop. */
	fragbot_phase[slot] += g_globalvars.frametime / (2.0f * period);
	if (fragbot_phase[slot] >= 1.0f) fragbot_phase[slot] -= 1.0f;
	cyc = fragbot_phase[slot];
	tri = (cyc < 0.5f) ? (-1.0f + 4.0f * cyc) : (3.0f - 4.0f * cyc);
	amp = on_ground ? 0.0f : (swing * gain);

	/* VIEW: only weave when NOT fighting. When fighting, leave native desired_angle
	 * (aimed at the enemy) untouched so we don't wobble its aim. */
	if (!fighting) {
		self->fb.desired_angle[PITCH] = 0;
		self->fb.desired_angle[YAW]   = anglemod(base_yaw + amp * tri);
		self->fb.desired_angle[ROLL]  = 0;
	}

	/* AIR CONTROL (regression fix for KTX 1.48): the native frogbot now leaves
	 * dir_move_ = 0 while airborne, so the weaving view had nothing to project ->
	 * the bot just coasted ballistically (floated) while the view panned. Set
	 * dir_move_ forward (base heading) ourselves while airborne so the weave turns
	 * it into real air-strafe acceleration. On the ground we leave dir_move_ alone
	 * so the native wall-aware navigation still drives the path. */
	if (fighting) {
		/* FIGHT MOVEMENT: native leaves dir_move_ = 0, so drive toward the enemy on
		 * XY -> the bot closes/pressures instead of freezing. Native aim + fire does
		 * the kill; the jump logic below lets it bunnyhop in. */
		vec3_t e; float el;
		e[0] = self->fb.look_object->s.v.origin[0] - self->s.v.origin[0];
		e[1] = self->fb.look_object->s.v.origin[1] - self->s.v.origin[1];
		e[2] = 0;
		el = VectorLength(e);
		if (el > 1.0f) {
			self->fb.dir_move_[0] = e[0] / el;
			self->fb.dir_move_[1] = e[1] / el;
			self->fb.dir_move_[2] = 0;
		}
	} else if (!on_ground && fragbot_grounded[slot]) {  /* only after it has landed once -> a spawn-airborne bot falls naturally first */
		vec3_t a;
		a[0] = 0; a[1] = base_yaw; a[2] = 0;
		trap_makevectors(a);
		self->fb.dir_move_[0] = g_globalvars.v_forward[0];
		self->fb.dir_move_[1] = g_globalvars.v_forward[1];
		self->fb.dir_move_[2] = 0;
	}

	/* JUMP only once we've built near ground-max speed, so the hop carries real
	 * distance and can be chained into a bunnyhop. Jumping from a standstill =
	 * useless little hops. Release in the air -> fresh press on every landing. */
	jump_min = cvar("k_fb_fragbot_jump_speed");
	if (jump_min <= 0) jump_min = 300.0f;
	self->fb.jumping = (on_ground && speed >= jump_min) ? true : false;
	/* (no firing override -- native combat controls the trigger; we only run here
	 *  when there is no player target, i.e. while navigating) */

	/* DEBUG (k_fb_dbg): is it navigating (nav>0, horizontal progress) or stuck/
	 * floating (og0, nav0, no xy change)? + spawn z. ~2x/sec. */
	{
		static int fb_dbgtick[MAX_CLIENTS];
		if ((int) cvar("k_fb_dbg") && ++fb_dbgtick[slot] >= 38) {
			fb_dbgtick[slot] = 0;
			G_bprint(2, "FB s%d fight%d og%d spd%d move%d xyz %d %d %d\n", slot, fighting, on_ground,
				(int) speed, (int) (VectorLength(self->fb.dir_move_) * 100),
				(int) self->s.v.origin[0], (int) self->s.v.origin[1], (int) self->s.v.origin[2]);
		}
	}
}
/* ===== /FRAGBOT_BLOCK ===== */

/* ===== FRAGBOT_CALL ===== */
	if ((int)cvar("k_fb_fragbot_mode") == 30 && !ISDEAD(self)
	    && !(match_in_progress != 2 && cvar(FB_CVAR_FREEZE_PREWAR)))
	{
		FragBot_CoupledAirStrafe(self);
	}
	/* MODE 31 — human aim smoothing (anti-snap) only. No bunnyhop, no view-weave,
	 * no movement override: native drives fight/nav/fire/move, we filter the view. */
	else if ((int)cvar("k_fb_fragbot_mode") == 31)
	{
		int aslot = NUM_FOR_EDICT(self) - 1;
		if (ISDEAD(self)) {
			/* dead: forget smoothed state so we re-init to the new aim on respawn */
			if (aslot >= 0 && aslot < MAX_CLIENTS) fragbot_aim_init[aslot] = 0;
		} else {
			FragBot_AimSmooth(self);
		}
	}
/* ===== /FRAGBOT_CALL ===== */

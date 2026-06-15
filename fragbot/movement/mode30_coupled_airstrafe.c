/* ============================================================================
 * FragBot moveprobe mode 30 — COUPLED AIR-STRAFE
 *
 * Drop-in addition to komodo's frogbot-moveprobe patch (src/bot_movement.c).
 * This is the FIRST FragBot movement brain: it makes the bot turn its VIEW YAW
 * in sync with its strafe input during air-accel — producing the human
 * view<->heading COUPLING that no stock frogbot has (DeepFrag coupling ~0.03
 * for frogbot vs 0.29-0.47 for humans; see docs/bot_dials_and_calibration.md).
 *
 * Mechanism (the classic bunnyhop air-strafe, executed continuously):
 *   - hold +forward and strafe to ONE side
 *   - rotate the VIEW toward that strafe side (the air-accel that gains speed)
 *   - as velocity curves toward the view, heading and view rotate TOGETHER
 *     => positive coupling (the whole point)
 *   - flip the strafe side every `swing_period` to weave back onto the goal
 *     heading from frogbot's own navigation (self->fb.dir_move_)
 *   - hold +jump so the engine auto-hops on every landing (pm_ktjump)
 *
 * This is a movement-only demonstrator (combat off) — milestone 1 is "watch it
 * move like a human". A later mode folds frogbot aim back in for real games.
 *
 * Knobs (set via the launch cfg; read as cvars, same pattern as the other modes):
 *   k_fb_moveprobe_forwardmove     forward command (default 320)
 *   k_fb_fragbot_coupling_gain     0=robotic .. ~0.35 human: how hard the view
 *                                  leads the strafe (the #1 human-likeness knob)
 *   k_fb_fragbot_swing_deg         peak view offset from heading per weave (deg)
 *   k_fb_fragbot_swing_period      seconds per weave half (strafe-side flip)
 *
 * Sweep these with komodo's mode-sweep harness; SCORE with fragbot/score_bot.py
 * (target: coupling_52ms -> 0.29-0.47), NOT raw bunnyhop speed.
 * ==========================================================================*/

/* --- 1. add to the static per-client state block at the top of the file --- */
static float moveprobe_fragbot_phase[MAX_CLIENTS];   /* mode 30: weave phase [0,1) */
static float moveprobe_fragbot_side[MAX_CLIENTS];    /* mode 30: current strafe side (-1/+1) */

/* --- 2. add this branch to the mode dispatch chain (after the mode==20/21/23
 *        blocks, before the final fall-through). --------------------------- */
else if (mode == 30)
{
	int   slot = NUM_FOR_EDICT(self) - 1;
	vec3_t goal_dir, flat_vel;
	float forwardmove = cvar("k_fb_moveprobe_forwardmove");
	float gain        = bound(0.0f, cvar("k_fb_fragbot_coupling_gain"), 1.0f);
	float swing       = cvar("k_fb_fragbot_swing_deg");
	float period      = cvar("k_fb_fragbot_swing_period");
	float speed, goal_yaw, vel_yaw, base_yaw, view_yaw, err;

	if (forwardmove <= 0) forwardmove = 320.0f;
	if (swing <= 0)       swing  = 35.0f;
	if (period <= 0)      period = 0.45f;

	/* goal heading: frogbot's own navigation direction (flattened) */
	VectorCopy(self->fb.dir_move_, goal_dir);
	goal_dir[2] = 0;
	if (VectorNormalize(goal_dir) > 0)
		goal_yaw = vectoyaw(goal_dir);
	else
		goal_yaw = self->s.v.angles[YAW];          /* no route: hold facing */

	/* current horizontal velocity heading */
	VectorCopy(self->s.v.velocity, flat_vel);
	flat_vel[2] = 0;
	speed   = VectorLength(flat_vel);
	vel_yaw = (speed > 1.0f) ? vectoyaw(flat_vel) : goal_yaw;

	/* weave phase: flip strafe side each half-period */
	moveprobe_fragbot_phase[slot] += g_globalvars.frametime / period;
	if (moveprobe_fragbot_phase[slot] >= 1.0f)
	{
		moveprobe_fragbot_phase[slot] -= 1.0f;
		moveprobe_fragbot_side[slot]   = -moveprobe_fragbot_side[slot];
	}
	if (moveprobe_fragbot_side[slot] == 0)
		moveprobe_fragbot_side[slot] = 1.0f;

	/* THE COUPLING: lead the view toward the strafe side, scaled by gain.
	 * Once at speed, lead off the *velocity* heading so view tracks the curve
	 * (this is what makes view & heading rotate together => coupling). */
	base_yaw = (speed > 320.0f) ? vel_yaw : goal_yaw;
	view_yaw = anglemod(base_yaw + moveprobe_fragbot_side[slot] * swing * gain);

	/* steer the weave back toward the goal heading (nav tracking) */
	err = anglemod(goal_yaw - view_yaw + 180.0f) - 180.0f;   /* [-180,180) */
	view_yaw = anglemod(view_yaw + 0.15f * err);

	self->fb.desired_angle[PITCH] = 0;
	self->fb.desired_angle[YAW]   = view_yaw;
	self->fb.desired_angle[ROLL]  = 0;

	/* air-strafe inputs: forward + strafe toward the weave side */
	direction[0] = forwardmove;
	direction[1] = moveprobe_fragbot_side[slot] * 400.0f;
	direction[2] = 0;

	*jumping = true;     /* engine only jumps when grounded -> continuous bunnyhop */
	*firing  = false;    /* movement-only demonstrator (milestone 1) */
	*impulse = 0;
	return;
}

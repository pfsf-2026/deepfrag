/* FragBot PHASE 2 seam — value routing + roam-aim alignment (mode 32).
 *
 * Two native facts (per Xerial's KTX read + bot_movement.c::BotSetCommand):
 *   1. Goal/route is a marker graph; native EvalGoal scores desire*(lookahead-
 *      routetime)/lookahead with proper routing. We TUNE it via desire_* fields
 *      (NOT fixed_goal — that short-circuits routing => bot strafes in place).
 *   2. forwardmove = DotProduct(v_forward, dir_move_)*800, where v_forward comes
 *      from desired_angle (the AIM angle). If aim points away from the route, the
 *      projection collapses into backpedal/strafe and speed dies (the aim/move
 *      conflict — the "some speed but not moving" symptom).
 *
 * FIX: when NOT fighting (no enemy), point the aim at the move direction so the
 * projection yields full forward speed and the view smoothly faces travel (also
 * kills the "zapping look to look"). dir_move_ is already normalized at the inject
 * point. Combat aim is left to native code when an enemy exists.
 *
 * Injected right before `trap_makevectors(self->fb.desired_angle);` so the angle
 * override is in effect for the projection. See docs/bot_pathing_methodology.md.
 */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_PATH_MODE 32

static void FragBot_Path(gedict_t *self)
{
	vec3_t ang;

	/* (1) value weights — native marker routing picks the best value/sec item */
	self->fb.fixed_goal = NULL;            /* never short-circuit native routing */
	self->fb.desire_mega_health     = 100.0f;
	self->fb.desire_armorInv        =  95.0f;   /* red armor */
	self->fb.desire_armor2          =  60.0f;   /* yellow armor */
	self->fb.desire_armor1          =  30.0f;   /* green armor */
	self->fb.desire_rocketlauncher  =  85.0f;
	self->fb.desire_lightning       =  70.0f;
	self->fb.desire_grenadelauncher =  35.0f;
	self->fb.desire_supernailgun    =  30.0f;
	self->fb.desire_supershotgun    =  25.0f;

	/* (2) roam-aim alignment — look where we're going so the move projection
	   gives full speed. Only when not actively fighting (else keep combat aim). */
	if (self->s.v.enemy < 1)
	{
		if (VectorLength(self->fb.dir_move_) > 0.01f)
		{
			vectoangles(self->fb.dir_move_, ang);
			self->fb.desired_angle[YAW]   = ang[YAW];
			self->fb.desired_angle[PITCH] = 0;   /* level look while running */
			self->fb.desired_angle[ROLL]  = 0;
		}
	}
}
/* ===== /FRAGBOT_BLOCK ===== */

/* ===== FRAGBOT_CALL ===== */
	if ((int) cvar("k_fb_fragbot_mode") == FRAGBOT_PATH_MODE && !ISDEAD(self))
	{
		FragBot_Path(self);
	}
/* ===== /FRAGBOT_CALL ===== */

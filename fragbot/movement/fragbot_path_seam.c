/* FragBot PHASE 2 seam — value routing + see-only targeting + human aim model
 * (mode 32). See docs/bot_pathing_methodology.md.
 *
 *  (1) VALUE ROUTING: tune native marker routing via desire_* (not fixed_goal).
 *  (2) ROAM-AIM: face dir_move_ when not fighting (full-speed move projection).
 *  (3) SEE-ONLY TARGETING: native BotsPickBestEnemy is OMNISCIENT (picks any
 *      player by marker route-distance, no line-of-sight) -> wallhack / turning
 *      into spawns. We gate combat on visible(): the bot only aims/fires at an
 *      enemy it can trace a clear line to. (Memory/anticipation = later.)
 *  (4) HUMAN AIM MODEL:
 *      - REACTION DELAY on first SIGHT (not on omniscient acquire): hold the look
 *        + hold fire for k_fb_react sec, then flick. Kills instant-shoot-on-sight.
 *      - CRITICALLY-DAMPED SMOOTHING (smoothdamp): accelerate -> settle, velocity-
 *        continuous. Slower smoothTime roaming (calm scan) than in combat.
 *      Live cvars: k_fb_react (0.28) k_fb_smooth_roam (0.22) k_fb_smooth_aim (0.09)
 *                  k_fb_aim_maxspeed (1400).  Lower smooth_aim / raise maxspeed for
 *                  higher LG accuracy at top skill (smoothness<->accuracy tradeoff).
 *
 * Injected before trap_makevectors(desired_angle). */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_PATH_MODE 32
extern float visible(gedict_t *targ);

static vec3_t fragbot_view[MAX_CLIENTS];        /* smoothed current view */
static vec3_t fragbot_vel[MAX_CLIENTS];         /* angular velocity (deg/s) */
static int    fragbot_init[MAX_CLIENTS];
static int    fragbot_saw[MAX_CLIENTS];         /* could see an enemy last frame */
static float  fragbot_react_until[MAX_CLIENTS];

static float fb_cvar(char *n, float def) { float v = cvar(n); return (v != 0) ? v : def; }
static float fb_adelta(float a) { while (a > 180) a -= 360; while (a < -180) a += 360; return a; }

/* Unity-style critically-damped smoothing toward target (no oscillation). */
static float fb_smoothdamp(float cur, float target, float *vel, float smoothTime,
                           float maxspeed, float dt)
{
	float omega, x, ex, change, maxchange, temp;
	if (smoothTime < 0.001f) smoothTime = 0.001f;
	omega = 2.0f / smoothTime;
	x = omega * dt;
	ex = 1.0f / (1.0f + x + 0.48f * x * x + 0.235f * x * x * x);
	change = fb_adelta(cur - target);
	maxchange = maxspeed * smoothTime;
	if (change > maxchange)  change = maxchange;
	if (change < -maxchange) change = -maxchange;
	temp = (*vel + omega * change) * dt;
	*vel = (*vel - omega * temp) * ex;
	return (cur - change) + (change + temp) * ex;
}

static void FragBot_Path(gedict_t *self, int cmd_msec)
{
	int slot = NUM_FOR_EDICT(self) - 1;
	vec3_t ang, tgt;
	int en, canSee, canHear, reacting, j;
	float dt, smoothTime, maxspeed;

	/* (1) value weights — native marker routing picks the best value/sec item */
	self->fb.fixed_goal = NULL;
	self->fb.desire_mega_health     = 100.0f;
	self->fb.desire_armorInv        =  95.0f;
	self->fb.desire_armor2          =  60.0f;
	self->fb.desire_armor1          =  30.0f;
	self->fb.desire_rocketlauncher  =  85.0f;
	self->fb.desire_lightning       =  70.0f;
	self->fb.desire_grenadelauncher =  35.0f;
	self->fb.desire_supernailgun    =  30.0f;
	self->fb.desire_supershotgun    =  25.0f;

	if (slot < 0 || slot >= MAX_CLIENTS)
		return;

	/* (3) see-only: gate the omniscient native enemy on real line-of-sight.
	   HEARING: if we can't see them but they're nearby AND moving (audible),
	   we can still localize the SOUND direction and turn toward it (no fire). */
	en = (int) self->s.v.enemy;
	canSee = canHear = 0;
	if (en >= 1 && en < MAX_EDICTS)
	{
		gedict_t *e = &g_edicts[en];
		if (visible(e))
			canSee = 1;
		else if (VectorDistance(self->s.v.origin, e->s.v.origin) < fb_cvar("k_fb_hear_range", 800.0f)
		         && VectorLength(e->s.v.velocity) > fb_cvar("k_fb_hear_minspeed", 150.0f))
			canHear = 1;
	}

	/* (4a) reaction delay on FIRST sight */
	if (canSee && !fragbot_saw[slot])
		fragbot_react_until[slot] = g_globalvars.time + fb_cvar("k_fb_react", 0.28f);
	fragbot_saw[slot] = canSee;
	reacting = canSee && (g_globalvars.time < fragbot_react_until[slot]);

	/* never aim/fire at something we can't see, or during the recognition beat */
	if (!canSee || reacting)
		self->fb.firing = false;

	/* pick this frame's TARGET view angle */
	if (canSee && !reacting)
	{
		VectorCopy(self->fb.desired_angle, tgt);          /* native enemy aim */
		smoothTime = fb_cvar("k_fb_smooth_aim", 0.09f);
	}
	else if (reacting)
	{
		VectorCopy(fragbot_view[slot], tgt);              /* hold look (notice beat) */
		smoothTime = fb_cvar("k_fb_smooth_roam", 0.22f);
	}
	else if (canHear)
	{
		vec3_t d;                                          /* turn toward the SOUND */
		VectorSubtract(g_edicts[en].s.v.origin, self->s.v.origin, d);
		d[2] = 0;                                          /* yaw only — localize dir, not height */
		vectoangles(d, ang);
		tgt[0] = 0; tgt[1] = ang[1]; tgt[2] = 0;
		smoothTime = fb_cvar("k_fb_smooth_roam", 0.22f);
	}
	else if (VectorLength(self->fb.dir_move_) > 0.01f)
	{
		vectoangles(self->fb.dir_move_, ang);
		tgt[0] = 0; tgt[1] = ang[1]; tgt[2] = 0;          /* roam: face travel */
		smoothTime = fb_cvar("k_fb_smooth_roam", 0.22f);
	}
	else
	{
		VectorCopy(self->fb.desired_angle, tgt);
		smoothTime = fb_cvar("k_fb_smooth_roam", 0.22f);
	}

	/* (4b) critically-damped smoothing of the view toward the target */
	dt = (cmd_msec > 0 ? cmd_msec : 13) / 1000.0f;
	maxspeed = fb_cvar("k_fb_aim_maxspeed", 1400.0f);
	if (!fragbot_init[slot])
	{
		VectorCopy(tgt, fragbot_view[slot]);
		fragbot_vel[slot][0] = fragbot_vel[slot][1] = fragbot_vel[slot][2] = 0;
		fragbot_init[slot] = 1;
	}
	for (j = 0; j < 2; j++)        /* PITCH=0, YAW=1 */
	{
		float c = fb_smoothdamp(fragbot_view[slot][j], tgt[j], &fragbot_vel[slot][j],
		                        smoothTime, maxspeed, dt);
		while (c > 180) c -= 360;
		while (c < -180) c += 360;
		fragbot_view[slot][j] = c;
	}
	self->fb.desired_angle[PITCH] = fragbot_view[slot][0];
	self->fb.desired_angle[YAW]   = fragbot_view[slot][1];
	self->fb.desired_angle[ROLL]  = 0;
}
/* ===== /FRAGBOT_BLOCK ===== */

/* ===== FRAGBOT_CALL ===== */
	if ((int) cvar("k_fb_fragbot_mode") == FRAGBOT_PATH_MODE && !ISDEAD(self))
	{
		FragBot_Path(self, cmd_msec);
	}
/* ===== /FRAGBOT_CALL ===== */

/* FragBot PHASE 2 seam — value routing + see/hear awareness + human aim (mode 32).
 * See docs/bot_pathing_methodology.md.
 *
 *  (1) VALUE ROUTING via desire_* (not fixed_goal), modulated by COMBAT CONTEXT
 *      and NEED: weapons cut hard in a fight (don't bolt), survival items (armor/
 *      health/mega) kept attractive; health desire scales with how hurt we are.
 *  (2) ROAM-AIM: face dir_move_ when idle (full-speed move projection).
 *  (3) SEE-ONLY TARGETING: gate aim/fire on visible() (no wallhack).
 *  (4) HEARING (event-driven, audibility-correct): hook sound() — for each PLAYER
 *      sound, the audible range is ~1000/att (real QW attenuation), and only bots
 *      that CAN'T already see the source remember it + do a BRIEF glance (gated by
 *      a cooldown so it's a quick head-check, not a stare that wrecks pathing).
 *  (5) HUMAN AIM: reaction delay on first SIGHT + critically-damped smoothing.
 *
 * cvars: k_fb_react k_fb_smooth_aim k_fb_smooth_roam k_fb_aim_maxspeed
 *        k_fb_hear_scale k_fb_glance_dur k_fb_glance_cd k_fb_mem k_fb_combat_itemcut
 *
 * Injected before trap_makevectors(desired_angle); hearing hook into sound(). */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);
// FRAGBOT_FILE2: g_utils.c
// FRAGBOT_ANCHOR2: trap_sound(NUM_FOR_EDICT(ed), channel, samp, vol, att);

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_PATH_MODE 32
extern float visible(gedict_t *targ);
extern qbool Visible_360(gedict_t *self, gedict_t *visible_object);

static vec3_t fragbot_view[MAX_CLIENTS];        /* smoothed current view */
static vec3_t fragbot_vel[MAX_CLIENTS];         /* angular velocity (deg/s) */
static int    fragbot_init[MAX_CLIENTS];
static int    fragbot_saw[MAX_CLIENTS];         /* could see an enemy last frame */
static float  fragbot_react_until[MAX_CLIENTS];
static vec3_t fragbot_mem_pos[MAX_CLIENTS];     /* belief: last heard enemy spot */
static float  fragbot_mem_until[MAX_CLIENTS];   /* memory expiry (anticipation) */
static float  fragbot_glance_until[MAX_CLIENTS];/* brief look-toward-sound window */
static float  fragbot_glance_cd[MAX_CLIENTS];   /* cooldown between glances */

static float fb_cvar(char *n, float def) { float v = cvar(n); return (v != 0) ? v : def; }
static float fb_adelta(float a) { while (a > 180) a -= 360; while (a < -180) a += 360; return a; }
static float fb_clamp(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }

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

/* Hearing hook — called from sound() for EVERY emitted sound, with attenuation.
 * NON-static (linked from g_utils.c). Audible range tracks real QW attenuation;
 * a bot that can already SEE the source doesn't "hear" it (it knows). */
void FragBot_HeardSound(gedict_t *emitter, float att)
{
	gedict_t *plr;
	float range;
	if ((int) cvar("k_fb_fragbot_mode") != FRAGBOT_PATH_MODE)
		return;
	if (!emitter || emitter->ct != ctPlayer)
		return;
	/* QW nominal clip distance ~1000 at ATTN_NORM(1); audible ~ 1000/att */
	range = (att > 0.0f ? 1000.0f / att : 100000.0f) * fb_cvar("k_fb_hear_scale", 1.0f);
	for (plr = world; (plr = find_plr(plr));)
	{
		int slot;
		if (!plr->isBot || plr == emitter || SameTeam(plr, emitter))
			continue;
		if (VectorDistance(plr->s.v.origin, emitter->s.v.origin) > range)
			continue;
		if (Visible_360(plr, emitter))     /* already sees the source — not "heard" */
			continue;
		slot = NUM_FOR_EDICT(plr) - 1;
		if (slot < 0 || slot >= MAX_CLIENTS)
			continue;
		VectorCopy(emitter->s.v.origin, fragbot_mem_pos[slot]);
		fragbot_mem_until[slot] = g_globalvars.time + fb_cvar("k_fb_mem", 4.0f);
		if (g_globalvars.time > fragbot_glance_cd[slot])   /* brief glance, not a stare */
		{
			fragbot_glance_until[slot] = g_globalvars.time + fb_cvar("k_fb_glance_dur", 0.4f);
			fragbot_glance_cd[slot]    = g_globalvars.time + fb_cvar("k_fb_glance_cd", 2.0f);
		}
	}
}

static void FragBot_Path(gedict_t *self, int cmd_msec)
{
	int slot = NUM_FOR_EDICT(self) - 1;
	vec3_t ang, tgt, d;
	int en, canSee, glancing, reacting, j;
	float dt, smoothTime, maxspeed, cfw, cfs, hp, hneed, mneed;

	if (slot < 0 || slot >= MAX_CLIENTS)
		return;

	/* (3) see-only + (4) hearing-glance */
	en = (int) self->s.v.enemy;
	canSee = (en >= 1 && en < MAX_EDICTS && visible(&g_edicts[en])) ? 1 : 0;
	glancing = (!canSee && g_globalvars.time < fragbot_glance_until[slot]) ? 1 : 0;

	/* (1) desire weights — combat-context + need scaled.
	   weapons cut hard in a fight; survival items stay attractive; health scales
	   with how hurt we are (goal_health0 has no native need-scaling). */
	/* Only cut WEAPON greed in combat. Survival items (armor/health/mega) keep
	   full desire so the bot still TIMES and grabs them mid-fight — cutting them
	   was making it abandon a perfectly-timed RA right before respawn. Native
	   route-time already prevents cross-map detours. */
	cfw = cfs = 1.0f;
	if (canSee)
	{
		int stacked = ((self->s.v.health + self->s.v.armorvalue) > 150.0f)
		              && ((int) self->s.v.items & IT_ROCKET_LAUNCHER);
		cfw = stacked ? fb_cvar("k_fb_combat_itemcut", 0.20f) : 0.60f;  /* weapons only */
	}
	hp = self->s.v.health;
	hneed = fb_clamp((100.0f - hp) / 100.0f, 0.0f, 1.0f);    /* h25 wanted only when hurt */
	mneed = fb_clamp((250.0f - hp) / 200.0f, 0.2f, 1.0f);    /* mega: buffer up to 250 */
	self->fb.fixed_goal = NULL;
	/* health base high enough that when genuinely hurt it OUTSCORES RA(95)/mega
	   and becomes the goal -> the bot detours to it (15hp~136, 30hp~112, 50hp~80,
	   70hp~48). goal_health0 has no native need-scaling, so we do it here. */
	self->fb.desire_health0         = 160.0f * hneed * cfs;
	self->fb.desire_mega_health     = 100.0f * mneed * cfs;
	self->fb.desire_armorInv        =  95.0f * cfs;
	self->fb.desire_armor2          =  60.0f * cfs;
	self->fb.desire_armor1          =  30.0f * cfs;
	self->fb.desire_rocketlauncher  =  85.0f * cfw;
	self->fb.desire_lightning       =  70.0f * cfw;
	self->fb.desire_grenadelauncher =  35.0f * cfw;
	self->fb.desire_supernailgun    =  30.0f * cfw;
	self->fb.desire_supershotgun    =  25.0f * cfw;

	/* (5a) reaction delay on FIRST sight */
	if (canSee && !fragbot_saw[slot])
		fragbot_react_until[slot] = g_globalvars.time + fb_cvar("k_fb_react", 0.28f);
	fragbot_saw[slot] = canSee;
	reacting = canSee && (g_globalvars.time < fragbot_react_until[slot]);

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
	else if (glancing)
	{
		VectorSubtract(fragbot_mem_pos[slot], self->s.v.origin, d);
		d[2] = 0;                                          /* yaw only — localize direction */
		if (VectorLength(d) > 0.01f)
		{
			vectoangles(d, ang);
			tgt[0] = 0; tgt[1] = ang[1]; tgt[2] = 0;
		}
		else
		{
			VectorCopy(fragbot_view[slot], tgt);
		}
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

	/* (5b) critically-damped smoothing of the view toward the target */
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

/* ===== FRAGBOT_CALL2 ===== */
	{ extern void FragBot_HeardSound(gedict_t *e_, float a_); FragBot_HeardSound(ed, att); }
/* ===== /FRAGBOT_CALL2 ===== */

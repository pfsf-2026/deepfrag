/* FragBot PHASE 2 seam — value routing + see-only targeting + event-driven
 * hearing + human aim model (mode 32). See docs/bot_pathing_methodology.md.
 *
 *  (1) VALUE ROUTING: tune native marker routing via desire_* (not fixed_goal).
 *  (2) ROAM-AIM: face dir_move_ when not fighting (full-speed move projection).
 *  (3) SEE-ONLY TARGETING: native BotsPickBestEnemy is omniscient -> wallhack.
 *      Gate aim/fire on visible() (clear line-of-sight). No fire at unseen foes.
 *  (4) HEARING (event-driven, NOT speed): running is silent in QW; only discrete
 *      sounds carry — item pickups, weapon fire, jumps, pain. sound() calls
 *      BotsSoundMadeEvent(emitter), so we hook it: when a PLAYER makes a sound
 *      within k_fb_hear_range, nearby enemy bots remember that position for
 *      k_fb_hear_mem sec and TURN TOWARD it (yaw only — localize direction, not
 *      height), holding fire, until they actually see someone.
 *  (5) HUMAN AIM: reaction delay on first SIGHT (k_fb_react) + critically-damped
 *      smoothing (accelerate->settle). Lower k_fb_smooth_aim / raise
 *      k_fb_aim_maxspeed for higher LG accuracy at top skill.
 *
 * Injected before trap_makevectors(desired_angle); the hearing hook is a second
 * injection into BotsSoundMadeEvent. */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);
// FRAGBOT_FILE2: bot_botenemy.c
// FRAGBOT_ANCHOR2: if (entity && entity->ct == ctPlayer)

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_PATH_MODE 32
extern float visible(gedict_t *targ);

static vec3_t fragbot_view[MAX_CLIENTS];        /* smoothed current view */
static vec3_t fragbot_vel[MAX_CLIENTS];         /* angular velocity (deg/s) */
static int    fragbot_init[MAX_CLIENTS];
static int    fragbot_saw[MAX_CLIENTS];         /* could see an enemy last frame */
static float  fragbot_react_until[MAX_CLIENTS];
static vec3_t fragbot_mem_pos[MAX_CLIENTS];     /* belief: last heard/seen enemy spot */
static float  fragbot_mem_until[MAX_CLIENTS];   /* memory expiry (anticipation) */
static float  fragbot_glance_until[MAX_CLIENTS];/* brief look-toward-sound window */
static float  fragbot_glance_cd[MAX_CLIENTS];   /* cooldown between glances */

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

/* Hearing hook — called from BotsSoundMadeEvent for EVERY emitted sound. Records
 * the sound position for nearby enemy bots (NON-static: linked from bot_botenemy.c). */
void FragBot_HeardSound(gedict_t *emitter)
{
	gedict_t *plr;
	float range;
	if ((int) cvar("k_fb_fragbot_mode") != FRAGBOT_PATH_MODE)
		return;
	if (!emitter || emitter->ct != ctPlayer)
		return;
	range = fb_cvar("k_fb_hear_range", 800.0f);
	for (plr = world; (plr = find_plr(plr));)
	{
		int slot;
		if (!plr->isBot || plr == emitter || SameTeam(plr, emitter))
			continue;
		if (VectorDistance(plr->s.v.origin, emitter->s.v.origin) > range)
			continue;
		slot = NUM_FOR_EDICT(plr) - 1;
		if (slot < 0 || slot >= MAX_CLIENTS)
			continue;
		/* update belief (memory) — persists for anticipation */
		VectorCopy(emitter->s.v.origin, fragbot_mem_pos[slot]);
		fragbot_mem_until[slot] = g_globalvars.time + fb_cvar("k_fb_mem", 4.0f);
		/* trigger only a BRIEF glance, and only if the cooldown has elapsed, so
		   the bot does a quick "what was that" instead of staring (which hijacks
		   pathing and gets it stuck) */
		if (g_globalvars.time > fragbot_glance_cd[slot])
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
	float dt, smoothTime, maxspeed, cf;

	if (slot < 0 || slot >= MAX_CLIENTS)
		return;

	/* (3) see-only: gate the omniscient native enemy on real line-of-sight */
	en = (int) self->s.v.enemy;
	canSee = (en >= 1 && en < MAX_EDICTS && visible(&g_edicts[en])) ? 1 : 0;
	/* (4) hearing: a brief glance toward a remembered sound, only while blind */
	glancing = (!canSee && g_globalvars.time < fragbot_glance_until[slot]) ? 1 : 0;

	/* (1) value weights, modulated by COMBAT CONTEXT: when we can see an enemy,
	   don't blindly abandon the fight for an item. Cut item pull hard if we're
	   well-stacked with a launcher (fight!), softly if low (still grab survival). */
	cf = 1.0f;
	if (canSee)
	{
		int stacked = ((self->s.v.health + self->s.v.armorvalue) > 150.0f)
		              && ((int) self->s.v.items & IT_ROCKET_LAUNCHER);
		cf = stacked ? fb_cvar("k_fb_combat_itemcut", 0.20f) : 0.70f;
	}
	self->fb.fixed_goal = NULL;
	self->fb.desire_mega_health     = 100.0f * cf;
	self->fb.desire_armorInv        =  95.0f * cf;
	self->fb.desire_armor2          =  60.0f * cf;
	self->fb.desire_armor1          =  30.0f * cf;
	self->fb.desire_rocketlauncher  =  85.0f * cf;
	self->fb.desire_lightning       =  70.0f * cf;
	self->fb.desire_grenadelauncher =  35.0f * cf;
	self->fb.desire_supernailgun    =  30.0f * cf;
	self->fb.desire_supershotgun    =  25.0f * cf;

	/* (5a) reaction delay on FIRST sight */
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
	{ extern void FragBot_HeardSound(gedict_t *e_); FragBot_HeardSound(entity); }
/* ===== /FRAGBOT_CALL2 ===== */

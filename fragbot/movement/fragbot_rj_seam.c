/* FragBot REAL rocket-jump executor seam. Mode 33.
 *
 * NO replay / NO teleport. The bot actually equips the RL, looks down at its
 * feet (or down-forward at a step), and presses JUMP + ATTACK on the SAME tick.
 * The ENGINE fires a real rocket -> real launch sound, real splash, real
 * self-damage knockback that throws the bot up exactly like a human RJ. Normal
 * player physics carries the whole arc. Cycles 3 jump styles forever so the set
 * can be watched on aerowalk:
 *   style 0 — vertical pop   : stand still, look straight down, jump+fire
 *   style 1 — long jump      : sprint forward to build speed, then down-forward jump+fire (air-steer)
 *   style 2 — short stair    : small forward, look down-forward, jump+fire
 *
 * Native primitive reference: BotPerformRocketJump() in bot_botjump.c
 *   (SetRocketJumpAngles default pitch 78.25, desired_weapon_impulse=7, fb.firing=true).
 * Knockback only applies while takedamage is ON (combat.c T_Damage early-returns
 * on DAMAGE_NO), so we KEEP takedamage normal and just top health up each cycle
 * instead of using invuln. FB_CVAR_FREEZE_PREWAR must be 0 (its default) or the
 * matchless server zeroes firing/jumping before the cmd is sent (bot_movement.c). */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_RJ_MODE 33

#ifndef IT_ROCKET_LAUNCHER
#define IT_ROCKET_LAUNCHER 32
#endif

/* per-style: aim pitch when firing (down = +), forward run-up frames before fire */
static const float fragbot_rj_pitch[3] = { 80.0f, 50.0f, 68.0f };
static const int   fragbot_rj_run[3]   = { 0,     14,    4     };

static int   fragbot_rj_phase[MAX_CLIENTS];   /* 0 wait/run, 1 fire, 2 air, 3 pause */
static int   fragbot_rj_timer[MAX_CLIENTS];
static int   fragbot_rj_style[MAX_CLIENTS];
static float fragbot_rj_yaw[MAX_CLIENTS];     /* locked facing for this jump */
static int   fragbot_rj_init[MAX_CLIENTS];

/* Set dir_move_ to a horizontal unit vector in the locked yaw, using the
 * engine's own angle->vector conversion (pitch 0 -> level forward). Avoids any
 * trig here; the real trap_makevectors(desired_angle) right after recomputes
 * the globals for the actual cmd, so clobbering them here is harmless. */
static void FragBot_RJ_Forward(gedict_t *self, float yaw)
{
	vec3_t a;
	a[0] = 0; a[1] = yaw; a[2] = 0;
	trap_makevectors(a);
	self->fb.dir_move_[0] = g_globalvars.v_forward[0];
	self->fb.dir_move_[1] = g_globalvars.v_forward[1];
	self->fb.dir_move_[2] = 0;
}

static void FragBot_RJ(gedict_t *self)
{
	int slot = NUM_FOR_EDICT(self) - 1;
	int st, onground;

	if (slot < 0 || slot >= MAX_CLIENTS) return;
	if (!fragbot_rj_init[slot]) {
		fragbot_rj_phase[slot] = 0;
		fragbot_rj_timer[slot] = 0;
		fragbot_rj_style[slot] = 0;
		fragbot_rj_yaw[slot]   = self->fb.desired_angle[YAW];
		fragbot_rj_init[slot]  = 1;
	}

	st = fragbot_rj_style[slot];
	if (st < 0 || st > 2) st = 0;
	onground = (int) self->s.v.flags & FL_ONGROUND;

	/* keep it alive + armed every tick (real RJ damage still launches it) */
	self->s.v.items = ((int) self->s.v.items) | IT_ROCKET_LAUNCHER;
	if (self->s.v.ammo_rockets < 5) self->s.v.ammo_rockets = 50;
	if (self->s.v.health < 150) self->s.v.health = 250;
	self->s.v.weapon = IT_ROCKET_LAUNCHER;
	self->s.v.currentammo = self->s.v.ammo_rockets;
	self->fb.desired_weapon_impulse = 7;          /* RL; matches BotUsingCorrectWeapon */

	/* default: no input this tick; keep a stable facing so it doesn't spin */
	self->fb.firing = false;
	self->fb.jumping = false;
	VectorClear(self->fb.dir_move_);
	self->fb.desired_angle[YAW]  = fragbot_rj_yaw[slot];
	self->fb.desired_angle[ROLL] = 0;

	switch (fragbot_rj_phase[slot]) {
	case 0: /* WAIT / RUN-UP: aim down, optionally sprint to build speed, then fire */
		self->fb.desired_angle[PITCH] = fragbot_rj_pitch[st];
		if (fragbot_rj_timer[slot] < fragbot_rj_run[st]) {
			FragBot_RJ_Forward(self, fragbot_rj_yaw[slot]);
			self->fb.desired_angle[PITCH] = 10.0f;       /* look ahead while running */
			fragbot_rj_timer[slot] += 1;
			break;
		}
		/* launch only when grounded, RL ready, and attack off cooldown */
		if (onground && self->attack_finished < self->client_time) {
			fragbot_rj_phase[slot] = 1;
		}
		break;

	case 1: /* FIRE: jump + rocket at the feet on the SAME tick */
		self->fb.desired_angle[PITCH] = fragbot_rj_pitch[st];
		if (fragbot_rj_run[st] > 0) FragBot_RJ_Forward(self, fragbot_rj_yaw[slot]);
		self->fb.firing  = true;
		self->fb.jumping = true;
		fragbot_rj_phase[slot] = 2;
		fragbot_rj_timer[slot] = 0;
		break;

	case 2: /* AIR: real physics carries the arc; air-steer the long jump */
		if (fragbot_rj_run[st] > 0) {
			FragBot_RJ_Forward(self, fragbot_rj_yaw[slot]);
			self->fb.desired_angle[PITCH] = 10.0f;
		}
		fragbot_rj_timer[slot] += 1;
		/* landed (after actually leaving the ground) or safety timeout */
		if ((fragbot_rj_timer[slot] > 6 && onground) || fragbot_rj_timer[slot] > 250) {
			fragbot_rj_phase[slot] = 3;
			fragbot_rj_timer[slot] = 60;                 /* ~0.8s to show the landing */
		}
		break;

	case 3: /* PAUSE on the ground, then advance to the next style */
		self->fb.desired_angle[PITCH] = 15.0f;
		fragbot_rj_timer[slot] -= 1;
		if (fragbot_rj_timer[slot] <= 0) {
			fragbot_rj_style[slot] = (st + 1) % 3;
			fragbot_rj_phase[slot] = 0;
			fragbot_rj_timer[slot] = 0;
			fragbot_rj_yaw[slot]   = self->fb.desired_angle[YAW]; /* re-lock facing */
		}
		break;
	}
}
/* ===== /FRAGBOT_BLOCK ===== */

/* ===== FRAGBOT_CALL ===== */
	if ((int) cvar("k_fb_fragbot_mode") == FRAGBOT_RJ_MODE && !ISDEAD(self))
	{
		FragBot_RJ(self);
	}
/* ===== /FRAGBOT_CALL ===== */

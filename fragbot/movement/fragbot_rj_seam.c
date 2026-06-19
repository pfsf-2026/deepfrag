/* FragBot rocket-jump demonstrator seam. Mode 33.  STABLE / PINNED design.
 *
 * Goal: let you WATCH a real rocket jump, reliably, without the bot wandering off
 * or wedging itself in geometry. Earlier versions drove the bot horizontally
 * (long/stair jumps) with no navigation, so it flung itself across aerowalk and
 * got stuck floating. This version does ONE thing well:
 *
 *   - equip the RL, look straight DOWN at its feet, press JUMP + ATTACK together
 *   - the ENGINE fires a real rocket -> real launch sound, splash, self-damage
 *     knockback -> the bot pops STRAIGHT UP and lands on the SAME spot
 *   - because there is no horizontal input, it cannot drift, wander, or wedge
 *   - SELF-RECOVERY: if it is ever airborne too long (wedged), it snaps back to
 *     its home spot on the ground and resumes. So it can never stay stuck.
 *
 * Native primitive reference: BotPerformRocketJump() in bot_botjump.c
 *   (SetRocketJumpAngles pitch 78.25, desired_weapon_impulse=7, fb.firing=true).
 * Knockback only applies while takedamage is ON (combat.c T_Damage early-returns
 * on DAMAGE_NO) so we keep takedamage normal and top health up each tick.
 * FB_CVAR_FREEZE_PREWAR must be 0 (default) or the matchless server zeroes
 * firing/jumping before the cmd is sent (bot_movement.c). */
// FRAGBOT_ANCHOR: trap_makevectors(self->fb.desired_angle);
//
// LAB-ONLY second injection: disable ezcsqc on this build. The 1.48 ezcsqc
// client draws players via a per-client CSQC weapon-prediction handshake that a
// bot (no real client connection) can never complete, so bots render invisible.
// The lab only needs to SEE bots, not client-side antilag, so we advertise
// qwm_ezcsqc 0 -> the client falls back to standard player rendering -> bots
// are visible again. (Fleet servers keep stock ezcsqc; this only affects the
// fragbot gamedir's qwprogs.so.)
// FRAGBOT_FILE2: g_main.c
// FRAGBOT_ANCHOR2: sv_extensions = cvar("sv_mod_extensions");

/* ===== FRAGBOT_CALL2 ===== */
	cvar_set("qwm_ezcsqc", "0"); /* FragBot lab: standard rendering so bots are visible */
/* ===== /FRAGBOT_CALL2 ===== */

/* ===== FRAGBOT_BLOCK ===== */
#define FRAGBOT_RJ_MODE 33

#ifndef IT_ROCKET_LAUNCHER
#define IT_ROCKET_LAUNCHER 32
#endif

#define FRAGBOT_RJ_PITCH      88.0f   /* look (almost) straight down at the feet */
#define FRAGBOT_RJ_STUCK_AIR  180     /* ~2.3s airborne -> treat as wedged, recover */
#define FRAGBOT_RJ_PAUSE      55      /* ~0.7s on the ground between jumps          */

static int   fragbot_rj_phase[MAX_CLIENTS];    /* 0 wait, 1 fire, 2 air, 3 pause */
static int   fragbot_rj_timer[MAX_CLIENTS];
static float fragbot_rj_home[MAX_CLIENTS][3];  /* the spot it jumps from / returns to */
static int   fragbot_rj_homeset[MAX_CLIENTS];
static int   fragbot_rj_init[MAX_CLIENTS];

static void FragBot_RJ(gedict_t *self)
{
	int slot = NUM_FOR_EDICT(self) - 1;
	int onground;

	if (slot < 0 || slot >= MAX_CLIENTS) return;

	if (!fragbot_rj_init[slot]) {
		fragbot_rj_phase[slot]   = 0;
		fragbot_rj_timer[slot]   = 0;
		fragbot_rj_homeset[slot] = 0;
		fragbot_rj_init[slot]    = 1;
	}

	onground = (int) self->s.v.flags & FL_ONGROUND;

	/* home = the first ground spot we see; that is where every pop starts/returns */
	if (!fragbot_rj_homeset[slot] && onground) {
		VectorCopy(self->s.v.origin, fragbot_rj_home[slot]);
		fragbot_rj_homeset[slot] = 1;
	}

	/* keep alive + armed every tick (real RJ damage still launches it) */
	self->s.v.items = ((int) self->s.v.items) | IT_ROCKET_LAUNCHER;
	if (self->s.v.ammo_rockets < 5) self->s.v.ammo_rockets = 50;
	if (self->s.v.health < 150) self->s.v.health = 250;
	self->s.v.weapon = IT_ROCKET_LAUNCHER;
	self->s.v.currentammo = self->s.v.ammo_rockets;
	self->fb.desired_weapon_impulse = 7;          /* RL; matches BotUsingCorrectWeapon */

	/* default every tick: NO movement input at all (this is why it can't drift),
	 * no firing/jumping, flat view aim straight down. */
	self->fb.firing  = false;
	self->fb.jumping = false;
	VectorClear(self->fb.dir_move_);
	self->fb.desired_angle[PITCH] = FRAGBOT_RJ_PITCH;
	self->fb.desired_angle[ROLL]  = 0;

	switch (fragbot_rj_phase[slot]) {
	case 0: /* WAIT: on the ground, RL ready, attack off cooldown -> fire */
		if (onground && self->attack_finished < self->client_time) {
			fragbot_rj_phase[slot] = 1;
		}
		break;

	case 1: /* FIRE: jump + rocket at the feet on the SAME tick -> straight-up pop */
		self->fb.firing  = true;
		self->fb.jumping = true;
		fragbot_rj_phase[slot] = 2;
		fragbot_rj_timer[slot] = 0;
		break;

	case 2: /* AIR: physics carries the straight-up arc; detect landing or wedge */
		fragbot_rj_timer[slot] += 1;
		if (fragbot_rj_timer[slot] > 6 && onground) {
			fragbot_rj_phase[slot] = 3;
			fragbot_rj_timer[slot] = FRAGBOT_RJ_PAUSE;
		}
		else if (fragbot_rj_timer[slot] > FRAGBOT_RJ_STUCK_AIR && fragbot_rj_homeset[slot]) {
			/* wedged / never came down -> recover to home spot on the ground */
			setorigin(self, PASSVEC3(fragbot_rj_home[slot]));
			VectorClear(self->s.v.velocity);
			fragbot_rj_phase[slot] = 3;
			fragbot_rj_timer[slot] = FRAGBOT_RJ_PAUSE;
		}
		break;

	case 3: /* PAUSE: stand on the ground a beat so the landing reads, then repeat */
		self->fb.desired_angle[PITCH] = 12.0f;   /* look up a little between pops */
		fragbot_rj_timer[slot] -= 1;
		if (fragbot_rj_timer[slot] <= 0) {
			fragbot_rj_phase[slot] = 0;
			fragbot_rj_timer[slot] = 0;
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

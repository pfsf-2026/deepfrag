/*
 * Strafe coach (DeepFrag) -- an opt-in bunnyhop / circle-jump trainer.
 *
 * THE PHYSICS
 *
 * QuakeWorld adds speed along the direction your movement keys point (the "wish
 * direction"), but only up to a cap of speed measured ALONG that direction:
 *
 *     addspeed   = CAP - dot(velocity, wishdir)
 *     accelspeed = min(sv_accelerate * wishspeed * frametime, addspeed)
 *     velocity  += accelspeed * wishdir
 *
 * In the AIR the cap is 30 (PM_AirAccelerate). A frame therefore adds the most speed
 * when the wish direction is exactly sideways to your velocity, and the window that adds
 * anything is only a few degrees wide. As you gain, your velocity turns, so the window
 * turns with it: bunnyhopping is a smooth mouse sweep, and the speed you gain is set by
 * how fast you sweep while staying inside the window. Holding the perfect angle every
 * frame needs a sweep of ~300 deg/sec at 400 ups, so nobody scores 100%.
 *
 * On the GROUND the cap is your full wish speed (320) and friction eats ~5% a frame.
 * Pointing the wish direction ~40 degrees off your velocity still nets speed, up to an
 * equilibrium near 485 ups. That run-up is the circle jump: what you carry into your
 * first hop.
 *
 * The server knows the keys held (self->movement), the view angle (v_angle) and the
 * velocity the move is about to use, every client frame, so all of this is exact.
 *
 * WHAT THE PLAYER SEES
 *
 *   HUD (centerprint):
 *         437                 your speed
 *              33%  >>        33% of the possible gain right now; turn RIGHT for more
 *         last hop +22        (or "circle jump 405" after the first hop of a run)
 *
 *   Console (top left of the screen): one line per hop, so the last few stay visible.
 *
 *   ORB: in the air it is a PACER. It starts where your view should be and sweeps in the
 *   direction you are strafing at a set rate ("scpace" picks 60 / 90 / 120 / 150 / 180
 *   deg/sec). Keep your crosshair on it and you are sweeping at that pace. It waits if
 *   you fall far behind and re-anchors every hop and every time you switch strafe key.
 *   On the ground it shows the best aim for the run-up.
 *   It sits at a fixed distance (constant size) on the plane of your standing eye height
 *   (no bobbing with your jumps) and is led by your ping.
 *
 * "strafecoach" (or "scoach") cycles: HUD + orb, HUD only, orb only, off.
 * It is a practice aid: it only runs outside a live match (prewar, race, practice mode)
 * unless k_strafecoach_match is set.
 */

#include "g_local.h"

#define STC_MODEL			"progs/s_light.spr"	// id1 light globe: a sprite, so it always faces you
#define STC_REFRESH			0.1f				// HUD refresh, seconds (same rate race mode prints at)
#define STC_DIST			320.0f				// the orb is always this far away, so its size never changes
#define STC_AIR_WISH		30.0f				// PM_AirAccelerate's wishspeed cap
#define STC_FRICTION		4.0f				// sv_friction
#define STC_STOPSPEED		100.0f				// sv_stopspeed
#define STC_MIN_SPEED		200.0f				// below this there is nothing to coach
#define STC_MIN_HOP_FRAMES	15					// ignore stair steps and tiny drops
#define STC_MAX_LEAD		0.15f				// never lead the orb by more than this many seconds
#define STC_GAIN_EFF		0.10f				// "gaining": this share of the best possible frame
#define STC_PACE_DEFAULT	90					// pacer sweep, degrees a second
#define STC_PACE_WAIT		20.0f				// the pacer stops while it is this far ahead of your view
#define STC_GROUND_SETTLE	3					// ground frames in a row before ground maths applies
#define STC_CHAIN_BREAK		20					// ground frames in a row that end a hop chain (~0.27 s)

static const int stc_paces[] = { 60, 90, 120, 150, 180 };
#define STC_NUM_PACES ((int)(sizeof(stc_paces) / sizeof(stc_paces[0])))

static float stc_angdiff(float a, float b)
{
	float d = a - b;

	while (d > 180)
	{
		d -= 360;
	}

	while (d <= -180)
	{
		d += 360;
	}

	return d;
}

static float stc_clamp(float v, float lo, float hi)
{
	return ((v < lo) ? lo : ((v > hi) ? hi : v));
}

static float stc_speed2d(gedict_t *p)
{
	return sqrt(p->s.v.velocity[0] * p->s.v.velocity[0] + p->s.v.velocity[1] * p->s.v.velocity[1]);
}

// A practice aid: never during a live match unless the server explicitly allows it.
static qbool stc_allowed(void)
{
	return ((match_in_progress != 2) || isRACE() || k_practice || cvar("k_strafecoach_match"));
}

static void stc_reset_stats(gedict_t *p)
{
	p->stc_in_air = false;
	p->stc_takeoff_speed = 0;
	p->stc_ideal_v2 = 0;
	p->stc_air_frames = 0;
	p->stc_ground_frames = 0;
	p->stc_last_gain = 0;
	p->stc_last_eff = 0;
	p->stc_last_ground = 0;
	p->stc_have_hop = false;
	p->stc_next_draw = 0;
	p->stc_orb_live = false;
	p->stc_orb_side = 0;
	p->stc_chain_hops = 0;
	p->stc_last_cj = 0;
	p->stc_acc_eff = 0;
	p->stc_acc_off = 0;
	p->stc_acc_n = 0;
}

// The orb entity can be freed under us (map change); never trust a stale pointer.
static gedict_t* stc_marker_get(gedict_t *p)
{
	gedict_t *m = p->stc_marker;

	if (m && !(m->classname && streq(m->classname, "stc_marker")))
	{
		m = NULL;
	}

	if (!m)
	{
		m = spawn();
		m->classname = "stc_marker";
		m->s.v.movetype = MOVETYPE_NONE;
		m->s.v.solid = SOLID_NOT;
		m->s.v.owner = EDICT_TO_PROG(p);
		setsize(m, 0, 0, 0, 0, 0, 0);
		p->stc_marker = m;
		p->stc_marker_shown = false;
	}

	return m;
}

static void stc_marker_hide(gedict_t *p)
{
	gedict_t *m = p->stc_marker;

	if (!m || !p->stc_marker_shown)
	{
		return;
	}

	if (m->classname && streq(m->classname, "stc_marker"))
	{
		setmodel(m, "");
		m->s.v.effects = 0;
	}

	p->stc_marker_shown = false;
}

static void stc_marker_remove(gedict_t *p)
{
	gedict_t *m = p->stc_marker;

	if (m && m->classname && streq(m->classname, "stc_marker"))
	{
		ent_remove(m);
	}

	p->stc_marker = NULL;
	p->stc_marker_shown = false;
}

// One frame of PM_Accelerate / PM_AirAccelerate for a wish direction at `wish_vs_vel_deg`
// from the velocity, as a share of the best frame possible. cap = 30 in the air, the full
// wish speed on the ground. d = speed along the wish direction.
//   addspeed = cap - d;  accelspeed = min(a_cap, addspeed);  speed^2 grows by 2*a*d + a*a
static float stc_frame_eff(float speed, float wish_vs_vel_deg, float cap, float a_cap, float ideal_step)
{
	float d = speed * cos(wish_vs_vel_deg * M_PI / 180);
	float a = stc_clamp(cap - d, 0, a_cap);

	return ((2 * a * d + a * a) / ideal_step);
}

// Three short lines:
//     437                      your speed
//     <<  21%                  21% of the possible gain right now; turn LEFT for more
//     last hop +22             or "circle jump 405" after the first hop of a run
// eff / offset are averages over the frames since the last refresh, so the line does not flicker.
static void stc_print(gedict_t *p, float speed, qbool guide, float eff, float offset, qbool strafing)
{
	char mid[32], last[40];
	int arrows, pct;
	float off_abs = (offset < 0) ? -offset : offset;

	last[0] = 0;
	if (p->stc_last_cj > 0)
	{
		snprintf(last, sizeof(last), "circle jump %d", (int)floor(p->stc_last_cj + 0.5f));
	}
	else if (p->stc_have_hop)
	{
		snprintf(last, sizeof(last), "last hop %+d", (int)floor(p->stc_last_gain + 0.5f));
	}

	if (!guide)
	{
		G_centerprint(p, "%d\n%s\n%s", (int)speed,
						((speed >= STC_MIN_SPEED) && !strafing) ? "hold a strafe key" : " ", last);

		return;
	}

	pct = (int)floor(eff * 100 + 0.5f);
	pct = (pct < 0) ? 0 : ((pct > 100) ? 100 : pct);
	arrows = (off_abs >= 6) ? 3 : ((off_abs >= 3) ? 2 : ((off_abs >= 1) ? 1 : 0));

	// fixed-width, so the number stays put: 3 arrow cells, the number, 3 arrow cells.
	// '<' | 0x80 and '>' | 0x80 are the red glyphs.
	if (offset > 0)			// the best aim is to your LEFT
	{
		snprintf(mid, sizeof(mid), "%.*s%*s %3d%%    ", arrows, "\xbc\xbc\xbc", 3 - arrows, "", pct);
	}
	else
	{
		snprintf(mid, sizeof(mid), "    %3d%% %*s%.*s", pct, 3 - arrows, "", arrows, "\xbe\xbe\xbe");
	}

	G_centerprint(p, "%d\n%s\n%s", (int)speed, mid, last);
}

void StrafeCoachPrecache(void)
{
	trap_precache_model(STC_MODEL);
}

// Called once per (re)connect, i.e. also after every map change. Mode and pace survive in
// the client's userinfo ("setinfo stc N", "setinfo stcp N") so the coach stays on across maps.
void StrafeCoachConnect(gedict_t *p)
{
	int mode = iKey(p, "stc"), pace = iKey(p, "stcp");

	p->stc_marker = NULL;
	p->stc_marker_shown = false;
	p->stc_lead = 0;
	p->stc_plane_z = 0;
	p->stc_ground_run = 0;
	p->stc_mode = (mode < 0 || mode > 3) ? 0 : mode;
	p->stc_pace = (pace < 30 || pace > 300) ? STC_PACE_DEFAULT : pace;
	stc_reset_stats(p);
}

void StrafeCoachDisconnect(gedict_t *p)
{
	stc_marker_remove(p);
	p->stc_mode = 0;
}

void StrafeCoachCmd(void)
{
	static char *names[] = { "off", "HUD + orb", "HUD only", "orb only" };

	self->stc_mode = (self->stc_mode + 1) % 4;
	stc_reset_stats(self);

	if (!self->stc_pace)
	{
		self->stc_pace = STC_PACE_DEFAULT;
	}

	if (!self->stc_mode)
	{
		stc_marker_remove(self);
		G_centerprint(self, " ");
	}

	stuffcmd_flags(self, STUFFCMD_IGNOREINDEMO, "setinfo stc %d\n", self->stc_mode);
	G_sprint(self, PRINT_HIGH, "Strafe coach: %s\n", redtext(names[self->stc_mode]));

	if (self->stc_mode == 1)
	{
		G_sprint(self, PRINT_HIGH, "In the air: hold a strafe key and sweep the mouse the same way.\n"
					"The %% is how much of the possible speed you are gaining. Arrows = turn that way for more.\n"
					"The orb sweeps at %d deg/sec: keep your crosshair on it. scpace changes the pace.\n",
					self->stc_pace);
	}

	if (self->stc_mode && !stc_allowed())
	{
		G_sprint(self, PRINT_HIGH, "It only runs outside a live match.\n");
	}
}

// "scpace": step the pacer through its sweep rates.
void StrafeCoachPaceCmd(void)
{
	int i, next = 0;

	for (i = 0; i < STC_NUM_PACES; i++)
	{
		if (stc_paces[i] == self->stc_pace)
		{
			next = (i + 1) % STC_NUM_PACES;
			break;
		}
	}

	self->stc_pace = stc_paces[next];
	self->stc_orb_live = false;
	stuffcmd_flags(self, STUFFCMD_IGNOREINDEMO, "setinfo stcp %d\n", self->stc_pace);
	G_sprint(self, PRINT_HIGH, "Strafe coach pace: %s deg/sec\n", dig3(self->stc_pace));
}

// Runs from PlayerPreThink: self->movement holds this command's keys and velocity is what
// the move is about to use, so the answer is exact for this frame.
void StrafeCoachFrame(void)
{
	static float cached_at = -1, sv_accel = 10, sv_maxspd = 320;
	float speed, v_eff, fmove, smove, ft, wishspeed, cap, a_cap, ideal_step, d_opt, theta_opt;
	float vel_yaw = 0, view_yaw = 0, wish_rel = 0, side = 0, ideal_view = 0, offset = 0, wish_vs_vel = 0, eff_now = 0;
	qbool onground, ground_phys, took_off = false, guide;

	if (!self->stc_mode)
	{
		return;
	}

	if ((self->ct != ctPlayer) || self->isBot || !ISLIVE(self) || !stc_allowed())
	{
		stc_marker_hide(self);
		self->stc_in_air = false;
		self->stc_orb_live = false;

		return;
	}

	// physics cvars: one lookup a second is plenty
	if ((g_globalvars.time < cached_at) || (g_globalvars.time - cached_at > 1))
	{
		cached_at = g_globalvars.time;
		sv_accel = cvar("sv_accelerate");
		sv_maxspd = cvar("sv_maxspeed");
		sv_accel = (sv_accel > 0) ? sv_accel : 10;
		sv_maxspd = (sv_maxspd > 0) ? sv_maxspd : 320;
	}

	speed = stc_speed2d(self);
	onground = ((int)self->s.v.flags & FL_ONGROUND) ? true : false;
	fmove = self->movement[0];
	smove = self->movement[1];
	ft = g_globalvars.frametime;
	ft = ((ft <= 0) || (ft > 0.1f)) ? 0.013f : ft;

	self->stc_ground_run = onground ? (self->stc_ground_run + 1) : 0;

	// A bunnyhop touch-down is not a ground frame: with jump held the engine leaves the
	// ground before friction and uses the air maths. Ground maths applies once you have
	// really been standing on it for a few frames without jumping.
	ground_phys = onground && !self->s.v.button2 && (self->stc_ground_run >= STC_GROUND_SETTLE);

	wishspeed = sqrt(fmove * fmove + smove * smove);
	wishspeed = ((wishspeed <= 0) || (wishspeed > sv_maxspd)) ? sv_maxspd : wishspeed;
	a_cap = sv_accel * wishspeed * ft;		// 43 at 77 fps

	if (ground_phys)
	{
		// friction first, then accelerate against the full wish speed
		float control = (speed < STC_STOPSPEED) ? STC_STOPSPEED : speed;

		v_eff = speed - control * STC_FRICTION * ft;
		v_eff = (v_eff < 0) ? 0 : v_eff;
		cap = wishspeed;
	}
	else
	{
		v_eff = speed;
		cap = STC_AIR_WISH;
	}

	// The best frame: accelspeed limited only by a_cap, with the wish direction as far along
	// the velocity as that allows (d_opt). In the air at 77 fps a_cap > 30, so d_opt = 0:
	// exactly sideways. On the ground d_opt = 320 - 43 = 277.
	d_opt = (a_cap >= cap) ? 0 : (cap - a_cap);
	ideal_step = (a_cap >= cap) ? (cap * cap) : (a_cap * (2 * cap - a_cap));

	// ---- hop bookkeeping: takeoff speed -> landing speed, against what was possible ----
	if (!onground)
	{
		if (!self->stc_in_air)
		{
			self->stc_in_air = true;
			took_off = true;
			self->stc_takeoff_speed = speed;
			self->stc_ideal_v2 = 0;
			self->stc_air_frames = 0;
			self->stc_last_ground = self->stc_ground_frames;
		}

		self->stc_air_frames++;
		self->stc_ideal_v2 += STC_AIR_WISH * STC_AIR_WISH;
	}
	else
	{
		if (self->stc_in_air)
		{
			self->stc_in_air = false;

			if ((self->stc_air_frames >= STC_MIN_HOP_FRAMES) && (self->stc_takeoff_speed >= 150)
					&& (self->stc_ideal_v2 > 0))
			{
				float eff = (speed * speed - self->stc_takeoff_speed * self->stc_takeoff_speed) / self->stc_ideal_v2;

				self->stc_last_gain = speed - self->stc_takeoff_speed;
				self->stc_last_eff = stc_clamp(eff, -0.99f, 1.5f);
				self->stc_have_hop = true;
				self->stc_chain_hops++;

				// One console line per hop: the last few stay on screen, top left.
				// The first hop of a run is the circle jump -- what it reaches is the number.
				if (self->stc_chain_hops == 1)
				{
					self->stc_last_cj = speed;

					if ((self->stc_mode == 1) || (self->stc_mode == 2))
					{
						G_sprint(self, PRINT_HIGH, "%s %d  (left the ground at %d)\n", redtext("circle jump"),
									(int)floor(speed + 0.5f), (int)floor(self->stc_takeoff_speed + 0.5f));
					}
				}
				else
				{
					self->stc_last_cj = 0;

					if ((self->stc_mode == 1) || (self->stc_mode == 2))
					{
						G_sprint(self, PRINT_HIGH, "hop %d  %+d  now %d  %d%%\n", self->stc_chain_hops,
									(int)floor(self->stc_last_gain + 0.5f), (int)floor(speed + 0.5f),
									(int)floor(self->stc_last_eff * 100 + 0.5f));
					}
				}
			}

			self->stc_ground_frames = 0;
		}

		self->stc_ground_frames++;

		if (self->stc_ground_frames > STC_CHAIN_BREAK)
		{
			self->stc_chain_hops = 0;		// the run is over; the next jump is a new circle jump
		}

		self->stc_plane_z = self->s.v.origin[2] + self->s.v.view_ofs[2];	// standing eye height
	}

	// ---- where should the view be right now? ----
	// Needs a strafe key (it picks the turn direction) and some speed.
	guide = (smove != 0) && (speed >= STC_MIN_SPEED) && (v_eff > 1);

	if (guide)
	{
		float c = stc_clamp(d_opt / v_eff, -1, 1);

		vel_yaw = atan2(self->s.v.velocity[1], self->s.v.velocity[0]) * 180 / M_PI;
		view_yaw = self->s.v.v_angle[1];
		wish_rel = atan2(-smove, fmove) * 180 / M_PI;	// wish direction relative to the view (right is -90)
		side = (smove < 0) ? 1 : -1;					// strafing left turns you left (yaw grows)

		// best wish direction: theta_opt off the velocity, on the side you are strafing to.
		// Air: 90 degrees (sideways). Ground: ~40 at 360 ups, 0 below 277 (just run straight).
		theta_opt = acos(c) * 180 / M_PI;
		ideal_view = vel_yaw + side * theta_opt - wish_rel;
		offset = stc_angdiff(ideal_view, view_yaw);		// + = the best aim is to your left

		wish_vs_vel = stc_angdiff(view_yaw + wish_rel, vel_yaw);
		eff_now = stc_frame_eff(v_eff, wish_vs_vel, cap, a_cap, ideal_step);

		self->stc_acc_eff += eff_now;
		self->stc_acc_off += offset;
		self->stc_acc_n++;
	}

	// ---- the orb ----
	if (guide && ((self->stc_mode == 1) || (self->stc_mode == 3)))
	{
		gedict_t *m = stc_marker_get(self);
		float yaw_r;
		vec3_t at;

		if (ground_phys)
		{
			// run-up: the best aim right now. No smoothing: on the ground the best aim itself
			// sweeps at up to ~300 deg/sec (that sweep IS the circle jump), and any lag here
			// would point the player well behind it.
			self->stc_orb_yaw = ideal_view;
			self->stc_orb_live = true;
			self->stc_orb_side = 0;				// 0 = not a pacer anchor
		}
		else
		{
			// in the air: a pacer. Sweeping the view at `pace` settles with the wish direction
			// trailing sideways by exactly the angle where one frame's gain turns the velocity
			// at that same pace: accelspeed = speed * pace * frametime, so d = 30 - that.
			float pace_r = self->stc_pace * M_PI / 180;

			if (!self->stc_orb_live || took_off || (self->stc_orb_side != side))
			{
				float d_t = stc_clamp(STC_AIR_WISH - speed * pace_r * ft, d_opt, STC_AIR_WISH);
				float theta_t = acos(stc_clamp(d_t / speed, -1, 1)) * 180 / M_PI;

				self->stc_orb_yaw = vel_yaw + side * theta_t - wish_rel;
				self->stc_orb_live = true;
				self->stc_orb_side = side;
			}
			else
			{
				// how far the orb is ahead of your view, in the direction it sweeps
				float ahead = stc_angdiff(self->stc_orb_yaw, view_yaw) * side;

				if (ahead < STC_PACE_WAIT)
				{
					self->stc_orb_yaw += side * self->stc_pace * ft;
				}
			}
		}

		// Fixed distance: its size on screen never changes. Fixed plane: your standing eye
		// height, so it does not bob with your jumps. Your client predicts you ahead of what
		// the server sees by about your ping and the orb's position takes half a ping to reach
		// you, so place it from where you WILL be: the direction is then right when drawn.
		yaw_r = self->stc_orb_yaw * M_PI / 180;
		at[0] = self->s.v.origin[0] + self->s.v.view_ofs[0] + self->s.v.velocity[0] * self->stc_lead + cos(yaw_r) * STC_DIST;
		at[1] = self->s.v.origin[1] + self->s.v.view_ofs[1] + self->s.v.velocity[1] * self->stc_lead + sin(yaw_r) * STC_DIST;
		at[2] = self->stc_plane_z;

		setorigin(m, PASSVEC3(at));
		m->s.v.effects = (eff_now >= STC_GAIN_EFF) ? EF_BLUE : 0;	// glows while you are gaining speed

		if (!self->stc_marker_shown)
		{
			setmodel(m, STC_MODEL);
			self->stc_marker_shown = true;
		}
	}
	else
	{
		stc_marker_hide(self);
		self->stc_orb_live = false;
	}

	// ---- the HUD (and the ping the orb is led by), ten times a second ----
	if (g_globalvars.time >= self->stc_next_draw)
	{
		float lead = atof(ezinfokey(self, "ping")) / 1000.0f;

		self->stc_next_draw = g_globalvars.time + STC_REFRESH;
		self->stc_lead = stc_clamp(lead, 0, STC_MAX_LEAD);

		if ((self->stc_mode == 1) || (self->stc_mode == 2))
		{
			qbool have = guide && (self->stc_acc_n > 0);

			stc_print(self, speed, have,
						have ? (self->stc_acc_eff / self->stc_acc_n) : 0,
						have ? (self->stc_acc_off / self->stc_acc_n) : 0, smove != 0);
		}

		self->stc_acc_eff = 0;
		self->stc_acc_off = 0;
		self->stc_acc_n = 0;
	}
}

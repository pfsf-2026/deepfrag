/*
 * Strafe coach (DeepFrag) -- an opt-in air-strafe trainer.
 *
 * QuakeWorld air acceleration (PM_AirAccelerate) adds speed along the direction
 * your movement keys point (the "wish direction"), but only up to 30 units/sec of
 * speed measured ALONG that direction:
 *
 *     addspeed   = 30 - dot(velocity, wishdir)
 *     accelspeed = min(sv_accelerate * sv_maxspeed * frametime, addspeed)
 *     velocity  += accelspeed * wishdir
 *
 * So a frame adds the most speed when the wish direction is exactly sideways to
 * your velocity (dot = 0): speed^2 grows by 30^2 = 900. Point it more along your
 * velocity and addspeed shrinks to nothing; point it past sideways and you start
 * pushing against yourself. The useful window is only a few degrees wide, and it
 * rotates as your velocity turns -- which is why bunnyhopping is a smooth mouse
 * turn, and why it is hard to learn blind.
 *
 * The server knows everything needed to solve this exactly, every client frame:
 * the keys held (self->movement), the view angle (v_angle) and the velocity the
 * move is about to use. The coach turns that into two things:
 *
 *   - a HUD (centerprint), three short lines:
 *         your speed
 *         NN% with arrows  -- NN% is how much of the possible speed gain you are getting
 *                             right now; the arrows say which way to turn for more
 *         last hop +N      -- speed gained by the hop you just finished
 *     One rule for the player: make the number go up by turning the way the arrows point.
 *
 *   - an ORB in the world at the yaw to aim at. It sits at a fixed distance (so it never
 *     changes size) on the plane of your standing eye height (so it does not bob with your
 *     jumps), is smoothed, and is led by your ping.
 *
 * Holding 100% needs a turn of ~300 deg/sec at 400 ups, so nobody does: the gain you get
 * is set by how fast you can turn while keeping the number above zero.
 *
 * "strafecoach" (or "scoach") cycles: HUD + orb, HUD only, orb only, off.
 * It is a practice aid, so it only runs outside a live match (prewar, race,
 * practice mode) unless k_strafecoach_match is set.
 */

#include "g_local.h"

#define STC_MODEL			"progs/s_light.spr"	// id1 light globe: a sprite, so it always faces you
#define STC_REFRESH			0.1f				// HUD refresh, seconds (same rate race mode prints at)
#define STC_DIST			320.0f				// the orb is always this far away, so its size never changes
#define STC_AIR_WISH		30.0f				// PM_AirAccelerate's wishspeed cap
#define STC_MIN_SPEED		200.0f				// below this there is nothing to coach
#define STC_MIN_HOP_FRAMES	15					// ignore stair steps and tiny drops
#define STC_MAX_LEAD		0.15f				// never lead the orb by more than this many seconds
#define STC_ORB_TAU			0.06f				// orb yaw smoothing time constant, seconds
#define STC_GAIN_EFF		0.10f				// "gaining": this share of the best possible frame

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

// One air frame of PM_AirAccelerate for a given wish direction, as a share of the best
// frame possible. d = speed along the wish direction.
//   addspeed = 30 - d;  accelspeed = min(a_cap, addspeed);  speed^2 grows by 2*a*d + a*a
static float stc_frame_eff(float speed, float wish_vs_vel_deg, float a_cap, float ideal_step)
{
	float d = speed * cos(wish_vs_vel_deg * M_PI / 180);
	float a = STC_AIR_WISH - d;

	a = (a > a_cap) ? a_cap : ((a < 0) ? 0 : a);

	return ((2 * a * d + a * a) / ideal_step);
}

// Three short lines:
//     437                      your speed
//     <<  21%                  21% of the possible gain right now; turn LEFT for more
//     last hop +22             what the hop you just finished gained
// eff / offset are averages over the frames since the last refresh, so the line does not flicker.
static void stc_print(gedict_t *p, float speed, qbool guide, float eff, float offset, qbool strafing)
{
	char mid[32], hop[32];
	int arrows, pct;
	float off_abs = (offset < 0) ? -offset : offset;

	hop[0] = 0;
	if (p->stc_have_hop)
	{
		snprintf(hop, sizeof(hop), "last hop %+d", (int)floor(p->stc_last_gain + 0.5f));
	}

	if (!guide)
	{
		G_centerprint(p, "%d\n%s\n%s", (int)speed,
						((speed >= STC_MIN_SPEED) && !strafing) ? "hold a strafe key" : " ", hop);

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

	G_centerprint(p, "%d\n%s\n%s", (int)speed, mid, hop);
}

void StrafeCoachPrecache(void)
{
	trap_precache_model(STC_MODEL);
}

// Called once per (re)connect, i.e. also after every map change. The mode survives in
// the client's userinfo ("setinfo stc N") so the coach stays on across maps.
void StrafeCoachConnect(gedict_t *p)
{
	int mode = iKey(p, "stc");

	p->stc_marker = NULL;
	p->stc_marker_shown = false;
	p->stc_lead = 0;
	p->stc_plane_z = 0;
	p->stc_mode = (mode < 0 || mode > 3) ? 0 : mode;
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

	if (!self->stc_mode)
	{
		stc_marker_remove(self);
		G_centerprint(self, " ");
	}

	stuffcmd_flags(self, STUFFCMD_IGNOREINDEMO, "setinfo stc %d\n", self->stc_mode);
	G_sprint(self, PRINT_HIGH, "Strafe coach: %s\n", redtext(names[self->stc_mode]));

	if (self->stc_mode == 1)
	{
		G_sprint(self, PRINT_HIGH, "In the air: hold a strafe key and turn the mouse the same way.\n"
					"The %% is how much of the possible speed you are gaining. Arrows = turn that way for more.\n"
					"The orb marks where to aim.\n");
	}

	if (self->stc_mode && !stc_allowed())
	{
		G_sprint(self, PRINT_HIGH, "It only runs outside a live match.\n");
	}
}

// Runs from PlayerPreThink: self->movement holds this command's keys and velocity is what
// the move is about to use, so the answer is exact for this frame.
void StrafeCoachFrame(void)
{
	static float cached_at = -1, sv_accel = 10, sv_maxspd = 320;
	float speed, fmove, smove, ft, wishspeed, a_cap, ideal_step, d_opt, theta_opt;
	float vel_yaw, view_yaw, wish_rel, side, ideal_view = 0, offset = 0, wish_vs_vel = 0, eff_now = 0;
	qbool onground, guide;

	if (!self->stc_mode)
	{
		return;
	}

	if ((self->ct != ctPlayer) || self->isBot || !ISLIVE(self) || !stc_allowed())
	{
		stc_marker_hide(self);
		self->stc_in_air = false;

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

	// accelspeed is capped by sv_accelerate * wishspeed * frametime (41.6 at 77 fps) as well as
	// by addspeed. Below ~106 fps the first cap never limits the best frame, so that frame adds
	// 30^2 = 900 to speed^2 with the wish direction exactly sideways. Above it the cap bites:
	// the best frame is smaller and sits a little short of sideways (d_opt > 0).
	ft = g_globalvars.frametime;
	ft = ((ft <= 0) || (ft > 0.1f)) ? 0.013f : ft;
	wishspeed = sqrt(fmove * fmove + smove * smove);
	wishspeed = ((wishspeed <= 0) || (wishspeed > sv_maxspd)) ? sv_maxspd : wishspeed;
	a_cap = sv_accel * wishspeed * ft;
	d_opt = (a_cap >= STC_AIR_WISH) ? 0 : (STC_AIR_WISH - a_cap);
	ideal_step = (a_cap >= STC_AIR_WISH) ? (STC_AIR_WISH * STC_AIR_WISH) : (a_cap * (2 * STC_AIR_WISH - a_cap));

	// ---- hop bookkeeping: takeoff speed -> landing speed, against what was possible ----
	if (!onground)
	{
		if (!self->stc_in_air)
		{
			self->stc_in_air = true;
			self->stc_takeoff_speed = speed;
			self->stc_ideal_v2 = 0;
			self->stc_air_frames = 0;
			self->stc_last_ground = self->stc_ground_frames;
		}

		self->stc_air_frames++;
		self->stc_ideal_v2 += ideal_step;
	}
	else
	{
		if (self->stc_in_air)
		{
			self->stc_in_air = false;

			if ((self->stc_air_frames >= STC_MIN_HOP_FRAMES) && (self->stc_takeoff_speed >= STC_MIN_SPEED)
					&& (self->stc_ideal_v2 > 0))
			{
				float eff = (speed * speed - self->stc_takeoff_speed * self->stc_takeoff_speed) / self->stc_ideal_v2;

				self->stc_last_gain = speed - self->stc_takeoff_speed;
				self->stc_last_eff = (eff < -0.99f) ? -0.99f : ((eff > 1.5f) ? 1.5f : eff);
				self->stc_have_hop = true;
			}

			self->stc_ground_frames = 0;
		}

		self->stc_ground_frames++;
	}

	// ---- where should the view be right now? ----
	// Needs a strafe key (it picks the turn direction) and some speed. It stays on through
	// landings so nothing blinks between hops.
	guide = (smove != 0) && (speed >= STC_MIN_SPEED);

	if (onground)
	{
		self->stc_plane_z = self->s.v.origin[2] + self->s.v.view_ofs[2];	// standing eye height
	}

	if (guide)
	{
		vel_yaw = atan2(self->s.v.velocity[1], self->s.v.velocity[0]) * 180 / M_PI;
		view_yaw = self->s.v.v_angle[1];
		wish_rel = atan2(-smove, fmove) * 180 / M_PI;	// wish direction relative to the view (right is -90)
		side = (smove < 0) ? 1 : -1;					// strafing left turns you left (yaw grows)

		// best wish direction: sideways to the velocity (or just short of it at very high fps),
		// on the side you are strafing to
		theta_opt = acos(d_opt / speed) * 180 / M_PI;
		ideal_view = vel_yaw + side * theta_opt - wish_rel;
		offset = stc_angdiff(ideal_view, view_yaw);		// + = the orb is to your left

		wish_vs_vel = stc_angdiff(view_yaw + wish_rel, vel_yaw);
		eff_now = stc_frame_eff(speed, wish_vs_vel, a_cap, ideal_step);
	}

	if (guide)
	{
		self->stc_acc_eff += eff_now;
		self->stc_acc_off += offset;
		self->stc_acc_n++;
	}

	// ---- the orb ----
	if (guide && ((self->stc_mode == 1) || (self->stc_mode == 3)))
	{
		gedict_t *m = stc_marker_get(self);
		float jump = stc_angdiff(ideal_view, self->stc_orb_yaw), yaw_r, k;
		vec3_t at;

		// Smooth the yaw so the orb glides. A big jump (keys changed) snaps instead.
		if (!self->stc_orb_live || (jump > 40) || (jump < -40))
		{
			self->stc_orb_yaw = ideal_view;
			self->stc_orb_live = true;
		}
		else
		{
			k = ft / (STC_ORB_TAU + ft);
			self->stc_orb_yaw += jump * k;
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
		self->stc_lead = (lead < 0) ? 0 : ((lead > STC_MAX_LEAD) ? STC_MAX_LEAD : lead);

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

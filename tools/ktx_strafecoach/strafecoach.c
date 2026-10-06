/*
 * Strafe coach (DeepFrag) -- an opt-in bunnyhop / circle-jump trainer.
 *
 * THE PHYSICS
 *
 * QuakeWorld adds speed along the direction your movement keys point (the "push"), but
 * only up to a cap of speed measured ALONG that direction:
 *
 *     addspeed   = CAP - dot(velocity, push)
 *     accelspeed = min(sv_accelerate * wishspeed * frametime, addspeed)
 *     velocity  += accelspeed * push
 *
 * In the AIR the cap is 30. Measure the push from your direction of travel:
 *
 *     0 .. 85 degrees   nothing happens (you already move faster than 30 that way)
 *     86 .. 92          you gain, most at exactly 90 (sideways)
 *     93 and beyond     you LOSE, and fast: past sideways the push points partly backward
 *                       and the engine pushes harder there (up to 41.6 a frame, against a
 *                       best gain of ~1). A flick to 180 costs 42 ups every frame.
 *
 * Gaining speed turns your direction of travel, so the window turns with it. A bunnyhop is
 * a smooth sweep, and speed is bought with turning: about half a unit of speed per degree
 * your direction of travel turns. Switching strafe key and reversing the sweep (zig-zag)
 * buys the same speed as one long sweep, so corridors cost nothing in theory.
 *
 * The window is asin(30 / speed) wide: 4.3 degrees at 400, 2.6 at 650. That is why it gets
 * harder to keep gaining the faster you go.
 *
 * On the GROUND the cap is your full wish speed (320) and friction eats ~5% a frame.
 * Aiming ~35 degrees off your direction of travel still nets speed, up to an equilibrium
 * near 485. That run-up is the circle jump: what you carry into your first hop.
 *
 * The server knows the keys held (self->movement), the view angle (v_angle) and the
 * velocity the move is about to use, every client frame, so all of this is exact.
 *
 * WHAT THE PLAYER SEES -- one centerprint block, "scpos <rows>" moves it down the screen:
 *
 *              437                    speed
 *         <<   ###--                  meter = how hard you are gaining right now;
 *                                     arrows = turn that way (they stick for a moment)
 *        last +22   avg +18           last hop, and the average of your last 10
 *        TOO FAR  lost 12             the mistake you just made and what it cost
 *
 *     +19  455                        your last five hops, newest first, set to the left
 *     -12  436  too far
 *     circle jump 448
 *
 *   Mistakes called out: TOO FAR (turned past sideways, the push went backward),
 *   LATE JUMP (touched down without jump held, friction took speed), HIT A WALL,
 *   TURN MORE (a whole hop with the push too far forward to gain), NO STRAFE KEY.
 *
 *   ORB: in the air a PACER. It starts where your view should be and sweeps the way you
 *   are strafing at a set rate ("scpace": 45 / 60 / 75 / 90 / 120 deg/sec; good players
 *   sweep at about 60). It waits if you fall far behind, re-anchors every hop and every
 *   time you switch strafe key, and stays up through the short gap a key switch leaves.
 *   On the ground it shows the best aim for the run-up. Fixed distance (constant size),
 *   on the plane of your standing eye height (no bobbing), led by your ping.
 *
 * "strafecoach" (or "scoach") cycles: HUD + orb, HUD only, orb only, off. A player with no
 * saved choice starts in the mode k_strafecoach_default names (1 on the coach port).
 * A practice aid: only runs outside a live match unless k_strafecoach_match is set.
 *
 * SESSIONS. A session starts at your first hop and ends on "scend", on turning the coach off,
 * on disconnect or map change, or after two minutes without a hop. You get a summary (hops,
 * average gain, best chain, top speed, mistakes) and the same line is appended as JSON to
 * demos/strafecoach_sessions.txt, which QTV serves over http: the DeepFrag API reads it from
 * there and shows your sessions on the Movement card. "scstats" shows the running session.
 */

#include "g_local.h"

#define STC_MODEL			"progs/s_light.spr"	// id1 light globe: a sprite, so it always faces you
#define STC_TICK_SOUND		"misc/menu2.wav"	// played to the player alone on a mistake
#define STC_REFRESH			0.1f				// HUD refresh, seconds
#define STC_DIST			320.0f				// the orb is always this far away, so its size never changes
#define STC_AIR_WISH		30.0f				// PM_AirAccelerate's wishspeed cap
#define STC_FRICTION		4.0f				// sv_friction
#define STC_STOPSPEED		100.0f				// sv_stopspeed
#define STC_MIN_SPEED		200.0f				// below this there is nothing to coach
#define STC_MIN_HOP_FRAMES	15					// ignore stair steps and tiny drops
#define STC_MAX_LEAD		0.15f				// never lead the orb by more than this many seconds
#define STC_PACE_DEFAULT	60					// pacer sweep, deg/sec: what the top quarter of duel players do
#define STC_PACE_WAIT		20.0f				// the pacer stops while it is this far ahead of your view
#define STC_GROUND_SETTLE	3					// ground frames in a row before ground maths applies
#define STC_CHAIN_BREAK		20					// ground frames in a row that end a hop chain (~0.27 s)
#define STC_LATCH			0.35f				// orb + arrows survive a guidance gap this long (key switches)
#define STC_EMA_TAU			0.25f				// smoothing of the meter and arrows, seconds
#define STC_MISS_SHOW		1.5f				// a mistake stays on screen this long
#define STC_HUD_ROW_DEFAULT	14					// blank rows above the block
#define STC_HIST			10					// hops remembered
#define STC_HIST_SHOWN		5
#define STC_LINE			40					// a centerprint line is at most 40 characters
#define STC_SESSION_IDLE	120.0f				// seconds without a hop that close a session
#define STC_SESSION_MIN		10					// hops a session needs before it is kept
#define STC_SESSION_LOG		"demos/strafecoach_sessions.txt"	// under the mod dir: QTV serves demos/ over http
#define STC_TIME_FMT		"%Y-%m-%dT%H:%M:%SZ"				// the box keeps UTC

enum
{
	STC_MISS_NONE = 0,
	STC_MISS_CJ,			// not a mistake: marks the circle jump in the history
	STC_MISS_TOOFAR,		// push went past sideways: speed lost
	STC_MISS_WALL,
	STC_MISS_LATE,			// touched down without jump held
	STC_MISS_TURNMORE,		// push too far forward all hop: nothing gained
	STC_MISS_NOKEY
};

static const char *stc_miss_short[] = { "", "", "too far", "wall", "late jump", "turn more", "no strafe" };
static const char *stc_miss_long[] = { "", "", "TOO FAR", "HIT A WALL", "LATE JUMP", "TURN MORE", "NO STRAFE KEY" };

static const int stc_paces[] = { 45, 60, 75, 90, 120 };
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

static int stc_round(float v)
{
	return (int)floor(v + 0.5f);
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

// Copy `src` into `dst` as Quake's red text (high bit set), leaving spaces alone.
static void stc_red(char *dst, int size, const char *src)
{
	int i;

	for (i = 0; src[i] && (i < size - 1); i++)
	{
		dst[i] = (src[i] > ' ') ? (char)(src[i] | 0x80) : src[i];
	}

	dst[i] = 0;
}

static void stc_reset_stats(gedict_t *p)
{
	p->stc_in_air = false;
	p->stc_takeoff_speed = 0;
	p->stc_land_speed = 0;
	p->stc_air_frames = 0;
	p->stc_ground_frames = 0;
	p->stc_chain_hops = 0;
	p->stc_next_draw = 0;
	p->stc_orb_live = false;
	p->stc_orb_side = 0;
	p->stc_guide_until = 0;
	p->stc_ema_eff = 0;
	p->stc_ema_off = 0;
	p->stc_prev_air = false;
	p->stc_burst_loss = 0;
	p->stc_losing_frames = 0;
	p->stc_hop_loss = 0;
	p->stc_hop_bump = 0;
	p->stc_hop_late = 0;
	p->stc_dead_frames = 0;
	p->stc_nokey_frames = 0;
	p->stc_miss_kind = STC_MISS_NONE;
	p->stc_miss_until = 0;
	p->stc_next_tick = 0;
	p->stc_h_n = 0;
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

// One frame of PM_Accelerate / PM_AirAccelerate for a push at `push_vs_vel_deg` from the
// velocity, as a share of the best frame possible (negative = speed lost). cap = 30 in the
// air, the full wish speed on the ground. d = speed along the push.
//   addspeed = cap - d;  accelspeed = min(a_cap, addspeed);  speed^2 changes by 2*a*d + a*a
static float stc_frame_eff(float speed, float push_vs_vel_deg, float cap, float a_cap, float ideal_step)
{
	float d = speed * cos(push_vs_vel_deg * M_PI / 180);
	float a = stc_clamp(cap - d, 0, a_cap);

	return ((2 * a * d + a * a) / ideal_step);
}

// Call a mistake out: on the HUD for a moment, and with a tick only the player hears.
static void stc_miss(gedict_t *p, int kind, float cost)
{
	p->stc_miss_kind = kind;
	p->stc_miss_cost = cost;
	p->stc_miss_until = g_globalvars.time + STC_MISS_SHOW;

	if (p->stc_sound && (g_globalvars.time >= p->stc_next_tick))
	{
		p->stc_next_tick = g_globalvars.time + 0.6f;
		stuffcmd_flags(p, STUFFCMD_IGNOREINDEMO, "play " STC_TICK_SOUND "\n");
	}
}

static void stc_hist_push(gedict_t *p, float gain, float speed, int tag)
{
	int i = p->stc_h_n % STC_HIST;

	p->stc_h_gain[i] = gain;
	p->stc_h_speed[i] = speed;
	p->stc_h_tag[i] = tag;
	p->stc_h_n++;
}

// ---- sessions ----

static void stc_session_clear(gedict_t *p)
{
	int i;

	p->stc_s_active = false;
	p->stc_s_start[0] = 0;
	p->stc_s_t0 = 0;
	p->stc_s_last = 0;
	p->stc_s_hops = 0;
	p->stc_s_gaining = 0;
	p->stc_s_best_chain = 0;
	p->stc_s_gain_sum = 0;
	p->stc_s_best_hop = 0;
	p->stc_s_top_speed = 0;
	p->stc_s_best_cj = 0;
	p->stc_s_lost = 0;

	for (i = 0; i < 7; i++)
	{
		p->stc_s_miss[i] = 0;
	}
}

// Every counted hop feeds the session; the first one starts it.
static void stc_session_hop(gedict_t *p, float gain, float speed, int tag, float lost)
{
	if (!p->stc_s_active)
	{
		stc_session_clear(p);
		p->stc_s_active = true;
		p->stc_s_t0 = g_globalvars.time;

		if (!QVMstrftime(p->stc_s_start, sizeof(p->stc_s_start), STC_TIME_FMT, 0))
		{
			p->stc_s_start[0] = 0;
		}
	}

	p->stc_s_last = g_globalvars.time;
	p->stc_s_hops++;
	p->stc_s_gain_sum += gain;
	p->stc_s_lost += lost;
	p->stc_s_gaining += (gain >= 4) ? 1 : 0;
	p->stc_s_best_hop = (gain > p->stc_s_best_hop) ? gain : p->stc_s_best_hop;
	p->stc_s_top_speed = (speed > p->stc_s_top_speed) ? speed : p->stc_s_top_speed;
	p->stc_s_best_chain = (p->stc_chain_hops > p->stc_s_best_chain) ? p->stc_chain_hops : p->stc_s_best_chain;

	if ((tag == STC_MISS_CJ) && (speed > p->stc_s_best_cj))
	{
		p->stc_s_best_cj = speed;
	}

	if ((tag > STC_MISS_CJ) && (tag < 7))
	{
		p->stc_s_miss[tag]++;
	}
}

static int stc_session_misses(gedict_t *p)
{
	return (p->stc_s_miss[STC_MISS_TOOFAR] + p->stc_s_miss[STC_MISS_WALL] + p->stc_s_miss[STC_MISS_LATE]
			+ p->stc_s_miss[STC_MISS_TURNMORE] + p->stc_s_miss[STC_MISS_NOKEY]);
}

// The session in words, to the player.
static void stc_session_say(gedict_t *p, const char *head)
{
	float avg = p->stc_s_hops ? (p->stc_s_gain_sum / p->stc_s_hops) : 0;
	int gaining = p->stc_s_hops ? stc_round(100.0f * p->stc_s_gaining / p->stc_s_hops) : 0;

	G_sprint(p, PRINT_HIGH, "%s: %d hops in %d min, avg %+d a hop, %d%% gaining, best hop %+d, best chain %d, top speed %d, circle jump %d\n",
				head, p->stc_s_hops, stc_round((p->stc_s_last - p->stc_s_t0) / 60), stc_round(avg), gaining,
				stc_round(p->stc_s_best_hop), p->stc_s_best_chain, stc_round(p->stc_s_top_speed), stc_round(p->stc_s_best_cj));

	if (stc_session_misses(p))
	{
		G_sprint(p, PRINT_HIGH, "  mistakes: too far %d, wall %d, late jump %d, turn more %d, no strafe key %d (cost %d ups)\n",
					p->stc_s_miss[STC_MISS_TOOFAR], p->stc_s_miss[STC_MISS_WALL], p->stc_s_miss[STC_MISS_LATE],
					p->stc_s_miss[STC_MISS_TURNMORE], p->stc_s_miss[STC_MISS_NOKEY], stc_round(p->stc_s_lost));
	}
}

// A player's name as plain JSON text: Quake's fun characters mapped back to plain ones, quotes
// and backslashes escaped.
static void stc_json_name(char *dst, int size, const char *src)
{
	int i, n = 0;

	for (i = 0; src[i] && (n < size - 3); i++)
	{
		unsigned char c = (unsigned char)src[i] & 0x7f;

		if ((c >= 18) && (c <= 27))
		{
			c = '0' + (c - 18);		// fun digits
		}
		else if ((c < 32) || (c == 127))
		{
			c = '_';
		}

		if ((c == '"') || (c == '\\'))
		{
			dst[n++] = '\\';
		}

		dst[n++] = (char)c;
	}

	dst[n] = 0;
}

// Close the session: tell the player, append the line. Short ones are dropped.
static void stc_session_end(gedict_t *p, const char *reason)
{
	fileHandle_t h;
	char name[64], line[512], end[24];
	float avg;

	if (!p->stc_s_active)
	{
		return;
	}

	p->stc_s_active = false;

	if (p->stc_s_hops < STC_SESSION_MIN)
	{
		if (streq(reason, "scend"))
		{
			G_sprint(p, PRINT_HIGH, "Strafe coach: only %d hops, not kept (a session is %d or more).\n", p->stc_s_hops, STC_SESSION_MIN);
		}

		return;
	}

	stc_session_say(p, "Strafe coach session");

	if (!QVMstrftime(end, sizeof(end), STC_TIME_FMT, 0))
	{
		end[0] = 0;
	}

	stc_json_name(name, sizeof(name), getname(p));
	avg = p->stc_s_gain_sum / p->stc_s_hops;
	snprintf(line, sizeof(line),
				"{\"v\":1,\"name\":\"%s\",\"start\":\"%s\",\"end\":\"%s\",\"map\":\"%s\",\"min\":%.1f,\"hops\":%d,\"gaining\":%d,"
				"\"avg\":%.1f,\"best_hop\":%.1f,\"best_chain\":%d,\"top_speed\":%d,\"cj\":%d,\"pace\":%d,\"lost\":%d,"
				"\"miss\":{\"too_far\":%d,\"wall\":%d,\"late\":%d,\"turn_more\":%d,\"no_key\":%d},\"reason\":\"%s\"}\n",
				name, p->stc_s_start, end, mapname, (p->stc_s_last - p->stc_s_t0) / 60, p->stc_s_hops, p->stc_s_gaining,
				avg, p->stc_s_best_hop, p->stc_s_best_chain, stc_round(p->stc_s_top_speed), stc_round(p->stc_s_best_cj),
				p->stc_pace, stc_round(p->stc_s_lost), p->stc_s_miss[STC_MISS_TOOFAR], p->stc_s_miss[STC_MISS_WALL],
				p->stc_s_miss[STC_MISS_LATE], p->stc_s_miss[STC_MISS_TURNMORE], p->stc_s_miss[STC_MISS_NOKEY], reason);

	if (trap_FS_OpenFile(STC_SESSION_LOG, &h, FS_APPEND_TXT) >= 0)
	{
		trap_FS_WriteFile(line, strlen(line), h);
		trap_FS_CloseFile(h);
	}
	else
	{
		G_cprint("strafecoach: cannot append to %s\n", STC_SESSION_LOG);
	}

	G_cprint("strafecoach session %s", line);
}

// Map change or server stop: close every running session while the players are still here.
void StrafeCoachShutdown(void)
{
	gedict_t *p;

	for (p = world; (p = find_plr(p));)
	{
		stc_session_end(p, "mapchange");
	}
}

// "scend": close the running session now; the next hop starts a new one.
void StrafeCoachEndCmd(void)
{
	if (!self->stc_s_active)
	{
		G_sprint(self, PRINT_HIGH, "Strafe coach: no session running. One starts with your first hop.\n");

		return;
	}

	stc_session_end(self, "scend");
}

// "scstats": the running session so far.
void StrafeCoachStatsCmd(void)
{
	if (!self->stc_s_active)
	{
		G_sprint(self, PRINT_HIGH, "Strafe coach: no session running. One starts with your first hop.\n");

		return;
	}

	stc_session_say(self, "Strafe coach session so far");
}

// What a steady sweep at `pace` deg/sec gains over one flat hop (52 frames) at `speed`.
static float stc_pace_gain(float speed, float pace, float ft)
{
	float a = speed * (pace * M_PI / 180) * ft;
	float d = STC_AIR_WISH - ((a > STC_AIR_WISH) ? STC_AIR_WISH : a);

	return (sqrt(speed * speed + (STC_AIR_WISH * STC_AIR_WISH - d * d) * 52) - speed);
}

// The whole display is ONE centerprint. With more than four lines the client starts it 48
// pixels from the top, so the blank rows in front decide how low it sits (scpos). A line is
// centred inside a 40-column box, so padding a line with trailing spaces slides it left:
// that is how the hop history ends up down and to the left of the main lines.
static void stc_print(gedict_t *p, float speed, qbool live, qbool ground, qbool strafing)
{
	char buf[1024], line[64], red[64];
	int len = 0, i, n, shown, arrows, cells;
	float off = p->stc_ema_off, off_abs = (off < 0) ? -off : off, sum;

#define STC_ADD(...) do { if (len < (int)sizeof(buf) - 1) { len += snprintf(buf + len, sizeof(buf) - len, __VA_ARGS__); \
							if (len > (int)sizeof(buf) - 1) len = sizeof(buf) - 1; } } while (0)

	for (i = 0; i < p->stc_hud_row; i++)
	{
		STC_ADD("\n");
	}

	// 1: speed
	STC_ADD("%d\n", (int)speed);

	// 2: arrows + meter. Arrows = which way the best aim is; they come from a smoothed value
	//    so they hold still long enough to read. Meter = how hard you are gaining right now.
	if (live)
	{
		arrows = (off_abs >= 8) ? 3 : ((off_abs >= 4) ? 2 : ((off_abs >= 1.5f) ? 1 : 0));

		if (p->stc_losing_frames >= 2)	// losing speed right now, not a moment ago
		{
			stc_red(red, sizeof(red), "LOSING");
			snprintf(line, sizeof(line), "%s", red);
		}
		else
		{
			cells = stc_round(stc_clamp(p->stc_ema_eff / 0.5f, 0, 1) * 5);

			for (i = 0; i < 5; i++)
			{
				line[i] = (i < cells) ? (char)('#' | 0x80) : '-';
			}

			line[5] = 0;
		}

		if (off > 0)		// the best aim is to your LEFT
		{
			STC_ADD("%.*s%*s  %s     \n", arrows, "\xbc\xbc\xbc", 3 - arrows, "", line);
		}
		else
		{
			STC_ADD("     %s  %*s%.*s\n", line, 3 - arrows, "", arrows, "\xbe\xbe\xbe");
		}
	}
	else
	{
		STC_ADD("%s\n", ((speed >= STC_MIN_SPEED) && !strafing && !ground) ? "hold a strafe key" : " ");
	}

	// 3: last hop + average of the last 10
	n = (p->stc_h_n < STC_HIST) ? p->stc_h_n : STC_HIST;

	if (n > 0)
	{
		int last = (p->stc_h_n - 1) % STC_HIST;

		for (sum = 0, i = 0; i < n; i++)
		{
			sum += p->stc_h_gain[i];
		}

		STC_ADD("last %+d   avg %+d\n", stc_round(p->stc_h_gain[last]), stc_round(sum / n));
	}
	else
	{
		STC_ADD(" \n");
	}

	// 4: the mistake you just made, and what it cost
	if ((p->stc_miss_kind > STC_MISS_CJ) && (g_globalvars.time < p->stc_miss_until))
	{
		if (p->stc_miss_cost >= 1)
		{
			snprintf(line, sizeof(line), "%s  lost %d", stc_miss_long[p->stc_miss_kind], stc_round(p->stc_miss_cost));
		}
		else
		{
			snprintf(line, sizeof(line), "%s", stc_miss_long[p->stc_miss_kind]);
		}

		stc_red(red, sizeof(red), line);
		STC_ADD("%s\n", red);
	}
	else
	{
		STC_ADD(" \n");
	}

	// 5..: the last five hops, newest first, pushed to the left edge of the 40-column box
	STC_ADD(" \n");
	shown = (n < STC_HIST_SHOWN) ? n : STC_HIST_SHOWN;

	for (i = 0; i < STC_HIST_SHOWN; i++)
	{
		if (i < shown)
		{
			int k = (p->stc_h_n - 1 - i) % STC_HIST, tag = p->stc_h_tag[k];

			if (tag == STC_MISS_CJ)
			{
				snprintf(line, sizeof(line), "circle jump %d", stc_round(p->stc_h_speed[k]));
			}
			else if (tag > STC_MISS_CJ)
			{
				snprintf(line, sizeof(line), "%+4d  %d  %s", stc_round(p->stc_h_gain[k]), stc_round(p->stc_h_speed[k]),
							stc_miss_short[tag]);
				stc_red(red, sizeof(red), line);
				snprintf(line, sizeof(line), "%s", red);
			}
			else
			{
				snprintf(line, sizeof(line), "%+4d  %d", stc_round(p->stc_h_gain[k]), stc_round(p->stc_h_speed[k]));
			}

			STC_ADD("%-*.*s\n", STC_LINE, STC_LINE, line);
		}
		else
		{
			STC_ADD(" \n");
		}
	}

#undef STC_ADD

	G_centerprint(p, "%s", buf);
}

// The coach runs as its own mod file on its own port (sv_progsname qwprogs_coach). When a
// server empties, KTX execs configs/reset.cfg -> server.cfg -> mvdsv.cfg, which sets
// sv_progsname back to "qwprogs": the next map change would then load the stock mod and the
// coach would silently vanish. The port config names the file it wants in k_stc_progs, and
// this guard puts sv_progsname back every few seconds. No effect when k_stc_progs is unset.
static void stc_guard_think(void)
{
	char *want = cvar_string("k_stc_progs");

	if (want && want[0] && !streq(cvar_string("sv_progsname"), want))
	{
		localcmd("sv_progsname \"%s\"\n", want);
	}

	self->s.v.nextthink = g_globalvars.time + 3;
}

void StrafeCoachPrecache(void)
{
	gedict_t *guard;

	trap_precache_model(STC_MODEL);

	guard = spawn();
	guard->classname = "stc_guard";
	guard->think = (func_t) stc_guard_think;
	guard->s.v.nextthink = g_globalvars.time + 3;
}

// Called once per (re)connect, i.e. also after every map change. The settings survive in the
// client's userinfo (setinfo stc / stcp / stcy / stcs) so the coach stays as you left it. No
// saved choice at all (a fresh client) means the server's default, k_strafecoach_default.
void StrafeCoachConnect(gedict_t *p)
{
	char *mode_s = ezinfokey(p, "stc"), *snd = ezinfokey(p, "stcs");
	int mode = (mode_s && mode_s[0]) ? atoi(mode_s) : (int)cvar("k_strafecoach_default");
	int pace = iKey(p, "stcp"), row = iKey(p, "stcy");

	stc_session_clear(p);
	p->stc_marker = NULL;
	p->stc_marker_shown = false;
	p->stc_lead = 0;
	p->stc_plane_z = 0;
	p->stc_ground_run = 0;
	p->stc_mode = (mode < 0 || mode > 3) ? 0 : mode;
	p->stc_pace = (pace < 30 || pace > 300) ? STC_PACE_DEFAULT : pace;
	p->stc_hud_row = (row < 1 || row > 80) ? STC_HUD_ROW_DEFAULT : row;
	p->stc_sound = (snd && snd[0] == '0') ? 0 : 1;
	stc_reset_stats(p);
}

void StrafeCoachDisconnect(gedict_t *p)
{
	stc_session_end(p, "disconnect");
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

	if (!self->stc_hud_row)
	{
		self->stc_hud_row = STC_HUD_ROW_DEFAULT;
		self->stc_sound = 1;
	}

	if (!self->stc_mode)
	{
		stc_session_end(self, "off");
		stc_marker_remove(self);
		G_centerprint(self, " ");
	}

	stuffcmd_flags(self, STUFFCMD_IGNOREINDEMO, "setinfo stc %d\n", self->stc_mode);
	G_sprint(self, PRINT_HIGH, "Strafe coach: %s\n", redtext(names[self->stc_mode]));

	if (self->stc_mode == 1)
	{
		G_sprint(self, PRINT_HIGH, "In the air: hold a strafe key and sweep the mouse the same way.\n"
					"Meter = how hard you are gaining. Arrows = turn that way. Red text = the mistake you just made.\n"
					"The orb sweeps at %d deg/sec: keep your crosshair on it.\n"
					"scpace = orb speed, scpos <rows> = move the display down, scsound = mistake sound.\n"
					"A session starts with your first hop: scstats shows it, scend closes it (so does 2 min without a hop).\n",
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
	G_sprint(self, PRINT_HIGH, "Strafe coach pace: %s deg/sec (about %+d a hop at 400 speed)\n", dig3(self->stc_pace),
				stc_round(stc_pace_gain(400, self->stc_pace, 0.013f)));
}

// "scpos <rows>": how many blank rows sit above the display. Bigger = lower on the screen.
void StrafeCoachPosCmd(void)
{
	char arg[16];

	if (trap_CmdArgc() < 2)
	{
		G_sprint(self, PRINT_HIGH, "scpos <rows>: the display sits %s rows down. Bigger = lower (1 to 80).\n",
					dig3(self->stc_hud_row ? self->stc_hud_row : STC_HUD_ROW_DEFAULT));

		return;
	}

	trap_CmdArgv(1, arg, sizeof(arg));
	self->stc_hud_row = (int)stc_clamp(atoi(arg), 1, 80);
	self->stc_next_draw = 0;
	stuffcmd_flags(self, STUFFCMD_IGNOREINDEMO, "setinfo stcy %d\n", self->stc_hud_row);
	G_sprint(self, PRINT_HIGH, "Strafe coach display: %s rows down\n", dig3(self->stc_hud_row));
}

// "scsound": the tick that plays when you make a mistake.
void StrafeCoachSoundCmd(void)
{
	self->stc_sound = !self->stc_sound;
	stuffcmd_flags(self, STUFFCMD_IGNOREINDEMO, "setinfo stcs %d\n", self->stc_sound);
	G_sprint(self, PRINT_HIGH, "Strafe coach mistake sound: %s\n", redtext(self->stc_sound ? "on" : "off"));
}

// Runs from PlayerPreThink: self->movement holds this command's keys and velocity is what
// the move is about to use, so the answer is exact for this frame.
void StrafeCoachFrame(void)
{
	static float cached_at = -1, sv_accel = 10, sv_maxspd = 320;
	float speed, v_eff, fmove, smove, ft, wishspeed, cap, a_cap, ideal_step, d_opt, theta_opt, k_ema;
	float vel_yaw, view_yaw, wish_rel = 0, side = 0, ideal_view = 0, offset = 0, push_vs_vel = 0, eff_now = 0, g2 = 0;
	qbool onground, ground_phys, took_off = false, guide, live;

	if (!self->stc_mode)
	{
		return;
	}

	// a session that has gone quiet closes itself
	if (self->stc_s_active && (g_globalvars.time - self->stc_s_last > STC_SESSION_IDLE))
	{
		stc_session_end(self, "idle");
	}

	if ((self->ct != ctPlayer) || self->isBot || !ISLIVE(self) || !stc_allowed())
	{
		stc_marker_hide(self);
		self->stc_in_air = false;
		self->stc_orb_live = false;
		self->stc_prev_air = false;

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
	vel_yaw = (speed > 1) ? (atan2(self->s.v.velocity[1], self->s.v.velocity[0]) * 180 / M_PI) : self->s.v.v_angle[1];
	view_yaw = self->s.v.v_angle[1];

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

	// The best frame: accelspeed limited only by a_cap, with the push as far along the
	// velocity as that allows (d_opt). In the air at 77 fps a_cap > 30, so d_opt = 0:
	// exactly sideways. On the ground d_opt = 320 - 43 = 277.
	d_opt = (a_cap >= cap) ? 0 : (cap - a_cap);
	ideal_step = (a_cap >= cap) ? (cap * cap) : (a_cap * (2 * cap - a_cap));

	// ---- did something other than the push take speed? (a wall, a ledge, another player) ----
	if (self->stc_prev_air && !onground && (self->stc_prev_pred - speed > 12) && (self->stc_prev_speed >= STC_MIN_SPEED))
	{
		float cost = self->stc_prev_pred - speed;

		self->stc_hop_bump += cost;
		stc_miss(self, STC_MISS_WALL, cost);
	}

	// ---- hop bookkeeping ----
	if (!onground)
	{
		if (!self->stc_in_air)
		{
			self->stc_in_air = true;
			took_off = true;
			self->stc_takeoff_speed = speed;
			self->stc_air_frames = 0;
			self->stc_hop_loss = 0;
			self->stc_hop_bump = 0;
			self->stc_hop_late = 0;
			self->stc_dead_frames = 0;
			self->stc_nokey_frames = 0;
			self->stc_burst_loss = 0;

			// Mid-run touch-down that sat on the ground: friction took speed. Holding jump
			// through the landing costs nothing.
			if ((self->stc_chain_hops >= 1) && (self->stc_ground_frames >= 2)
					&& (self->stc_land_speed - speed > 6))
			{
				self->stc_hop_late = self->stc_land_speed - speed;
				stc_miss(self, STC_MISS_LATE, self->stc_hop_late);
			}
		}

		self->stc_air_frames++;
	}
	else
	{
		if (self->stc_in_air)
		{
			self->stc_in_air = false;
			self->stc_land_speed = speed;

			if ((self->stc_air_frames >= STC_MIN_HOP_FRAMES) && (self->stc_takeoff_speed >= 150))
			{
				float gain = speed - self->stc_takeoff_speed;
				int tag = STC_MISS_NONE;

				self->stc_chain_hops++;

				// what, if anything, went wrong on this hop: the costliest thing wins
				if ((self->stc_hop_loss >= 5) && (self->stc_hop_loss >= self->stc_hop_bump))
				{
					tag = STC_MISS_TOOFAR;
				}
				else if (self->stc_hop_bump >= 12)
				{
					tag = STC_MISS_WALL;
				}
				else if (self->stc_hop_late > 6)
				{
					tag = STC_MISS_LATE;
				}
				else if ((self->stc_nokey_frames * 10 > self->stc_air_frames * 7) && (gain < 4))
				{
					tag = STC_MISS_NOKEY;
					stc_miss(self, tag, 0);
				}
				else if ((self->stc_dead_frames * 10 > self->stc_air_frames * 7) && (gain < 4))
				{
					tag = STC_MISS_TURNMORE;
					stc_miss(self, tag, 0);
				}
				else if (self->stc_chain_hops == 1)
				{
					tag = STC_MISS_CJ;		// the first hop of a run: what the circle jump reached
				}

				stc_hist_push(self, gain, speed, tag);
				stc_session_hop(self, gain, speed, tag, self->stc_hop_loss + self->stc_hop_bump + self->stc_hop_late);
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
		wish_rel = atan2(-smove, fmove) * 180 / M_PI;	// the push relative to the view (right is -90)
		side = (smove < 0) ? 1 : -1;					// strafing left turns you left (yaw grows)

		// best push: theta_opt off the velocity, on the side you are strafing to.
		// Air: 90 degrees (sideways). Ground: ~35 at 360 ups, 0 below 277 (just run straight).
		theta_opt = acos(stc_clamp(d_opt / v_eff, -1, 1)) * 180 / M_PI;
		ideal_view = vel_yaw + side * theta_opt - wish_rel;
		offset = stc_angdiff(ideal_view, view_yaw);		// + = the best aim is to your left

		push_vs_vel = stc_angdiff(view_yaw + wish_rel, vel_yaw);
		eff_now = stc_frame_eff(v_eff, push_vs_vel, cap, a_cap, ideal_step);
		g2 = eff_now * ideal_step;						// what this frame does to speed^2

		k_ema = ft / (STC_EMA_TAU + ft);
		self->stc_ema_eff += (stc_clamp(eff_now, 0, 1) - self->stc_ema_eff) * k_ema;
		self->stc_ema_off += (offset - self->stc_ema_off) * k_ema;
		self->stc_guide_until = g_globalvars.time + STC_LATCH;

		// ---- mistakes, as they happen ----
		if (!ground_phys)
		{
			if (g2 < 0)
			{
				// past sideways: the push is taking speed away
				float cost = speed - sqrt((speed * speed + g2 > 0) ? (speed * speed + g2) : 0);

				self->stc_burst_loss += cost;
				self->stc_hop_loss += cost;
				self->stc_losing_frames++;

				if (self->stc_burst_loss >= 4)
				{
					stc_miss(self, STC_MISS_TOOFAR, self->stc_hop_loss);
				}
			}
			else
			{
				self->stc_burst_loss = 0;

				if (eff_now <= 0)
				{
					self->stc_dead_frames++;	// push too far forward: nothing gained this frame
				}
			}
		}
	}
	else if (!onground && (speed >= STC_MIN_SPEED))
	{
		self->stc_nokey_frames++;
	}

	// what the push alone should make the speed next frame (to spot walls)
	self->stc_prev_air = !onground;
	self->stc_prev_speed = speed;
	self->stc_prev_pred = sqrt((speed * speed + g2 > 0) ? (speed * speed + g2) : 0);

	// Switching strafe key leaves a few frames with no key at all (and sv_safestrafe adds
	// more). Keep the orb and the arrows up through that gap instead of blinking.
	live = guide || ((g_globalvars.time < self->stc_guide_until) && (speed >= STC_MIN_SPEED));

	// ---- the orb ----
	if (live && ((self->stc_mode == 1) || (self->stc_mode == 3)))
	{
		gedict_t *m = stc_marker_get(self);
		float yaw_r;
		vec3_t at;

		if (!guide)
		{
			// in the gap: hold it where it is
			if (!self->stc_orb_live)
			{
				self->stc_orb_yaw = view_yaw;
				self->stc_orb_live = true;
			}
		}
		else if (ground_phys)
		{
			// run-up: the best aim right now. No smoothing: on the ground the best aim itself
			// sweeps fast (that sweep IS the circle jump), and lag would point well behind it.
			self->stc_orb_yaw = ideal_view;
			self->stc_orb_live = true;
			self->stc_orb_side = 0;				// 0 = not a pacer anchor
		}
		else
		{
			// in the air: a pacer. Sweeping the view at `pace` settles with the push trailing
			// sideways by exactly the angle where one frame's gain turns the velocity at that
			// same pace: accelspeed = speed * pace * frametime, so d = 30 - that.
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
		m->s.v.effects = (guide && (eff_now >= 0.10f)) ? EF_BLUE : 0;	// glows while you are gaining speed

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
			stc_print(self, speed, live, ground_phys, smove != 0);
		}

		self->stc_losing_frames = 0;
	}
}

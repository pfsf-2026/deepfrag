# KTX strafe coach

An opt-in air-strafe trainer built into a patched KTX. Runs on its own port so the match servers and the
nightly rebuild are untouched.

- **Where:** Denver `den.qwsrv.com:29001` ("DeepFrag Denver Strafe Coach"), unit `qw-coach.service`,
  config `/opt/qw/nquakesv/ktx/port_29001.cfg`, mod file `ktx/qwprogs_coach.so` (`sv_progsname qwprogs_coach`).
- **Source on the box:** `/opt/qw/coach/` holds its own KTX checkout, `strafecoach.patch` and `build_coach.sh`.
  The nightly `qw-update` wipes `/opt/qw/nquakesv/build/ktx`, so the patch must never live there.
- **Rebuild:** copy a new `strafecoach.patch` to `/opt/qw/coach/`, then
  `sudo -u qw -H bash /opt/qw/coach/build_coach.sh [ktx-commit]` and change map (or
  `systemctl restart qw-coach`). Pinned to KTX `f67d6cc5`; bump it if mvdsv's game API changes.
- **In game:** `strafecoach` (or `scoach`) cycles HUD + orb, HUD only, orb only, off. `scpace` changes the orb's sweep speed. The choice is kept in
  the client's userinfo (`setinfo stc N`) so it survives map changes. Only runs outside a live match
  (prewar, race, practice) unless `k_strafecoach_match 1`.
- **Map:** the coach port defaults to `speed` (wide open, Peter's old training map). `speed2`, `rawspeed` and
  `speedrush` are on the box too.

## What it shows (v3)

**The physics.** QuakeWorld adds speed along the direction your keys point, capped at a speed measured along
that direction. In the air the cap is 30, so a frame gains the most when that direction is exactly sideways to
your velocity, and the window that gains anything is only a few degrees wide. As you gain, your velocity turns
and the window turns with it. So a bunnyhop is a smooth mouse sweep, and **what you gain is set by how fast
you sweep while staying in the window**. On the ground the cap is your full run speed (320) and friction takes
about 5% a frame; aiming ~35 degrees off your direction of travel still nets speed, up to an equilibrium near
485. That run-up is the circle jump.

Holding the perfect angle every air frame is 100% and the maximum gain, but at 400 ups it needs a ~300 deg/s
sweep and would spin you 200 degrees in one hop. Nobody does. From the physics simulation at 400 ups:

| sweep | gain per hop | share of the possible gain |
|---|---|---|
| none | +1 | 1% |
| 60 deg/s | +20 | 35% |
| 90 deg/s | +27 | 47% |
| 120 deg/s | +34 | 62% |
| 200 deg/s | +48 | 87% |

**HUD** (centerprint, 10 Hz):

```
437                 your speed
   +21/hop  >>      right now you are gaining at a rate of 21 ups a hop; turn RIGHT for more
last hop +22        or "circle jump 405" after the first hop of a run
```

On the ground the middle line reads `+N/s` (net of friction). The rate is in real units on purpose: v2/v3
showed a percent of the theoretical best frame, and since that ceiling needs a ~300 deg/s sweep it read as
"the coach is asking for something impossible" (Peter).

**Hop log** (console, so the last few lines sit top left of the screen): one line per hop.

```
circle jump 444  (left the ground at 417)
hop 2  +19  now 455
hop 3  +23  now 478
```

The first hop after standing or running on the ground is the circle jump; the number is the speed it reaches.
About 400 is fine, 440 is good, 480+ is exceptional (the ground equilibrium is ~485).

**Orb.**
- *In the air it is a pacer.* It starts where your view should be and sweeps the way you are strafing at a set
  rate. Keep your crosshair on it and you are sweeping at that pace. `scpace` steps through 45 / 60 / 75 / 90 / 120
  deg/s (default 60, which is what the top quarter of duel players do; saved as `setinfo stcp N`). It re-anchors on every takeoff and every time you switch
  strafe key, and it waits when it gets 20 degrees ahead of you.
- *On the ground* it marks the best aim for the run-up, unsmoothed, because that aim itself sweeps fast.
- Always 320 units away (constant size), on the plane of your standing eye height (no bobbing), led by your
  ping. Glows blue while you are gaining. Other players on the server can see it.

**History.** v1 was a one-character-per-degree gauge nobody could read, with an orb that changed size and
jumped. v2 made the HUD three plain lines and stabilised the orb, but the orb marked the instantaneous best
angle, which always sits a few degrees ahead of wherever you are looking, so it seemed to follow the crosshair
instead of leading it (Peter). v3 made it a pacer and added circle-jump tracking, ground guidance and the hop log.

## Is the maths right? (checked 2026-10-02 after Peter asked)

- The formula is the engine's own: `PM_AirAccelerate` in the mvdsv source the box builds from
  (`wishspd = min(wishspd, 30); addspeed = wishspd - dot(velocity, wishdir); accelspeed = min(accel * wishspeed
  * frametime, addspeed)`), which is the same function as `SV_AirAccelerate` in id's original `sv_user.c`.
- Replaying real hops from a demo with that formula, given only the takeoff velocity and the recorded view
  angle each frame, reproduces how far the direction of travel turned on each hop almost exactly (95.2
  predicted vs 96.9 real, 60.3 vs 61.2, 67.6 vs 69.3 degrees) and the speed gained to within ~5 ups for a
  77 fps player. A cap of 20 or 45 instead of 30 fits clearly worse.
- So the best angle really is "wish direction sideways to the velocity", which for strafe-only keys means
  **looking along your direction of travel**. The "~300 deg/s" figure is not a turn the player is asked to
  make: it is how fast that perfect spot moves if you sit exactly on it. Real players sit 2-4 degrees
  behind it and sweep at 40-90 deg/s for +15 to +25 a hop.

## Files

- `strafecoach.c`: the whole feature (`src/strafecoach.c` in KTX).
- `strafecoach.patch`: that file plus the hooks (command table, PlayerPreThink, connect/disconnect,
  precache, gedict fields, CMake).
- `build_coach.sh`: the on-box build.

The maths was checked two ways before deploying: a Python model of `PM_AirAccelerate`, and the real C file
compiled into a harness with stubbed KTX services and simulated hops (gauge direction, hop gain and
efficiency all matched the model).

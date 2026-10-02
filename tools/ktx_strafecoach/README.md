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
- **In game:** `strafecoach` (or `scoach`) cycles HUD + orb, HUD only, orb only, off. `scpace` changes the orb's sweep speed, `scpos <rows>` moves the display down, `scsound` toggles the mistake sound. The choice is kept in
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

**The display (v5)** is one centerprint block, refreshed 10 times a second:

```
         437                    speed
    <<   ###--                  meter = how hard you are gaining right now; arrows = turn that way
   last +22   avg +18           last hop, and the average of your last 10
   TOO FAR  lost 12             the mistake you just made and what it cost (red, 1.5 s, plus a tick sound)

+19  455                        last five hops, newest first, set to the left
-12  436  too far
circle jump 448
```

- **Position.** With more than four lines the client starts a centerprint 48 pixels from the top, so the
  block is pushed down with blank rows: `scpos <rows>` (default 14, saved as `setinfo stcy N`). A line is
  centred in a 40-column box, so the hop list is padded with trailing spaces to sit at the box's left edge.
  A player using ezQuake's new-HUD centerprint element positions the whole block with that element instead.
- **Mistakes called out as they happen:**
  - `TOO FAR`: the push went past sideways and is taking speed. This is the "quick flip to the side": at
    180 degrees it costs 42 ups every frame, so 474 becomes 244 inside one hop.
  - `LATE JUMP`: touched down mid-run without jump held and friction took speed.
  - `HIT A WALL`: speed dropped by more than the push explains.
  - `TURN MORE`: a whole hop with the push too far forward to gain anything.
  - `NO STRAFE KEY`: a hop with no strafe key held.
  `scsound` toggles the tick (played with `play`, so only that player hears it).
- **Arrows and meter** come from values smoothed over a quarter second, and the orb and arrows are held for
  0.35 s after guidance drops. Without that they blinked off on every strafe-key switch, because a switch
  leaves a few frames with no key held and `sv_safestrafe` adds more (Peter: "arrows disappear too fast").
- v4 showed a live `+N/hop` rate above `last hop +N`; the two read as the same number, so the rate became the
  meter and the average of the last 10 hops was added.
- The **gain window is asin(30 / speed) wide**: 4.3 degrees at 400, 3.4 at 500, 2.6 at 650, 2.1 at 800. A
  steady 60 deg/s sweep still gains about +18 a hop at 650, but the same hand error now falls out of the
  window, which is why gains drop off up there.

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

## Reset gotcha (found 2026-10-02)

When a KTX server empties it execs `configs/reset.cfg` -> `server.cfg` -> `mvdsv.cfg`, and the shared
`mvdsv.cfg` sets `sv_progsname qwprogs`. The next map change on the coach port then loaded the STOCK mod and
the coach silently vanished. Fix, without touching the shared configs: `port_29001.cfg` sets
`k_stc_progs qwprogs_coach`, and the coach build runs a small guard entity that puts `sv_progsname` back to
that value every 3 seconds. Checked by exec'ing `configs/reset.cfg` over rcon and changing map: the coach
build loaded again. If the port ever does come up on the stock mod: `rcon sv_progsname qwprogs_coach`, then
`rcon map speed`.

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

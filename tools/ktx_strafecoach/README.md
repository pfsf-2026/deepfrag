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
- **In game:** `strafecoach` (or `scoach`) cycles orb + gauge, gauge only, orb only, off. The choice is kept in
  the client's userinfo (`setinfo stc N`) so it survives map changes. Only runs outside a live match
  (prewar, race, practice) unless `k_strafecoach_match 1`.

## What it shows

QuakeWorld air acceleration adds speed along the direction your keys point, capped at 30 ups measured along
that direction. A frame gains the most when that direction is exactly sideways to your velocity; the window
that gains anything is only a few degrees wide and rotates as your velocity turns.

- **Orb** (`progs/s_light.spr`): placed 300 units out along the yaw to look at right now, led by the player's
  ping so the direction is right when the client draws it. Glows blue while the crosshair is gaining speed.
  It is a normal entity, so other players on the server can see it too.
- **Gauge** (centerprint, 10 Hz): `speed  hop +gain eff%`, then one character per degree with the crosshair in
  the middle (`^`). Red `=` is where the crosshair gains speed, the knob is the best spot. `<` / `>` means the
  window is off the gauge that way.
- **Hop numbers:** speed gained takeoff to landing, and that gain as a share of the theoretical maximum
  (every air frame perfectly sideways).

Holding the knob exactly needs a ~300 deg/s turn at 400 ups, so nobody scores 100%. What you gain is set by how
fast you can turn while staying in the band. From the physics simulation at 400 ups, 77 fps, one hop:
60 deg/s turn = +20 ups (35%), 120 deg/s = +35 (62%), 200 deg/s = +48 (87%), no turn = +1.

## Files

- `strafecoach.c`: the whole feature (`src/strafecoach.c` in KTX).
- `strafecoach.patch`: that file plus the hooks (command table, PlayerPreThink, connect/disconnect,
  precache, gedict fields, CMake).
- `build_coach.sh`: the on-box build.

The maths was checked two ways before deploying: a Python model of `PM_AirAccelerate`, and the real C file
compiled into a harness with stubbed KTX services and simulated hops (gauge direction, hop gain and
efficiency all matched the model).

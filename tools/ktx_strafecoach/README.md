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
- **In game:** `strafecoach` (or `scoach`) cycles HUD + orb, HUD only, orb only, off. The choice is kept in
  the client's userinfo (`setinfo stc N`) so it survives map changes. Only runs outside a live match
  (prewar, race, practice) unless `k_strafecoach_match 1`.
- **Map:** the coach port defaults to `speed` (wide open, Peter's old training map). `speed2`, `rawspeed` and
  `speedrush` are on the box too.

## What it shows

QuakeWorld air acceleration adds speed along the direction your keys point, capped at 30 ups measured along
that direction. A frame gains the most when that direction is exactly sideways to your velocity; the window
that gains anything is only a few degrees wide and rotates as your velocity turns.

- **HUD** (centerprint, 10 Hz), three short lines. v2 after Peter's first test: the first version drew a
  one-character-per-degree gauge that nobody could read.

  ```
  437                 your speed
       33%  >>        33% of the possible gain right now; turn RIGHT for more
  last hop +19        what the hop you just finished gained
  ```

  One rule: make the number go up by turning the way the arrows point. More arrows = further off (1 = 1 deg,
  2 = 3 deg, 3 = 6 deg or more). The values are averaged over the 0.1 s between refreshes so the line is steady.
- **Orb** (`progs/s_light.spr`): the yaw to aim at. Always 320 units away, so its size never changes. It sits
  on the plane of the player's standing eye height, so it does not bob with jumps. Its yaw is smoothed
  (60 ms) and it is led by the player's ping so the direction is right when the client draws it. Glows blue
  while the crosshair is gaining speed. It is a normal entity, so other players on the server see it too, and
  on a tight map it can end up inside a wall.
- **Hop number:** speed gained from takeoff to landing.

Holding 100% needs a ~300 deg/s turn at 400 ups, so nobody scores 100%. What you gain is set by how
fast you can turn while keeping the number above zero. From the physics simulation at 400 ups, 77 fps, one hop:
60 deg/s turn = +20 ups (35%), 120 deg/s = +35 (62%), 200 deg/s = +48 (87%), no turn = +1.

## Files

- `strafecoach.c`: the whole feature (`src/strafecoach.c` in KTX).
- `strafecoach.patch`: that file plus the hooks (command table, PlayerPreThink, connect/disconnect,
  precache, gedict fields, CMake).
- `build_coach.sh`: the on-box build.

The maths was checked two ways before deploying: a Python model of `PM_AirAccelerate`, and the real C file
compiled into a harness with stubbed KTX services and simulated hops (gauge direction, hop gain and
efficiency all matched the model).

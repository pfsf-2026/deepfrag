# FragBot movement brain — mode 30 (coupled air-strafe)

`mode30_coupled_airstrafe.c` is FragBot's first movement controller: a new
moveprobe mode that turns the bot's **view in sync with its strafe** during
air-accel, producing the human view↔heading **coupling** no frogbot has
(frogbot ~0.03, human 0.29–0.47). It runs on komodo's KTX moveprobe substrate.

## Build & deploy (once we have server access)

The server runs MVDSV + KTX (`~/nquakesv/`, like servexeri). Steps, against the
**KTX version that server runs** (confirm the commit first):

```bash
# 1. patch KTX with komodo's moveprobe modes + our mode 30
cd ktx
git apply  ~/Projects/komodobots/experiments/ktx_moveprobe/frogbot-moveprobe.patch
#    then insert the two pieces from mode30_coupled_airstrafe.c:
#      (a) the two static float[] arrays into the per-client state block
#      (b) the `else if (mode == 30) { ... }` branch into the dispatch chain
# 2. build the game lib
cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build
#    -> build/qwprogs.so   (linux x86_64 to match the server)
# 3. drop it in and launch on a NEW port
scp build/qwprogs.so  user@server:~/nquakesv/ktx/qwprogs.so
```

(If `git apply` rejects against a newer KTX, I rebase the moveprobe patch to that
commit — that's why I need the server's KTX version up front.)

## Launch config (FragBot mode 30 vs frogbot)

A KTX cfg (`fragbot_dm2_<port>.cfg`) on a free port, QTV on so you can watch:

```
hostname "fragbot-lab:<port>"
set k_matchless 1
set k_defmode ffa
set k_defmap dm2
set sv_demoMaxSize 0          // optional: keep recording

// FragBot movement brain
set k_fb_moveprobe_mode 30
set k_fb_moveprobe_forwardmove 320
set k_fb_fragbot_coupling_gain 0.35   // the dial: 0 robotic .. ~0.35 human
set k_fb_fragbot_swing_deg 35
set k_fb_fragbot_swing_period 0.45

// QTV so unezquake can watch
set qtv_streamport <port>
```

Spawn the bots from a client shim (komodo's `qw_min_client.py`) or console:
`addbot 10` (a frogbot) then a FragBot slot — or per-slot cvars
(`k_fb_moveprobe_mode_s<N> 30`) to make only slot N a FragBot and the rest
frogbots, for direct A/B in the same match.

## Watch in unezquake
```
/qtvplay <server-ip>:<port>     # spectator stream (passive)
/connect  <server-ip>:<port>    # join the server as a spectator
```

## Tune it (the loop)
1. Record a match (server auto-records MVD, or pull via komodo's harness).
2. `fragbot/score_bot.py score --demo <mvd> --mode 1on1 --roster roster.json` — the
   roster marks the FragBot slot vs the frogbot slot.
3. Read the evidence table: did `coupling_52ms` move toward 0.29–0.47? did speed hold?
4. Sweep `coupling_gain` / `swing_deg` / `swing_period` (fork komodo's
   `mode23_sweep.py` LawParams) and re-score. **Target: coupling → human band
   without tanking speed.**

## Honesty note
This is a first, untested-until-build controller. The *structure* is correct
(view leads strafe → air-accel → coupling), but the optimal `gain/swing/period`
come from the sweep — air-strafe is sensitive. Expect 1–2 tuning passes before it
both couples AND keeps speed. Combat is off in mode 30 (movement milestone);
a later mode re-integrates frogbot aim for real FragBot-vs-frogbot games.

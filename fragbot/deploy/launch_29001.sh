#!/usr/bin/env bash
# Launch an ISOLATED FragBot server on port 29001 (qw-dal-1). Separate gamedir
# + screen session; does NOT touch nquakesv.service or the live 28501-28504.
set -e
ROOT=/opt/qw/nquakesv
SO=/opt/qw/fragbot/ktx-src/build-fragbot/linux-amd64/qwprogs.so
PORT=29001
cd "$ROOT"

# ensure our FragBot qwprogs.so is the one this gamedir loads
cp "$SO" fragbot/qwprogs.so
echo "qwprogs.so: $(stat -c %s fragbot/qwprogs.so) bytes"

# launch config
cat > "fragbot/port_${PORT}.cfg" <<'CFG'
set k_motd1 "FragBot Lab - mode30 coupled air-strafe"
hostname "FragBot Lab (Dallas):29001"
sv_serverip "144.202.66.126:29001"
qtv_streamport "29001"
set k_matchless 1
set k_mode 3
set k_defmode ffa
set k_use_matchless_dir 1
set k_defmap dm6
// FragBot movement brain (mode 30)
set k_fb_fragbot_mode 30
set k_fb_moveprobe_forwardmove 320
set k_fb_fragbot_coupling_gain 0.35
set k_fb_fragbot_swing_deg 35
set k_fb_fragbot_swing_period 0.45
CFG

# (re)start the isolated instance
screen -S "qw_${PORT}" -X quit 2>/dev/null || true
sleep 1
screen -dmS "qw_${PORT}" ./mvdsv -port "${PORT}" -mem 64 -game fragbot +exec "port_${PORT}.cfg"
sleep 3

# load map + spawn two bots (global mode 30 => both are FragBots)
screen -S "qw_${PORT}" -p 0 -X stuff "map dm6$(printf \\r)"
sleep 2
screen -S "qw_${PORT}" -p 0 -X stuff "addbot 10$(printf \\r)"
sleep 1
screen -S "qw_${PORT}" -p 0 -X stuff "addbot 10$(printf \\r)"
sleep 2

echo "--- listening? ---"
ss -lun | grep ":${PORT}" || echo "(no udp listener on ${PORT})"
echo "--- process ---"
ps ax | grep -v grep | grep "mvdsv -port ${PORT}" || echo "NOT RUNNING"
echo "--- server status ---"
quakestat -qws "localhost:${PORT}" -P 2>/dev/null | head -12 || echo "(quakestat unavailable)"

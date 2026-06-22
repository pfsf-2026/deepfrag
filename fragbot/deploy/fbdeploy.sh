#!/bin/bash
# fbdeploy.sh — deploy a FragBot seam to the isolated 29001 lab WITH verification.
#
# The whole point: never again "trust" a deploy. We bake a unique build-id into
# the .so, kill the old server for real, launch fresh, and then CONFIRM the live
# server reports back that exact build-id. If it doesn't, the deploy FAILED
# (stale .so still in memory / zombie holding the port) and we say so loudly.
#
# Usage: fbdeploy.sh <seam.c> [mode] [map]
set -u
SEAM="${1:?seam.c required}"; MODE="${2:-30}"; MAP="${3:-dm6}"
NQ=/opt/qw/nquakesv; KTX=$NQ/build/ktx; DST=/opt/qw/fragbot
HERE="$(cd "$(dirname "$0")" && pwd)"
INJECT="$HERE/inject_and_build.py"; [ -f "$INJECT" ] || INJECT=/tmp/inject_and_build.py
QUERY="$HERE/fbquery.py"; [ -f "$QUERY" ] || QUERY=/tmp/fbquery.py
LOG=/tmp/fb29001.log
STAMP="$(date -u +%Y%m%d-%H%M%S)-$RANDOM"

echo "=== [1/5] build-id for this deploy: $STAMP ==="
TMP=/tmp/fb_seam_stamped.c
sed "s/@@FRAGBOT_BUILD@@/$STAMP/" "$SEAM" > "$TMP"
grep -q "$STAMP" "$TMP" || { echo "FAIL: seam has no @@FRAGBOT_BUILD@@ placeholder"; exit 1; }

echo "=== [2/5] compile .so ==="
python3 "$INJECT" "$TMP" "$KTX" "$DST" 2>&1 | grep -E "injected|CALL2|OK ->|FAILED|error:" || true
SO=$DST/ktx-src/build-fragbot/linux-amd64/qwprogs.so
[ -f "$SO" ] || { echo "FAIL: no .so produced"; exit 1; }
SOHASH=$(sha256sum "$SO" | cut -c1-12)

echo "=== [3/5] kill old server + free port 29001 (never the 28xxx fleet) ==="
for p in $(pgrep -x mvdsv); do tr "\0" " " </proc/$p/cmdline 2>/dev/null | grep -q "port 29001" && { echo "  kill $p (uptime $(ps -o etime= -p $p|tr -d ' '))"; kill -9 $p; }; done
screen -S qw_29001 -X quit 2>/dev/null; screen -S fragbot_host -X quit 2>/dev/null; sleep 2
if ss -lun 2>/dev/null | grep -q :29001; then o=$(ss -lunHp 2>/dev/null|grep :29001|grep -oE "pid=[0-9]+"|head -1|cut -d= -f2); echo "  force-kill socket owner $o"; kill -9 "$o"; sleep 2; fi
ss -lun 2>/dev/null | grep -q :29001 && { echo "FAIL: port 29001 still bound; aborting"; exit 1; }

echo "=== [4/5] deploy .so + cfg (mode=$MODE map=$MAP) + launch ==="
cp "$SO" $NQ/fragbot/qwprogs.so
cd $NQ
sed -i "s/^set k_fb_fragbot_mode .*/set k_fb_fragbot_mode $MODE/" fragbot/port_29001.cfg
sed -i "s/^set k_defmap .*/set k_defmap $MAP/" fragbot/port_29001.cfg
: > "$LOG"
screen -L -Logfile "$LOG" -dmS qw_29001 ./mvdsv -port 29001 -mem 64 -game fragbot +exec port_29001.cfg
sleep 4; screen -S qw_29001 -p 0 -X stuff "map $MAP$(printf \\r)"; sleep 3

echo "=== [5/5] VERIFY the live server is running THIS build ==="
ACTUAL=$(python3 "$QUERY" fragbot_build)
BP=$(ss -lunHp 2>/dev/null|grep :29001|grep -oE "pid=[0-9]+"|head -1|cut -d= -f2)
EL=$(ps -o etime= -p "$BP" 2>/dev/null | tr -d ' ')
echo "------------------------------------------------------------"
echo " intended build : $STAMP"
echo " LIVE build     : ${ACTUAL:-<none>}"
echo " bound pid      : ${BP:-none}   uptime: ${EL:-?}"
echo " .so sha256     : $SOHASH"
echo " mode / map     : $MODE / $MAP"
if [ "$ACTUAL" = "$STAMP" ]; then
  echo " RESULT: PASS - live server is provably running exactly this build"
else
  echo " RESULT: FAIL - live build != intended (stale/zombie). DO NOT TRUST."; exit 2
fi
echo "------------------------------------------------------------"

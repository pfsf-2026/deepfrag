#!/usr/bin/env bash
# FragBot keeper — runs persistently on qw-dal-1 in a screen (qw_keeper).
# Guarantees the isolated FragBot server (29001) + idle host + 2 FragBots are
# always present, re-establishing within ~30s after any reset (KTX clamps the
# matchless timelimit to 30min, so the level cycles periodically — this heals it).
# Touches ONLY port 29001 / the fragbot gamedir; never the live 285xx servers.
ROOT=/opt/qw/nquakesv
PORT=29001
SHIM=/tmp/fragbot_host.py
cd "$ROOT"
while true; do
  # 1. ensure mvdsv is up on 29001 (detect by the UDP listener, not pgrep -f)
  if ! ss -lun 2>/dev/null | grep -q ":${PORT} "; then
    screen -S "qw_${PORT}" -X quit 2>/dev/null || true
    sleep 1
    screen -L -Logfile /tmp/fb_screen.log -dmS "qw_${PORT}" \
      ./mvdsv -port "${PORT}" -mem 64 -game fragbot +exec "port_${PORT}.cfg"
    sleep 6
  fi
  # 2. ensure idle host + 2 FragBots (3 player rows). re-add if a cycle wiped them.
  n=$(quakestat -qws "localhost:${PORT}" -P 2>/dev/null | grep -c frags)
  if [ "${n:-0}" -lt 3 ]; then
    screen -S fragbot_host -X quit 2>/dev/null || true
    sleep 2
    screen -dmS fragbot_host python3 "$SHIM" "${PORT}" --host 127.0.0.1 \
      --bot-count 2 --bot-spacing 3 --run-for 100000 --name FragBotHost
    sleep 10
  fi
  sleep 30
done

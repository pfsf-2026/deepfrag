#!/usr/bin/env bash
# FragBot CLIENT-ONLY keeper: maintains 1 host + 1 replay bot on 29001, re-adding
# after each auto-changelevel. Never starts/restarts mvdsv or the live 285xx.
PORT=29001; SHIM=/tmp/fragbot_host.py
while true; do
  if ss -lun 2>/dev/null | grep -q ":${PORT} "; then
    n=$(quakestat -qws "localhost:${PORT}" -P 2>/dev/null | grep -c frags)
    host_up=$(screen -ls 2>/dev/null | grep -c fragbot_host)
    if [ "${host_up:-0}" -eq 0 ] || [ "${n:-0}" -lt 2 ]; then
      screen -S fragbot_host -X quit 2>/dev/null || true; sleep 1
      screen -dmS fragbot_host python3 "$SHIM" "${PORT}" --host 127.0.0.1 \
        --bot-count 1 --bot-spacing 2 --run-for 100000 --name ReplayHost
      sleep 8
    fi
  fi
  sleep 8
done

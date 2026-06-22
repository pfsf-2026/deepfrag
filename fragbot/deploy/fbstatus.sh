#!/bin/bash
# fbstatus.sh — what is the 29001 lab ACTUALLY running right now? Query anytime.
HERE="$(cd "$(dirname "$0")" && pwd)"
QUERY="$HERE/fbquery.py"; [ -f "$QUERY" ] || QUERY=/tmp/fbquery.py
echo "=== LIVE 29001 (what the running process advertises) ==="
python3 "$QUERY"
BP=$(ss -lunHp 2>/dev/null|grep :29001|grep -oE "pid=[0-9]+"|head -1|cut -d= -f2)
echo "bound pid         : ${BP:-NONE}  uptime: $(ps -o etime= -p "$BP" 2>/dev/null|tr -d ' ')"
echo "deployed .so hash : $(sha256sum /opt/qw/nquakesv/fragbot/qwprogs.so 2>/dev/null|cut -c1-12)"
n=0; for p in $(pgrep -x mvdsv); do tr "\0" " " </proc/$p/cmdline 2>/dev/null | grep -q "port 29001" && n=$((n+1)); done
echo "mvdsv on 29001    : $n  (must be 1)"

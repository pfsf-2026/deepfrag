#!/usr/bin/env python3
"""Pull new lines from mvdsv's player logs on each fleet box and post them to the join log.

Runs on the devbox from cron every 5 minutes (it has the fleet SSH keys and the admin key in
~/.deepfrag_admin_key). Read-only on the boxes: `stat` and `tail`, nothing touches nquakesv.
State (byte offset per log file) lives in ~/.deepfrag/player_log_state.json, so each run sends
only what's new; the API ignores rows it already has, so a re-send is harmless.

Line format (mvdsv sv_logplayers):
  [Mon Nov 09, 01:35:49 2026].[1] connect\\<nick>\\<userid>\\<ip>\\<realip>\\<port>\\<userinfo k\\v...>

  python3 tools/player_log/pull_joins.py            # pull and post
  python3 tools/player_log/pull_joins.py --dry-run  # parse and count, post nothing, keep state
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ssh alias → log directory on that box (all boxes run in UTC)
HOSTS = {
    "qw-dal-1": "/opt/qw/nquakesv/logs",
    "qw-atl-1": "/opt/qw/nquakesv/logs",
    "qw-den-2": "/opt/qw/nquakesv/logs",
    "qw-den-1": "nquakesv/logs",  # old AWS Denver, home dir of user admin
}
API = os.environ.get("DEEPFRAG_API", "https://deepfrag-api-751658372467.us-central1.run.app")
STATE = Path.home() / ".deepfrag" / "player_log_state.json"
BATCH = 2000
MAX_CHUNK = 20_000_000  # bytes per file per run


def ssh(host, script, timeout=60):
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, "sh", "-s"],
                       input=script.encode(), capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{host}: ssh exit {r.returncode}: {r.stderr.decode(errors='replace').strip()[:200]}")
    return r.stdout


def parse_line(raw: bytes, server: str, port: int):
    """One log line → a row dict, or None (other line types, loopback bots, junk)."""
    s = raw.decode("latin-1").rstrip("\r\n")
    if not s.startswith("[") or "] " not in s:
        return None
    stamp, _, rest = s.partition("].")
    try:
        ts = datetime.strptime(stamp[1:], "%a %b %d, %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    rest = rest.partition("] ")[2]
    parts = rest.split("\\")
    if len(parts) < 6 or parts[0] not in ("connect", "disconnect"):
        return None
    event, name, userid, ip, realip, _cport = parts[:6]
    if not ip or ip.startswith("127.") or ip == "0.0.0.0":
        return None  # ReplayHost, FragBot and other local clients
    info = dict(zip(parts[6::2], parts[7::2]))
    return {
        "ts": ts.isoformat(), "server": server, "port": port, "event": event,
        "name": name, "userid": int(userid) if userid.isdigit() else None, "ip": ip,
        "realip": realip if realip and realip != "0.0.0.0" else None,
        "client": info.get("*client") or info.get("*ver"), "team": info.get("team"),
        "spectator": info.get("*spectator") == "1", "proxy": "*qwfwd" in info,
    }


def post(rows, key):
    req = urllib.request.Request(f"{API}/api/admin/player-log/ingest", method="POST",
                                 data=json.dumps({"rows": rows}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def pull_host(host, logdir, state, key, dry):
    files = ssh(host, f"cd {shlex.quote(logdir)} 2>/dev/null && stat -c '%i %s %n' player_*.log 2>/dev/null; true")
    hs = state.setdefault(host, {})
    sent = new = 0
    for line in files.decode().splitlines():
        inode, size, fname = line.split(" ", 2)
        size = int(size)
        try:
            port = int(fname.split("_")[1])
        except (IndexError, ValueError):
            continue
        st = hs.get(fname, {})
        off = st.get("offset", 0) if st.get("inode") == inode and st.get("offset", 0) <= size else 0
        if size <= off:
            hs[fname] = {"inode": inode, "offset": off}
            continue
        n = min(size - off, MAX_CHUNK)
        chunk = ssh(host, f"cd {shlex.quote(logdir)} && tail -c +{off + 1} {shlex.quote(fname)} | head -c {n}",
                    timeout=300)
        cut = chunk.rfind(b"\n") + 1  # whole lines only; the rest waits for the next run
        rows = [r for r in (parse_line(l, host, port) for l in chunk[:cut].splitlines()) if r]
        for i in range(0, len(rows), BATCH):
            if not dry:
                res = post(rows[i:i + BATCH], key)
                new += res.get("inserted", 0)
        sent += len(rows)
        if not dry:
            hs[fname] = {"inode": inode, "offset": off + cut}
    return sent, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--host", action="append", help="only these ssh aliases")
    a = ap.parse_args()
    key = "" if a.dry_run else (Path.home() / ".deepfrag_admin_key").read_text().strip()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    failed = False
    for host, logdir in HOSTS.items():
        if a.host and host not in a.host:
            continue
        try:
            sent, new = pull_host(host, logdir, state, key, a.dry_run)
            print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} {host}: {sent} rows, {new} new")
        except Exception as e:  # one box down mustn't stop the others
            failed = True
            print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} {host}: FAILED {e}", file=sys.stderr)
        if not a.dry_run:
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(json.dumps(state, indent=1))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

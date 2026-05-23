#!/usr/bin/env python3
"""Probe QW servers via UDP getstatus to see what's actually live.

QW server status protocol:
  Client → server: 0xff 0xff 0xff 0xff + "getstatus\n"
  Server → client: 0xff 0xff 0xff 0xff + "statusResponse\n\<serverinfo>\n\<player1>\n\<player2>..."
    serverinfo is a backslash-delimited key/value blob
    each player line is: <frags> <ping> "<name>" <skin> <topcolor> <bottomcolor>

Picks a representative sample (recent vs. stale) and reports what came back.
"""

from __future__ import annotations  # Python 3.9 needs this for `dict | None`

import socket
import sys
from datetime import datetime, timedelta, timezone

import db as dbmod

TIMEOUT_SEC = 2.0
GETSTATUS = b"\xff\xff\xff\xffgetstatus\n"


def parse_serverinfo(blob: str) -> dict:
    """Parse '\\sv_maxclients\\8\\fraglimit\\50\\…' into a dict."""
    parts = [p for p in blob.split("\\") if p]
    return dict(zip(parts[0::2], parts[1::2]))


def probe(host: str, port: int) -> dict | None:
    """Send UDP getstatus, parse response. Returns dict or None on timeout/error."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT_SEC)
    try:
        try:
            ip = socket.gethostbyname(host)
        except (socket.gaierror, UnicodeError) as e:
            return {"error": f"dns_failed: {e}", "host": host, "port": port}

        sock.sendto(GETSTATUS, (ip, port))
        data, _ = sock.recvfrom(8192)
        text = data.decode("latin-1", errors="replace")

        # Strip leading OOB bytes + "statusResponse\n"
        if not text.startswith("\xff\xff\xff\xffstatusResponse\n"):
            return {"error": "unexpected_response", "raw": text[:200], "host": host, "port": port, "ip": ip}
        body = text[len("\xff\xff\xff\xffstatusResponse\n"):]
        lines = body.splitlines()
        info = parse_serverinfo(lines[0]) if lines else {}

        players = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            # frags ping "name" skin topcolor bottomcolor
            # Quick + dirty: pull name (inside quotes), frags+ping from leading ints.
            try:
                parts = line.split(" ", 2)
                frags = int(parts[0])
                ping = int(parts[1])
                rest = parts[2] if len(parts) > 2 else ""
                name = rest.split('"')[1] if '"' in rest else rest
                players.append({"name": name, "frags": frags, "ping": ping})
            except (ValueError, IndexError):
                players.append({"raw": line})

        return {
            "host": host, "port": port, "ip": ip,
            "hostname": info.get("hostname"),
            "map": info.get("mapname") or info.get("map"),
            "gamedir": info.get("*gamedir") or info.get("gamename"),
            "max_clients": info.get("sv_maxclients") or info.get("maxclients"),
            "deathmatch": info.get("deathmatch"),
            "teamplay": info.get("teamplay"),
            "fraglimit": info.get("fraglimit"),
            "timelimit": info.get("timelimit"),
            "players_count": len(players),
            "players": players,
        }
    except socket.timeout:
        return {"error": "timeout", "host": host, "port": port}
    except OSError as e:
        return {"error": f"socket: {e}", "host": host, "port": port}
    finally:
        sock.close()


def split_host_port(raw: str) -> tuple:
    """'ny.quake.world:28501 NAQW' → ('ny.quake.world', 28501).
    'The-Den' (no port) → ('The-Den', 27500) (QW default)."""
    raw = raw.strip()
    # Strip trailing tags after a space
    if " " in raw:
        raw = raw.split(" ", 1)[0]
    if ":" in raw:
        host, port = raw.rsplit(":", 1)
        try:
            return host, int(port)
        except ValueError:
            return host, 27500
    return raw, 27500


def main():
    db = dbmod.connect()
    cur = db.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

    # Use server_port from the matches table — friendly names like "The-Den" have
    # no DNS but real port info recorded. Group by (host_root, port) so we probe
    # each game-server instance separately.
    cur.execute("""
        SELECT split_part(server_hostname, ':', 1) AS host_root,
               server_port, MAX(match_date) AS last_match, COUNT(*) AS games
        FROM matches WHERE server_hostname IS NOT NULL AND server_port IS NOT NULL
        GROUP BY split_part(server_hostname, ':', 1), server_port
        HAVING MAX(match_date) >= %s
        ORDER BY MAX(match_date) DESC LIMIT 5
    """, (cutoff,))
    recent = cur.fetchall()

    cur.execute("""
        SELECT split_part(server_hostname, ':', 1) AS host_root,
               server_port, MAX(match_date) AS last_match, COUNT(*) AS games
        FROM matches WHERE server_hostname IS NOT NULL AND server_port IS NOT NULL
        GROUP BY split_part(server_hostname, ':', 1), server_port
        HAVING MAX(match_date) < %s
        ORDER BY MAX(match_date) DESC LIMIT 5
    """, (cutoff,))
    stale = cur.fetchall()

    for label, rows in [("RECENT (active in last 60d)", recent), ("STALE (last match > 60d ago)", stale)]:
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        for r in rows:
            host = r["host_root"]
            port = r["server_port"]
            print(f"\n[{host}:{port}]  last_match={r['last_match'][:10]}  games_total={r['games']}")
            print(f"  probing {host}:{port} …", flush=True)
            result = probe(host, port)
            if not result or "error" in (result or {}):
                print(f"  → {result.get('error', 'unknown') if result else 'no response'}")
                continue
            print(f"  → IP {result['ip']}  hostname='{result['hostname']}'")
            print(f"  → map={result['map']}  mode={result.get('gamedir','?')}  players={result['players_count']}/{result['max_clients']}")
            if result['players']:
                for p in result['players'][:6]:
                    print(f"      - {p.get('name','?'):20s} frags={p.get('frags','—')}  ping={p.get('ping','—')}")


if __name__ == "__main__":
    main()

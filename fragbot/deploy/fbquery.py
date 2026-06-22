#!/usr/bin/env python3
"""Query the LIVE 29001 lab server's serverinfo over UDP (out-of-band status).
Prints one serverinfo value, or all key fields if no key given. This reads what
the RUNNING process advertises — including `fragbot_build`, the build-id baked
into the loaded qwprogs.so — so we can confirm exactly which build is live."""
import socket, sys

PORT = 29001
key = sys.argv[1] if len(sys.argv) > 1 else None

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3)
try:
    s.sendto(b"\xff\xff\xff\xffstatus\n", ("127.0.0.1", PORT))
    data = s.recvfrom(8192)[0].decode("latin1")
except Exception:
    print("" if key else "ERROR: no response from :%d" % PORT)
    sys.exit(1)

line = data[data.find("\\"):].split("\n")[0]
toks = line.strip("\\").split("\\")
info = {toks[i]: toks[i + 1] for i in range(0, len(toks) - 1, 2)}

if key:
    print(info.get(key, ""))
else:
    for k in ("hostname", "map", "ktxver", "fragbot_build", "ezcsqc", "k_fb_fragbot_mode"):
        print("%-18s: %s" % (k, info.get(k, "<none>")))

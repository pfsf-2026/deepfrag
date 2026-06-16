#!/usr/bin/env python3
"""Runs ON the server. Copies the dusty-qw KTX source to an isolated FragBot
build dir, injects the FragBot seam into bot_movement.c, builds qwprogs.so for
linux-amd64. Idempotent. Never touches /opt/qw/nquakesv (production) — that's
rebuilt nightly and must stay stock.

Usage:  inject_and_build.py <seam.c> <src_ktx> <dst_root>
  e.g.  inject_and_build.py /tmp/fragbot_seam.c /opt/qw/nquakesv/build/ktx /opt/qw/fragbot
"""
import re, shutil, subprocess, sys
from pathlib import Path

seam_path, src_ktx, dst_root = map(Path, sys.argv[1:4])
seam = seam_path.read_text()

def section(name):
    m = re.search(rf"/\* ===== {name} ===== \*/\n(.*?)/\* ===== /{name} ===== \*/", seam, re.S)
    if not m:
        sys.exit(f"missing section {name} in seam")
    return m.group(1)

block = section("FRAGBOT_BLOCK")
call = section("FRAGBOT_CALL")

dst_ktx = dst_root / "ktx-src"
print(f"[1/4] copy {src_ktx} -> {dst_ktx}")
if dst_ktx.exists():
    shutil.rmtree(dst_ktx)
dst_root.mkdir(parents=True, exist_ok=True)
shutil.copytree(src_ktx, dst_ktx)

bm = dst_ktx / "src" / "bot_movement.c"
text = bm.read_text()
if "FragBot_CoupledAirStrafe" in text:
    print("[2/4] already injected, skipping")
else:
    anchor_fn = "void BotSetCommand(gedict_t *self)"
    if anchor_fn not in text:
        sys.exit("anchor 'void BotSetCommand' not found")
    text = text.replace(anchor_fn, block + "\n" + anchor_fn, 1)
    anchor_call = "\tbuttons |= (firing ? 1 : 0);"
    if anchor_call not in text:
        sys.exit("anchor 'buttons |= (firing ? 1 : 0);' not found")
    text = text.replace(anchor_call, call + anchor_call, 1)
    bm.write_text(text)
    print("[2/4] injected FragBot block + call")

print("[3/4] build linux-amd64 ...")
r = subprocess.run(["bash", "build_cmake.sh", "linux-amd64"], cwd=dst_ktx,
                   env={"BUILDDIR": "build-fragbot", "PATH": "/usr/bin:/bin:/usr/local/bin"},
                   capture_output=True, text=True)
tail = (r.stdout + r.stderr).splitlines()[-25:]
print("\n".join(tail))
sos = list(dst_ktx.glob("build-fragbot/**/qwprogs.so"))
if r.returncode != 0 or not sos:
    sys.exit(f"[4/4] BUILD FAILED (rc={r.returncode}, sos={sos})")
print(f"[4/4] OK -> {sos[0]}  ({sos[0].stat().st_size} bytes)")

#!/bin/bash
# Build the strafe-coach KTX: a pinned upstream commit + strafecoach.patch -> ktx/qwprogs_coach.so.
# Runs as user qw on the game box. Uses its OWN checkout under /opt/qw/coach: the nightly
# qw-update job does `git clean` + `git reset --hard` on /opt/qw/nquakesv/build/ktx, which would
# wipe a patch applied there. The output name does not match the nightly's qwprogs-*-??????.so
# pattern, so the nightly never touches or replaces it.
set -euo pipefail
REV=${1:-f67d6cc5}
BASE=/opt/qw/coach
OUT=/opt/qw/nquakesv/ktx/qwprogs_coach.so
cd "$BASE"
[ -d ktx/.git ] || git clone -q https://github.com/dusty-qw/ktx.git ktx
cd ktx
git fetch -q origin
git checkout -q -f "$REV"
git clean -qfdx
git apply "$BASE/strafecoach.patch"
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release > cmake.log
nice make -j3 > make.log 2>&1 || { tail -20 make.log; exit 1; }
install -m 755 qwprogs.so "$OUT.new" && mv "$OUT.new" "$OUT"
echo "built $(basename "$OUT") from ktx $REV + strafecoach.patch ($(stat -c %s "$OUT") bytes)"

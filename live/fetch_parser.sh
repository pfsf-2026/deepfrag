#!/bin/sh
# galfthan's mvd_analyzer (MIT), pinned. We use its mvd-reader as a library, unchanged.
set -e
COMMIT=d4622d368019b8da35a2318127f049ab591da802
DIR="$(dirname "$0")/third_party/mvd_analyzer"
if [ ! -d "$DIR/.git" ]; then
  git clone -q https://github.com/galfthan/mvd_analyzer.git "$DIR"
fi
git -C "$DIR" fetch -q origin
git -C "$DIR" checkout -q "$COMMIT"
echo "mvd_analyzer at $(git -C "$DIR" log --oneline -1)"

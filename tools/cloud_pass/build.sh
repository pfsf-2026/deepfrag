#!/bin/bash
# Build the demo-pass image: cross-compile qw-analyze from ~/Projects/mvd_analyzer, then Cloud Build.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${MVD_ANALYZER_SRC:-$HOME/Projects/mvd_analyzer}
IMAGE=us-central1-docker.pkg.dev/deepfrag-prod/cloud-run-source-deploy/demo-pass
(cd "$SRC" && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o "$HERE/qw-analyze" ./mvd-analytics/cmd/qw-analyze)
TAG=$(git -C "$SRC" rev-parse --short HEAD)-$(git -C "$HERE" rev-parse --short HEAD)
gcloud builds submit "$HERE/.." --region us-central1 --quiet \
  --config /dev/stdin <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: [build, -f, cloud_pass/Dockerfile, -t, $IMAGE:$TAG, -t, $IMAGE:latest, .]
images: [$IMAGE:$TAG, $IMAGE:latest]
EOF
echo "$IMAGE:$TAG"

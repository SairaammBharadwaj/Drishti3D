#!/usr/bin/env bash
# Ship the showcase image from this workstation to the server laptop and
# (re)start it there. Build the image first (see deploy/showcase/server/README.md).
#
#   deploy/showcase/server/deploy.sh <user>@<server-address>
#
# The image goes over SSH (docker save | docker load); nothing is pushed to a
# registry. Ends by checking the site answers on the server itself.
set -euo pipefail

HOST=${1:?usage: deploy.sh user@server}
HERE=$(cd "$(dirname "$0")" && pwd)
IMAGE=drishti3d-showcase:latest

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || { echo "no $IMAGE here; build it first (README.md)" >&2; exit 1; }

echo "== copying compose.yaml"
ssh "$HOST" 'mkdir -p ~/drishti3d'
scp -q "$HERE/compose.yaml" "$HOST:drishti3d/compose.yaml"

echo "== sending the image ($(docker image inspect -f '{{.Size}}' "$IMAGE" | numfmt --to=iec))"
docker save "$IMAGE" | gzip -1 | ssh "$HOST" 'gunzip | docker load'

echo "== starting"
ssh "$HOST" 'cd ~/drishti3d && docker compose up -d --force-recreate && docker image prune -f >/dev/null'

echo "== waiting for the site"
for _ in $(seq 60); do
  if ssh "$HOST" 'curl -sf http://127.0.0.1:7860/api/deployment' 2>/dev/null; then
    echo; echo "up on $HOST"; exit 0
  fi
  sleep 2
done
echo "did not come up; on the server: docker logs drishti3d-showcase" >&2
exit 1

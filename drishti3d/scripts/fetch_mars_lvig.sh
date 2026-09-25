#!/usr/bin/env bash
# Resumable download of MARS-LVIG files from Google Drive.
#
# MARS-LVIG (HKU, IJRR 2024) records a 10 Hz global-shutter camera and a DJI L1
# survey LiDAR on the same drone in the same flight, with RTK position truth.
# See https://mars.hku.hk/dataset.html. Licence: CC BY-NC-SA 4.0.
#
# Large Drive files need a per-request confirm token (the "download anyway"
# page), so a fresh one is fetched before every attempt; `curl -C -` then
# continues from the bytes already on disk. Re-running the script after an
# interruption resumes rather than restarts.
#
# Usage: scripts/fetch_mars_lvig.sh [dest_dir] [file_name ...]
# With file names, only those entries are fetched.
set -uo pipefail

DEST="${1:-$(dirname "$0")/../../datasets/public/mars_lvig}"
mkdir -p "$DEST/raw"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
BASE="https://drive.usercontent.google.com/download"
CHUNK=$(( 200 * 1024 * 1024 ))

# name  drive_id  bytes (0 = learn from the server)
FILES=(
  "HKisland01.bag 1nhX7hGyjCaoIfqc2b3PhAaHHu2Vv8wOQ 18839130084"
  "HKisland02.bag 1CPOE1y6fVz20f4tbFv44TWMatihb8JTZ 11787624886"
  "HKisland03.bag 1Now3Dz8UIHkwya8YvoJYHzukEWEBAobB 9459767048"
  "HKisland.7z 1OZ2gBMe6H0v3dqRJqo4lhHhC3OkHvuH- 0"
)

fetch() {
  local name=$1 id=$2 want=$3 out="$DEST/raw/$1" uuid have
  for attempt in $(seq 1 100000); do
    uuid=$(curl -sL -A "$UA" --max-time 60 "$BASE?id=$id&export=download" \
           | grep -oP 'name="uuid" value="\K[^"]+')
    if [ "$want" = 0 ]; then
      want=$(curl -s -A "$UA" -r 0-0 -D - -o /dev/null --max-time 60 \
             "$BASE?id=$id&export=download&confirm=t&uuid=$uuid" \
             | grep -ioP 'content-range: bytes 0-0/\K[0-9]+')
    fi
    have=$(stat -c %s "$out" 2>/dev/null || echo 0)
    if [ -n "$want" ] && [ "$have" -ge "$want" ]; then
      echo "$name complete ($have bytes)"; return 0
    fi
    # Fetch in fixed chunks and append a chunk only when Drive served real
    # bytes (HTTP 206). An exhausted quota comes back as an HTML page with
    # HTTP 200; appending that would corrupt the file silently.
    local end=$(( have + CHUNK - 1 )) code
    [ "$end" -ge "$want" ] && end=$(( want - 1 ))
    code=$(curl -s -A "$UA" -r "$have-$end" --speed-limit 50000 --speed-time 60 \
           -o "$out.chunk" -w '%{http_code}' \
           "$BASE?id=$id&export=download&confirm=t&uuid=$uuid")
    if [ "$code" = 206 ] && [ "$(stat -c %s "$out.chunk")" -eq $(( end - have + 1 )) ]; then
      cat "$out.chunk" >> "$out"; rm -f "$out.chunk"
      echo "$name: $(( (end + 1) / 1000000 )) / $(( want / 1000000 )) MB"
      continue
    fi
    rm -f "$out.chunk"
    if [ "$code" = 200 ]; then
      echo "$name: Drive is not serving the file (download quota exceeded); re-run later" >&2
      return 1
    fi
    echo "$name: chunk failed (HTTP $code), retrying" >&2
    sleep 5
  done
  echo "$name FAILED" >&2; return 1
}

# One file hitting Drive's quota must not stop the others; re-run later for it.
status=0
ONLY=("${@:2}")
for f in "${FILES[@]}"; do
  if [ ${#ONLY[@]} -gt 0 ] && [[ ! " ${ONLY[*]} " == *" ${f%% *} "* ]]; then continue; fi
  # shellcheck disable=SC2086
  fetch $f || status=1
done
ls -la "$DEST/raw"
exit $status

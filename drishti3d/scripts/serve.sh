#!/usr/bin/env bash
# Bring up the API and the workspace UI together.
#
# Both are dev servers. They previously died with whatever shell launched them,
# and Vite's default host (`localhost`) resolves to IPv6 first on Node 17+, so
# it bound [::1]:5173 only and the documented 127.0.0.1 URL had no listener.
# Both are pinned here.
set -euo pipefail
cd "$(dirname "$0")/.."

LOG="${TMPDIR:-/tmp}/drishti3d"
mkdir -p "$LOG"

if ss -ltn | grep -q ':8000'; then
  echo "api    already listening on 8000"
else
  setsid nohup .venv/bin/uvicorn backend.app.main:app \
      --host 127.0.0.1 --port 8000 > "$LOG/backend.log" 2>&1 < /dev/null &
  echo "api    starting  → $LOG/backend.log"
fi

if ss -ltn | grep -q ':5173'; then
  echo "ui     already listening on 5173"
else
  ( cd frontend && setsid nohup npm run dev -- --host 127.0.0.1 \
      > "$LOG/frontend.log" 2>&1 < /dev/null & )
  echo "ui     starting  → $LOG/frontend.log"
fi

for _ in $(seq 30); do
  sleep 1
  if curl -sf -o /dev/null http://127.0.0.1:8000/api/health \
     && curl -sf -o /dev/null http://127.0.0.1:5173/; then
    echo
    echo "  workspace   http://127.0.0.1:5173"
    echo "  api docs    http://127.0.0.1:8000/docs"
    exit 0
  fi
done
echo "did not come up; check $LOG/*.log" >&2
exit 1

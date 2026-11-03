#!/usr/bin/env bash
# Stops the X Education API, website and CRM started by start-all.sh. Data is kept in backend/data.
# "./stop-all.sh quiet" stops without messages (start-all.sh uses it to clear an earlier run).
cd "$(dirname "$0")"
RUN="backend/data/run"
stopped=0
for name in api website crm; do
  pid_file="$RUN/$name.pid"
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
      stopped=1
    fi
    rm -f "$pid_file"
  fi
done
# anything still listening on the three ports (for example started by hand)
for port in 8000 5173 5174; do
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      kill -TERM $pids 2>/dev/null || true
      stopped=1
    fi
  fi
done
[ "${1:-}" = "quiet" ] && exit 0
if [ "$stopped" = 1 ]; then
  echo "The API, the website and the CRM are stopped. Your data is kept in backend/data."
else
  echo "Nothing was running."
fi

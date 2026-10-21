#!/bin/sh
# Record every shot of the demo (DEMO_MASTERPLAN_50USD.md §6 step 7, T-061).
# Builds the three apps, starts the api in replay mode with the demo script armed, records with Playwright, stops
# the api. The newsroom worker and MCP server for a full rehearsal are started separately (T-062).
#   scripts/record_demo.sh [--only shot_a,shot_b]
set -e
cd "$(dirname "$0")/.."
PORT="${WHYLINE_API_PORT:-8000}"
for app in overlay studio fan; do npm --prefix "apps/$app" run build >/dev/null; done
export PYTHONPATH=packages WHYLINE_MODE=replay WHYLINE_DEMO_SCRIPT=packages/demo/demo_script.yaml
mkdir -p packages/demo/out
.venv/bin/python -m api.replay --seed "${WHYLINE_MATCH_SEED:-4242}" --port "$PORT" >packages/demo/out/api.log 2>&1 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
for _ in $(seq 1 100); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 0.1; done
.venv/bin/python -m demo.record_demo --shots packages/demo/shot_list.yaml --api "http://127.0.0.1:$PORT" "$@"

#!/bin/sh
# Video v3 studio takes on the recorded real-clip newsroom run (no newsroom process: the run is in the blackboard).
# $1 = out dir (default packages/demo/out/v3). The blackboard is copied, so the veto's decision lands in the copy.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="${1:-$ROOT/packages/demo/out/v3}"; W=$(mktemp -d)
cd "$ROOT"
export PYTHONPATH=packages WHYLINE_MODE=replay
cp data/footage/liverpool-mancity-2526/cache/studio/blackboard.sqlite "$W/bb.sqlite"
mkdir -p "$OUT"
env WHYLINE_BLACKBOARD="$W/bb.sqlite" WHYLINE_SPEND_LEDGER="$W/ledger.jsonl" WHYLINE_DEMO_LOG="$OUT/demo_v3.log" \
  WHYLINE_DEMO_SCRIPT=packages/demo/demo_script_v3.yaml \
  .venv/bin/python -m api.replay --match m_9001 --port 8783 >"$W/api.log" 2>&1 &
A=$!
for _ in $(seq 1 150); do curl -sf http://127.0.0.1:8783/health >/dev/null && break; sleep 0.2; done
.venv/bin/python -m demo.record_demo --shots packages/demo/shot_list_v3.yaml --api http://127.0.0.1:8783 --out "$OUT" || true
kill $A 2>/dev/null || true
cp "$W/api.log" "$OUT/studio_api.log"
echo "== done: $OUT"

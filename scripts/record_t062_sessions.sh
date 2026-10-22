#!/bin/sh
# T-062 recording in two sessions. $1 = rehearsal dir (its bb.sqlite feeds session 2), $2 = out dir.
# Session 1: fresh blackboard, demo script armed, newsroom running (the kill and veto happen in the take).
# Session 2: the rehearsed blackboard, no newsroom, demo script off (every cue already on screen at its time).
set -e
ROOT=/Users/ahsanbilal/projects/football-hackathon
R="$1"; OUT="$2"; W=$(mktemp -d)
cd "$ROOT"
export PYTHONPATH=packages WHYLINE_MODE=replay WHYLINE_REPLAY_FEED=1
PY=.venv/bin/python
wait_api() { for _ in $(seq 1 150); do curl -sf "http://127.0.0.1:$1/health" >/dev/null && return 0; sleep 0.2; done; return 1; }

echo "== session 1: fresh blackboard, demo script armed, newsroom running"
mkdir -p "$W/s1"
S1="WHYLINE_BLACKBOARD=$W/s1/bb.sqlite WHYLINE_WORKER_PIDFILE=$W/s1/newsroom.pid WHYLINE_CHECKPOINT_DIR=$W/s1/ckpt WHYLINE_DEMO_LOG=$OUT/demo_session1.log WHYLINE_SPEND_LEDGER=$W/s1/ledger.jsonl"
env $S1 WHYLINE_DEMO_SCRIPT=packages/demo/demo_script.yaml $PY -m api.replay --seed 4242 --port 8781 --feed >"$W/s1/api.log" 2>&1 &
A1=$!
env $S1 $PY -m newsroom.supervisor --mode replay --match m_4242 >"$W/s1/newsroom.log" 2>&1 &
N1=$!
wait_api 8781; sleep 6
$PY -m demo.record_demo --shots packages/demo/shot_list.yaml --api http://127.0.0.1:8781 --out "$OUT" \
  --only panel_kill_studio,veto_studio || true
kill $N1 $A1 2>/dev/null || true; sleep 2
cp "$W/s1/api.log" "$OUT/session1_api.log"; cp "$W/s1/newsroom.log" "$OUT/session1_newsroom.log"
$PY - "$W/s1/bb.sqlite" > "$OUT/session1_traces.json" <<'PY'
import collections, json, sys
from blackboard import SqliteBlackboard
bb = SqliteBlackboard(sys.argv[1])
ts = bb.query("traces", match_id="m_4242")
print(json.dumps({"by_status": collections.Counter(t["status"] for t in ts),
                  "red": [(t["executor"], t["status"], t.get("moment_id"), t.get("reason")) for t in ts
                          if t["status"] in ("cache_miss", "error", "interrupted")],
                  "decisions": [(d["request_id"], d["decision"]) for d in bb.query("decisions")]}, indent=1))
PY

echo "== session 2: rehearsed blackboard, no newsroom, demo script disarmed"
mkdir -p "$W/s2"; cp "$R/bb.sqlite" "$W/s2/bb.sqlite"
[ -f "$R/bb.sqlite-wal" ] && cp "$R/bb.sqlite-wal" "$W/s2/bb.sqlite-wal" || true
env WHYLINE_BLACKBOARD="$W/s2/bb.sqlite" WHYLINE_SPEND_LEDGER="$W/s2/ledger.jsonl" \
  $PY -m api.replay --seed 4242 --port 8782 --feed >"$W/s2/api.log" 2>&1 &
A2=$!
wait_api 8782
$PY -m demo.record_demo --shots packages/demo/shot_list.yaml --api http://127.0.0.1:8782 --out "$OUT" \
  --only opener_3d,sliding_doors_2d,sliding_doors_3d_player,sliding_doors_3d_wide,fourth_official,oracle,dugout,split_analyst,split_casual,split_player_cam,halftime || true
kill $A2 2>/dev/null || true
cp "$W/s2/api.log" "$OUT/session2_api.log"
echo "== done: $W"

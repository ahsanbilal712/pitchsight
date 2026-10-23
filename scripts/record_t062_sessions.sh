#!/bin/sh
# T-062 recording in two sessions. $1 = rehearsal dir (its bb.sqlite feeds session 2), $2 = out dir.
# Session 1: per live beat (kill, veto) a fresh blackboard, demo script armed, newsroom running, so the beat
# happens in the take. ONLY_SESSION1=1 skips session 2.
# Session 2: the rehearsed blackboard, no newsroom, demo script off (every cue already on screen at its time).
set -e
ROOT=/Users/ahsanbilal/projects/football-hackathon
R="$1"; OUT="$2"; W=$(mktemp -d)
cd "$ROOT"
export PYTHONPATH=packages WHYLINE_MODE=replay WHYLINE_REPLAY_FEED=1
PY=.venv/bin/python
wait_api() { for _ in $(seq 1 150); do curl -sf "http://127.0.0.1:$1/health" >/dev/null && return 0; sleep 0.2; done; return 1; }

# each live beat gets its own fresh session, so the newsroom is idle when the take starts
for SHOT in ${SESSION1_SHOTS:-panel_kill_studio veto_studio}; do
echo "== session 1 ($SHOT): fresh blackboard, demo script armed, newsroom running"
D="$W/s1_$SHOT"; mkdir -p "$D"
S1="WHYLINE_BLACKBOARD=$D/bb.sqlite WHYLINE_WORKER_PIDFILE=$D/newsroom.pid WHYLINE_CHECKPOINT_DIR=$D/ckpt WHYLINE_DEMO_LOG=$OUT/demo_$SHOT.log WHYLINE_SPEND_LEDGER=$D/ledger.jsonl"
# a take that warms up across the kill clock (veto_studio, v2) runs the demo script without the kill
SCRIPT=packages/demo/demo_script.yaml
[ "$SHOT" = veto_studio ] && { grep -v 'action: kill' "$SCRIPT" > "$D/demo_script.yaml"; SCRIPT="$D/demo_script.yaml"; }
env $S1 WHYLINE_DEMO_SCRIPT="$SCRIPT" $PY -m api.replay --seed 4242 --port 8781 --feed >"$D/api.log" 2>&1 &
A1=$!
env $S1 $PY -m newsroom.supervisor --mode replay --match m_4242 >"$D/newsroom.log" 2>&1 &
N1=$!
wait_api 8781; sleep 6
$PY -m demo.record_demo --shots packages/demo/shot_list.yaml --api http://127.0.0.1:8781 --out "$OUT" --only "$SHOT" || true
kill $N1 $A1 2>/dev/null || true; sleep 2
$PY - "$D/bb.sqlite" > "$OUT/${SHOT}_traces.json" <<'PY'
import collections, json, sys
from blackboard import SqliteBlackboard
bb = SqliteBlackboard(sys.argv[1])
ts = bb.query("traces", match_id="m_4242")
print(json.dumps({"by_status": collections.Counter(t["status"] for t in ts),
                  "red": [(t["executor"], t["status"], t.get("moment_id"), t.get("reason")) for t in ts
                          if t["status"] in ("cache_miss", "error", "interrupted")],
                  "decisions": [(d["request_id"], d["decision"]) for d in bb.query("decisions")]}, indent=1))
PY
done

[ -n "$ONLY_SESSION1" ] && { echo "== done (session 1 only): $W"; exit 0; }
echo "== session 2: rehearsed blackboard, no newsroom, demo script disarmed"
mkdir -p "$W/s2"; cp "$R/bb.sqlite" "$W/s2/bb.sqlite"
[ -f "$R/bb.sqlite-wal" ] && cp "$R/bb.sqlite-wal" "$W/s2/bb.sqlite-wal" || true
env WHYLINE_BLACKBOARD="$W/s2/bb.sqlite" WHYLINE_SPEND_LEDGER="$W/s2/ledger.jsonl" \
  $PY -m api.replay --seed 4242 --port 8782 --feed >"$W/s2/api.log" 2>&1 &
A2=$!
wait_api 8782
$PY -m demo.record_demo --shots packages/demo/shot_list.yaml --api http://127.0.0.1:8782 --out "$OUT" \
  --only "${SESSION2_SHOTS:-opener_3d,sliding_doors_2d,sliding_doors_3d_player,sliding_doors_3d_wide,fourth_official,oracle,dugout,split_analyst,split_casual,split_player_cam,halftime}" || true
kill $A2 2>/dev/null || true
cp "$W/s2/api.log" "$OUT/session2_api.log"
echo "== done: $W"

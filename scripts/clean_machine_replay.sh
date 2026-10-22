#!/usr/bin/env bash
# Clean-machine replay test (T-064, DEMO_MASTERPLAN §9 item 1, TECH_PLAN 1.12 "Judges can test").
#
#   bash scripts/clean_machine_replay.sh [--runs 3] [--speed 10] [--keep]
#
# Clones the committed HEAD into a temporary folder, builds a fresh Python 3.12 venv from requirements.lock (the
# only step that uses the network), then runs scripts/replay_headless.py --runs times with no .env, every API key
# variable unset, gcloud pointed at an empty config, and the harness's loopback-only network guard. Passes when every
# run delivers the same cue-stream SHA-256 and no process tried to reach anything but localhost.
set -euo pipefail

RUNS=3
SPEED=10
KEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runs) RUNS="$2"; shift 2 ;;
    --speed) SPEED="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3.12}"
TMP="$(mktemp -d -t whyline_clean.XXXXXX)"
cleanup() { if [[ "$KEEP" == 0 ]]; then rm -rf "$TMP"; else echo "kept $TMP"; fi; }
trap cleanup EXIT

echo "clone $(git -C "$REPO" rev-parse --short HEAD) -> $TMP/whyline"
git clone --quiet --no-hardlinks "$REPO" "$TMP/whyline"
cd "$TMP/whyline"
[[ ! -e .env ]] || { echo ".env present in a fresh clone" >&2; exit 1; }

echo "fresh venv ($("$PY" --version)) + requirements.lock"
"$PY" -m venv "$TMP/venv"
"$TMP/venv/bin/python" -m pip install --quiet --upgrade pip
"$TMP/venv/bin/python" -m pip install --quiet -r requirements.lock

unset ANTHROPIC_API_KEY GOOGLE_API_KEY GEMINI_API_KEY GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT \
  AZURE_OPENAI_API_KEY WHYLINE_BATCH_BUCKET || true
export CLOUDSDK_CONFIG="$TMP/no-gcloud"

hashes=()
for i in $(seq 1 "$RUNS"); do
  out="$TMP/run$i/cues.jsonl"
  line="$("$TMP/venv/bin/python" scripts/replay_headless.py --seed 4242 --speed "$SPEED" --out "$out" \
          --work "$TMP/run$i/work" | tail -1)"
  echo "run $i: $line"
  hashes+=("$("$TMP/venv/bin/python" -c 'import json,sys; print(json.loads(sys.argv[1])["sha256"])' "$line")")
done

first="${hashes[0]}"
for h in "${hashes[@]}"; do
  if [[ "$h" != "$first" ]]; then
    echo "FAIL: cue-stream hashes differ: ${hashes[*]}" >&2
    diff "$TMP/run1/cues.jsonl" "$TMP/run2/cues.jsonl" | head -20 >&2 || true
    KEEP=1
    exit 1
  fi
done
echo "PASS: $RUNS runs, cue-stream sha256 $first"

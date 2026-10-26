#!/bin/zsh
# Render every beat of a generated cut (demo.match_cut) six at a time, then assemble it.
#   packages/demo/match_render.sh <slug> <name>
set -e
cd "$(dirname "$0")/../.."
PYTHONPATH=packages .venv/bin/python packages/demo/match_cut.py "$1" "$2"
export PITCHSIGHT_MOMENTS="$PWD/packages/demo/out/$2_moments.yaml"
mkdir -p packages/demo/out/logs
grep -o "footage/$2_[0-9]*_[a-z]*" "packages/demo/out/edit_$2.yaml" | sed 's#footage/##' | sort -u |
  xargs -P 6 -I{} sh -c 'cd packages && ../.venv/bin/python -m demo.composite {} > demo/out/logs/{}.log 2>&1 || echo "FAILED {}"'
.venv/bin/python packages/demo/assemble.py "packages/demo/out/edit_$2.yaml" | tail -1

# Clean-machine replay, v0.1 (T-064)

Command: `bash scripts/clean_machine_replay.sh --runs 3` (also `make clean-replay`). Run 23 Oct 2026 on the
development Mac (Apple silicon, Python 3.12.12), commit `3c9e478`.

What it does: `git clone` of HEAD into a temporary folder (no `.env`, no runtime files, no policy checkpoints), a
fresh venv from `requirements.lock`, every API-key variable unset and gcloud pointed at an empty config, then
`scripts/replay_headless.py --seed 4242 --speed 10` three times. Each run starts `python -m mcp_server`,
`python -m newsroom.supervisor --mode replay` and `python -m api.replay --feed` on free localhost ports with a
fresh blackboard, checkpoint folder and spend ledger; every process loads a `sitecustomize` network guard that
refuses any socket connection that is not loopback and logs it. The replay clock plays the golden match to full
time; the worker answers every moment from the committed cache. The cue stream (sorted by cue id, volatile fields
removed) is hashed.

| Run | Cue-stream SHA-256 | Cues | Verified | Moments run | Refused connections | Wall time |
|---|---|---|---|---|---|---|
| 1 | `b90e1e0312860f46d60dd91d2faffb515580bf157edbbe7fd5b026d57cb1e994` | 55 | 55 | 125/125 | 0 | 546 s |
| 2 | `b90e1e0312860f46d60dd91d2faffb515580bf157edbbe7fd5b026d57cb1e994` | 55 | 55 | 125/125 | 0 | 550 s |
| 3 | `b90e1e0312860f46d60dd91d2faffb515580bf157edbbe7fd5b026d57cb1e994` | 55 | 55 | 125/125 | 0 | 545 s |

**Result: PASS.** Three consecutive runs from a fresh clone and venv, with networking blocked and no keys, produce
the same cue stream; the same hash came from a run in the development checkout. Recaps wait for a producer
decision, which the harness does not send, so they are not in the stream.

Earlier attempt (commit `5315eba`): the worker stopped taking moments after mo_00020 and the run timed out after an
hour; it did not recur in the four runs since (commits in between include track C's T-062 change to how the demo
veto request reaches the worker). The harness now fails within 240 s when no moment completes and dumps every
process's stacks (faulthandler on SIGUSR1) into its logs, so a recurrence comes with a diagnosis.

`make demo` (`docker compose up --build`, six services: api :8000, mcp :8080, newsroom, overlay :5173, studio
:5174, fan :5175) is defined in `docker-compose.yml` and validated with `docker compose config`; it was not started
here because the Docker daemon was not running on this machine.

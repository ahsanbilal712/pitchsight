# For the judges

## Watch first

The demo video (v10, 1:48) shows Pitchsight on real Premier League broadcast footage, used with the Premier
League's written permission ([permissions](permissions/README.md), [sources](../data/footage/SOURCES.md)). Its link
is in the [README](../README.md#the-video) once uploaded.

## About the real footage

- The clips are never in this repository and are not distributed as files: the permission covers the prototype, the
  hosted demonstration for judges and the public demo video, and excludes redistribution. You see the footage in the
  video, and streamed from the demo where it is hosted.
- The hosted demo is not deployed at the moment: everything below runs locally. The Azure deployment
  (`azd up`, [infra/README.md](../infra/README.md)) is in the repository and has not been provisioned yet.
- What is model output and what is measured is stated in the README's
  [Limits](../README.md#limits-stated-plainly): positions come from broadcast tracking (about 0.5 m), the
  counterfactuals run in the synthetic engine, the Fourth Official card is an assessment, not a ruling.

## Run it locally (no keys)

1. `git clone https://github.com/ahsanbilal712/pitchsight.git && cd pitchsight`
2. `make demo` (docker compose: the api, the newsroom and the three screens replaying the synthetic golden match)
3. Open the overlay at http://localhost:5173, the studio at http://localhost:5174 and the fan app at
   http://localhost:5175 (the api is on :8000).

In the studio you can follow every agent step on the trace, open the Why? drawer on any cue, veto a recap before it
airs, and kill the newsroom mid-moment to watch it resume from its checkpoint.

## The studio on a real clip

The producer studio can also replay a real clip's recorded newsroom run (Liverpool v Manchester City, 86:23 and the
held full-time recap), with real names, no keys and no model calls:

```bash
cp data/footage/liverpool-mancity-2526/cache/studio/blackboard.sqlite /tmp/pitchsight-lfc.sqlite
PYTHONPATH=packages WHYLINE_BLACKBOARD=/tmp/pitchsight-lfc.sqlite .venv/bin/python -m api.replay --match m_9001
```

Then serve `apps/studio/dist` and open it with `?api=127.0.0.1:8000`, seek to 86:16 and press play.

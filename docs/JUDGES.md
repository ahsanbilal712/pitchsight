# For the judges

## Watch first

The demo video (1:55) shows Pitchsight on real Premier League broadcast footage, used with the Premier League's
written permission ([permissions](permissions/README.md), [sources](../data/footage/SOURCES.md)). The clips are not in
this repository: the permission excludes redistribution, so the footage appears in the video only.

## Run it locally (no keys)

1. `git clone https://github.com/ahsanbilal712/pitchsight.git && cd pitchsight`
2. `make demo` (docker compose: the api, the newsroom and the three screens replaying the synthetic golden match)
3. Open the overlay at http://localhost:5173, the studio at http://localhost:5174 and the fan app at
   http://localhost:5175 (the api is on :8000).

In the studio you can follow every agent step on the trace, open the Why? drawer on any cue, veto a recap before it
airs, and kill the newsroom mid-moment to watch it resume from its checkpoint.

## The studio on a real clip

The producer studio also replays a real clip's recorded newsroom run (Liverpool v Manchester City, 86:23 and the
held full-time recap), with real names, no keys and no model calls:

```bash
cp data/footage/liverpool-mancity-2526/cache/studio/blackboard.sqlite /tmp/pitchsight-lfc.sqlite
PYTHONPATH=packages WHYLINE_BLACKBOARD=/tmp/pitchsight-lfc.sqlite .venv/bin/python -m api.replay --match m_9001
```

Then serve `apps/studio/dist` and open it with `?api=127.0.0.1:8000`, seek to 86:16 and press play.

## Deploy to Azure

`azd up` provisions the full stack (Container Apps, Static Web Apps, Cosmos DB, Web PubSub, Application Insights,
Azure AI Foundry) from [infra/README.md](../infra/README.md); every service reads its endpoints from the environment.

## Where to look

- Agents: `packages/newsroom/` (Microsoft Agent Framework workflow, checkpoints and resume), tools over MCP in
  `packages/mcp_server/`.
- Evidence binding: `packages/newsroom/factcheck.py`; evaluation table: `packages/evals/results.md`.
- Vision on broadcast footage: `packages/evals/pitchwatch/`; drawing on the real frame: `packages/demo/composite.py`.
- Azure path: `packages/cloud/`, `infra/`.

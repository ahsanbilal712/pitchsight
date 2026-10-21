# api

FastAPI replay server, WebSocket stream, cue fan-out, ingest, control endpoints and SpendGuard.

Interface restated from `TECH_PLAN.md` section 1.4 "api" (TECH_PLAN wins on conflict).
Tests live in `tests/api/`. Run: `PYTHONPATH=packages python -m api.replay --seed 4242` (port `WHYLINE_API_PORT`).

FastAPI (pin at T-001). Endpoints: `GET /health`, `GET /match/{id}/events?from&to`, `GET /match/{id}/cues?viewer=…`, `POST /ingest/events`, `POST /ingest/tracking`, `POST /replay/control {action: play|pause|seek|speed}`, `POST /producer/decision {request_id, decision}`, `POST /demo/kill {target}`, `GET /spend`, `WS /ws?viewer_id&mode&club&player` (messages in 1.9). `SpendGuard` middleware wraps every `LLMClient` call. Performance: cue fan-out to 20 clients < 50 ms.

## As built (T-022, T-033)

| Endpoint | Module | Notes |
|---|---|---|
| `GET /health` | `main.py` | match, mode, connected clients, replay clock, stream clock |
| `GET /match/{id}/events?from&to` | `main.py` | `from`/`to` in ms or `mm:ss`; replayed match from `events.jsonl`, live matches from blackboard `events` |
| `GET /match/{id}/cues?viewer=<mode>&club&player` | `cues.py` | cues that profile would receive; vetoed cues excluded; `viewer` defaults to `studio` (all) |
| **`GET /match/{id}/doc/{collection}/{doc_id}`** | `docs.py` | **addition to the 1.4 list**: read-only blackboard documents for the studio Why? drawer and `/replay3d`. Whitelist: `counterfactuals`, `explanations`, `pitch_control`, `moments`, `facts`, `events` |
| **`GET /match/{id}/doc/{doc_id}`** | `docs.py` | **addition**: same, collection from the id prefix (`cf_`, `ex_`, `pc_`, `mo_`, `f_`, `e_`), so every evidence id in a claim resolves |
| `POST /ingest/events` | `ingest.py` | one event or a list; stored in blackboard `events`; the first post switches the stream to live mode |
| `POST /ingest/tracking?match_id=` | `ingest.py` | one `tracking_frame` or a list (exact 1.3 shape, 23 rows) |
| `POST /replay/control` | `control.py` | `{action: play\|pause\|seek\|speed, value}`; seek also takes `t_ms`; speed x1..x10 |
| `POST /producer/decision` | `control.py` | `{request_id, decision: approved\|vetoed\|held}` (approve/veto/hold accepted) → blackboard `decisions/<request_id>` for the worker; a veto of a shown cue id also marks the cue `vetoed` and broadcasts `cue_remove` |
| `POST /demo/kill {target}` | `control.py` | 202 stub until T-051 |
| `GET /spend` | `main.py` | `{match_usd, day_usd, project_usd, caps}` from the ledger; also streamed to studio every 5 s as `spend` |
| `WS /ws` | `ws.py` | see below |

**Stream** (`ws.py`, `cues.py`, `messages.py`). Every 1.9 message type is produced: `hello`, `tracking_frame`,
`event` (replay clock or ingest); `fact`, `moment`, `cue`, `oracle` from the blackboard collections `facts`,
`moments`, `cues`, `oracle`, released when the stream clock reaches their `t_ms` (`t_in_ms` for cues); `trace`,
`mode`, `request_info` from `traces`, `modes`, `requests` (`{request_id, cue}`) as soon as they are written;
`cue_remove` on a veto; `spend` every 5 s. Additions screens use: `lineup` (substitutions), `counterfactual`
(sent before the first cue that names it), and extra `hello` fields (`t_ms`, `score`, `player_ids`, `clubs`).
A `hello` is re-sent after each seek with a snapshot (cues on screen, latest fact per name, recent moments for
studio).

**Filtering** (server side, `messages.cue_matches`): studio gets every cue; others need their mode in
`targets.modes`, a matching club unless `targets.clubs` has `any`, and for `player_tag`/`decision_index` cues with
`targets.players` a player_cam viewer of one of those players. `moment`, `trace`, `request_info` and `spend` go to
studio only.

**Live**: `python -m kickoff play --seed N --target api [--api URL] [--speed S]` (`packages/kickoff/stream.py`).

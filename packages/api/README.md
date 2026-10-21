# api

FastAPI replay server, WebSocket stream and SpendGuard.

Interface restated from `TECH_PLAN.md` section 1.4 "api" (TECH_PLAN wins on conflict).
Tests live in `tests/api/`.

FastAPI (pin at T-001). Endpoints: `GET /health`, `GET /match/{id}/events?from&to`, `GET /match/{id}/cues?viewer=…`, `POST /ingest/events`, `POST /ingest/tracking`, `POST /replay/control {action: play|pause|seek|speed}`, `POST /producer/decision {request_id, decision}`, `POST /demo/kill {target}`, `GET /spend`, `WS /ws?viewer_id&mode&club&player` (messages in 1.9). `SpendGuard` middleware wraps every `LLMClient` call. Performance: cue fan-out to 20 clients < 50 ms.

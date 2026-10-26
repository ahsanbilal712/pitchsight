# WHYLINE developer targets. `make ci` mirrors the lint, unit, schemas and spend-ledger CI jobs.
VENV ?= .venv
PY := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python)

.PHONY: ci lint unit schemas spend hooks overlay demo clean-replay

ci: lint unit schemas spend

lint:
	$(PY) -m ruff check .

unit: overlay
	$(PY) -m pytest -q -m "not live"

overlay:
	npm --prefix apps/overlay run build

schemas:
	$(PY) scripts/validate_schemas.py

spend:
	$(PY) scripts/check_spend.py

hooks:
	sh scripts/install_hooks.sh

# The six services and the golden replay in one command: open :5173, :5174, :5175.
demo:
	docker compose up --build

# Three replays from a fresh clone and venv, no keys, loopback-only network: identical cue streams.
clean-replay:
	bash scripts/clean_machine_replay.sh --runs 3

# WHYLINE developer targets. `make ci` mirrors the four CI jobs that are live from T-005.
VENV ?= .venv
PY := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python)

.PHONY: ci lint unit schemas spend hooks

ci: lint unit schemas spend

lint:
	$(PY) -m ruff check .

unit:
	$(PY) -m pytest -q -m "not live"

schemas:
	$(PY) scripts/validate_schemas.py

spend:
	$(PY) scripts/check_spend.py

hooks:
	sh scripts/install_hooks.sh

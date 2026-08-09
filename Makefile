.PHONY: demo dev test test-live coverage mutants eval eval-live fit seed check audit preflight install frontend fixtures release clean

UV      ?= uv
PY      ?= $(UV) run python
PORT    ?= 8000
RUNS    ?= 3

## install --- sync the pinned toolchain (python 3.12 via uv)
install:
	$(UV) sync --all-extras

## frontend --- build the SPA into backend/app/static
frontend:
	cd frontend && npm install --silent && npm run build

## demo --- the single command. Cold start to a usable UI. (FR-106, NFR-11)
demo: install frontend
	@$(PY) -m app.cli.preflight
	$(UV) run uvicorn app.main:app --host 127.0.0.1 --port $(PORT)

## dev --- backend with reload; run `cd frontend && npm run dev` alongside
dev: install
	$(UV) run uvicorn app.main:app --reload --host 127.0.0.1 --port $(PORT)

## test --- the deterministic suite. Fast, free, no network. Excludes `live`.
test: install
	$(UV) run pytest -q -m "not live"

## test-live --- the shipped configuration, against the real API. Costs money.
##   The product runs live-first, so this is the suite that tests what ships.
test-live: install
	@test -n "$$ANTHROPIC_API_KEY" || { echo "  ANTHROPIC_API_KEY is not set"; exit 1; }
	$(UV) run pytest -q -m live tests/live

## check --- lint + types + structural guards
check: install
	$(UV) run ruff check backend tests
	$(UV) run mypy backend/app/domain backend/app/reasoner
	$(UV) run pytest -q tests/structure

## eval --- golden-set harness -> scorecard + exit code (FR-092..FR-101)
eval: install
	$(PY) -m app.eval.run

## eval-live --- the scorecard against the real API. 54 calls, billed.
eval-live: install
	@test -n "$$ANTHROPIC_API_KEY" || { echo "  ANTHROPIC_API_KEY is not set"; exit 1; }
	$(PY) -m app.eval.run --live

## fit --- fit the weight vector to the golden labels (FR-098)
fit: install
	$(PY) -m app.eval.fit

## seed --- regenerate the reference dataset. NEVER invoked by demo. (FR-103)
seed: install
	$(PY) -m app.cli.generate_seed

## preflight --- readiness report (NFR-12)
preflight: install
	$(PY) -m app.cli.preflight

## coverage --- line coverage, so gaps are a number rather than an impression
coverage: install
	$(UV) run --with pytest-cov python -m pytest tests -q \
		--cov=backend/app --cov-report=term-missing

## mutants --- mutation testing over the decision core (~2 min)
##   Coverage says a line ran. This asks whether a test would notice it being wrong.
mutants: install
	$(PY) scripts/mutate.py

## audit --- known-CVE scan over both dependency trees
audit: install
	$(UV) run --with pip-audit python -m pip_audit
	cd frontend && npm audit

## fixtures --- record LLM fixtures. ONLINE, DELIBERATE, ONCE. Never on the demo path.
fixtures: install
	@test -n "$$ANTHROPIC_API_KEY" || { echo "  ANTHROPIC_API_KEY is not set"; exit 1; }
	SCHED_LLM_MODE=live $(PY) -m app.cli.record_fixtures

## release --- N cold starts, everything after install run with the network blocked
release: 
	scripts/release-check.sh $(RUNS)

clean:
	rm -rf .venv frontend/node_modules backend/app/static .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

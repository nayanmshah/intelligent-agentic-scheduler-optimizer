#!/usr/bin/env bash
#
# Release verification. Repeats a full cold start N times and fails on the first
# unrecovered error.
#
# The run is split into two phases on purpose, because conflating them would let the
# offline claim quietly become false:
#
#   Phase A -- toolchain install (uv sync, npm install). Needs the network. This is
#              not part of NFR-09: fetching pinned dependencies is a build step, not
#              a request path.
#   Phase B -- everything the product actually does: preflight, tests, the eval
#              scorecard, booting the server, answering real requests over HTTP.
#              Runs with outbound connections *blocked at the socket layer*
#              (scripts/offline/sitecustomize.py) and with ANTHROPIC_API_KEY unset.
#
# So "works with networking disabled" is enforced by the harness rather than asserted
# by the author. A path that reaches out raises instead of silently succeeding
# whenever the wifi happens to be up.
#
# Usage:  scripts/release-check.sh [runs]        # default 3
#         COLD=0 scripts/release-check.sh 1      # skip the destructive rebuild

set -uo pipefail

RUNS="${1:-3}"
COLD="${COLD:-1}"
PORT="${PORT:-8099}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OFFLINE_ENV=(env -u ANTHROPIC_API_KEY PYTHONPATH="$ROOT/scripts/offline" SCHED_LLM_MODE=fixtures)
LOG_DIR="${LOG_DIR:-$ROOT/.release-check}"
mkdir -p "$LOG_DIR"

pass=0; fail=0; failures=()

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
step() { printf '  %-46s' "$*"; }
ok()   { printf '\033[32mok\033[0m %s\n' "${1:-}"; }
bad()  { printf '\033[31mFAILED\033[0m %s\n' "${1:-}"; fail=$((fail+1)); failures+=("$1"); }

run_step() {         # run_step <label> <logfile> <cmd...>
  local label="$1" log="$2"; shift 2
  step "$label"
  if "$@" >"$log" 2>&1; then ok; return 0; fi
  bad "$label -- see $log"
  tail -20 "$log" | sed 's/^/      /'
  return 1
}

for run in $(seq 1 "$RUNS"); do
  say "═══ cold-start run $run of $RUNS ═══"
  L="$LOG_DIR/run$run"; mkdir -p "$L"
  started=$(date +%s)

  # ---- Phase A: build the world from nothing -------------------------------
  if [ "$COLD" = "1" ]; then
    step "clean (venv, node_modules, static, caches)"
    make clean >"$L/clean.log" 2>&1 && ok || bad "clean"
  fi
  run_step "install toolchain (network allowed)"  "$L/install.log"  make install || { continue; }
  run_step "build SPA (network allowed)"          "$L/frontend.log" make frontend || { continue; }

  # ---- Phase B: nothing below here may touch the network -------------------
  run_step "preflight [NFR-12]"      "$L/preflight.log" "${OFFLINE_ENV[@]}" uv run python -m app.cli.preflight
  run_step "test suite [offline]"    "$L/pytest.log"    "${OFFLINE_ENV[@]}" uv run pytest -q
  run_step "structural guards"       "$L/structure.log" "${OFFLINE_ENV[@]}" uv run pytest -q tests/structure
  run_step "lint + types"            "$L/check.log"     make check
  run_step "eval scorecard [FR-092]" "$L/eval.log"      "${OFFLINE_ENV[@]}" uv run python -m app.eval.run

  # ---- boot the real server and answer real requests -----------------------
  step "boot server on :$PORT"
  "${OFFLINE_ENV[@]}" uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
      >"$L/server.log" 2>&1 &
  server_pid=$!
  up=0
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then up=1; break; fi
    kill -0 "$server_pid" 2>/dev/null || break
    sleep 0.5
  done
  if [ "$up" = "1" ]; then ok "(pid $server_pid)"; else bad "server never became healthy"; fi

  if [ "$up" = "1" ]; then
    run_step "end-to-end smoke over HTTP" "$L/smoke.log" \
      "${OFFLINE_ENV[@]}" uv run python scripts/offline/smoke.py "http://127.0.0.1:$PORT"

    kill "$server_pid" 2>/dev/null; wait "$server_pid" 2>/dev/null
  fi

  step "no outbound connection was attempted"
  if grep -q 'outbound network is disabled for this run' "$L"/*.log 2>/dev/null; then
    bad "a MUST path tried to reach the network [NFR-09]"
    grep -h 'outbound network is disabled for this run' "$L"/*.log | head -3 | sed 's/^/      /'
  else
    ok
  fi

  printf '  run %d finished in %ds\n' "$run" "$(( $(date +%s) - started ))"
  pass=$((pass+1))
done

say "═══ summary ═══"
printf '  runs completed : %d/%d\n  failures       : %d\n' "$pass" "$RUNS" "$fail"
if [ "$fail" -gt 0 ]; then
  printf '\n  Unrecovered failures:\n'
  printf '    - %s\n' "${failures[@]}"
  printf '\n  Logs: %s\n' "$LOG_DIR"
  exit 1
fi
printf '  \033[32mRELEASE CHECK PASSED\033[0m -- %d cold starts, zero unrecovered failures.\n' "$RUNS"
printf '  Logs: %s\n' "$LOG_DIR"

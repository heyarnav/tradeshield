#!/usr/bin/env bash
set -o pipefail
cd "$(dirname "$0")/.."

echo "=== run_e2e.sh: single-command E2E (flask + next) ==="
echo "    This is the canonical one-command entry point for the Playwright suite."
echo "    The pytest fixture itself starts Flask + Next.js dev and tears both down;"
echo "    this script only ensures no stale servers are holding the ports."

# Best-effort cleanup of anything listening on the two E2E ports, so a rerun
# after a crash does not fail on address-already-in-use.
pkill -9 -f "run.py" 2>/dev/null || true
pkill -9 -f "next-server" 2>/dev/null || true
sleep 2

echo "=== run pytest (fixture owns server lifecycle) ==="
backend/.venv/bin/python -m pytest backend/tests/test_e2e_playwright.py -q "$@"
EXIT=$?

echo "=== done, exit $EXIT ==="
exit $EXIT

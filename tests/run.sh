#!/usr/bin/env bash
# Every module checks its own contract. This runs all of them.
set -u
cd "$(dirname "$0")/.."
status=0
for module in link_check scam_signals triage verdict_gate recovery_steps; do
    echo "== $module"
    python3 "scripts/$module.py" --self-test || status=1
    echo
done
exit $status

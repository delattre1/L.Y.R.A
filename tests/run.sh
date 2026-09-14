#!/usr/bin/env bash
# Every module checks its own contract. This runs all of them.
set -u
cd "$(dirname "$0")/.."
status=0
for module in language countries injection_check pii_check sender_check link_check scam_signals payment_check domain_age reputation triage verdict_gate recovery_steps recovery_gate police_report; do
    echo "== $module"
    python3 "scripts/$module.py" --self-test || status=1
    echo
done
exit $status

#!/usr/bin/env bash
# A script that errors on every call gets quarantined after its error budget,
# without the game hanging or logging the same stack trace forever.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TMP=$(test_capture "$ROOT/build/kp_luatest" "$ROOT/scripts/examples/edge_quarantine" \
  OnTick 1 --repeat 5)
trap 'rm -f "$TMP"' EXIT

assert_contains "$TMP" "quarantined after 3 errors" "the script quarantines on its third strike"
# Exactly 3 stack traces -- one per strike before quarantine -- not 5 (the
# --repeat count): dispatches 4 and 5 must not still be calling a quarantined
# script, or "quarantine" is a label with no effect behind it.
N=$(grep -c "deliberate failure on tick" "$TMP")
[[ "$N" -eq 3 ]] && ok "exactly 3 errors logged, not 5 -- quarantine actually stops dispatch" \
                  || bad "expected exactly 3 errors before quarantine, got $N"

summary_and_exit

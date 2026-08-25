#!/usr/bin/env bash
# The multi-script return-arbitration rule, without the game.
#
# scripts/examples/arbitration/ is six scripts that deliberately disagree about
# the same OnRunScript event. kp_luatest dispatches it once and prints who
# claimed it and why; this asserts the documented rule actually held:
# priority 80's string "1" converts and claims, despite two higher-priority
# scripts running first and abstaining.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
"$ROOT/build/kp_luatest" "$ROOT/scripts/examples/arbitration" \
  OnRunScript k_def_heartbt01 0 0 > "$TMP" 2>&1

assert_contains "$TMP" "claimed by  : 25_claims_via_string" "correct script claims the event"
assert_contains "$TMP" "reconciles  : yes" "called/abstained/errored/ignored/claimed reconcile"
assert_contains_re "$TMP" "abstained *: 2" "the two abstaining scripts are counted as abstentions, not errors"

summary_and_exit

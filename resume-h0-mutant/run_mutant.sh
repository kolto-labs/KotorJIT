#!/usr/bin/env bash
set -u

ROOT=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
BUILD=/tmp/lifecycle-cfg
OUT=/home/brunner56/kp-live-20260922/resume-h0-mutant
mkdir -p "$OUT"

if [ ! -x "$BUILD/libkphasor.so" ]; then
    echo "green shared lib not ready: $BUILD/libkphasor.so" >&2
    exit 3
fi
if [ ! -f "$ROOT/tools/kp_harnessdrain_test.cpp" ]; then
    echo "frozen fixture missing" >&2
    exit 3
fi

g++ -m32 -std=c++20 -Wall -Wextra -I "$ROOT/src" \
    -c "$ROOT/tools/kp_harnessdrain_test.cpp" -o "$OUT/fixture.o" \
    >"$OUT/compile_fixture.stdout" 2>"$OUT/compile_fixture.stderr"
g++ -m32 -std=c++20 -Wall -Wextra -I "$ROOT/src" \
    -c "$OUT/channel_push_reply_old.cpp" -o "$OUT/channel_push_reply_old.o" \
    >"$OUT/compile_mutant.stdout" 2>"$OUT/compile_mutant.stderr"
g++ -m32 -Wl,--export-dynamic "$OUT/fixture.o" "$OUT/channel_push_reply_old.o" \
    -L"$BUILD" -Wl,-rpath,"$BUILD" -lkphasor -lpthread -ldl -lm \
    -o "$OUT/kp_harnessdrain_mutant" \
    >"$OUT/link.stdout" 2>"$OUT/link.stderr"

nm -C -D "$OUT/kp_harnessdrain_mutant" >"$OUT/symbols.txt"
if ! rg -q 'T kp::harness::Channel::push_reply\(' "$OUT/symbols.txt"; then
    echo "mutant push_reply symbol is not exported by executable" >&2
    exit 4
fi

set +e
timeout 15s env KOTORPHASOR_NO_AUTOSTART=1 "$OUT/kp_harnessdrain_mutant" \
    >"$OUT/run.stdout" 2>"$OUT/run.stderr"
rc=$?
set -e
printf '%s\n' "$rc" >"$OUT/run.rc"

# The red control must fail the final-error invariant; a timeout or another
# unrelated failure is not evidence of the old admission behavior.
if [ "$rc" -ne 1 ]; then
    echo "expected mutant fixture rc=1, got $rc" >&2
    exit 5
fi
if ! rg -q '\[FAIL\] the error is the final line; no post-condemn event follows' "$OUT/run.stdout"; then
    echo "mutant did not fail the condemned-event invariant" >&2
    exit 6
fi
printf 'mutant invariant failure verified\n'

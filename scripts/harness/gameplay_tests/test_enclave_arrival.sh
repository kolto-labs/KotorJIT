#!/usr/bin/env bash
# tools/tests/examples/fixtures/legacy/showcase/50_enclave_arrival.lua — OnModuleLoad greeting per world.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
OUT="${OUT:-$ROOT/tmp/gameplay-test-enclave-arrival}"
DISPLAY_NUM="${DISPLAY_NUM:-89}"

deploy_scripts "$GAME_DIR" "$ROOT/tools/tests/examples/fixtures/legacy/showcase/50_enclave_arrival.lua"
rm -f "$GAME_DIR/kotorphasor.log"

start_live_session "$GAME_DIR" "$OUT" "$DISPLAY_NUM"

send "warp danm13"
send "#sleep 55"
send "warp manm26ad"
send "#sleep 55"

assert_contains_re "$GAME_DIR/kotorphasor.log" '\[arrival\] dan' \
  "50_enclave_arrival spoke on Dantooine (danm13)"
assert_contains_re "$GAME_DIR/kotorphasor.log" '\[arrival\] man' \
  "50_enclave_arrival spoke on Manaan (manm26ad)"

summary_and_exit

#!/bin/sh
set -e
WT=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
LJ=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/build/luajit32/src
RP2=/home/brunner56/kp-live-20260922/review-probes-lifecycle-r2
cd "$WT"
COMMON="-std=c++20 -m32 -Wall -Wextra -Isrc -I$LJ"
BASE="src/api/output.cpp src/api/timers.cpp src/api/strings.cpp src/lua/host.cpp src/lua/value.cpp src/platform/platform.cpp src/platform/platform_linux.cpp"
for t in "$@"; do
  case $t in
    lifecycle) g++ $COMMON tools/kp_lifecycletest.cpp $BASE $LJ/libluajit.a -lm -ldl -o $RP2/bin/kp_lifecycletest ;;
    scriptsapi) g++ $COMMON -DKP_REPO="\"$WT\"" tools/kp_scriptsapitest.cpp src/api/scripts_lua.cpp $BASE $LJ/libluajit.a -lm -ldl -o $RP2/bin/kp_scriptsapitest ;;
    probe) g++ $COMMON $RP2/probe_lifecycle.cpp src/api/scripts_lua.cpp $BASE $LJ/libluajit.a -lm -ldl -o $RP2/bin/probe_lifecycle ;;
    casefold) g++ $COMMON $RP2/probe_casefold.cpp src/api/scripts_lua.cpp $BASE $LJ/libluajit.a -lm -ldl -o $RP2/bin/probe_casefold ;;
    r2) g++ $COMMON $RP2/probe_r2.cpp src/api/scripts_lua.cpp $BASE $LJ/libluajit.a -lm -ldl -o $RP2/bin/probe_r2 ;;
  esac
  echo "built $t rc=$?"
done

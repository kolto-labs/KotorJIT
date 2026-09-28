#!/bin/bash
set -x
export PYTHONDONTWRITEBYTECODE=1
D=/home/brunner56/kp-live-20260922/dll-build-20260928
W=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
G=/run/host/usr/bin/i686-w64-mingw32-g++

echo "=== compiler version ==="
"$G" --version
/run/host/usr/bin/i686-w64-mingw32-objdump --version | head -1

echo "=== configure ==="
cmake -S "$W" -B "$D/build" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DKP_MINGW_CXX="$G" \
  2>&1

echo "=== build (kphasor_dll only, -j2) ==="
cmake --build "$D/build" --target kphasor_dll -j2 2>&1

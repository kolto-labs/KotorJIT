#!/bin/sh
set -e
cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
mkdir -p /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/tmpcc
export TMPDIR=/home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/tmpcc
COMMON="-std=c++20 -O1 -Wall -Wextra -Isrc -I/run/media/brunner56/MyBook/Workspaces/KotorPhasor/third_party/luajit/src"
BASE="src/api/output.cpp src/api/timers.cpp src/api/strings.cpp src/lua/host.cpp src/lua/value.cpp src/platform/platform.cpp src/platform/platform_win32.cpp"
LIBS="/run/media/brunner56/MyBook/Workspaces/KotorPhasor/third_party/luajit/src/libluajit.a -static -static-libgcc -static-libstdc++"
for t in "$@"; do
  case $t in
    lifecycle) i686-w64-mingw32-g++ $COMMON tools/kp_lifecycletest.cpp $BASE $LIBS -o /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/kp_lifecycletest.exe ;;
    casefold) i686-w64-mingw32-g++ $COMMON /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/probe_casefold.cpp src/api/scripts_lua.cpp $BASE $LIBS -o /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/probe_casefold.exe ;;
    r2) i686-w64-mingw32-g++ $COMMON /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/probe_r2.cpp src/api/scripts_lua.cpp $BASE $LIBS -o /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/probe_r2.exe ;;
    equiv) i686-w64-mingw32-g++ -std=c++20 /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/equiv.cpp -static -static-libgcc -static-libstdc++ -o /home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/win/equiv.exe ;;
  esac
  echo "built $t"
done

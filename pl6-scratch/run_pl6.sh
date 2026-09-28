#!/bin/sh
set -eu
D=${1:-/home/brunner56/kp-live-20260922/pl6-scratch}
O=${2:-/tmp/kp-pl6-snippet}
mkdir -p "$O"
WT=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
g++ -m32 -std=c++20 -Wall -Wextra -Werror -I"$D/src" -I"$WT/src" \
  "$D/pause_lease_snippet2.cpp" "$D/src/harness/pause_lease.cpp" \
  "$D/publication_direct_caller_test.cpp" -pthread -o "$O/publication_direct_caller_test"
"$O/publication_direct_caller_test"
g++ -m32 -std=c++20 -Wall -Wextra -Werror -I"$D/src" -I"$WT/src" \
  "$D/pause_lease_snippet2.cpp" "$D/src/harness/pause_lease.cpp" \
  "$D/owner_thread_passthrough_test.cpp" -pthread -o "$O/owner_thread_passthrough_test"
"$O/owner_thread_passthrough_test"

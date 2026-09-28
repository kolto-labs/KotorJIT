#!/bin/sh
W=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
O=/home/brunner56/kp-live-20260922/review-probes-camera-r2
SRC="$W/tools/kp_cameratest.cpp $W/src/api/camera.cpp $W/src/api/camera_profiles.cpp $W/src/api/camera_backend.cpp $W/src/api/camera_lua.cpp"
INC="-I$W/src -I$W/tools -I$W/third_party/luajit/src"
i=0
while read -r name flags; do
  [ -z "$name" ] && continue
  g++ $flags -m32 -Wall -Wextra $INC $SRC $O/libluajit.a -lm -ldl -o $O/kpc_$name 2>$O/warn_$name.txt
  b=$?
  out=$($O/kpc_$name 2>&1); r=$?
  echo "$name [$flags] build=$b warnings=$(wc -l <$O/warn_$name.txt) rc=$r :: $out"
done <<L
std_O3 -O3 -DNDEBUG -std=c++20
std_O0 -O0 -std=c++20
std_O2 -O2 -DNDEBUG -std=c++20
sse_O3 -O3 -DNDEBUG -std=c++20 -msse2 -mfpmath=sse
gnu_O3 -O3 -DNDEBUG -std=gnu++20
gnu_sse_O3 -O3 -DNDEBUG -std=gnu++20 -msse2 -mfpmath=sse
gnu_O0 -O0 -std=gnu++20
std_fast_O3 -O3 -DNDEBUG -std=c++20 -fexcess-precision=fast
L
echo "FLT_EVAL c++20:"; echo | g++ -m32 -std=c++20 -dM -E -x c++ - | grep FLT_EVAL_METHOD
echo "FLT_EVAL sse:"; echo | g++ -m32 -std=c++20 -msse2 -mfpmath=sse -dM -E -x c++ - | grep FLT_EVAL_METHOD
g++ --version | head -1

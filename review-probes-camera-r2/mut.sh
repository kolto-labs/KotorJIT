W=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation; O=/home/brunner56/kp-live-20260922/review-probes-camera-r2
for fl in "-O3 -DNDEBUG -std=c++20" "-O3 -DNDEBUG -std=c++20 -msse2 -mfpmath=sse" "-O3 -DNDEBUG -std=gnu++20"; do
g++ $fl -m32 -I$W/src -I$W/tools -I$W/third_party/luajit/src $O/mut_unfixed.cpp $W/src/api/camera.cpp $W/src/api/camera_profiles.cpp $W/src/api/camera_backend.cpp $W/src/api/camera_lua.cpp $O/libluajit.a -lm -ldl -o $O/mut && out=$($O/mut 2>&1); echo "unfixed [$fl] rc=$? :: $out"
done

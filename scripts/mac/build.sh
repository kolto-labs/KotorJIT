#!/usr/bin/env bash
# Build libkotorjit.dylib for the x86_64 macOS Steam builds of KOTOR 1 and 2.
#
# Everything is -arch x86_64, deployment 10.13: the retail games are x86_64,
# and on Apple silicon they run under Rosetta 2, so the runtime we inject must
# match. Run this on a Mac with Xcode Command Line Tools. No network is needed;
# LuaJIT and Dear ImGui are vendored under third_party/.
#
#   scripts/mac/build.sh              # builds build-mac/libkotorjit.dylib
#   scripts/mac/build.sh clean
#
# Output: build-mac/libkotorjit.dylib (ad-hoc signed). Install it with
# scripts/mac/install_to_game.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/build-mac"
LJ="$ROOT/third_party/luajit"
ARCH=x86_64
MIN=10.13
CXX="${CXX:-clang++}"
CC="${CC:-clang}"

[[ "${1:-}" == "clean" ]] && { rm -rf "$OUT"; echo "removed $OUT"; exit 0; }

case "$(uname -s)" in Darwin) ;; *)
  echo "build.sh must run on macOS with Xcode Command Line Tools." >&2; exit 1;; esac
[[ -d "$LJ/src" ]] || { echo "missing $LJ/src; clone LuaJIT v2.1 into third_party/luajit first." >&2; exit 1; }
mkdir -p "$OUT/obj"

# --- LuaJIT: x86_64 static ---------------------------------------------------
# GC64 is LuaJIT's default on x86_64. The build host tool (buildvm) must also be
# x86_64 so it runs under Rosetta on Apple silicon, hence HOST_CC too.
LIBLUAJIT="$LJ/src/libluajit.a"
if [[ ! -f "$LIBLUAJIT" ]] || ! lipo -info "$LIBLUAJIT" 2>/dev/null | grep -q x86_64; then
  echo ">> building LuaJIT ($ARCH static)"
  make -C "$LJ" clean >/dev/null 2>&1 || true
  make -C "$LJ" -j"$(sysctl -n hw.ncpu)" BUILDMODE=static \
       CC="$CC -arch $ARCH" HOST_CC="$CC -arch $ARCH" \
       TARGET_FLAGS="-arch $ARCH" MACOSX_DEPLOYMENT_TARGET="$MIN" amalg
fi

# --- source set --------------------------------------------------------------
# Everything the shipping runtime uses, minus the files for other platforms and
# ABIs. The exclusions mirror the CMake source lists: no Windows/Linux platform
# layer, no i386 detour engine/bridge or arm32, no binkw32 proxy, no Windows
# launcher, and the i386-only harness adapters are replaced by engine_unsupported.cpp.
SRCS=()
while IFS= read -r f; do
  SRCS+=("$f")
done < <(cd "$ROOT" && find src -name '*.cpp' \
  ! -path 'src/platform/platform_win32.cpp' \
  ! -path 'src/platform/platform_linux.cpp' \
  ! -path 'src/proxy/*' \
  ! -path 'src/launcher/*' \
  ! -path 'src/hooks/trampoline.cpp' \
  ! -path 'src/hooks/lua_bridge.cpp' \
  ! -path 'src/hooks/lua_stub.cpp' \
  ! -path 'src/hooks/arm32/*' \
  ! -path 'src/harness/engine_k1.cpp' \
  ! -path 'src/harness/engine_k2.cpp' \
  | sort)
SRCS+=(
  third_party/imgui/imgui.cpp
  third_party/imgui/imgui_draw.cpp
  third_party/imgui/imgui_tables.cpp
  third_party/imgui/imgui_widgets.cpp
  third_party/imgui/backends/imgui_impl_opengl2.cpp
)

# Exceptions stay ON: hooks/thiscall.hpp's guard() wraps every hook body in a
# try/catch so a C++ throw on a game thread becomes a logged, contained return
# instead of unwinding into game frames that have no unwind info.
CXXFLAGS=(-std=c++20 -O2 -DNDEBUG -arch "$ARCH" -mmacosx-version-min="$MIN"
          -fvisibility=hidden -Wall -Wextra -Wno-unused-parameter
          -I"$ROOT/src" -I"$LJ/src" -I"$ROOT/third_party/imgui")

echo ">> compiling ${#SRCS[@]} sources ($ARCH)"
OBJS=()
for s in "${SRCS[@]}"; do
  o="$OUT/obj/$(echo "$s" | tr '/' '_').o"
  "$CXX" "${CXXFLAGS[@]}" -c "$ROOT/$s" -o "$o"
  OBJS+=("$o")
done

# --- link --------------------------------------------------------------------
# -bind_at_load: no lazy binding. The detour engine must never run dyld's lazy
# stub resolver while a code page is briefly writable, and lazy binding is the
# one thing that could. install_name @executable_path so a copy placed beside
# the game resolves; DYLD_INSERT_LIBRARIES overrides that with the real path.
DYLIB="$OUT/libkotorjit.dylib"
echo ">> linking libkotorjit.dylib"
"$CXX" -arch "$ARCH" -mmacosx-version-min="$MIN" -dynamiclib \
  -install_name "@executable_path/libkotorjit.dylib" \
  -Wl,-bind_at_load \
  -o "$DYLIB" "${OBJS[@]}" "$LIBLUAJIT" \
  -framework OpenGL -framework Cocoa -lobjc -lc++

# Ad-hoc signature: the games have no library validation, but a dylib mapped
# into a signed process still must itself be signed (even ad-hoc) on recent
# macOS, or dyld refuses it.
codesign -f -s - "$DYLIB"
echo ">> $DYLIB"
codesign -dv "$DYLIB" 2>&1 | sed -n '1,2p' || true
lipo -info "$DYLIB"

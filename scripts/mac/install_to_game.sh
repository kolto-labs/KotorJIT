#!/usr/bin/env bash
# Install KotorJIT into a macOS Steam KOTOR 1 or KOTOR 2 install, and take
# it back out. No game file is modified: the runtime is delivered through
# DYLD_INSERT_LIBRARIES, so uninstalling is deleting a folder.
#
#   install_to_game.sh install   <app-or-game-dir> [build-mac-dir]
#   install_to_game.sh uninstall <app-or-game-dir>
#   install_to_game.sh status    <app-or-game-dir>
#
# <app-or-game-dir> is the .app bundle or the folder that contains the
# executable (KOTOR_Exe for K1, KOTOR2sub for K2). For Steam this is usually:
#   ~/Library/Application Support/Steam/steamapps/common/swkotor/KOTOR.app
#   ~/Library/Application Support/Steam/steamapps/common/Knights of the Old Republic II/KOTOR2.app
#
# After installing, set the game's Steam launch options to:
#   DYLD_INSERT_LIBRARIES="<printed path>" %command%
# The installer prints the exact line. That is the whole install; the game is
# untouched and Steam integrity-verify stays green.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ACTION="${1:-}"; TARGET="${2:-}"; BUILD="${3:-$ROOT/build-mac}"
usage(){ sed -n '2,20p' "$0"; exit 2; }
[[ -n "$ACTION" && -n "$TARGET" ]] || usage

# Resolve the directory that actually holds the executable.
find_macos_dir() {
  local t="$1"
  for exe in KOTOR_Exe KOTOR2sub swkotor swkotor2; do
    [[ -f "$t/$exe" ]] && { echo "$t"; return; }
    [[ -f "$t/Contents/MacOS/$exe" ]] && { echo "$t/Contents/MacOS"; return; }
  done
  # search one level down for a .app
  local app; app=$(find "$t" -maxdepth 2 -name '*.app' -type d 2>/dev/null | head -1)
  [[ -n "$app" && -d "$app/Contents/MacOS" ]] && { echo "$app/Contents/MacOS"; return; }
  return 1
}
MACOS="$(find_macos_dir "$TARGET")" || { echo "no KOTOR executable under: $TARGET" >&2; exit 1; }
EXE=""
for e in KOTOR_Exe KOTOR2sub swkotor swkotor2; do [[ -f "$MACOS/$e" ]] && { EXE="$e"; break; }; done
[[ -n "$EXE" && -f "$MACOS/$EXE" ]] || { echo "no KOTOR executable inside $MACOS" >&2; exit 1; }
KPDIR="$MACOS/kotorjit"
DYLIB="$MACOS/libkotorjit.dylib"

case "$ACTION" in
install)
  [[ -f "$BUILD/libkotorjit.dylib" ]] || { echo "build first: scripts/mac/build.sh (missing $BUILD/libkotorjit.dylib)" >&2; exit 1; }
  # Identify the build by the code-section hash so the right address table is
  # shipped, exactly as the runtime identifies it at load.
  local_sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
  SHA="$(local_sha "$MACOS/$EXE")"
  BUILDID=""
  case "$EXE" in
    KOTOR_Exe|swkotor)   BUILDID=k1_mac_steam_x64;;
    KOTOR2sub|swkotor2)  BUILDID=k2_mac_steam_x64;;
  esac
  # Upgrading an install made under the old name (KotorPhasor): keep its
  # scripts by moving the data folder, and keep any Steam launch option that
  # still says libkphasor.dylib working by pointing that name at the new
  # runtime. Both runtimes are never present as separate files.
  if [[ -d "$MACOS/kotorphasor" && ! -e "$KPDIR" ]]; then
    mv "$MACOS/kotorphasor" "$KPDIR"
    echo "moved kotorphasor/ -> kotorjit/ (scripts kept)"
  fi
  [[ -f "$MACOS/kotorphasor.ini" && ! -e "$MACOS/kotorjit.ini" ]] && mv "$MACOS/kotorphasor.ini" "$MACOS/kotorjit.ini"
  mkdir -p "$KPDIR/scripts" "$KPDIR/addresses"
  cp "$BUILD/libkotorjit.dylib" "$DYLIB"
  if [[ -e "$MACOS/libkphasor.dylib" || -L "$MACOS/libkphasor.dylib" ]]; then
    ln -sf "libkotorjit.dylib" "$MACOS/libkphasor.dylib"
    echo "libkphasor.dylib now points at libkotorjit.dylib (old launch options keep working)"
  fi
  cp "$ROOT/data/addresses/$BUILDID.json" "$KPDIR/addresses/$BUILDID.json"
  # A starter ini and an example script, only if absent.
  [[ -f "$MACOS/kotorjit.ini" ]] || cat > "$MACOS/kotorjit.ini" <<INI
; KotorJIT settings. Scripts live in kotorjit/scripts/*.lua.
; harness_port is off (0) by default; it is a test surface, not for play.
harness_port = 0
INI
  if [[ ! -e "$KPDIR/scripts/hello.lua" ]]; then cat > "$KPDIR/scripts/hello.lua" <<'LUA'
priority = 10
function OnRunScript(script_name, object_id, has_object, relevant)
  kp.print("script fired: " .. tostring(script_name))
end
LUA
  fi
  echo "installed for build $BUILDID (exe $EXE, sha ${SHA:0:12})"
  echo
  echo "Set this game's Steam launch options to:"
  echo "    DYLD_INSERT_LIBRARIES=\"$DYLIB\" %command%"
  echo
  echo "Or launch from a terminal with:"
  echo "    DYLD_INSERT_LIBRARIES=\"$DYLIB\" \"$MACOS/$EXE\""
  ;;
uninstall)
  rm -f "$DYLIB" "$MACOS/libkphasor.dylib"
  echo "removed $DYLIB"
  echo "kotorjit/ (scripts, ini, logs) left in place: delete $KPDIR to remove it."
  echo "Clear the game's Steam launch options (remove the DYLD_INSERT_LIBRARIES line)."
  ;;
status)
  echo "executable: $MACOS/${EXE:-<none found>}"
  [[ -f "$DYLIB" ]] && echo "libkotorjit.dylib: present" || echo "libkotorjit.dylib: not installed"
  [[ -d "$KPDIR" ]] && echo "kotorjit/: present ($(ls "$KPDIR/scripts" 2>/dev/null | wc -l | tr -d ' ') script(s))"
  [[ -f "$MACOS/kotorjit.log" ]] && echo "log: $MACOS/kotorjit.log"
  ;;
*) usage;;
esac

#!/usr/bin/env bash
# Put KotorPhasor into a game directory, and take it back out again.
#
# Installing renames the game's binkw32.dll to binkw32_real.dll and drops our
# proxy in its place. Nothing else in the game folder is touched, and no game
# file is modified -- so uninstalling is a rename back.
#
#   install_to_game.sh install   <game-dir> [build-dir]
#   install_to_game.sh uninstall <game-dir>
#   install_to_game.sh status    <game-dir>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:-}"
GAME="${2:-}"
BUILD="${3:-$ROOT/build}"

usage() { sed -n '2,12p' "$0"; exit 2; }
[[ -n "$ACTION" && -n "$GAME" ]] || usage
[[ -d "$GAME" ]] || { echo "not a directory: $GAME" >&2; exit 1; }

PROXY="$GAME/binkw32.dll"
REAL="$GAME/binkw32_real.dll"
MARK="$GAME/kotorphasor/.installed"

is_ours() {
  # Our proxy is small and imports kphasor; the real one is ~370 KB of codec.
  [[ -f "$PROXY" ]] && [[ $(stat -c%s "$PROXY") -lt 200000 ]] &&
    grep -qa "kphasor.dll" "$PROXY" 2>/dev/null
}

case "$ACTION" in
install)
  if is_ours; then
    echo "already installed; run uninstall first if you want a clean swap" >&2
    exit 1
  fi
  [[ -f "$PROXY" ]] || { echo "no binkw32.dll in $GAME -- is this a game directory?" >&2; exit 1; }

  for f in kphasor.dll binkw32.dll; do
    [[ -f "$BUILD/$f" ]] || { echo "missing $BUILD/$f -- build first" >&2; exit 1; }
  done

  # Preserve the original before anything else. If this step fails we have not
  # touched the game.
  if [[ ! -f "$REAL" ]]; then
    cp -p "$PROXY" "$REAL"
    echo "saved original binkw32.dll -> binkw32_real.dll"
  fi

  install -D -m644 "$BUILD/kphasor.dll" "$GAME/kphasor.dll"
  install -m644 "$BUILD/binkw32.dll" "$PROXY"

  mkdir -p "$GAME/kotorphasor/scripts"
  # Address tables and the event contract travel with the runtime; the build id
  # is chosen at load time from the executable's hash.
  cp -r "$ROOT/data/addresses" "$GAME/kotorphasor/"
  date -Iseconds > "$MARK"

  echo "installed into $GAME"
  echo "  scripts go in $GAME/kotorphasor/scripts"
  ;;

uninstall)
  if [[ -f "$REAL" ]]; then
    mv -f "$REAL" "$PROXY"
    echo "restored original binkw32.dll"
  else
    echo "no binkw32_real.dll found; leaving binkw32.dll alone" >&2
  fi
  rm -f "$GAME/kphasor.dll" "$MARK"
  echo "uninstalled (scripts and logs left in place)"
  ;;

status)
  if is_ours; then
    echo "installed"
    [[ -f "$MARK" ]] && echo "  since: $(cat "$MARK")"
    [[ -f "$GAME/kotorphasor.log" ]] && echo "  log:   $GAME/kotorphasor.log"
  else
    echo "not installed"
  fi
  ;;

*) usage ;;
esac

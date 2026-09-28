#!/usr/bin/env bash
# Put a curated save at the top of KOTOR's load menu for demo discovery/recording.
#
# KOTOR lists saves by folder name under $GAME_DIR/Saves/. Prefix 000000 sorts
# before 000001 AUTOSAVE so live_session.sh always loads the intended slot.
#
# Labels (copy source under Saves/):
#   endar           — early-game slot; uses AUTOSAVE when present
#   dantooine_party — Game37 (Dantooine enclave, full party incl. Bastila)
#   any             — most recent AUTOSAVE
#
#   Or pass a folder name as the second argument: pick_save.sh custom "000038 - Game37"
#
# Usage:
#   ./scripts/harness/pick_save.sh dantooine_party
#   GAME_DIR=tmp/k1_harness ./scripts/harness/pick_save.sh endar
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$ROOT/tmp/k1_harness}"
SAVES="$GAME_DIR/Saves"
PICK="000000 - _pick"

label="${1:-}"
src_override="${2:-}"

[[ -n "$label" ]] || {
  echo "usage: pick_save.sh <endar|dantooine_party|any|custom> [source_folder]" >&2
  exit 2
}

[[ -d "$SAVES" ]] || { echo "pick_save: no Saves at $SAVES" >&2; exit 1; }

resolve_source() {
  local want="$1"
  case "$want" in
  endar)
    for d in "$SAVES"/000014\ -\ Game13 "$SAVES"/000001\ -\ AUTOSAVE; do
      [[ -f "$d/SAVEGAME.sav" ]] && { echo "$d"; return 0; }
    done
    for d in "$SAVES"/*/; do
      [[ -f "${d}SAVEGAME.sav" ]] && { echo "${d%/}"; return 0; }
    done
    ;;
  any)
    for d in "$SAVES"/000001\ -\ AUTOSAVE "$SAVES"/000014\ -\ Game13; do
      [[ -f "$d/SAVEGAME.sav" ]] && { echo "$d"; return 0; }
    done
    # Fall back to any complete save (warp still works for Endar demos).
    for d in "$SAVES"/*/; do
      [[ -f "${d}SAVEGAME.sav" ]] && { echo "${d%/}"; return 0; }
    done
    ;;
  dantooine_party)
    for d in "$SAVES"/000038\ -\ Game37 "$SAVES"/*Game37*; do
      [[ -f "$d/SAVEGAME.sav" ]] && { echo "$d"; return 0; }
    done
    ;;
  custom)
    [[ -n "${src_override:-}" ]] || { echo "pick_save: custom needs source folder" >&2; return 1; }
    local p="$SAVES/$src_override"
    [[ -d "$p" && -f "$p/SAVEGAME.sav" ]] || p="$src_override"
    [[ -d "$p" && -f "$p/SAVEGAME.sav" ]] || {
      echo "pick_save: not a complete save: $src_override" >&2
      return 1
    }
    echo "$p"
    return 0
    ;;
  *)
    echo "pick_save: unknown label: $want" >&2
    return 1
    ;;
  esac
  echo "pick_save: no save found for label: $want" >&2
  return 1
}

if [[ "$label" == "custom" ]]; then
  src=$(resolve_source custom)
else
  src=$(resolve_source "$label")
fi

rm -rf "$SAVES/$PICK"
cp -a "$src" "$SAVES/$PICK"

echo "pick_save: $label -> $SAVES/$PICK (from $(basename "$src"))"

#!/usr/bin/env bash
# Put KotorJIT into a game directory, and take it back out again.
#
# Deployment methods (--method):
#   auto     Windows .exe -> proxy; native Linux ELF32 -> linked (or preload if no PT_NOTE)
#   proxy    Windows/Wine/Proton: replace binkw32.dll with our proxy (saves binkw32_real.dll)
#   inject   Native Windows: copy kotorjit.dll + kotorjit-launch.exe (leaves binkw32.dll untouched)
#   linked   Native Linux ELF32: add DT_NEEDED $ORIGIN/libkotorjit.so via tools/elf_needed.py
#   preload  Native Linux ELF32: copy libkotorjit.so + write run-kotorjit.sh (LD_PRELOAD)
#
#   install_to_game.sh [--method auto|proxy|inject|linked|preload] install <game-dir> [build-dir]
#   install_to_game.sh uninstall <game-dir>
#   install_to_game.sh status    <game-dir>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -d "$SCRIPT_DIR/data/addresses" ]]; then
  ROOT="$SCRIPT_DIR"
else
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
METHOD="auto"
POS=()

usage() { sed -n '2,14p' "$0"; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --method)
      [[ $# -ge 2 ]] || usage
      METHOD="$2"
      shift 2
      ;;
    --method=*)
      METHOD="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      POS+=("$1")
      shift
      ;;
  esac
done

case "$METHOD" in
  auto|proxy|inject|linked|preload) ;;
  *) echo "unknown --method '$METHOD' (expected auto, proxy, inject, linked, preload)" >&2; exit 2 ;;
esac

ACTION="${POS[0]:-}"
GAME="${POS[1]:-}"
if [[ -n "${POS[2]:-}" ]]; then
  BUILD="${POS[2]}"
elif [[ -d "$ROOT/build" ]]; then
  BUILD="$ROOT/build"
elif [[ -f "$ROOT/kotorjit.dll" || -f "$ROOT/libkotorjit.so" ]]; then
  BUILD="$ROOT"
else
  BUILD="$ROOT/build"
fi

[[ -n "$ACTION" && -n "$GAME" ]] || usage
[[ -d "$GAME" ]] || { echo "not a directory: $GAME" >&2; exit 1; }

PROXY="$GAME/binkw32.dll"
REAL="$GAME/binkw32_real.dll"
MARK="$GAME/kotorjit/.installed"
METHOD_FILE="$GAME/kotorjit/install-method.txt"
LAUNCHER_DST="$GAME/kotorjit-launch.exe"
SO_DST="$GAME/libkotorjit.so"
PRELOAD_WRAPPER="$GAME/run-kotorjit.sh"

find_elf_tool() {
  for cand in "$ROOT/tools/elf_needed.py" "$ROOT/../tools/elf_needed.py" "$(dirname "$0")/tools/elf_needed.py"; do
    if [[ -f "$cand" ]]; then
      echo "$cand"
      return 0
    fi
  done
  return 1
}

find_addresses_dir() {
  for cand in "$ROOT/data/addresses" "$BUILD/data/addresses"; do
    if [[ -d "$cand" ]]; then
      echo "$cand"
      return 0
    fi
  done
  return 1
}

find_win_exe() {
  for name in swkotor.exe swkotor2.exe; do
    if [[ -f "$GAME/$name" ]]; then
      echo "$name"
      return 0
    fi
  done
  return 1
}

is_elf32_le() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local magic
  magic="$(od -An -tx1 -N6 "$f" 2>/dev/null | tr -d ' \n')"
  [[ "$magic" == "7f454c460101" ]]
}

find_linux_exe() {
  if [[ -f "$GAME/KOTOR2" ]] && is_elf32_le "$GAME/KOTOR2"; then
    echo "KOTOR2"
    return 0
  fi
  for cand in "$GAME"/KOTOR* "$GAME"/swkotor*; do
    [[ -f "$cand" && -x "$cand" ]] || continue
    [[ "${cand##*/}" == *.so* || "${cand##*/}" == *.sh ]] && continue
    if is_elf32_le "$cand"; then
      echo "${cand##*/}"
      return 0
    fi
  done
  for cand in "$GAME"/*; do
    [[ -f "$cand" && -x "$cand" ]] || continue
    case "${cand##*/}" in
      *.so|*.so.*|*.sh|*.exe|*.dll) continue ;;
    esac
    if is_elf32_le "$cand"; then
      echo "${cand##*/}"
      return 0
    fi
  done
  return 1
}

is_ours() {
  # Our proxy is small and names the runtime DLL; the real one is ~370 KB of
  # codec. Proxies built before the KotorPhasor -> KotorJIT rename name
  # kphasor.dll instead -- those are still ours, and must never be mistaken
  # for the original and saved as binkw32_real.dll.
  [[ -f "$PROXY" ]] && [[ $(stat -c%s "$PROXY") -lt 200000 ]] &&
    grep -qaE "kotorjit\.dll|kphasor\.dll" "$PROXY" 2>/dev/null
}

prepare_kotorjit_dir() {
  if [[ -d "$GAME/kotorphasor" && ! -e "$GAME/kotorjit" ]]; then
    mv "$GAME/kotorphasor" "$GAME/kotorjit"
    echo "moved kotorphasor/ -> kotorjit/ (scripts kept)"
  fi
  if [[ -f "$GAME/kotorphasor.ini" && ! -e "$GAME/kotorjit.ini" ]]; then
    mv "$GAME/kotorphasor.ini" "$GAME/kotorjit.ini"
    echo "moved kotorphasor.ini -> kotorjit.ini"
  fi
  mkdir -p "$GAME/kotorjit/scripts"
  local addr_dir
  if addr_dir="$(find_addresses_dir)"; then
    cp -r "$addr_dir" "$GAME/kotorjit/"
  fi
}

case "$ACTION" in
install)
  if is_ours || [[ -f "$METHOD_FILE" ]] || [[ -f "$MARK" ]] || [[ -f "$GAME/kotorphasor/.installed" ]] || [[ -f "$LAUNCHER_DST" ]] || [[ -f "$PRELOAD_WRAPPER" ]]; then
    echo "already installed; run uninstall first if you want a clean swap" >&2
    exit 1
  fi

  WIN_EXE=""
  LINUX_EXE=""
  WIN_EXE="$(find_win_exe || true)"
  LINUX_EXE="$(find_linux_exe || true)"

  if [[ "$METHOD" == "auto" ]]; then
    if [[ -n "$WIN_EXE" ]]; then
      # Proxy works on Windows, Wine, Proton, and packed Steam K1 alike; pass
      # --method inject on native Windows to use kotorjit-launch.exe instead.
      METHOD="proxy"
    elif [[ -n "$LINUX_EXE" ]]; then
      ELF_TOOL="$(find_elf_tool || true)"
      if [[ -n "$ELF_TOOL" ]] && readelf -lW "$GAME/$LINUX_EXE" 2>/dev/null | grep -q '^[[:space:]]*NOTE'; then
        METHOD="linked"
      else
        METHOD="preload"
      fi
    else
      echo "no swkotor.exe, swkotor2.exe, or ELF32 executable found in $GAME" >&2
      exit 1
    fi
  fi

  case "$METHOD" in
    proxy)
      [[ -f "$PROXY" ]] || { echo "no binkw32.dll in $GAME -- is this a Windows game directory?" >&2; exit 1; }
      for f in kotorjit.dll binkw32.dll; do
        [[ -f "$BUILD/$f" ]] || { echo "missing $BUILD/$f -- build first" >&2; exit 1; }
      done
      if [[ ! -f "$REAL" ]]; then
        cp -p "$PROXY" "$REAL"
        echo "saved original binkw32.dll -> binkw32_real.dll"
      fi
      install -D -m644 "$BUILD/kotorjit.dll" "$GAME/kotorjit.dll"
      install -m644 "$BUILD/binkw32.dll" "$PROXY"
      prepare_kotorjit_dir
      echo "proxy" > "$METHOD_FILE"
      date -Iseconds > "$MARK"
      echo "installed (method: proxy) into $GAME"
      echo "  scripts go in $GAME/kotorjit/scripts"
      ;;

    inject)
      [[ -n "$WIN_EXE" ]] || { echo "no swkotor.exe or swkotor2.exe in $GAME" >&2; exit 1; }
      for f in kotorjit.dll kotorjit-launch.exe; do
        [[ -f "$BUILD/$f" ]] || { echo "missing $BUILD/$f -- build first" >&2; exit 1; }
      done
      [[ ! -e "$GAME/kotorjit.dll" ]] || { echo "$GAME/kotorjit.dll already exists; refusing" >&2; exit 1; }
      install -D -m644 "$BUILD/kotorjit.dll" "$GAME/kotorjit.dll"
      install -m755 "$BUILD/kotorjit-launch.exe" "$LAUNCHER_DST"
      prepare_kotorjit_dir
      echo "inject" > "$METHOD_FILE"
      date -Iseconds > "$MARK"
      echo "installed (method: inject) into $GAME"
      echo "  launch with: $LAUNCHER_DST"
      echo "  scripts go in $GAME/kotorjit/scripts"
      ;;

    linked)
      [[ -n "$LINUX_EXE" ]] || { echo "no ELF32 Linux executable found in $GAME" >&2; exit 1; }
      [[ -f "$BUILD/libkotorjit.so" ]] || { echo "missing $BUILD/libkotorjit.so -- build first" >&2; exit 1; }
      ELF_TOOL="$(find_elf_tool)" || { echo "missing tools/elf_needed.py" >&2; exit 1; }
      prepare_kotorjit_dir
      mkdir -p "$GAME/kotorjit/backup"
      python3 "$ELF_TOOL" add "$GAME/$LINUX_EXE" '$ORIGIN/libkotorjit.so' \
        --backup "$GAME/kotorjit/backup/${LINUX_EXE}.orig"
      install -D -m755 "$BUILD/libkotorjit.so" "$SO_DST"
      echo "linked:${LINUX_EXE}" > "$METHOD_FILE"
      date -Iseconds > "$MARK"
      echo "installed (method: linked on $LINUX_EXE) into $GAME"
      echo "  scripts go in $GAME/kotorjit/scripts"
      ;;

    preload)
      [[ -n "$LINUX_EXE" ]] || { echo "no ELF32 Linux executable found in $GAME" >&2; exit 1; }
      [[ -f "$BUILD/libkotorjit.so" ]] || { echo "missing $BUILD/libkotorjit.so -- build first" >&2; exit 1; }
      install -D -m755 "$BUILD/libkotorjit.so" "$SO_DST"
      cat > "$PRELOAD_WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
LD_PRELOAD="\$DIR/libkotorjit.so\${LD_PRELOAD:+:\$LD_PRELOAD}" exec "\$DIR/${LINUX_EXE}" "\$@"
EOF
      chmod 755 "$PRELOAD_WRAPPER"
      prepare_kotorjit_dir
      echo "preload:${LINUX_EXE}" > "$METHOD_FILE"
      date -Iseconds > "$MARK"
      echo "installed (method: preload) into $GAME"
      echo "  launch with: $PRELOAD_WRAPPER"
      echo "  scripts go in $GAME/kotorjit/scripts"
      ;;
  esac
  ;;

uninstall)
  REC=""
  if [[ -f "$METHOD_FILE" ]]; then REC="$(cat "$METHOD_FILE")"; fi

  case "$REC" in
    linked:*)
      TARGET_EXE="${REC#linked:}"
      BACKUP_BIN="$GAME/kotorjit/backup/${TARGET_EXE}.orig"
      if [[ -f "$BACKUP_BIN" ]]; then
        cp -p "$BACKUP_BIN" "$GAME/$TARGET_EXE.tmp"
        chmod --reference="$BACKUP_BIN" "$GAME/$TARGET_EXE.tmp" 2>/dev/null || chmod 755 "$GAME/$TARGET_EXE.tmp"
        mv -f "$GAME/$TARGET_EXE.tmp" "$GAME/$TARGET_EXE"
        rm -f "$BACKUP_BIN"
        rmdir "$GAME/kotorjit/backup" 2>/dev/null || true
        echo "restored original $TARGET_EXE"
      else
        echo "no backup $BACKUP_BIN found; leaving $TARGET_EXE alone" >&2
      fi
      rm -f "$SO_DST"
      ;;
    preload:*)
      rm -f "$PRELOAD_WRAPPER" "$SO_DST"
      echo "removed run-kotorjit.sh and libkotorjit.so"
      ;;
    inject)
      rm -f "$GAME/kotorjit.dll" "$GAME/kphasor.dll" "$LAUNCHER_DST"
      echo "removed kotorjit.dll and kotorjit-launch.exe"
      ;;
    proxy|"")
      if [[ -f "$REAL" ]]; then
        mv -f "$REAL" "$PROXY"
        echo "restored original binkw32.dll"
      elif is_ours; then
        echo "no binkw32_real.dll found; leaving binkw32.dll alone" >&2
      fi
      rm -f "$GAME/kotorjit.dll" "$GAME/kphasor.dll" "$LAUNCHER_DST" "$PRELOAD_WRAPPER" "$SO_DST"
      ;;
  esac

  rm -f "$MARK" "$METHOD_FILE" "$GAME/kotorphasor/.installed"
  echo "uninstalled (scripts and logs left in place)"
  ;;

status)
  REC=""
  if [[ -f "$METHOD_FILE" ]]; then REC="$(cat "$METHOD_FILE")"; fi

  if [[ "$REC" == linked:* ]]; then
    TARGET_EXE="${REC#linked:}"
    echo "installed (method: linked, target: $TARGET_EXE)"
    if [[ -f "$MARK" ]]; then echo "  since: $(cat "$MARK")"; fi
    if [[ -f "$SO_DST" ]]; then echo "  so:    $SO_DST"; else echo "  so:    missing"; fi
    if [[ -f "$GAME/kotorjit.log" ]]; then echo "  log:   $GAME/kotorjit.log"; fi
  elif [[ "$REC" == preload:* ]]; then
    TARGET_EXE="${REC#preload:}"
    echo "installed (method: preload, target: $TARGET_EXE)"
    if [[ -f "$MARK" ]]; then echo "  since: $(cat "$MARK")"; fi
    if [[ -f "$PRELOAD_WRAPPER" ]]; then echo "  run:   $PRELOAD_WRAPPER"; fi
    if [[ -f "$GAME/kotorjit.log" ]]; then echo "  log:   $GAME/kotorjit.log"; fi
  elif [[ "$REC" == "inject" ]] || [[ -f "$LAUNCHER_DST" && -f "$GAME/kotorjit.dll" ]]; then
    echo "installed (method: inject)"
    if [[ -f "$MARK" ]]; then echo "  since: $(cat "$MARK")"; fi
    if [[ -f "$GAME/kotorjit.log" ]]; then echo "  log:   $GAME/kotorjit.log"; fi
  elif is_ours; then
    echo "installed (method: proxy)"
    if [[ -f "$MARK" ]]; then echo "  since: $(cat "$MARK")"; fi
    if [[ -f "$GAME/kotorjit.log" ]]; then echo "  log:   $GAME/kotorjit.log"; fi
  else
    echo "not installed"
  fi
  ;;

*) usage ;;
esac

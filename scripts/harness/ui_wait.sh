# Wait until KOTOR's LOADING splash (or menu chrome) is gone.
#
# Creature heartbeats and OnTick fire while the splash is still up -- the module
# is live underneath. The cheat console is a gameplay HUD surface and does not
# exist yet, so typing then lands on the loading bar. A fixed POST_LOAD_WAIT
# was too short on llvmpipe and too long when the splash cleared early.
#
# Discriminator, read off tmp/cave-reality screenshots at 1024x768: every menu,
# load-list, and LOADING frame has the same dark metal pixel at (40,46) =
# #292E36. Gameplay draws the minimap there instead. Unique-colour count jumps
# from ~29k (splash) to ~69k (3D + HUD) as a second signal.
#
# Sourced, not run. Callers must have WID set and a `log` function.

_ui_chrome_hex() {
  # ImageMagick 7 prefers `magick`; 6 still ships `convert`.
  local tool=convert
  command -v magick >/dev/null 2>&1 && tool=magick
  import -window "$WID" png:- 2>/dev/null |
    "$tool" - -format '%[hex:s.p{40,46}] %k' info: 2>/dev/null
}

# Return 0 once two consecutive samples look like gameplay.
wait_until_gameplay_visible() {
  local timeout="${1:-120}" i sample hex colors streak=0
  for i in $(seq 1 "$timeout"); do
    sample=$(_ui_chrome_hex) || sample=""
    hex=${sample%% *}
    colors=${sample##* }
    hex=${hex#\#}
    hex=${hex:0:6}
    hex=${hex^^}
    if [[ -n "$hex" && "$hex" != "292E36" ]] ||
       [[ "$colors" =~ ^[0-9]+$ && "$colors" -ge 45000 ]]; then
      streak=$((streak + 1))
      if (( streak >= 2 )); then
        log "  loading splash gone at t+${i}s (tl=#$hex colors=$colors)"
        return 0
      fi
    else
      streak=0
    fi
    if (( i % 15 == 0 )); then
      log "  waiting for LOADING splash to clear... t+${i}s (tl=#${hex:-?} colors=${colors:-?})"
    fi
    sleep 1
  done
  log "  LOADING splash still up after ${timeout}s; console keystrokes may miss"
  return 1
}

# Open the cheat console and prove DirectInput accepted a line.
# Writes $OUT/02_console.png. Returns 0 on `status: phase=` in the runtime log.
open_console_smoke() {
  local attempts="${1:-2}" n before
  before=$(wc -l < "$GAME_DIR/kotorphasor.log" 2>/dev/null || echo 0)
  for n in $(seq 1 "$attempts"); do
    xdotool windowactivate --sync "$WID" 2>/dev/null || true
    log "opening console ($CONSOLE_KEY) attempt $n"
    xdotool key --clearmodifiers "$CONSOLE_KEY"
    sleep 1
    import -window "$WID" "$OUT/02_console.png" 2>/dev/null
    xdotool type --clearmodifiers --delay 60 "lua status"
    sleep 0.5
    xdotool key --clearmodifiers Return
    sleep 3
    if tail -n +$((before + 1)) "$GAME_DIR/kotorphasor.log" 2>/dev/null |
         grep -q 'status: phase='; then
      log "  console smoke ok (status: phase=)"
      return 0
    fi
    log "  console did not accept lua status"
    # Toggle closed in case the first grave opened it and the type missed.
    xdotool key --clearmodifiers "$CONSOLE_KEY"
    sleep 0.5
  done
  return 1
}

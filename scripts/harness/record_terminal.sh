#!/usr/bin/env bash
# Record a terminal session to mp4/gif, with the commands typed rather than dumped.
#
#   record_terminal.sh <out-basename> <scene-file> [width] [height]
#
# A scene file is a shell script run inside the recorded terminal. Two helpers
# are defined for it:
#
#   say  "text"     a comment line, in dim green, no command run
#   run  "cmd"      types the command at human speed, then runs it
#   beat [seconds]  a pause, so a reader can catch up
#
# The typing is the point. A wall of output that appears instantly reads as a
# screenshot and gives a viewer nothing to follow; watching the command appear
# and then answer is what makes a short clip legible. Nothing here knows what is
# being demonstrated, so it records any command-line tool.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/harness/record.sh"

OUT_BASE="${1:?usage: record_terminal.sh <out-basename> <scene-file> [w] [h]}"
SCENE="${2:?scene file required}"
W="${3:-1280}"
H="${4:-720}"
DISPLAY_NUM="${TERM_DISPLAY_NUM:-91}"
FONT_SIZE="${FONT_SIZE:-13}"

[[ -f "$SCENE" ]] || { echo "no scene file: $SCENE" >&2; exit 1; }
mkdir -p "$(dirname "$OUT_BASE")"

command -v xterm >/dev/null || { echo "xterm not installed" >&2; exit 1; }

cleanup() {
  rec_stop
  [[ -n "${XTERM_PID:-}" ]] && kill "$XTERM_PID" 2>/dev/null
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" 2>/dev/null
  rm -f "$DRIVER"
  return 0
}
trap cleanup EXIT

# The driver wraps the scene with the helpers and a prompt that looks like a
# prompt. It is generated rather than kept as a file because it has to carry the
# scene's own path and the repo root into a shell that xterm starts fresh.
DRIVER="$(mktemp /tmp/kp_scene_XXXXXX.sh)"
cat > "$DRIVER" <<DRIVER_EOF
#!/usr/bin/env bash
cd "$ROOT" || exit 1
export TERM=xterm-256color
G=\$'\e[38;5;114m'; D=\$'\e[38;5;244m'; C=\$'\e[38;5;81m'; R=\$'\e[0m'
PS="\${G}kotorphasor\${R} \${C}\\\$\${R} "

type_out() {   # one character at a time, with a slight stumble so it reads human
  local s="\$1" i c
  for (( i=0; i<\${#s}; i++ )); do
    c="\${s:i:1}"
    printf '%s' "\$c"
    sleep 0.0\$(( RANDOM % 4 + 2 ))
  done
  printf '\n'
}

say()  { printf '%s\n' "\${D}# \$*\${R}"; sleep 0.7; }
beat() { sleep "\${1:-1.2}"; }
run()  {
  printf '%s' "\$PS"
  type_out "\$*"
  sleep 0.25
  eval "\$*"
  printf '\n'
  sleep 1.0
}

clear
sleep 1.2
source "$SCENE"
sleep 3
DRIVER_EOF
chmod +x "$DRIVER"

Xvfb ":$DISPLAY_NUM" -screen 0 "${W}x${H}x24" -nolisten tcp \
  >"$OUT_BASE.xvfb.log" 2>&1 &
XVFB_PID=$!
export DISPLAY=":$DISPLAY_NUM"
for _ in $(seq 1 40); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.25; done
xdpyinfo >/dev/null 2>&1 || { echo "Xvfb failed" >&2; exit 1; }

# Colours chosen to survive gif quantisation: a near-black background and a small
# number of saturated foregrounds stay legible at 256 colours, where a
# low-contrast theme turns to mud.
xterm -display ":$DISPLAY_NUM" \
      -fa "${FONT_NAME:-Noto Sans Mono}" -fs "$FONT_SIZE" \
      -bg '#0b0e14' -fg '#c8d3e0' -cr '#7ee787' \
      -geometry 200x60+0+0 -b 14 -bc -sb -si -sk \
      -title "kotorphasor" \
      -e "$DRIVER" &
XTERM_PID=$!

sleep 2
rec_start "$DISPLAY_NUM" "$OUT_BASE"

# Wait for the scene to finish on its own; the timeout is a backstop for a demo
# command that hangs, not the expected path.
LIMIT="${SCENE_TIMEOUT:-600}"
for _ in $(seq 1 "$LIMIT"); do
  kill -0 "$XTERM_PID" 2>/dev/null || break
  sleep 1
done

rec_stop
echo "terminal demo: $OUT_BASE.mp4"

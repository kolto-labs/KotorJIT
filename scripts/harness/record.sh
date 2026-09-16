#!/usr/bin/env bash
# Record an X display to mp4, and cut short gifs out of it afterwards.
#
# Sourced, not run: a harness that already owns an Xvfb calls rec_start after the
# display is up and rec_stop from its exit trap. Nothing here knows what is being
# recorded, so it works for any X client.
#
#   source record.sh
#   rec_start 78 "$OUT/session"      # -> session.mp4
#   rec_mark  "loading finished"     # timestamps a moment, for cutting later
#   rec_stop
#   rec_gif "$OUT/session.mp4" "$OUT/clip.gif" 00:01:20 8
#
# Why mp4 first and gifs second: a gif of a whole session is unusable (hundreds
# of MB, and nobody watches ninety seconds of a loading screen). Recording once
# and cutting many times also means a clip can be re-cut without re-running the
# game, which matters when a run takes ten minutes.

# Frames per second. Low on purpose -- this is a software-rendered game on a
# virtual display, and the capture competes with the thing being captured for
# CPU. 15 is smooth enough to read and cheap enough not to distort the timings
# the harness is also measuring.
KP_REC_FPS="${KP_REC_FPS:-10}"
KP_REC_CRF="${KP_REC_CRF:-23}"

_harness_root_for_rec() {
  if [[ -n "${ROOT:-}" ]]; then echo "$ROOT"
  elif [[ -n "${BASH_SOURCE[0]:-}" ]]; then cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
  else echo "/tmp"; fi
}
_rec_scratch() {
  local dir="${HARNESS_SCRATCH:-$(_harness_root_for_rec)/tmp/scratch}"
  mkdir -p "$dir"
  echo "$dir"
}

_kp_rec_pid=""
_kp_rec_base=""
_kp_rec_t0=""
_kp_rec_marks=""

rec_available() { command -v ffmpeg >/dev/null 2>&1; }

# rec_start <display-number> <output-basename>
rec_start() {
  local disp="$1" base="$2"
  if ! rec_available; then
    echo "record: ffmpeg not found, continuing without video" >&2
    return 0
  fi
  mkdir -p "$(dirname "$base")"

  # Ask the server how big it is rather than assuming. x11grab fails outright on
  # a size mismatch, and hardcoding the harness's resolution here would couple
  # this to a caller that is free to change it.
  local geom
  geom=$(DISPLAY=":$disp" xdpyinfo 2>/dev/null |
         sed -n 's/^ *dimensions: *\([0-9]*x[0-9]*\).*/\1/p' | head -1)
  [[ -z "$geom" ]] && { echo "record: no display :$disp" >&2; return 1; }

  _kp_rec_base="$base"
  _kp_rec_marks="$base.marks"
  : > "$_kp_rec_marks"
  _kp_rec_t0=$(date +%s)

  # -nostdin matters: without it ffmpeg competes with the calling script for the
  # terminal's stdin and silently eats keystrokes meant for something else.
  # yuv420p + faststart are what make the file play in a browser rather than only
  # in mpv, which is the whole point if these end up on a page somewhere.
  ffmpeg -nostdin -loglevel error -y \
    -f x11grab -draw_mouse 0 -framerate "$KP_REC_FPS" -video_size "$geom" -i ":$disp" \
    -c:v libx264 -preset "${KP_REC_PRESET:-ultrafast}" -crf "$KP_REC_CRF" -pix_fmt yuv420p \
    -movflags +faststart \
    "$base.mp4" >"$base.ffmpeg.log" 2>&1 &
  _kp_rec_pid=$!
  sleep 1
  if ! kill -0 "$_kp_rec_pid" 2>/dev/null; then
    echo "record: ffmpeg died immediately; see $base.ffmpeg.log" >&2
    _kp_rec_pid=""
    return 1
  fi
  echo "record: capturing :$disp ($geom @ ${KP_REC_FPS}fps) -> $base.mp4"
}

# rec_mark <label> -- note that something happened, at a time relative to the
# start of the recording, so a clip can be cut around it later without anyone
# scrubbing through the video by hand.
rec_mark() {
  [[ -z "$_kp_rec_marks" ]] && return 0
  local t=$(( $(date +%s) - _kp_rec_t0 ))
  printf '%02d:%02d:%02d\t%s\n' $((t/3600)) $((t%3600/60)) $((t%60)) "$*" \
    >> "$_kp_rec_marks"
}

rec_stop() {
  [[ -z "$_kp_rec_pid" ]] && return 0
  # SIGINT, not SIGKILL. ffmpeg writes the moov atom on a clean shutdown; killed
  # outright it leaves a file no player will open, which is a miserable way to
  # discover a ten-minute run produced nothing.
  kill -INT "$_kp_rec_pid" 2>/dev/null
  for _ in $(seq 1 600); do   # up to 2 min: a loaded host flushes slowly
    kill -0 "$_kp_rec_pid" 2>/dev/null || break
    sleep 0.2
  done
  kill -0 "$_kp_rec_pid" 2>/dev/null && kill -9 "$_kp_rec_pid" 2>/dev/null
  wait "$_kp_rec_pid" 2>/dev/null
  _kp_rec_pid=""
  if [[ -s "$_kp_rec_base.mp4" ]]; then
    local secs
    secs=$(ffprobe -v error -show_entries format=duration -of csv=p=0 \
           "$_kp_rec_base.mp4" 2>/dev/null | cut -d. -f1)
    echo "record: wrote $_kp_rec_base.mp4 (${secs:-?}s, $(du -h "$_kp_rec_base.mp4" | cut -f1))"
  else
    echo "record: no video was produced; see $_kp_rec_base.ffmpeg.log" >&2
  fi
}

# rec_gif <src.mp4> <out.gif> <start> <seconds> [width]
#
# Two passes. A gif is limited to 256 colours, and letting ffmpeg pick them per
# frame produces the dithered mush that makes people assume gifs look bad; a
# palette computed over the whole clip first does not.
rec_gif() {
  local src="$1" out="$2" start="$3" dur="$4" width="${5:-720}"
  rec_available || return 0
  [[ -s "$src" ]] || { echo "record: $src missing, no gif" >&2; return 1; }
  local pal; pal=$(_rec_scratch)/kp_palette_$$.png
  local fps="${KP_GIF_FPS:-12}"
  local filters="fps=$fps,scale=$width:-1:flags=lanczos"

  ffmpeg -nostdin -loglevel error -y -ss "$start" -t "$dur" -i "$src" \
    -vf "$filters,palettegen=stats_mode=diff" "$pal" 2>/dev/null
  ffmpeg -nostdin -loglevel error -y -ss "$start" -t "$dur" -i "$src" -i "$pal" \
    -lavfi "$filters [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
    "$out" 2>/dev/null
  rm -f "$pal"
  [[ -s "$out" ]] && echo "record: $out ($(du -h "$out" | cut -f1))"
}

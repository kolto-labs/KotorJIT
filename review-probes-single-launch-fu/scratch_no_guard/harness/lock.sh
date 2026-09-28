# Stale-aware session locking for the headless game harnesses.
#
# The previous pattern was "if a game or Xvfb is already running on this
# display, refuse unless FORCE=1" -- which is safe but not automatic: an agent
# whose host process was killed (a session moved to another machine, a Task
# was cancelled) leaves its Xvfb and wine dead, and every re-run after that
# needs a human to notice and pass FORCE=1. That happened three times in one
# afternoon. This replaces it with the standard CI-runner pattern: a lock file
# holding the owning PID plus that PID's own start time. A live PID with a
# matching start time is a real, running session -- refuse. A missing PID, or
# a live PID whose start time does NOT match (the PID was recycled by an
# unrelated process since) is a stale lock -- reclaim it automatically, no
# human required. Sourced, not run.
#
#   lock_acquire "$OUT/session.lock" 78 swkotor.exe   # exits 6 if genuinely held
#   trap lock_release EXIT                            # release on the way out
LOCK_PATH=""

_pid_start() {  # $1 = pid -> that process's start time in jiffies, or empty
  awk '{print $22}' "/proc/$1/stat" 2>/dev/null
}

# lock_acquire <lock-file> <display-num> <process-name-substring>
#
# The display number and process name are recorded so a human (or the next
# call) can tell what a lock was FOR without cross-referencing this script --
# a lock file that only holds a PID is a mystery six months later.
lock_acquire() {
  local path="$1" display="$2" what="$3"
  LOCK_PATH="$path"
  mkdir -p "$(dirname "$path")"

  if [[ -f "$path" ]]; then
    local held_pid held_start held_display held_what now_start
    { read -r held_pid; read -r held_start; read -r held_display; read -r held_what; } < "$path"
    now_start=$(_pid_start "$held_pid")
    if [[ -n "$now_start" && "$now_start" == "$held_start" ]]; then
      echo "lock: display $held_display is held by pid $held_pid ($held_what), still alive" >&2
      if [[ "${FORCE:-0}" == "1" ]]; then
        echo "lock: FORCE=1, taking it anyway" >&2
        pkill -x "$held_what" 2>/dev/null
        pkill -f "Xvfb :$held_display " 2>/dev/null
        sleep 2
      else
        return 6
      fi
    else
      echo "lock: stale (pid $held_pid is gone or was recycled) -- reclaiming automatically" >&2
    fi
  fi

  echo "$$" > "$path"
  _pid_start "$$" >> "$path"
  echo "$display" >> "$path"
  echo "$what" >> "$path"
}

lock_release() {
  [[ -n "$LOCK_PATH" && -f "$LOCK_PATH" ]] || return 0
  local held_pid; held_pid=$(head -1 "$LOCK_PATH" 2>/dev/null)
  # Only remove a lock this process actually owns -- a lock_release in a trap
  # must never delete a lock some OTHER still-running session just acquired.
  [[ "$held_pid" == "$$" ]] && rm -f "$LOCK_PATH"
}

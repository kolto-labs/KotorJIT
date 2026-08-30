# Shared scratch paths for harness scripts. Sourced, not run.
#
# kp_luatest capture and Xvfb both need writable temp space. Redirecting scratch
# into $ROOT/tmp avoids mktemp's /tmp default, which some sandboxes truncate,
# and keeps palette/scene files next to the run logs they belong with.

_harness_root() {
  if [[ -n "${ROOT:-}" ]]; then
    echo "$ROOT"
  else
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
  fi
}

harness_scratch() {
  local root
  root=$(_harness_root)
  local dir="${HARNESS_SCRATCH:-$root/tmp/scratch}"
  mkdir -p "$dir"
  echo "$dir"
}

# harness_mktemp [suffix]
harness_mktemp() {
  local suffix="${1:-}"
  mktemp "$(harness_scratch)/kp.XXXXXX${suffix:+.$suffix}"
}

# preflight_tmp_write [--quiet]
#
# Xvfb writes /tmp/.tX<n>-lock before the display exists. When the user's tmpfs
# quota is full this fails with "Could not write pid to lock file" and every
# live test looks like an Xvfb bug instead of a quota problem.
preflight_tmp_write() {
  local probe="/tmp/.kp_harness_write_probe.$$"
  if echo ok > "$probe" 2>/dev/null; then
    rm -f "$probe"
    return 0
  fi
  [[ "${1:-}" == "--quiet" ]] || {
    echo "preflight: cannot write to /tmp (disk quota exceeded or permission denied)." >&2
    echo "  Xvfb needs /tmp for display lock files; live-game tests cannot start until this is fixed." >&2
    echo "  Check:  quota -s ; df -h /tmp ; du -sh /tmp/* | sort -hr | head" >&2
    echo "  Stale parallel game copies from earlier agent runs often live in /dev/shm/kp_a{1,2} (~7G)." >&2
  }
  return 1
}

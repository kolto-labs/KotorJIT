#!/usr/bin/env bash
# Run a harness scenario while recording the exact Xvfb display it owns.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
name="${1:?usage: record_proof.sh <scenario> [scenario args ...]}"; shift
stamp="$(date +%Y%m%d-%H%M%S)"
case "$name" in
  k2*) run_root="$ROOT/tmp/k2_harness/runs" ;;
  *)   run_root="$ROOT/tmp/k1_harness/runs" ;;
esac
out="$run_root/recorded-${name}-${stamp}"
mkdir -p "$out"
# Force line-buffered driver output so display discovery does not wait for the
# scenario to finish before seeing the harness-owned Xvfb announcement.
PYTHONUNBUFFERED=1 "$ROOT/scripts/harness/kpharness.sh" run "$name" "$@" >"$out/driver.log" 2>&1 & hp=$!
disp=""
for _ in $(seq 1 180); do
  if [[ -s "$out/driver.log" ]]; then
    disp=$(sed -n 's/.*Xvfb up on :\([0-9][0-9]*\).*/\1/p' "$out/driver.log" | head -1)
    [[ -n "$disp" ]] && break
  fi
  kill -0 "$hp" 2>/dev/null || break
  sleep 1
done
if [[ -z "$disp" ]]; then
  wait "$hp" || true
  echo "record_proof: harness never exposed an owned Xvfb display; see $out/driver.log" >&2
  exit 2
fi
ffmpeg -nostdin -loglevel error -y -f x11grab -framerate 15 \
  -video_size 1024x768 -i ":$disp" -c:v libx264 -preset veryfast \
  -pix_fmt yuv420p -movflags +faststart "$out/live-proof.mp4" \
  >"$out/ffmpeg.log" 2>&1 & fp=$!
set +e; wait "$hp"; rc=$?; set -e
kill -INT "$fp" 2>/dev/null || true; wait "$fp" 2>/dev/null || true
report=$(sed -n 's/.*report: \(.*\/report\.json\).*/\1/p' "$out/driver.log" | tail -1)
if [[ -n "$report" && -f "$report" ]]; then
  cp -- "$report" "$out/report.json"
fi
echo "record_proof: output=$out display=:$disp exit=$rc"
if [[ "$rc" -ne 0 || ! -s "$out/live-proof.mp4" || ! -s "$out/report.json" ]]; then
  echo "record_proof: no confirmed proof (scenario exit=$rc)" >&2
  exit "${rc:-1}"
fi

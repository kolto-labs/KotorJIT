# Task 7 Gamescope capture-cadence fix report

Date: 2026-09-27

## Scope

This slice changes only the Gamescope recorder's source drawable and its
capture/cadence evidence. It does not launch Wine, K1, Gamescope, X11 capture,
or real FFmpeg, and it does not add PipeWire, GStreamer, CFR interpolation, an
FPS filter, a second encoder, or timestamp rewriting.

The reviewed post-accept export implementation in `recording.py`,
`creative_export.py`, and the existing host tests was preserved.

## Implemented behavior

- The immutable `OwnedWindow`, PID/start identity, lease, private display,
  one-visible-window discovery, dimensions, and 250 ms continuous verifier stay
  as authorization evidence.
- The Linux recorder additionally proves the authorized window is at `0,0` and
  exactly covers both the lease dimensions and the private display root.
- Gamescope capture now reads normalized screen zero (`:N.0`) with
  `-draw_mouse 0`; the command has no `-window_id`.
- The encoder remains libx264, ultrafast, CRF 28, yuv420p, two threads, the
  requested acquisition FPS, and an MP4 master.
- Startup consumes machine-readable FFmpeg progress, requires a complete block
  with `frame >= 1` within five monotonic seconds, and validates the run-local
  regular non-symlink output.
- `ffmpeg.log` is scanned incrementally with overlap for both forbidden SHM
  fallback strings through orderly stop. Successful evidence is accurately
  named `no_fallback_observed`.
- Startup failures retain typed evidence and clean up only the owned FFmpeg
  process with SIGINT, a two-second wait, then kill and another two-second wait.
- Portable named markers, marker byte offsets, shared-process monotonic times,
  polling uncertainty, configurable cadence endpoints, FFmpeg terminal
  counters, ffprobe PTS evidence, interval metrics, and fail-closed cadence
  thresholds are serialized.
- Schema-2 recomputation rejects the old child-window command, duplicate source
  flags, mismatched display/lease/window identity, inexact coverage, caller
  display reuse, SHM fallback, incomplete diagnostics, and cadence status that
  contradicts the primitive metrics.
- Route status remains independent. Capture or cadence failure prevents overall
  acceptance and representative-success rendering while retaining partial media.

## Failure classes

The slice emits the stable capture failure strings requested by the brief:

- `capture_start_timeout`
- `capture_shm_fallback`
- `capture_progress_malformed`
- `capture_process_exited`
- `capture_output_invalid`
- `capture_log_read_failed`
- `capture_lease_lost`
- `capture_binding_changed`
- `capture_finalize_timeout`
- `capture_cadence_failed`
- `capture_markers_incomplete`

Marker/cadence failures are also retained in the portable cadence failure list
so capture authorization and cadence acceptance remain distinct.

## Host-only verification

The final verification commands are:

```sh
python3 tools/kpharness_gamescope_backend_test.py
python3 tools/kpharness_creative_test.py
python3 tools/kpharness_gamescope_boot_repair_test.py
python3 -m py_compile \
  scripts/harness/kpharness/recording.py \
  scripts/harness/kpharness/display_backends.py \
  scripts/harness/kpharness/creative_wine.py \
  scripts/harness/kpharness/creative.py \
  tools/kpharness_creative_test.py \
  tools/kpharness_gamescope_backend_test.py
```

All recorder launches in these tests use fake processes and mocked host queries.
No live acceptance content or animated diagnostic was run.

## Next gate

Stop after static review. The next action requires separate parent authorization:
run one serialized bounded animated-pattern diagnostic on the same owned private
Gamescope display. Do not launch K1 first. If it reports
`capture_shm_fallback`, retain the result and open a separate PipeWire adapter
slice rather than loosening cadence or timestamp gates.

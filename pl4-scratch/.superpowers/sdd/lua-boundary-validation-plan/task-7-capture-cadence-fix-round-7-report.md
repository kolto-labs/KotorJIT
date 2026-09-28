# Task 7 capture cadence fix: round 7

Date: 2026-09-27

## Scope

This host-only round closes R6-1 and R6-2 from both round-6 reviews and closes
the durable-cleanup residual. No Wine, game, Gamescope, X11 server, FFmpeg, or
FFprobe process was launched. Process behavior was exercised with mocks and
native executable descriptors were inspected without executing them.

## Verified executable descriptor

- Acceptance opens the configured resolved FFprobe path with `O_NOFOLLOW`,
  requires a regular executable native ELF file, and hashes/fstats that retained
  descriptor against the producer-recorded tool identity.
- The fresh probe command uses `/proc/self/fd/<tool_fd>` and inherits that tool
  descriptor alongside the zero-link media descriptor. The configured pathname
  is never reopened for child execution.
- Acceptance rehashes and re-fstats the same tool descriptor after probing and
  rechecks the configured public path. Rename/install/restore changes ctime and
  fails; regardless, the probe callback observes only the original retained
  executable bytes.
- Script and unsupported executable formats fail closed rather than falling
  back to pathname execution.

## Independent route commitment

- `creative_accept` now requires `--route-sha256`, supplied independently by
  the reviewer/operator in the same manner as the reviewed media digest.
- The expected digest must equal the launch-selected `route_source` digest and
  is signed into `visual_review`, including the acceptance digest.
- `verify_acceptance`, `accepted_receipt`, and export all require the expected
  digest as an explicit caller input. The export CLI also requires
  `--route-sha256`, and the derivative sidecar records it.
- A coherent replacement of `executed-route.toml`, its stat identity/digest,
  report, duplicated steps, and execution identity remains internally ready but
  cannot be accepted using the independently retained launch digest.

## Route speed semantics

- Report `game_speed_requested` and `game_speed_effective` must equal the parsed
  executed route's `scenario.settings.game_speed` within the established exact
  tolerance. Internal requested/effective agreement at another speed fails.
- Optional retained speed must still equal effective speed; restored speed
  remains the prior valid speed reported by attached-run semantics.

## Durable unreaped-child evidence

- `ProbeCleanupError` retains the exact process, command, PID, and Linux process
  start identity after both bounded two-second waits fail.
- Before the acceptance CLI can exit, acceptance atomically writes
  `ffprobe-cleanup-failure.json` with failed status, failure type, exact PID/start,
  command, verified tool identity, wait bounds, and the identity-checked recovery
  requirement.
- The execution remains unaccepted and no cleanup-passed claim is emitted.

## Regression coverage

- Replace-for-invocation/restore proves the callback receives original ELF bytes
  through the tool FD and acceptance detects identity change.
- Both inherited descriptors are present during probing and are closed after the
  operation, covering descriptor lifetime and reuse boundaries.
- A direct mocked `probe_frame_pts` call proves argv element zero is the inherited
  `/proc/self/fd/<tool_fd>` path and both descriptors are in `pass_fds`.
- Coherent all-local route substitution passes internal readiness but fails the
  independent expected-route check.
- Consistent report speed `8.0/8.0` fails against a parsed 16x route.
- Wrong expected route SHA fails acceptance verification and export admission.
- An unreaped mocked child produces the durable typed cleanup receipt with exact
  PID/start identity and `[2, 2]` bounded waits.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 87/87 passed.
- Total focused tests: 158/158 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both
  focused test modules.
- `git diff --check` passed.

Expected creative and boot-repair diagnostic lines are mocked failure-path output,
not live-process failures.

## Files changed in round 7

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative_accept.py`
- `scripts/harness/kpharness/creative_export.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.

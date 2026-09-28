# Task 7 capture cadence fix: round 6

Date: 2026-09-27

## Scope

This host-only round closes R5-1 through R5-3 from both round-5 reviews. No
Wine, game, Gamescope, X11 server, FFmpeg, or FFprobe process was launched.
All process behavior was exercised with mocks or pure filesystem operations.

## Descriptor-only acceptance probe

- Acceptance copies the retained `O_NOFOLLOW` public-master descriptor into an
  exclusive private file, verifies the copy with exactly one link, reopens it
  read-only, unlinks it, and requires the retained descriptor to have zero
  links before probing.
- FFprobe receives only `/proc/self/fd/<n>` and `pass_fds=(n,)`. There is no
  stable-copy pathname left to rename, replace, or restore.
- Stable and public identities now include device, inode, size, mtime, ctime,
  and link count in addition to SHA-256. The exact zero-link stable descriptor
  is fstat'ed and rehashed after the callback. A private write-and-restore can
  restore bytes and mtime but cannot restore ctime, so it fails acceptance.
- The canonical producer records the configured FFprobe command, its resolved
  regular-file path, and executable SHA-256. Readiness verifies that executable
  identity, the PTS artifact must contain the same identity, and acceptance
  invokes the verified resolved path rather than artifact-controlled text.

## Route-source and report binding

- The producer records the copied route's device, inode, size, mtime, ctime,
  link count, path, and SHA-256 and includes an execution identity binding the
  route scenario, K1 target, build/profile string, route digest, and runtime
  artifact hashes.
- Readiness opens `executed-route.toml` and `report.json` with `O_NOFOLLOW`,
  bounds and hashes both, verifies the route's recorded one-link identity, and
  parses the exact route bytes.
- Report target/scenario/build, step count, consecutive indices, and step
  descriptions must match the parsed K1 route and receipt build. The runtime
  artifact names must equal the K1 runtime set, and their current SHA-256 values
  must match both receipt artifacts and the route execution identity.
- Report execution metadata accepts only requested/effective and optional
  restored-or-retained game-speed fields. Values must be finite, non-boolean,
  in `(0,16]`, and obey requested/effective/retained consistency.
- The producer independently marks the route failed when the returned report
  scenario, target, build, step count, indices, or descriptions disagree with
  the selected route.

## Bounded probe cleanup and byte ceiling

- FFprobe cleanup performs two bounded two-second kill/reap attempts. It never
  calls an unbounded `wait()`, including the missing-stdout path.
- A child that survives both attempts raises `ProbeCleanupError`, which retains
  the exact process object for later owner-controlled cleanup. Acceptance fails.
- Each nonblocking read is limited to the remaining byte budget. Oversized
  output is rejected after retaining exactly 16 MiB plus one byte, even when
  the producer has a full 64 KiB chunk ready.

## Regression coverage

- The acceptance callback receives an inherited zero-link descriptor path.
- Private descriptor bytes changed and restored during the callback are rejected
  through ctime/descriptor identity even when their digest is restored.
- An artifact-selected probe executable fails readiness.
- Coherently rehashed wrong K2/scenario/build reports, fully substituted matching
  report/receipt steps, arbitrary execution keys, boolean/nonfinite speeds, and
  contradictory speeds fail readiness.
- A sparse full-chunk oversized stream proves exact 16 MiB-plus-one retention,
  kill, and reap behavior.
- An unkillable missing-stdout child records waits `[2, 2]`, raises the typed
  cleanup error, and exposes the exact child object through that error.

## Validation

Final serial run:

- `python3 tools/kpharness_creative_test.py`: 30/30 passed.
- `python3 tools/kpharness_gamescope_boot_repair_test.py`: 41/41 passed.
- `python3 tools/kpharness_gamescope_backend_test.py`: 81/81 passed.
- Total focused tests: 152/152 passed.
- `python3 -m py_compile` passed for the six owned harness modules and both
  focused test modules.
- `git diff --check` passed.

The creative and boot-repair diagnostic lines are expected mocked failure-path
output. They are not live-process failures.

## Files changed in round 6

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `tools/kpharness_creative_test.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

No files were staged, reset, or committed.

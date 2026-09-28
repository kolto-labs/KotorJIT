# Task 7 capture cadence fix: round 4 implementation report

Date: 2026-09-27

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

This round closes all Critical, Important, and authoritative-field Minor findings from the appended round-3 reviews. Work remained host-only and mock-driven. No real FFmpeg, FFprobe, Gamescope, X11/Xvfb server, Wine process, or game process was launched. No files were staged or committed.

## Canonical media-to-PTS evidence

- The producer writes exactly one canonical `ffprobe-cadence.json` after the final master is published.
- The artifact is bounded to 250,000 frames and 16 MiB. It records schema version, exact master path and SHA-256, probe executable/method, frame count, and one finite strictly increasing ordered PTS list.
- Cadence execution evidence records the artifact's exact path, SHA-256, master SHA-256, and frame count.
- Readiness opens the artifact with `O_NOFOLLOW`, requires a regular bounded file, verifies its SHA-256, hashes the actual regular non-symlink master, compares both master identities, and validates the canonical list.
- Visual acceptance freshly reruns the bounded probe against the digest-verified master and requires exact ordered equality with the canonical artifact before signing. The accepted review record binds the artifact SHA-256.
- Acceptance verification and export rerun execution readiness, reopen and verify the artifact/master identities, and require the review-bound artifact digest. A coherent alternative cadence-perfect PTS history for the same master can no longer be accepted, even if its artifact and execution receipt hashes are refreshed before review.

## Authoritative projections and topology

- `whole_capture` must use the entire canonical PTS list, with bounds exactly equal to its first and last PTS.
- Every named, acceptance, and route interval must contain the exact inclusive ordered projection selected from that canonical list. Disjoint, shifted-lattice, widened-bound, omitted-subsequence, and fabricated-summary evidence fails closed.
- Terminal frame count must cover the canonical whole-capture frame count. Terminal encoded time must cover the canonical whole PTS clock.
- The receipt serializes configured required marker order, patterns, optional `effect_start`, and acceptance pair. Capture markers may contain only those names; required markers must appear exactly in configured order with matching patterns.
- The interval set must equal the union of all configured consecutive required-marker pairs and exactly one acceptance pair. Invented, missing, extra, and duplicate markers or interval pairs fail.
- The producer avoids emitting a duplicate acceptance pair and derives conservative uncertainty bounds for any same-poll consecutive pair.
- Route capture-clock bounds are stored in the route receipt. If present, `route_interval` is required, fully recomputed, and must be the exact canonical PTS projection for those bounds. If trustworthy route bounds are absent, route cadence evidence must be absent.

## Progress and policy scope

- Acceptance progress samples are related to canonical PTS prefixes. The left cumulative frame/time cannot advance beyond the interval boundary; the right frame count and encoded clock must cover the canonical prefix and final included PTS. Zero or insufficient right progress cannot enclose a populated interval.
- `gamescope-cadence-v1` now states its scope explicitly: rate, gap, missing-slot, and FFmpeg drop-delta gates apply to the acceptance interval; FFmpeg duplicate count applies to the whole capture.
- Terminal drops outside the accepted interval are permitted under that exact scope. Terminal duplicate count remains globally zero.

## Red-first evidence

Before production changes, seven new false-ready states were reproduced: disjoint/replaced whole history, invented marker evidence, unchecked route interval, zero progress frame/time around a populated interval, terminal frame count below the whole decoded count, bad canonical-artifact digest, and altered policy scope. Widened whole bounds were already rejected by the round-3 arithmetic validator.

Additional acceptance tests install a coherent alternative artifact and recomputed whole/interval summaries for the unchanged master, confirm readiness can validate the artifact as internally coherent, then prove that the mandatory fresh acceptance probe rejects it. Acceptance/export verification also rejects artifact/review digest drift.

## Final validation

```text
PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py
74 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
30 tests passed

PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_boot_repair_test.py
41 tests passed

python3 -m py_compile [eight scoped Python files]
PASS

git diff --check [scoped implementation, tests, and documentation]
PASS
```

Total focused tests: 145 passed.

## Round-4 files edited

- `scripts/harness/kpharness/recording.py`
- `scripts/harness/kpharness/display_backends.py`
- `scripts/harness/kpharness/creative.py`
- `scripts/harness/kpharness/creative_accept.py`
- `tools/kpharness_gamescope_backend_test.py`
- `docs/creative-runner.md`

Earlier task-unit changes in `creative_export.py`, `creative_wine.py`, and `tools/kpharness_creative_test.py` were preserved and revalidated.

## Remaining proof boundary

These checks establish deterministic artifact, producer, lifecycle, schema, acceptance, and export contracts under mocks. They do not establish real FFmpeg/FFprobe inherited-file behavior, live Gamescope private-root capture, active MIT-SHM use, GPU cadence, distinct rendered frames, visual framing, or K1 behavior. The separately serialized bounded animated-pattern diagnostic remains the next live proof step only after independent re-review authorizes it.

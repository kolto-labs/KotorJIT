# Task 7 Gamescope exact-window backend report

Status: DONE; CODE-REVIEW CRITICAL/IMPORTANT FIX ROUND IMPLEMENTED

## Scoped rereview closure

The second review's two Critical and four Important findings were addressed:

- Schema 2 parses the executed FFmpeg argument array and requires exactly one
  `-f x11grab`, `-framerate`, `-video_size`, `-window_id`, and `-i`; every
  value must match the frozen recorder/window/display identity. Missing,
  duplicate, conflicting, or foreign-display options refuse success.
- Creative execution always ends with visual review pending and `ok=false`.
  `kpharness.creative_accept` is a separate post-capture action which rechecks
  run identity, execution readiness, artifact containment, receipt digest,
  reviewer-supplied digest, reviewer identity, and scope before atomically
  recording acceptance.
- Capture checks wrap every step kind and run inside creative helper polling
  loops, including immediately before success returns.
- Cleanup receipts preserve the exact recorder, game/Wine, display order and
  per-component results. Every later phase is attempted after an earlier
  component failure.
- Gamescope cleanup remains retryable until the recorded group is verified
  absent. It performs a bounded post-SIGKILL check and refuses to mark the
  lease closed while a verified group member survives.

## Final acceptance-provenance closure

The post-run acceptance boundary no longer trusts the serialized
`acceptance_ready` field. It authoritatively recomputes the complete execution
chain, including timestamps, route-report identity, physical-console
correlation, ownership, effective capture command, media, preservation, and
per-component cleanup. Acceptance is bound to both the reviewed media digest
and a canonical digest of the completed pre-acceptance receipt. Review-derived
fields are excluded from that digest to avoid self-reference. The accepted
receipt records reviewer, UTC time, scope, media digest, and execution digest;
`verify_acceptance()` detects later execution-evidence tampering.
It also resolves the contained continuous-media path on every verification,
requires it to remain inside the recorded run directory, reopens the file, and
recomputes SHA-256. Missing, moved, or replaced post-acceptance media therefore
invalidates the accepted receipt even when its JSON fields are unchanged.

The prior skeletal positive fixture is now a rejection test. The focused gate
also covers a full pending receipt, caller-forged readiness, missing completion
time, route/cleanup/capture mutations, media mutation, and post-acceptance
execution tampering.

## Review-fix integration

The follow-up fix round made the backend executable through
`kpharness.creative --backend linux-wine-k1-gamescope`. Admission occurs before
directory claims. The production session owns the Gamescope process group,
proves child ancestry/session/authority and an accelerated nested renderer,
launches Wine with a strict environment allowlist, freezes and continuously
revalidates one mapped game window, then starts exact-window capture. Capture
failure is checked at route-step boundaries and before publication. Teardown is
recorder, game/Wine, then the revalidated Gamescope group, including the
leader-dead/child-live case.

Schema 2 now cross-checks adapter, lease, display, window/PID/start, geometry,
FFmpeg `-window_id` argv, absence of failure evidence, retained media identity,
physical-console receipts, cleanup, preservation, and visual status before
allowing `ok=true`. Host and evidence structures are deeply frozen/copied.
The focused test is registered in CTest and the support/refusal matrix is in
`docs/creative-runner.md`.

## Implemented boundary

- Added `display_backends.py` with immutable host facts, backend capabilities,
  PID/start identity, owned-window identity, explicit admission/refusal, exact
  PID-owned X11 discovery, and a copied schema-2 evidence builder.
- Added `gamescope_xwayland.py` with an owned process-group lease, atomic child
  readiness publication, private authority allowlisting, bounded X11 and
  renderer probes, software-renderer refusal, sanitized receipts, PID/start
  revalidation, and idempotent owned-group cleanup.
- Added `X11WindowRecorder` beside the unchanged Xvfb root recorder.  It accepts
  only `OwnedWindow`, uses exact `-window_id` and actual mapped geometry, watches
  lease/window/ffmpeg liveness at 250 ms or slower, fails closed on resize or
  replacement, retains typed failure evidence, and keeps cadence and visual
  acceptance separate.
- Added the `OwnedWindow` input bridge to the existing checked-in physical X11
  adapter.  Existing Xvfb input command behavior remains compatible.
- Added a host-only focused test with injected process, environment, renderer,
  X11, time, and ffmpeg seams.  It launches no real game, Wine, Xvfb,
  Gamescope, or ffmpeg.

## Exact validation

- `python3 tools/kpharness_gamescope_backend_test.py`: 24/24 PASS.
- `python3 tools/kpharness_physical_console_test.py`: 22/22 PASS.
- `python3 tools/kpharness_creative_test.py`: 28/28 PASS.
- Fresh CMake configure followed by
  `ctest --test-dir /tmp/kp-gamescope-ctest.gbBen4 -R '^kpharness_creative_test$' --output-on-failure`:
  1/1 PASS, label `harness;offline`.
- `python3 -m py_compile` over all five affected Python modules/tools: PASS.
- `git diff --check` over the owned files: PASS.
- Fresh final registration gate in `/tmp/kp-gamescope-review.ftSeGM`:
  `kpharness_creative_test`, `kpharness_physical_console_test`, and
  `kpharness_gamescope_backend_test`: 3/3 PASS.
- Final scoped-rereview registration gate in `/tmp/kp-gamescope-final.RZHEMZ`:
  the same three tests passed 3/3.

## Self-review rulings

- GNOME/KDE and X11/Wayland remain host facts.  They do not become native
  compositor support.  Only a newly owned Gamescope/Xwayland lease can be
  admitted by this adapter.
- Crostini, Windows, macOS, native/shared Wayland, K2, missing dependencies,
  render-device absence, and display reuse are refused.
- The receipt does not serialize Xauthority values or the full environment.
  It records only the nested display and whether Xauthority is present.
- Encoded/requested FPS never becomes a distinct-game-frame claim.  `ok` is
  false until physical-console correlation, route/capture/cleanup and input
  preservation pass and visual review is explicitly accepted.
- A physical-console regression exposed an unnecessary change to legacy key
  argv.  That change was reverted; scoped input remains the verified private
  display plus a mandatory exact-window focus.

## Acceptance limit

The executable adapter and host-only lifecycle proof are complete, but no
installed K1 GPU route was launched in this task. Therefore this task does not
claim live GPU or visual acceptance, generic GNOME/KDE/Wayland support, or any
Windows, macOS, ChromeOS, K2, native/shared-Wayland support. The remaining
acceptance action is the frozen installed-K1 physical-console route plus human
review of its unaltered continuous recording.

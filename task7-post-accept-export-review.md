# Task 7 post-accept media export review

Date: 2026-09-27

Worktree reviewed: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`

Scope: `scripts/harness/kpharness/creative.py`, `scripts/harness/kpharness/recording.py`, `scripts/harness/kpharness/creative_export.py`, `tools/kpharness_creative_test.py`, `tools/kpharness_gamescope_backend_test.py`, and `docs/creative-runner.md`. The capture-cadence audit was used only to understand the evidence boundary. No Wine, game, Gamescope, X server, or real FFmpeg/FFprobe process was launched. Product files were not edited by this review.

## Verdict

**Specification verdict: PASS.** The implementation satisfies the requested post-accept derivative boundary in the reviewed code and mocked tests.

**Code-quality verdict: PASS.** The exporter is small, keeps acceptance verification centralized in `creative_accept.verify_acceptance`, reuses the legacy encoder without changing its established settings, and separates derivative provenance from the accepted execution receipt. The staging and error paths are direct enough to audit mechanically.

## Findings

### Critical

None.

### Important

None.

### Minor

None.

## Boundary verification

### No Gamescope derivative before acceptance

`creative.run_creative()` invokes the automatic renderer only when the backend is not `linux-wine-k1-gamescope`. A schema-2 Gamescope run retains `continuous.mp4`, stays `ok=false` with `visual_review.status=pending`, and never calls the renderer. The focused driver regression also checks that `representative.mp4`, `representative.gif`, and `media.json` do not exist.

This is a hard control-flow boundary, rather than a convention in the command documentation.

### Legacy behavior preserved

The refactor moves the two encoder calls into `encode_clip()` while leaving the legacy selector and settings intact:

- the existing `clip_window()` still selects at most ten seconds;
- marker selection still includes the existing one-second lead where available;
- the MP4 remains width 640, H.264, `preset=fast`, and `crf=24`;
- the legacy GIF call still passes 8 FPS and width 480;
- legacy output names and `media.json` structure remain in the same run directory.

The original creative tests pass, including the legacy success and render-failure paths.

### Current acceptance and master verified before encoding

`creative_export.accepted_receipt()` reads `creative-run.json` fresh, requires schema 2 and the Gamescope backend, binds the serialized run directory to the selected directory, recomputes completed execution readiness, and calls `verify_acceptance()`. That verifier hashes the actual master and requires equality among the actual SHA-256, the continuous-media receipt SHA-256, and the accepted review SHA-256. It also requires the accepted execution digest to match a fresh canonical digest of the execution receipt.

Export performs this verification before probing or encoding. After probing, it calls `accepted_receipt()` again and requires the receipt bytes to remain identical before either encoder can run. Pending, rejected, malformed, wrong-directory, legacy, execution-tampered, missing-master, and replaced-master cases are all rejected without an encoder call in the focused tests.

### Explicit finite bounds fail closed

The exporter rejects booleans, non-numeric values, NaN, infinity, negative starts, equal endpoints, reversed intervals, and an endpoint beyond the probed master duration. This validation occurs before `encode_clip()`. The supplemental mocked check confirmed that the exact valid endpoint `end_seconds == master duration` is admitted.

Both encoder commands receive the same computed `start_seconds` and `duration_seconds`. No internal ten-second selector or implicit end marker is used in the post-accept path. Each encoded artifact is probed; an output whose duration differs from the requested interval by more than 100 ms for MP4 or the larger of 100 ms and one selected GIF frame period is rejected. The small tolerance accounts for normal container/frame quantization and does not select or silently shorten a different interval.

### Identical bounds and configurable GIF rate

`encode_clip()` constructs one shared FFmpeg prefix containing `-ss`, `-t`, and `-i`, then uses that prefix for both MP4 and GIF. The GIF filter uses the validated integer `gif_fps`, accepted only from 1 through 60. The sidecar records the selected GIF rate and both output widths. Focused tests inspect both argument vectors and the filter string; the supplemental check repeated this at 60 FPS and at the exact end of the master.

### Staged publication and failure behavior

Both outputs and `export.json` are created under a private temporary directory inside the run directory. The destination name is a fresh UUID. Publication is one same-filesystem directory rename after encoding, output probing, duration validation, and the post-render provenance check. Encoder, probe, duration, or provenance failure exits the temporary-directory context and leaves no `accepted-media-*` directory or derivative sidecar.

The CLI converts expected validation, filesystem, subprocess, and timeout failures into JSON with `ok=false` and exit status 1. The supplemental mocked test confirmed probe failure invokes no encoder, publishes nothing, and reports failure rather than success.

The rename provides atomic directory-entry publication. This review does not claim fsync-backed crash durability, which was not part of the requested contract.

### Provenance rechecked after rendering

After both artifacts have been encoded and probed, export reloads and fully verifies the accepted receipt and actual master again. It also requires the current receipt bytes to equal the initially accepted bytes. Tests mutate the master, execution fields, and review fields during rendering; all three cases fail without publication.

### Separate derivative sidecar and immutable acceptance receipt

`export.json` is stored beside the derivatives in the newly published directory. It records:

- the complete continuous-master artifact identity, including its SHA-256;
- the accepted execution SHA-256;
- the SHA-256 of the exact accepted `creative-run.json` bytes;
- explicit start, end, and duration;
- GIF FPS, output widths, cadence statement, and tool selections;
- each output's path, SHA-256, geometry, duration, and encoded stream metadata.

Export never writes `creative-run.json` or the master. The focused success and encoder-failure tests compare the accepted receipt bytes before and after export. The supplemental success check independently repeated the byte-for-byte comparison.

## Validation run

The following safe checks passed from the isolated worktree:

```text
python3 tools/kpharness_creative_test.py
29 tests passed

python3 tools/kpharness_gamescope_backend_test.py
44 tests passed

additional mocked export boundary checks
PASS

python3 -m py_compile [five scoped Python files]
PASS

git diff --check [tracked scoped files]
PASS

git diff --no-index --check [new exporter and backend test]
PASS (exit 1 only for the expected added-file difference)
```

The additional mocked checks covered a clip ending exactly at the master duration, identical MP4/GIF bounds at GIF FPS 60, accepted-receipt byte identity after success, and FFprobe failure through the CLI.

## Residual proof limits

Per the task constraint, no real encoder ran. The tests prove command construction, gating, staging, duration decisions, hashes, receipt immutability, and error propagation against controlled subprocess/probe doubles. They do not prove that a particular installed FFmpeg build produces visually readable output, smooth GIF motion, exact frame content at the reviewed boundaries, or durable output across a host power loss. Those remain visual/integration checks and are accurately described as such in `docs/creative-runner.md`.

The cadence defects documented in `task7-capture-cadence-audit.md` remain properties of the accepted master and are outside this derivative-boundary review. Export does not claim to repair them.

# Task 7 capture cadence — round 11 brief

Date: 2026-09-27. Orchestrator-authored. Sole writer. Host-only: no Wine, game, Gamescope, Xvfb/Xwayland, mpv, x11grab capture; synthetic lavfi encodes with `/usr/bin/ffmpeg` on the host are allowed for tests/calibration. Do not touch `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock`.

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`. Preserve unrelated dirty work. No reset/stash/staging/commit/push.
Owned files: `scripts/harness/kpharness/{recording,display_backends,creative,creative_accept,creative_export,capture_diagnostic}.py`, `tools/kpharness_{creative,gamescope_backend,capture_diagnostic}_test.py`, `docs/creative-runner.md`. Do not touch other writers' files (src/**, scripts/examples/**, playback.py, cli.py, pioneer.py, session.py).

Inputs: round-10 sections of `/home/brunner56/kp-live-20260922/task7-capture-cadence-fix-review.md` and `task7-capture-cadence-adversarial-review.md`; probes in `review-probes-r10-correctness/` and `review-probes-r10-adversarial/` (reuse them as regression sources); round-10 report `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`.

## Rulings (orchestrator)
- **Content gate (R10-1 Critical, both reviews): noise floor, not a lossless diagnostic master.** The diagnostic must measure the same encoder path production uses; switching the diagnostic to lossless would test a different pipeline. Add a per-policy `distinct_noise_floor` (luma/chroma frame-difference threshold). A frame counts as distinct only if max(YDIF,UDIF,VDIF) exceeds the floor. Calibrate the floor from synthetic encodes using the recorder's exact codec settings (measured: duplicate ≤0.14, fresh ≥1.27 on testsrc2); choose a value with margin on both sides and record the calibration evidence (script + numbers) in the report. Policies stay a fixed table in code.
- **First-frame black check (R10-6):** evaluate the black check on the first frame at or after the acceptance-interval start marker, not the first frame of the capture. Startup black before the marker is recorded as evidence only.
- **Small animated area (R10-7):** keep the game policy as is, and document the limitation in the policy docs; the animated-diagnostic policy already requires ≥99% distinct frames over a full-frame pattern.

## Required fixes (red-first regressions for each)
1. R10-1 (Critical): noise floor per ruling. Regressions: half-duplicate (30→60), one-in-ten fresh, static still, textured static, 8x8 blink (game passes, diagnostic fails), full animated (passes). Use real synthetic encodes through the production probe where feasible on host; mocked rows otherwise.
2. R10-1 adversarial / R10-2 correctness (Important): a surviving FFprobe child is always recorded. Write the ledger record before (and independently of) commitment-log validation; if the log append fails, still print the head line, survivor PID and start identity to stderr and exit nonzero; the gate must not stay clear. Regressions: log deleted, rotated, hard-linked during probe.
3. R10-2 adversarial (Important): SIGINT/SIGHUP/SIGTERM during the diagnostic must run the ordered cleanup (recorder → client → display) within a bounded budget. Start the child in its own session/process group, forward the signal, wait bounded by the cleanup budget, then kill only owned processes; the result file must list any survivor exactly. Regressions with a real subprocess tree of dummy processes (no display): SIGINT, SIGHUP, repeated SIGINT.
4. Minors:
   - `--child` entry refuses unless it receives an unforgeable parent token (e.g. inherited fd carrying a nonce the parent created) and re-checks the lock fd.
   - Preflight refuses when any `/proc/<pid>` entry of this uid cannot be read, and detects targets via `/proc/<pid>/exe` basename and argv as well as comm (catches the bash-wrapped ffmpeg). It never kills processes it doesn't own.
   - Recorder FFprobe and xwininfo children inherit the lock descriptor when running under the diagnostic/creative lock.
   - FFprobe deadlines scale with media duration/frame count (bounded max), with a regression for a long clip.
   - Docs: state the trust root honestly — the commitment log anchors the head only if it lives where the run's writer cannot rewrite it; operators should copy the printed head line out of band; fix the export example that reads the head from the run dir; diagnostic re-validates the log before appending. Refuse a log on the same device+inode path as the run dir tree even via bind mount where detectable (compare st_dev/st_ino of the log's parent chain against the run dir), and document residual limits.

## Validation to paste
Suites in container and on host (host via `/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/<suite>.py'`): creative, gamescope_boot_repair, gamescope_backend, capture_diagnostic. py_compile touched modules. Scoped `git diff --check` on touched tracked files; whitespace check on untracked touched files. Rerun reviewer probes p2, p5, p7, p9 (adversarial) and content_noise (correctness) adapted to the new API and paste outputs.

## Report
`.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`: per requirement file:line + regression name, calibration evidence, commands + outputs, files changed, residual proof boundary. Then stop editing.

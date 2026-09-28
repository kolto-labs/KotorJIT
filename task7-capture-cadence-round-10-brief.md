# Task 7 capture cadence — round 10 brief

Date: 2026-09-27. Orchestrator-authored. Sole writer owns the unit. Host-only: no Wine, game, Gamescope, Xvfb/X server, FFmpeg capture or FFprobe on real media; do not touch `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/tmp/harness-locks/live-game.lock`.

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (branch `codex/lua-boundary-validation`). The tree is intentionally dirty with other work. Preserve every unrelated change. No reset, stash, broad staging, commit or push. Never edit the canonical checkout.

Inputs:
- Round 9 reviews (both FAIL): `/home/brunner56/kp-live-20260922/task7-capture-cadence-fix-review.md` (section "Round 9 verdict") and `/home/brunner56/kp-live-20260922/task7-capture-cadence-adversarial-review.md` (section "Round 9 verdict").
- Rootless research: `/home/brunner56/kp-live-20260922/task7-rootless-root-capture-research.md`.
- Diagnostic readiness scout: `/home/brunner56/kp-live-20260922/task7-animated-diagnostic-readiness.md`.
- Original brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-fix-brief.md`. Round reports 1–9 under `.superpowers/sdd/lua-boundary-validation-plan/`.

## Part A — close R9-1: the cleanup-ledger head must be truly external (both reviews)

Required:
1. The empty ledger carries a per-run random nonce, so no two runs share a launch head.
2. Every ledger change (run initialization, acceptance-time failure append, signal-error-reaped resolution, recovery resolution) emits the new head and the affected failure ID outside the run directory: print a single machine-parseable line to stdout/stderr of the invoking CLI **and** append it to an operator-supplied commitment log whose path must resolve outside the run directory (refuse paths inside it, symlinks into it, or missing). Launch must print the initial head before any child runs.
3. Failure exceptions carry the failure ID and new head; the accept/recover CLIs catch them, print the head line, and exit nonzero.
4. Docs (`docs/creative-runner.md`, including the stale lines ~407-420 describing per-failure files and `--recover-cleanup` without the head) say: supply the last head the tool printed / wrote to the commitment log; never hash the file at review time.
5. Red-first regressions: rollback-to-empty, reset-to-launch-head, forged failure+resolution pair, deletion — each with the head taken **only** from captured tool output / commitment log, never from the ledger file. The existing helper at `tools/kpharness_gamescope_backend_test.py:41` that hashes the file must not be the source of the head in these tests.

## Part A minors (both reviews)
- Exact schema must reject bool/float stand-ins for int fields (`schema`, `sequence`, waits, pid), non-dict payloads (return False / typed error, never `AttributeError` escaping gates), duplicate JSON keys, non-canonical encoding (require exact canonical re-serialization equality), and a resolution timestamp earlier than its failure. Pick one UTC timestamp form and reject the other.
- Serialize ledger appends with an exclusive lock (e.g. `fcntl.flock` on the ledger or a sibling lock file) and re-verify the head the caller supplied immediately before appending; a mismatch fails closed.
- A surviving child with empty start identity must not silently produce no record and a clear gate; record an explicit unrecoverable failure (or refuse acceptance) — never a clear gate.
- A recorded PID whose current start differs from the recorded start is proof the original exited: allow resolution as `original_exited_pid_reused` without signaling anything.
- Bind boot ID (`/proc/sys/kernel/random/boot_id`) and PID-namespace identity (`/proc/self/ns/pid` inode) into failure records; recovery from a different boot or namespace refuses rather than concluding absence.
- Make the two tests `test_marker_bounded_cadence_recomputes_terminal_duplication` and `test_same_poll_markers_keep_byte_order_without_claiming_reverse_time` hermetic (inject the probe-tool identity or a fake executable); the suite must pass inside a container that has no `ffprobe`.

## Part B — capture target correction (orchestrator, verified from upstream source)

Private Gamescope-root capture records all-zero frames: rootless Xwayland creates a 0x0 screen pixmap (`hw/xwayland/xwayland-glamor.c:154-156`) and nulls root `borderClip` (`xwayland-window.c:1606-1623`); ShmGetImage uses `borderClip` as visible region (`Xext/shm.c:656-657`) and censors to zero without error. Current SHM/cadence gates would pass black media.

Required:
1. Refuse root capture when the lease's Xwayland is rootless (typed failure `capture_target_rootless_root`). Do not delete the root path's evidence code if another backend (Xvfb) still uses it legitimately; scope the refusal to Gamescope rootless.
2. Return the Gamescope backend to exact verified child-window capture (`-window_id` on the owned, verified game window) and, before FFmpeg starts, require and record: window mapped/viewable (realized), absolute origin, size, border width, screen/root size, and that the capture rectangle is fully inside the screen (the exact conditions of `Xext/shm.c:639-654`) and equals the lease geometry. Re-read immediately before exec; a mismatch refuses launch. Record this as structured evidence bound into the receipt.
3. Keep the fail-closed MIT-SHM fallback gate and first-frame startup admission.
4. Add a mandatory content gate evaluated before any cadence verdict can pass: first frame not all black (luma max above a black threshold and nonzero variance) and a distinct-frame measurement over the acceptance interval (e.g. per-frame MD5 via the existing FFprobe/FFmpeg descriptor transport). Typed failures `capture_content_black` and `capture_content_static`. Thresholds are policy fields; for the animated diagnostic the policy requires distinct frames ≥ 99% of expected pattern changes. For game capture, record the distinct ratio as evidence with a configurable minimum.
5. The acceptance receipt, verification and export must bind the content-gate evidence and geometry precondition evidence.
6. If SHM BadMatch still occurs with verified geometry, the design answer is the PipeWire adapter (separate reviewed unit); do not add CFR duplication or silent non-SHM fallback.

## Part C — checked-in animated-pattern diagnostic driver (no launch)

Add a checked-in diagnostic entry point (e.g. `kpharness.capture_diagnostic`) that, when later authorized, runs exactly once on the host:
- takes the canonical lock (fd kept, passed to children), refuses if any `wineserver`, `swkotor`, `gamescope` or `ffmpeg`/`ffprobe` process not owned by this run exists, and records `/proc` evidence for the refusal;
- creates a fresh source-equal snapshot with `gamescope_snapshot.create_snapshot` + `verify_snapshot`, and runs from it;
- computes and prints pre-launch commitments: route SHA (a `diagnostic-route.json` describing the pattern and markers), FFprobe SHA of the resolved ELF, and the launch ledger head;
- starts a private Gamescope Xwayland lease, launches host `mpv` playing lavfi `testsrc2` at 60 fps with a fixed `--title` (it sets `_NET_WM_PID`; glxgears/vkcube do not), discovers the single owned window, applies Part B geometry preconditions, and records through the existing recorder with `/usr/bin/ffmpeg` (not the `~/.local/bin` wrapper) and the brew ffprobe;
- writes `pattern_start`/`pattern_end` markers around a 30 s acceptance interval;
- cleans up recorder → client → display in order, and checks protected X0/X94/X100 unchanged;
- evaluates every pass criterion and writes a structured result: no MIT-SHM fallback string; first-frame admission; exact geometry; content gate; canonical PTS artifact/master binding; ≥99% of 60 FPS; ≤0.5% missing/drop ratio in the acceptance interval; no gap >50 ms; zero FFmpeg duplicates; complete cleanup with no unresolved ledger entry; protected displays unchanged; media SHA printed.
- no automatic retry; exit nonzero on any failure; all failure evidence retained.
- host tests with mocks for preflight refusal, snapshot, commitments, criteria evaluation (each criterion failing independently), and cleanup ordering.

## Validation the writer must run and paste
- Focused suites **both** in the container and on the host (`/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/<suite>.py'`): creative, gamescope_boot_repair, gamescope_backend, plus any new diagnostic test file.
- `python3 -m py_compile` on every touched module.
- `git diff --check -- <touched tracked files>` and a whitespace check for untracked touched files (`creative_accept.py`, `creative_export.py` are untracked). Do not run a whole-worktree `git diff --check` (it takes >12 minutes on MyBook).

## Report
Write `.superpowers/sdd/lua-boundary-validation-plan/ta[REDACTED].md`: per requirement, the file:line and the named regression; the exact commands and outputs; files changed; residual proof boundary. Then stop editing.

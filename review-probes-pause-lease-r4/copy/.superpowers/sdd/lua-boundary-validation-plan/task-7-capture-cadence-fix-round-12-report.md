# Task 7 capture cadence fix, round 12 report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-12-brief.md`.

Nothing live ran. No Wine, game, Gamescope, Xwayland, mpv, or x11grab was started. Only synthetic lavfi encodes ran, through host `/usr/bin/ffmpeg`, plus dummy `sleep` and Python process trees. The live-game lock was never opened. The p12 rerun and the production code path only `stat` its pathname. Nothing was reset, stashed, staged, committed, or pushed. Pre-round copies of the owned files are in `/tmp/r12-backup/` (container `/tmp`). Host load was 229 to 270 on 12 CPUs for the whole round.

## Files changed

All changes are inside the owned set.

- `scripts/harness/kpharness/display_backends.py`:
  - policy `animated-diagnostic-v2` (floor 3.9, `separation_factor` 3.0) replaces v1;
  - `content_separation` and `CONTENT_HISTOGRAM_EDGES`;
  - `content_recomputed`, which `_content_evidence_passed` now uses.
  - `game-capture-v1` is byte-identical.
- `scripts/harness/kpharness/capture_diagnostic.py`:
  - `PATTERN_STEP` / `PATTERN_GRAPH`, and the client and route now use them;
  - the `calibration_ambiguous` verdict;
  - the signal mask around the spawn, with the child unblocking;
  - the trusted lock check for `--child`;
  - exe-identity preflight, which also feeds the post-run scan.
- `scripts/harness/kpharness/gamescope_socket.py`: `common_repository_root`, `canonical_lock_path_for`, `trusted_repository_root`, and `held_lock_descriptor`. `canonical_lock_guard` behaves as before. Only its `.git` resolution moved into a helper.
- `docs/creative-runner.md`.
- `tools/kpharness_gamescope_backend_test.py` and `tools/kpharness_capture_diagnostic_test.py`.

Four tests were added after a review pass and were not run red first:

- `test_recorder_keeps_calibration_ambiguous_content_recomputable`
- `test_snapshot_child_lock_path_equals_the_supervisor_lock_path`
- `test_a_multithreaded_supervisor_refuses_before_the_spawn`
- the `content_separation` and `supervisor_threads_at_spawn` assertions in the supervisor commitments test

The first two verify existing behavior. The other two are new behavior, but their red was not captured.

`recording.py`, `creative.py`, `creative_accept.py`, `creative_export.py`, and `tools/kpharness_creative_test.py` did not change.

## Red-first evidence

The tests were written first and run against the unchanged modules. Output is in `/home/brunner56/kp-live-20260922/r12-red/`.

- `red-unit.txt`: 25 tests, `FAILED (failures=2, errors=35)`.
  - Most errors are the missing v2 policy, `PATTERN_*`, `repository_root=`, and `tools=`.
  - Two failures show behavior:
    - `test_admitted_child_pins_the_trusted_root_for_every_later_lock_check`: the environment stayed `/elsewhere`.
    - `test_supervisor_refuses_a_renamed_tool_copy_before_any_launch`: the child was spawned.
- `red-interrupt.txt` (spawn window, real processes): three subtest failures.
  - SIGINT: `'interrupted before launch: SIGINT' unexpectedly found`.
  - SIGHUP and SIGTERM: `launches 0 != 1`. The orphan from the SIGINT subtest still held the fake lock, so the next supervisor refused. That orphan is the defect itself. It was my own test's dummy child, and it finished its own run and exited. I sent it no signal.
  - `test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes` passed on the baseline, by construction. It guards the new blocking and is not a red test.
- Only ruling 2 has a behavioral red of my own. For rulings 1, 3, and 4, the red is missing-API errors plus the two unit failures above. Their behavioral red is the reviewers' baseline output:
  - `review-probes-r11-adversarial/p12.out`: `forged_pipe_commitments_env_redirected_lock: ADMITTED`.
  - `p10.out`: `real renamed_enc_binary: detected=False`.

## Ruling 1 (R11-C1, Critical): pattern, calibration, separation

### Pattern and why

`PATTERN_STEP = eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.11:eval=frame`, and `PATTERN_GRAPH = testsrc2=size=1024x768:rate=60,` + step (`capture_diagnostic.py`, near `CLIENT_TITLE`). The client plays `av://lavfi:` + `PATTERN_GRAPH`.

- Every output frame gets a full-frame brightness level `(3n mod 7) - 3`. There are seven levels, 0.11 apart (about 18 luma).
- Any two frames 1 to 6 source frames apart differ by at least one level over the whole frame. Adjacent frames differ by at least three.
- This does not depend on how fast `testsrc2` moves. `testsrc2` is only texture at 40% contrast.
- Blind spot: a skip of exactly 7 frames (117 ms) repeats the level. The cadence gate's 50 ms maximum gap is 3 frame intervals, so a capture that skips 7 frames already fails cadence.
- `PatternTests` asserts both properties from the expression itself.

I chose a brightness step over checker inversion. Inversion has period 2, so a one-frame skip returns to the same polarity and leaves only `testsrc2` motion. That is the R11-C1 failure again.

The expression has no comma, so it needs no filtergraph escaping in mpv's URL. On the host, `ldd` shows `/usr/bin/mpv` (mpv-0.41.0-5.fc44) and `/usr/bin/ffmpeg` (ffmpeg-8.1.2-3.fc44) link the same `/lib64/libavfilter.so.11`, `libavformat.so.62`, and `libavdevice.so.62`. I did not run mpv.

### Calibration

Script: `/home/brunner56/kp-live-20260922/r12-calibration/calib_r12.py`. It is the correctness reviewer's `calib_r11.py` with `SOURCES` rewritten onto the new pattern, plus six families.

- Each clip is 18 s at 1024x768. It is rendered to `bgr0` and encoded with the recorder's exact args (`-c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p -threads 2`).
- The production `probe_frame_content` and `probe_frame_pts` read each clip over `/proc/self/fd/N` with brew FFprobe.
- Labels come from the framemd5 of every source frame.
- The step is applied at the pattern output. Capture duplication (`fps=R,fps=60`) and I-frame alignment trims come after it.
- I-frames are at 250, 500, 750, and 1000 in every clip, checked by `pict_type`.
- Output: `summary.out`.

| Family | Fresh n / min | Duplicate n / max | I-frame duplicates n / max | v2 verdict |
| --- | --- | --- | --- | --- |
| fresh60 | 1079 / 51.83 | 0 | 0 | passed, separated |
| slow_half | 1079 / 51.78 | 0 | 0 | passed, separated |
| slow_quarter (R11-C1 case) | 1079 / 51.84 | 0 | 0 | passed, separated, ratio 1.0 |
| frozen (testsrc2 at 1 FPS) | 1079 / 51.73 | 0 | 0 | passed, separated |
| r30_k0 / r30_k1 | 539 / 15.35, 540 / 15.35 | 540 / 0.398, 539 / 0.944 | 0; 4 / 0.944 | failed 0.50, separated |
| r30_k1_slowq | 540 / 15.28 | 539 / 0.913 | 4 / 0.913 | failed 0.50, separated |
| r20_k0 / k1 / k2 | 359-360 / 33.24 | 719-720 / 0.985 max | 2-3 / 0.985 max | failed 0.33, separated |
| r12_d5 / r12_d5_k1 (distance 5, one level) | 215-216 / 15.57 | 863-864 / 0.975 | 4 / 0.975 | failed 0.20, separated |
| r15, r45, r50, r58, r3 | min 15.37 | max 1.0167 (r45 I-frame) | r45 2 / 1.0167 | all failed, separated |

- Duplicates: 7,825 frames, max **1.0167** (an I-frame duplicate, r45).
- Fresh: 10,518 frames, min **15.2818** (r30_k1_slowq, one level).
- The ratio is 15.03 and the geometric midpoint is 3.942.
- **Floor 3.9.** That is 3.84x above the largest duplicate and 3.92x below the smallest fresh frame, so there is at least 3x on both sides.
- `test_policy_floor_sits_inside_the_calibrated_gap_with_threefold_margin_on_both_sides` pins this, using `CALIBRATED_DUPLICATE_MAX = 1.0167` and `CALIBRATED_FRESH_MIN = 15.2818`.

The opt-in real-encode test ran on the host with the new pattern (`r12-calibration/real-encode-test.txt`, `OK`):

- `slow_quarter_stepped` passed at 1.0.
- `half_duplicate_30_to_60` failed at 0.5.
- `one_in_ten_fresh` failed at 0.0979.
- `static_still`, `textured_static`, and `blink_8x8` failed.
- `full_animated_60` passed.

Encode cost (`encode_cost.out`): bitrate is +13% (7,467 vs 6,595 kbit/s at identical size and duration). The speed numbers are unusable at load 233-270: old 0.555x and 0.359x, new 0.296x and 1.28x. The cost is unverified beyond bitrate.

### Separation rule (mandatory check)

`display_backends.content_separation` runs when a policy defines `separation_factor`, which only the diagnostic policy does.

- The guard band is the open interval `(floor/3, floor*3)` = (1.3, 11.7), taken from the policy table and never from the data.
- `separation` records:
  - the guard band and the counts below, inside, and above it;
  - `duplicate_max` and `fresh_min`;
  - a histogram over fixed bins `CONTENT_HISTOGRAM_EDGES`, so recomputation is exact.
- If any acceptance frame is inside the band, the status is `ambiguous`. The only failure is then `calibration_ambiguous: ...`, and `capture_content_static` is suppressed.
- `capture_diagnostic.evaluate` recomputes separation from the hashed artifact under the v2 policy (`content_separation_status`), never from the receipt.
- `ambiguous` makes the verdict `calibration_ambiguous`. That outranks PASS and FAIL, every criterion is still recorded, and the exit is nonzero.
- `supervise` writes the recomputed separation dict (guard band, counts, `duplicate_max`, `fresh_min`, and histogram) to `diagnostic-result.json` as `content_separation`. It is `null` when nothing could be recomputed.

Tests:

- `ContentSeparationTests` covers:
  - fixed histogram;
  - band values give ambiguous and never pass or blame capture: one frame at the floor, fresh values inside the band, duplicates inside the band, and plain slow-testsrc2 values;
  - stuck and half-duplicate captures separate and blame capture;
  - the game result shape is unchanged.
- `CaptureTargetAndContentTests.test_recorder_keeps_calibration_ambiguous_content_recomputable` runs the recorder's own `_finalize_cadence` on rows at the floor. It checks:
  - the recorder receipt has `separation.status == 'ambiguous'`;
  - the first content failure is `calibration_ambiguous`, with no `capture_content_static`;
  - `D.content_recomputed` equals the recorder's content block;
  - `CD.content_separation_status` returns the ambiguous separation.
- `SnapshotAndCommitmentTests` asserts that `content_separation` is present in the result JSON. It is `None` in that test, because no content is recomputed.
- `CriteriaTests` covers:
  - ambiguous outranks another failed criterion;
  - separated stale content gives FAIL;
  - the receipt cannot claim a separation the artifact does not show, in either direction;
  - a loosened `separation_factor` fails the content gate.

Worked example (`r12-calibration/old_pattern_under_v2.out`): the reviewer's round-11 old-pattern encodes, judged by v2.

```text
OLD-pattern slow_quarter  v2: status=failed ratio=0.0000 sep=ambiguous below=1000 inside=79 above=0 failures=['calibration_ambiguous']
OLD-pattern fresh60       v2: status=failed ratio=0.0000 sep=ambiguous below=0 inside=1079 above=0 failures=['calibration_ambiguous']
```

So if the step did not reach the screen, the verdict would be `calibration_ambiguous`, not a capture failure.

The game policy is unchanged (`GAME_POLICY_R11` equality test). The docs and the `display_backends.py` comment say its zero floor is not calibrated.

## Ruling 2: spawn-window signals

The supervisor side (`capture_diagnostic.py`, `supervise`, the `driver.log` block) works in this order:

1. `signal.pthread_sigmask(SIG_BLOCK, INTERRUPT_SIGNALS)` runs before `spawn_child`.
2. The supervisor assigns `signals.child`, reads the child's PID and start, and records `result['child']`.
3. The previous mask is restored in `finally`, which also covers a Popen exception. A held signal is then delivered, and the handler forwards one SIGINT.
4. The single-threaded assumption is enforced. `result['supervisor_threads_at_spawn']` records `threading.active_count()`. With more than one thread, the supervisor refuses before `launches = 1` and before any spawn (`test_a_multithreaded_supervisor_refuses_before_the_spawn`).

The child side: `run_child` installs its handlers, then calls `_ChildSignals.unblock()` as the first statement inside the ordered-cleanup `try`. It does this before it starts the lease, the client, or FFmpeg.

Regressions (`InterruptTests`, real supervisor, child, and `sleep` grandchildren):

- `test_a_signal_between_fork_and_popen_return_still_supervises_the_child` covers SIGINT, SIGHUP, and SIGTERM. The signal is sent from inside `spawn` after the child exists. The test checks:
  - `interrupts == [sig]` and exactly one forwarded SIGINT;
  - the child identity is recorded, and the child has exited and is not alive;
  - no survivors.
- `test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes` reads `SigBlk` from `/proc/PID/status` of the child, the Gamescope stand-in, and the client stand-in. The INT, HUP, and TERM bits are 0.

The whole `InterruptTests` class passed: 11 tests, `r12-red/green-interrupt.txt`.

p11b rerun, unchanged probe (`/home/brunner56/kp-live-20260922/review-probes-r12-rerun/p11b.out`):

```text
supervisor_exit=1 errors=['interrupted: SIGINT'] launches=1 child_returncode=1 owned_survivors=[]
child_alive_after_supervisor_exit=False owned_started_after_supervisor_exit=[]
unsupervised_child_completed_run=True its_cleanup_steps=[] result_file_rewritten=False
```

The probe's labels come from round 11. Here `unsupervised_child_completed_run=True` only means the child wrote `diagnostic-run.json` before it exited. The supervisor waited for it (`child_returncode=1`, child not alive). Nothing had started, so the cleanup steps list is empty.

## Ruling 3: `--child` authority

- `gamescope_socket.trusted_repository_root(module_file)` derives the root from the code's own location and never from the environment.
  - Code under `<snapshot>/runtime/kpharness/` runs `verify_snapshot(snapshot)`, which checks the manifest canonical form, its `.sha256` sidecar, and every copied module. It then takes the manifest's `repository_root`.
  - Checkout code takes `parents[3]`.
- `held_lock_descriptor(fd, path)` requires all of these:
  - `fstat(fd)` and `stat(path)` are regular files with the same `(st_dev, st_ino)`;
  - that exact descriptor's `/proc/self/fdinfo/<fd>` shows the `FLOCK ... WRITE` entry for that dev:ino;
  - the path still names the same inode after the check.
- `verify_child_authority` uses `held_lock_descriptor(config['lock_fd'], trusted_lock_path())`. `_child_main` then pins `KP_GAMESCOPE_REPO_ROOT` to the trusted root, so later socket-cleanup guard calls cannot be redirected.
- The global `canonical_lock_guard` still honours the environment, because the boot_repair suite, which I do not own, relies on it.

Regressions (`ChildAuthorityTests`, temporary roots only):

- the passed descriptor itself must hold the lock: another fd of the same file is refused, an unlocked fd is refused, and a closed fd is refused;
- `test_environment_redirected_private_lock_is_refused` is the p12 regression. It also asserts that `trusted_repository_root()` returns the checkout with the environment redirected;
- a real snapshot gives its manifest root even with the environment redirected, and a tampered or missing manifest raises;
- the admitted child pins the trusted root;
- `test_snapshot_child_lock_path_equals_the_supervisor_lock_path` compares pure paths, with no lock opened. The lock path derived from a real snapshot manifest (manual `.git`/`commondir` parse) equals `CD.canonical_lock_path()` (`git rev-parse`). `CD.trusted_lock_path()` equals it too.

p12 rerun, unchanged probe (`review-probes-r12-rerun/p12.out`):

```text
forged_pipe_and_commitments_no_lock: refused: child does not hold the canonical lock: canonical lock descriptor or path is unavailable: [Errno 9] Bad file descriptor
forged_pipe_commitments_env_redirected_lock: refused: child does not hold the canonical lock: lock descriptor is not the canonical lock file
```

The other four p12 cases stay refused. p12 and `held_lock_descriptor` only `stat` the canonical lock pathname. Neither opens it.

Documented trust boundary (`docs/creative-runner.md`, capture diagnostic section):

- A same-UID process that really holds the canonical lock is inside the boundary.
- So is a same-UID author who writes their own snapshot whose manifest names a private root, because that is running code they control.

## Ruling 4 (Minor): renamed binaries

- `process_inventory(..., tools=...)` covers readable own-UID rows with an openable `/proc/PID/exe`.
  - It first compares the configured FFmpeg and FFprobe ELF by device and inode, which catches a hard link.
  - Next, only for files of the same size, it compares SHA-256. Each `(dev, ino, size, mtime)` is hashed once.
  - A match sets `exe_tool_match`, and `forbidden_processes` refuses it.
- `supervise` now computes `native_elf_identity` for both tools before preflight. It passes them to preflight and to the post-run survivor scan.
- `preflight.json` records `tool_identities`.
- Tests (`PreflightExeIdentityTests`):
  - a renamed copy and a hard link are detected;
  - a same-size different file and an unreadable exe are not;
  - hashing happens once for three rows sharing an inode, and a small file is never hashed;
  - the supervisor refuses a renamed copy before launch, and `spawn_child` is not called.
- The docs narrow the guarantee: name, exe basename, and argv detection, plus exe content for readable own-UID processes. Not covered: another build, another UID, non-dumpable processes, and processes that start after the scan.

p10 reruns (`review-probes-r12-rerun/`):

- The unchanged `p10-original.out` still gives `renamed_enc_binary: detected=False`. It calls `process_inventory` without configured identities, as round 11 did.
- The adapted `p10_r12_preflight.py` / `p10-r12.out` passes a `/bin/sleep` copy as the configured-FFmpeg stand-in:

```text
renamed_copy_exe_argv_comm_with_configured_identity: refused: preflight found existing Wine, game, Gamescope, or FFmpeg processes
real renamed_enc_binary: exe_tool_match=ffmpeg by=sha256 detected=True comm=enc exe=/tmp/kp-r11-p10-l55pyqgp/enc
```

In that adapted run, every host `sleep` also matches. That is expected, because the stand-in identity is `sleep`, and it shows the matching is by content. The probe's `forbidden_all` line lists them. It sent no signal: `os.kill` is patched to raise, and only its own three dummies were terminated.

## Validation

Final run, after the follow-up changes. Output is in `/home/brunner56/kp-live-20260922/r12-suites/final/`.

```text
# container (Python 3.12.3): PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 142 OK (skipped=1: RealEncodeContentTests) | capture_diagnostic 50 OK
# host (Python 3.14.7): host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py'
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 142 OK (skipped=1) | capture_diagnostic 50 OK
```

- Total: 266 in each environment, with 265 run and 1 skipped. Round 11 had 246.
- An earlier full run, before the follow-ups, had 263 per environment, all OK (`r12-suites/`).
- The skipped opt-in `RealEncodeContentTests` was run separately on the host with `KP_R11_REAL_ENCODES=1`: 1 test, OK (`r12-calibration/real-encode-test.txt`).

- `py_compile` of the three changed modules and two changed test files: OK.
- Trailing-whitespace scan of the six touched files: 0 lines.
- `git diff --check -- docs/creative-runner.md`: clean. The other touched files are untracked.
- No whole-worktree diff was run.

## Residual proof boundary

- **Synthetic calibration only.** The mpv, Gamescope, and x11grab path is not measured. If its noise differs, the separation rule turns that into `calibration_ambiguous`, not a pass or a capture blame.
- **The duplicate maximum crept up as families were added** (0.944, then 0.985, then 1.0167). The band edge is 1.3. A real I-frame duplicate above 1.3 gives `calibration_ambiguous`, which fails safe.
- **mpv's use of `eq ... eval=frame` is inferred** from the shared libavfilter, not run.
- **The spawn-mask fix needs a single-threaded supervisor.** This is enforced by refusal, not proven for threads started between the check and the block. None are started there.
- **Forgery residual:** a same-UID author of a snapshot manifest naming a private root is inside the trust boundary, as documented.
- **The one authorized diagnostic has still not run.** Nothing here authorizes it.

## Grill me

1. **Can a forger still redirect `--child` to a private lock?** (weakest)
   Yes, by writing a whole fake snapshot whose manifest (and its `.sha256`) names a private root, then running the copied code from it. The env-var path is closed. p12 case 6 is refused in `review-probes-r12-rerun/p12.out`, and `test_environment_redirected_private_lock_is_refused` covers it. The manifest path is the same redirect moved into a data file the forger writes. I documented it as inside the trust boundary, because the forger then runs code they control. Closing it needs an anchor outside the same UID's reach, and nothing in this tree provides one. Status: unresolved by design, documented in `docs/creative-runner.md`.
2. **Does the calibration represent the real mpv to x11grab path?**
   Unverified. The only referents are synthetic: `r12-calibration/summary.out` and `real-encode-test.txt`. What makes a mismatch safe is the separation rule. `old_pattern_under_v2.out` shows plain testsrc2 at native and quarter speed judged `calibration_ambiguous`, not PASS and not a capture failure. The first real run's `content.separation.histogram` is the check.
3. **Why is there only 1.28x between the duplicate maximum (1.0167) and the band edge (1.3)?**
   The brief's 3x is floor-to-population, and that is 3.84x and 3.92x (`summary.out`, last two lines). The band edge sits at floor/3 by construction, so a duplicate above 1.3 lands in the band and the verdict is ambiguous. That is a failure, not a false pass. The maximum rose with each family added: 0.944 for r30_k1, 0.985 for r20_k1, 1.0167 for r45. More I-frame alignments could push it past 1.3. That would give a false `calibration_ambiguous`, never a false PASS.
4. **Could the blocked mask leak into Gamescope, mpv, or FFmpeg, or be lost?**
   `test_the_spawn_mask_never_reaches_the_child_or_its_owned_processes` reads `SigBlk`: the INT, HUP, and TERM bits are 0 in the child, the lease stand-in, and the client stand-in. Unblocking happens in the first statement of the `run_child` cleanup scope. A second supervisor thread would defeat the block. The supervisor now refuses in that case (`test_a_multithreaded_supervisor_refuses_before_the_spawn`) and records `supervisor_threads_at_spawn`.
5. **Does the child refuse if a repository input changes between snapshot and child start?**
   Yes. `verify_snapshot` in `trusted_repository_root` rehashes the manifest's `repository_inputs` (`gamescope_snapshot.py`, `verify_snapshot`). In this dirty, multi-writer worktree, an edit to `data/addresses/*.json` in those seconds would refuse `--child` (exit 2, no lease). That fails closed and has not been observed (unverified).

Handoff, the one question not settled: does the real mpv render of `PATTERN_GRAPH` keep every duplicate at or below 1.3 and every fresh frame at or above 11.7? The single check that settles it is `content_separation` (with its histogram) in `diagnostic-result.json` from the one authorized diagnostic run.

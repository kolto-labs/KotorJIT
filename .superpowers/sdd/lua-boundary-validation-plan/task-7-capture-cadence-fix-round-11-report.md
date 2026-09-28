# Task 7 capture cadence fix, round 11 report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-11-brief.md`.

Nothing live was started: no Wine, game, Gamescope, Xvfb, Xwayland, mpv, or x11grab. Only synthetic lavfi encodes ran, through host `/usr/bin/ffmpeg`. The live-game lock was not opened. Nothing was reset, stashed, staged, committed, or pushed. Pre-round copies of every owned file are in `/tmp/r11-backup/`.

Host load was 115 to 260 on 12 CPUs for the whole round. All probe timings below were measured under that load.

## Files changed

The changes stay inside the owned set.

- `scripts/harness/kpharness/display_backends.py`: per-policy noise floor, and the black check at the acceptance start.
- `scripts/harness/kpharness/recording.py`: frame-scaled FFprobe deadlines, and `inherited_fds` for FFmpeg, FFprobe, and xwininfo.
- `scripts/harness/kpharness/creative_accept.py`: survivor always recorded, log bind-mount alias check, `append_commitment_line`, unrecorded-survivor sidecar, scaled re-probe deadlines.
- `scripts/harness/kpharness/capture_diagnostic.py`: preflight, child token and lock check, signal forwarding, cleanup budget, owned-process kill, run bound.
- `scripts/harness/kpharness/creative.py`: `live_lock` yields its stream, and the Gamescope recorder inherits that descriptor.
- `docs/creative-runner.md`.
- Tests: `tools/kpharness_gamescope_backend_test.py`, `tools/kpharness_capture_diagnostic_test.py`, `tools/kpharness_creative_test.py`.

`creative_export.py` did not change. It gates through `verify_acceptance` → `cleanup_state_clear` (`creative_export.py:34`), so the new sidecar check reaches export. `ExportTests.test_unrecorded_survivor_sidecar_blocks_verify_and_export` proves this.

## Red-first evidence

The round-11 tests were run against a tree that holds the pre-round owned modules (`/tmp/r11-red`, modules copied from `/tmp/r11-backup`) and the new tests. Result: `Ran 32 tests ... FAILED (failures=16, errors=26)`. The full output is in `/tmp/r11-red-run.txt` and `/tmp/r11-red-summary.txt`. These are the failures that show behavior, not a missing API:

- `half_duplicate_30_to_60` under `animated-diagnostic-v1`: `'passed' != 'failed'`, and `1.0 != 0.5` for the ratio.
- Black startup before the marker: `'failed' != 'passed'`.
- Bind-mount alias of the run directory, a subdirectory, or a file: `ValueError not raised` (3 cases).
- `--child` without a token: `DiagnosticRefused not raised`.
- Wrapped, `exe`, and `env` targets: `[] != [301, 302, 303, 304]` and `[] != [401]`.
- Commitments append after a hard link was added: `Expected 'mock' to not have been called`, meaning the child was spawned.
- Creative recorder lock inheritance: `not enough values to unpack (expected 1, got 0)`.
- Export with a sidecar: `True is not false`.

The survivor tests fail on the missing `survivor` field. The substantive red for those is the reviewers' own baseline output: p2 and p7 gave `ledger_records_after=0 gate_clear_with_same_head=True reaccept ... exit=0`. The interrupt tests fail on baseline because the supervisor has no Popen path. The mechanism red is the reviewers' p5 (`child_cleanup_steps_completed=[]`).

Two defects were found during this round, and each got a regression:

- **Run deadline.** An honest diagnostic would have been cut off at 74 s, before its own normal cleanup finished. With the pre-fix formula, `test_an_uninterrupted_run_is_never_cut_short_by_the_run_deadline` fails with `AssertionError: 74.0 not greater than or equal to 1576.0`.
- **Unreadable `exe` refusal.** A host classification (below) showed that refusing on an unreadable `exe` would block the run permanently. It is now evidence only (`test_unreadable_exe_alone_is_evidence_not_a_refusal`).

## Requirement 1: R10-1 content noise floor (Critical)

- **Policy table.** `display_backends.py:32-46`. `animated-diagnostic-v1` sets `distinct_noise_floor` to 1.2. `game-capture-v1` sets it to 0.0, which keeps the game policy as it was, per the ruling.
- **Counting.** `evaluate_content` (`display_backends.py:204`) counts a frame as distinct only when `max(ydif, udif, vdif) > floor`, and records the floor in `acceptance`. `_content_evidence_passed` still requires the receipt policy to equal the table, so a changed floor is refused.
- **Mocked-row regressions.** `ContentNoiseFloorTests` covers these cases. The rows are shaped on the calibration values below.

| Clip | animated-diagnostic-v1 | game-capture-v1 |
| --- | --- | --- |
| Half duplicate | fails, ratio 0.5 | passes |
| One in ten fresh | fails, ratio 0.1 | passes |
| Static still | fails | fails |
| Textured static | fails | fails |
| 8x8 blink | fails | passes |
| Full animated | passes | passes |

  The class also covers floor-in-gap margins, receipt tampering (`test_receipt_cannot_loosen_the_noise_floor`, and `content_noise_floor_loosened` in the execution-gate mutations), and table immutability.
- **Real encodes through the production probe.** `RealEncodeContentTests` is host-only. It is skipped in the default suites; set `KP_R11_REAL_ENCODES=1` to run it. Host run (`/home/brunner56/kp-live-20260922/r11-calibration/real-encode-test.txt`):

```text
half_duplicate_30_to_60 {'animated-diagnostic-v1': ('failed', 0.5), 'game-capture-v1': ('passed', 1.0)}
one_in_ten_fresh {'animated-diagnostic-v1': ('failed', 0.0979), 'game-capture-v1': ('passed', 0.8608)}
static_still {'animated-diagnostic-v1': ('failed', 0.0), 'game-capture-v1': ('failed', 0.0)}
textured_static {'animated-diagnostic-v1': ('failed', 0.0), 'game-capture-v1': ('failed', 0.0)}
blink_8x8 {'animated-diagnostic-v1': ('failed', 0.0), 'game-capture-v1': ('passed', 0.0515)}
full_animated_60 {'animated-diagnostic-v1': ('passed', 1.0), 'game-capture-v1': ('passed', 1.0)}
Ran 1 test in 168.995s  OK
```

  The real `blink_8x8` game ratio (0.0515) is only just above 0.05 on this 4 s clip. The deterministic mocked case is the regression that carries this behavior. The real case is corroboration only.

### Calibration evidence

The scripts are in `/home/brunner56/kp-live-20260922/r11-calibration/`:

- `calibrate_noise_floor.py`: lavfi → bgr0 rawvideo, which is x11grab's input format, → `libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p -threads 2`, the exact recorder settings. It then runs the production `probe_frame_content` and `probe_frame_pts` over `/proc/self/fd/N` with brew FFprobe 9.0.1. The clips are 12 s at 1024x768.
- `analyze_rows.py`: labels each frame fresh or duplicate by FFmpeg `fps` round=near slot semantics.
- `split_by_pict_type.py`: splits the values by I and P frame.

The outputs are `calibration-run3.txt`, `analysis-floor-1.2.txt`, and `split-by-pict-type.txt`. Each value below is the largest of Y, U, and V DIF.

| testsrc2 source | fresh min | duplicate max |
| --- | --- | --- |
| 60 FPS | 1.8907 | none |
| 30→60 | 3.0935 | 0.1797 |
| 20→60 | 3.8659 | 0.5374 |
| 6→60 | 4.1965 | 0.3311 |
| 59→60 | 1.8911 | 0.3048 |
| 15→60 | 3.9283 | 0.4800 |
| 45→60 | 2.2950 | 0.7596 |

Across all testsrc2 sources, 2,813 fresh frames had a minimum of 1.8907, and 2,220 duplicate frames had a maximum of 0.7596. The geometric midpoint is 1.198.

**Chosen floor: 1.2.** It is 1.58x above the largest duplicate and 1.58x below the smallest fresh frame. No duplicate is above the floor, and no fresh frame is at or below it.

By picture type, the duplicate maximum is 0.3311 for P frames (n=2,216) and 0.7596 for I frames (n=4, all at the keyframe index 250). Against P duplicates the margin is 3.6x. The I-frame outliers occur only at keyframes (keyint 250, so one per about 4.2 s). All of them together could add at most about 7 frames to a 30 s interval of about 1,800. That cannot lift a half-stale capture (about 50%) anywhere near 99%.

The floor is pattern-specific. Plain `testsrc` fresh frames measured as low as 0.1347. The docs state that the floor holds only for the diagnostic's full-frame testsrc2 pattern.

The reviewers' clips were re-probed through the adapted `content_ratio.py`. Output: `review-probes-r11-rerun/content_ratio.out`.

```text
static_flat     game failed 0.0     diag failed 0.0 (black + static)
static_pattern  game failed 0.0021  diag failed 0.0
static+noise    game failed 0.023   diag failed 0.0
half_dup        game passed 0.9958  diag failed 0.499   (above_floor_frames 299/599)
tenth_fresh     game passed 0.7996  diag failed 0.0981
anim60          game passed 1.0     diag passed 1.0
```

### R10-6: first-frame black check

`evaluate_content` (`display_backends.py:220-236`) applies the black check to the first frame at or after `interval_start`. Black frames before that are recorded only, in `content.startup` (the count before acceptance, the black count, and the capture's first frame). If no frame falls in the interval, the check fails. Regression: `test_black_check_uses_the_first_frame_at_the_acceptance_start`.

### R10-7: game policy limit

The game policy is unchanged. `docs/creative-runner.md` ("Content gate", with the table) states that the game ratio is an upper bound, that the 8x8 blink passes it, and that partial censoring is not ruled out.

## Requirement 2: a surviving FFprobe child is always recorded (Important)

- `_append_cleanup_record(..., survivor=True)` (`creative_accept.py:441-490`) skips the up-front log validation. It writes under the ledger lock. If the head moved during the probe, it appends to the current valid chain and sets `head_changed`. Only then does it call `_emit_head`, which prints to stderr before it validates the log.
- A log failure after the write raises `CommitmentLogFailed` (`:56`), which carries the new head.
- `_record_surviving_probe` (`:644`) always prints one `kpharness.ffprobe-survivor.v1` line to stderr. The line holds the PID, start, command, `recorded_in_ledger`, `failure_id`, head, and any log or ledger error. It then returns `CleanupLedgerChanged` with `survivor`.
- If the ledger cannot take the record (lock timeout, or a malformed or missing ledger), the function writes an exclusive `ffprobe-cleanup-unrecorded-*.json` sidecar (`:688`). `cleanup_state_clear` refuses while any sidecar exists (`:424-431`).
- The CLI prints `survivor` in its failure JSON (`:989`) and exits 1. A failed recovery log append also reports its head (`:966`).
- Regressions in `CleanupLedgerHeadTests`:
  - `test_log_deleted_during_probe_still_records_survivor_and_blocks`
  - `test_log_rotated_during_probe_still_records_survivor_and_blocks`, covering both a missing log and a fresh file at the old path
  - `test_log_hard_linked_during_probe_still_records_survivor_and_blocks`
  - `test_head_changed_during_probe_still_records_survivor_on_the_current_chain`
  - `test_ledger_lock_unavailable_during_probe_leaves_a_blocking_survivor_record`
  - Export: `ExportTests.test_unrecorded_survivor_sidecar_blocks_verify_and_export`

  Each asserts the stderr survivor line, a ledger failure, the gate blocked under both the launch head and the new head, and a refused re-accept.

## Requirement 3: signals during the diagnostic (Important)

- **Supervisor.**
  - `Dependencies.host().spawn_child` is `subprocess.Popen`.
  - The child starts with `start_new_session=True` and `pass_fds=(lock_fd, token_fd)` (`capture_diagnostic.py:879-884`).
  - `_SupervisorSignals` (`:736`) handles SIGINT, SIGHUP, and SIGTERM. Before launch it aborts to the `finally` block. After launch it forwards exactly one SIGINT.
  - `_wait_for_child` (`:767`) waits up to `CLEANUP_BUDGET_SECONDS` after a forward.
  - Only after the budget, or when the child ended without a passed ordered cleanup while owned processes are alive, does `_kill_owned_after_budget` (`:787`) act. It runs `killpg` on the child's own session group, then calls `kill_owned_identity` (pidfd, start re-checked, `:283`) for each identity in `diagnostic-owned.json`.
  - `diagnostic-result.json` records `interrupts`, `cleanup_budget` (seconds, components, exhausted, kill evidence), `owned_alive_after_child`, and `owned_survivors`, each with role, PID, and start.
- **Child.**
  - `run_child` (`:519`) installs `_ChildSignals` (`:482`): the first signal raises `DiagnosticInterrupted`, and later ones are recorded only (`cleaning`, `:565`).
  - `record_owned` (`:458`) writes each owned identity as soon as it exists: lease identities, client, and recorder FFmpeg.
- **Budget.** `CLEANUP_BUDGET_COMPONENTS` (`:72`) totals 1,442 s: recorder 1,398 (thread join 2, four xwininfo x 5, FFmpeg 15+5, two probes at `probe_deadline_seconds(3240)` = 678 s each), client 4, display 25, margin 15.
- **Run bound.** `CHILD_RUN_SECONDS` = pre-cleanup 134 s (`CHILD_PRE_CLEANUP_COMPONENTS`, `:82`) + 1,442 s = 1,576 s (`:93`). An uninterrupted run is never cut off by its own cleanup.
- **Regressions.** `InterruptTests` runs a real supervisor process, a real child running the real `run_child`, and real `sleep` grandchildren. There is no display.
  - SIGINT, SIGHUP, and repeated SIGINT each give ordered cleanup `recorder, source_process, display`, exactly one forwarded SIGINT, no survivors, and all owned processes dead.
  - Budget exhausted: only owned processes are killed, and a bystander `sleep` survives.
  - Survivor listed exactly.
  - Crashed child: its owned processes are killed.
  - Quiet run: no interrupt.
  - Run-deadline bound, and budget = sum of components.

## Minors

- **`--child` token and lock.**
  - `create_child_token` (`:409`) writes a 64-hex nonce into a pipe and closes the write end. Only the read fd is inherited, and its SHA-256 goes into the printed and logged commitments.
  - `verify_child_authority` (`:420`) requires a FIFO fd, a token whose digest equals both the config and `commitments.json`, and `canonical_lock_guard()` returning the configured `lock_fd`.
  - `main` returns 2 with a JSON refusal.
  - Tests: `ChildAuthorityTests`. `test_production_lock_guard_admits_only_the_configured_held_descriptor` uses the real guard on a temporary `KP_GAMESCOPE_REPO_ROOT` and never touches the canonical lock.
- **Preflight** (`:146-260`).
  - It refuses if `comm`, `stat`, or `cmdline` of any own-uid row is unreadable.
  - It detects targets by `comm`, the `/proc/PID/exe` basename, `argv[0]`, and the first script argument after a launcher (`WRAPPER_NAMES`, `:61`, skipping `VAR=value`).
  - It excludes this process and its ancestors (`_launch_chain`).
  - It never signals.
  - An unreadable `exe` is kept as evidence only (`:185`).
  - Tests: `PreflightRound11Tests`, which patches `os.kill` and `os.killpg` to raise.
- **Lock inheritance.**
  - `X11WindowRecorder(inherited_fds=...)` (`recording.py:611`) passes the descriptor to FFmpeg (`:1209`), both default probes (`:665-671`), and every xwininfo query (`_query`, `:673`).
  - The diagnostic child passes `inherited_fds=(lock_fd,)` and a lock-wrapped `run` to discovery, the verifier, and the recorder (`capture_diagnostic.py:525`, `:550`).
  - Creative Gamescope runs pass the held live-lock stream's fd (`creative.py:103`, `:242`).
  - Tests: `LockInheritanceTests` (two) and `test_gamescope_recorder_children_inherit_the_held_live_lock`.
- **FFprobe deadlines.**
  - `probe_deadline_seconds(frames)` = min(3,600, 30 + 0.2 x frames) (`recording.py:37-47`).
  - Recorder: the PTS probe is sized from terminal FFmpeg frames (`:761`) and the content probe from `len(pts)` (`:871`).
  - Acceptance sizes it from the PTS artifact `frame_count` (`creative_accept.py:871`).
  - Tests: `ProbeDeadlineTests`. A 10-minute clip finishes at 45 fake seconds under the scaled bound, times out under the old fixed 30 s, and the cap still holds.
  - Basis: a 12 s, 720-frame clip took 61 to 194 s for both probes combined at load 125 to 260 (`calibration-run3.txt` `probe_seconds`). The first calibration attempt died at the old fixed 30 s bound (`calibration-run1.txt`). So 0.2 s per frame is about 1.5x the worst measured per-frame cost.
- **Docs and log placement.**
  - `validate_commitment_log` (`creative_accept.py:313-360`) now compares the log and its parent chain by `(st_dev, st_ino)` with every inode in the run tree.
  - Tests: `CommitmentLogPlacementTests` (mocked stat). The real bind mount was rerun with p8 on the host: `bind_mount_alias_of_run_log: refused ... (it aliases the run tree by device and inode, for example a bind mount)`.
  - The supervisor's commitments append goes through `append_commitment_line`, which re-validates the log (`capture_diagnostic.py:864`; test `test_commitments_append_revalidates_the_log_before_the_single_launch`).
  - Docs: the trust root is the captured output, and the log is an anchor only when out of the writer's reach (`chattr +a`, another account, or off the host). Copy head lines out of band. The export example now uses `LAST_HEAD_THE_TOOL_PRINTED_FOR_THIS_RUN`, with a warning not to read it from `creative-run.json`. Bind-mount refusal and its limits are documented.

## Host preflight classification (read-only)

This reads `/proc` only. It took no lock, sent no signal, and did not call `preflight()`. Output: `review-probes-r11-rerun/host-preflight-classification.out`.

```text
rows 1215 own_uid_rows 785
forbidden [(2547167, 'wineserver', ...), (3970958, 'ffprobe', ...)]
unreadable [sd-pam, passless, kwin_wayland, polkit-kde-auth, ssh-agent, ksystemstats, ksgrd_network_h: all "exe: PermissionError"]
```

The `ffprobe` was this round's own `content_ratio` probe. The `wineserver` is the known foreign process, so preflight will refuse until it exits.

All the unreadable rows were exe-only kernel protections. That is why unreadable `exe` became evidence only. Under the final code, the unreadable list for these rows is empty, because only `comm`, `stat`, and `cmdline` failures refuse.

## Validation

```text
# container (no ffprobe on PATH)
PYTHONPATH=scripts/harness:tools python3 tools/kpharness_<suite>_test.py
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 137 OK (skipped=1: RealEncodeContentTests) | capture_diagnostic 35 OK
# host: host-cmd sh -c 'cd <worktree> && PYTHONPATH=scripts/harness python3 tools/kpharness_<suite>_test.py'  (Python 3.14.7)
creative 33 OK | gamescope_boot_repair 41 OK | gamescope_backend 137 OK (skipped=1) | capture_diagnostic 35 OK
```

Total: 246 in each environment (245 run, 1 skipped). The round-10 total was 208.

`py_compile` was run on the five changed modules and three test files: OK. A scoped `git diff --check` was run on the touched tracked files (`recording.py`, `creative.py`, `tools/kpharness_creative_test.py`, and `docs/creative-runner.md`): clean. A trailing-whitespace scan of the untracked touched files (`display_backends.py`, `creative_accept.py`, `capture_diagnostic.py`, the two untracked tests, and this report) found 0 lines.

### Reviewer probe reruns (adapted copies in `/home/brunner56/kp-live-20260922/review-probes-r11-rerun/`)

p2 (`p2.out`, container):
```text
inside_direct=refused
relative_inside=refused
dotdot_into_run=refused
via_dir_symlink_into_run=refused
lexical_dotdot_through_symlink=refused
outside_through_link_in_run=accepted
run_dir_itself=refused
outside_plain=accepted
run_given_via_symlink_log_inside=refused
log_vanished_during_probe: exit=1 stdout_error='canonical PTS re-probe cleanup failed: survived; surviving ffprobe pid=4242 start=12345; failure_id=c3b3cf497dc34f859cc601e26350e992; cleanup_ledger_sha256=16ae7846823ee80a4f967e85fae51fd201b12fbf8c009617f341bef61a695949; do not accept or export this run; retain this line, the ledger head, and the survivor PID/start out of band'
  survivor_mentioned_in_output=True
  r11_stderr_heads=1 stderr_survivor=[(4242, '12345', True, 'cleanup commitment log is missing; create it outside the run directory')]
  ledger_records_after=1 gate_clear_with_same_head=False
  reaccept_after_unrecorded_survivor: exit=1 ok=False
  r11_gate_clear_with_new_stderr_head=False
concurrent_same_head_appends=['ok', 'refused', 'refused', 'refused'] records=1 logged_failures=1 log_head_matches_file=True
```

p7 (`p7.out`, container):
```text
hardlink_during_probe: exit=1 error='canonical PTS re-probe cleanup failed: survived; surviving ffprobe pid=4242 start=12345; failure_id=3b58d1ff67324ff99144172d1ba1654b; cleanup_ledger_sha256=15b8688296e3c5fa8e9136b7a1386b369855f7c1f58d2889911c66d4473922a7; do not accept or export this run; retain this line, the ledger head, and the survivor PID/start out of band' records=1 clear=False pid_in_output=True
  r11_stderr_survivor_pid=True stderr_head_event=['acceptance_failure']
title_injection: status=verified size=[1024, 768] map=IsViewable border=0 origin=[0, 0]
reuse_while_pidfd_held='cleanup PID identity changed while pidfd held' signals=0 ledger_unchanged=True
```

p5 adapted to the real supervisor and a real child (`p5_sigint_cleanup_r11.py`, `p5.out`):
```text
cooperative ['SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGINT'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
cooperative ['SIGHUP']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGHUP'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
cooperative ['SIGTERM']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGTERM'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
cooperative ['SIGINT', 'SIGINT', 'SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=['recorder', 'source_process', 'display'] interrupts=['SIGINT', 'SIGINT', 'SIGINT'] budget_exhausted=False owned_alive_after=[] result_owned_survivors=[]
stubborn ['SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=[] interrupts=['SIGINT'] budget_exhausted=True owned_alive_after=[] result_owned_survivors=[]
survivor ['SIGINT']: parent_exit=1 parent_finally_ran=True child_cleanup_steps_completed=[] interrupts=['SIGINT'] budget_exhausted=True owned_alive_after=['client'] result_owned_survivors=[('client', 3919327)]
production_budget_seconds=1442.0 components={'recorder': 1398.0, 'source_process': 4, 'display': 25, 'evidence_margin': 15}
```

p9 (`p9.out`, host, scaled deadline):
```text
half_dup_30_to_60 animated-diagnostic-v1: failed ratio=0.5000 floor=1.2
half_dup_30_to_60 game-capture-v1: passed ratio=0.9958 floor=0.0
tenth_fresh_6_to_60 animated-diagnostic-v1: failed ratio=0.1000 floor=1.2
tenth_fresh_6_to_60 game-capture-v1: passed ratio=0.8000 floor=0.0
content_probe_35s_1024x768: 117.7s frames=2100 (scaled bound 450 s)
nproc=12 loadavg=(259.03759765625, 263.47314453125, 242.64013671875)
exit=0
```

content_ratio over the reviewers' clips: see the table under Requirement 1 (`content_ratio.out`).

p8, the real user-namespace bind mount on the host: `bind_mount_alias_of_run_log: refused ... (it aliases the run tree by device and inode, for example a bind mount)`.


## Residual proof boundary

- **The floor is calibrated on synthetic encodes, not on a Gamescope/mpv capture.** The mpv-to-x11grab path of the diagnostic has not been measured. The first real diagnostic's per-frame DIF values should be compared against the 1.2 floor before its verdict is trusted.
- **The game policy (floor 0, 5%) proves only that something moved.** This is documented.
- **The sidecar fallback depends on the run directory being writable.** If the sidecar write also fails, only the stderr survivor line remains. The CLI still exits 1.
- **A same-user writer can still delete the sidecar or the ledger.** The captured stderr head is the anchor, as documented.
- **Bind-mount detection is point-in-time.** It misses an alias created after the check, or a mount the process cannot stat.
- **`canonical_lock_guard` is trusted for the lock check.** The `--child` token stops accidental and replayed starts. A same-user process that builds its own pipe and commitments and holds the lock could still start a child, but it would already hold the lock.
- **The cleanup budget is long.** A Ctrl-C can wait up to 1,442 s, dominated by probe deadlines sized for this load.
- **`RealEncodeContentTests` is opt-in** and is not part of the default suite counts.
- **The one authorized diagnostic has still not run.** Nothing here authorizes it.

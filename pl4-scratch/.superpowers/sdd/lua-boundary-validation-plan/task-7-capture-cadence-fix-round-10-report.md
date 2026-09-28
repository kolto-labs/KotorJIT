# Task 7 capture cadence fix, round 10: writer report

Date: 2026-09-27. Sole writer. Brief: `/home/brunner56/kp-live-20260922/task7-capture-cadence-round-10-brief.md`.
Worktree: `.worktrees/lua-boundary-validation` (branch `codex/lua-boundary-validation`).

Safety: every edit is inside this worktree. There was no reset, stash,
staging, commit, or push. No Gamescope, Xwayland, X server, Wine, game, mpv,
FFmpeg, or FFprobe process was started. The only host commands were
`command -v` / `rpm -qf` tool-presence checks and the test suites. The
canonical `tmp/harness-locks/live-game.lock` was never opened. Test lock paths
are temporary files, and one test asserts that the real path is never opened.
The diagnostic driver is checked in and was never run. Unrelated dirty changes
are preserved. A byte comparison against a session-start copy shows changes only
in the files listed under "Files changed".

## Results

| Suite | Container | Host (`host-cmd`, Python 3.14.7) |
|---|---|---|
| `tools/kpharness_creative_test.py` | 32 OK | 32 OK |
| `tools/kpharness_gamescope_boot_repair_test.py` | 41 OK | 41 OK |
| `tools/kpharness_gamescope_backend_test.py` | 121 OK | 121 OK |
| `tools/kpharness_capture_diagnostic_test.py` (new) | 14 OK | 14 OK |
| **Total** | **208 OK** | **208 OK** |

Round 9 baseline: 173 on the host, and 171 of 173 in the container (R9-6, two
FFprobe-dependent tests). The backend suite now passes in a container with no
`ffprobe`.

## Part A: external ledger head (R9-1) and minors

Line references are to `scripts/harness/kpharness/creative_accept.py` unless
another file is named. The regressions are in
`tools/kpharness_gamescope_backend_test.py` (class `CleanupLedgerHeadTests`,
lines 1764-1985) unless another file is named.

| # | Requirement | Code | Regression |
|---|---|---|---|
| A1 | Empty ledger has a random per-run nonce. The ledger is `{"schema":2,"nonce":<32 hex>,"records":[]}`, and the chain starts at the nonce-bound launch head. | `_launch_bytes` :262, `initialize_cleanup_ledger` :359, genesis link in `_load_cleanup_ledger` :283-287 | `test_launch_heads_are_unique_per_run_and_emitted_before_use` :1764 |
| A2 | Every ledger change emits one JSON head line (`kind: kpharness.cleanup-ledger-head.v1`, event, run_dir, nonce, sequence, head, failure_id). It goes to stderr and is appended to an operator log that must already exist outside the run directory. The log may not be a symlink or hard link, and may not be inside the run directory. Events: `run_initialized`, `acceptance_failure`, `signal_error_reaped`, `recovery_resolution`. | `validate_commitment_log` :295, `_emit_head` :313, called from `initialize_cleanup_ledger` :359 and `_append_cleanup_record` :386 (the only mutation path) | `test_commitment_log_must_exist_outside_run_and_never_link` :1776; `test_recovery_cli_emits_resolution_head_and_catches_refusal` :1842 |
| A2 | Launch prints the initial head before any child runs. The log is validated before the run directory is created. | `creative.py:176-181` (validate before mkdir), `:205-212` (initialize right after mkdir, before session boot), `:261-262` (`cleanup_ledger_launch` in receipt), `--cleanup-commitment-log` at `:412` | `tools/kpharness_creative_test.py`: `test_gamescope_launch_emits_unique_initial_head_before_any_child` :440 (boot observes the logged head equal to the ledger bytes), `test_gamescope_launch_refuses_missing_or_inside_commitment_log_before_run_directory` :462 |
| A3 | A failure raises `CleanupLedgerChanged(ValueError)` carrying `failure_id`, `cleanup_ledger_sha256`, and the head line. The message includes both. The accept and recover CLIs catch it, print `{"ok":false,...,"failure_id","cleanup_ledger_sha256","cleanup_ledger_head"}`, and exit 1. | class :40, raise :774, `main` :812 (catch :850) | `test_failed_acceptance_cli_prints_failure_id_and_head_and_exits_nonzero` :1788 (drives `A.main([...])` end to end; probes resolved at call time) |
| A4 | Docs: pass the last head the tool printed or logged; never hash the file at review time. The stale per-failure-file and `--recover-cleanup` text is replaced. | `docs/creative-runner.md`: acceptance command and warning; ledger section ("The head must come from outside the run directory..."); recovery command with `--cleanup-commitment-log`; the old `ffprobe-cleanup-failure-ID.json` paragraph now describes the single chain | n/a (docs) |
| A5 | Rollback, reset, forged pair, and deletion regressions. Each takes the head only from captured CLI stderr and stdout, or from the commitment log, and never from the ledger file. | n/a | `test_rollback_to_fresh_empty_ledger_is_refused_with_logged_head` :1798 (fresh empty ledger, new nonce); `test_reset_to_exact_launch_bytes_is_refused_with_logged_head` :1809 (byte-exact launch bytes; shows only the stale launch head would pass); `test_forged_failure_resolution_pair_is_refused_with_logged_head` :1819 (rechained forged resolution passes under its own head, refused under the logged head); `test_deleted_ledger_is_refused_with_logged_head` :1837. Each runs the acceptance CLI with the logged head and asserts nonzero exit, `ok:false`, `cleanup_state_clear(logged head) is False`, and a receipt still pending. |

Minors:

| Requirement | Code | Regression |
|---|---|---|
| Exact integers (`type is int`) for ledger `schema`, record `schema` and `sequence`, both waits, failure `pid`, and resolution `pid`. A non-dict payload or unhashable `failure_id` gives a typed `ValueError`, never an `AttributeError`. Duplicate JSON keys are rejected (`object_pairs_hook`). Bytes must equal the canonical re-serialization. The only timestamp form is `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`; `Z` and forms without microseconds are refused. A resolution may not predate its failure. Loader `TypeError`, `KeyError`, `AttributeError`, and similar become `ValueError`. | `_UTC` :36, `_utc_now` :124, `_exact_int` :142, `_unique_object` :156, `_validate_failure_payload` :201, `_validate_cleanup_record` :226 (time order :254), `_load_cleanup_ledger` :266 (canonical :277, exception conversion) | `test_exact_schema_rejects_standins_nondicts_duplicates_noncanonical_and_time_order` :1874. 18 mutations, each against a fully resolved ledger and each with its own self-computed head. All give `cleanup_state_clear(...) is False` and a `ValueError` from the loader. |
| Appends take an exclusive `flock` on the run-directory descriptor (bounded 10 s) and recheck the caller-supplied head under the lock. A mismatch fails closed. | `_ledger_lock` :341, `_append_cleanup_record` :386 (recheck just before append) | `test_append_is_serialized_by_lock_and_refuses_stale_supplied_head` :1917 (held lock refuses; a second caller holding the same launch head is refused; one record is kept and the log head matches the file) |
| A surviving child with an empty start identity is recorded as `identity: "unavailable"` with the recovery text `UNRECOVERABLE_REQUIREMENT`. It can never be resolved, recovery refuses, and the gate stays blocked. | `_persist_probe_cleanup_failure` :550; resolution refused in `_validate_cleanup_record`; recovery refusal in `recover_cleanup` | `test_surviving_child_without_start_identity_blocks_permanently` :1945 |
| A different start at the recorded PID resolves as `original_exited_pid_reused` with `pidfd: not_needed`, `signal: not_sent`, and `wait: start_mismatch`. No pidfd is opened and nothing is signaled. | `recover_cleanup` :599 (resolution at :650); `_RESOLUTION_SHAPES` :194 | `test_cleanup_recovery_resolves_pid_reuse_without_signal_and_already_exited` :1282 (pidfd open and send mocks assert they are not called) |
| `boot_id` and `/proc/self/ns/pid` are stored in each failure. Recovery on another or unknown boot or namespace refuses before reading `/proc/<pid>`. | `_host_identity` :169; checks in `recover_cleanup` :624-626 | `test_recovery_refuses_other_boot_or_pid_namespace_before_concluding_absence` :1969 (identity reader never called; ledger unchanged) |
| Hermetic tests: `ffprobe=sys.executable` plus an injected content probe. | test file :2360, :2384 | Both pass in the container, which has no `ffprobe`. Before: the container baseline (session start) failed both with `configured ffprobe executable was not found`. |

## Part B: capture target correction

| # | Requirement | Code | Regression |
|---|---|---|---|
| B1 | Root capture is refused. `capture_target='root'` fails as `capture_target_rootless_root` when the lease's Xwayland argv has `-rootless`, or when it cannot be read (`xwayland_rootless` returns None). Any other Gamescope lease fails as `capture_target_unsupported`. Both happen before any geometry query or process. The Xvfb `X11Recorder` root path is unchanged. | `recording.py:386` (`xwayland_rootless`), `:1053-1066` | `test_root_capture_is_refused_on_rootless_or_unknown_xwayland` :2024 |
| B2 | Capture uses exact `-window_id` on the verified window. `xwininfo -id` and `-root` supply map state, absolute origin, size, border width, and root size. The `Xext/shm.c:639-654` conditions (viewable, inside screen, inside border) plus equality with the lease give `capture.geometry_precondition`. The geometry is re-read immediately before exec; a refusal gives `capture_geometry_precondition` and a change gives `capture_geometry_changed`, with no FFmpeg. Watch and stop checks compare against the frozen pre-exec read. `xwininfo` is added to `GAMESCOPE_TOOLS`. | `display_backends.py:132` (`geometry_precondition`), `:166` (`_geometry_evidence_matches` recomputes from recorded fields), `:26`; `recording.py:368` (parser), `:850` (`_geometry`), `:863` (`_binding`), `:1069-1083` (initial), `:1112` (`-window_id`), `:1143-1158` (pre-exec reread) | `test_geometry_precondition_refuses_each_shm_condition_before_exec` :2045 (unviewable, unmapped, four off-screen directions, size, border, root, foreign window, malformed, nonzero exit); `test_geometry_is_reread_immediately_before_exec_and_change_refuses` :2077 (the last two queries before `popen` are the xwininfo pair; drift refuses); `test_gamescope_recorder_captures_verified_window_after_geometry_precondition` :2411; `test_gamescope_recorder_refuses_offscreen_window_before_process_creation` :2437 |
| B3 | The MIT-SHM fallback gate and first-frame admission are kept unchanged. | `recording.py` `_admit_startup` and watch loop (untouched) | Existing `test_startup_fallback_is_typed_and_cleans_only_owned_recorder` and siblings still pass |
| B4 | Content gate before any cadence verdict. The configured FFprobe runs `-f lavfi -i movie=/proc/self/fd/N,signalstats` over an inherited master descriptor; only fd paths are accepted. `ffprobe-content.json` is hashed and bound to the master. `capture_content_black` fires when first-frame YMAX is at or below `black_luma_max` or when YMAX <= YMIN (zero variance). `capture_content_static` fires on zero changes or a changed ratio below the minimum; a frame is changed when Y, U, or V DIF > 0 inside the acceptance projection. A frame-count mismatch with canonical PTS gives `capture_content_failed`. Policies come from a fixed table: `animated-diagnostic-v1` (0.99) and `game-capture-v1` (0.05). The verifier compares the serialized policy to that table and recomputes from the artifact. | `display_backends.py:32` (table), `:191` (`evaluate_content`), `:223` (`_content_evidence_passed`), `:757` (required inside `_cadence_evidence_passed`); `recording.py:243` (shared bounded reader), `:319` (`probe_frame_content`), `:774-803`, `:815` (`_measure_content`) | `test_content_gate_rejects_black_and_static_before_cadence_can_pass` :2108; `test_content_probe_uses_fd_signalstats_and_bounded_reader` :2136 |
| B5 | Acceptance re-probes content over the same retained media and tool descriptors, inside the `ProbeCleanupError` block, and requires the exact rows. The visual review signs `content_artifact_sha256` and `geometry_precondition_sha256`, and `verify_acceptance` checks both. The export sidecar records `accepted_content_artifact_sha256` and `accepted_geometry_precondition_sha256`. Execution readiness now requires `_window_capture_matches`; `_root_capture_matches` is removed. | `creative_accept.py:747` (re-probe), `:783`, `:794-795`, `:524-527`; `creative_export.py:92-93`; `display_backends.py:763` | `test_execution_gate_requires_exact_window_geometry_and_bound_content` :2165 (14 mutations, including coherent re-hashed black, static, and short artifacts, forged origin, loosened or unknown policy, root form); `test_acceptance_reprobes_content_and_records_surviving_content_probe` :2211 (coherent substitution refused; field tamper with a recomputed acceptance digest refused; a surviving content-probe child is written to the ledger); export assertions in `test_reviewed_interval_includes_restoration_and_preserves_accepted_evidence` :448 |
| B6 | No CFR duplication and no silent non-SHM fallback. SHM BadMatch with verified geometry points to the PipeWire adapter. | Docs only | n/a |

## Part C: diagnostic driver (never run)

`scripts/harness/kpharness/capture_diagnostic.py`, tests in
`tools/kpharness_capture_diagnostic_test.py`. The CLI refuses without
`--authorized-single-run` (exit 2, no files created).

| Brief item | Code | Regression |
|---|---|---|
| Takes the canonical lock with the descriptor kept, and passes it to every child (`with_inherited_descriptor`, and `pass_fds` on the child spawn) | `acquire_lock`, `with_inherited_descriptor`, `supervise` | `test_supervisor_refuses_a_held_lock_before_preflight_snapshot_or_launch` :123; `test_supervisor_snapshots_then_prints_commitments_before_the_single_launch` :161 (one `pass_fds` entry); `test_child_orders_launch_markers_and_cleanup_and_passes_the_lock` :242 (mpv launched with fd 77) |
| Refuses on any `wineserver`, `swkotor`, `gamescope*`, `ffmpeg`, or `ffprobe` process not owned by this run, and writes `/proc` evidence (with `-auth` redacted) to `preflight.json` | `process_inventory`, `forbidden_processes`, `preflight` | `test_preflight_refuses_unowned_game_display_and_capture_processes_with_proc_evidence` :81; `test_supervisor_refuses_before_snapshot_or_launch_and_never_touches_canonical_lock` :104 |
| Fresh `create_snapshot` plus `verify_snapshot` with `DEFAULT_ENTRIES + ('kpharness.capture_diagnostic',)`; the child runs `-I -S -B` from the snapshot runtime | `SNAPSHOT_ENTRIES`, `supervise` | `test_real_snapshot_closure_contains_the_diagnostic_driver_and_verifies_source_equal` :152 (real copy into a temp directory); :161 (create, then verify, with those entries) |
| Pre-launch commitments: route SHA of `diagnostic-route.json`, FFprobe ELF SHA, launch ledger head. They are printed and appended to the commitment log before the single spawn. FFmpeg and FFprobe must each resolve to one native ELF; wrapper scripts are refused. | `route_document`, `native_elf_identity`, `supervise` | :161 (spawn sees the commitments line already printed); `test_wrapper_script_or_missing_capture_tool_is_refused_before_launch` :198 |
| Private lease; `mpv` `testsrc2` at 60 FPS with a fixed `--title`; single owned-window discovery (10 s); Part B recorder with `/usr/bin/ffmpeg`, brew ffprobe, and `animated-diagnostic-v1`; `pattern_start`, then 30 s, then `pattern_end` | `client_command`, `run_child` | :242 (sleeps `[3.0, 30.0, 1.0]`, exact marker lines, recorder kwargs) |
| Cleanup order recorder, client, display, with every step attempted; bounded client stop (SIGINT, 2 s, SIGKILL, 2 s); X0/X94/X100 socket and lock identities checked before and after | `ordered_cleanup`, `stop_client`, `protected_displays` | `test_ordered_cleanup_attempts_every_component_in_recorder_client_display_order` :213; `test_client_stop_interrupts_then_kills_only_the_owned_process_with_bounded_waits` :230; `test_child_failure_still_cleans_up_in_order_and_retains_error` :288 |
| Every criterion is evaluated and written to `diagnostic-result.json`. There are 18 criteria, including the brief's list plus `cadence_evidence_recomputed`, `acceptance_interval_matches_route`, `no_owned_survivors`, `snapshot_unchanged`, and `no_driver_error`. The ledger criterion uses the head the driver emitted, never `None`. The media SHA is printed. No retry; nonzero exit on any failure. | `evaluate`, `CRITERIA`, `supervise` | `test_complete_observation_passes_every_criterion` :336; `test_each_criterion_fails_independently` :341 (one mutation per criterion; each flips its own criterion and the verdict) |

## Rulings (fail-closed choices the brief did not settle)

1. The commitment log must already exist. "Missing" is refused rather than
   created, as is a symlink, a hard link (`st_nlink != 1`), or a path inside the
   run directory. Operators create the empty file first.
2. Head lines go to stderr, so each CLI's single-line stdout JSON contract is
   kept. The accept and recover CLIs also put the head on their stdout failure
   JSON. Commitment-log writes are one `O_APPEND` write per line, with no `flock`.
   Locking the log could deadlock on a leaked descriptor, which a round-10 test
   run showed.
3. The ledger schema moved to 2. Schema-1 ledgers from older runs are refused.
4. `xwininfo` "Absolute upper-left" is treated as the outer corner, including
   the border. That reading was not verified from source here. To stay
   fail-closed, `border_width == 0` is required, so the corner and the content
   origin coincide.
5. Root capture is refused on every Gamescope lease: rootless and unknown give
   `capture_target_rootless_root`, anything else gives
   `capture_target_unsupported`. `_root_capture_matches` was removed because
   no other backend used it; the Xvfb `X11Recorder` root path is untouched.
6. Distinct-frame measurement uses signalstats Y/U/VDIF > 0 against the
   previous decoded frame. The brief offered MD5 only as an example. This
   keeps the single configured FFprobe and the descriptor transport, and
   avoids adding FFmpeg as a second probe tool. A tiny difference that prints
   as 0.000000 counts as unchanged, which fails closed.
7. The game policy minimum is 5%. Zero changes always fail, whatever the
   policy.
8. A surviving child with no start identity stays permanently unresolved,
   even when it was reaped.
9. A start change while the pidfd is held still refuses
   (`test_pidfd_recovery_rechecks_identity_after_open_before_signal`). The
   reuse resolution applies only to the pre-pidfd read.
10. The diagnostic requires `--authorized-single-run`.
    `acceptance_interval_matches_route` also requires the acceptance pair to
    be `pattern_start`/`pattern_end` and its span to be at least 90% of 30 s.

## Red-first evidence

- Part A: after the fixture and regression edits, before implementation:
  `Ran 114 tests ... FAILED (failures=2, errors=58)` (`/tmp/r10-red-A-backend.txt`).
  The new tests failed because the API did not exist (`commitment_log`
  keyword, `CleanupLedgerChanged`, `_host_identity`). The pre-fix code had no
  head source at all, which is the R9-1 defect. The behavioural red for
  rollback is the round-9 reviewers' probe (`rollback_accepted=True`), not
  reproduced here. Creative: `Ran 32 tests ... FAILED (errors=5)`
  (`TypeError: initialize_cleanup_ledger() missing 1 required keyword-only
  argument: 'commitment_log'`).
- Part B: `Ran 121 tests ... FAILED (failures=27, errors=50)`
  (`/tmp/r10-red-B-backend.txt`).
- Part C: `ImportError: cannot import name 'capture_diagnostic'`
  (`/tmp/r10-red-C.txt`).

## Commands and outputs

```text
$ cd <worktree>; for s in creative gamescope_boot_repair gamescope_backend capture_diagnostic; do
    PYTHONPATH=scripts/harness python3 tools/kpharness_${s}_test.py; done        # container
Ran 32 tests in 1.983s   OK
Ran 41 tests in 0.453s   OK
Ran 121 tests in 17.022s OK
Ran 14 tests in 3.345s   OK

$ /home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && for s in ...; do
    PYTHONPATH=scripts/harness python3 tools/kpharness_${s}_test.py; done'         # host, Python 3.14.7
Ran 32 tests in 0.471s   OK
Ran 41 tests in 0.557s   OK
Ran 121 tests in 4.854s  OK
Ran 14 tests in 1.644s   OK

$ python3 -m py_compile scripts/harness/kpharness/{creative_accept,creative_export,creative,recording,display_backends,capture_diagnostic}.py \
    tools/kpharness_{gamescope_backend,capture_diagnostic,creative}_test.py
py_compile-ok

$ git diff --check -- scripts/harness/kpharness/creative.py scripts/harness/kpharness/recording.py \
    docs/creative-runner.md tools/kpharness_creative_test.py
(no output) exit=0

# untracked touched files: trailing whitespace / leading tabs / final newline
creative_accept.py trailing=0 leading_tabs=0 final_newline=yes
creative_export.py trailing=0 leading_tabs=0 final_newline=yes
display_backends.py trailing=0 leading_tabs=0 final_newline=yes
capture_diagnostic.py trailing=0 leading_tabs=0 final_newline=yes
tools/kpharness_gamescope_backend_test.py trailing=0 leading_tabs=0 final_newline=yes
tools/kpharness_capture_diagnostic_test.py trailing=0 leading_tabs=0 final_newline=yes

$ host-cmd sh -c 'command -v xwininfo xdotool mpv gamescope /usr/bin/ffmpeg /home/linuxbrew/.linuxbrew/bin/ffprobe /usr/bin/python3.14; rpm -qf /usr/bin/xwininfo'
all present; xwininfo-1.1.6-4.fc44.x86_64
```

## Files changed

Tracked (modified): `scripts/harness/kpharness/creative.py`,
`scripts/harness/kpharness/recording.py`, `docs/creative-runner.md`,
`tools/kpharness_creative_test.py`.

Untracked (modified): `scripts/harness/kpharness/creative_accept.py`,
`scripts/harness/kpharness/creative_export.py`,
`scripts/harness/kpharness/display_backends.py`,
`tools/kpharness_gamescope_backend_test.py`.

New: `scripts/harness/kpharness/capture_diagnostic.py`,
`tools/kpharness_capture_diagnostic_test.py`, this report.

## Residual proof boundary (`unverified`)

- No live run. Nothing proves that Gamescope child-window ShmGetImage keeps
  MIT-SHM, gives non-black frames, or reaches 60 FPS cadence under verified
  0,0 / in-screen geometry. The diagnostic exists to settle that.
- `xwininfo` output format and the outer-corner reading of "Absolute
  upper-left" come from the fixture shape. The border-0 ruling covers either
  reading.
- Not run: brew FFprobe `lavfi` / `movie` / `signalstats` availability, the tag
  names and print precision of the `*DIF` tags, and `/proc/self/fd/N` fd-exec
  of that FFprobe. The same applies to `movie=` decoding exactly the same
  frame count as `ffprobe -show_entries frame=best_effort_timestamp_time`. A
  mismatch fails closed as `capture_content_failed`.
- Not run: `-window_id` hex parsing by FFmpeg 8.1.2, `mpv` `_NET_WM_PID`, a
  single window, and 0,0 geometry under headless Gamescope.
- Recovery host identity (`boot_id`, pid-ns) was checked only with injected
  readers, and in one shared namespace (container and host share
  `pid:[4026531836]` per round 9).
- The first-frame black check will also fail a game capture whose first
  recorded frame is really black. That is by the brief's rule, and its effect
  on K1 is untested.
- The commitment log only anchors the head if the operator keeps it out of
  reach of the same-user attacker. That is an operational boundary.
- Rounds 0-9 findings are covered only by the regressions that still pass;
  they were not re-probed.

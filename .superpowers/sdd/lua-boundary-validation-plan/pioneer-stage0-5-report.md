# Pioneer playback Stage 0 + Stage 5 report (host-only)

Date: 2026-09-27. Plan: /home/brunner56/kp-live-20260922/fanout-pioneer-devtools-plan.md sections 1 and 3.
Worktree: .worktrees/lua-boundary-validation. Nothing staged, committed or pushed. No Wine, game,
Gamescope or FFmpeg. tmp/harness-locks/live-game.lock not touched.

## Red first

The new suite was written before any fix. First run on the draft (container):
`Ran 17 tests ... FAILED (failures=9, errors=5)`. The three that already passed are guards for
existing behavior: ordered steps/one connection, stale descriptor, no retry. Selected red output:

    FAIL: test_invalid_arguments_rejected_before_mutation  'uncertain' != 'idle'
      last_error: 'PlaybackError: route needs an initial native load/checkpoint or verify-current predicate'
    FAIL: test_status_during_wait_then_stop_is_clean_execution_stop  'stopped' != 'execution_stopped'
    FAIL: test_engine_lock_lives_in_private_state_dir  /tmp/kpharness-playback-ab3b640d26a0cb59/localhost-42801
    FAIL: test_cli_step_without_owner_takes_engine_guard  0 != 1 : execution: game speed 16x
    FAIL: test_cli_step_commit_route_through_owner  pioneer step: another Pioneer command owns this route
    FAIL: test_cli_play_status_stop_end_to_end  usage: kpharness pioneer [-h] {init,step,commit,discard,status}
    ERROR: test_second_owner_for_other_route_is_refused  PioneerError: another Pioneer command owns this route
    ERROR: test_speed_restored_after_failed_step  KeyError: 'speed_after_job'
    ERROR: test_step_and_commit_route_through_attached_owner  no attribute 'author'

## Per requirement

Line numbers are for the files as they stand now. Tests are in tools/kpharness_playback_test.py.

| Requirement | Fix (file:line) | Test |
|---|---|---|
| Defect 1: a cancelled wait/expect/sleep no longer sets world_uncertain | playback.py:138 `_cancel_is_read_only`, :340 | test_status_during_wait_then_stop_is_clean_execution_stop (:261), test_speed_restored_after_stop_during_fastforward (:491) |
| Defect 2: validation errors before any engine write leave the owner idle, not uncertain | playback.py:322 (`mutation_started` set only before the speed policy), :424-429 | test_invalid_arguments_rejected_before_mutation (:327) |
| Defect 3: effective_speed is published only from readback | playback.py:325-330 | test_fastforward_reads_back_before_publishing_and_restores (:454), test_acknowledged_but_not_applied_speed_is_not_published (:470) |
| Defect 4: `pioneer step`/`commit` without an owner take engine_guard | cli.py:227, :255 (status: :290, skips its live read if the lock is held) | test_cli_step_without_owner_takes_engine_guard (:429) |
| Defect 5: lifetime route lock; step/commit/discard go through the owner | pioneer.py:253 `execute_pending_locked`, :300 `commit_pending_locked`; playback.py:366 author_step, :385 author_commit, :405 author_discard, :213 reload_route (rewrites descriptor hash), :572 `author()`; cli.py:219, :249, :267 | test_step_and_commit_route_through_attached_owner (:376), test_cli_step_commit_route_through_owner (:439) |
| Defect 6: engine lock moved to a user-private state dir | playback.py:71 state_root ($XDG_STATE_HOME or ~/.local/state, %LOCALAPPDATA% on Windows)/kpharness/playback-locks, :81 0700 check, :97 engine_guard | test_engine_lock_lives_in_private_state_dir (:364) |
| One engine connection | playback.py:473 serve holds the engine lock and route lock, then opens one Channel | test_one_engine_connection_and_ordered_steps (:245) |
| Ordered steps | playback.py execute loop | test_one_engine_connection_and_ordered_steps (:245) |
| Status during wait | control socket; `active_step` published before run_step | test_status_during_wait_then_stop_is_clean_execution_stop (:261) |
| Stop during wait | cancel_event, then `execution_stopped` with detached=true | same, plus :491 |
| Speed restored after failure | attached_execution compare-and-restore (scenario.py, unchanged); `speed_after_job` readback at playback.py:361 | test_speed_restored_after_failed_step (:283) |
| Stale descriptor rejected, never replaced | control() hash/port/token checks; start() never overwrites | test_stale_descriptor_rejected_without_spawning (:294) |
| Second owner on another route refused | start() pre-check at playback.py:520 plus the owner's own engine_guard | test_second_owner_for_other_route_is_refused (:318) |
| Invalid args rejected before mutation | playback.py:114 validate_speed, :125, command() | test_invalid_arguments_rejected_before_mutation (:327) |
| No retry | wait_job (:559) only polls; failed step is not reissued; a busy/uncertain owner refuses new jobs | test_failed_step_is_not_retried (:353) |
| CLI end to end | cli.py:317 attach, :328 play/fastforward, :355 stop, :478 parsers, :495 stop parser | test_cli_play_status_stop_end_to_end (:406) |
| Stage 5 bounds (0,16] | playback.py:114; `play` refuses a speed argument | test_invalid_arguments_rejected_before_mutation (0, 16.5, -1, True, "4"), test_speed_bounds_accept_upper_edge (:502), CLI `--speed 17` in :406 |
| Stage 5 restore on finish/stop/failure | attached_execution (scenario.py) + `speed_after_job` | :454 finish, :491 stop, :283 failure |
| Stage 5 explicit speed step keeps its setting | playback.py:351 `ownership['retain']` | test_explicit_speed_step_keeps_its_setting (:483) |
| Stage 5 readback before effective_speed | playback.py:325-330; a mismatch issues no step and reports observed_speed | :454 checks the engine log order: speed set, then `kp.game_speed()`, then the first step. :470 covers an engine that acks 8 but reads back 3 |
| Label "configured multiplier" | playback.py:39 SPEED_LABEL, in every state; cli help; docs | :454, :406 |
| No world-pause claim | `world_paused=False` fixed at playback.py:173; state `execution_stopped`; stop note in cli.py:363; docs | :261 asserts world_paused is false; :406 asserts "does not pause" |

"Pause" in the Stage 5 restore list has no operation in this stage. Stop is the only interruption,
and it restores the speed (:491). Pause wiring is Stage 2.

## Commands and output

Final run, container (Python 3.12.3):

    == PYTHONPATH=scripts/harness python3 tools/kpharness_playback_test.py
    rc=0
    Ran 17 tests in 11.117s
    OK
    == PYTHONPATH=scripts/harness python3 tools/kpharness_pioneer_policy_test.py
    rc=0
    Ran 21 tests in 0.191s
    OK
    == PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
    rc=0
    Ran 32 tests in 0.791s
    OK
    == PYTHONPATH=scripts/harness python3 tools/kpharness_offline_test.py
    rc=0
    Ran 150 tests in 48.287s
    OK

Final run, host (`/home/brunner56/.local/bin/host-cmd sh -c 'cd <worktree> && ...'`, Python 3.14.7):

    == PYTHONPATH=scripts/harness python3 tools/kpharness_playback_test.py
    rc=0
    Ran 17 tests in 14.130s
    OK
    == PYTHONPATH=scripts/harness python3 tools/kpharness_pioneer_policy_test.py
    rc=0
    Ran 21 tests in 0.116s
    OK
    == PYTHONPATH=scripts/harness python3 tools/kpharness_creative_test.py
    rc=0
    Ran 32 tests in 0.858s
    OK
    == PYTHONPATH=scripts/harness python3 tools/kpharness_offline_test.py
    rc=0
    Ran 150 tests in 51.534s
    OK

The playback suite also passed three more times in a row in each environment.

A race showed up once on the host before the final runs. It was not seen in the container.
`status()` polled while the owner was exiting and got `ConnectionResetError`. Fix at
playback.py:549: fall back to the journal only when the descriptor is already gone, because the
owner writes its final journal, then removes the descriptor, then exits. Otherwise the error is
raised again.

Static checks:

    python3 -m py_compile scripts/harness/kpharness/playback.py scripts/harness/kpharness/cli.py \
      scripts/harness/kpharness/pioneer.py tools/kpharness_playback_test.py   -> compile_ok
    git diff --check -- scripts/harness/kpharness/cli.py scripts/harness/kpharness/pioneer.py \
      docs/pioneer-authoring.md   -> rc=0
    grep -nE ' +$' playback.py kpharness_playback_test.py (untracked)   -> no matches

After the runs, pgrep found no leftover `kpharness.playback --serve` or synthetic engine processes
in either environment.

## Files changed

- scripts/harness/kpharness/playback.py (untracked draft, reworked)
- scripts/harness/kpharness/cli.py (pioneer attach/play/fastforward/stop; engine_guard; owner routing)
- scripts/harness/kpharness/pioneer.py (execute/commit split into `*_locked` bodies with the same public signatures; lock message mentions the owner and keeps the "owns this route" phrase that the existing tests match)
- tools/kpharness_playback_test.py (new, 17 tests)
- docs/pioneer-authoring.md (Playback owner and Speed sections)

scenario.py and waits.py were not edited. kpharness_creative_test.py was rerun anyway, and passes.

## Residual proof boundary

- All proof comes from a synthetic engine. Live proof is still pending: attached K1
  `pioneer play --until 3`, `status`, `stop`, speed readback restored, game PID alive, state
  `execution_stopped`.
- The readback is `kp.game_speed()`, a configured multiplier. It does not measure simulation rate.
- If the readback does not match the request, attached_execution sees current != requested and
  keeps the value (compare-and-restore policy). The prior speed is not restored in that case. The
  job reports observed_speed and marks the world uncertain.
- Authoring `step` jobs through the owner run without the owner's cancel event. `stop` waits for
  that step to finish.
- tools/kpharness_pioneer_policy_test.py calls `cli.main(['pioneer','step',...])` with port 12345.
  That call now takes engine_guard, which leaves an empty `localhost-12345.lock` under the real
  ~/.local/state/kpharness/playback-locks (0700). This is harmless, but it is a side effect of a
  test I was not allowed to edit.
- The owner Popen in start() is detached and never waited on. unittest prints ResourceWarning
  lines for it. This is not a failure.

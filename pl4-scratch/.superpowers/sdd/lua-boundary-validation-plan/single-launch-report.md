# Single-launch mode (G-RETRY) report

Date: 2026-09-27. Sole writer. Resumed from a rate-limited writer; its session.py
diff and test file were inspected, re-verified and kept unchanged.

Finding closed: `/home/brunner56/kp-live-20260922/live-runbook-20260927.md` G-RETRY
(`BOOT_ATTEMPTS = 5`; `_launch_and_connect` relaunched after `crash` / `boot timeout`).

No Wine, game, Xvfb or live-game lock was touched. No git writes.

## What changed

`scripts/harness/kpharness/session.py` (G-RETRY hunks only; the
`capture_owned_game_window` hunk in the same diff belongs to another writer and
was left alone):

- `MAX_BOOT_ATTEMPTS_ENV = "KP_MAX_BOOT_ATTEMPTS"`, `BOOT_ATTEMPTS_EVIDENCE = "boot-attempts.json"`.
- `InvalidBootAttempts(ValueError)` and `resolve_max_boot_attempts(value=None) -> (n, source)`.
  Keyword beats env; env beats default. Accepts 1..5 only. Refuses bools, floats,
  strings as the keyword, and any env value that is not plain ASCII digits
  (empty, spaces, `1.0`, `0x2`, `5 ` all refused, never silently defaulted).
- `GameSession(..., max_boot_attempts=None)` resolves in `__init__` before any
  lock, stage or display work. Stores `max_boot_attempts`, `max_boot_attempts_source`.
- `_launch_and_connect` loops `range(1, budget + 1)`. It re-validates the budget
  (a mutated attribute cannot widen it or give zero launches). With budget 1 a
  `crash` / `boot timeout` is re-raised after exactly one launch, with no
  `_kill_game` and no settle. `refusal` and other reasons are still never retried.
- Every launch is recorded before it starts in `run_dir/boot-attempts.json`
  (atomic tmp + `os.replace`). Fields: `max_boot_attempts`, `max_boot_attempts_source`,
  `launch_count`, `outcome` (`launching` / `retrying` / `failed` / `channel`), and
  `attempts[]` with `attempt`, `outcome`, `reason`, `detail`, `started`, `ended`.
  Non-`BootFailure` exceptions (OSError, KeyboardInterrupt) are also recorded.
  `teardown` keeps `run_dir`, so the receipt and `wine.log` / `game.log` survive a failed boot.
- The raised exception is the original typed failure (`BootFailure` with its
  `reason`), carrying `launch_count`, `launch_attempts`, `max_boot_attempts` and `evidence_path`.
- `SessionInfo` / `session.json` gain `max_boot_attempts` and `launch_count` on success.
- The default is unchanged: `BOOT_ATTEMPTS = 5`, same retry classes and settle.

`tools/kpharness_single_launch_test.py` (new, 18 tests, launch/connect stubbed).

Only one launch site exists. `grep -rn "\.launch()\|_launch_and_connect\|\.boot(" scripts/ tools/`
(non-test) finds `self.launch()` only at `session.py:1471`, inside the budgeted loop.
The other hits are `boot()` / `__enter__` (:1599, :1687), `creative_wine.py:116` / `:226`,
`creative.py:271`, and `cli.py:102` / `:191`, and all of them route through `_launch_and_connect`.
The shell `seq` loops in `drive_k1_console.sh:170` and `ui_wait.sh:57` retry input, not launches.

## Verification

| Check | Command | Result |
|---|---|---|
| Red first | new test (the first 17 tests) run against `git show HEAD:scripts/harness/kpharness/session.py` in a temp copy | `FAILED (failures=3, errors=29)`, Ran 17 |
| New test, container (Python 3.12.3, `/run/.containerenv` present) | `python3 tools/kpharness_single_launch_test.py` | Ran 18, OK |
| Offline suite, container | `python3 tools/kpharness_offline_test.py` | Ran 150, OK (96.2 s) |
| New test, host (Python 3.14.7, no `/run/.containerenv`) | `host-cmd bash -c '... python3 tools/kpharness_single_launch_test.py'` | Ran 18, OK |
| Offline suite, host | `host-cmd bash -c '... python3 tools/kpharness_offline_test.py'` | Ran 150, OK (70.1 s) |

Suites ran one at a time. The 18th test (`test_unwritable_receipt_does_not_mask_boot_failure`)
only changed the test file, so it was re-run on its own in both places. The 150-test suite did not need a re-run.

## Follow-up edits needed outside my allowed files

Today an acceptance run is single-launch only if the operator exports
`KP_MAX_BOOT_ATTEMPTS=1`. All callers inherit it, because the creative sessions
subclass `GameSession` without their own `__init__`. To force it rather than
rely on the environment:

1. `cli.py` `boot_args` (~:421): add `--max-boot-attempts` (`type=int`, choices 1..5,
   default None). Pass `max_boot_attempts=a.max_boot_attempts` to both
   `GameSession(...)` calls (`cmd_boot` :98, the scenario path :187).
2. `cli.py` :98 and :187: the constructor sits outside the `try`, and the `except`
   lists only `BootFailure, LockHeld, FileNotFoundError`. An invalid env value
   therefore exits with a traceback (still nonzero, still no launch). Catch
   `InvalidBootAttempts` and return 2 with a one-line message.
3. `cli.py` failure print (:104 and the scenario twin): print
   `launch_count` / `max_boot_attempts` / `evidence_path` from the exception.
4. `creative.py` :271 and `creative_wine.py` (`LinuxWineCreativeSession`,
   `LinuxWineGamescopeCreativeSession`, whose `boot` calls `_launch_and_connect`
   at :226): acceptance recordings should construct with `max_boot_attempts=1`
   explicitly. They should also copy `run_dir/boot-attempts.json` (or its path)
   into the cleanup / run receipt they already persist.
5. `playback.py`, `pioneer.py`, `capture_diagnostic.py`, `recording.py`,
   `display_backends.py`: no `GameSession(` or boot retry loop found by grep. They
   should record `launch_count` from `session.json` in their receipts, and refuse
   acceptance status when it is greater than 1.
6. The legacy shell scripts `live_session.sh`, `drive_k1_console.sh`, `measure_boot.sh` and
   `spike_headless_k1.sh` launch the game themselves, without `GameSession`, so the budget
   does not cover them. Acceptance runs must not use them, or each needs its own one-launch receipt.
7. Live runbook preflight: require `KP_MAX_BOOT_ATTEMPTS=1` for items 1-9 until
   follow-ups 1-4 land, and check `boot-attempts.json` shows `launch_count: 1` after each run.

## Grill me

1. **Could a write failure of the receipt mask the boot error?** No. `_write_boot_attempts`
   catches `OSError`, logs it and returns None. The original `BootFailure` still propagates,
   with `evidence_path=None` and `launch_count=1`. Referent: `test_unwritable_receipt_does_not_mask_boot_failure`
   (run_dir points at a regular file), 18 OK in the container and on the host. Not covered: a
   full disk partway through a write. The tmp + `os.replace` should leave the previous receipt intact (`unverified`).
2. **Is there a reason the CLI refusal of a bad env value is not tested end to end?** `cli.py` is out of scope.
   A code read settles the behavior: `GameSession(` at `cli.py:98` and `:187` sits outside the `try`, so
   `InvalidBootAttempts` escapes as a traceback. It is still nonzero and still happens before any launch,
   because `__init__` resolves first (`test_constructor_refuses_invalid_env`). Follow-up 2 fixes the message.
   Do not settle this by running the CLI: if the refusal ever regressed, that command would boot the game.
3. **How come an acceptance run is not forced to single-launch yet?** The CLI and creative runners are out of my
   file scope. Today it relies on `KP_MAX_BOOT_ATTEMPTS=1` in the environment. Referent: grep finds no
   `max_boot_attempts` in `cli.py` / `creative*.py`. See follow-ups 1 and 4.
4. **Why does `session.json` not carry the evidence on failure?** It is written only after a successful boot and
   unlinked at teardown. The durable receipt is `run_dir/boot-attempts.json`, which teardown keeps. Referent:
   `boot()` calls `write_session_info()` after `_launch_and_connect` (`session.py:1599-1603`). Teardown unlinks
   only `session_info_path` (:1678), and session.py has no `rmtree(run_dir)` (grep).
5. **Did the default path change?** No. Referent: `test_default_keeps_five_attempts` (5 launches, 4 kills),
   `test_refusal_is_still_not_retried_under_default`, and the existing boot-retry tests in
   `kpharness_offline_test.py` (~:2453-2466) all pass inside the 150 OK.

Open question for a reviewer: the legacy direct-launch shell scripts (follow-up 6). One check settles it:
confirm that no runbook item 1-9 invokes them.

## Follow-up (2026-09-27, after the PARTIAL review)

Review: `/home/brunner56/kp-live-20260922/single-launch-review.md` (Single-launch: PARTIAL).
Sole writer. No Wine, game, Xvfb or live-game lock. No git writes. All test runs used `python3 -B`.

### What changed

`scripts/harness/kpharness/creative.py`
- `boot_budget()` (:150) validates `KP_MAX_BOOT_ATTEMPTS` even though the explicit budget wins. It returns
  1 (`default_single`) unless `--dev-max-boot-attempts N` is given (`dev_override`).
- It is called at :199, straight after `adapter_factory`. That is before `validate_commitment_log` (:228),
  `live_lock` (:246), `run_dir.mkdir`, the ledger head, the stage/prefix claims and the recorder. This closes the review's
  "does not hold on the creative path" claim.
- `session_type(..., max_boot_attempts=budget['max_boot_attempts'])` (:298). Both creative sessions pass
  `**kwargs` to `GameSession.__init__`.
- `boot_evidence()` (:167) runs in the `finally` after teardown (:394). It copies `boot-attempts.json` into
  `receipt['boot_attempts']`: the artifact hash, the parsed record, `launch_count`, `acceptance_eligible` and `refusal`.
  A run is eligible only if all of these hold:
  - the file exists and is a JSON object
  - the budget is `default_single` 1
  - the record says `max_boot_attempts == 1`
  - `launch_count` is the int 1
- `ok` now also requires eligibility (:425). On Gamescope, after `schema2_receipt`, an ineligible run gets
  `ok=false`, `acceptance_ready=false` and `visual_review.status='refused_boot_budget'` (:446). `creative_accept.accept()`
  then refuses it with "run is not pending visual acceptance".
- New parser flag `--dev-max-boot-attempts N` (:465). An invalid env or flag is a `ValueError`, so `main()` prints
  the one-line preflight JSON and exits 2.

`scripts/harness/kpharness/cli.py`
- `--max-boot-attempts N` is added to `boot_args` (:460). That covers `boot` and `run`, the only two users (`grep -n "boot_args(" cli.py`).
- `_boot_budget_error` (:96) validates the env and then the flag. `cmd_boot` (:117) and `cmd_run` (:204) call it
  before `GameSession` and before scenario lookup. On a bad value they print one line to stderr, exit 3 (the usage-error code in the docstring) and launch nothing.
- The flag reaches `GameSession(max_boot_attempts=...)` (:124, :218). With no flag it passes `None`, so the session resolves the env itself.
- The boot failure line now appends `launch_count`, `max_boot_attempts` and `evidence_path` (`_boot_failed`, :108).

`tools/kpharness_creative_test.py`
- The fake `Session` now writes `boot-attempts.json`, standing in for `GameSession._launch_and_connect`, and captures the
  `max_boot_attempts` kwarg.
- 6 new tests: default budget 1 plus embedded evidence, relaunch refused, missing evidence refused,
  dev override never acceptance, Gamescope pending when single, and Gamescope `refused_boot_budget` with `accept()` refusing.

`tools/kpharness_single_launch_test.py`
- +10 tests. Creative refusal before any claim covers env 0/6/''/one on both backends, a bad env with a valid dev flag, and dev flags 0/6/-1.
  Each asserts that `live_lock`, `Path.mkdir`, `validate_commitment_log`, `initialize_cleanup_ledger`, the session,
  the recorder and the claim were never called.
- The other new tests cover `boot_budget` resolution, the `boot_evidence` judgement table, the CLI flag parse, a bad env or flag (one line, rc 3, `GameSession`
  never called), the flag reaching the session with the failure line naming the evidence, and no-flag leaving the env to the session.

`/home/brunner56/kp-live-20260922/live-runbook-20260927.md` (private, edited in place)
- G-RETRY now names `KP_MAX_BOOT_ATTEMPTS` everywhere. The old name appears only in a warning that it is ignored.
- It adds preconditions: export and echo the variable; build a new snapshot per Gamescope item; the command `grep -c KP_MAX_BOOT_ATTEMPTS
  $SNAP/runtime/kpharness/session.py` must return ≥ 1, as must `grep -c dev-max-boot-attempts .../creative.py`.
- It adds a post-run check: `boot-attempts.json` must read `max_boot_attempts==1` and `launch_count==1`. It does not check `source`,
  because creative runs record `kwarg`.
- It bans the six legacy entry points, and notes that the D-route command must be grepped for them.
- Items 1, 2, 3, 6a, 7 and 8 are updated. Item 2 and item 3 `boot` gain `--max-boot-attempts 1`.
- G-RETRY stays open, pending an independent review.

### Verification

| Check | Result |
|---|---|
| Red first (tests written before code) | single-launch: Ran 27, `FAILED (failures=1, errors=28)`; creative: Ran 39, `FAILED (failures=1, errors=5)` |
| Container, Python 3.12.3, `/run/.containerenv` present (this pass, 2026-09-27 confirmation) | single-launch Ran 29, OK (11.1 s); creative Ran 39, OK (0.58 s); offline Ran 150, OK (70.6 s) |
| Host through `host-cmd`, Python 3.14.7, no `/run/.containerenv` (this pass, `TMPDIR=/home/brunner56/kp-live-20260922/tmp-sl`) | single-launch Ran 29, OK (4.5 s); creative Ran 39, OK (1.16 s); offline Ran 150, OK (68.0 s) |

The suites ran one at a time, `python3 -B`, against the code and tests as they sit on disk right now.
`host-cmd` was confirmed to reach the real host, not another container wrapper, before trusting its results:
`host-cmd bash -c 'python3 --version; test -f /run/.containerenv && echo yes || echo no'` printed `Python 3.14.7` and `no`.
`TMPDIR` was exported inline in the same `host-cmd bash -c '...'` invocation as each test run, and the directory
was created fresh this pass (`mkdir -p` after an `ls` that failed with "No such file or directory"); after the pass
it holds `snap-check/`, `ok.json` and `bad-count.json` (see below). That is consistent with the suites using it, and
equally consistent with them not needing it and `unittest`'s own `tempfile`/`tearDown` cleanup leaving it looking
untouched either way — the two cases were not distinguished; no per-suite temp-file trace under `TMPDIR` was checked.

**Single-launch count, corrected.** An earlier draft of this pass's own edit mis-stated this twice: it said a rerun
showing 29 was "confirmed by name in the container run's verbose-less output" (no `-v` run had actually been made at
that point, so that had no referent), and it then guessed the file "did not change between the second Follow-up and
this pass" and that "only the report's arithmetic was wrong" — also unsupported, since no timestamped log of the
second Follow-up's own "Ran 28" runs exists anywhere in this worktree or its plan directory (checked:
`grep -rl "single_launch\|single-launch" .superpowers/sdd/lua-boundary-validation-plan/` finds no dated log, only
this report and the test file itself). What is actually known, each with its own referent:
- `python3 -B tools/kpharness_single_launch_test.py -v 2>&1 | grep ' ok$' | wc -l` → 29, this pass, both places.
- The name list (`grep ' ok$' | sed ...`) shows all six `TestCliBootBudget` tests present, including
  `test_constructor_refusal_is_also_one_line`, whose docstring calls it a "second guard" against the constructor's
  own `InvalidBootAttempts` escaping as a traceback. The second Follow-up's "What changed" prose names only five of
  the six by description, omitting that one.
- `stat -c '%y %n'` on `cli.py` and the test file shows both at `19:01:0x`/`19:01:18` — after the second Follow-up
  section's prose was written (it is earlier in this same file), but there is no independent timestamp for exactly
  when that section's "Ran 28" table was captured, so whether that specific run predates or postdates 19:01 is
  `unverified`. What is not in doubt: 18 (original) + 11 (second round: 5 in `TestCreativeRefusesBeforeClaims` + 6 in
  `TestCliBootBudget`, by direct count of the class bodies right now) = 29, and every run in this pass, container and
  host, returned exactly that count, green.

**Resumed step, now finished.** The writer this session replaced stopped mid-way through "running the runbook
snippets on the host against a scratch snapshot". A scratch dir at `/home/brunner56/kp-live-20260922/boundary-followup/`
looked like a candidate at first glance, but its contents are from a different task: `boundary-followup/tests/red-default-value.out`
names `package_creative_harness_test.FollowupScanTests.test_tmp_and_var_tmp_are_markers`, and
`boundary-followup/tests/creative-dryrun.json` is a dry-run file-selection manifest (`ATTRIBUTION.md`, `LICENSE`,
release doc paths) for a release-packaging harness, not `KP_MAX_BOOT_ATTEMPTS`. It was left untouched. Before running
anything, `scripts/harness/kpharness/gamescope_snapshot.py` `create_snapshot` (:146) was read in full: it hashes
files, `shutil.copyfile`s them into a temp dir, writes a canonical-JSON manifest, and `os.replace`s the temp dir into
place — no subprocess, no Wine, no lock, no launch. Safe to run under "no Wine/game". It, both runbook preconditions,
and the post-run one-liner were then run for real, on the host, under the required `TMPDIR`:
- `create --snapshot /home/brunner56/kp-live-20260922/tmp-sl/snap-check` (the runbook's exact command form, `$WT`
  substituted with this worktree per the runbook's own line-7 definition) → `{"ok": true, ...}`.
- `grep -c KP_MAX_BOOT_ATTEMPTS "$SNAP/runtime/kpharness/session.py"` → **4** (same count as the worktree source;
  the runbook only requires `-ge 1`, so this passes with room to spare, not exactly 1).
- `grep -c dev-max-boot-attempts "$SNAP/runtime/kpharness/creative.py"` → **1** (pass).
- `sha256sum` of both snapshot files against their worktree originals: identical digests for both
  (`session.py` `29a454b2...`, `creative.py` `f160f81f...`), so the snapshot is a byte-exact copy of the code just
  test-verified above, not merely a file that happens to contain the search strings.
- The post-run one-liner against three synthetic `boot-attempts.json` files: `{"max_boot_attempts":1,"launch_count":1}`
  printed `1 1` and exited 0; `{"max_boot_attempts":1,"launch_count":2}` printed `1 2` and exited 1; a missing file
  raised an uncaught `FileNotFoundError` and exited 1 (nonzero either way, so the runbook's "any other pair, or a
  missing file, is FAIL" holds, though a missing file surfaces as a traceback rather than a clean message — the
  runbook does not promise a clean message, only a nonzero exit and "do not launch").
No Wine, game, Xvfb or live-game lock was touched; nothing here starts the game. No git writes.

### Grill me

1. **The run_dir identity claim in an earlier version of this report was wrong — what actually holds?** An earlier
   draft claimed `creative_wine.py` has "no reassignment" of `run_dir`. False: `LinuxWineCreativeSession.__init__`
   (`creative_wine.py:92`) sets `self.run_dir = run_dir.resolve()`, which *is* an assignment.
   Referent: `grep -n "run_dir" scripts/harness/kpharness/creative_wine.py` → line 92. What actually holds: the
   local `run_dir` in `creative.py` (`:226`, `output / (timestamp+uuid)`) is absolute by construction — `output`
   comes from `Path(options.output).expanduser().resolve()` or from `root / 'tmp/creative-runs'` where
   `root = discover.repo_root()` is itself already `.resolve()`d (`discover.py:28`). `root` being resolved does not
   by itself prove `root / 'tmp/creative-runs'` has no symlink component: `.resolve()` only ran on `root`, not on
   the appended `tmp/creative-runs`. Checked directly in this worktree: `ls -ld tmp tmp/creative-runs` shows `tmp`
   is a plain directory (`drwxr-xr-x`), not a symlink, so in this tree the path strings match exactly. If `tmp` were
   ever a symlink elsewhere, `.resolve()` would still name the same directory on disk, just with a different string
   — the identity `boot_evidence()` depends on is about the resolved directory, and that still holds either way.
   The earlier "no assignment" wording (an even earlier draft of this section) was flatly wrong and is retracted.
   Not a live-run proof; an actual Gamescope boot producing a real receipt at that path remains `unverified`.
2. **Is `visual_review.status = 'refused_boot_budget'` a sound way to block Gamescope acceptance?** It is the only lever
   in my file scope. `creative_accept.py` and `display_backends.py` are off-limits, and `execution_evidence_ready` never reads boot data.
   Referent: `creative_accept.py:834` refuses unless `ok is False` and the status is `pending`. `test_gamescope_relaunch_blocks_visual_acceptance`
   calls the real `accept()` and gets that error. Weak spot: a future `accept()` that stops checking `pending` would lose the block.
   The durable fix is for `execution_evidence_ready` to require `boot_attempts.acceptance_eligible`. That belongs to the owner of `display_backends.py` (`unverified`, not done).
3. **Why is a valid `KP_MAX_BOOT_ATTEMPTS=4` accepted, not refused, on the creative path?** The creative runner passes 1 anyway, so
   the env can only mean fewer launches, never more. The value is recorded in `boot_attempts.env`. Referent: `test_resolved_budget`,
   case `({ENV: '4'}, None) -> (1, 'default_single')`. Refusing it would be stricter. That is a scope call for the reviewer.
4. **Could an old snapshot still run with 5 attempts?** Yes. Neither the code nor its tests can stop that, because the old snapshot
   carries old code. The runbook's two snapshot greps are the only guard, and this pass ran them for real against a freshly built
   snapshot (see above) rather than only reading the runbook text. Referent: `snap-check` grep results this pass —
   `session.py` 4 (runbook only requires `-ge 1`), `creative.py` 1 — plus sha256-identical to the worktree source.
5. **Does the CLI refusal really happen before anything launches?** Yes. `_boot_budget_error` returns before `GameSession(` and before
   `S.find_scenario`. Referent: `test_invalid_env_is_one_line_nonzero_without_session` and `test_invalid_flag_...` assert that the `GameSession` mock
   and `find_scenario` were never called, rc 3, one stderr line. `GameSession.__init__` also still resolves first (`session.py:465`) as a second guard.
6. **Why was the host single-launch run sometimes ~26 s in an earlier pass but 4.5 s in this one?** The earlier number
   was the cold first `import kpharness.cli` from the MyBook disk (`python3 -B -m unittest --durations 5`: 9.7 s in
   `test_flag_is_parsed_on_boot_and_run`, every other test < 0.3 s). This pass's 4.5 s host run is warm-cache; both
   are the same 29 tests, same result, only wall time differs (`unverified` which specific OS cache state produced 4.5 s).
7. **Open question for a reviewer: does a real Gamescope run's `boot-attempts.json` end to end show
   `acceptance_eligible: true`?** Not settled by this pass. What this pass adds: the snapshot mechanism that ships
   the code to a live run is now verified file-exact (sha256-identical to the worktree source, both required strings
   present), so if a live run fails this check, the cause is not a stale or wrong snapshot. What remains open: an
   actual Wine boot producing a real `boot-attempts.json` and a real `creative-run.json` with
   `boot_attempts.acceptance_eligible: true`. That needs a live item run, out of scope here ("no Wine/game"), and is
   the same open item the prior pass named.

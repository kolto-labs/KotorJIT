# Single-launch (G-RETRY) independent review — 2026-09-27

Scope: `.worktrees/lua-boundary-validation` read-only. Probes and outputs are in
`/home/brunner56/kp-live-20260922/review-probes-single-launch/`. No Wine, no game, no
live-game lock, no git writes. The one lock taken by a probe was a scratch file under `/tmp`. One disclosure: the required container and host test runs ran without `-B`, so they may have written gitignored `__pycache__/*.pyc` files into the worktree (`git check-ignore` confirms these are ignored). Other writers share the worktree, so some of those files may be theirs.

I formed my own view from the diff and my own probes first. After that I read the writer's report (`.superpowers/sdd/lua-boundary-validation-plan/single-launch-report.md`).

## Claim blocks

claim: new tests are red on HEAD session.py
referent: `single-red-HEAD.out`: Ran 18, `FAILED (failures=3, errors=30)`. The three FAILs are the core ones: `test_one_attempt_crash_launches_once_and_does_not_relaunch`, `..._boot_timeout_launches_once`, `test_env_one_forces_single_launch`. The writer's "17 tests, 3F/29E" is the same result before the 18th test was added.
checked: `git show HEAD:scripts/harness/kpharness/session.py` swapped into a scratch copy of `kpharness/*.py` (`review-probes-single-launch/red/`)
verdict: holds
confidence: high

claim: green now, container and host; offline suite 150 OK
referent: `single-container.out` Ran 18 OK (py3.12). `single-host.out` Ran 18 OK (py3.14.7 via host-cmd). `offline-container.out` Ran 150 OK. `offline-host.out` Ran 150 OK, rc=0, 258 s.
checked: `python3 tools/kpharness_single_launch_test.py`, `python3 tools/kpharness_offline_test.py`, each run in the container and through `/home/brunner56/.local/bin/host-cmd`
verdict: holds
confidence: high

claim: KP_MAX_BOOT_ATTEMPTS=1 gives exactly one launch on crash and on boot timeout, with no kill-and-relaunch and a typed failure that carries launch_count and evidence_path
referent: `probe_boot.py` drives the real `GameSession.__init__ → boot → _launch_and_connect → launch → connect → teardown`. Only Popen/run (fake launcher: `sleep 0` = crash, `sleep 30` = boot timeout), the locks, stage and Xvfb are faked.
- `probe-crash-1.json`: `BootFailure reason=crash launch_count=1 max_boot_attempts=1 evidence_path=.../boot-attempts.json`, 1 `wine swkotor.exe` Popen.
- `probe-timeout-1.json`: `reason=boot timeout`, launch_count 1, 1 Popen.
- Both runs made exactly 1 `wineserver -k` call. That call comes from teardown, so `_kill_game` never ran.
- Control, env=5 (`probe-crash-5.json`): 5 Popens, launch_count 5, 5 `wineserver -k` calls.
checked: `python3 probe_boot.py <WT> {crash|timeout} {1|5}`
verdict: holds
confidence: high. This would change if a real Wine crash reached `connect()` through a path other than launcher-exit, stderr or runtime-log. The code reads no other path (`session.py:1370-1434`).

claim: boot-attempts.json survives teardown; the runbook's detection greps work
referent: the probes above report `evidence_exists_after_teardown: true` and `session_json_exists: false`, and `outcome: failed, launch_count: 1, source: env`. With a real `session.log` open (`probe-runbook-greps.out`), env=1 gives `launching: 1, boot attempt: 0` and env=5 gives `launching: 5, boot attempt: 4`. That matches runbook line 30.
checked: `probe_boot_log.py`
verdict: holds on base `GameSession.teardown`. For the creative/Gamescope path I checked by grep only: `grep -nE "rmtree|unlink|iterdir|glob|listdir"` over `creative*.py` finds no deletion of run-dir contents, and the only run-dir glob is `creative_accept.py:32/426` `ffprobe-cleanup-unrecorded-*.json`, which `boot-attempts.json` does not match.
confidence: high for GameSession; medium for Gamescope (grep only, no live teardown)

claim (writer): "GameSession(..., max_boot_attempts=None) resolves in __init__ before any lock, stage or display work"
referent: True for a direct `GameSession` (`session.py:465`, first statement). False for the creative runner. `probe-creative-invalid-0.json` sets env=0 through `run_creative` with the real `LinuxWineCreativeSession`. The run takes the lock (a scratch path) and constructs the recorder before it raises `InvalidBootAttempts`. It leaves `run_dir/driver.log`, `executed-route.toml`, `sources/`, claimed `stage-k1`/`wineprefix-k1` and their owner markers.
Order in `creative.py`:
1. `with live_lock` :198
2. `run_dir.mkdir` :204
3. Gamescope only: `initialize_cleanup_ledger` :209 writes a launch head to the operator's commitment log
4. `claim(stage…)` :223
5. `recorder_type` :238
6. `session_type(...)` :247, where the refusal finally happens

No receipt is written because the raise happens before the `try` at :270.
checked: `probe_creative_invalid.py <WT> 0`
verdict: does not hold on the creative path. Nothing launches, so the no-launch property is intact.
confidence: high
fix: in `run_creative`, call the module function `kpharness.session.resolve_max_boot_attempts()` next to the other option checks (~:153), before `live_lock`. Pass the result as `session_type(..., max_boot_attempts=n)`.

claim (writer): creative sessions "subclass GameSession without their own __init__"
referent: `creative_wine.py:87-88` and `:206-207` both define `__init__`, and both call `super().__init__(...)`
verdict: the stated reason does not hold. The conclusion (both inherit the env budget) holds, because they call super.
confidence: high

claim: no other launch path bypasses the limit (session, creative_wine, creative, cli, scenario, playback, pioneer)
referent:
- `grep -nE "\.launch\(|_launch_and_connect|\.boot\(|GameSession\(|Popen|subprocess\.run|gamescope|swkotor|wine"` over the seven files finds one `self.launch()`, at `session.py:1471`, inside the budgeted loop.
- `_launch_and_connect` is called from `session.py:1599` and `creative_wine.py:226`. The Gamescope boot does not call `super().boot()`, but it does use the budgeted method.
- `playback.py:835/855` Popens only the playback owner (`python -m kpharness.playback`), not the game. `playback.py:744` is a channel connect.
- `pioneer.py` and `scenario.py` have no launch or boot calls.
- The `gamescope_xwayland.py` lease Popens gamescope, the display. The game still starts through `launch()` with `lease.game_environment`.
- `kpharness.sh` and the snapshot `driver` both pass `os.environ` through (`gamescope_snapshot.py:330`), so the env reaches the session.
checked: grep above, plus reads of `creative_wine.py:204-240` and `playback.py:825-860`
verdict: holds for the Python harness
confidence: high

claim (writer): four legacy shell scripts launch the game outside the budget
referent: they are `live_session.sh:88`, `spike_headless_k1.sh:101`, `drive_k1_console.sh:118` and `measure_boot.sh:79`. Each runs `exec wine swkotor.exe`. The writer missed two transitive launchers: `demo_play.sh:176` calls `drive_k1_console.sh`, and `gameplay_tests/lib.sh:92` calls `live_session.sh`.
checked: grep of `scripts/harness/*.sh` and `gameplay_tests/lib.sh`
verdict: holds, but the list is incomplete. Six entry points, not four.
confidence: high

claim: which runbook items call the legacy scripts
referent: `grep -nE "live_session|drive_k1_console|measure_boot|spike_headless|demo_play|gameplay_tests|record_*"` on `live-runbook-20260927.md` finds no hits.
- Item 0: `capture_diagnostic`. It is exempt because it runs no Wine.
- Items 1, 6a, 7, 8: the Gamescope creative runner, through the `gamescope_snapshot driver`.
- Item 2: `kpharness.sh run`.
- Item 3: `kpharness.sh boot` + `pioneer` + `down`.
- Items 4, 5, 9: "combined D-route". No launch command has been written yet (`:470-477`, hash `unverified`).
checked: runbook grep, `:252`, `:297-298`, `:196-197`, `:470-494`
verdict: holds for items 0-3, 6a, 7, 8. Unresolved for 4/5/9 until their command exists.
confidence: medium. This changes if the D-route command names a legacy script.

## Blockers for live use (not in the writer's report)

claim: an operator following the runbook gets single-launch on Gamescope items
referent: every existing snapshot has 0 hits for `KP_MAX_BOOT_ATTEMPTS` in `runtime/kpharness/session.py`. That includes `next-k1-preparations/20260927-task7-scale-102038-74cb804b/harness-snapshot` and the 3 under `harness-snapshots/`. On those snapshots the variable is silently ignored and the run makes up to 5 launches. A new `gamescope_snapshot create` copies working-tree bytes: my scratch snapshot `review-probes-single-launch/snap` has 4 hits, and its `session.py` is byte-identical to the worktree copy (`cmp`). So a new snapshot works, and an old one does not.
checked: `find ... -path '*runtime/kpharness/session.py'` + grep; `gamescope_snapshot create --snapshot <scratch>`
verdict: does not hold unless every Gamescope item (1, 7, 8, and 6a if it runs on Gamescope) creates a new snapshot and runs a preflight check first: `grep -c KP_MAX_BOOT_ATTEMPTS "$SNAP/runtime/kpharness/session.py"` ≥ 1.
confidence: high

claim: the runbook's variable name will be used
referent: runbook `:29` suggests `KP_BOOT_ATTEMPTS=1`. The code reads only `KP_MAX_BOOT_ATTEMPTS` (`session.py:79`). An unset or misspelled name silently resolves to "default", which is 5 attempts. Only a set-but-invalid value is refused.
verdict: does not hold. The runbook must name `KP_MAX_BOOT_ATTEMPTS=1` exactly. The preflight should echo it. After each run, check `boot-attempts.json` for `max_boot_attempts: 1` and `source: env`. Do not rely on the launch count alone, because a successful boot shows 1 either way.
confidence: high

## Grill me, attacked weakest first

1. Writer Q2, "refused before any launch because `__init__` resolves first". The launch half holds. "Before any lock/staging" does not hold on the creative path; see the claim block above. The writer said running the CLI would be unsafe to settle it. That is fair for the CLI. For the creative path, `run_creative` with fakes and a scratch lock settles it safely.
2. Writer Q3, "relies on the env today". This holds (grep finds no `max_boot_attempts` in `cli.py` or `creative*.py`), with the missing caveat that the env is a no-op on every existing snapshot.
3. Writer Q1, "a receipt write failure does not mask the failure". This holds: `test_unwritable_receipt_does_not_mask_boot_failure` passes in both places, and `_write_boot_attempts` catches `OSError` (`session.py:1508-1514`).
4. Writer Q4 and Q5 (session.json on failure; default unchanged). Both hold: the env=5 probe gives 5 launches, and the offline suite is 150 OK on host and container.
5. My own question: can a mutated `max_boot_attempts` attribute widen the budget? No. `_launch_and_connect` re-resolves it (`session.py:1459-1462`), and `test_invalid_env_refuses_before_any_launch` passes.

Unsettled, with the one check that settles it: the launch path for the D-route items 4/5/9. When its command is written, grep it for the six legacy entry points.

Single-launch: PARTIAL

---

# Follow-up re-review — 2026-09-27

Scope: `.worktrees/lua-boundary-validation` read-only, second pass, after the writer's
"Follow-up (2026-09-27, after the PARTIAL review)" section in
`.superpowers/sdd/lua-boundary-validation-plan/single-launch-report.md`. Sole reviewer, no
subagents, no worktree isolation. Probes and outputs are in
`/home/brunner56/kp-live-20260922/review-probes-single-launch-fu/` (`TMPDIR` exported there
for every run). No Wine, no game, no live-game lock, no git writes. I signalled no process I
did not start myself.

I read the code first (`creative.py`, `creative_wine.py`, `cli.py`, `session.py`), formed my
own view of each ruling, then ran fresh probes before reading past the writer's "What changed"
section a second time.

## Claim blocks

claim: invalid `KP_MAX_BOOT_ATTEMPTS` values are refused before any filesystem side effect, on
both the creative path and the CLI path, including a unicode-digit value
referent: `probe_invalid_values.py` drives the real `run_creative` (real
`LinuxWineCreativeSession`, scratch lock path, no game/Wine — only `Popen`-adjacent code is
never reached) and the real `cli._boot_budget_error`, for `"0"`, `"6"`, `"-1"`, `"1.0"`,
`" 1"`, `""`, and `"１"` (fullwidth digit 1, which `str.isdigit()` alone would accept).
Every value raised `InvalidBootAttempts` with `events: []` (the spied `live_lock` was never
entered) and `files_created: []` (nothing appeared under the fresh temp root). The unicode
case is caught by the `raw.isascii()` gate in `resolve_max_boot_attempts` (`session.py:115`),
not by `isdigit()` alone.
checked: `python3 -B review-probes-single-launch-fu/probe_invalid_values.py <WT>` →
`review-probes-single-launch-fu/invalid-values.json`
verdict: holds
confidence: high

claim: acceptance-path precedence (env vs. kwarg vs. CLI flag) is flag > env > default for the
CLI, and dev-flag > default(1) for creative, and this is documented
referent: live probe against `cli.build_parser()`/`_boot_budget_error`/`resolve_max_boot_attempts`:
`--max-boot-attempts 2` with `KP_MAX_BOOT_ATTEMPTS=3` in the environment resolves to `(2, "kwarg")`;
no flag with the same env resolves to `(3, "env")`. `resolve_max_boot_attempts`'s docstring states
"An explicit keyword wins over KP_MAX_BOOT_ATTEMPTS" (`session.py:104`); the CLI flag's help text
states "Default: KP_MAX_BOOT_ATTEMPTS, else 5" (`cli.py:469-470`). For creative, `boot_budget`
(`creative.py:150-163`) always resolves the non-dev budget to 1 regardless of what
`KP_MAX_BOOT_ATTEMPTS` is set to (it is validated via a no-arg `resolve_max_boot_attempts()`
call but its value never reaches `n`); only `--dev-max-boot-attempts` raises `n`, and that path
is marked `dev_override`, never acceptance-eligible.
checked: ad hoc script importing `kpharness.cli` and `kpharness.session` directly (see transcript;
not saved as a file)
verdict: holds. The creative precedence is under-documented as a "precedence" per se (there is no
flag competing with the env on that path), but the behavior itself — dev flag is the only thing
that can raise the budget, and doing so forfeits acceptance — is stated in the `boot_budget`
docstring.
confidence: high

claim: `creative.py`'s `boot_budget()` forces `budget_source='default_single'` (and `n=1`)
regardless of `KP_MAX_BOOT_ATTEMPTS`, and this is the intended acceptance behavior, not a bug
that silently ignores an operator's explicit value
referent: `creative.py:150-163`. Non-dev calls always take the `resolve_max_boot_attempts(1)`
branch; the env var is read only via the earlier no-arg `resolve_max_boot_attempts()` call, whose
sole effect is to raise `InvalidBootAttempts` on a malformed value — its resolved count is discarded.
The env value is still recorded for visibility in `budget['env']` (`creative.py:164`) and threads
through to `boot_attempts.env` in the receipt. The docstring says "Only the dev flag raises the
budget above 1, and such a run is never acceptance-eligible" (`creative.py:152-153`.) This matches
the review's own ruling: "acceptance creative runs default max_boot_attempts=1."
checked: code read of `creative.py:150-163`; `test_resolved_budget` case
`({KP_MAX_BOOT_ATTEMPTS: '4'}, None) -> (1, 'default_single')` in
`tools/kpharness_creative_test.py` (ran green, see below)
verdict: holds — intended, not a silent-ignore bug. A `KP_MAX_BOOT_ATTEMPTS=4` on a creative
acceptance run can only ever mean "run with the acceptance default of 1," never "run with 4."
That is stricter than the env's general meaning elsewhere in the harness, and it is named in the
function's own docstring and in the runbook's G-RETRY section ("The creative runner … always
passes `max_boot_attempts=1`").
confidence: high. Would change if a future caller passed a non-`None`, non-acceptance value as
"default" without going through the `dev_override` label — not seen anywhere in this diff.

claim: the acceptance path cannot be made to use more than one launch via env, kwarg, or CLI flag
referent: `creative.parser()` (`creative.py:455-478`) defines only `--dev-max-boot-attempts`,
which is explicitly the non-acceptance override; there is no other flag or kwarg path into
`boot_budget`. `boot_evidence` (`creative.py:166-195`) refuses eligibility whenever
`budget_source != 'default_single'` or `max_boot_attempts != 1`, independent of what actually
happened at runtime. `creative_accept.accept()` (`creative_accept.py:833-834`) additionally
refuses any receipt whose `ok` is not `False` or whose `visual_review.status` is not `'pending'`
— an ineligible run gets `status='refused_boot_budget'` (`creative.py:449`), which is neither.
checked: grep of `creative.py` for `add_argument`; read of `creative_accept.py:820-836`
verdict: holds
confidence: high

claim: receipt refuses `launch_count>1` and missing `boot-attempts.json`
referent: `boot_evidence` (`creative.py:166-195`): a missing/symlinked file sets
`refusal='boot-attempts.json missing'`; unreadable/non-dict JSON is refused; `launch_count` must
be the exact `int` `1` (`type(count) is not int or count != 1`, so a bool or a float `1.0` would
also be refused, not just `>1`). Wired into `receipt['ok']` (`creative.py:425-428`) and, on
Gamescope, into `visual_review.status` (`creative.py:444-450`), which `accept()` rejects (above).
checked: code read; `tools/kpharness_creative_test.py` new tests (ran green, see below)
verdict: holds
confidence: high

claim: `cli.py --max-boot-attempts` refuses before any launch, with a documented, tested second
guard around the constructor call itself
referent: `_boot_budget_error` (`cli.py:96-104`) runs before `GameSession(` in both `cmd_boot`
and `cmd_run`, validating env then flag, and returns a one-line message on failure (rc 3, nothing
constructed). `cmd_boot`/`cmd_run` additionally wrap the `GameSession(` constructor call itself in
`except InvalidBootAttempts` (`cli.py:121-127`, `:218-224`), printing the same one-line, rc-3
refusal instead of a traceback, for the case where the environment changes between the pre-check
and the constructor call.
The writer flagged (grill-me Q2) that `test_constructor_refusal_is_also_one_line` has no recorded
red run anywhere — only a code-read argument that the guard matters. I settled this myself rather
than trust the code read: I copied `scripts/harness` and `tools` into a scratch dir, removed the
`try/except InvalidBootAttempts` around both constructor calls (leaving `_boot_budget_error`
intact), and ran that one test against the patched copy. It went red for real:
`kpharness.session.InvalidBootAttempts: KP_MAX_BOOT_ATTEMPTS must be in 1..5, got 0` propagates
as an uncaught exception from `cmd_boot`, `FAILED (errors=2)` (one error per `subTest` cmd). This
is a fresh, observed red run, not a restatement of the code read.
checked: `review-probes-single-launch-fu/scratch_no_guard/` (patched `cli.py`, guard removed),
`python3 -B -m unittest tools.kpharness_single_launch_test.TestCliBootBudget.test_constructor_refusal_is_also_one_line -v`
→ `FAILED (errors=2)`, traceback shown above
verdict: holds, now with an observed referent instead of only a code read
confidence: high

claim: green now, container and host; single-launch 29, creative 39, offline 150
referent: host (Python 3.14.7 via `host-cmd`, confirmed real host by `test -f /run/.containerenv`
→ `no`), one suite at a time, fresh `TMPDIR`:
- `tools/kpharness_single_launch_test.py` → Ran 29 tests, OK (8.995s)
- `tools/kpharness_creative_test.py` → Ran 39 tests, OK (2.027s)
- `tools/kpharness_offline_test.py` → Ran 150 tests, OK (76.374s)
checked: `review-probes-single-launch-fu/host-single.out`, `host-creative.out`, `host-offline.out`
verdict: holds
confidence: high

claim: the live runbook uses `KP_MAX_BOOT_ATTEMPTS` exactly, everywhere, and bans all six legacy
entry points
referent: `grep -noE '[A-Za-z_]*BOOT_ATTEMPTS[A-Za-z_]*' live-runbook-20260927.md | sort | uniq -c`
→ 10 hits of `KP_MAX_BOOT_ATTEMPTS`, 1 bare `BOOT_ATTEMPTS` (line 23, quoting the code constant
`BOOT_ATTEMPTS = 5` as history, not as an env-var name). No `KP_BOOT_ATTEMPTS` or other
misspelling anywhere. All six legacy scripts (`live_session.sh`, `spike_headless_k1.sh`,
`drive_k1_console.sh`, `measure_boot.sh`, `demo_play.sh`, `gameplay_tests/lib.sh`) are named
under the G-RETRY global gate, which the runbook's own header states applies to every item
(1-9). Every Wine item I read (0, 1, 2, 3, 6, 7, 8, 9) restates the `KP_MAX_BOOT_ATTEMPTS=1`
precondition and, where the command is `kpharness.sh boot`/`run`, adds `--max-boot-attempts 1`
explicitly. Items 4, 5 remain BLOCKED with no launch command written yet (unchanged from the
prior pass); item 9 is BLOCKED on an unrelated integration dependency.
checked: the two greps above; `sed -n` reads of items 0-9 in `live-runbook-20260927.md`
verdict: holds for items 0, 1, 2, 3, 6, 7, 8. Items 4, 5, 9 remain open pending their own launch
commands, same as the prior pass — not a regression, just still unsettled.
confidence: high

## Grill me, attacked weakest first

1. Writer Q9 ("does a real Gamescope run's `boot-attempts.json` end to end show
   `acceptance_eligible: true`?"). Still not settled by any pass, including this one — no Wine/game
   was run, per my own scope. That holds as open; no referent exists to close it, and manufacturing
   one would mean running the game, which is out of scope here.
2. Writer Q2 (the untested second guard). Does not hold as "no red run recorded" — see the claim
   block above. I produced the red run myself, on a scratch patched copy, in a scope-safe way.
3. Writer Q5 ("why is `KP_MAX_BOOT_ATTEMPTS=4` accepted, not refused, on the creative path").
   Holds, and matches the ruling given to me directly ("acceptance creative runs default
   max_boot_attempts=1"). Not a silent-ignore bug: the env is validated, recorded, and then
   deliberately overridden for acceptance runs. See claim block above.
4. My own question: could the CLI's `--max-boot-attempts` flag and a conflicting env value ever
   both reach `GameSession` and race? No — `_boot_budget_error` resolves the flag over the env by
   calling `resolve_max_boot_attempts(a.max_boot_attempts)` when the flag is set at all, and the
   same precedence is re-applied inside `GameSession.__init__` via the identical function, so the
   pre-check and the constructor agree (probe above, and `test_flag_reaches_the_session` in the
   suite, which passed).
5. My own question: does anything besides `--dev-max-boot-attempts` let a creative run claim
   `acceptance_eligible=True` with more than one launch? No — `boot_evidence` re-derives eligibility
   from the on-disk `boot-attempts.json` record itself (`record.get('max_boot_attempts')`,
   `count`), not from the caller's intent, so even a hypothetical future caller that mislabels its
   `budget_source` would still be caught by the record's own `max_boot_attempts`/`launch_count`
   checks (double gate: budget dict source label AND the receipt's own numbers).

Unsettled, with the one check that settles it: item 9 in the writer's own list — a real Gamescope
boot producing `boot_attempts.acceptance_eligible: true` end to end. That needs a live item run,
out of scope for both passes so far.

Single-launch follow-up verdict: PASS

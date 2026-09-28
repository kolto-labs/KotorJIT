# Task 2 report: harness safety and TOML contracts

## Result

Implemented the assigned harness-only changes from base `997a0cf`.

- `run_all.sh` now accepts only the documented default, `--live`, and
  `--live-all` modes. Only `FAST` enters the bounded parallel scheduler;
  `LIVE` and `LIVE_WIP` both execute serially under `live-game.lock`.
- `ScenarioRunner` derives report and automatic checkpoint targets from the
  effective session target. An explicit CLI target therefore remains visible
  without mutating the parsed route's authored target.
- Malformed selected workspace TOML returns CLI status 3 through the existing
  configuration boundary, now pinned by an offline regression.
- K1 overlay creation copies known runtime-written top-level files instead of
  linking them. Reused legacy stages materialize those files before runtime
  installation or launch. This covers `steam_appid.txt`, `kphasor.dll`,
  `kotorphasor.log`, and `kotorphasor-proxy.log`.
- Staging refuses an effective staged path equal to either the install root or
  discovered data directory, including a symlink alias.
- The driver contract documents the effective target reporting/checkpoint
  behavior and confirms that the WIP live group is serialized. Existing TOML
  ownership, nearest-file selection, path precedence, validation, and no-merge
  compatibility semantics remain distinct from runtime INI and route TOML.

No game, Wine, display, source installation, or canonical checkout was used.
The scheduler regression uses temporary fake shell fixtures only.

## Validation

Focused regressions:

```text
/usr/bin/python3 -m unittest \
  tools.kpharness_offline_test.TestScenario.test_runner_uses_effective_session_target_for_report_and_fallback_checkpoints \
  tools.kpharness_offline_test.TestStaging.test_stage_preserves_runtime_written_source_files_and_repairs_legacy_links \
  tools.kpharness_offline_test.TestStaging.test_stage_refuses_source_install_even_through_symlink \
  tools.kpharness_offline_test.TestConfigurationContracts.test_cli_reports_malformed_workspace_configuration_as_invalid_input
Ran 4 tests in 7.123s -- OK

bash tools/gameplay_scheduler_test.sh
gameplay scheduler regression: PASS
```

Existing Python harness suites and shell regression:

```text
/usr/bin/python3 tools/kpharness_offline_test.py
Ran 148 tests in 46.887s -- OK

/usr/bin/python3 tools/kpharness_world_test.py
Ran 6 tests in 0.006s -- OK

bash tools/gameplay_scheduler_test.sh
gameplay scheduler regression: PASS
```

Configured CTest registration with system Python, without rebuilding C++:

```text
cmake -S . -B /home/brunner56/kp-validation-20260922-build
ctest --test-dir /home/brunner56/kp-validation-20260922-build \
  --output-on-failure \
  -R '^(kpharness_offline_test|kpharness_world_test|gameplay_scheduler_test)$'
3/3 passed; 0 failed; 47.78 seconds
```

Static checks:

```text
git diff --check
bash -n scripts/harness/gameplay_tests/run_all.sh tools/gameplay_scheduler_test.sh
/usr/bin/python3 -m py_compile scripts/harness/kpharness/scenario.py \
  scripts/harness/kpharness/session.py tools/kpharness_offline_test.py
```

All returned status 0 with no diagnostics.

## Self-review

- Scope is limited to the assigned harness Python/session/scenario tests,
  gameplay shell scheduler/test, driver contract, and CMake test registration.
- Source protection happens before `_install_runtime`, INI tuning, app-ID
  writing, and launch. The symlink-equality refusal happens before staged-tree
  directory or session-log creation.
- The source-preservation regression begins with legacy top-level links into a
  synthetic install, compares all relevant source bytes after staging, and
  checks that runtime/app-ID output exists privately in the stage.
- Fake fixture results establish scheduler classification and locking behavior;
  they are not represented as live-game evidence.
- `Scenario` remains immutable; only the execution report and automatically
  constructed checkpoint store use the effective target. Callers that provide
  an explicit checkpoint store retain ownership of that choice.

## Review round 1

Addressed every finding in `/tmp/kp-task2-review.md` against base `69291c9`:

- Every selected stage path is now canonicalized, including default and legacy
  `_stage_root` results. Source identity validation runs before the stage lock
  can create its parent or lock file, and runs again at staging.
- A directory containing only `.kpharness-stage.lock` is treated as a fresh,
  uninitialized stage. This preserves the lock-first boot order while ensuring
  the K1 overlay, codec, executable assets, and writable trees are created.
- Legacy linked stages also materialize top-level INI files before `_tune_inis`
  or `write_runtime_ini` can modify them. The source-byte regression now covers
  `swkotor.ini` and `kotorphasor.ini` along with the DLL, app ID, and logs.
- The scheduler fixture tries to take the expected shared lock from each fake
  live test and fails the test if it succeeds. It also compares exact selected
  identities for all three modes and asserts status 2 for both invalid inputs.

Focused review regressions:

```text
/usr/bin/python3 -m unittest \
  tools.kpharness_offline_test.TestStaging.test_default_stage_alias_is_rejected_before_lock_or_source_write \
  tools.kpharness_offline_test.TestStaging.test_lock_first_fresh_stage_initializes_overlay_and_private_ini \
  tools.kpharness_offline_test.TestStaging.test_stage_preserves_runtime_written_source_files_and_repairs_legacy_links \
  tools.kpharness_offline_test.TestStaging.test_stage_refuses_source_install_even_through_symlink
Ran 4 tests in 0.047s -- OK

bash tools/gameplay_scheduler_test.sh
gameplay scheduler regression: PASS
```

Relevant full gates after the fixes:

```text
/usr/bin/python3 tools/kpharness_offline_test.py
Ran 150 tests in 63.072s -- OK

/usr/bin/python3 tools/kpharness_world_test.py
Ran 6 tests in 0.006s -- OK

bash tools/gameplay_scheduler_test.sh
gameplay scheduler regression: PASS

bash -n scripts/harness/gameplay_tests/run_all.sh tools/gameplay_scheduler_test.sh
/usr/bin/python3 -m py_compile scripts/harness/kpharness/session.py \
  tools/kpharness_offline_test.py
git diff --check
```

The static commands returned status 0 with no diagnostics. No live process or
source installation was used.

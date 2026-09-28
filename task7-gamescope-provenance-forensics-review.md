# Task 7 Gamescope provenance and early-boot forensics review

Date: 2026-09-27  
Checkout: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`  
Review basis: `task7-gamescope-provenance-review-checklist.md`, current worktree source, and `tools/kpharness_gamescope_backend_test.py`  
Scope: read-only review; no Gamescope, Wine, Xwayland, recorder, or game process was launched.

## Verdict

**FAIL — the completed slice is useful and narrowly tested, but it does not yet satisfy the checklist’s provenance or forensic acceptance contract.**

The focused host-only suite passes **27/27**, including snapshot module/source drift checks, snapshot import-root setup, atomic early boot evidence on a pre-readiness exit, secret-free lease receipt checks, PID reuse refusal, cleanup ordering, and cleanup failure recording. Those tests establish meaningful local behavior. They do not establish a complete Task 7 source manifest, isolated module resolution in a real driver invocation, crash-durable terminal receipts, or complete ownership evidence for a readiness child that fails validation.

No product files were changed by this review. The only artifact written is this report.

## Critical findings

### C1 — The snapshot manifest is not the required complete Task 7 source manifest

`gamescope_snapshot.py` materializes a static Python `kpharness` import closure for the `creative` and snapshot entrypoints. Its manifest contains only relative Python paths and SHA-256 values. It does not bind the selected route TOML, every Lua input, K1 executable/source identity, address profile, build inputs, built DLL/proxy/runtime artifacts, deployed copies, or the external tool/interpreter identities required by the checklist.

This is a valid harness-module snapshot, but it cannot serve as the complete source/artifact manifest for a live result. The current `creative.py` still discovers the repository, build, route, Lua, and installed game independently after the harness snapshot is selected. A run can therefore have an intact Python snapshot while its route, game source, runtime, or deployed bytes remain unbound.

Required disposition: retain the narrow harness snapshot as one manifest component, then add a run-level closed manifest that includes all live inputs and produced/deployed artifacts, with before/after equality checks.

### C2 — Driver module resolution is not actually isolated from the caller’s working directory

`gamescope_snapshot.driver_command()` verifies the snapshot and returns `[python, "-m", "kpharness.creative", ...]`. `main()` replaces `PYTHONPATH` with `<snapshot>/runtime`, but the subprocess keeps the caller’s current working directory and uses a caller-selected Python executable. The test only asserts the `PYTHONPATH` value and mocked command; it does not execute a real import-resolution check.

Python’s module search can include the working directory before `PYTHONPATH`. A `kpharness` package in the working directory or another interpreter configuration can shadow the manifest closure. The code records neither the resolved `__file__` paths nor their hashes at driver startup, and it does not refuse an unexpected module origin.

Required disposition: execute from a controlled directory or use an isolated import mode, record the absolute interpreter and resolved module files/hashes, and refuse any import outside the manifest closure. Preserve the snapshot path and interpreter identity in the run receipt.

### C3 — A readiness child that publishes invalid or changed identity is not retained in the lease receipt

The lease records the Gamescope owner immediately after spawn, including PID/start/parent/PGID/SID. It only assigns `self.ready_child` after the readiness payload passes identity, ancestry, and authority validation. If the child publishes malformed data, a changed start identity, foreign ancestry, or mismatched authority, the durable receipt’s `owner.ready_child` remains `null`, even though a child may have existed and may be the reason readiness failed.

Group cleanup is still scoped to the validated Gamescope group, which is safer than name-based cleanup, but the forensic chain cannot show the child identity that was observed and rejected. This fails the requirement to retain ownership facts before readiness and makes an early boot failure less auditable.

Required disposition: record the candidate readiness PID/start/environment in a sanitized rejected-child field before validation, then retain the exact refusal reason and relationship snapshot. Continue to use the validated owner/group identity for any cleanup signal.

## Important findings

### I1 — Lease evidence has atomic replacement but not directory durability

`_write_evidence()` writes a temporary file, flushes and fsyncs it, and uses `os.replace()`. That provides atomic visibility, and the tests verify that a complete JSON receipt survives an early boot failure. It does not fsync the containing directory after replacement. A host crash can therefore lose the directory entry or the latest terminal state despite the file fsync.

Required disposition: fsync the parent directory after each published receipt, or document a platform-specific durable journal/sidecar protocol and test the resulting guarantee.

### I2 — Cleanup failure can leave the lease receipt at `cleanup_phase=started`

`close()` publishes `cleanup_phase=started`, then can raise on changed PID identity, a missing group identity, a surviving group after escalation, or a failed leader wait. On those paths it does not itself publish `cleanup_phase=failed`; `start()` catches and publishes a failed event only for failures occurring inside `start()`. A later caller-side session cleanup error can be recorded in the outer cleanup receipt while `gamescope-lease.json` remains terminally ambiguous.

Required disposition: make `close()` publish a failed terminal lease event on every exception, preserve the first cleanup error, and make repeated close idempotent without erasing the unresolved status.

### I3 — Snapshot verification allows unlisted non-Python files in the runtime tree

`verify_snapshot()` compares the manifest against `runtime.rglob("*.py")`. It catches a changed or missing listed Python file and an extra Python file, but an extra unlisted non-Python file can be added beneath `runtime` without failing verification. The current creator does not add such files, but a tampered snapshot can carry arbitrary extra data that is outside the declared closure.

Required disposition: compare the complete runtime file list, reject symlinks and unexpected file types, or use a manifest that explicitly accounts for every filesystem entry.

### I4 — Snapshot creation has no run-level source-change lock or later source binding

`create_snapshot()` hashes the static module closure before and after copying and refuses a mixed closure. That is good protection against changes during the copy. The driver path subsequently calls `verify_snapshot(snapshot)` without `source_root`, and the live creative path independently discovers route/game/build inputs. There is no single run-level manifest digest tying those inputs to the snapshot or a later check that the selected source tree still matches the declared source authority.

Required disposition: create and verify one run-level manifest immediately before mutation/launch, carry its digest into the early receipt, and repeat all input equality checks after teardown.

### I5 — Secret handling is narrow assertion, not a manifest/log scrub gate

`isolated_environment()` drops several authority and injection variables, and the focused lease test confirms the private Xauthority path does not appear in the serialized lease receipt. The implementation does not scan manifest data, command arguments, failure strings, Gamescope logs, renderer output, or outer receipts for cookies, tokens, passwords, keys, or other secret material. It also does not prove that arbitrary tool output cannot be copied into a receipt.

Required disposition: add an explicit redaction/scrub gate for all persisted evidence and retain only sanitized authority identity/presence. A finding must refuse publication and must not include the secret in the diagnostic.

### I6 — Test coverage does not execute the actual snapshot driver import boundary

The 27/27 test suite mocks `subprocess.run` for `gamescope_snapshot.main(["driver", ...])` and checks the generated command and `PYTHONPATH`. It does not spawn a Python child, inspect `kpharness.__file__`, verify that all imported modules resolve under the snapshot, or exercise a shadowing package in the working directory.

Required disposition: add a subprocess-free equivalent using an import hook, or a tightly controlled Python child test, that proves resolved module paths and refuses an injected/shadowed package. Keep it host-only and do not launch Gamescope or Wine.

## Conditions that passed

- `python3 -m py_compile` passed for `gamescope_snapshot.py` and `gamescope_xwayland.py`.
- `PYTHONPATH=scripts/harness python3 tools/kpharness_gamescope_backend_test.py` passed **27/27**.
- Snapshot tests reject a changed imported helper and a missing copied module.
- Snapshot creation uses a temporary directory, per-file digest checks, before/after closure comparison, canonical JSON, a manifest digest sidecar, and an atomic directory rename.
- Lease evidence is written before spawn (`prepared`), after owner identity capture (`leader_spawned`), after readiness-child validation, and after renderer readiness (`ready`).
- Lease evidence records owner PID/start, parent PID/start, PGID, and session for the Gamescope leader; receipts intentionally omit the Xauthority path and cookie.
- Cleanup checks PID start identity and expected PGID/SID before `killpg`; the focused PID-reuse test confirms it refuses to signal a changed identity.
- Focused tests cover a pre-readiness process exit and verify a failed boot plus passed cleanup evidence, and cover repeated close/cleanup ordering.

## Acceptance decision

The slice is **not acceptance-ready**. The highest-priority repairs are C1 and C2: produce a run-level manifest that closes over all live inputs/artifacts and prove that the actual driver imports only the manifest closure. Then repair C3 and I2 so rejected readiness children and cleanup failures have durable terminal evidence. I1, I3, I4, I5, and I6 should be closed before treating the receipt as release-quality provenance.


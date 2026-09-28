# Pioneer attached-policy and transactional authoring foundation

Status: SOURCE FROZEN for independent review,2026-09-22. This is the bounded foundation assignment, not completion of play/pause/fastforward/rewind or RenPy-like game-state control. Sole-writer ownership was observed; no native/projectile/CMake/index/commit/game changes. The controller copied a stable intermediate harness snapshot before the final portability changes; that private snapshot must not be presented as this final source.

## Changes

- Pioneer now invokes the existing ScenarioRunner execution-policy setup in attached mode before the SAME run_step interpreter. Attached1x explicitly calls speed rather than assuming a fresh process. Temporary speed is captured through existing kp.game_speed(), restored on completion/failure if still owned, and restoration acknowledgement is required. Same-session validation precedes setup/restoration. Successful explicit speed steps retain their effect, even if equal to route policy; independently changed values are not overwritten.
- Shared scenario helper preserves full managed-run behavior and its existing fresh-process1x opt-out. No new interpreter, control daemon or native API introduced.
- Pending transactions journal issued BEFORE live dispatch. Exact original route bytes/settings, requested step, expected index and attached session/runtime identity are bound to provenance. Completed results are digested. Unresolved pending work cannot be overwritten; timeout/restoration failure/session-or-route change leaves noncommittable issued work. No automatic retry of mutations.
- Commit reconnects to the recorded target, verifies live PID/build/session start/path/port metadata and nonregressing uptime, route/settings/index/step/result provenance and exact rendered candidate. Legacy/malformed/stale/foreign/unfinished receipts reject. Force only permits an explicitly failed recorded result and cannot bypass provenance.
- Atomic same-directory writes preserve original authored TOML bytes/comments/line endings and file permission bits. Committing journal precedes route replace; committed receipt remains for idempotent retry. A crash after route replacement but before receipt completion is recognized by exact candidate hash and cannot append twice.
- Advisory per-route locks serialize init/step/commit/discard/append helpers. Linux/macOS use flock; Windows uses msvcrt byte-range locking. Windows skips unavailable stdlib directory fsync while retaining file fsync+atomic replace. Synthetic platform-adapter tests cover Windows branches; no actual Windows execution claim.
- Discard CLI/help/docs explicitly say metadata-only: live side effects are NOT undone. No fabricated rewind, world pause or playback completion claim.

## Validation executed

1. `python3 tools/kpharness_pioneer_policy_test.py`:21 PASS(final rerun0.102s). Uses real temporary route/pending files and real ScenarioRunner.run_step with a synthetic channel; no game. Covers attached1x/default16x and restoration, explicit speed preservation, failures/restart, issued-before-dispatch, lock exclusion, target mismatch, unrenderable input, stale content/settings/session/build/uptime, malformed/legacy receipts, CLI path, atomic-commit retry windows, preserved CRLF/comments, symlink-route refusal, metadata-only discard, and Windows adapter branches.
2. `python3 tools/kpharness_offline_test.py TestPioneer TestScenario`:57 PASS(57.151s). Existing full-run policy and actual scenario dispatch regression suite. Later changes were confined to Pioneer receipt validation/locking and dedicated tests/docs; existing TestPioneer rerun7 PASS(final0.003s).
3. `python3 -m py_compile` scoped four Python files:PASS.
4. Scoped `git diff --check`:PASS. Read-only Git check; no index mutations.

No game, native build or live acceptance performed. File hashes below identify reviewed/tested source; existing fake-channel tests do not prove live speed control or durability on real Windows filesystems.

## Limits and next required slice

Compare-and-restore speed is not a native multi-owner token service: another owner writing the identical scalar is indistinguishable. Session identity catches ordinary replacement/restart but is not a native load epoch; no claim that game state remained unchanged in-process. Receipt hashes detect accidental drift, not deliberate local forgery. Advisory locks cannot enforce cooperation from arbitrary external editors; detected edits fail, but no filesystem compare-and-swap against noncooperating writers is claimed. Atomic replacement on Windows lacks stdlib directory-fsync durability.

Full playback remains required. Next bounded implementation: one persistent attached owner and command queue holding a single Channel, shared runner, execution cursor and job state; implement play/stop/fastforward using existing dispatch, cooperative wait cancellation, owned speed restore and no game teardown. Use controller pioneer-controls-brief.md. Add native symmetric pause ownership and async checkpoint completion/restore verification before advertising world pause or rewind. Then pending-step rollback and branch-after-rewind must restore actual native game state plus declared mod state, not delete metadata or move a route cursor. Preserve the full RenPy-like quest/inventory/party/object/effect/dialog restoration goal and explicit Lua-timer/VM limitations.

## Scoped final source hashes
- scripts/harness/kpharness/pioneer.py SHA256 `99070d2cf16d5712bdc064c870b59c928ad5b62d8d4ca92404b2726b5eeb1230`
- scripts/harness/kpharness/cli.py SHA256 `371063fd6fd73b6a0e74879e1b94056ae566e3c4d293a9d71e14461dc8e1ad37`
- scripts/harness/kpharness/scenario.py SHA256 `70fd23042892700f9b7a266607737939533e781a888c6fb03a07fe62a93f580a`
- tools/kpharness_pioneer_policy_test.py SHA256 `e39fcbe245e8153dd7f4c403147d5be5ecf8de521e8ba84cab4d92c0f4347120`
- docs/pioneer-authoring.md SHA256 `a36fabfaee9b10cc8a9332ab0df3ec811d962d4270d05f04641f9b0b2011b26c`

# Dead-event registration independent review

Date: 2026-09-28. Worktree reviewed:
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
No product files or ledger entries were edited by this review. Host-only tests
were used; no Wine/game launch and no live-game lock.

## Claims

claim: `kp.events.register` now refuses an event only when its contract is
actually undispatchable, while preserving live EventHandler registrations.

referent: `src/api/compat.cpp:112-133` retains the existing nonexistent-game
constant refusal and then calls `events::find(event)` plus
`!events::dispatchable(*contract)`. `src/events/table.cpp:53-59` routes
`outer_event_id >= 0` through `find_by_site(hook_site, outer_event_id,
event_type) == &ev`; direct-name events are checked against the eight names in
`:46-49`.

checked: rebuilt and ran `tmp/lifecycle-cfg/kp_namespacetest` for both default
K1 and the `k2` argument. Both reported `namespace contract: 0 failure(s)`.
The test explicitly asserts false for `OnCreatureDamaged` and
`OnDialogConditional`, and true then unregisters `OnCreatureAttacked` and
`OnModuleHeartbeat` (ordinary and SIGNAL_EVENT routing).

verdict: holds

confidence: high for the host contract.

claim: the eight direct-dispatch names are grounded in current call sites and
are shared by K1/K2.

referent: `rg -n "find_contract\\(|events::find\\(|set_lifecycle\\(" src`
finds direct lookups in `src/runtime/hook_bodies.cpp` for
`OnRunScriptDone`, `OnRunScript`, `OnTick`, `OnConsoleCommand`, `OnSave`, and
`OnLoad`; `src/runtime/runtime.cpp` looks up `OnScriptLoad` and
`OnScriptUnload` and passes them to `Host::set_lifecycle`. The same runtime
hook bodies are used by both game builds; the generated event table is shared.

checked: source search and line inspection; both K1 and K2 namespace test
invocations passed.

verdict: holds

confidence: high, subject to re-audit if a game-specific event table or a new
direct lookup is introduced.

claim: the documented 14 dead names agree with the implementation's table-wide
classification.

referent: `tools/kp_namespacetest.cpp:60-91` enumerates the 14 names from the
"Dead names" documentation, verifies each table entry's
`events::dispatchable()` result, and verifies all 14 are present. The direct
registration assertions are at `:205-221`.

checked: current rebuilt test passed for K1 and K2. `docs/user/api-status.md:181-188`
describes the dead `vm.run_script` names and the new false-return behavior;
`docs/lua-api.md:9` documents the same contract.

verdict: holds

confidence: high for the checked table/docs snapshot.

claim: the stale object-blaster mock follow-up is resolved in the current
worktree.

referent: `tools/tests/examples/object_blaster.lua:7-11` now states that the
fixture dispatches only `OnCreatureAttacked`; `:199-215` asserts that
`OnCreatureDamaged` registration returns false and retains no callback.

checked: `luajit tools/tests/examples/object_blaster.lua` produced 17 PASS
cases and `all checks passed`, including
`OnCreatureDamaged registration is refused and retains no callback`.

verdict: holds

confidence: high for this mock suite; it remains a Lua-level fixture and does
not prove live engine delivery.

claim: the changed implementation compiles and the real namespace target was
rebuilt from the current source.

referent: `cmake --build tmp/lifecycle-cfg --target kp_namespacetest --clean-first -j2`
was run after the source edits; its build receipt is
`/home/brunner56/kp-live-20260922/dead-event-namespacetest-build-current.log`.
The prior incremental receipt is also retained at
`dead-event-namespacetest-build-current.log` only if its final `build_rc=0`
line is present; the executable hash is recorded alongside the receipt.

checked: The clean target command was
`cmake --build tmp/lifecycle-cfg --target kp_namespacetest --clean-first -j2`;
it returned `build_rc=0`, with the exact receipt in
`/home/brunner56/kp-live-20260922/dead-event-namespacetest-build-current.log`.
That receipt recorded target SHA-256
`aa479d8ada5ba18cf8674d4dcdcf2fd72c74efc485aa0baed1befefa7154098d`.
Target execution was rerun after that build for K1 and K2. A full
`kphasor_dll` relink was not required for this target review; the changed
`compat.cpp` and `table.cpp` are linked into the target, and the target build
also rebuilt the dependency `kphasor`.

verdict: holds

confidence: medium-high; full Windows DLL relink remains outside this targeted
host acceptance check.

## Grill me

1. Could an `outer_event_id == -1` event be live without appearing in the
   eight-name list? Current call-site search finds exactly the eight direct
   lookups plus the table helper itself. A future direct lookup requires adding
   its name to the same implementation list and test.
2. Is `find_by_site` being used as a different, possibly weaker test? No: the
   helper compares the exact returned contract pointer, including the
   SIGNAL_EVENT `event_type` condition already enforced by `find_by_site`.
3. Does the fixture now model the changed false return? Yes: the 17-case LuaJIT
   suite passes, and the dead registration test checks both false and no
   retained callback.
4. Does the namespace test prove live game behavior? No. It proves the
   contract/table and registration logic with synthetic/offline Lua; live event
   delivery remains unverified.

## Verdict

**PASS.** The dead-event registration change is internally consistent, tested
for both K1 and K2, preserves ordinary and SIGNAL_EVENT live registrations,
and the stale object-blaster mock now matches the false-return contract. The
remaining boundary is the stated one: host tests do not establish live engine
event delivery, and a future direct-by-name dispatch must update the explicit
direct-dispatch set and its table-wide test.

Unsettled question: whether a full production Windows DLL relink exposes any
cross-target link/ODR issue not exercised by `kp_namespacetest`. Single check:
run the configured `kphasor_dll` target with the same current worktree after
the integration writer's changes.

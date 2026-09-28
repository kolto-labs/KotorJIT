# Pause-lease Round 6 independent review

Date: 2026-09-28

Scope: read-only review of `/home/brunner56/kp-live-20260922/pl6-scratch/`
against `pause-lease-r6-snippet-report.md`. No product files, writer scratch,
shared builds, Wine, game, display, or live state were modified.

## Verdict

**CONFIRMED for the standalone publication/owner guard snippet; PARTIAL for
production integration.** The bounded 32-bit executable uses the real
`pause::Machine` implementation. It confirms refusal before publication,
reordered publication, unset owner, and off-thread direct calls without
Machine/native state mutation. It confirms a valid owner can register,
acquire, and release. An actual gate-removal mutant aborts at the unchanged
prepublication assertion. The production source still has no publication
call, no direct caller routed through these wrappers, and no demonstrated
unpublication path.

## Evidence-first claim blocks

claim: The standalone guard refuses prepublish, reordered publication, unset
owner, and off-thread register/acquire calls without state mutation.
referent: `pl6-scratch/publication_direct_caller_test.cpp` exercises the real
Machine through `guarded_register_timer`, `guarded_acquire`, and
`guarded_release` from `pause_lease_snippet2.cpp`.
checked: `timeout 60s sh /home/brunner56/kp-live-20260922/pl6-scratch/run_pl6.sh /home/brunner56/kp-live-20260922/pl6-scratch /tmp/kp-pl6-review` returned 0. Output:
`prepublish=register+acquire_refused; reordered=register+acquire_refused; unset_owner=register+acquire_refused; valid_owner=register_acquire_release_paused_restored; off_thread=register+acquire_refused; no_mutation=1`.
The test checks `status(timer).tracked`, lease count, and native `paused`
state after each refusal.
verdict: CONFIRMED for the standalone snippet.
confidence: high; it links the real 32-bit `pause_lease.cpp`.

claim: A valid published owner can perform real Machine operations.
referent: `publication_direct_caller_test.cpp` binds current-thread ownership,
publishes after `set_hooks_installed`, then invokes real register/acquire/release.
checked: The same executable returned 0, with lease count 1 and native pause
set during acquire, then zero and restored after release.
verdict: CONFIRMED for the standalone snippet.
confidence: high.

claim: The off-thread hook path remains passthrough and state-preserving.
referent: `owner_thread_passthrough_test.cpp` and the hook functions in
`pause_lease_snippet2.cpp`.
checked: The same script returned 0 with
`owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1`.
verdict: CONFIRMED for the standalone snippet.
confidence: high for host behavior; medium for production wiring.

claim: Removing the publication/owner gate causes the executable acceptance
test to go red.
referent: A private `/tmp/kp-pl6-review/pause_lease_snippet2_mutant.cpp`
removed the `direct_caller_can_touch` check from the real snippet's
`guarded_register_timer`; the unchanged publication test and real
`pause_lease.cpp` were compiled and linked against it.
checked: `timeout 10s /tmp/kp-pl6-review/publication_direct_caller_mutant`
returned 134. The assertion was the unchanged prepublish check:
`guarded_register_timer(m, timer) == Status::HooksUnavailable`.
Receipt: `/tmp/kp-pl6-review/mutant.log`.
verdict: CONFIRMED for this actual standalone gate-removal mutant.
confidence: high for snippet mutation sensitivity; no production call-site
claim.

claim: The snippet is wired into the production runtime owner-thread seam.
referent: The current validation-worktree source.
checked: No. `rg` finds no production `bind_pause_hooks_after_install`,
`g_pause` publication, or direct wrapper calls. The concrete existing engine
callback seam is `src/harness/commands.cpp:1492-1496`, where
`after_frame()` invokes `g_adapter->after_frame()` through `engine(...)`; the
native frame paths are `src/runtime/hook_bodies.cpp:1280` and `:1304`, both
calling `kp::harness::after_frame()` after the original frame call. The
startup `DllMain` worker is hook-installation context and is not evidence of
the engine owner thread.
verdict: UNVERIFIED; production integration remains PARTIAL.
confidence: high.

claim: Production publication withdrawal/unpublication is covered.
referent: `pause_lease_snippet2.cpp` and current production source.
checked: The snippet test manually clears `g_pause` for one reordered case,
but the snippet has no production lifecycle unpublish function or test that
withdraws publication after a published Machine while asserting later direct
calls refuse and state remains unchanged. Current source has no production
`g_pause` at all.
verdict: UNVERIFIED.
confidence: high.

## Future owner-capture seam

The smallest credible production seam is the engine callback that already
executes on the native frame thread: capture
`std::this_thread::get_id()` in the immediately enclosing native frame hook or
in the first engine-thread `commands::after_frame()` callback, then publish
the owner identity only after detours and Machine readiness are complete. The
startup worker used by `DllMain`/`Runtime::start` must not be used as owner
identity merely because it installs hooks. The eventual production patch must
route every direct Machine caller through the same publication, readiness, and
owner check, and must demonstrate publication withdrawal before teardown.

This is a seam recommendation, not landed integration evidence. The current
snippet proves the reusable contract only.

## Grill me

1. Does the green snippet prove production safety? No. It proves real Machine
   behavior through scratch wrappers; no production caller uses them.
2. Does the red mutant prove production wiring? No. It proves the standalone
   gate is test-sensitive. A later production-linked mutant must remove the
   actual production guard after integration.
3. Is owner identity established by the startup worker? No. The concrete
   owner candidate is the native frame callback that invokes `after_frame()`.
4. Is unpublication complete? No. The packet manually clears its scratch
   atomic in one test, but no lifecycle unpublish path is wired in production.

## Receipts and freeze state

The writer report records the scratch hash set and `/tmp/kp-pl6-snippet/pl6-run.log`.
The independent rerun returned zero with both direct-caller and passthrough
executables. The gate-removal mutant returned 134 at the exact unchanged
prepublish assertion. No writer scratch or product file was edited by this
review.

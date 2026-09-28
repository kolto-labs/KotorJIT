# Pause-lease Round 5 publication and owner-thread review

Date: 2026-09-28. Scope was limited to
`/home/brunner56/kp-live-20260922/pl5-scratch/pause_lease_snippet2.cpp`,
`owner_thread_test.cpp`, `direct_caller_gate_test.cpp`, the scratch Machine
headers/implementation, and the Round 4/5 reports. No worktree product files,
shared builds, Wine, game, display, or live-game lock were touched.

## Verdict

**Round 5 publication/owner-thread packet: PARTIAL.** The standalone snippet
does execute the real scratch `pause::Machine` implementation and its
publication ordering is sound as an isolated host contract. The owner-thread
test also executes the real Machine hook state transitions, but the owner
identity is supplied by the test and no production caller initializes it. The
direct-caller test exercises only a scratch boolean gate; it does not call
`Machine::acquire` or `register_timer` through that gate, and no current
production direct caller is wired. Therefore these claims are not yet
CONFIRMED as integration/publication evidence.

## Claim blocks

claim: `bind_pause_hooks_after_install` publishes a ready Machine only after
hook installation and owner-thread state are initialized.

referent: `pl5-scratch/pause_lease_snippet2.cpp:105-116` stores the original
callbacks, calls `machine.set_hooks_installed(...)`, stores the supplied owner
thread with release ordering, and performs the release-store to `g_pause` last.
The hook bodies acquire-load `g_pause` before checking
`ownership_available()`/calling Machine methods.

checked: `/tmp/kp-r5-snippet/owner_thread_test` ran and printed
`owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1`.
The executable links the real scratch `pause_lease.cpp` and calls the real
`Machine::register_timer`, `Machine::acquire`, `set_hooks_installed`, and
`loading` methods.

verdict: **CONFIRMED** as an isolated scratch publication ordering contract.

confidence: high for the snippet's release/acquire ordering; medium for
integration because the file header says it is not in the build graph and the
production detours are not wired.

claim: the owner-thread guard forwards worker calls and avoids Machine state
mutation.

referent: `pause_lease_snippet2.cpp:61-93` calls Machine methods only when the
acquired owner thread matches; off-thread calls increment a diagnostic counter
and forward to the original callback. `owner_thread_test.cpp:27-39` binds the
current test thread, acquires a real lease, invokes the hook on the owner and
on a worker, and checks `machine.loading()==false`.

checked: `/tmp/kp-r5-snippet/owner_thread_test` output above; no production
caller or live thread-affinity receipt exists.

verdict: **PARTIAL**.

confidence: high for the isolated owner/worker behavior; medium for the
production contract. The owner identity is passed explicitly by the test to
`bind_pause_hooks_after_install`; the source search and Round 5 report show no
production call that supplies the actual engine owner thread.

claim: all direct callers are prevented from touching Machine before the
published/ready boundary, including reordered publication.

referent: `direct_caller_gate_test.cpp:18-30` sets `g_pause` null, then
published, then deliberately publishes after clearing hook readiness. Its
`direct_caller_can_touch` helper returns the conjunction of the published
pointer, `machine.ownership_available()`, and owner-thread equality.

checked: `/tmp/kp-r5-snippet/direct_caller_gate_test` printed
`direct caller before publish=refused; after publish=allowed; reordered publish=refused`.
However, the test never invokes `Machine::acquire` or `Machine::register_timer`
through `direct_caller_can_touch`, and `rg` over the current worktree finds no
production direct caller wired to this helper or to a shared publication gate.

verdict: **PARTIAL**, not CONFIRMED.

confidence: high that the three-state helper result is reproduced; high that
the requested direct-caller execution proof is absent. The settling check is a
test that races an actual direct `acquire/register_timer` caller against
installation and proves it cannot return `Ok` until publication and hook
readiness both hold.

claim: the owner thread is initialized safely before publication in production.

referent: the snippet's `bind_pause_hooks_after_install` takes an explicit
`std::thread::id owner_thread` and stores it before `g_pause`. Its own comment
identifies the intended current caller as the DllMain `CreateThread` worker
(`dllmain.cpp:70 -> run_startup -> Runtime::start -> install`).

checked: source inspection only. There is no production call site in the
current tree and no assertion rejecting a default/unset `std::thread::id`.
The owner test supplies `std::this_thread::get_id()` directly at
`owner_thread_test.cpp:28`, so it cannot establish production initialization.

verdict: **UNVERIFIED**.

confidence: high. The one settling check is a source-linked integration test
showing the actual install thread passes its identity, rejects unset identity
before publication, and then exercises both owner and worker hook calls.

claim: the Round 5 packet proves the real engine `on_fail` publication/cleanup
path.

referent: `/home/brunner56/kp-live-20260922/pause-lease-r5-review.md:132-150`
explicitly records that the linked fixture covers only the timeout to
`finish_load`; the real `GameAdapter::load_save()` `on_fail` lambda remains
unexecuted because the parsed bindings, save inputs, pointer graph, and
callable engine sites are not supplied.

checked: the Round 5 report's linked fixture receipt and its source-mutant
receipt; no new build was run here.

verdict: **FAIL** for a claim of `on_fail` runtime coverage; overall pause
integration remains **PARTIAL**.

confidence: high; this limitation is directly acknowledged by the current
Round 5 report and is separate from the isolated publication/owner snippets.

## Required integration gate

Do not mark the pause packet CONFIRMED from these scratch receipts alone. The
minimum next evidence is:

1. A production source call site that initializes owner-thread identity and
   publishes `g_pause` only after hook readiness, with an explicit refusal for
   unset identity.
2. A production direct-caller wrapper or equivalent shared gate used by every
   `acquire/register_timer` caller, plus a race test that exercises those real
   calls across null, published, and reordered states.
3. A bounded linked fixture for the real `load_save()` `on_fail` branch and a
   source mutation removing that branch's cleanup that makes the executable go
   red.
4. A final source inspection proving installation/publication and any waiting
   calls remain outside DllMain/loader-lock execution.

## Grill me

1. Why does the owner test not establish the real owner thread? It passes
   `std::this_thread::get_id()` directly from `main` into a scratch helper; no
   production installation call is present. The exact source and output are
   `owner_thread_test.cpp:27-39` and `/tmp/kp-r5-snippet/owner_thread_test`.
2. Does the direct-caller green output prove `acquire/register_timer` safety?
   No. The helper returns a boolean and the test never calls either Machine
   method through it; `direct_caller_gate_test.cpp:18-30` is only a publication
   state model.
3. Does the linked Round 5 engine fixture close all cleanup paths? No. The
   current report confirms only timeout -> `finish_load`; its `on_fail` path is
   explicitly unexecuted at `pause-lease-r5-review.md:132-150`.

Open question: what production-owned install seam supplies the actual owner
thread and direct-caller gate? The single settling check is a source-linked
host fixture that calls that seam, races the direct callers, and runs the
`on_fail` source mutant red.

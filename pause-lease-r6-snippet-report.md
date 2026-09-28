# Pause-lease Round 6 isolated publication snippet

Date: 2026-09-28. This packet is isolated under
`/home/brunner56/kp-live-20260922/pl6-scratch/`. `pl5-scratch` and
`pl5-review-scratch` were not modified. No product/runtime files, shared
builds, Wine, game, display, or live-game lock were touched.

## Verdict

**CONFIRMED for the repaired standalone snippet; PARTIAL for production
integration.** The current 32-bit host executables link the copied real
scratch `pause::Machine` implementation and execute guarded
`register_timer`, `acquire`, and `release` operations. Prepublish, reordered
publication, unset owner, and off-thread calls exercise both registration and
acquisition and refuse with `Status::HooksUnavailable`; timer status, lease
count, and native paused state remain unchanged. A valid owner after
publication registers and acquires, observes `paused == true`, then releases
and observes `paused == false`. The native passthrough guard test still passes.
No production caller is wired by this packet, so it does not claim runtime
owner-thread or direct-caller integration.

## Repair implemented in scratch

`pause_lease_snippet2.cpp` now:

- rejects `std::thread::id{}` at the start of
  `bind_pause_hooks_after_install`, before callback/readiness/publication
  state changes;
- returns `bool` from the bind helper so a caller can handle that refusal;
- provides `guarded_register_timer`, `guarded_acquire`, and
  `guarded_release`, each performing the same acquire-loaded
  `g_pause == &machine`, `ownership_available()`, and owner-thread checks
  before invoking a real Machine method;
- returns `Status::HooksUnavailable` on a rejected direct call, ensuring that
  refusal cannot mutate timer registration or lease state;
- retains the hook passthrough path and publish-last release/acquire ordering.

The wrappers are a small proof seam, not a claim that the production runtime
already uses them. Production integration must expose the same guard at the
actual direct-call boundary rather than relying on a caller convention.

## Reproducible evidence

The bounded script is
`/home/brunner56/kp-live-20260922/pl6-scratch/run_pl6.sh`. Its commands use
`g++ -m32 -std=c++20 -Wall -Wextra -Werror -pthread` and link the scratch
`pause_lease.cpp`; this exercises the intended x86 ABI rather than an x86_64
`thiscall` approximation. Both the hook callback declaration and the test
original declaration use `KP_THISCALL`.

Command:

```text
sh /home/brunner56/kp-live-20260922/pl6-scratch/run_pl6.sh 2>&1 | tee /tmp/kp-pl6-snippet/pl6-run.log
```

Exit status was `0`. Receipt `/tmp/kp-pl6-snippet/pl6-run.log`, SHA-256
`b55cb0bfaee449c227f29b4c5709cb3ac999cbe66535d5806499c85ac48dacd6`.

The direct-caller executable printed:

```text
prepublish=register+acquire_refused; reordered=register+acquire_refused; unset_owner=register+acquire_refused; valid_owner=register_acquire_release_paused_restored; off_thread=register+acquire_refused; no_mutation=1
```

The owner passthrough executable printed:

```text
owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1
```

Current scratch source hashes:

```text
dc6dc3e8a531d78a8eee0dc174efffe6387b311bdfe85f88f07a7c2111e5ca4b  pl6-scratch/pause_lease_snippet2.cpp
edaf6a1964abd4060f51c6578734065be42451305b06d8155e6daefafd878551  pl6-scratch/publication_direct_caller_test.cpp
96c2299ce1cedd2b7ac569e6c2022348fe628b97ede1bfc7c540443fc7308b7c  pl6-scratch/owner_thread_passthrough_test.cpp
a98f3d7440e7acd609b3d3ca0887d79acf1f09be74573f0e27e704b9af62ce70  pl6-scratch/src/harness/pause_lease.hpp
4c7c7a82bc9292eb8268b179f71855c13db28a2f78440fc344be5ffc3cfd4cd9  pl6-scratch/src/harness/pause_lease.cpp
57453334be570963cd7baf98b09deca684bcefcbc2d5873ef87dfc4a0b2d077c  pl6-scratch/run_pl6.sh
```

### Negative control

`mutant_no_register_gate.cpp` removes only the `direct_caller_can_touch`
gate from `guarded_register_timer`; the unchanged publication test is then
compiled with the same `-m32 -std=c++20 -Wall -Wextra -Werror -pthread`
flags. Compilation returned `0`, but execution aborted at the unchanged
prepublish actual-operation assertion with return code `134`:

```text
mutant_publication_test: publication_direct_caller_test.cpp:37: int main(): Assertion `guarded_register_timer(m, timer) == Status::HooksUnavailable' failed.
```

Receipt `/tmp/kp-pl6-snippet/mutant-register-gate.log`, SHA-256
`96898db2f6a7473dcee86d4b29a92d3e3bcbf07c1ef455d097046633e1839747`; mutant
source SHA-256
`b9e1436d6f8ec0c7e1a1997d7bbaaed43090e13acf4a25d575d150df67e574ae`.
This is evidence that the test detects removal of a wrapper gate rather than
only checking a boolean model.

## Exact future production owner-thread seam

The current source identifies the narrowest engine-thread callback:
`src/harness/commands.cpp:1492-1496` calls `g_adapter->after_frame()` inside
the `engine(...)` hook-body scope. The native frame paths call
`kp::harness::after_frame()` at `src/runtime/hook_bodies.cpp:1280` and `:1304`.
The future production integration should capture
`std::this_thread::get_id()` at that engine-thread callback (or immediately
inside the selected native frame hook), publish it only after detours and
Machine readiness are complete, and use that identity for direct wrappers.
The startup `DllMain` `CreateThread` worker is a hook installer, not evidence
of the engine owner thread, and must not supply this identity merely because
it installs hooks.

The current source has no production
`bind_pause_hooks_after_install` call, no `g_pause` publication call, and no
direct Machine caller routed through these new wrappers. That absence is
intentional in this scratch-only task and keeps the result separate from
production integration.

## Claim blocks

claim: the repaired direct-caller guard refuses prepublish, reordered, unset,
and off-thread calls without state mutation.

referent: `pl6-scratch/publication_direct_caller_test.cpp:35-75` invokes real
Machine operations through the guarded wrappers and checks timer status, lease
count, and native paused state after every refused case.

checked: `sh pl6-scratch/run_pl6.sh`; direct executable output above; m32
compile and run returned zero; current receipt hash above.

verdict: CONFIRMED for the standalone snippet.

confidence: high; the test uses real Machine methods and the intended 32-bit
ABI.

claim: owner-thread passthrough remains nonfatal and state-preserving.

referent: `owner_thread_passthrough_test.cpp:27-42` binds the current thread,
acquires a real lease, then invokes the hook from owner and worker threads.

checked: same m32 receipt; owner output above.

verdict: CONFIRMED for the standalone snippet.

confidence: high for host behavior, medium for production wiring.

claim: every production direct caller is now guarded.

referent: none; this packet changes only `pl6-scratch`.

checked: bounded source review finds no production bind helper or direct-caller
wrapper call.

verdict: UNVERIFIED; production integration remains PARTIAL.

confidence: high; a production call-site review and linked host test are still
required.

## Grill me

1. Why is the DllMain startup worker not the owner? The runtime chain identifies
   it as the hook installer, while the native frame hook calls
   `commands::after_frame()` on the engine callback thread. The future capture
   seam is `commands.cpp:1492-1496` / `hook_bodies.cpp:1280,1304`, not the
   startup worker.
2. Does this prove production direct callers? No. It proves real Machine
   operations through scratch wrappers. The current source has no production
   wrapper call; the required next evidence is a linked integration test.
3. Can snippet confirmation be separated from integration proof? Yes. The
   snippet establishes the reusable publication contract without claiming
   production wiring. A later integration review must independently prove the
   actual callback, every direct caller, publication/unpublication order, and
   linked `on_fail`/terminal paths.

Open question: which exact native frame hook is selected for the final build
configuration between the two existing `hook_bodies.cpp` call sites? The
settling check is a source/configuration review that identifies the installed
frame hook and shows owner capture executes there before publication.

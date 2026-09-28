# Pause-lease Round 5 independent review

Date: 2026-09-28

Scope: independent review of the Round 5 scratch repairs under
`/home/brunner56/kp-live-20260922/pl5-scratch/`, against
`pause-lease-r4-review.md`, `pause-lease-r5-brief.md`, and the appended Round 5
report in `pioneer-stage1-pause-lease-report.md`. No worktree product files,
Browser A1 files, shared builds, Wine, game, or live processes were touched.
Private review artifacts are under `pl5-review-scratch/`.

## Verdict

**Pause-lease Round 5: PARTIAL.** The Armed timeout helper and the scratch
publication/owner-thread demonstrations hold as isolated host evidence. The
claimed engine terminal linkage does not hold as runtime linkage evidence:
`engine_linkage_probe.py` is a lexical regex/mutation check over source text,
and the only engine compile is `-fsyntax-only`/object compilation. No binary
containing the real `GameAdapter::load_save()` and `finish_load()` call sites
was linked or executed. Integration remains gated.

## Claim blocks

claim: The Armed state has a bounded timeout and clears the load lease once.
referent: `pl5-scratch/armed_timeout.hpp` defines `kArmedTimeout{60}` and a
`>=` check; the extracted test asserts 59s false, 60s true, one cleanup call,
`loading=false`, and no later cleanup.
checked: `g++ -std=c++20 -Wall -Wextra -Werror -I/home/brunner56/kp-live-20260922/pl5-scratch armed_timeout_test.cpp -o /tmp/kp-r5-snippet/armed_timeout_test && /tmp/kp-r5-snippet/armed_timeout_test`; preserved output says `armed timeout: 60s; terminal end_load calls=1; loading=false; later frame calls=0`; the `>` mutation abort receipt is in the Round 5 report.
verdict: holds
confidence: high for the extracted helper; medium for the actual engine call site because that call site was not linked/executed.

claim: `engine_linkage_probe.py` proves the real engine terminal call sites are linked and covered by mutation tests.
referent: `pl5-scratch/engine_linkage_probe.py` reads `engine_k1.cpp` with regexes, copies the text twice, removes a matching `pause_machine_.end_load()` substring, and checks whether the regex still sees it. It invokes no compiler, linker, executable, or `GameAdapter` method.
checked: `python3 /home/brunner56/kp-live-20260922/pl5-scratch/engine_linkage_probe.py` emits “on_fail mutation: detected missing cleanup (red)” and “finish_load mutation: detected missing cleanup (red)”; source inspection shows only `Path.read_text`, `source.replace`, regex, and assertions.
verdict: does not hold
confidence: high; the probe is lexical text evidence only and cannot detect dead code, wrong object selection, macro/configuration effects, or whether the mutated call site is executed.

claim: The scratch `engine_k1.cpp` has been compiled in a way that establishes native adapter linkage.
referent: Round 5 records `clang++ -m32 ... -fsyntax-only` and the review report records a private `-c` object compile. Neither produces a linked executable.
checked: private command `clang++ -m32 -std=c++20 -Wall -Wextra -Werror -Ipl5-scratch/src -I<worktree>/src -c pl5-scratch/src/harness/engine_k1.cpp -o pl5-review-scratch/engine_k1.o` returned `rc=0`; `nm -u` shows unresolved project symbols including `make_k2_adapter`, `pause::Machine::begin_load`, `runtime::Runtime::instance`, `runtime::enter_hook_body/leave_hook_body`, `runtime::active_multiplayer_transport`, `hooks::HookSet::original`, `platform::is_readable/set_protection/log`, and runtime path helpers. A bounded link of that object plus `pause_lease.cpp` returned `rc=1`, beginning with missing `main` and the same unresolved runtime/platform/hook/adapter symbols (`pl5-review-scratch/link.log`).
verdict: unresolved
confidence: high that compile-only proof is real; high that runtime linkage is absent. The smallest missing closure is an executable harness plus those production objects/stubs, with a real call path into `load_save()` and `finish_load()`.

claim: Direct callers are blocked until publication and rejected under reordered publication.
referent: `pl5-scratch/direct_caller_gate_test.cpp` exercises the scratch `direct_caller_can_touch` bridge with null/published/reordered machine state and prints the three expected decisions.
checked: preserved `/tmp/kp-r5-snippet/direct_caller_gate_test`; source and output inspected. No current product caller is wired.
verdict: holds
confidence: medium; this proves the scratch bridge contract, not runtime integration or a race with actual hook installation.

claim: The owner-thread guard forwards worker calls without mutating Machine state.
referent: `pl5-scratch/owner_thread_test.cpp` binds scratch hooks with the current thread, acquires a lease, calls owner and worker hooks, and checks worker forwarding plus unchanged state.
checked: preserved `/tmp/kp-r5-snippet/owner_thread_test` output: `owner hook suppressed=1; worker passthrough=1; off_thread_calls=1; tool_state_unchanged=1`.
verdict: holds
confidence: medium; scratch bridge only, no production caller or live thread-affinity receipt.

## Smallest feasible real linkage target

The cheapest credible proof is a private 32-bit executable that links the
scratch `engine_k1.cpp` object with a test `main` that constructs the adapter
and drives the terminal transition through a production-owned seam. The
current failed link identifies the first closure explicitly:

- `kp::harness::make_k2_adapter`
- `kp::harness::pause::Machine::begin_load` and the pause-lease implementation
- `kp::runtime::Runtime::instance`, `enter_hook_body`, `leave_hook_body`,
  `active_multiplayer_transport`, `self_module_path`, `directory_of`
- `kp::hooks::HookSet::original`
- `kp::platform::is_readable`, `set_protection`, and `log`
- a `main`/fixture that supplies the address table, bindings, and native field
  reads used by `GameAdapter`

Those dependencies are why a textual mutation probe is insufficient. If the
full adapter closure is too broad, extract the terminal state transition into
a production-owned helper called by `engine_k1.cpp`; link that helper and the
real caller into a private test executable, then mutate the production helper
call to prove the executable goes red. A copied regex or reimplemented model
does not settle call-site execution.

## Grill me

1. Weakest answer: does the green “mutation” output prove the real call is
   executed? No. `source.replace` plus regex only proves the text changed and
   the expected substring disappeared; it never compiles or runs the mutated
   engine path.
2. Does `-fsyntax-only` or `-c` prove linkage? No. The private object has
   unresolved runtime, platform, hook, adapter and pause symbols, and the
   bounded link failed with `rc=1`.
3. Is the Armed timeout useless? No. Its isolated helper test is good evidence
   for the boundary and mutation, but it must be wired into and exercised by
   the actual `step_load_completion()` path before integration acceptance.

Open question: whether the project already has a private adapter fixture that
can supply the missing runtime/platform/hook closure without a game launch.
The settling check is one bounded `-j1` link/run of a real production caller,
followed by the same two call-site mutations at the executable level.

## Round 5 linkage follow-up

The smallest executable proof was completed in the private scratch directory.
`actual_finish_fixture.cpp` includes the real scratch
`src/harness/engine_k1.cpp` translation unit, constructs the real
`GameAdapter`, sets its real `Armed` state and an expired timestamp, and calls
the real public-to-private test route `step_load_completion()` (private access
is enabled only in this fixture). The production `step_load_completion()` then
selects its timeout terminal branch and calls the production `finish_load()`;
the fixture asserts `GaveUp` and exactly one `end_load_calls_`. The real
`pause_lease.cpp` is linked, so the `Machine::end_load()` member call is also
present in the executed path.

claim: A linked executable executes the real engine timeout terminal path into
`finish_load`.
referent: `/home/brunner56/kp-live-20260922/pl5-review-scratch/actual_finish_fixture.cpp`,
the scratch `engine_k1.cpp`, and `actual_finish_fixture`.
checked: `clang++ -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections ... -c actual_finish_fixture.cpp` returned 0; link with `-Wl,--gc-sections` and real `pause_lease.o` returned 0; `timeout 10s actual_finish_fixture` returned 0 and printed `actual GameAdapter::step_load_completion -> finish_load call path: PASS`. Logs are `actual-compile.log`, `actual-link.log`, and `actual-run.log`.
verdict: CONFIRMED for the timeout -> `finish_load` call path and its cleanup counter.
confidence: high for this exact host path; this is not Windows or game proof.

claim: The executable acceptance is sensitive to a terminal-cleanup regression.
referent: `actual_finish_fixture_expectation_mutant.cpp` is the same linked
real TU and route with a deliberately mutated assertion requiring two cleanup
calls after one timeout.
checked: It was compiled and linked with the same objects; execution returned
134 from `assert(adapter.end_load_calls_ == 2)` and emitted the assertion text
in `actual-mutant-run.log`.
verdict: PARTIAL. The executable test goes red for an observable cleanup
contract mutation, but this is an expectation mutant rather than a source
mutation that removes the production `finish_load` call. The earlier lexical
source mutants remain non-evidence for runtime mutation coverage.
confidence: high for test sensitivity; low for arbitrary source-mutation
coverage.

claim: The real `load_save()` `on_fail` lambda path has been exercised.
referent: `GameAdapter::load_save()` in the real scratch TU, including the
`begin_load()` followed by `on_fail()` returns.
checked: No. The fixture does not manufacture a complete `AddressTable`, save
ERF/LASTMODULE input, engine pointer graph, and callable site bindings needed
to reach the post-`begin_load` failure branches. The linked executable uses
typed stubs for platform readability/logging, runtime singleton/path helpers,
hook originals, K2 factory, and unstarted-object destructors; those stubs are
explicitly recorded in `actual_stubs.cpp` and cannot establish live engine
semantics. `load_save()` therefore remains unexecuted evidence.
verdict: FAIL as a claim of on_fail runtime coverage; integration gate remains
PARTIAL.
confidence: high.

## Freeze receipt hardening

Before freeze, both reproducibility scripts were hardened so their green
status cannot be caused by a stale dependency or an arbitrary mutant crash.
Each script now compiles its own real `pause_lease.cpp` and `actual_stubs.cpp`,
uses `ulimit -c 0`, captures mutant output, and requires both exit code 134 and
the exact real loading-state assertion (`adapter.pause_machine_.loading()` for
the timeout route, `a.pause_machine_.loading()` for `on_fail`). Existing logs
were preserved with `.prefreeze`, `.prefreeze2`, `.before-manifest`, and
`.failed-hardening` suffixes before reruns.

The final bounded rerun passed both scripts (`actual_script_rc=0`,
`onfail_script_rc=0`). Hash manifests were generated after the final script
contents and binaries were built:

- `pl5-review-scratch/actual-linkage-manifest.sha256`
- `pl5-review-scratch/onfail-linkage-manifest.sha256`

Each manifest covers the scratch engine and pause-lease sources, fields and
timeout headers, validation-worktree runtime/platform/lua/hooks headers, the
fixtures, private mutant TUs, typed stubs, scripts, and resulting binaries.
The final source-mutant receipts remain `actual-mutant-run.log` and
`onfail-mutant-run.log`; both show the required loading assertion and both
scripts report the expected red mutant while exiting successfully.

## Actual `load_save()` on-fail call-site proof

The smaller private route requested by the owner was completed. The fixture
uses `#define private public` only inside the private test TU to populate the
real adapter's `bound_` map directly; it does not replace `load_save()` or
`pause::Machine`. An empty `AddressTable` is passed to the real constructor,
then the fixture inserts the minimal required bindings. A real 32-bit pointer
graph supplies `g.app_manager`, client/server apps, and their internal
pointers. The fake `app.create_server` binding writes the server pointer into
the real manager object. The client `net_layer` field is deliberately a valid
field binding whose value is zero, forcing the first post-`begin_load()`
failure branch at the production `on_fail("load_save: client.net_layer not
readable")` return.

The fixture also creates private `savenfo.res` and empty valid `SAVEGAME.sav`
inputs under `pl5-review-scratch/onfail-input`, and sets both environment
variables to that private directory. No shared save or game directory is
used.

claim: The real `GameAdapter::load_save()` path enters `begin_load()`, reaches
the real `on_fail()` lambda, and clears the real Machine loading state.
referent: `pl5-review-scratch/onfail_fixture.cpp` includes the real scratch
`engine_k1.cpp`; the real `pause_lease.cpp` and shared typed scratch stubs are
linked.
checked: `run_onfail_linkage.sh` compiled and linked the fixture with
`clang++ -m32 -std=c++20 -O0 -ffunction-sections -fdata-sections` and
`-Wl,--gc-sections`, then ran it under `timeout 10s`. It returned 0 and
printed `actual GameAdapter::load_save -> on_fail call path: PASS`. Assertions
verify the exact `client.net_layer not readable` error, `loading()==false`,
and one cleanup call. Full receipt: `pl5-review-scratch/run_onfail_linkage.log`.
verdict: CONFIRMED for this bounded early post-`begin_load()` failure route.
confidence: high for the host call path and Machine state; fake bindings do
not establish Windows ABI or live-engine semantics.

claim: Removing the production `on_fail()` cleanup call makes the unchanged
fixture fail.
referent: `pl5-review-scratch/onfail-mutant-engine.cpp` is a private copy of
the engine TU with only the `pause_machine_.end_load()` statement inside the
`on_fail` lambda removed. `onfail_mutant_fixture.cpp` points at that copy and
keeps the same loading-state assertion.
checked: The mutant compiled and linked with the same real pause-lease object
and stubs. It returned 134 at `assert(!a.pause_machine_.loading())`; receipt:
`pl5-review-scratch/onfail-mutant-run.log`. The exact command sequence is
`pl5-review-scratch/run_onfail_linkage.sh`, which exits 0 only after observing
the expected red mutant.
verdict: CONFIRMED for this actual source call-site mutant.
confidence: high for the bounded host route; the fake engine bindings remain a
test harness boundary.

At this point the remaining proof boundary is broader load behavior after the
minimal early `on_fail` route, including refused connect and successful
request paths. No product, Browser, shared build, Wine, game, or live files
were modified.

## Source-call-site mutant correction

The follow-up fixture was corrected to use the validation worktree headers at
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src`.
The earlier fixture had accidentally named the main-checkout headers; that
path-binding defect is closed in the private scratch sources and is called out
here so the prior result is not overclaimed.

The green fixture now calls the real `pause::Machine::begin_load()`, asserts
that the real machine reports `loading()==true`, runs the real
`step_load_completion()` -> `finish_load()` timeout route, and asserts that
the real machine reports `loading()==false` afterward. The counter remains a
secondary observation.

claim: Removing the production `finish_load()` call makes the unchanged
executable fixture fail.
referent: `pl5-review-scratch/mutant-engine.cpp` is a private copy of the
scratch engine TU with only the `pause_machine_.end_load()` statement inside
`GameAdapter::finish_load()` removed. `actual_finish_fixture_expectation_mutant.cpp`
points at that copied TU; its assertions are otherwise unchanged for the
machine-state route.
checked: The exact reproducible command sequence is in
`pl5-review-scratch/run_actual_linkage.sh`. The mutant TU compiled with the
same `-m32 -O0 -ffunction-sections -fdata-sections` flags, linked with the same
`-Wl,--gc-sections`, scratch stubs, and real `pause_lease.o`, and ran. It
returned 134 at `assert(!adapter.pause_machine_.loading())`; the output is in
`actual-mutant-run.log`. The unmutated worktree-bound fixture returned 0 and
printed its PASS line.
verdict: CONFIRMED for this actual source call-site mutant and the real
Machine loading-state contract.
confidence: high for the host timeout route; no Windows/game/live claim.

claim: The production `load_save()` `on_fail` path has equivalent executable
coverage for the minimal early failure route.
referent: `GameAdapter::load_save()` post-`begin_load()` failure lambda in the
real engine TU.
checked: Yes for the first post-`begin_load()` `client.net_layer` failure;
the exact fixture, real Machine assertions, and source mutant are documented
above. Broader `on_fail` branches and a successful load remain untested.
verdict: CONFIRMED for the bounded route; overall integration remains PARTIAL.
confidence: high.

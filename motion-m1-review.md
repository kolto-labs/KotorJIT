# Motion M1 independent review — K1 GOG read-only placeable capture

Date: 2026-09-27

Scope reviewed: `kp.motion.capabilities()` / `kp.motion.capture(id)`, the nine
M1 implementation/data files named in the task, the seven M1 hooksite rows,
the M0 safe/keep-out receipts, and the M1 report. This review did not change
the worktree, run Wine/a game, touch the live-game lock, or run an address
generator. Scratch artifacts are under
`/home/brunner56/kp-live-20260922/review-probes-motion-m1/`.

## Resume receipt

The prior writer left these M1 paths untracked: `src/api/motion.hpp`,
`motion.cpp`, `motion_profiles.cpp`, `motion_backend.cpp`, `motion_lua.cpp`,
`motion.cmake`, `tools/kp_motiontest.cpp`, and
`data/adjudication/k1_gog_103_motion_bindings.json`.  The only tracked allowed
file is `data/hooksites.toml`; its total dirty diff is +219 lines because it
also contains an earlier camera block. The M1 portion is the seven rows at
`data/hooksites.toml:2354-2411` (+58 lines). No required review file existed
at this path; `/home/brunner56/kp-live-20260922/codex-runs/motion-m1-review.md`
was a copy of the task prompt, not a partial review.

The prior `kp_motiontest` binary and four MinGW objects existed in the mandated
scratch directory. I re-ran them rather than trusting their timestamps.

## Independent specification pass

### Claims that hold

claim: M1 uses only M0-safe data and leaves the M0 keep-out set out.
referent: `motion-m0-verification.md:183-188` safe list; `src/api/motion_profiles.cpp:12-53`; `data/adjudication/k1_gog_103_motion_bindings.json:41`.
checked: `rg -n '0x3a0|0x3c0|0x3d8|0x50dc40|0x50dfd0|0x52cce0|0x24' src/api/motion* data/adjudication/k1_gog_103_motion_bindings.json` found only the adjudication keep-out declaration, not implementation use.
verdict: holds.
confidence: high; an independent raw-image re-read would be needed to re-prove M0 itself, which is out of M1 review scope.

claim: capture refuses unsupported images/ABIs, checks guards before the getter, fences identity after the getter, and never writes a partial `Capture`.
referent: `src/api/motion.cpp:57-70` (bind), `:81-128` (capture); `tools/kp_motiontest.cpp` test names `guard_flip_refuses_before_call`, `chain_failure_refuses_before_call`, `wrong_vtable_refuses`, `id_roundtrip_mismatch_refuses`, and `unreadable_field_refuses`.
checked: `/home/brunner56/.local/bin/host-cmd sh -c '/home/brunner56/kp-live-20260922/review-probes-motion-m1/kp_motiontest <worktree>'`.
verdict: holds in the synthetic fallible-reader fixture. The run reports 20/20 tests, 2926 checks.
confidence: high for the tested checked core; no live address/ABI proof is implied.

claim: valid `0xffffffff` is not treated as invalid, while `OBJECT_INVALID` is refused before the call.
referent: `src/api/motion.cpp:11,83-84`; `tools/kp_motiontest.cpp` test `motion.accepts_client_id_0xffffffff` and `motion.invalid_object_id_refused_before_call`.
checked: same 20/20 synthetic run.
verdict: holds.
confidence: high.

claim: the native getter ABI is Win32 i386 `thiscall(CServerExoApp*, uint32_t)` with a one-argument callee cleanup (`ret 4`).
referent: `motion-m0-verification.md:55-59`; `src/api/motion_backend.cpp:18-23`.
checked: `/home/brunner56/.local/bin/host-cmd sh -c "cd <worktree> && for f in motion motion_profiles motion_backend motion_lua; do i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2 -Isrc -Ithird_party/luajit/src -c src/api/$f.cpp -o /home/brunner56/kp-live-20260922/review-probes-motion-m1/mingw-rerun/$f.o || exit 1; done"`; exit 0, no compiler output. The source declaration uses `__attribute__((thiscall))` at `motion_backend.cpp:20`.
verdict: holds as a compile-time declaration backed by the M0 disassembly receipt.
confidence: high for call shape, medium for live invocation until the required M1 live proof runs.

claim: the Lua capture object is protected/read-only and failures use `nil, "kind: reason"`.
referent: `src/api/motion_lua.cpp:19-27,60-73,93-105`; `tools/kp_motiontest.cpp` tests `motion.forged_userdata_argerror` and `motion.lua_capture_surface`.
checked: same 20/20 synthetic run.
verdict: holds. The exact closed error prefixes are `unsupported`, `guard`, `chain`, `identity`, and `value` from `motion.cpp:22-25` and `motion_profiles.cpp:62-71`.
confidence: high.

claim: facing stays in `[0,360)` even when a near-360 double rounds upward as a float.
referent: `src/api/motion.cpp:116-121`; `tools/kp_motiontest.cpp` test `motion.capture_reads_server_xyz_and_orientation`.
checked: same 20/20 synthetic run, including the near-360 fixture assertion.
verdict: holds.
confidence: high.

claim: `kp.motion`, `capabilities`, and `capture` do not duplicate an NWScript routine name.
referent: proposed namespace in `fanout-lua-lifecycle-plan.md:93`; Lua registration at `motion_lua.cpp:101-104`.
checked: a recursive JSON name extraction over `data/routines/k1.json` (1,848 name occurrences) and `k2.json` (2,082) intersected their case-folded names with `{motion,capabilities,capture}`; both intersections were empty.
verdict: holds for the exposed routine/module names.
confidence: high.

claim: the seven motion hooksite rows are additive field rows and do not collide with camera rows.
referent: `data/hooksites.toml:2354-2411`; the camera block ends at `:2352`.
checked: `git diff --unified=0 -- data/hooksites.toml` shows the camera and motion blocks are both additions and has no removed line; `rg -n 'motion|server_object.area_id|placeable.aabb_registered' data/hooksites.toml` found each M1 name once.
verdict: holds, with an attribution caveat: the file's +219 statistic must not be represented as M1-only work; only +58 lines are M1.
confidence: high.

claim: the binding material records two derivations rather than relying on a single uncorroborated source.
referent: `data/adjudication/k1_gog_103_motion_bindings.json` citations and `motion-m0-rederivation.md` plus `motion-m0-verification.md`.
checked: source inspection; the M0 verification explicitly says it independently re-derived every safe item at `motion-m0-verification.md:175-187`.
verdict: holds for the stated METHOD-style two-derivation requirement.
confidence: high.

## Adversarial findings

### F1 — FAIL: no engine-thread enforcement or binding, and no production integration

`capture()` makes a direct engine call at `src/api/motion.cpp:93`. The module
has no current-thread predicate, dispatcher, runtime-live predicate, or fault
guard of its own. This matters because repository policy says engine calls are
legal only on the game main thread: `src/harness/channel.hpp:5-8` and
`src/harness/engine.hpp:12-15`. The eventual normal protection is architectural
rather than present in this patch: Lua dispatch is executed from engine hook
bodies (for example `src/runtime/hook_bodies.cpp:699+`), but none of the M1
sources establishes or checks that precondition.

More immediately, `rg -n 'motion' CMakeLists.txt src/runtime/runtime.cpp
src/runtime/runtime.cmake tools/kp_namespacetest.cpp` returned no M1
integration. `motion.cmake` itself says production sources belong in
`runtime.cmake` (`src/api/motion.cmake:1-2`), but `CMakeLists.txt` does not
include the fragment and the runtime never calls `bind_native`, `register_all`,
or `unbind`. Thus the reviewed source can pass its standalone fixture while it
is neither compiled into nor exposed by the actual runtime.

This does not authorize touching the shared integration files: the plan makes
I-M a serialized integration task (`fanout-lua-lifecycle-plan.md:165-170`). It
does mean the submitted M1 behavior is incomplete and cannot claim an
engine-thread guarantee.

Required resolution owner: the serialized I-M integrator. It must add the
motion production sources and lifecycle calls, register the API, and document
the exact engine-thread gate (or make an explicit runtime assertion/dispatch
that turns an off-thread request into `nil, "unsupported: ..."`). Then run the
normal runtime-linked namespace test and the M1 live disposable-footlocker
oracle from plan line 171 under the controller's lock.

### F2 — contract mismatch: `capabilities().reads` is a string, not a list

The implementation pushes one space-delimited literal at
`src/api/motion_lua.cpp:82-84`. The writer report describes `reads` as “a list
of field names.” A Lua caller receives `type(kp.motion.capabilities().reads) ==
"string"`, not a table. The plan does not prescribe a representation, so this
is not independently a safety failure; it is nevertheless a public-contract
mismatch against the accompanying report/doc proposal. Resolve before public
documentation: either return a fresh Lua array or describe it explicitly as a
space-delimited string and add an assertion in `motion.lua_capture_surface`.

### Non-finding: dangling/freed pointer and ID reuse

The code cannot make arbitrary process memory safe once the engine getter has
returned a pointer. It does minimize the window: every capture repeats all
guards, traverses the current manager/server/internal/array chain before the
call (`motion.cpp:83-93`), then validates the returned object’s vtable, type,
and round-trip ID (`:94-101`) before fields, and obtains fields through the
fallible reader (`:103-126`). The synthetic tests cover unmapped chain,
vtable, field, and wrong-ID cases. This holds as a bounded defensive design;
the race between a successful read and a concurrent free is unresolved without
the engine-thread guarantee in F1. No live test currently proves ID reuse.

## Writer grill-me check

The writer’s weakest implied question is whether the direct getter is safely
confined to the engine thread. That does not hold yet: the source evidence
above shows neither a guard nor integration. The synthetic fixture proves
ordering/refusal, not thread affinity. The single settling check is a
runtime-linked test that exercises `kp.motion.capture` from the main hook
dispatch and a deliberate off-thread/harness request that is rejected before
the getter; then the controller performs the plan’s live footlocker oracle.

## Verdict

**Motion M1 verdict: FAIL.**

The checked core, profile guards, Lua userdata, K1-GOG `thiscall` declaration,
safe-list discipline, hooksite separation, and bounded synthetic/MingW checks
are good. The result is not a shippable M1 surface until serialized I-M makes
the feature part of the runtime and proves/enforces its engine-thread
precondition. No live game/readback claim is made.

## Re-run evidence

* `review-probes-motion-m1/kp_motiontest`: **20/20 passed, 2,926 checks**;
  synthetic memory only, exit 0. Saved as `rerun-kp_motiontest.txt`.
* i686-w64-mingw32 compilation of the four M1 sources: **4/4 object files,
  exit 0, no warnings**. Saved as `rerun-mingw.txt` and `mingw-rerun/*.o`.


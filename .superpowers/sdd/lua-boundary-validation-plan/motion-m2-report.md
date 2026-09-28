# Motion M2 + engine-thread gate: writer report (host-tested)

Date: 2026-09-27. Sole writer. Resumed a writer that was cut off after its red run; its sources were kept after the checks below.
Spec: `/home/brunner56/kp-live-20260922/motion-m2-plan.md`. `W/` = this worktree.
No game, no Wine, no git write, and the live-game lock was never touched. No forbidden file was edited (`src/runtime/**`, `src/lua/**`, `CMakeLists.txt`, `kp_namespacetest.cpp`, `src/api/camera*`, `data/addresses/*.json`, `src/hooks/**`).

## Rulings applied

- `allow_stale_collision` is an explicit per-call opt-in. The default is refuse. It is documented in `capabilities().limits`, and test `motion.capabilities_tables` asserts that text.
  - Unknown `opts` keys are refused, so the typo `allow_stale_colision` cannot fall back to the default (`motion.lua_relocate_surface`).
- M2b settle (Remove/Add) and M3 auto-restore are out of scope. `motion.hpp` has an "M3 hook point" block that states the `release_state` contract. Nothing implements it.
- Camera and model do not adopt the gate here. Only `motion*` calls `engine::on_engine_thread()`.

## Files

| File | State |
|---|---|
| `W/src/api/engine_gate.hpp`, `.cpp` | new. `bind_gate`, `on_engine_thread`, `gate_refusal`. A seqlock over (probe, context): fails closed when unbound, and a reader that sees a rebind in flight is refused |
| `W/src/api/motion.hpp` | M2 types: `Writer`, `Status`, `Observation`, `Entry`, the policy constants, `bind_owner_probe`, `bind_tick`, `state_token`, and the M3 hook-point comment |
| `W/src/api/motion.cpp` | `relocate`, `restore`, `observe` and the ledger. Rules R1..R12 run in plan order. The gate is asked before any read |
| `W/src/api/motion_lua.cpp` | `kp.motion.relocate/restore/observe`. A per-state owner token lives in the registry. `capabilities` gains the `reads`/`writes`/`refusals` tables and the `limits` text |
| `W/src/api/motion_backend.cpp` | the native thiscall `set_position` adapter (Win32 i386 only) |
| `W/src/api/motion_profiles.cpp` | 5 new SetPosition spans, read from the raw image |
| `W/src/api/motion.cmake` | adds `engine_gate.cpp` to `kp_motiontest` and adds a new `kp_enginegatetest` target. Still included nowhere (I-M2) |
| `W/tools/kp_enginegatetest.cpp` | new, 5 tests |
| `W/tools/kp_motiontest.cpp` | +34 M2 tests (51 total) |
| `W/data/adjudication/k1_gog_103_motion_bindings.json` | `CSWSObject::SetPosition` row (two derivations, bytes). This session added its `sqlite_func` signal (METHOD.md function rule, signal one) |
| `W/data/hooksites.toml` | not edited. `server_object.set_position` already exists at `:394` |

This session's edits to the previous writer's work:
1. `kp_motiontest.cpp` `restore_conflict_when_moved_by_other_writer_no_write`, third block.
   - The test was wrong, not the code. It used `refused_write()`, which asserts that the ledger is unchanged, on the one refusal that deliberately drops the entry.
   - It is replaced by inline checks: `conflict` kind, no setter call, output untouched, entry gone. The block also checks that the other writer's pose survives and that the same script can then start over, with the new origin.
2. The bindings JSON `sqlite_func` field. Referent: a read-only query of `kotorxid.sqlite` `func` where binary_id=8 and addr=0x4cd1a0 returns `SetPosition, CSWSObject, USER_DEFINED, size 159, __thiscall, void`.

## Evidence

claim: red first. The M2 tests fail against a stubbed core, and the gate tests fail against a stub gate.
referent: `/tmp/kp-motion-m2/red.txt`: `24/51 tests passed`. The M1 tests pass, plus `write_refused_while_staged`, `capabilities_tables`, `new_spans_match_reference_image` and `names_disjoint...`, which the stub satisfies trivially. Every other M2 test fails with `unsupported: stub: M2 not implemented`. The stub is `/tmp/kp-motion-m2/red/api/` (the gate is forced open and relocate/restore/observe return early). Gate: `/tmp/kp-motion-m2/gate-red.txt` `0/5`, and `gate-naive.txt` `4/5`. A naive two-atomic gate fails `concurrent_rebind_never_tears`.
checked: `diff` of the red copy against `W/src/api` shows only the stub lines.
verdict: holds
confidence: high

claim: green.
referent: `/tmp/kp-motion-m2/green.txt` `51/51 tests passed, 4120 checks` (exit 0). `/tmp/kp-motion-m2/gate-green2.txt` `5/5 tests passed, 18 checks`.
checked: built with `g++ -std=c++20 -m32 -Wall -Wextra -O1` against `KotorPhasor/build/luajit32/src/libluajit.a` and run via `host-cmd`. No warnings.
verdict: holds
confidence: high

claim: the tests kill the rules they name.
referent: 6 source mutants under `/tmp/kp-motion-m2/mut/*`. Every mutant fails at least one test:

| Mutant | Tests that fail |
|---|---|
| core gate removed | `gate_refusal_zero_reads_zero_calls` |
| a4=1 instead of 0 | 4 tests fail: dirty-bit mutation |
| R8 removed | `collision_registered_refused_by_default`, `collision_opt_in_allows`, `lua_relocate_surface` |
| restore fence 6 removed | `restore_conflict_...` |
| R10 removed | `second_owner_refused`, `owner_token_not_pointer` |
| Lua gate removed | `lua_gate_refusal_before_args` (the arg error now wins over the gate) |

checked: run output in this session
verdict: holds
confidence: high

claim: the M2 spans are the image bytes. Nobody typed them from mnemonics.
referent: a Python read of the raw image at `~/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image` gives:
- `0x4cd1b1 e8cad7fdff`, whose call target is `0x4aa980`
- `0x4cd1bd 8b44241c5533ed3bc57507`
- `0x4cd1c8 838efc01000002`
- `0x4cd202 8b0b890f8b53048957048b4308894708`
- `0x4cd212 8b44241885c0`
- `0x4cd238 5d5f5e5bc21000`

All six equal `motion_profiles.cpp:42-55`. The tests `spans_match_reference_image` and `new_spans_match_reference_image` re-read the same bytes; the image was present, so neither SKIPped.
checked: this session
verdict: holds
confidence: high

claim: the mingw build compiles and emits the right thiscall shape.
referent: `i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2 -c` gives OK for motion, motion_profiles, motion_backend, motion_lua and engine_gate (`/tmp/kp-motion-m2/mingw/*.o`). The objdump of `Native::set_position` shows:
- `ecx` = object
- 4 dwords pushed: `&vec`, a2, a3, a4
- `sub $0x10,%esp` after the call, which undoes the callee's `ret 0x10`
- the floats copied with `flds`/`fstps`, which is bit-exact for finite floats (NaN is refused earlier)
checked: this session
verdict: holds for compile and codegen. The live ABI is `unverified` (no game).
confidence: high for the compile, medium for the runtime call

claim: the names are disjoint from NWScript routines.
referent: test `motion.names_disjoint_from_nwscript_routines` passes. It checks 6 names against every `data/routines/*.json` (k1 >= 1848 names, k2 >= 2082).
verdict: holds
confidence: high

Regression set:
- `ctest -L offline`: not run. `motion.cmake` is included nowhere until I-M2, so this change cannot reach any existing target.
- `kp_namespacetest`: not run, for the same reason. It is forbidden to edit here anyway.
- `tools/nwscript_boundary_test.py`: exit 1, with one violation: `docs/devtools-design.md:134: dotted member on removed host root: kotor.lua`. The output is in `/tmp/kp-motion-m2/nwscript_boundary.txt`.
  - That file is staged by other work (`A docs/devtools-design.md` in git status). No M2 file is involved.
  - None of the files touched here is flagged.

## Test list (M2 + G), all green

- G: `engine_gate.unbound_refuses`, `bound_probe_true_allows`, `rebind_nullptr_refuses`, `other_thread_refused` (a real `std::thread` with a latch probe), `concurrent_rebind_never_tears`.
- M2 core:
  - `gate_refusal_zero_reads_zero_calls`: capture, relocate, restore and observe, both gate-closed and unbound; the reads, calls and sets counters do not move.
  - Argument and policy refusals: `nonfinite_refused_zero_calls`, `step_bound_refused`, `dz_bound_refused`, `origin_range_refused`.
  - Stale and area refusals: `stale_capture_pose_refused`, `stale_epoch_refused`, `area_change_refused`, `area_sentinel_refused` (both 0x7f000000 and 0).
  - Collision: `collision_registered_refused_by_default` (markers 3 and 0), `collision_opt_in_allows`.
  - Write and readback: `relocate_single_setter_call_flags_110`, `readback_requires_exact_pos_and_dirty_bit` (skip-dirty, nudge, skip-write, area-change), `readback_mismatch_reports_mutation_and_keeps_entry`, `same_position_reported_noop_zero_setter_calls` (including -0.0 against 0.0).
  - Restore and ownership: `restore_exact_readback`, `restore_refused_after_identity_change` (vtable, type, id, gone, pointer, area; chain failure keeps ownership), `restore_conflict_when_moved_by_other_writer_no_write`, `second_owner_refused`, `write_refused_without_host_owner_core`, `unbind_clears_ledger`.
  - `observe_reports_push_consumed_without_client_read`.
  - `new_spans_match_reference_image`.
- M2 Lua:
  - Gate and ownership: `lua_gate_refusal_before_args`, `write_refused_without_host_owner` (unbound probe and `none`), `write_refused_while_staged`, `restore_allowed_while_staged`, `owner_token_not_pointer`.
  - Surface: `lua_relocate_surface`, `capabilities_tables`, `names_disjoint_from_nwscript_routines`.

## Integration snippets for I-M2 (not applied; forbidden files)

`src/runtime/runtime.cmake`, after the camera sources (`:65-68`):
```cmake
    "${KP_SRC_ROOT}/api/engine_gate.cpp"
    "${KP_SRC_ROOT}/api/motion.cpp"
    "${KP_SRC_ROOT}/api/motion_profiles.cpp"
    "${KP_SRC_ROOT}/api/motion_backend.cpp"
    "${KP_SRC_ROOT}/api/motion_lua.cpp"
```
`CMakeLists.txt`, after `include(.../src/api/camera.cmake)` (`:137`):
```cmake
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/motion.cmake)
```
`src/runtime/runtime.cpp`. Anchor on the camera calls, because the line numbers drift.
```cpp
// next to api::camera::bind_native (~:400)
if(!api::motion::bind_native(image_sha256_,runtime_base_,read_model,nullptr,model_error))
    log("motion: %s",model_error.c_str());
// once at start, before load_all
api::engine::bind_gate(+[](void*) { return live() && engine_thread_latched_is_current(); }, nullptr);
api::motion::bind_owner_probe(+[](lua_State* L, void*) {
    lua::Script* s = lua::Script::owner(L);
    return !s ? api::motion::Writer::None : s->staged() ? api::motion::Writer::Staged : api::motion::Writer::Loaded;
}, nullptr);
api::motion::bind_tick(+[](void*) -> std::uint64_t { lua::Host* h = active_host(); return h ? h->tick() : 0; }, nullptr);
// on_state_created, after api::camera::register_all(L) (~:729)
api::motion::register_all(L);
// next to BOTH api::camera::operations().unbind() (~:817, ~:881)
api::motion::operations().unbind();
// in stop(), before host_.reset(): unbind the gate so nothing passes after stop
api::engine::bind_gate(nullptr, nullptr);
```
`src/runtime/hook_bodies.cpp` `main_loop_body` (`:759`). The latch goes at the very top, **before** the console pump at `:768`, so the console's reads pass on the first tick:
```cpp
static std::atomic<std::uint32_t> g_engine_tid{0};   // 0 = unlatched: every thread refused
std::uint32_t expected = 0; std::uint32_t me = GetCurrentThreadId();
g_engine_tid.compare_exchange_strong(expected, me);
// engine_thread_latched_is_current(): tid != 0 && tid == GetCurrentThreadId()
```
In `client_main_loop_body` and `client_frame_wrapper_body`: compare with the latch, log once on a mismatch, never re-latch.

## Grill me

1. **Is the probe's `Script::owner(L)` really the per-script owner for both the new and the old generation during a hot reload, so that `staged()` refuses both?** (weakest)
   - The plan's reading is `host.cpp:141-148`: the owner key is pushed before `on_state_created`, and `staged_L_` is set.
   - `host.hpp:80` has `staged() { return staged_L_ != nullptr; }`. It is a per-Script flag, so both generations of that script see true.
   - Host-tested only through a fake probe (`write_refused_while_staged`, `restore_allowed_while_staged`). The real `Script` mapping is `unverified` until I-M2 lands `motion_lifecycle.top_level_relocate_refused`, and that is M3 scope.
2. **Why does a relocate by the owner, after someone else moved the object, return `conflict` and release ownership, instead of just moving on?**
   - Otherwise `origin` still names the pre-conflict pose, and a later restore would silently undo the other writer's move.
   - Test: `restore_conflict_when_moved_by_other_writer_no_write`, block 3. After the release, the same script re-owns the object with `origin` equal to the other writer's pose.
   - This is a design choice the plan does not spell out for relocate. The plan states it for restore only (fence 6).
3. **Can a gate refusal ever cost a read?**
   - No. In the core, `motion.cpp:121,207,276,326` ask the gate right after the null-binding check, which reads only members. In Lua, `motion_lua.cpp:38` asks before any argument is touched.
   - Test `gate_refusal_zero_reads_zero_calls` asserts that reads, calls and sets do not change, gate closed and unbound alike. The mutant with the gate removed fails it.
4. **Is the native call bit-exact for -0.0 and denormals?**
   - The adapter copies through `flds`/`fstps` (mingw objdump above). x87 load and store of a finite single is exact, and -0.0 keeps its sign.
   - Readback then compares bit for bit. Denormal behaviour in the live engine is `unverified`.
   - -0.0 against 0.0 is a noop by design (`engine_equal` mirrors 0x4AA980's fcomp), so the setter is never called there.
5. **Why is `restore` allowed from a `Staged` writer, but not from `None`?**
   - Plan R3: "an owner can always put things back". A `None` state (console, harness) has no token that owns anything, and its close never runs `on_state_closing`.
   - Tests: `restore_allowed_while_staged` and `write_refused_without_host_owner` (restore from `none` is refused).

Hand-off: the one question I could not settle is whether K1's client loop runs on the same thread as the server MainLoop. It decides whether the tid latch admits the console's reads from the client body. The single check that settles it is live-proof step 1: log `GetCurrentThreadId()` in `main_loop_body` and `client_main_loop_body` on one tick.

---


## Round 2 (response to `motion-m2-review.md`, FAIL)

Scope this round: `src/api/engine_gate.{hpp,cpp}`, `tools/kp_enginegatetest.cpp`,
`tools/kp_motiontest.cpp`, this report. Motion semantics untouched: `src/api/motion.cpp`
is untracked in this worktree (`git status --porcelain -- src/api/motion.cpp`
shows `??`, not `M`), so there is no tracked baseline to diff against; the
referent for "unchanged" instead is that all six mutant trees under
`review-probes-motion-m2/mut/*/api/motion.cpp` still each differ from the
current `motion.cpp` at exactly the mutant's own change — if this round had
touched `motion.cpp`, at least one of those diffs would have grown. Five are
a one-line swap; `gate_late` is a two-hunk move (deletes the gate check at
`:207`, re-adds it at `:218`, same text). All six, rerun this round
(`diff -u src/api/motion.cpp .../mut/<name>/api/motion.cpp`):

```
stale:     -    if (!bit_equal(cur.position, from.position) || !bit_equal(cur.orientation, from.orientation))
           +    if (!engine_equal(cur.position, from.position) || !bit_equal(cur.orientation, from.orientation))
fence6:    -    if (!bit_equal(cur.position, e.last_written) || !bit_equal(cur.orientation, e.origin_orientation))
           +    if (!engine_equal(cur.position, e.last_written) || !bit_equal(cur.orientation, e.origin_orientation))
readback:  -    if (!bit_equal(after.position, target))
           +    if (!engine_equal(after.position, target))
conflict:  -                 mine->binding_epoch != epoch_ || !bit_equal(cur.position, mine->last_written))) {
           +                 mine->binding_epoch != epoch_ || !engine_equal(cur.position, mine->last_written))) {
flags:     -    backend_->set_position(at(profile_->set_position), before.object, target, 1, 1, 0);
           +    backend_->set_position(at(profile_->set_position), before.object, target, 1, 0, 0);
gate_late: -    if (!engine::on_engine_thread()) return fail(Failure::Unsupported, error, "not on the engine thread");
             (deleted at :207)
           +    if (!engine::on_engine_thread()) return fail(Failure::Unsupported, error, "not on the engine thread");
             (same line re-added at :218, after the getter call instead of before it)
```
No git write, no game, no Wine.

An internal review pass (before handing this back) caught four problems in
the first draft of this round, listed here with what changed as a result:
a red test weak enough to pass clean 1 run in 5, an unverified claim that
`std::mutex` doesn't add a new mingw import, a declined instruction (NaN
cases) that turned out to be a defensible skip only if I actually built the
tests proving why, and a wrong report referent (see "Report-referent
corrections" at the end). All four are folded into the sections below,
not left as a separate errata list.

### F1 — `bind_gate` concurrent-writer tear

**Fix chosen: a plain `std::mutex` around `bind_gate`'s three stores, not a
CAS/spin retry loop.** Criterion from the task: "no lock on the reader
path; minimal change."
- No lock on the reader path: `on_engine_thread()` is untouched — still three
  plain atomic loads, no mutex, no CAS, no retry. Only `bind_gate` (called at
  most a few times per `Runtime` lifecycle: bind at start, unbind at stop,
  plus any future rebind) takes the lock.
- Minimal change: one `#include <mutex>`, one `std::mutex` member, one
  `std::lock_guard` line, versus a CAS-retry alternative that would need to
  reintroduce the parity logic the seqlock already half-encodes (spin on
  odd, retry the read of "am I the one who should proceed") for a path that
  is not hot.
- **Blast radius, checked rather than assumed:** `std::mutex` needs
  `libwinpthread` under mingw's posix thread model
  (`i686-w64-mingw32-g++ -v` → `Thread model: posix`), and the DLL link
  step forbids any new dynamic runtime import (`runtime.cmake:141-144`:
  "A dynamic dependency on libwinpthread-1.dll ... makes the DLL fail to
  load under Wine and reports nothing"). Two checks, not one:
  1. Production code already ships `std::mutex`/`std::thread` through this
     exact link step: `src/harness/channel.{cpp,hpp}` (`std::thread thread_`,
     seven `std::lock_guard<std::mutex>` call sites) is part of
     `KP_HARNESS_SOURCES`, which `runtime.cmake`'s win32 foreach loop
     compiles and the same custom command links into `kphasor.dll` with
     `-static -static-libgcc -static-libstdc++` (`runtime.cmake:107,138-145`).
  2. Direct link test, same flags the DLL uses: a tiny program that calls
     `bind_gate` from a second `std::thread` (`/home/brunner56/kp-live-20260922/tmp-m2r2/mingw_link_test.cpp`),
     built with `i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2 -Isrc
     mingw_link_test.cpp src/api/engine_gate.cpp -static -static-libgcc
     -static-libstdc++ -Wl,--exclude-all-symbols -o mingw_link_test.exe`
     (exit 0). `i686-w64-mingw32-objdump -p mingw_link_test.exe` lists
     exactly two imported DLLs, `KERNEL32.dll` and `msvcrt.dll` — no
     `libwinpthread-1.dll`, no `libstdc++`/`libgcc` DLL. The mutex adds no
     new dynamic import under the DLL's actual link flags.
  My first draft of this round asserted the mutex was safe on the strength
  of a `-c` (compile-only) mingw check, which cannot see link-time imports
  at all — that was an unearned claim; the link test above is the actual
  referent.
- `engine_gate.hpp`'s contract comment is corrected: `bind_gate` may be
  called concurrently from any thread (that claim is now true — it did not
  hold before, per F1); the bound probe / `on_engine_thread()` still take no
  lock and may run concurrently with `bind_gate` and each other at any time;
  and a new sentence states the one thing the fix does *not* provide:
  `bind_gate` does not wait for an in-flight `on_engine_thread()` call, so a
  reader that already read the old (probe, context) pair may still invoke
  the old probe with the old context after the new bind returns — `context`
  must outlive the bind that installs it. The runtime's own two call sites
  both pass `nullptr` as context, which trivially satisfies this.

**Red first, made reliable.** Ported the review's `gate_twowriters.cpp` into
`kp_enginegatetest.cpp` as `concurrent_two_writers_never_tear`: two binder
threads race `bind_gate` against each other while two asker threads call
`on_engine_thread()` in a tight loop; a torn (probe, context) pair increments
an atomic counter the test asserts is zero. First draft used 200,000
iterations per writer and caught the tear in only 4 of 5 sampled runs
against the unfixed gate — too weak to call "red-first" with a straight
face. Raised to 1,500,000 iterations per writer (3,000,000 binds total,
matching the order of magnitude of the review's own probe run). Rebuilt
(`g++ -std=c++20 -m32 -Wall -Wextra -pthread`, no warnings) and sampled 10
runs each:

```
unfixed (kp_enginegatetest_red2): 10/10 runs FAIL. All ten torn counts
  (grep -ho 'torn=[0-9]*' red2_run_*.out), out of 3,000,000 binds each:
  31779  16592  56216  74242  60745  39468  42087  106673  12846  67915
fixed   (kp_enginegatetest_green2, then rebuilt again unchanged as
  kp_enginegatetest_final3 after the header-comment-only edit below):
  10/10 runs "6/6 tests passed, 19 checks", 0 torn, both builds.
```
10 runs of the unfixed build took 4.9s total (~0.5s each); 10 runs of the
fixed build took 10.3s total (~1.0s each) — both well under the 5s
per-run budget.

**TSAN.** Tried on this host, not assumed infeasible: `g++ -m32
-fsanitize=thread` failed to link with `cannot find
/usr/lib64/libtsan.so.2.0.0` — that file is g++'s **64-bit** TSAN runtime
and it is simply not installed here, which says nothing about whether a
32-bit TSAN build is possible. Separately, and independent of what's
installed: mingw-w64/i686 has no ThreadSanitizer runtime at all for any
host, so a 32-bit TSAN build matching the production ABI was never
achievable here regardless of what got installed. `clang++`'s bundled TSAN
runtime, by contrast, is present and working (see below) — it's g++'s
64-bit `libtsan.so` specifically that's missing, not TSAN in general. Built
a 64-bit variant instead with `clang++ -std=c++20 -Wall -Wextra -pthread
-fsanitize=thread`,
which is a genuinely different build (64-bit, different compiler) from the
32-bit suite above, run once as the task's "if feasible" extra rather than
folded into the 5s-per-run budget that applies to the offline suite:
- Unfixed: TSAN reports **no data race** but the test's own torn-counter
  still catches the bug directly (`torn=7 of iters=400000`, at the smaller
  200K-iteration build tested before the raise above; not rebuilt at 1.5M
  under TSAN since the point — that TSAN stays silent either way — was
  already established). This is expected, not a TSAN gap: every shared
  field here is a `std::atomic`, so there is no unsynchronized memory
  access for TSAN's happens-before model to flag. The bug is a *protocol*
  race (a multi-step sequence of otherwise-atomic operations can interleave
  into a torn multi-field state), not a *data*-race in the C++ memory-model
  sense — exactly why the review needed a purpose-built probe instead of a
  sanitizer.
- Fixed, at the raised 1.5M-iteration count: no data race, test passes,
  ~7.6s (this run does fall outside a 5s cap, but per the point above that
  cap was never claimed for the TSAN build — the 32-bit non-TSAN suite,
  which the 5s budget actually governs, is 1.0s/run).

Evidence files: `/home/brunner56/kp-live-20260922/tmp-m2r2/{red2_run_1..10,green2_run_1..10,tsan_green2}.out`,
`mingw_link_test.{cpp,exe}`, plus the binaries
(`kp_enginegatetest_red2`, `_green2`, `_tsan_green2`).

### F2 — signed-zero and NaN-payload coverage at the fences

Added one signed-zero test per site named by the review, plus a shared
`MotionFake::flip_sign` flag (flips the sign of any zero-valued position
component actually written, without changing magnitude — needed to make the
*readback* site's bit_equal/engine_equal choice observable, since it can't
be forced by constructing a `Capture` directly the way the other two sites
can):

- `stale_capture_pose_refused_on_signed_zero` (relocate's R6, `motion.cpp:224`)
- `restore_conflict_on_signed_zero` (restore's fence 6, `motion.cpp:302`)
- `readback_mismatch_on_signed_zero` (`write_and_verify`'s readback, `motion.cpp:194`)

Each constructs a pose pair that is `engine_equal` (their 0x4AA980-style fcomp
would call them the same) but not `bit_equal` (a zero component's sign
differs), and asserts both propositions directly before asserting the
production code's behavior.

**Rerun against the three named mutants** (`review-probes-motion-m2/mut/{stale,fence6,readback}/api/motion.cpp`,
each a one-line `bit_equal`→`engine_equal` swap at exactly the site named
above), built with the final `kp_motiontest.cpp` (58 tests) and everything
else from this worktree:

| Mutant | Site | Result | New failure, and only that one |
|---|---|---|---|
| `stale` | `:224` | 57/58 | `stale_capture_pose_refused_on_signed_zero` |
| `fence6` | `:302` | 57/58 | `restore_conflict_on_signed_zero` |
| `readback` | `:194` | 57/58 | `readback_mismatch_on_signed_zero` |

**NaN-payload cases: added, at the boundary the argument actually supports.**
My first draft of this round skipped these on the reasoning that `bit_equal`
and `engine_equal` can only disagree on a bit-identical NaN pair on both
sides, and `read_fields` (`motion.cpp:141-177`) refuses non-finite fields
before returning — so one operand at each of the three fences is always
finite, ruling out the divergent case. That reasoning holds, but declining a
named instruction on unbuilt reasoning is exactly the kind of claim the
review process exists to catch, so I turned it into tests instead of a
paragraph:

- `stale_capture_refused_on_nan_before_fence`: corrupts `cur.position` to
  NaN after a valid capture, relocates — refused `Value` ("not finite"), not
  `Stale`, proving `locate()`/`read_fields()` (`motion.cpp:218`) intercepts
  before line 224's fence is ever reached.
- `readback_refused_on_nan_landed`: a new `MotionFake::write_nan` flag lands
  a NaN x-component after the setter call — refused `Mutation` ("readback
  failed"), not a readback mismatch, proving `write_and_verify`'s own
  `read_fields` call (`motion.cpp:189`) intercepts before line 194.
- `restore_refused_on_nan_before_fence`: corrupts the current position to
  NaN after a successful move, restores — refused `Value`, ownership
  released (`motion.cpp:288-292`'s non-Guard/Chain path), before line 302.
- A primitive-level addition to `same_position_reported_noop_zero_setter_calls`:
  one new line asserts `bit_equal(v3(qnan,0,0), v3(qnan,0,0))` is true
  (`memcmp` on an identical payload); the pre-existing line just above it
  already asserted `engine_equal` of the same pair is false. Together they
  are the one case where the two functions really do disagree, shown at the
  primitive level since the three fences provably never reach it.

All four pass against the current code and, being refusals from the
upstream finite check rather than the bit_equal/engine_equal fence itself,
are unaffected by the `stale`/`fence6`/`readback` mutants (confirmed: none
of the three mutant reruns above shows these four as new failures — only
the one targeted signed-zero test fails per mutant).

**Fourth site found and closed with a test, not a code change.** Rerunning
mutants against the round-2 test file also picked up
`review-probes-motion-m2/mut/conflict/api/motion.cpp` (`bit_equal`→
`engine_equal` at `motion.cpp:242`, inside relocate's R10 ownership-
consistency check), which the review's F2 did not name and which was
unkilled before this round (`mut/conflict/out.txt`: `51/51`, pre-existing).
Same divergent-only-on-signed-zero shape as the three named sites, and
closing it needed only a test (`relocate_conflict_on_signed_zero`), not a
`motion.cpp` edit — so it is in scope after all ("Allowed:
`tools/kp_motiontest.cpp`"; "do not change motion semantics" is satisfied
because no line of `motion.cpp` moved). Rerun: `mut/conflict` now 57/58,
failing only `relocate_conflict_on_signed_zero`.

### Validation this round

All of the following is from a final rebuild of every artifact after the
last source edit (the header-comment addition and dropping one duplicate
assertion) — not carried over from an earlier build in this session.

- `kp_enginegatetest`: unfixed (`kp_enginegatetest_red2`) 10/10 sampled runs
  caught the tear, all ten torn counts out of 3,000,000 binds each: `31779
  16592 56216 74242 60745 39468 42087 106673 12846 67915`. Fixed, rebuilt
  from the final `engine_gate.{hpp,cpp}` (`kp_enginegatetest_final3`): 10/10
  runs `6/6 tests passed, 19 checks`, 0 torn across 10 * 3,000,000 =
  30,000,000 binds. TSAN (clang++, 64-bit, separate build): fixed build
  green, no race warning, ~7.6s (a one-off check, not bound by the 5s
  offline-suite budget — see the TSAN paragraph above for why no 32-bit
  TSAN build was possible at all).
- `kp_motiontest`, rebuilt from the final test file
  (`kp_motiontest_final4`): `58/58 tests passed, 4158 checks` (was `51/51,
  4120` before this round: +7 tests — 3 signed-zero at the named fences
  (stale/fence6/readback), 3 NaN-payload at those same three fences, 1
  signed-zero at the unnamed fourth site (conflict) — and +38 checks
  across them). Mutants, each rebuilt and rerun against the final test file:
  `stale`/`fence6`/`readback`/`conflict` each fail exactly their one
  targeted new test and nothing else (57/58 each, confirmed by `grep
  ^FAIL` on each run's output showing a single line);
  `flags` unchanged (2 failures, same two tests as the prior round: 56/58);
  `gate_late` unchanged (1 failure, same test as the prior round: 57/58,
  4127 checks — re-run three times after an earlier capture in this
  session came back truncated for an unrelated reason (a transient
  host-spawn output-capture glitch, not a test crash or a disk issue: `df
  -h` showed 9.9G free throughout), all three full runs agreeing).
- mingw i686 compile (`i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2`),
  rebuilt from final `engine_gate.cpp`, no warnings: `engine_gate.cpp`,
  `motion.cpp`, `motion_profiles.cpp`, `motion_backend.cpp`,
  `motion_lua.cpp` (the last needs `-Ithird_party/luajit/src`). Link-level
  check (not just compile): a `std::thread`-calling-`bind_gate` program
  linked with the DLL's actual
  `-static -static-libgcc -static-libstdc++ -Wl,--exclude-all-symbols`
  flags imports only `KERNEL32.dll`/`msvcrt.dll` (see F1 above).
- Motion semantics: untouched this round — see the note at the top of this
  section on why "empty diff" isn't the right referent for an untracked
  file, and what is used instead.

### Report-referent corrections (from the internal review pass)

- The claim "diff of `motion.cpp` against the version the review read is
  empty" used `git diff --stat`, which is vacuous on an untracked file (it
  always shows nothing, changed or not). Replaced above with the actual
  referent: every mutant tree's diff against current `motion.cpp` is still
  exactly the mutant's own change (five one-line swaps, `gate_late` a
  same-text two-hunk move) — the six diffs are now pasted in full at the
  top of this section, not just described.
- The TSAN paragraph originally said the 64-bit `-fsanitize=thread` link
  failure meant "TSAN and `-m32` don't combine on this host," which
  conflated two different facts: the missing library
  (`/usr/lib64/libtsan.so.2.0.0`) is g++'s *64-bit* runtime, not evidence
  about 32-bit at all, and separately mingw/i686 has no TSAN runtime for
  any host. Both are now stated as the two separate facts they are.
- A garbled parenthetical about check counts ("+19 checks") from an earlier
  draft's numbers was replaced with the actual before/after counts for the
  final test file (4120 → 4158, after also dropping one duplicate
  assertion this pass found: `!engine_equal(qnan,qnan)` was asserted twice
  in `same_position_reported_noop_zero_setter_calls`).
- All red/green run counts, mutant tables and test counts above are from a
  final rebuild after every source edit in this round, including the
  `gate_late` mutant rerun (an earlier capture of that one run came back
  truncated after only 66 of 68 lines for an unrelated, transient
  output-capture reason; re-run three times with `df -h` checked, all
  three agreeing at 57/58, 4127 checks, `df` showing 9.9G free throughout —
  not a truncated or lucky result).

### Files

- `src/api/engine_gate.hpp` — corrected contract comment, including the
  context-lifetime sentence (F1).
- `src/api/engine_gate.cpp` — `bind_gate` now takes a `std::mutex`;
  `on_engine_thread()` byte-for-byte unchanged (F1).
- `tools/kp_enginegatetest.cpp` — ported `gate_twowriters.cpp` as
  `concurrent_two_writers_never_tear`, at 1,500,000 iterations/writer (F1).
- `tools/kp_motiontest.cpp` — `MotionFake::flip_sign`/`write_nan`, seven new
  tests (3 signed-zero, 3 NaN, 1 signed-zero at the unnamed fourth site),
  registered in the test table.
- This report.

## Grill me

1. **Given the mutex needed a real link test to trust, not just a compile,
   what else in this round is still resting on an assumption rather than a
   check?** (weakest — this is the internal reviewer's own top finding,
   restated as a question against myself)
   - The clearest remaining one: `concurrent_two_writers_never_tear` is
     still probabilistic. 10/10 at 1.5M iterations is much stronger than
     4/5 at 200K, but it is not a proof that the fixed build can never tear
     under some adversarial scheduler, only evidence at the confidence this
     session's sampling supports. Referent: the run counts above.
     `unverified` beyond 10 samples each way — I did not, for instance, run
     it under a scheduler that deliberately preempts at instruction
     granularity.
2. **Why a mutex and not a lock-free CAS retry, now that the link risk is
   checked and looks clean?**
   - The link check removes what would have been the only reason to prefer
     CAS (avoiding a new dynamic dependency); with that closed, the mutex
     still wins on "minimal change" (one lock_guard vs. reintroducing the
     parity protocol in a retry loop) and the reader path is unaffected
     either way. Referent: `mingw_link_test.exe`'s import table, this
     round's F1 section.
3. **Does the mutex introduce any deadlock risk, e.g. a probe callback that
   itself calls `bind_gate` reentrantly?**
   - `std::mutex` is not reentrant; a probe that calls `bind_gate` from
     inside itself would deadlock. The probe is invoked from
     `on_engine_thread()`, which never takes the lock and is never called
     from inside `bind_gate` — so this can only happen if some *other* code
     path calls `bind_gate` from inside a probe, a caller-discipline
     question this primitive doesn't and can't enforce (the old code had
     the same reentrancy hazard in spirit, via `fetch_add` instead of a
     mutex). `unverified` beyond static reading — no test exercises "probe
     calls bind_gate."
4. **The `conflict` mutant fix is a test, not a code change — could it have
   been a false negative, i.e. does the test actually kill the mutant for
   the reason claimed, or by accident?**
   - Checked, not assumed: the mutant rerun table above shows `mut/conflict`
     failing exactly `relocate_conflict_on_signed_zero` and no other test,
     and the current (non-mutant) build passes all 58 — so the test isn't
     incidentally failing against the mutant via some unrelated assertion.
     Referent: `r2b_mut_conflict_run.out`'s single `FAIL` line.
5. **Is `bit_equal(qnan, qnan)` being `true` actually correct, or is it an
   accident of how the test constructs both sides from the same literal?**
   - It's `memcmp` on the raw bytes: two NaNs with the same payload have the
     same bits, regardless of how they were produced. Referent: `bit_equal`'s
     definition (`motion.cpp:31-33`, unchanged), a raw `memcmp`.
     `std::numeric_limits<float>::quiet_NaN()` is one fixed bit pattern per
     platform/compiler, and the test uses that same in-scope constant on
     both sides, so the `true` result is the real behavior, not an artifact
     of the test.

Hand-off: the one thing I could not settle is whether a hot-reload path
(the same one the Round 1 review's own hand-off named for F1) could call
`bind_gate` often enough for the mutex or the two-writer test's iteration
count to stop being representative. The single check that would settle it:
count `bind_gate` call sites and their expected call frequency once
`src/runtime/runtime.cpp` actually wires this in (I-M2/M3 scope).

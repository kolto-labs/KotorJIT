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

# Motion M2 (relocate / restore / observe) and M3 (auto-restore on unload): read-only plan

Date: 2026-09-27. Read-only planner. I edited no repository file and ran no build, Wine, game or address generator. I did not touch `tmp/harness-locks/live-game.lock`.
`WT/` = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (HEAD `ca329e5`, with a dirty tree). `R/` = `/home/brunner56/kp-live-20260922/`.
Inputs read this session:
- `R/fanout-lua-lifecycle-plan.md` §Track M and §L1-L3
- `R/motion-m0-rederivation.md`
- `R/motion-m0-verification.md` (CONFIRMS, with the safe list and the keep-out list)
- `R/motion-m1-review.md` (FAIL, narrow)
- `R/lua-lifecycle-l1l2-review.md` (FAIL on I1)
- `WT/src/api/motion*`, `WT/src/api/camera.hpp`, `WT/src/api/model.hpp`
- `WT/src/lua/host.{hpp,cpp}`
- `WT/src/runtime/{runtime.cpp,hook_bodies.cpp,fault_guard.cpp,runtime.hpp,internal.hpp,dllmain.cpp}`
- `WT/src/devtools/console.cpp`
- `WT/src/harness/commands.cpp`

Any claim without a file:line or a receipt is marked `unverified`.

---

## 0. Facts this plan rests on (independently re-read)

claim: boot `load_all` runs script chunks on the DLL worker thread, not the engine thread.
referent: `WT/src/runtime/dllmain.cpp:51,70` (the `worker` thread is created with CreateThread). `WT/src/runtime/runtime.cpp:193` says of boot: "Written once during boot, on the worker thread, before any hook body can run". In `Runtime`'s start path, `load_all` runs before `set_live(true)`, and `OnScriptLoad` is dispatched **after** `set_live(true)`, still inside the same start() on the worker. In the tree read at 2026-09-27 these are `runtime.cpp:756` (load_all), `:767` (set_live) and `:774` (dispatch). The file is being edited concurrently: its lines moved by about 27 during this session, so re-grep before citing.
checked: file reads
verdict: holds
confidence: high

claim: the devtools console runs Lua on a game thread but **outside** any `KP_HOOK_GUARD`, so `in_hook_body()` is false there.
referent: `hook_bodies.cpp:768` pumps the console before `KP_HOOK_GUARD_BEGIN` at `:774`. The same holds for the client loop at `:1277` and the frame wrapper at `:1302`. `console.cpp:374-380` shows that `Console::pump` never calls `enter_hook_body`. `fault_guard.cpp:409` defines `in_hook_body()` as the thread-local `depth > 0`.
checked: file reads
verdict: holds. So `in_hook_body()` is a fault-ownership predicate, not an engine-thread predicate. It is the wrong gate here: it would refuse the console, which is legitimate, and it says nothing about the thread.
confidence: high

claim: the owner key is set before `on_state_created` and before the chunk runs. `Script::staged()` is true from before the chunk until `commit_staged`.
referent: `host.cpp:141-144` pushes `kOwnerKey`→`this` into the new state's registry. `:146-148` set `staged_L_ = N` and then call `on_state_created`. `:163` runs the chunk. `host.hpp` gives `staged() { return staged_L_ != nullptr; }`. `commit_staged` (`host.cpp:170+`) calls `release_state()` for the old generation.
checked: file reads
verdict: holds. The probe `Script::owner(L) && !owner->staged()` therefore refuses three things: a chunk top level (at boot and on hot reload alike), the old generation while its successor is staged (this closes the L1 review's I1 window for writes), and every state with no owner. The registry is shared across coroutines, so a coroutine resolves to the same owner.
confidence: high for the code path. The live behaviour is `unverified` until I-M2.

claim: the console and harness states close without the lifecycle hook.
referent: `console.cpp:348-372` (`Console::reset` calls `lua_close(old)` directly); `harness/commands.cpp:252-254` (`close_harness_state` calls `lua_close(g_L)`).
checked: file reads
verdict: holds. Neither state could ever auto-restore, so neither may write (rule R3 below).
confidence: high

claim: `on_state_closing` exists in the Host but is not wired in the runtime.
referent: `host.hpp:179-182` declares it. `host.cpp:79-84` (`close_state`) calls it exactly once before `lua_close`. `grep -n on_state_closing src/runtime/*.cpp` returns no lines.
checked: grep
verdict: holds. L3 `src/api/ownership.*` does not exist either (`ls` fails).
confidence: high

claim: at `Runtime::stop` the live flag drops and hooks are uninstalled **before** the Host is destroyed. `~Host` calls `unload_all`, so every script's closing hook fires with `live()==false`, on whatever thread calls stop().
referent: `Runtime::stop` in `runtime.cpp`: `set_live(false)` (`:863`), `hooks_->uninstall()` (`:875`), `host_.reset()` (`:877`), per the latest read; the lines drift. `host.cpp:265` `Host::~Host() { unload_all(); }`.
checked: file reads
verdict: holds. Auto-restore at stop is refused by the gate and logged (see M3).
confidence: high

claim: the engine precedent for moving an object is `SetPosition(obj, &pos, 1, 1, 0)`.
referent: `hook_bodies.cpp:307` and `:354` (multiplayer replay on a creature).
checked: file read
verdict: holds as a creature precedent. It has not been tried on a placeable.
confidence: high for the call shape (M0 verification, 0x4CD1A0 row)

---

## 1. Write strategy

### Decision: M2 uses raw `SetPosition` 0x4CD1A0 with flags (a2=1, a3=1, a4=0). Remove/Add is deferred.

Why raw SetPosition:
- It is on the M0 safe list (`motion-m0-verification.md` "Functions" rows for 0x4CD1A0).
- It is thiscall `(this, const Vector*, a2, a3, a4)`, `ret 0x10`, with no read of a3.
- It returns early on exact 3-float equality (0x4AA980).
- a4==0 sets dirty bit value 2 at +0x1FC.
- The per-tick consumer 0x4B0B70 pushes the pose to the client and clears the bit, gated on +0x1F8 != 0. So no explicit sync call is needed.
- It touches none of +0x344, +0x3A0, +0x3C0, +0x3D8.
- It is the engine's own creature precedent (`hook_bodies.cpp:307`).

What raw SetPosition costs:
- The collision stays behind.
- Where +0x344 >= 0, the placeable has a walkmesh AABB registered at its old pose. The new spot is walk-through, and the old spot may still block. Whether pathing reads that list is `unverified` (M0 §4).
- There is no Z snap, so the caller supplies Z.

Rule this implies: see R8 below. By default, relocate is refused when `collision_registered` is true.

Remove (0x584950) plus Add (0x587170) is the engine's full re-placement. CreateObject and the GIT loader both use it (M0 rederivation §3). Everything it needs beyond the safe list is still missing:

| # | Missing evidence | Why it blocks Remove/Add |
|---|---|---|
| E1 | AddToArea's third argument. CreateObject passes 1 (`0052fc0f`); the GIT loader passes a loaded `flag` (`0050aa3e`). Meaning `unverified` | We would be picking a value with no known semantics |
| E2 | 0x50DC40 (called from Remove) and 0x50DFD0(id,1) (called from Add). These are keep-out, and their semantics are `unverified` beyond the `(id[,flag])` call shape | They may be area object-list remove/add. They may fire area events or send a client destroy/create, which would be flicker, an event storm, or script re-entry |
| E3 | Add re-reads `placeables.2da` (PreciseUse, Hostile, ModelName) keyed by +0x230 and rewrites +0x33C/+0x340 | It could clobber any runtime change to those fields. Whether anything changes them at runtime is `unverified` |
| E4 | The collision-mesh branch (0x596670 gate on +0x3A0; +0x3C0/+0x3D8 writes; 0x596D10; 0x58FD50). All keep-out | Needed to claim that collision moved at all |
| E5 | Readers of `area+0x44..0x50` (the AABB list) | Needed to claim a gameplay effect in either direction |
| E6 | Remove's own `SetPosition(&{0,0,0},1,1,0)` sets dirty bit 1 (M0 verification addition) | Harmless inside one call if the consumer only runs later on the same thread. That is `unverified` for any client message that 0x50DC40 may send |

Remove/Add becomes a later stage, **M2b "settle"**, gated on a receipt for E1, E2 and E4, the same way M0 was done. Its shape would be one Remove/Add at the end of a motion, not per tick (M0 §4 proposal). E3 decides whether M2b must snapshot and re-apply +0x33C/+0x340. M2b is **not** in this plan's file list.

### Orientation

M2 writes position only. Capture keeps returning orientation, and restore verifies that orientation is unchanged. It does not write orientation.
0x4CD170 (SetOrientation) is on the safe list, but a rotation leaves the collision quaternion stale (M0 §4). Orientation writes stay in M5.

### Readback contract (per relocate)

After the single setter call, the fallible reader must show:
- (a) +0x90..0x98 **bit-for-bit equal** to the target floats. SetPosition copies the vector; +0x90 is its `lea edi` target.
- (b) +0x1FC & 2 set. a4==0 on the non-early-return path sets it. The consumer runs from MainLoop on the same thread, so it cannot interleave within one Lua call. That is `unverified` live, and item 10 of the live proof checks it.
- (c) The id, vtable, type and area_id fences all unchanged.

If any of these fails, the result is `nil, "mutation: readback mismatch; the write may have happened"`. The ownership entry **is still recorded** with `last_written = readback`, so M3 can restore.

---

## 2. Engine-thread enforcement, shared by motion, camera and model

M1 review F1 is resolved by one gate that every native reader and writer asks first.

**Where it lives:** new `WT/src/api/engine_gate.hpp/.cpp` (namespace `kp::api::engine`). It is domain-free and has no Lua and no runtime include.

```cpp
using Probe = bool (*)(void* context);
void bind_gate(Probe, void* context);   // runtime binds; nullptr unbinds
bool on_engine_thread();                // false when unbound (fail closed)
const char* gate_refusal();             // "unsupported: not on the engine thread"
```

**What the runtime binds (I-M2):**
- The probe is `live() && current_thread_id() == g_engine_tid`.
- `g_engine_tid` is latched with a compare-exchange on the first entry to `main_loop_body` (`hook_bodies.cpp:759`).
- Before the latch is set, every thread is refused. An unlatched id is not a match.
- `client_main_loop_body` (`:1266`) and `client_frame_wrapper_body` (`:1293`) compare against the latch. On a mismatch they log once and do not re-latch.
- Thread id comes from `GetCurrentThreadId` on Windows and from `pthread_self` elsewhere.
- It is `unverified` that K1's client loop and server MainLoop share one thread. The drain comment at `hook_bodies.cpp:760-764` ("a nested server/client invocation") implies it; live proof item 1 settles it.

**What it gives:**
- The boot chunk is refused twice over: it runs before `set_live(true)`, and it runs on the worker. The boot `OnScriptLoad` dispatch runs **after** `set_live(true)` but still on the worker, so only the thread-id half can refuse it. That makes it the case that separates the two halves (live proof step 2).
- A stop() on any thread is refused, because `live()` is false.
- The console and harness states are allowed to **read**, because they run on the engine thread.
- Hot-reload chunks pass the thread gate. They are refused for **writes** by the owner probe (R3), not by the thread gate.

**Order inside every public op:** gate → pure argument checks → guards → chain → getter → fences. A gate refusal does **zero** backend reads and **zero** calls (test `engine_gate.refusal_zero_reads_zero_calls`).

**How tests fake it:** `bind_gate(+[](void* c){ return *static_cast<bool*>(c); }, &flag)`. The tests flip `flag`. Any test that leaves the gate unbound must see refusal, which proves fail-closed. One extra test starts a real `std::thread` and uses a thread-latch probe to show that the other thread is refused. That test is host-only; the probe helper is compiled only into the test.

**Adoption:**

| Module | Engine calls? | Adopts in | Owner | Public behaviour change |
|---|---|---|---|---|
| motion | yes (getter, SetPosition) | M2 | motion writer | none (new API) |
| model | yes (`set_scale`, getters) | separate stage G-model | model owner (edits `model.cpp`) | a boot top-level `kp.model.*` call starts refusing |
| camera | reads only | separate stage G-camera | camera owner (edits `camera.cpp`) | a boot top-level `kp.camera` snapshot starts refusing. It is a racy read today, and fault-safe only through the fallible reader |
| animation, projectiles | bound natively (`runtime.cpp:375-377`); not reviewed here | later, listed only | their owners | `unverified` |

This plan claims the gate for **motion only**. For camera, model, animation and projectiles it claims only that the gate is available to them.

---

## 3. Capture token and restore contract

### Lua surface (all lowercase; none equals an NWScript routine name)

claim: none of `motion`, `capabilities`, `capture`, `relocate`, `restore`, `observe` or `owner_token` is an NWScript routine name.
referent: a recursive walk of every `name` key in `WT/data/routines/k1.json` (1,848 names) and `k2.json` (2,082 names), case-folded and intersected with that set. Both intersections are empty (`k1 1848 []`, `k2 2082 []`). This is the M1 review's method.
checked: python3 over the JSON files, run this session
verdict: holds
confidence: high

- `kp.motion.capture(id)`
  - Unchanged from M1. Read-only, allowed from any state on the engine thread.
  - One new read field is added: `owned` (bool, true when the calling state owns the object). The per-state token is **not** exposed. The name `generation` is already taken by `kp.scripts.list()` with a different meaning.
- `kp.motion.relocate(capture, target [, opts])` → `capture2, status` or `nil, "kind: reason"`.
  - `target` is `{x=,y=,z=}` or a `kp.vec`.
  - `status` is `"moved"` or `"noop"`. `"noop"` means the target was exactly equal to the current pose, so no setter call was made.
  - `capture2` is the post-readback capture. It is what the next relocate must be given.
- `kp.motion.restore(capture_or_id)` → `capture2` or `nil, "kind: reason"`.
- `kp.motion.observe(capture)` → a table, read-only.
  - `pushed`: true when +0x1FC & 2 is clear and +0x1F8 != 0.
  - `push_gate_raw`
  - `dirty_position`
  - `ticks_since_write`, which needs the injected tick source below
  - `client = "unverified"`
- `capabilities()` gains:
  - `writes = {"position"}`, a table.
  - `reads`, which becomes a table. This folds in M1 review F2; assert it in `motion.lua_capture_surface`.
  - `refusals`, a table holding the closed set of error kinds.
  - `limits`, which adds the save-while-moved hazard and the stale-collision note.

### Observe was narrowed

The fanout plan's "observe agrees within N ticks (client)" cannot be met:
- The client placeable's position offset has no receipt (M0 rederivation §"live readback" item 5: "client field offset still to be found").
- Client `vtbl+0x12C/+0x130` and "+0x24" are keep-out.

So `observe` is a **server-side proxy**. The consumer clears bit 1 only when the gate passes (`motion-m0-verification.md` "+0x1FC" row: `004b1098` gate then `004b1138` clear). So "bit clear and +0x1F8 != 0" means the server issued the client push.

The fanout test `motion.observe_reports_client_lag_without_client_setter` is renamed `motion.observe_reports_push_consumed_without_client_read`.

What would restore the original contract is an M0-style receipt (two derivations) for the client placeable position offset, reached through 0x5ED5F0.

### Tick source

`motion::bind_tick(std::uint64_t(*)(void*), void*)` is injected. The runtime binds it to `active_host()->tick()` (I-M2), and the tests fake it. Unbound, `ticks_since_write` is nil. The field `last_write_tick` uses the same source.

### Per-state owner token (the owner key)

- `register_all(L)` stores a fresh `uint64` from a process-wide monotonic counter in the state's registry under a motion-private lightuserdata key.
- The ledger keys on this token, **never on `lua_State*`**, because pointers are reused after `lua_close`.
- Every hot reload makes a new state, and so a new token. This subsumes the Host's `Script::generation` for ownership; the script name and generation are logged only.

### Ownership ledger (process-wide, in `motion.cpp`)

Entry, keyed by object id:
- `owner_token`
- `binding_epoch` (M1 `epoch_`, bumped on unbind)
- `object` (the pointer, used **for comparison only and never dereferenced**)
- `area_id`
- `origin` (position and orientation at the first relocate)
- `last_written` (the readback)
- `writes`
- `last_write_tick`

Rules:
- **Single owner per object.** A relocate from another token is refused with `owned: object is moved by another script`.
- **First relocate** records `origin` from the *capture* pose, after re-verifying that the current pose equals the capture pose (see "stale" below).
- **restore** is allowed only for the owning token (`not_owner` otherwise). It re-runs every fence, then writes `origin`, reads back, and drops the entry.
- **Restore fences**, in order:
  1. Binding epoch is the same.
  2. The getter(id) returns non-null.
  3. The returned pointer == `object`.
  4. The vtable, type and id round-trip.
  5. `area_id` is the same.
  6. The current position is **bit-equal to `last_written`**.

  Fence 6 carries the most weight. It defeats id or pointer reuse, and it keeps us from overwriting a move made by NWScript, the engine or a save load. When it fails, the result is `conflict: moved by another writer; ownership released`, with **no write**, and the entry is dropped.
- **Stale capture.** Relocate requires that the capture's epoch equals the current epoch and that the capture pose equals the current pose (bit-equal). Otherwise it returns `stale: ...`. This forces a script to pass the latest `capture2`.

### M3: auto-restore on close (one path only)

- `motion` exposes `void release_state(lua_State*)`. It reads the token and, for each entry with that token, runs restore-with-fences or logs a refusal. It then drops all of that token's entries.
- **It makes no Lua calls.** Every fallible read happens before the single SetPosition.
- **Gated.** When `on_engine_thread()` is false (stop, worker thread), it writes nothing and logs one line per entry: `motion: not restored (runtime not live); id=... left at x,y,z`.
- **The only caller is L3's `ownership::run_and_clear(L)`**, from `HostConfig::on_state_closing`. Motion registers `{ "motion", release_state }` with L3.
- M3 does **not** add a direct runtime→motion call. If L3 is not landed when M3 is ready, M3 waits. Two close paths would mean ordering questions and double restores.
- **Fault exposure.** On the hot-reload and service paths, `close_state` runs inside the MainLoop `KP_HOOK_GUARD` (`hook_bodies.cpp:774-796`). A fault in the engine SetPosition would longjmp past `lua_close`, which leaks that state (`fault_guard.cpp` header, "anything a longjmp skips"). This is accepted and stated. The pre-call fences make it unlikely.

---

## 4. Refusal rules (checked in this order; each is one error kind)

| # | Rule | Kind | Engine calls |
|---|---|---|---|
| R1 | Not bound, or wrong profile | `unsupported` | 0 |
| R2 | `on_engine_thread()` false | `unsupported: not on the engine thread` | 0, and 0 reads |
| R3 | The write comes from a state with no Host owner (console, harness, bare), or from a state whose owner `staged()` (chunk top level, or the old generation during a reload) | `unsupported: only a loaded script can move placeables` | 0. `restore` is exempt from the `staged()` half, so an owner can always put things back |
| R4 | Arguments: a non-finite component, a missing field, a forged or foreign capture userdata | `value` or argerror | 0 |
| R5 | Guards (spans, slots) | `guard` | 0 |
| R6 | Chain, getter null, or fences (vtable, type, id round-trip) | `chain` / `identity` | the getter only |
| R7 | Stale: epoch changed, or current pose != capture pose; area_id changed; area_id is 0x7f000000 or 0 | `stale` | the getter only. Which value SetArea(0) leaves in +0x8C is `unverified`, so both are refused |
| R8 | `collision_registered` (+0x344 >= 0) and not `opts.allow_stale_collision == true` | `collision: placeable has a registered walkmesh; a raw move leaves it behind` | the getter only |
| R9 | Bounds (policy, not evidence): \|target−current\| ≤ 5.0 m, \|Δz\| ≤ 1.0 m, \|target−origin\| ≤ 25.0 m, \|coord\| ≤ 1e5 | `bounds` | the getter only |
| R10 | Owned by another token | `owned` | the getter only |
| R11 | Exact equality with the current pose | none; returns `status="noop"` | the getter only (it matches the engine's own early return) |
| R12 | Readback mismatch | `mutation` (the entry is kept) | getter + 1 setter |

Also refused, as a stated limit: moving an object across areas. No SetArea is ever called.

**Known hazard with no mitigation.** A save taken while an object is moved persists the moved pose. The save routine 0x586A70 writes +0x90..0x98 (M0 verification "save" row). The ledger lives only in memory, so the origin is lost across a save-load. It goes in `limits`. Mitigating it needs a receipt for an area-save hook; none exists.

---

## 5. Host tests to write first (all fail before the code; synthetic backend with read and call counters)

Stage **G** (engine gate), new `tools/kp_enginegatetest.cpp`:
- `engine_gate.unbound_refuses`
- `engine_gate.bound_probe_true_allows`
- `engine_gate.rebind_nullptr_refuses`
- `engine_gate.other_thread_refused` (real `std::thread` with a latch probe)

Stage **M2**, added to `tools/kp_motiontest.cpp`:
- `motion.gate_refusal_zero_reads_zero_calls`, which covers capture, relocate, restore and observe
- `motion.nonfinite_refused_zero_calls`
- `motion.step_bound_refused`
- `motion.dz_bound_refused`
- `motion.origin_range_refused`
- `motion.stale_capture_pose_refused`
- `motion.stale_epoch_refused`
- `motion.area_change_refused`
- `motion.area_sentinel_refused`
- `motion.collision_registered_refused_by_default`
- `motion.collision_opt_in_allows`
- `motion.relocate_single_setter_call_flags_110`: exactly one call; args (1,1,0); function VA 0x4CD1A0 relocated by base
- `motion.readback_requires_exact_pos_and_dirty_bit`
- `motion.readback_mismatch_reports_mutation_and_keeps_entry`
- `motion.same_position_reported_noop_zero_setter_calls` (includes -0.0 vs 0.0)
- `motion.restore_exact_readback`
- `motion.restore_refused_after_identity_change`
- `motion.restore_conflict_when_moved_by_other_writer_no_write`
- `motion.second_owner_refused`
- `motion.owner_token_not_pointer`: close state A, open B at the same address, B does not inherit
- `motion.write_refused_without_host_owner` (fake owner probe)
- `motion.write_refused_while_staged`
- `motion.restore_allowed_while_staged`
- `motion.observe_reports_push_consumed_without_client_read`
- `motion.capabilities_tables`, for `reads`, `writes` and `refusals` (the M1 F2 fold-in)
- `motion.new_spans_match_reference_image`
  - This extends `spans_match_reference_image`.
  - It covers every added span: the `ret 0x10` epilogue near `004cd23c`, the `004cd1c4` a4 compare, and the `004cd1b1` call to 0x4AA980.
  - **The writer reads the bytes from the image; nobody types them from mnemonics.**

For the tests, the owner probe is injected (`motion::bind_owner_probe(Probe, void*)`), so the motion test does not link `src/lua/host.cpp`. The runtime binds it to `Script::owner(L) && !owner->staged()`.

Stage **M3**:
- in `kp_motiontest.cpp`:
  - `motion.release_state_restores_owned`
  - `motion.release_state_skips_when_gate_false_and_logs`
  - `motion.release_state_after_identity_change_logs_not_writes`
  - `motion.explicit_restore_clears_ownership`
  - `motion.release_state_makes_no_lua_calls` (instrumented with `lua_gethook`/a panic)
- in a new `tools/kp_motionlifecycletest.cpp`, which links the real `lua::Host`, L3 `ownership` and a fake backend:
  - `motion_lifecycle.unload_one_restores_once`
  - `motion_lifecycle.hot_reload_restores_old_generation_before_new_can_move`
  - `motion_lifecycle.top_level_relocate_refused`

Regression set per the fanout convention:
- `ctest -L offline`
- `kp_namespacetest.k1` and `.k2`
- `tools/nwscript_boundary_test.py`
- `i686-w64-mingw32-g++` compile of every touched source

---

## 6. File ownership

| Stage | Owned files | Disjoint from |
|---|---|---|
| G | new `src/api/engine_gate.{hpp,cpp}`, new `src/api/engine_gate.cmake`, new `tools/kp_enginegatetest.cpp` | everything below except I-M2 |
| M2 | `src/api/motion.hpp`, `motion.cpp`, `motion_profiles.cpp`, `motion_backend.cpp`, `motion_lua.cpp`, `motion.cmake` (compiles `engine_gate.cpp` into `kp_motiontest`), `tools/kp_motiontest.cpp`, `data/adjudication/k1_gog_103_motion_bindings.json` | L1-L3, U1/U2, camera, model, harness, runtime, CMakeLists.txt, `data/hooksites.toml` |
| M3 | the M2 files plus new `tools/kp_motionlifecycletest.cpp` (registered in `motion.cmake`) | same; needs L3's `src/api/ownership.*` landed (read-only use) |
| G-model / G-camera | `src/api/model.cpp` / `src/api/camera.cpp` and their tests | motion |
| **I-M2** (serialized with the camera and I-L integration, one integrator) | `src/runtime/runtime.cpp` (motion `bind_native` after the camera bind; `register_all` after `api::camera::register_all` in `on_state_created`; unbind next to both camera unbinds; `engine::bind_gate`; `motion::bind_owner_probe`; `motion::bind_tick`). Anchor on the camera calls, not on line numbers, because the file is being edited concurrently.; `src/runtime/hook_bodies.cpp` (tid latch in `main_loop_body`, compare in the client bodies; I-L also edits this file, to add `service_requests` near `:785`); `src/runtime/runtime.cmake` (motion sources and `engine_gate.cpp`); `CMakeLists.txt` (`include` `motion.cmake` and `engine_gate.cmake`); `tools/kp_namespacetest.cpp` (`kp.motion.*`; apply the L1/L2 review M8 fix pattern for table-valued namespaces); `docs/lua-api.md`; `docs/user/api-status.md`; `data/hooksites.toml` only if a row for the setter is wanted | — |
| **I-M3** | `runtime.cpp`: none beyond what I-L3 already wires (`on_state_closing` → `ownership::run_and_clear`). M3's registration with `ownership` lives in `motion.cpp` | — |

M2's `motion.cmake` is untracked today and is included nowhere (M1 review F1). So nothing M2 does can break the runtime build until I-M2.

---

## 7. Minimal live proof

Conditions:
- Serialized, controller only, under `tmp/harness-locks/live-game.lock`.
- Runs after I-M2, and for step 9, after I-L, I-L3 and I-M3.
- K1 GOG, Wine.
- Uses a private fixture `zz_motion_probe.lua` staged in the runtime scripts dir, never in the source tree. The route TOML is private under `R/`.

Steps:
1. **Thread latch.** The log shows the latched engine tid, and that the client loop tid equals it (or the one mismatch line). This settles the `unverified` same-thread claim.
2. **Boot gate.** The fixture calls `kp.motion.capture(0x7f000001)` in two places at boot: at its top level, where it is refused because live is false and the thread is the worker, and in its `OnScriptLoad` handler, where it is refused **only** because the thread is the worker. Both log lines must show `unsupported: not on the engine thread`, not `identity`. The `OnScriptLoad` line is the one that proves the thread-id half.
3. **Spawn and record.** The fixture's OnTick spawns one footlocker via `nwscript.call('CreateObject', …)` near the PC. It logs `capture(id)`, including `collision_registered`, `push_gate_raw` and `dirty_position`.
   - The collision state of the footlocker is `unverified`.
   - **Branch:** if `collision_registered` is false, the proof uses the default path. If it is true, step 5 first shows the R8 refusal. It then uses `allow_stale_collision=true` and records that choice.
4. **Harness refusal.** Harness `lua`: `kp.motion.relocate(kp.motion.capture(id), …)` on the spawned id returns `unsupported: only a loaded script…`. The GetPosition oracle is unchanged.
5. **Relocate.** Relocate +1.0 m in x with z unchanged. Log `status`, the readback, the dirty bit, and `nwscript.call('GetPosition', id)`. They must agree bit-for-bit, or within 1e-4 on the NWScript float path.
6. **Observe.** Within N ≤ 4 ticks, `observe().pushed == true`. The expected N is 1, because `main_loop_body` runs Lua `OnTick` before `orig(self)`, and the consumer's only caller (`004bac73`) is inside MainLoop. That N=1 is `unverified` until the hooked server-loop address is compared to the function that contains `004bac73`. N ≤ 4 is slack. If `push_gate_raw == 0` at spawn, then `pushed=false` is the expected outcome and is logged as such, not as a failure.
7. **Screenshot.** The controller takes one. The crate is visibly offset. This is the only client-side evidence.
8. **Restore.** Restore; the oracle equals the original bit-for-bit, and `capture().owned == false`.
9. **(M3)** The fixture relocates again. The controller issues `kp.scripts.unload('zz_motion_probe')` via harness `lua`. The oracle equals the original, and the log has exactly one `motion: restored` line.
10. **Source preservation.** A source-preservation receipt, as in prior runs. The fixture and the crate are removed afterwards.

Explicitly not claimed: collision at the destination, use-at-destination, client-side XYZ, orientation, and save interaction.

---

## Grill me

1. **Is refusing the console and harness states for writes right, or too strict?** (the weakest point, because it is a ruling rather than evidence)
   - The evidence is that their closes skip `on_state_closing` (`console.cpp:348-372`, `commands.cpp:252-254`), so they could never auto-restore.
   - Relaxing it later is cheap, while taking a permissive rule back is not.
   - The cost is that devtools experiments must go through a script file. That is a ruling for the user. `unverified` whether the user wants console writes with "no auto-restore" instead.
2. **Why does R8 refuse walkmesh placeables by default, and is `allow_stale_collision` a public contract we want?**
   - The data flow holds: SetPosition never touches +0x344/+0x3C0/+0x3D8 (M0 verification, final "Behaviour" row).
   - The gameplay effect is `unverified` (E5). Once shipped, the opt-in flag becomes public contract.
   - The alternative is to wait for M2b (Remove/Add), which needs E1, E2 and E4.
3. **Is a thread-id latch in `main_loop_body` enough when K1 might run the client loop on another thread?**
   - Server/client nesting on one thread is `unverified`. The only hint is `hook_bodies.cpp:760-764`.
   - Live proof step 1 settles it. If the tids differ, the latch must become the thread that calls the server MainLoop, which is where the engine functions are legal per `harness/channel.hpp:5-8`.
4. **Why is `observe` server-side only?**
   - The client placeable position offset has no receipt, and the client vtbl slots and "+0x24" are keep-out (M0 verification's closing list).
   - The proxy rests on the verified gate→clear order (`004b1098` → `004b1138`).
5. **Can bit-equality to `last_written` really stand in for "nobody else moved it"?**
   - It holds, with one exception. A third writer that moved the object away and back to exactly `last_written` would pass, and restore would then be correct anyway.
   - An id reused by a new placeable at bit-identical coordinates would also pass. It is additionally fenced by pointer, area and epoch.
   - Residual risk: low. `unverified` live.

Hand-off: the one question I could not settle is whether the spawned footlocker has a registered walkmesh (+0x344 >= 0). The single check that settles it is step 3 of the live proof: a read-only `capture(id).collision_registered` on a freshly spawned footlocker. M1's live oracle could record it before M2 code lands.

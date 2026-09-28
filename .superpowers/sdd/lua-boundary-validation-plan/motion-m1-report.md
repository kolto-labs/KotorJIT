# Motion M1 report: read-only `kp.motion.capabilities()` / `kp.motion.capture(id)`

Date: 2026-09-27. Stage M1 of `/home/brunner56/kp-live-20260922/fanout-lua-lifecycle-plan.md` (Track M).
Evidence used: `motion-m0-rederivation.md` (sha256 `c9a3d022…`) and `motion-m0-verification.md` (sha256 `93cda1dc…`, verdict CONFIRMS). Only the verification's "safe to enter reviewed data" list was used.
Nothing was staged, committed or pushed. No Wine or game was run. The live-game lock was not touched. `gen_address_tables.py` was not run. `data/addresses/*` was not edited.

## Result

- 20/20 tests pass, 2926 checks, on synthetic memory. The red-stub run failed 17/19. A later facing-edge test failed red before its fix.
- The i686-w64-mingw32 compile of all four motion sources is clean, and the thiscall branch is the one compiled.
- The standalone data check passes: TOML parses, there are no duplicate names, each new row binds in exactly one file, and no motion offset overlaps another binding.
- Nothing is proven live.

## Files (all new except the additive hooksites rows)

| File | Lines | Role |
|---|---|---|
| `src/api/motion.hpp` | 98 | Profile, Span/Slot, Failure {None, Unsupported, Guard, Chain, Identity, Value}, Backend, Capture, Operations |
| `src/api/motion_profiles.cpp` | 72 | One profile `windows-k1-gog` (SHA 9c10e045…): 23 byte spans and 4 vtable slots |
| `src/api/motion.cpp` | 130 | Checked core |
| `src/api/motion_backend.cpp` | 42 | Native adapter, `_WIN32 && __i386__` only; every other host gets no adapter |
| `src/api/motion_lua.cpp` | 107 | `kp.motion.{capabilities,capture}` and the protected capture userdata |
| `src/api/motion.cmake` | 16 | `kp_motiontest` target and `add_test` (label `offline;motion`); passes `${CMAKE_SOURCE_DIR}`. **Written, not configured**: I built by hand, and CMakeLists.txt does not include it yet |
| `tools/kp_motiontest.cpp` | 534 | Tests. The fixture `MotionFake` is inlined at :37-78, because `tools/tests/` was not on the allowed list |
| `data/adjudication/k1_gog_103_motion_bindings.json` | 395 | 1 function, 1 reference and 7 fields, plus 23 guards and 4 slots, with a two-derivation citation |
| `data/hooksites.toml` | +59 at :2354 | 7 optional `kind="field"` rows, appended after `g.camera_style_pending`. Camera rows untouched (diff has 0 removed lines) |

### Core behaviour (file:line)

`Operations::capture`, `src/api/motion.cpp:81-127`, runs these steps in order:

1. **Guards on every capture.** `:83` calls `guards()` (`:36-54`). That checks all 23 spans byte for byte and the 4 placeable vtable slots.
2. **OBJECT_INVALID.** `:84` refuses `0x7f000000` before the call. `0xffffffff` and `0x7fffffff` are passed through to the getter.
3. **Server chain.** `:86-91`: `[0x7a39fc]` → `+8` CServerExoApp → `+4` internal → `+0x1005c` array → a 1-byte probe. Any failure is `Chain`, and no call is made.
4. **The only engine call.** `:93` calls `backend_->placeable(0x4AE7A0, server, id)`. On Win32 that is `thiscall(void*, uint32)` (`motion_backend.cpp:20`).
5. **Fences.** `:96` requires vtable == 0x7494D0, `:98` requires type byte == 9, and `:100` requires `[obj+4]` == the requested id. Any failure is `Identity`.
6. **Field reads.** Reads go into a local `Capture`. An unreadable field is `Chain`. Non-finite position, orientation or quaternion is `Value` (`:113-115`).
7. **Output.** `out = c` at `:126` only after everything above passes. The caller's struct is never partially written, and every refusal test asserts that.

Bind refuses an unknown SHA, an ABI or width mismatch, a zero base, and a relocated base (`:66`; the spans hold absolute immediates). A guard mismatch at bind unbinds and reports `Guard`.

### Lua surface (`src/api/motion_lua.cpp`)

- `kp.motion.capabilities()` returns these fields:
  - `available`, `profile`, `abi` (`windows-i386-thiscall` or "no verified host binding").
  - `writes=false`.
  - `reads`, a list of the field names.
  - `limits`, which covers the gate, the quaternion order, the facing normalisation and the missing live readback.
- `kp.motion.capture(id)` returns a protected userdata (`kp.motion.capture`, magic `KPMOTIO1` at `:16`, size check, `__metatable` at `:97`, `__newindex` raises). On failure it returns `nil, "<kind>: <reason>"`.
  - The id must be an exact uint32 number. Anything else returns `value:` before any engine call.
- Capture fields:
  - `id`, `area_id`, `epoch`, and `object` (a hex string).
  - `position` and `orientation` as fresh `{x,y,z}` tables.
  - `facing`: atan2(y,x) in degrees, [0,360). It wraps after the float cast (`motion.cpp:118-121`), because 360-5.7e-6 rounds to 360.0f.
  - `push_gate_raw` (u32).
  - `dirty_position` (bit 1) and `dirty_orientation` (bit 2). The raw word and bit 0 are not exposed.
  - `collision_registered`: `+0x344 >= 0`. The marker value itself is not exposed.
  - `quaternion_raw` (array of 4) and `quaternion_order="unverified"`.
- Name check: routine names in `data/routines/k1.json` (772) and `k2.json` (877), compared case-insensitively. None equals `motion`, `capabilities`, `capture` or any capture field name. `x`, `y` and `z` occur only as argument names, never as routine names.

## Tests (`tools/kp_motiontest.cpp`)

The plan's seven M1 names are all present, marked with *. The rest are additions.

| Test | Line | What it asserts |
|---|---|---|
| *motion.unsupported_profile_capabilities_false | :97 | 7 other build SHAs, `""` and `wrong` all fail with Unsupported; so do a null backend, width 8, a Darwin ABI and base 0. An unbound capture is Unsupported with 0 getter calls. On the Linux host `native_backend` is null and `bind_native` fails, including with a null reader |
| motion.relocated_image_refused | :126 | base+0x10000 is Unsupported and says "relocated" |
| motion.span_table_valid | :133 | 23 spans valid; negatives: empty, odd length, uppercase, non-hex, 17 bytes, null |
| *motion.guard_flip_refuses_before_call | :146 | Every byte of every span, flipped before bind, gives Guard. Flipped after bind, then unmapped, gives Guard on capture with 0 getter calls and an untouched out. Each of the 4 slots, wrong at bind and zero after bind, gives Guard |
| motion.chain_failure_refuses_before_call | :175 | Manager null or unreadable, server null, internal null, array null or unreadable: each is Chain with 0 calls |
| motion.invalid_object_id_refused_before_call | :192 | 0x7f000000 is Identity with 0 calls |
| *motion.non_placeable_type_refuses | :197 | Type 5, 10, 6 and 0 give Identity after exactly 1 call. An unknown id (getter returns null) gives Identity |
| motion.wrong_vtable_refuses | :208 | CSWSObject vtable 0x745f18, vtable+4, 0 and unreadable: each is Identity |
| motion.id_roundtrip_mismatch_refuses | :217 | `[obj+4]` != id gives Identity |
| *motion.capture_reads_server_xyz_and_orientation | :222 | Reads XYZ, orientation, area id, facing, the gate (0, 1, 0xdeadbeef raw) and the dirty masks (1→none, 2, 4, all). Marker -1/0/3 maps to the boolean. Facing 0/90/180/270, and orientation (1,-1e-7) stays below 360. The quaternion passes through raw. 14 calls for 14 captures |
| motion.nonfinite_value_refuses | :253 | NaN and ±inf in 7 float slots give Value with an untouched out |
| motion.unreadable_field_refuses | :262 | 9 fields unmapped, one at a time: refused with an untouched out |
| *motion.accepts_client_id_0xffffffff | :272 | 0xffffffff, 0x7fffffff, 0x80000001 and 0 each reach the getter exactly once and capture |
| motion.unbind_bumps_epoch | :283 | After unbind, capture is Unsupported; after rebind the epoch is larger |
| motion.lua_unbound_capabilities_false | :309 | `available==false` and `writes==false`; capture returns `unsupported:`; 0 calls |
| *motion.forged_userdata_argerror | :320 | A `newproxy` given the capture metatable fails; a zeroed same-size userdata fails with "magic"; writing a field fails |
| motion.lua_capture_surface | :336 | `kp.motion` keys are exactly `capabilities,capture`. There is no relocate, restore or observe, and no NWScript-shaped alias. Ten bad ids return `value:` with 0 calls. All fields are checked, and tables are copies. An unknown id or a type-5 object returns `identity:` |
| *motion.profile_matches_address_table_row | :400 | Reads `data/addresses/k1_gog_103.json` read-only and is strict on existing rows: `server_object.set_position` addr 0x004CD1A0 with expected_bytes equal to span 0x4cd1a0; `object.id` +4/4; `object.type` +8/1; `g.app_manager` 0x007A39FC; `event.placeable` 0x00587BA0 equal to vtable slot +0x78. Motion rows must match when present, otherwise they are printed as PENDING |
| motion.bindings_json_matches_profile | :439 | Diffs the C++ profile against `k1_gog_103_motion_bindings.json`: all 23 guards (order, VA, bytes), 4 slots, 7 field offsets and sizes with verdict accept, the getter addr and the vtable addr. Mutation check: changing one guard byte in a temp-root copy fails exactly this test (`19/20`) |
| motion.spans_match_reference_image | :481 | Re-reads all 23 spans and 4 slots from the raw image (`$KP_K1_GOG_IMAGE`, or `$HOME/biodecompwarehouse/…/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`); SKIP if absent. It ran here |

## Commands and outputs

The build and run below happen in the scratch dir `/tmp/kp-motion-build`. `g++` is the host wrapper. The 32-bit binary runs via `host-cmd`, because this container has no 32-bit loader.

```
W=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
g++ -std=c++20 -m32 -Wall -Wextra -O1 -I$W/src -I$W/third_party/luajit/src \
  tools/kp_motiontest.cpp src/api/motion.cpp src/api/motion_profiles.cpp src/api/motion_backend.cpp src/api/motion_lua.cpp \
  /run/media/brunner56/MyBook/Workspaces/KotorPhasor/build/luajit32/src/libluajit.a -lm -ldl -o /tmp/kp-motion-build/kp_motiontest
host-cmd sh -c "/tmp/kp-motion-build/kp_motiontest $W"
```

Red run (stub core, backend and Lua). Stored at `/tmp/kp-motion-build/red.txt`:
```
FAIL motion.unsupported_profile_capabilities_false: line 123: op.bind(k1().sha256,f.base,&f,e)
FAIL motion.relocated_image_refused: line 130: e.find("relocated")!=std::string::npos
FAIL motion.span_table_valid: line 135: Operations::valid_span(s)
FAIL motion.guard_flip_refuses_before_call: line 154: op.last_failure()==Failure::Guard
... (13 more FAIL, all on bind or `kp` nil)
PASS motion.profile_matches_address_table_row
PASS motion.spans_match_reference_image
2/19 tests passed, 239 checks (synthetic memory; no live ABI proof)
```
The two red-phase passes check profile data only, not the core.

The green run went through two test-side fixes before it passed, then one core fix:
- The quaternion literals `.1f` compared unequal under `-m32 -std=c++20` (x87 excess precision). I changed them to exactly representable values.
- The expected call count was wrong, 15 instead of 13.
- Review found that `facing` could equal 360.0. I added the test first; it failed red (`/tmp/kp-motion-build/facing-red.txt`: `FAIL ... line 247: c.facing>=0.f&&c.facing<360.f`, 18/19). Then I fixed the core.

Final run, stored at `/tmp/kp-motion-build/green.txt`:
```
PASS motion.unsupported_profile_capabilities_false
... (16 more PASS)
  PENDING regeneration: server_object.area_id
  PENDING regeneration: server_object.position
  PENDING regeneration: server_object.orientation
  PENDING regeneration: server_object.client_push_gate_unverified
  PENDING regeneration: server_object.dirty_bits
  PENDING regeneration: placeable.aabb_registered
  PENDING regeneration: placeable.quaternion_raw_order_unverified
  PENDING regeneration: server.get_placeable_by_object_id (proposed row)
  PENDING regeneration: placeable.vtable (proposed row)
PASS motion.profile_matches_address_table_row
PASS motion.bindings_json_matches_profile
PASS motion.spans_match_reference_image
20/20 tests passed, 2926 checks (synthetic memory; no live ABI proof)
exit=0
```

mingw compile check (`/tmp/kp-motion-build/mingw.txt`; re-run after the facing fix, `mingw2.txt`, still clean):
```
host-cmd sh -c "cd $W && for f in motion motion_profiles motion_backend motion_lua; do \
  i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2 -I$W/src -I$W/third_party/luajit/src -c src/api/$f.cpp -o /tmp/kp-motion-build/mingw/$f.o || echo FAILED $f; done"
```
- There were no warnings and no FAILED lines. `_WIN32` and `__i386__` are both defined.
- `nm` lists `(anonymous namespace)::Native::placeable`.
- Its disassembly loads `ecx`=server (`mov 0x10(%ebp),%ecx`), pushes one stack arg, `call *%eax`, then `sub $0x4,%esp`. The `sub` is the compiler re-adjusting after a callee that cleans up, which matches `ret 4`.

Data check, a scratch script that does not import the generator: `python3 /tmp/kp-motion-build/check_motion_data.py $W`
```
sites 283 duplicate names []
OK  server_object.area_id CSWSObject::area_id ['k1_gog_103_motion_bindings.json']
... (6 more OK)
OVERLAP ... (5 pre-existing harness `sizeof` rows; none involve motion)
motion data check: PASS
```

## Integration snippet (for the serialized I-M integrator; I did not touch these files)

`src/runtime/runtime.cpp`:
- Include: `#include "api/motion.hpp"`.
- In the image-bind block after model/animation (about `:370-373`), reuse the existing `read_model` lambda (same `model::Reader` type):
  ```cpp
  if(!api::motion::bind_native(image_sha256_,runtime_base_,read_model,nullptr,model_error))
      log("motion: %s",model_error.c_str());
  ```
- In `register_all` after `api::model::register_all(L);` (about `:698`):
  ```cpp
  api::motion::register_all(L);     // read-only placeable capture (K1 GOG)
  ```
- Next to both `api::model::operations().unbind();` (about `:785` and `:848`):
  ```cpp
  api::motion::operations().unbind();
  ```

`src/runtime/runtime.cmake`, next to the model sources (`:61-64`):
```cmake
    "${KP_SRC_ROOT}/api/motion.cpp"
    "${KP_SRC_ROOT}/api/motion_profiles.cpp"
    "${KP_SRC_ROOT}/api/motion_backend.cpp"
    "${KP_SRC_ROOT}/api/motion_lua.cpp"
```

`CMakeLists.txt`, after `include(.../src/api/camera.cmake)` (`:137`):
```cmake
include(${CMAKE_CURRENT_SOURCE_DIR}/src/api/motion.cmake)
```

`tools/kp_namespacetest.cpp`. It links `kphasor`, so it needs the runtime.cmake sources first.
- Add `#include "api/motion.hpp"`.
- In `install_native` after `kp::api::entity::register_all(L);`, add `kp::api::motion::register_all(L);`.
- In the contract Lua, add:
  ```lua
  assert(type(kp.motion.capabilities) == 'function' and type(kp.motion.capture) == 'function')
  assert(kp.motion.relocate == nil and kp.motion.SetPosition == nil and kp.motion.GetPosition == nil)
  assert(kp.motion.capabilities().writes == false)
  ```
- The existing routine loop (`:121-131`) already proves that no routine name appears under `kp`. The double `install` checks that re-registration keeps the table (`register_all` reuses `kp` and replaces `kp.motion`).

## Doc text (for `docs/lua-api.md` and `docs/user/api-status.md`; the integrator places it)

> ### `kp.motion` (read-only, K1 GOG only)
>
> `kp.motion.capabilities()` returns a table:
> - `available`, `profile` and `abi`.
> - `writes` (always `false` in this stage).
> - `reads`, the names of the fields a capture holds.
> - `limits`, a text note on what is not yet proven.
>
> `kp.motion.capture(id)` looks up a server placeable by its server object ID and returns a read-only capture. On any failure it returns `nil, "<kind>: <reason>"`:
> - `unsupported`: this build or host has no verified binding.
> - `guard`: the game code does not match the reviewed bytes.
> - `chain`: the server object table is not available.
> - `identity`: the ID is not a placeable.
> - `value`: the ID is not an exact whole number from 0 to 4294967295, or the object holds a non-finite number.
>
> A capture has these fields:
> - `id`, `area_id`, `epoch` and `object` (an address string for logs).
> - `position` and `orientation`, each a new `{x, y, z}` table on every read.
> - `facing`, in degrees from 0 up to 360.
> - `push_gate_raw`: a raw number. The engine uses it to decide whether it pushes this object's changes to the client. What its values mean is not yet known.
> - `dirty_position` and `dirty_orientation`: true when the server has a change that the next tick will push.
> - `collision_registered`: true when the placeable's walk-blocking box is registered with the area.
> - `quaternion_raw`: four raw numbers. Their order is not yet known, so `quaternion_order` is `"unverified"`.
>
> A capture cannot be changed. This stage has no call that moves anything. The names do not match any NWScript routine; use `nwscript.call('GetPosition', id)` for the engine's own answer.

`docs/user/api-status.md` row: `kp.motion.capabilities / capture` | K1 GOG | offline-tested (19 tests), live readback pending | read-only.

## Address-table entries the orchestrator must regenerate (`k1_gog_103.json`)

These 7 field rows are now in `data/hooksites.toml:2354-2411`, each backed by `k1_gog_103_motion_bindings.json`:

| hooksites name | key | offset | size |
|---|---|---|---|
| `server_object.area_id` | `CSWSObject::area_id` | 0x8C | 4 |
| `server_object.position` | `CSWSObject::position` | 0x90 | 12 |
| `server_object.orientation` | `CSWSObject::orientation` | 0x9C | 12 |
| `server_object.client_push_gate_unverified` | `CSWSObject::client_push_gate_unverified` | 0x1F8 | 4 |
| `server_object.dirty_bits` | `CSWSObject::dirty_bits` | 0x1FC | 4 |
| `placeable.aabb_registered` | `CSWSPlaceable::aabb_registered` | 0x344 | 4 |
| `placeable.quaternion_raw_order_unverified` | `CSWSPlaceable::quaternion_raw_order_unverified` | 0x428 | 16 |

Two more rows are proposed but not added, because I was allowed to add field rows only. Both are bound and inert in the bindings file:

```toml
[[site]]
name     = "server.get_placeable_by_object_id"
class    = "CServerExoApp"
method   = "GetPlaceableByGameObjectID"
kind     = "call"
required = false
purpose  = "CSWSPlaceable* __thiscall(this, uint32_t server_object_id). Typed placeable lookup used by kp.motion."
convention = "thiscall"

[[site]]
name   = "placeable.vtable"
class  = "CSWSPlaceable"
method = "vtable"
kind   = "reference"
required = false
purpose = "Exact identity of a server placeable. Compared as a pointer."
```

The function would also resolve through the corpus func layer (`func binary_id=8 0x4ae7a0 CServerExoApp::GetPlaceableByGameObjectID USER_DEFINED`), so the binding would show "func row agrees". Expected bytes after regeneration: `8b4904e9283100009090909090909090`. After regeneration, `kp_motiontest` turns every PENDING line into a strict check.

Not rebound on purpose: `CSWSObject::SetPosition`, `CGameObject::id` and `CGameObject::object_type` already resolve. Rebinding them would change their `source` and `method_detail` on the next regen.

## Other readers of the changed data (for the regen step)

`grep -rln "hooksites.toml\|_bindings.json\|adjudication" tools/*.py tools/*.cpp CMakeLists.txt src/*/*.cmake` finds these readers:

- `tools/gen_address_tables.py`: not run, as instructed. The 7 new `[[site]]` rows are global, so the next regen adds 7 entries to **every** build's table, not only k1_gog_103.
  - Overlays load per alias stem (`load_overlay(alias)`, `gen_address_tables.py:581`). So only `k1_gog_103` resolves them.
  - Every other build, including both K1 Steam tables, gets the 7 rows as `unresolved`. That is harmless, because all 7 are `required = false`.
  - If any check compares committed tables to the manifest, regenerating only the GOG table would leave it red on the other builds. Regenerate all tables together.
- `tools/camera_profile_consistency_test.py`: reads only the camera overlay. See the run below.
- `tools/nwscript_boundary_test.py`: a lexical scan of active source for removed-root paths and duplicate routine calls. It covers `src/api/motion*` and `tools/kp_motiontest.cpp`. See the run below.
- Results, via `host-cmd sh -c "python3 tools/nwscript_boundary_test.py | tail -3; python3 tools/camera_profile_consistency_test.py | tail -3"`:
  - Boundary test: its only finding is `docs/devtools-design.md:134: dotted member on removed host root: kotor.lua`. That is a pre-existing staged doc from another writer; there are no findings in any motion file. The printed `rc=0` belongs to `tail`, not to the test, so I read the violation line as the test failing on that doc.
  - Camera consistency: `Ran 5 tests ... OK`.
- `tools/kpharness_offline_test.py`: asserts specific harness rows in `k1_gog_103.json` / `k1_steam_103.json`. It does not touch the motion rows; not run.
- `tools/contribute_findings.py`: reads only `*_vm_bindings.json`, so it is unaffected. `package_creative_harness*.py` deny-list `data/adjudication/` from packaging, which is also unaffected.

## M1 live readback checklist

This comes from the receipt's "What live readback M1 must prove" and the verification. Only reads are involved. Spawning the one crate is the single scene change.

1. **Spawn.** Create one disposable footlocker with `nwscript.call('CreateObject', …)` and note its id.
2. **Capabilities.** `kp.motion.capabilities().available == true` and `profile == "windows-k1-gog"`.
3. **Type fence.**
   - `kp.motion.capture(crate)` succeeds.
   - `kp.motion.capture(GetFirstPC id)` returns `identity:`.
   - A creature id returns `identity:`, because the typed getter returns null for type ≠ 9.
4. **Pose oracle.** `capture.position` equals `nwscript.call('GetPosition', crate)` within 1e-3 on x, y and z.
5. **Facing.** `capture.facing` equals `GetFacing(crate)` within 0.01°. Record whether GetFacing uses [0,360) or (-180,180]; this is open.
6. **Area.** `capture.area_id` equals the id of `GetArea(crate)`.
7. **Sync gate at rest.** For an on-screen crate in the player's area, `push_gate_raw ~= 0`, and `dirty_position == false` and `dirty_orientation == false`. This records a raw value only; it makes no claim about what the value means.
8. **Collision marker.** Record `collision_registered` for the crate. It is expected true for a model with a walkmesh; record it and do not assert it.
9. **Quaternion order.** Capture a GIT placeable with a non-zero `Bearing` and compare `quaternion_raw` against the bearing to settle (w,x,y,z) versus (x,y,z,w).
10. **No mutation.** Capture twice with nothing in between. Every field is identical, the source receipt is unchanged, and no `[model]`/setter log lines appear.

Receipt items 5-7 (dirty consumption, same-position no-op, collision state after SetPosition) need a write, so they belong to M2.

## Deviations and open items

- The fixture lives in `tools/kp_motiontest.cpp`, not `tools/tests/motion_backend_fixture.hpp`, because only the test file was allowed.
- The plan listed `capture` fields "id, type-checked placeable pointer, server XYZ, orientation vector, area and epoch". I added the gate, dirty bits, collision flag, facing and raw quaternion, as the brief asked.
- `facing` normalisation versus GetFacing, the quaternion order and the gate's meaning are all unverified. They are named that way in code, in data and in `capabilities().limits`.
- Keep-out list honoured: +0x3A0, +0x3C0, +0x3D8, 0x50DC40, 0x50DFD0, client vtbl+0x12C/+0x130/+0x134, the 0x506FE0 reverse pass, 0x52CCE0 and "+0x24" appear nowhere except the bindings `open_items` keep-out note.
- Nothing is live. The whole claim is "offline, synthetic memory, K1 GOG byte guards match the reference image".

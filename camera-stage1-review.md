# Review: kp.camera Stage 1 (read-only snapshot and capabilities, K1 GOG only)

Date: 2026-09-27. Reviewer: an independent agent that wrote none of the code.

Scope: the worktree `.worktrees/lua-boundary-validation`. The source tree was only read. Scratch builds went to `review-probes-camera/`. No game, Wine or live-game lock was touched.

I formed my view from the code, the specs and the image before reading the writer's report (rule 1).

## Stage A: spec compliance

| Requirement (plan §2, rederivation) | Result | Referent |
|---|---|---|
| Uses only safe-list offsets | holds | The 26 offsets and addresses in `camera_profiles.cpp` are each in the rederivation "safe" table. The raw +0x28/+0x38/+0x50 fields are named `*_unverified`. |
| Every pointer hop is fallible and guarded | holds | `camera.cpp` `pointer()` routes each hop through `Backend::read` and rejects 0. The native reader is `LiveImage::read` (VirtualQuery + ReadProcessMemory, `loaded_image.cpp:45`). There are 7 hops, and the chain tests at `kp_cameratest.cpp:137-157` cover null and unmapped for each. |
| Guard bytes match the image | holds | All 31 spans and 4 slots are byte-exact and decode to the claimed instruction (host objdump, below). `.data` raw offset equals RVA (`.data` raw 0x38d000/0x17000), so the -1 at 0x7a242c is a real file byte. |
| Every profile offset is pinned by a span | holds | client +4 is pinned by 0x64b996 `mov ecx,[eax+4]`. internal +4 by 0x5ed530. module +0x18 by 0x644760. options by 0x5ed700. mode +0x6d by 0x61b6f6. camera +0x40 by 0x64b9b0. The behaviour slot by 0x45c160 (+4) and 0x43f5a0 (+0x188). Chase fields, dolly, base, style_row, pending and raw each have their own span. |
| Fails closed on other builds, at bind and per call | holds | `bind` checks sha, abi, width, base and relocation. `snapshot` re-runs `guards()`, which fails `Unsupported` after unbind. Test: 7 other SHAs plus ""/"wrong" at `kp_cameratest.cpp:28-38`. |
| No engine call from snapshot | holds | `Backend` has no call method (`camera.hpp`). The native adapter only reads (`camera_backend.cpp`). |
| No partial output | holds | `out = {}` on entry, and `out = c` only on the success paths (`camera.cpp` snapshot). The "other" behaviour case returns identity only, by design, and the docs say so. |
| Userdata is protected | holds | Magic plus length plus `luaL_checkudata`, and `__metatable` is locked. Forged, `newproxy` and zero-filled captures are rejected in the test (`:219-224`). |
| Lua names vs NWScript | holds | Only `capabilities` and `snapshot` are exported. `test_lua_names_are_not_routines` passes against more than 700 routine names. The test also asserts that no `SetCameraFacing`, `SetCameraMode` or `set_distance` key exists. |
| hooksites rows are optional; motion rows after them are preserved | holds | The diff adds 20 camera rows with `required = false`. The kp.motion block that follows is intact. |
| Regenerated `k1_gog_103.json` changes only intended entries | holds | Against HEAD: 20 sites added, 0 removed, 0 changed. `adjudicated_bindings` goes 199→219, `summary.total` 256→276. |
| Docs are honest | **does not hold yet** | The docs say "host-tested". The host test is red (see I1). Otherwise the text is accurate: K1 GOG only, no live proof, raw fields unverified. |

## Findings

### Critical
None.

### Important

**I1. `kp_cameratest` fails under the project's own flags, and the writer's "fixed" claim does not hold.**
- claim: "the test is fixed / host-tested" (writer, docs)
- referent:
  - A fresh scratch build with `-O3 -DNDEBUG -std=c++20 -m32 -Wall -Wextra` (flags copied from `/tmp/kp-w1-build/build.ninja`) exits rc=1 with `line 103: c.raw_28[0]==.1f*1&&...`. The existing `/tmp/kp-w1-build/kp_cameratest` fails the same way, so the binary is not stale.
- checked:
  - `probe103.cpp` prints the stored bits `3dcccccd` / `3ecccccd`, which are the correct float values. Terms t0 and t1 are false; t2..t4 are true.
  - `__FLT_EVAL_METHOD__` = 2 under `-std=c++20 -m32`.
  - `CMakeLists.txt:50` sets `CMAKE_CXX_EXTENSIONS OFF`, so the build uses `-fexcess-precision=standard`. Under that setting the literal `.1f*1` is evaluated in x87 long double, so it is not equal to the float stored on the fixture side.
  - The same probe passes with `-std=gnu++20`, with `-fexcess-precision=fast`, and with `-msse2 -mfpmath=sse`. That is likely how the writer saw it pass.
- verdict: this is a test-assertion defect. Production reads are correct. It is blocking because the Stage 1 offline gate is red and the docs claim "host-tested".
- fix:
  - Compare against `static_cast<float>(.1f*1)` and `static_cast<float>(.1f*4)`, or use fixture values that are exact in binary (0.5f, 0.25f).
  - Checked in scratch: with only line 103 changed, the suite prints `camera checks passed: 1818` at both -O0 and -O3 (rc=0).
- confidence: high. Only a different compiler or flag set would change it.

### Minor

**M1. The overlay under-cites the two-signal rule for three bindings. The substance holds when checked.**
- METHOD.md's field rule (lines 196-205) asks for a declaration or two decompiled consumers, plus an immediate. The overlay's `accept_rule` substitutes "two derivations of the same immediate plus a second code site".
- For `camera_mode`, the cited second site is the same function (0x61b6f0 "also writes +0x6e").
- For `raw_38` and `raw_50`, the second signal cites the same ResetLastPosition site again.
- I checked the image myself:
  - `GetClientOptions` is followed by `cmp byte [eax+0x6d],5` at 0x5f6046, 0x60b94b, 0x615b71 and more (10+ call sites).
  - The chase ctor stores +0x38..+0x40 and +0x50..+0x58 at 0x63a011..0x63a02c and 0x63a28f..0x63a2a4.
  - The copy-ctor does the same at 0x63adb4..0x63adcc and 0x63afd3..0x63b012.
- So every binding does have two independent sites. Cite them in the overlay.

**M2. Spec naming drift, consistent across the docs.**
- `behavior` is `"chase"`, not `"on_a_stick"`.
- `dolly` and `pending_style` are raw ints, not booleans.
- Orientation and position are `raw_*_unverified`.
- These are defensible (raw beats decoded for a possibly uninitialised +0x84), but the spec (§2a) is not followed verbatim.

**M3. A camera or owner vtable mismatch is refused, not returned as an identity-only capture.**
- The spec contradicts itself here: §2b and §2e say "identity-only capture", while §2e also says "is refused".
- The refusal carries the observed hex in the message (`kp_cameratest.cpp:161-165`), so the L1 diagnostic value survives.

**M4. Spans are 16 bytes or fewer, not the plan's whole-function spans.**
- The plan's spans are, for example, 0x637a30/0xb9 and 0x64b991/0x6c.
- Every offset is still pinned by a verified instruction, and all four vtable slots are checked. The narrower spans catch less patch drift but do not weaken identity.

**M5. The engine-thread requirement is structural, not enforced by `kp.camera`.**
- Every Lua state that registers `kp.camera` runs on the main-loop hook:
  - host hooks
  - `console().pump(init_lua_state)`
  - `harness::drain()` (`hook_bodies.cpp:767-769`, `1276-1278`)
- The console state uses the same registrar (`runtime.cpp:692-712`).
- If something called it off-thread, it would not fault (fallible reader). It could see torn object state, though. `Operations` is also unsynchronised: `guards()` checks `profile_`, and then `*profile_` is used after it, so a concurrent `unbind()` would race. This is inherited from `model`, and `stop()` is documented as needing a quiescent point.

**M6. The finiteness gate covers +0x88/+0x8c.**
- Those two fields are written only on the camerastyle.2da path. On a default (no-2DA) chase they may be heap garbage, and a NaN there refuses the whole snapshot.
- The copy-ctor does initialise +0x28..+0x58 (0x63ada4..0x63adcc), so the raw fields are not at risk.
- Retail ships the 2DA, so this is low risk. It is still worth knowing before the single L1 launch.

**M7. `docs/camera-api.md` (plan §2d) was not created.** The `lua-api.md` section covers the contract. The two derivation docs live outside the repo but are pinned by SHA-256 in the overlay; both SHAs match.

**M8 (cross-stage, not camera's defect). `k1_gog_103.json` predates the kp.motion rows.**
- A fresh `gen_address_tables.py --build k1_gog_103` from current inputs, run in a scratch copy, adds exactly 7 motion sites (228 vs 219 adjudicated). All camera rows are byte-identical.
- `tools/kp_motiontest.cpp` cross-checks this table, so the motion owner must regenerate.
- `address_table_layout_test.py` passes (26 tests).

**M9. Protocol.** The writer's report has no "Grill me" section. It also reports "red-first offline checks complete" without a passing `kp_cameratest` receipt: it shows only that the build succeeded.

## Grill (the writer supplied none, so these are the reviewer's own)

1. Why does line 103 pass for you and not for ctest? Answered by I1: x87 excess precision with `CXX_EXTENSIONS OFF`.
2. Is `camera_mode` two-signal? It holds after my own check (M1). The overlay does not show it.
3. Can a snapshot be refused on a restore-path chase camera? Only through +0x88/+0x8c with no 2DA (M6). The raw fields are initialised by the copy-ctor.
4. What stops an off-thread call? Nothing in `kp.camera`; it relies on hook placement (M5).

The one question I could not settle is the live value of +0x84 (and +0x88/+0x8c) on a copy-constructed chase camera. One check would settle it: an L1 `snapshot()` after a mode change that goes through the restore path (0x641dc0 → 0x642221).

## Commands and outputs

```
# fresh scratch build, project flags, reused /tmp/kp-w1-build/luajit32/src/libluajit.a
host-cmd sh -c 'g++ -std=c++20 -m32 -Wall -Wextra -I$W/src -I$W/tools -I$W/third_party/luajit/src \
  $W/tools/kp_cameratest.cpp $W/src/api/camera{,_profiles,_backend,_lua}.cpp libluajit.a -lm -ldl -o kp_cameratest; ./kp_cameratest'
line 103: c.raw_28[0]==.1f*1&&c.raw_28[3]==.1f*4&&c.raw_38[0]==10.f&&c.raw_38[2]==12.f&&c.raw_50[1]==21.f
rc=1            (/tmp/kp-w1-build/kp_cameratest: same line, rc=1)

./probe103  -> raw_28[0] bits=3dcccccd ... t0=0 t1=0 t2=1 t3=1 t4=1
-std=gnu++20 / -fexcess-precision=fast / -msse2 -mfpmath=sse -> t0=1 t1=1 ...
__FLT_EVAL_METHOD__ = 2

# line 103 wrapped in static_cast<float> (scratch copy only)
-O0: camera checks passed: 1818 (K1 GOG profile, synthetic memory; no live proof)  rc=0
-O3 -DNDEBUG: camera checks passed: 1818 ...  rc=0     (no compiler warnings)

python3 tools/camera_profile_consistency_test.py
Ran 5 tests in 8.903s  OK   (image present; test_image_bytes ran, not skipped)

python3 spans2.py   (stdlib PE parse + host objdump; the capstone venv hung)
sha 9c10e045...91435; ImageBase 0x400000; no reloc dir
31/31 spans OK, each decoding as labelled (e.g. 0x64b996 mov ecx,[eax+0x4]; 0x43f5a0 mov ecx,[ecx+0x188])
4/4 slots OK; pending init -1 at mapped offset 0x3a242c; mismatches 0

git show HEAD:data/addresses/k1_gog_103.json vs worktree: added 20 (camera only), removed 0, changed 0
scratch regen --build k1_gog_103: 283/283 resolved; +7 motion sites only; camera rows identical
python3 tools/address_table_layout_test.py: Ran 26 tests OK
```

Scratch artefacts are in `/home/brunner56/kp-live-20260922/review-probes-camera/`: `probe103.cpp`, `kp_cameratest_fixed103.cpp`, `spans2.py`, `text.asm` and `regen/`.

## Claim blocks

```
claim: production snapshot reads only safe-list offsets through guarded fallible hops
referent: camera.cpp snapshot(); spans2.py 31/31 + 4/4; kp_cameratest chain tests
checked: image bytes + scratch run (1818 checks with line 103 fixed)
verdict: holds
confidence: high statically; a live L1 read would raise it further

claim: kp_cameratest passes (writer)
referent: none in the report (build only)
checked: scratch and /tmp builds both rc=1 at line 103
verdict: does not hold
confidence: high
```

Camera Stage 1 verdict: FAIL

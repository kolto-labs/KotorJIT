# `kp.camera` Stage 1 — K1 GOG-only report

Status: implementation and red-first offline checks complete; the requested clean
32-bit CMake/CTest rerun is recorded below.  This is strictly a read-only surface:
`kp.camera.capabilities()` and `kp.camera.snapshot()` only.  It does not establish
that a snapshot has been taken from a running game.

## Delivered surface

- K1 GOG 1.03 profile only, keyed to SHA-256
  `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`.
  Unsupported image, ABI, width, base, code-span, literal, or vtable checks fail
  closed.
- `kp.camera.capabilities()` reports availability, profile, ABI, that writes are
  disabled, and the host-test/no-live-proof limitation.
- `kp.camera.snapshot()` returns protected userdata.  It makes no engine calls;
  it follows app manager → client → internal → camera owner → camera → active
  behaviour entirely through fallible reads.  It exposes the four named chase
  values and the raw `+0x28`, `+0x38`, and `+0x50` values explicitly as
  meaning-unverified fields.
- The profile guards the requested identities: camera vtable `0x741b20`, owner
  vtable `0x751848`, chase/OnAStick vtable `0x75165c`, and its TypeId routine
  returning `0x106a`.  It reports the `+0x84` dolly word raw; the re-derivation
  says it can be uninitialised on the copy-constructed mode-restore path.

## Evidence and reviewed data

`data/adjudication/k1_gog_103_camera_bindings.json` contains both the original
plan and the independent re-derivation as derivations, plus two or more signals
per accepted binding.  `data/hooksites.toml` has optional camera rows, and only
`data/addresses/k1_gog_103.json` was regenerated (never `--all`).

The offline consistency test verified the profile, overlay, generated K1 GOG
table, image SHA, every code/literal guard span, vtable slots, and that exported
Lua names do not duplicate NWScript routine names:

```
python3 tools/camera_profile_consistency_test.py
Ran 5 tests in 3.910s
OK
```

## Native test rerun

Command requested and launched through the host boundary:

```
cmake --build /tmp/kp-w1-build --target kp_cameratest -j1
ctest --test-dir /tmp/kp-w1-build \
  -R '^(kp_cameratest|camera_profile_consistency_test)$' --output-on-failure
```

The serial native build completed and produced `/tmp/kp-w1-build/kp_cameratest`
(837,964 bytes).  CTest's `camera_profile_consistency_test` was still in host
I/O wait when this report was written; do not interpret this report as a final
clean CTest pass until that process exits with its receipt.  No game, Wine,
Gamescope, capture service, or live-game lock was used or touched.

## Documentation

- `docs/lua-api.md` documents the two API calls, capability limitations, protected
  capture, individual values, and raw-field caveat.
- `docs/user/api-status.md` marks both calls host-tested, K1 GOG-only, and not
  live-proven.

## Remaining acceptance boundary

Host/synthetic-memory validation is not live-game validation.  A future live
K1 GOG-only owner must prove the application can bind and obtain a stable
snapshot; no write API is included in this stage.

## Fix round 1 (2026-09-27): review FAIL on I1, plus M1

Review: `/home/brunner56/kp-live-20260922/camera-stage1-review.md`. It failed only on I1.

### I1: `tools/kp_cameratest.cpp:103`, x87 excess precision

- The literals `.1f*1` and `.1f*4` are now wrapped in `static_cast<float>(...)`. The comment says why: `-m32` with `CMAKE_CXX_EXTENSIONS OFF` gives `__FLT_EVAL_METHOD__` 2, so the unrounded product is a long double.
- Scan of the rest of the test for the same pattern:
  - `grep -nE '[0-9.]f\s*[*/+-]\s*[0-9.]|[*/+-]\s*[0-9.]+f\b'` matches only line 103.
  - The other C++ float compares use single literals that are exact in binary: 6.25f, 20.f, 80.f, 3.5f, 55.f, 10.f, 12.f and 21.f.
  - The Lua asserts at lines 212-213 compare doubles against 6.25, 3.5 and integers, which are all exact. Line 214 already uses a `1e-6` tolerance.
  - No other sites needed a change.

### M1: independent second sites added to the overlay

I verified these bytes myself in the raw image (sha256 `9c10e045...91435`, PE section mapping), and they match the reviewer's `text.asm`. Each is now a third `signals` entry in `data/adjudication/k1_gog_103_camera_bindings.json`:

- `CClientOptions::camera_mode`:
  - `e8ba76ffff80786d05` @0x5f6041. That is `call 0x5ed700` (GetClientOptions) and then `cmp byte [eax+0x6d],5`.
  - The same `80786d05` also appears @0x60b94b and @0x615b71.
- `CSWCameraOnAStick::raw_38_unverified`:
  - `897e38` @0x63a011 in the OnAStick ctor. The ctor's vtable store `c7065c167500` is @0x639fee.
  - `897e38` @0x63adb4 in the copy-ctor. Its vtable store is @0x63ad94.
- `CSWCameraOnAStick::raw_50_unverified`:
  - `897e50` @0x63a026, through `897e58` @0x63a02c.
  - `897e50` @0x63adc6, through @0x63adcc.
- `gen_address_tables.py` does not emit evidence text into `k1_gog_103.json` (`grep -c ResetLastPosition` = 0), so that table is not stale. `python3 -m json.tool` passes.

### Minor findings recorded, not fixed this round

- **M5, engine thread not enforced.**
  - `kp.camera` depends on hook placement, the same way the model API does. Every registering Lua state runs on the main-loop hook.
  - An off-thread call would not fault, because the reader is fallible. It could still see torn object state.
  - `Operations::guards()` followed by `*profile_` would race a concurrent `unbind()`.
  - This is inherited from `model`. It stays open until a shared thread-affinity check lands for all APIs.
- **M6, NaN refusal risk at +0x88/+0x8c.**
  - Only the camerastyle.2da path writes these two fields. On a no-2DA chase camera they may be uninitialised, and a NaN there makes the finiteness gate refuse the whole snapshot.
  - Retail ships the 2DA, so the risk is low.
  - The L1 check that settles it is `snapshot()` after a mode change through the restore path (0x641dc0 -> 0x642221).
- **M2, spec naming drift.**
  - `behavior` is `"chase"`, not `"on_a_stick"`.
  - `dolly` and `pending_style` are raw ints, not booleans.
  - Orientation and position are `raw_*_unverified`.
  - This is deliberate: a raw value beats a decoded one for possibly uninitialised fields. The docs are consistent with the code, but the spec §2a is not followed verbatim.
- M3, M4, M7 and M8 are unchanged, as the review describes. M8 belongs to the kp.motion owner, who must regenerate `k1_gog_103.json`.

### Receipts

```
$ host-cmd sh -c 'cd /tmp/kp-w1-build && ninja kp_cameratest && ./kp_cameratest; echo rc=$?; ctest --test-dir /tmp/kp-w1-build -R "^(kp_cameratest|camera_profile_consistency_test)$" --output-on-failure'
[13/16] Building CXX object CMakeFiles/kp_cameratest.dir/tools/kp_cameratest.cpp.o
[16/16] Linking CXX executable kp_cameratest
camera checks passed: 1818 (K1 GOG profile, synthetic memory; no live proof)
rc=0
1/2 Test #22: kp_cameratest .....................   Passed    0.05 sec
2/2 Test #23: camera_profile_consistency_test ...   Passed   86.04 sec
100% tests passed, 0 tests failed out of 2

$ python3 tools/camera_profile_consistency_test.py -v
test_image_bytes ... ok   (image present, not skipped)
Ran 5 tests in 0.608s
OK
```

No game, Wine or live-game lock was touched. Nothing was staged or committed.

### Grill me

1. **Does the fix hold on a build other than `/tmp/kp-w1-build`, for example an SSE2 or gnu++20 config?**
   - `static_cast<float>` rounds to float under every `FLT_EVAL_METHOD`, so it should.
   - I ran only the project flags here. The reviewer's scratch run passed at -O0 and -O3 with the same change.
   - Unverified for SSE builds in this round.
2. **Are the ctor stores at 0x63a011/0x63a026 really inside the chase ctor, and not a neighbouring function?**
   - `text.asm` shows `mov esi,ecx` @0x639fe0 and the vtable store @0x639fee.
   - No `ret` appears between those and 0x63a02c.
   - The copy-ctor is the same shape: `mov esi,ecx` @0x63ad83, then the vtable store @0x63ad94.
3. **Is the cmp at 0x5f6046 independent of SetCameraMode?**
   - Yes. It is a reader in another function that reaches +0x6d through the GetClientOptions call. `e8ba76ffff` resolves to 0x5f6046+0xffff76ba = 0x5ed700.
4. **Does adding a third signal break the overlay schema?**
   - No. `test_overlay_records_guards_and_derivations` only requires at least 2 signals, and it passes.
   - `derivations` still holds exactly two roles.

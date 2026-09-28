# KotorPhasor native `kp.camera` API: staged plan (K1 GOG first)

Prepared 2026-09-27. Read-only planning. I edited no file in the repository. I launched no Wine, game, Gamescope or FFmpeg, and did not touch `tmp/harness-locks/live-game.lock`. This file is the only file I wrote. Every byte-level claim below comes from in-memory reads of the authoritative raw image (read-only `python3` and `i686-w64-mingw32-objdump` pointed at the image file). The replay commands are in §7.

Paths:

- WT = `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
- IMG = `~/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`. Its SHA256 is `9c10e045…91435`, the same as `WT/docs/research/camera-win-k1.md:3` and the `windows-k1-gog` profile in `WT/src/api/model_profiles.cpp:17`.
- FP = `/home/brunner56/kp-live-20260922/task7-k1-framing-plan.md`

## 0. Bottom line

1. **A read-only `kp.camera.snapshot()` is feasible without calling any engine function.** Everything is plain reads. The chain is: app manager → client → client internal → module → camera → active behaviour → four named `m_f*` floats, plus orientation and position.
   - Every hop has a candidate offset, and each offset is written literally in code bytes that can be guarded (§1).
   - **None of the new hops is adjudicated in the repository yet.** They were derived in this session. Stage 1 coding is blocked until a durable receipt exists and an independent reviewer has re-derived it (gate E1).
2. **The four camera properties are named by the engine itself.** `CSWCameraOnAStick::Message` (0x637a30) compares the first word of a command against these literals:
   - `m_fDist` → this+0x110
   - `m_fSpeed` → +0x114
   - `m_fPresetPitch` → +0x11c
   - `m_fHeight` → +0x120

   It then parses a float into that field. `SetCameraStyle` (0x638070) seeds the same four fields with 6.25 / 20 / 80 / 3.5 and then with `camerastyle.2da` values.
3. **`SetCameraFacing` is now more firmly expected to be inert under OnAStick.** The client handler sends the strings `yaw %f`, `pitch %f` and `dist %f` (0x64b9e3, 0x64ba43, 0x64ba13). OnAStick's Message matches only the four `m_f*` literals and does not call its parent. This strengthens `camera-win-k1.md:17`. It is still not live-proven, because the active behaviour in mode 2 has never been read.
4. **Configured distance is not effective distance. That question decides whether Stage 2 is worth building.**
   - m_fDist is the *target* distance.
   - `Control_HitCheckCamera` (0x63b050) never touches +0x110 (field scan, §7 R6). Collision therefore most likely moves the camera position without changing m_fDist.
   - If the RUN's 35% framing was collision-limited, `set_distance` would do nothing at that spot.
   - Stage 1's first live diagnostic must run a yaw-sweep invariance test: with the PC fixed and m_fDist, pitch and height unchanged, the horizontal radius |pos − pc_pos| (xy only) must stay constant while the view orbits.
   - A dip in radius that tracks the framing change points to collision. The camera sits at m_fDist from the *look-at point*, not from the PC origin, so a direct |pos − pc_pos| vs m_fDist comparison would be geometry, not evidence (§2h step 4).
5. **Stage 2 write path:** call the engine's own OnAStick `Message` with the command string `"m_fDist <float>"` and verify by readback.
   - Refuse the write when any of these holds:
     - the dolly flag at +0x84 is set, because `Control` then recomputes m_fDist every tick (0x63bcc1..0x63bcfa)
     - a camera-style reapply is pending (global 0x7a242c ≠ −1, 0x638fb3..0x638fc5)
     - the behaviour is not OnAStick
     - the capture is stale
   - Open evidence item: who writes 0x7a242c. An absolute-reference scan finds only the check itself.
6. **Stage 1 alone might meet the framing gate, but probably only if G1 is relaxed a little (estimate, §4).**
   - The only measured alternative view (CAL shot 0007) is 220 px (28.6%). G1's ≤ 211 px ceiling for a 2.0 giant rejects it by 9 px.
   - Four of the five clip-consistent fits (FP §2c) still keep ≥ 60 px of headroom at 220 px. The worst fit allows only 217 px.
   - No proven way exists to reproduce that view. Recommendation: build Stage 1 regardless, since it provides the in-route G5 readback. Decide Stage 2 from Stage 1's configured-vs-effective diagnostic.

---

## 1. Evidence ledger (three tiers)

### 1a. Established in the repository (usable now)

| Item | Value | Referent |
|---|---|---|
| Image identity, K1 GOG | SHA256 9c10e045…, base 0x400000 | `WT/docs/research/camera-win-k1.md:3`; `WT/src/api/model_profiles.cpp:17` |
| `g_pAppManager` | 0x7A39FC | `WT/data/addresses/k1_gog_103.json:2128-2142` (`g.app_manager`, adjudicated 0.95) |
| AppManager → client | +0x4 | `appmgr.client`, `WT/data/adjudication/k1_gog_103_harness_bindings.json:1156-1170` |
| CClientExoApp → internal | +0x4 | `client.internal`, same file `:1216-1230` |
| Camera vtable; slot +0x60 = 0x45c160 (Camera::BehaviorMessage) | 0x741b20 | `camera-win-k1.md:17` (I re-read the slot, §7 R3) |
| Camera::BehaviorMessage → Gob::BehaviorMessage 0x43f5a0 → active behaviour → vtable+0xc | chain | `camera-win-k1.md:17`. The doc's "activebehavior+0x188" is relative to the Gob (camera+4). |
| OnAStick::Message at 0x637a30 handles four `m_f…` commands with no yaw branch | 0x637a30 | `camera-win-k1.md:17`, with a 32-byte guard at `:39` |
| Client camera handler 0x64b8e0; SetCameraMode writes options byte +0x6d | 0x64b8e0, 0x61b6f0 | `camera-win-k1.md:13,19`, guard at `:37` |
| Codecave after `Control_CheckAndUpdateCameraStyle` | 0x638FD1 | `WT/data/codecaves.toml:9077-9082`. This is padding location only, not a field. |
| Adjudication accept rule for fields | a types.h declaration **plus** a disassembled consumer whose immediate is the offset | `k1_gog_103_harness_bindings.json` header `accept_rule`; `WT/data/adjudication/METHOD.md` §1 |

### 1b. Derived in this session only (not durable; must become a receipt, gate E1)

Each row names the code bytes whose immediate *is* the offset. Those bytes are also what the runtime guard should check (§2c).

| Hop / field | Offset | Code referent (VA: bytes) | Second signal |
|---|---|---|---|
| CClientExoAppInternal → module | +0x18 | `CClientExoApp::GetModule` 0x5ed530: `8b4904 e9…` tail-jumps to 0x644760: `8b4118 c3` (`mov eax,[ecx+0x18]; ret`) | Warehouse asm symbol name `CClientExoApp::GetModule` |
| CSWCModule → camera | +0x40 | Client handler 0x64b991..0x64b9b3: `mov eax,[0x7a39fc]; mov ecx,[eax+4]; call 0x5ed530; …; mov esi,[eax+0x40]`, then `call [vtbl+0x60]` on esi | Historical `types.h` `CSWCModule { …; void * camera; }` at +0x40 |
| Camera → active behaviour | +0x18c | 0x45c160 `83c104` (add ecx,4) → 0x43f5a0 `8b8988010000 … ff600c` (`mov ecx,[ecx+0x188]; jmp [vtbl+0xc]`) | The two-hop reading agrees with camera-win-k1.md:17 |
| OnAStick behaviour vtable | 0x75165c | .rdata word at 0x751668 = 0x637a30 (slot +0xc). The constructor 0x639fc0 stores it at 0x639fee: `c706 5c167500`. Two more stores are at 0x63a328 and 0x63ad96. | Warehouse symbol `CSWCameraOnAStick::CSWCameraOnAStick` at 0x639fc0 |
| m_fDist / m_fSpeed / m_fPresetPitch / m_fHeight | +0x110 / +0x114 / +0x11c / +0x120 | Message 0x637a30..0x637ae9: `lea eax,[edi+0x110]` / `[edi+0x114]` / `[edi+0x11c]` / `add edi,0x120`, each paired with a literal. The literals are `m_fDist`@0x7437dc, `m_fSpeed`@0x7437d0, `m_fPresetPitch`@0x7514f8 and `m_fHeight`@0x7437c4. Their lengths 7/8/14/9 equal the parse offsets `param+7/+8/+0xe/+9`. | `SetCameraStyle` 0x638070: `mov [esi+0x110],6.25`, `[+0x114],20.0`, `[+0x11c],80.0`, `[+0x120],3.5`, then 2DA reads into the same fields. types.h `CSWCameraOnAStick` has size 0x138 and unnamed fields there. |
| Dolly mode flag | +0x84 (dword) | `Control` 0x63bcb8: `mov eax,[esi+0x84]; test; je`. Otherwise m_fDist = tan(+0x8c·π/360)·(+0x88) / tan(fov·π/360), stored at 0x63bcfa `fstp [esi+0x110]`. The constant 0x741bb4 = 0.0087266 = π/360. | vtable slot 2 = 0x63bcb0 (`Control`) |
| Pending camera style | global 0x7a242c (dword, −1 = none) | `CheckAndUpdateCameraStyle` 0x638fb3: `mov eax,[0x7a242c]; cmp eax,-1; je`, then `call 0x638070` (SetCameraStyle), then store −1 | Called only from `Control` 0x63bd02 (call-site scan) |
| Orientation quaternion (4 floats) | +0x28..+0x37 | `ResetLastPosition` 0x637c4e: `lea ecx,[esi+0x28]`, then 4 dword stores from the Quaternion argument. `Control_ComputeDesiredPosition` 0x637b06 passes `ecx+0x28` to the rotate helper 0x4a9bb0 together with m_fDist. | types.h `float field_28` |
| Position vector(s) | +0x38 and +0x50 (3 floats each) | `ResetLastPosition` stores the Vector argument into both +0x38 and +0x50, then calls owner `[+0x10]` vtbl+0x5c/+0x60 | — (meaning "current" vs "last" is **unverified**) |
| Client options → camera mode byte | options = `[[client+4]+4]`; mode at +0x6d | `GetClientOptions` 0x5ed700: `8b4104 8b4004 c3`. The byte offset comes from camera-win-k1.md:19. | The handler at 0x64ba85..0x64ba9e uses the same chain |
| Message command grammar | `firstword(param)` + `__stricmp(literal, word)`, then `Parse_float(param+len)` (sscanf `%f`) | 0x463530 is `firstword`. It copies into the **static buffer 0x7fbaf8**, so the call is not thread-safe. 0x70acaf is `__stricmp`; 0x4635c0 is `Parse_float`. | Warehouse symbol names; `camera-win-k1.md:17` (parser 0x4635c0) |

### 1c. Unverified (needs a live receipt or more RE)

- Which behaviour is active in `SetCameraMode(p,2)` (OnAStick, FreeLook, Navigate or another).
- Whether +0x28 is the *current* orientation, and its component order (x,y,z,w vs w,x,y,z).
- Whether +0x38 is the camera's *current* world position.
- The units of m_fPresetPitch (the 80.0 default suggests degrees) and of m_fHeight.
- Whether collision (`Control_HitCheckCamera` 0x63b050) shortens the effective distance while m_fDist stays unchanged.
- The writer of 0x7a242c: area load, SetCameraMode or something else.
- Whether m_fSpeed interpolates toward a new m_fDist (so "settled" must be measured, not assumed).
- The historical `types.h` is provenance-only per the warehouse README. It serves as a second signal, never as the only one.
- `/tmp/kp-camera-win-k1-disassembly.txt` from the earlier audit is **not durable** (it lives in /tmp). Do not cite it as evidence.

---

## 2. Stage 1: read-only `kp.camera.snapshot()`

### 2a. Lua surface (names are not NWScript names; lowercase like `kp.model`)

```lua
local caps = kp.camera.capabilities()  -- {available, profile, abi, limits}
local s = assert(kp.camera.snapshot()) -- nil, reason on failure
-- s.behavior     "on_a_stick" | "other"      (identity from the behaviour vtable)
-- s.mode         camera mode byte (options+0x6d)
-- s.distance     m_fDist        (+0x110)  configured target distance
-- s.speed        m_fSpeed       (+0x114)
-- s.pitch        m_fPresetPitch (+0x11c)  raw; units unverified
-- s.height       m_fHeight      (+0x120)
-- s.dolly        boolean, [+0x84] ~= 0   (distance recomputed every tick)
-- s.style_pending boolean, [0x7a242c] ~= -1
-- s.orientation  {q0,q1,q2,q3} raw floats at +0x28 (order unverified)
-- s.position     {x,y,z} raw floats at +0x38 (meaning unverified)
-- s.position2    {x,y,z} raw floats at +0x50 (unverified; ResetLastPosition writes both)
-- s.camera, s.behavior_ptr  hex strings, diagnostic only
```

- Return a protected full userdata, following the `kp.model.capture` pattern (`WT/src/api/model_lua.cpp:12-35`): magic, allocation length, metatable with `__metatable` locked, and read-only `__index`.
- Capture identity is binding epoch + module + camera + behaviour pointers. Stage 2 needs this for staleness.
- If `behavior == "other"`, return identity, mode and pointers but leave the numeric OnAStick fields nil. That makes a mode-2 surprise diagnosable instead of a bare failure.
- Do **not** expose yaw in degrees in Stage 1. G5 only needs "raw fields unchanged within tolerance".
- The collision diagnostic uses `s.position` against `kp.obj.position(pc)` (`WT/src/api/entity.cpp:211,443`) as a **yaw-sweep invariance** test.
  - Record the horizontal radius and Δz separately.
  - It does not compare against m_fDist directly, because the look-at point is offset from the PC origin by an unrecovered amount (m_fHeight defaults to 3.5, against 6.25 for m_fDist).
  - The look-at target offset is not needed for this test.
- The framing plan's illustrative `kp.camera.set_distance(d)` becomes `set_distance(capture, d)` in Stage 2, so the write is bound to a checked identity. This is the same reason `kp.model.resize` takes a capture.

### 2b. Resolution (pure reads, no engine calls)

`mgr=[0x7a39fc]` → `client=[mgr+4]` → `internal=[client+4]` → `module=[internal+0x18]` → `camera=[module+0x40]` → require `[camera]==0x741b20` → `beh=[camera+0x18c]` → `vt=[beh]`, and `vt==0x75165c` means on_a_stick. Camera mode: `options=[internal+4]` (`GetClientOptions` 0x5ed700 computes `[[client+4]+4]`), then the byte at `options+0x6d`.

- Every hop uses the model's fallible reader (`WT/src/runtime/runtime.cpp:364-369`).
- Null or unreadable at any hop returns `nil, "<hop> unavailable"`. If the camera vtable is not 0x741b20, return an identity-only capture with `camera_vtable` set to the observed hex value, rather than a bare failure, so a surprise does not waste the single L1 launch.
- Every float must be finite, or the snapshot is refused.
- Rebase each VA as `loaded_base + va − 0x400000`, as in `model::Operations::site`.

### 2c. Guards: offset-bearing spans, checked at bind and before every operation

- `model::Operations::guards` (`WT/src/api/model.cpp:13-27`) hard-requires 16-byte / 32-hex guards. **Do not reuse it.** Write a camera guard routine that accepts `{va, length, hex}` spans of any length and compares bytes exactly.
- Candidate spans (sha256 prefixes from §7 R5; the receipt must re-derive the full hex):

| Guard | VA, length | Pins |
|---|---|---|
| internal.GetModule | 0x644760, 4 (`8b4118c3`) | module +0x18 |
| handler module→camera | 0x64b991, 0x6c | g_pAppManager, client +4, module +0x40, camera vtbl +0x60 call |
| Camera::BehaviorMessage | 0x45c160, 8 | camera→Gob +4 |
| Gob::BehaviorMessage | 0x43f5a0, 16 | behaviour +0x188 from the Gob, Message slot +0xc |
| OnAStick::Message (whole) | 0x637a30, 0xb9 | +0x110/+0x114/+0x11c/+0x120 and literal VAs |
| OnAStick::Control head | 0x63bcb0, 0x55 | dolly +0x84, the per-tick +0x110 store |
| CheckAndUpdateCameraStyle | 0x638f60, 0x71 | pending global 0x7a242c |
| ResetLastPosition | 0x637c20, 0x50 | +0x28 quaternion, +0x38/+0x50 |
| OnAStick ctor vtable store | 0x639fee, 6 (`c7065c167500`) | vtable 0x75165c |
| GetClientOptions | 0x5ed700, 7 | options chain |
| CClientOptions::SetCameraMode | 0x61b6f0, 16 (`…88416d…`) | mode byte +0x6d |

- Also check that the `.rdata` bytes at 0x7437dc, 0x7437d0, 0x7514f8 and 0x7437c4 equal the four literals. Also check vtable word 0x751668 == 0x637a30 and camera vtable word 0x741b80 == 0x45c160.
- **Profile gating.** Use a new `camera::Profile` table keyed by exact SHA256 with one entry, `windows-k1-gog`.
  - Any other SHA (K1 Steam, K2 GOG/Steam, Mac) binds nothing.
  - `capabilities()` reports `{available=false, profile="unsupported"}`, and `snapshot()` returns `nil,"unsupported: …"`.
  - Log `camera: <reason>` at bind, as model does at `runtime.cpp:370-371`.
- **Data placement.** `data/addresses/*.json` is *generated* by `tools/gen_address_tables.py` from `data/hooksites.toml` plus `data/adjudication/<alias>_*_bindings.json` (generator `:598`). So:
  - add `kind="field"` rows to `WT/data/hooksites.toml`, next to `appmgr.client` at `:1425-1462`: `client_internal.module`, `client_module.camera`, `camera.active_behavior`, `camera_onastick.dist|speed|preset_pitch|height|dolly|orientation|position`, `g.camera_style_pending`, `client_options.camera_mode`
  - add the evidence to a new overlay `WT/data/adjudication/k1_gog_103_camera_bindings.json`, with two signals per row, as in §1b
  - every new `hooksites.toml` row is `required = false`, so K1 Steam, K2 and Mac tables never gain unresolvable required sites on a later `--all`
  - regenerate **only** K1 GOG. `data/addresses/k2_gog_aspyr.json` currently has another writer's uncommitted changes, so do not run `--all`.
  - the review of the regenerated `k1_gog_103.json` must confirm the diff contains only the new camera rows (plus the binding counts). Corpus drift must not silently change the existing 199 bindings.
  - The C++ profile carries the same constants, following the model precedent. An offline consistency test (§2e) compares them with the regenerated JSON, so the two cannot drift.

### 2d. Files to touch (Stage 1)

New:
- `WT/src/api/camera.hpp`: Profile, Span, Backend (read-only in Stage 1), Capture, Operations
- `WT/src/api/camera.cpp`: checked core (bind, guards, resolve, snapshot)
- `WT/src/api/camera_profiles.cpp`: the single K1 GOG profile
- `WT/src/api/camera_backend.cpp`: native reader adapter (Win32 i386 only; others return nullptr)
- `WT/src/api/camera_lua.cpp`: `kp.camera` table, protected capture userdata, `capabilities`, `snapshot`
- `WT/src/api/camera.cmake`: `kp_cameratest`, `-m32`, labels `offline;camera`, copying `model.cmake:1-13`
- `WT/tools/kp_cameratest.cpp` and `WT/tools/tests/camera_backend_fixture.hpp`
- `WT/tools/camera_profile_consistency_test.py`: C++ profile constants vs `data/addresses/k1_gog_103.json` camera rows vs IMG bytes. The IMG part is skipped with a clear message if the warehouse is absent.
- `WT/data/adjudication/k1_gog_103_camera_bindings.json`
- `WT/docs/camera-api.md`: contract doc in the style of `WT/docs/model-memory-api.md`

Edited:
- `WT/src/runtime/runtime.cpp`:
  - `bind_native` after model, around `:370-375`
  - `api::camera::register_all(L)` next to model at `:698`
  - `unbind()` next to `:785` and `:848`
- `WT/src/runtime/runtime.cmake:61-64`: add the camera sources
- `WT/CMakeLists.txt:136`: include `camera.cmake`. This file currently has another writer's uncommitted edit, so coordinate.
- `WT/data/hooksites.toml` (field rows), then regenerate `WT/data/addresses/k1_gog_103.json`
- `WT/docs/research/camera-win-k1.md`: append the §1b receipt with replay commands (gate E1)
- `WT/docs/lua-api.md`: add a "Native camera (`kp.camera`)" section. `kp.model` is also missing from this file; note that as a separate gap.
- `WT/docs/user/api-status.md`: a row in "Script metadata and native facilities" (`:30-45`): `kp.camera.capabilities`, `snapshot` = Bound (K1 GOG only), then Live after proof L1
- `WT/data/hostapi.toml`: optional catalog row (it has no `kp.model` row today)
- `WT/tools/kp_namespacetest.cpp:100-104`: only if the isolated install includes native modules. The existing loop at `:121-131` already proves no NWScript routine name appears under `kp`.
- Not touched: `scripts/harness/kpharness/*.py` (another writer). Route and generator changes stay in FP §3b as text.

### 2e. Tests (Stage 1, offline)

`kp_cameratest` uses a Fake backend, as in `WT/tools/tests/model_backend_fixture.hpp`. The fake maps the guard spans, the literal bytes and a synthetic object graph.

- **Bind refusal:** wrong SHA; wrong ABI or width; base 0; **each guard span with any single byte flipped** (loop over every byte of every span); a literal byte flipped; the vtable word changed.
- **Chain:** null or unreadable at each of the 7 hops gives `nil`+reason naming the hop. A camera vtable other than 0x741b20 is refused.
- **Behaviour:** vtable ≠ 0x75165c gives `behavior=="other"` with numeric fields nil. A camera vtable ≠ 0x741b20 gives an identity-only capture carrying the observed vtable value.
- **Values:** NaN or Inf in any float is refused. Dolly and pending flags are decoded (0 / nonzero; −1 / other).
- **Purity:** the Fake counts calls, and snapshot makes **zero** engine calls.
- **Staleness:** unbind, rebind, then an old capture's epoch differs. Changing the module, camera or behaviour pointer changes identity.
- **Lua:** forged userdata (wrong length, wrong magic, table) raises argument errors. `kp.camera` contains no PascalCase key. `capabilities()` on an unbound profile gives `available=false`.
- **Consistency test:** C++ constants == JSON rows == IMG bytes.
- **Regression suites:** `ctest -L offline`, `tools/nwscript_boundary_test.py` and `kp_namespacetest`.

### 2f. Evidence before coding (Stage 1)

| Gate | Needed | Exists? |
|---|---|---|
| E1 | Durable receipt with IMG SHA, the exact replay commands (§7), the byte spans and each derived offset with two signals | **No.** Only this session and this plan. Must be appended to `camera-win-k1.md` or the adjudication overlay. |
| E2 | Independent re-derivation of E1 by a reviewer who did not produce it, ideally an AgentDecompile/Ghidra xref pass on 0x644760, 0x64b9b0, 0x43f5a0, 0x637a30 and 0x75165c | **No** |
| E3 | Confirmation that the Lua script thread may read client-side camera memory. Pure reads carry low risk; the model API already calls client functions from this thread (`WT/docs/model-memory-api.md` "Calls belong on the existing engine script thread"). | Precedent exists; nothing camera-specific |

### 2g. Review gates (Stage 1)

- **R0 evidence:** E1 and E2 pass. The reviewer re-runs §7 and gets identical bytes.
- **R1 code:**
  - Guards are exact.
  - No engine call is reachable from snapshot.
  - Unsupported profiles fail closed at bind *and* per call.
  - Userdata is protected.
  - No NWScript name is added.
  - Docs state the Stage 1 limits (§1c).
- **R2 live-proof review:** a reviewer who did not run L1 adjudicates the receipts.

### 2h. Minimal live proof L1 (one serialized launch, under the canonical lock)

Setup: K1 GOG, the same save and module `danm14aa`, PC at (105.7, 96.5, 1.0). There is no F12 console and no acceptance media; this is a diagnostic.

1. Receipt: `capabilities().available == true`, `profile == "windows-k1-gog"`. The runtime log contains no `camera:` refusal.
2. `SetCameraMode(p,2)` via `nwscript.call`, then advance 600 ticks. Snapshot twice, 180 ticks apart, with `screenshot=true` beside each.
   - Record `behavior`. **This settles the open gate in camera-win-k1.md:17.**
   - Record `dolly` and `style_pending`.
3. Correlation: the pixel displacement of a fixed background feature between the two shots, against the change in `orientation` and `position`.
   - Admit only if steady shots (≤ 4 px) give raw fields equal within 1e-4.
   - Admit only if a panning pair (> 4 px, as RUN showed) gives a nonzero change.
   - If the view never pans during L1, that half stays unproven.
4. Yaw-sweep collision test. RUN panned about 10 px/s, so L1 will probably sweep yaw on its own; if it does not, use the CAL step-22 composition when it reproduces.
   - Sample `snapshot()` at ≥ 8 points across the drift, with m_fDist, pitch and height unchanged throughout.
   - Record the horizontal radius r = |(pos − pc_pos).xy| and Δz = pos.z − pc_pos.z at each point.
   - An invariant r (within 2%) and invariant Δz mean no collision along the sweep. In that case, framing differences between views come from yaw alone, and a larger m_fDist should dolly (Stage 2 justified, subject to E8).
   - An r dip that tracks the framing change (the 35% view has smaller r than the 28.6% view) means collision limits the RUN view. Stage 2 must then first choose an open view, or it may be inert.
   - Also record whether `position` and `position2` diverge. That cheaply tests which vector is "current".
5. Cleanup: nothing to restore; Stage 1 does not write.

Admission rule: steps 1–4 have receipts in `report.json` plus the PPMs, and R2 signs off. Afterwards `api-status.md` may say Live for `kp.camera.snapshot` on K1 GOG only.

---

## 3. Stage 2: checked `kp.camera.set_distance(capture, d)` and `kp.camera.restore(capture)`

### 3a. Write mechanism

- Resolve as in Stage 1. Require all of the following:
  - `behavior == on_a_stick`
  - `dolly == false`, because the per-tick recompute at 0x63bcfa would override the write
  - `style_pending == false`, because SetCameraStyle would overwrite all four fields on the next `Control`
  - `mode == capture.mode`
  - capture identity is unchanged: epoch, module, camera, behaviour, i.e. the `model::Operations::same` pattern (`WT/src/api/model.cpp:113-115`)
- Build the command string `"m_fDist " + C-locale float` into a local buffer.
  - Use `%.9g`, which round-trips every IEEE single, after asserting `localeconv()->decimal_point == "."`. Refuse the call otherwise.
  - The engine's `%f` sscanf accepts exponent form.
- Call the **engine's** handler through the verified vtable slot: `[beh]+0xc`, which the guard proves is 0x637a30. Use thiscall with `char*` (Win32 adapter, like `KP_MODEL_CALL` in `WT/src/api/model_backend.cpp:6-8`).
  - This is the same parse path the engine uses. It is not a raw field poke.
  - A raw store to +0x110 would have the same effect. Choosing the engine route matches the model precedent: "does not … write raw scale fields" (`WT/docs/model-memory-api.md:3-5`).
  - Message returns void, so **readback is the only success signal**.
- `firstword` writes to the static buffer 0x7fbaf8. So only call on the engine script thread (as model), never from a timer thread or a worker.

### 3b. Bounds

- `d` must be finite and within **[0.5, 2.0] × capture.distance**, and inside an absolute **[1.0, 30.0]**. These are policy values for the reviewer to fix; they are not engine facts. The framing need is a 1.11–1.48 ratio (FP §2c).
- The absolute cap should be revisited once the K1 `camerastyle.2da` distance column has been decoded. That decode is `unverified`.

### 3c. Verification, settle, restore

- **Immediate readback.** Re-snapshot:
  - `distance == d` within 1e-4 relative
  - speed, pitch and height bit-identical to before
  - identity unchanged
- **Log line**, as model does (`WT/src/api/model.cpp:125-136`): `[camera] camera=… beh=… dist_before=… requested=… readback=… verified=…`. A failure returns `nil, "…mutation may have occurred"`.
- **Settle.** It is not implemented natively. The route polls `snapshot()` every N ticks until `position` and `orientation` change by less than epsilon over 180 ticks.
  - m_fSpeed suggests interpolation, so a readback of m_fDist alone does not prove the view has settled.
- **`restore(capture)`** sends `m_fDist <capture.distance>` (formatted `%.9g`) under the same refusals and requires a **bit-exact** readback of the captured float.
  - If identity changed (module or area load), refuse; do not write. SetCameraStyle will have re-seeded the camera anyway.
  - Stage 2 writes only m_fDist. Restore verifies that all four fields equal the original capture and reports any difference.

### 3d. Files (Stage 2)

- `camera.hpp` / `camera.cpp`: `set_distance` and `restore`, with refusal order and logging
- `camera_backend.cpp`: Win32 thiscall `message(beh, const char*)`
- `camera_lua.cpp`: the two functions and their argument checks
- `kp_cameratest.cpp`:
  - a Fake Message that reproduces the engine grammar (first word up to space/tab/CR/LF, case-insensitive compare, strtof at `param+len`) and writes the four fields
- Docs: `camera-api.md`, `lua-api.md`, `api-status.md` (Bound, then Live after L2)

### 3e. Tests (Stage 2, offline)

- **Refusals:** each of these makes zero Message calls: bounds (≤0, NaN, Inf, ratio out of range, absolute out of range); `dolly=1`; `style_pending`; `behavior=other`; stale epoch, module, camera or behaviour; a guard byte flipped between bind and call.
- **Command bytes:** the exact string is `m_fDist 8` for 8.0f and `m_fDist 6.25` for 6.25f. A table of awkward floats inside the [1,30] bounds (for example 7.1f, 8.000001f, 29.999998f, and the neighbours of 6.25f) must round-trip bit-exactly through `%.9g` → `strtof`. Under `LC_NUMERIC=de_DE.UTF-8`, if installed, the call must refuse rather than emit a comma.
- **Readback:** if the Fake ignores the command, `set_distance` fails with "mutation may have occurred". If the Fake also changes speed, the call fails.
- **Round trip:** `set_distance` then `restore` gives the bit-identical original value, and a verified log line.
- **Parser parity:** `m_fdist 5` (case) is accepted, as the engine would. Trailing garbage is ignored, as `%f` does.

### 3f. Evidence before coding (Stage 2)

| Gate | Needed | Exists? |
|---|---|---|
| E4 | L1 passed, with `behavior=="on_a_stick"` in mode 2 | No |
| E5 | The L1 yaw-sweep shows an invariant radius (no collision) at the chosen view, or a view is chosen where that holds. Otherwise `set_distance` may be inert. | No |
| E6 | The writer of 0x7a242c is identified (Ghidra xref / AgentDecompile receipt). It must not be set by SetCameraMode or on a timer that would revert the write mid-scene. An absolute-reference scan of `.text` found only 0x638fb4 and 0x638fc7, both inside the check. | **Open** |
| E7 | Who sets +0x84 (dolly) and when. It must be proven false in gameplay chase mode. Checking it at call time plus in every phase gate covers the runtime side. | Partial: the runtime check is designed; the writer is unknown |
| E8 | `Control_ComputeNewCameraPosition` (0x6398f0) uses m_fDist and m_fHeight (field scan: Dist at +0x26b/+0x27b, Height at +0x30f). A reviewer confirms that a larger m_fDist dollies along the view ray at fixed pitch, as FP §2c assumes. | No |
| E9 | Enumerate **every** writer of OnAStick +0x110/+0x11c/+0x120 across the whole binary (a typed-struct xref pass in Ghidra/AgentDecompile). The R6 scan covered only `swbehaviorcamera.cpp.S`, and SetCameraStyle already lies outside it. The in-phase readback gates in L2 and the route stay the runtime backstop. | No |

### 3g. Review gates and live proof L2

- **R3 code:** refusal order is before any call; the thread constraint is documented; the format is locale-proof; restore refuses stale captures.
- **L2** is one serialized diagnostic launch under the lock, after L1, with the same save and setup:
  1. Snapshot `c0`. Call `set_distance(c0, c0.distance*K)` with K frozen before launch (about 1.28 from FP §2c; 27.5% row).
  2. Readback passes.
  3. Poll until settled. Take two shots 180 ticks apart.
  4. Pass criteria:
     - G1 player height is 192–211 px
     - G5 background displacement is ≤ 4 px
     - raw fields are unchanged between the two settled snapshots
  5. Call `restore(c0)`, check the readback, and take a shot. Restored framing matches baseline within ±6 px (G2).
  6. Negative case: attempt `set_distance` with a stale capture after the restore (identity forged by rebinding is offline-only). Only the ratio-bound refusal is exercised live.
- **R4:** an independent review of the L2 receipts. Only then may the acceptance route (FP §3b Track N) use `kp.camera`.

---

## 4. Could Stage 1 alone plus existing camera behaviour satisfy the framing gate?

Estimate, using FP §2 numbers only:

- At the only other measured view (CAL shot 0007, same PC position, chase mode 2), normal height was 220 px (28.6%).
  - G1's range of 192–230 px accepts it.
  - The stricter ≤ 211 px rule for a 2.0 giant rejects it by 9 px.
- Headroom at 220 px for a 2.0 giant, per FP §2c "largest share with top@2.0 ≥ 60 px":
  - 670/0/−5 → 249 px OK
  - worst fit → 217 px FAIL by 3 px
  - 670/+5/0 → 226 px OK
  - 670/+5/+5 → 237 px OK
  - 4-point → 229 px OK
  - That is 4 of 5 fits. Those fits assume dolly geometry and were calibrated on the RUN view, so they are only indicative for another view.
- Blockers for a Stage-1-only route:
  1. No proven way to reach that view. `SetCameraFacing` is now expected to be inert under OnAStick (§0.3). PC `SetFacing` via `with_caller` is `unverified`. The cause of the CAL step-19 → step-22 change is unknown.
  2. That view also drifted: 935 → 952 px between CAL 0008 and 0009. With Stage 1 the drift becomes *detectable in-route* (G5), but it cannot be prevented.
  3. It needs one of two changes: G1 relaxed to about 217–220 px (with the worst fit's 60 px headroom rule accepted as marginal), or the giant scale reduced to about 1.95.
- **Verdict:** possible but unlikely without a policy change (qualitative; `unverified`, no probability referent).
  - Stage 1 is still the right first build. It is required for in-route G5 either way, and its L1 configured-vs-effective diagnostic decides whether Stage 2 can help at all.
  - If L1 shows the RUN view is collision-limited, choosing an open view matters more than any distance write.

---

## 5. Sequencing

1. E1 receipt, then E2 independent re-derivation, then R0.
2. Stage 1 code and offline tests, then R1.
3. L1 (under the lock, serialized, after the capture diagnostic that FP says must pass first), then R2.
4. Decision: Stage 2 only if E4 and E5 hold. Resolve E6–E8.
5. Stage 2 code and tests, then R3, L2, R4.
6. Then the Track N route edits (FP §3b), done by the harness owner, not here.

---

## 6. Claim blocks

```
claim: OnAStick::Message maps m_fDist/m_fSpeed/m_fPresetPitch/m_fHeight to +0x110/+0x114/+0x11c/+0x120.
referent: IMG bytes 0x637a30..0x637ae9 (lea [edi+0x110], [edi+0x114], [edi+0x11c], add edi,0x120) + literals at 0x7437dc/0x7437d0/0x7514f8/0x7437c4 whose lengths equal the parse offsets; SetCameraStyle 0x638070 writes the same four offsets with 6.25/20/80/3.5
checked: §7 R1, R4
verdict: holds (session-derived; needs E1/E2)
confidence: high; a different active-behaviour class in mode 2 would make it irrelevant, not wrong
```
```
claim: the active camera is [[[[[0x7a39fc]+4]+4]+0x18]+0x40], and its active behaviour is [camera+0x18c].
referent: 0x5ed530 -> 0x644760 "mov eax,[ecx+0x18]"; handler 0x64b9b0 "mov esi,[eax+0x40]" then call [vtbl+0x60]; 0x45c160 add ecx,4 -> 0x43f5a0 mov ecx,[ecx+0x188]; types.h CSWCModule.camera at +0x40
checked: §7 R2, R3
verdict: holds (session-derived)
confidence: medium-high; a live L1 read returning camera vtable 0x741b20 would make it high
```
```
claim: known revert mechanisms for a distance write are Control (dolly flag +0x84) and a pending style (0x7a242c); other writers may exist (E9).
referent: 0x63bcb8..0x63bcfa; 0x638fb3..0x638fc5 calling SetCameraStyle 0x638070
checked: §7 R2
verdict: holds for these two; completeness unresolved (the scan covered one source file only)
confidence: medium; a whole-binary xref of +0x110 writers and of 0x7a242c/+0x84 setters would settle it
```
```
claim: SetCameraFacing's yaw is ignored under OnAStick.
referent: client handler sends "yaw %f" (0x74fc28) via vtbl+0x60; OnAStick Message matches only four m_f* literals and returns without calling the parent
checked: §7 R1, R4; camera-win-k1.md:17
verdict: holds statically; live unverified (active behaviour not yet read)
confidence: medium; L1 behavior=="on_a_stick" would raise it to high
```
```
claim: Stage 1 alone likely cannot meet G1 <= 211 px at any proven view.
referent: FP §2a CAL 0007 = 220 px; FP §2c headroom limits 217-249 px
checked: arithmetic from FP numbers
verdict: holds as an estimate
confidence: low-medium; an L1 view measuring <= 211 px would overturn it
```

---

## 7. Replay commands (read-only; for the E1 receipt)

`.text`, `.rdata` and `.data` in IMG have file offset == RVA (section table read in session), so `--adjust-vma=0x400000` maps VAs directly for those sections.

```sh
IMG=~/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image
OD=/run/host/usr/bin/i686-w64-mingw32-objdump   # /run/host/usr/bin/objdump lacks libopcodes here
dis(){ $OD -D -b binary -m i386 -M intel --adjust-vma=0x400000 --start-address=$1 --stop-address=$2 "$IMG" | sed -n '8,$p'; }
sha256sum "$IMG"                          # R0: 9c10e045...91435
dis 0x637a30 0x637ae9                     # R1: Message, four lea/add + literal pushes
dis 0x63bcb0 0x63bd05; dis 0x638f60 0x638fd1   # R2: dolly recompute; pending style
dis 0x45c160 0x45c168; dis 0x43f5a0 0x43f5b0; dis 0x644760 0x644764; dis 0x64b991 0x64b9fd  # R3: chain
python3 -c "d=open('$IMG','rb').read();[print(hex(a),d[a-0x400000:a-0x400000+16].split(b'\0')[0]) for a in (0x7437dc,0x7437d0,0x7514f8,0x7437c4,0x74fc28,0x74fc3c,0x74fc30)]"  # R4: literals
dis 0x638070 0x6380f3; dis 0x637c20 0x637c70; dis 0x637af0 0x637b22; dis 0x61b6f0 0x61b705   # R5: style defaults, quat/pos, mode byte
python3 -c "import struct;d=open('$IMG','rb').read();print(hex(struct.unpack_from('<I',d,0x751668-0x400000)[0]),hex(struct.unpack_from('<I',d,0x741b80-0x400000)[0]))"  # vtable slots: 0x637a30, 0x45c160
# R6: field-access scan of swbehaviorcamera functions; source:
#   ~/biodecompwarehouse/.../source/asm/game/clientcore/swbehaviorcamera.cpp.S (byte-exact per its header)
# R7: absolute-reference scan of .text for 0x7a242c -> only 0x638fb4, 0x638fc7
```

Symbol names (GetModule, firstword, __stricmp, Parse_float, SetCameraStyle, CSWCameraOnAStick ctor) come from the comment headers in `…/source/asm/**/*.S`. The CSWCModule and CSWCameraOnAStick layouts come from `…/historical/readable/include/types.h` (provenance-only, used as a second signal).

## 8. Open items

- The E6 and E7 writers; E8 dolly geometry; units of pitch and height; quaternion order; meaning of +0x38.
- `camerastyle.2da` distance limits and area binding (FP §4). This affects only the absolute bound.
- Whether K1 Steam (`k1_steam_103*`) shares these bytes. Out of scope; it fails closed until it has its own receipt.
- `docs/lua-api.md` has no `kp.model` section either. That is a documentation gap outside this plan.

### Critical files for implementation

- `WT/src/api/model.cpp`, `WT/src/api/model_lua.cpp`, `WT/src/api/model_profiles.cpp` (the pattern to copy)
- `WT/src/runtime/runtime.cpp` (bind at `:364-375`, register at `:698`, unbind at `:785`/`:848`)
- `WT/docs/research/camera-win-k1.md` (receipt destination)
- `WT/data/hooksites.toml` + `WT/data/adjudication/k1_gog_103_harness_bindings.json` (field-row format and the adjudication accept rule)
- `WT/tools/kp_modeltest.cpp` + `WT/tools/tests/model_backend_fixture.hpp` (test harness pattern)

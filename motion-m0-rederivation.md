# M0 receipt: K1 GOG placeable movement, re-derived read-only

Date: 2026-09-27. Stage M0 of `fanout-lua-lifecycle-plan.md` (Track M).
Nothing in the repo was edited. No Wine, game, Gamescope or FFmpeg was run, and the live-game lock was not touched.
Scratch lives in `/home/brunner56/kp-live-20260922/motion-m0-scratch/`:
- `pe.py` is a section-table reader that uses only the standard library.
- `asm.py` searches the existing capstone listing `camera-rederive-scratch/text.asm`.
- `f542830.txt`, `f52cdc0.txt` and `f52f820.txt` are saved function listings.

The camera venv's python spent more than 13 minutes stuck in the `D` state because I/O pressure was about 87%. So every read below uses the pre-built capstone listing plus direct byte reads with `pe.py`.

## Image identity

claim: The image analysed is the reference image for `k1_gog_103.json`.
referent: `sha256sum .../K1__k1_win_gog_swkotor.exe/artifacts/raw_image` gives `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`. This equals `reference_sha256` and `derived_sha256` at `k1_gog_103.json:4041-4042` in the lua-boundary-validation worktree (the brief said about :3730; the file has grown).
checked: command run here.
verdict: holds. confidence: high.

claim: The 16 bytes at VA 0x004CD1A0 equal the expected bytes in the row.
referent: `pe.py rd(0x4cd1a0,16)` gives `538b5c240856578bf18dbe9000000053`. That matches `k1_gog_103.json:540` (`server_object.set_position`, `addr_hex` at :539).
checked: command run here.
verdict: holds. confidence: high.

The image sections are `.text` 0x401000 (raw 0x1000), `.rdata` 0x73D000, `.data` 0x78D000 and `.rsrc` 0x836000. Addresses below are VAs with image base 0x400000.

Translation-unit names such as `nwsplaceable.cpp` come from kotorxid's `source/asm/**` file placement. They are naming hints only. No claim rests on them.

---

## (1) Engine position setter 0x004CD1A0 (`CSWSObject::SetPosition`)

claim: The function is `__thiscall` with `this` in ECX and exactly 4 stack arguments. The callee cleans the stack: `ret 0x10`. The signature is `void SetPosition(this, const Vector* pos, int a2, int a3, int a4)`.
referent: `004cd1a7 mov esi, ecx` uses ECX as `this`. `004cd23c ret 0x10` pops 16 bytes. `hook_bodies.cpp:205` declares `SetPositionFn = void(KP_THISCALL*)(void*, Vector3*, int, int, int)`, which agrees.
checked: `asm.py fn 4cd1a0`.
verdict: holds. confidence: high.

claim: The position vector is `this+0x90/+0x94/+0x98`, stored as 3 floats.
referent: `004cd1a9 lea edi,[esi+0x90]`, then `004cd202..0f` copies `pos[0..2]` to `[edi]`, `[edi+4]` and `[edi+8]`. Base ctor `0x4CFCB0` zeroes `+0x90/+0x94/+0x98` at `004cfd13..1e`. Placeable save `0x586A70` writes `X`, `Y` and `Z` from `+0x90`, `+0x94` and `+0x98`. It reads them at `005870dc`, `005870f0` and `00587104`, and the strings are at 0x7476e8, 0x74699c and 0x747a88.
checked: `asm.py fn 4cd1a0`, `asm.py show 5870d6`, string reads with `pe.py`.
verdict: holds. confidence: high.

claim: If the new position equals the current one, the function returns early. It then writes nothing and sets no flag.
referent: `004cd1af push ebx(pos); push edi(this+0x90); call 0x4aa980`. `0x4AA980` compares 3 floats with `fcomp`/`jp`, returns `eax=1` if all are equal and `xor eax,eax` otherwise (`004aa9ad`/`004aa9b3`). Then `004cd1bb jne 0x4cd239` jumps to the epilogue.
checked: `asm.py fn 4aa980`, `asm.py show 4aa9b3`.
verdict: holds. confidence: high.

claim: `a4 == 0` sets dirty bit 1 (`|= 2`) in the bitset at `this+0x1FC`. That bit is what makes the client copy move. `a4 != 0` changes the server position silently.
referent: `004cd1bd mov eax,[esp+0x1c]` reads `a4`, because there are 3 pushes plus the return address before `a1` at `+0x10`. Then `jne` skips `004cd1c8 or dword ptr [esi+0x1fc], 2`. Section (2) shows the consumer.
checked: stack arithmetic over `asm.py fn 4cd1a0`.
verdict: holds. confidence: high.

claim: `a2 != 0` re-sorts the object inside its current area's object list via `0x506FE0`. `a3` is not read by this build.
referent: After `004cd1c1 push ebp`, `a1..a4` sit at `[esp+0x14..0x20]`. `004cd212 mov eax,[esp+0x18]` reads `a2` and gates `0x4cd21a..33`. No instruction reads `[esp+0x1c]` after the push. Before the push, `[esp+0x1c]` is `a4`.

`0x506FE0` is `__thiscall` on the area with `ret 4`. It searches `area+0x190/+0x194`, an id array with its count, for `obj+4`. It then swaps neighbours while it compares `obj+0x90`, the X coordinate (`00507069..0050706f`, `005070b5..005070ce`). I read the forward-swap pass. I did not read the reverse-direction branch at `0x507195`.
checked: `asm.py fn 4cd1a0 506fe0`.
verdict: holds for the `a2`/`a3` roles. The claim that 0x506FE0 is an X-sorted spatial index holds with medium confidence. Reading 0x507195 would settle the reverse pass.

claim: The area comes from `this+0x8C`, which holds the area object id. The id is resolved through the server object array and `vtbl+0x28` (the AsSWSArea conversion). The area index is only touched when that lookup succeeds.
referent: `004cd1cf..0x4cd200`: `[0x7A39FC]+8` → `0x4AED70`, which returns `internal+0x1005C`, the object array. Then `0x4D8230(id=[esi+0x8c], &out)`. On a hit, `0x4D8230` stores `node+4` and returns `al=0` (`004d827b..84`). `call [vtbl+0x28]` follows, and ebp=area is used at `004cd233`. The standalone `GetArea` at `0x4CB120` does the same thing.
checked: `asm.py fn 4cd1a0 4aed70 4d8230 4cb120`.
verdict: holds. confidence: high.

claim: SetPosition accepts both creatures and placeables. It never checks the type byte. Its only type-dependent step is `vtbl+0x30`, which is a no-op for placeables.
referent: The body has no read of `[esi+8]`. `0x4cd21e call [vtbl+0x30]` runs twice and its result is discarded. For the placeable vtable 0x7494D0, slot 0x30 is 0x63E7F0 (`xor eax,eax; ret`).

The engine itself calls SetPosition on placeables. `CreateObject` (routine 243 → `0x52F820`) calls it at `0052fb95` right after the placeable ctor `0x5877E0`. `CSWSPlaceable::AddToArea` (`0x587170`) calls it at `005871b8`, and `RemoveFromArea` (`0x584950`) calls it at `005849c5`.
checked: `pe.py` vtable dump; `asm.py show 52fbb0 30 40`; `asm.py fn 587170 584950`.
verdict: holds. confidence: high.

claim: SetPosition updates only raw coordinates, the per-area X-order (when `a2` is set) and the client dirty bit (when `a4` is 0). It does not touch area membership, the walkmesh or collision, trigger enter/exit, or the render model directly.
referent: The full callee set of `0x4CD1A0` is `0x4AA980`, `0x4AED70`, `0x4D8230`, `vtbl+0x28`, `vtbl+0x30` and `0x506FE0`. There is nothing else between `004cd1a0` and `004cd23c`. Section (3) shows the placeable collision state that it does not touch.
checked: `asm.py fn 4cd1a0`.
verdict: holds. confidence: high.

claim: `hook_bodies.cpp:307` and `:354` call `(obj, &pos, 1, 1, 0)`. That means re-sort, `a3` ignored, and client dirty set.
referent: The argument roles are derived above. The call text is at `hook_bodies.cpp:307` and `:354`.
checked: `sed -n 285,356p src/runtime/hook_bodies.cpp`.
verdict: holds. confidence: high.

---

## (2) Placeable fields, orientation, and the server-to-client sync

claim: The placeable type byte (`CGameObject+0x8`) is 9, loaded from the constant at 0x746638. The object id is at `+0x4`.
referent: The placeable ctor `0x5877E0` runs `00587803 mov cl, byte ptr [0x746638]` and then `call 0x4cfcb0(type, id, 0)`. The CSWSObject ctor calls `0x4D7D60`, which writes `[this+4]=id` and `[this+8]=type` (`004d7d70`, `004d7d73`). The byte at 0x746638 is `09`, read with `pe.py`.
checked: `asm.py show` around 0x5877E0 and 0x4D7D60; `pe.py rd(0x746638,1)`.
verdict: holds. confidence: high.

claim: The CSWSPlaceable vtable is 0x7494D0. Conversion slot `+0x48` returns `this`, which makes it AsSWSPlaceable. Slot `+0x10` is the common AsSWSObject. Slot `+0x78` is the placeable EventHandler 0x587BA0, which matches the existing row `event.placeable`.
referent: The ctor stores the vtable (`00587824 mov [esi], 0x7494d0`), and so does the dtor (`005854ce`). In the dump, slots `0x10` and `0x48` are 0x641DB0 (`mov eax,ecx; ret`), and every other conversion slot from 0x0C to 0x5C is 0x63E7F0 (returns 0). The CSWSObject vtable 0x745F18 has only `0x10` returning `this`. Slot 0x78 is 0x587BA0.
checked: `pe.py` vtable dump; `asm.py show 5854b0`.
verdict: holds. confidence: high.

claim: The typed server getter is the `CServerExoApp` wrapper 0x4AE7A0, which calls the internal function 0x4B18D0. It resolves an id through `internal+0x1005C`, requires type byte == `[0x746638]` (9), and returns `vtbl+0x48`. Otherwise it returns 0. It is `thiscall` with 1 argument, `ret 4`.
referent: `004ae7a0 mov ecx,[ecx+4]; jmp 0x4b18d0`, followed by `004b18fe..0b` (`cmp al,[0x746638]; jne` → `call [edx+0x48]`) and `004b1912 xor eax,eax`.
checked: `asm.py show 4b18d0`.
verdict: holds. confidence: high.

claim: The client-side typed getter 0x5ED5F0 (`CClientExoApp`) calls 0x5F12C0. That function uses the client object array at `internal+0x14`, requires type 9, and returns `vtbl+0x4C`.
referent: `005ed5f0 mov ecx,[ecx+4]; jmp 0x5f12c0`, then `005f12c5 mov ecx,[ecx+0x14]`, then `005f12ee cmp al,[0x746638]` and `005f12f8 call [edx+0x4c]`.
checked: `asm.py fn 5ed5f0 5f12c0`.
verdict: holds. confidence: high.

The brief says "client wrapper 0x5ED5F0 +0x24", and I could not tie that `+0x24` to anything in these two functions. unresolved. A second question would need the original audit's meaning of `+0x24`.

claim: The orientation is a 3-float direction vector at `this+0x9C/+0xA0/+0xA4`. `SetOrientation` at 0x4CD170 is `__thiscall(this, const Vector*)` with `ret 4`. It copies the vector and sets dirty bit 2 (`|= 4`). It has no equality early-return and no area or walkmesh side effects.
referent: `004cd170..93` in full: `lea eax,[ecx+0x9c]`, 3 dword copies, `or dword ptr [ecx+0x1fc], 4`, `ret 4`. The ctor zeroes 0x9C..0xA4 (`004cfd27..33`). NWScript `SetFacing` builds `(cos θ, sin θ, 0)` from degrees × 0.0174533 (`005428ab..d5`; the constant at 0x7415F8 reads as 0.017453292) and passes it here.
checked: `asm.py show 4cd170`, `pe.py f32(0x7415f8)`.
verdict: holds. confidence: high.

claim: Placeables also keep a quaternion at `+0x428..+0x434`. `CSWSPlaceable::SetOrientation(quat*)` at 0x5853C0 (`ret 4`) stores it, derives the facing vector from it, and calls 0x4CD170. The ctor default is `[+0x428]=1.0` and the rest are 0.
referent: `005853cf..e6` copies 16 bytes to `+0x428`, then there is float math, `0x4AB180` (normalize), and `00585451 call 0x4cd170`. The ctor has `005878a8..ba`. The callers are CreateObject `0052fc00`, the area GIT loader `0050a99c` (after reading `Bearing`) and `0x4CE220` `004ce602`.
checked: `asm.py fn 5853c0`, `asm.py callers 5853c0`.
verdict: holds. Component order `(w,x,y,z)` versus `(x,y,z,w)`: unverified. confidence: medium, because the 1.0 at +0x428 suggests w comes first. A live readback of a rotated GIT placeable would settle it.

claim: `+0x1FC` is a bitset with set, test and clear helpers at 0x4CC1F0, 0x4CC220 and 0x4CC250. Bit 0 is animation, bit 1 position, bit 2 orientation. The bits are consumed once per server tick by `CServerAIMaster` 0x4B0B70, which `CServerExoAppInternal::MainLoop` 0x4BABB0 calls at `004bac73` (existing row `app.server_main_loop`). For each object in the 5 AI priority lists at `aimaster+0x04..+0x48`, the consumer does the following:
- It requires type > `[0x746633]` (=4) and `[obj+0x1F8] != 0`.
- It gets the client counterpart via 0x4CC2B0 (cached `+0x224` or a client lookup).
- It requires `client->vtbl+0xC` to be non-null.
- Bit 1 calls `render->vtbl+0x12C(&obj+0x90, [obj+0xD4], [obj+0xB8])` and clears the bit.
- Bit 2 calls `render->vtbl+0x130(&obj+0x9C)` and clears the bit.

referent: `004cc1f0..77` holds the shift/or/and helpers. The consumer code is `004b10c6..004b1166`: `push 1; call 0x4cc220`, then `lea ecx,[esi+0x90]` and `call [edx+0x12c]`, then `push 1; call 0x4cc250`. The same pattern with `push 2` uses `lea ecx,[esi+0x9c]` and `call [edx+0x130]`. The gates are at `004b1089..c0`. `pe.py` reads `[0x746633] = 04`.
checked: `asm.py show`/`fn` on those ranges, and `asm.py callers 4b0b70` (1 caller, in 0x4BABB0).
verdict: holds. confidence: high for the mechanism. The exact client classes behind `vtbl+0xC`, `vtbl+0x12C` and `vtbl+0x130` are unverified; they are identified by call shape only.

claim: Placeables are in the AI master lists, so the consumer sees their dirty bits.
referent: The placeable ctor calls `005878c4..da`, which is `0x4AED80` (returns `internal+0x10044`, the AI master), then `0x4B0850(this, 0)`. `0x4B0850` appends `obj+4` to the list at `master+4+prio*0x10` for priority 0..4 and records `[obj+0x78]=prio`.
checked: `asm.py fn 4aed80 4b0850`, and the ctor listing.
verdict: holds. confidence: high.

claim: `+0x1F8` is the per-object gate for syncing to the client. It is written by the player-message builder 0x578060 from the result of 0x56DC60, and the ctor zeroes it.
referent: `005780a6 mov [esi+0x1f8], eax` follows `call 0x56dc60`. The ctor has `004d00de`.
checked: `asm.py fn 578060`, `asm.py show 4d00de`.
verdict: the writer holds. What 0x56DC60 tests (for example "visible to player" or "in player's area"): unverified. confidence: medium.

Consequence: no separate "sync to client" call is needed. `SetPosition(..., a4=0)` or `SetOrientation` sets the bit, and the next server tick pushes the change to the client object. This depends on `[obj+0x1F8] != 0` and on MainLoop reaching `004bac73`, which requires `[[0x7A39FC]+0x14]->[0]==0 && [internal+0x10008]==2` (`004bac56..6b`).

---

## (3) Engine paths that move a placeable

claim: NWScript `JumpToLocation` (313), `ActionJumpToLocation` (214), `JumpToObject` (385) and `ActionJumpToObject` (196) do not move placeables.
referent: The command table is built in 0x54C960. It allocates 0xC10 bytes, which is 772 slots and equals the routine count in `data/routines/k1.json`. The handlers are:

| Routine | Handler | Stored at |
|---|---|---|
| 313 and 214 | 0x52CDC0 | `[tbl+0x4E4]` and `[tbl+0x358]` |
| 385 and 196 | 0x52CCE0 | `[tbl+0x604]` and `[tbl+0x310]` |

0x52CDC0 resolves OBJECT_SELF and calls `vtbl+0x30`. On 0, which is always the case for a placeable (slot 0x30 is 0x63E7F0), it jumps to `0052cfe5`, and that path does `xor eax,eax; ret 8` without doing anything (`0052cead..b2`).
checked: parser over `fn(0x54c960)` in the scratch session; `f52cdc0.txt`.
verdict: holds for 313/214. 0x52CCE0 was not read. It shares the handler across 385/196, and it is unverified whether it also gates on `vtbl+0x30`. confidence: high for 313/214.

claim: NWScript `SetFacing` (10) and `SetFacingPoint` (143) share handler 0x542830. It works on placeables because it only requires type > 4 and `[vm+4]==1`. It calls `vtbl+0xC0` (a no-op `ret 4` for placeables, 0x60E760) and then `SetOrientation` 0x4CD170. It never touches the walkmesh.
referent: `005428f9..02` checks the type. `005429ce` checks `[ebp+4],1`. `00542a2a call [eax+0xc0]` is followed by `00542a39 call 0x4cd170`. The placeable vtable at 0xC0 is 0x60E760, which is `ret 4`.
checked: `f542830.txt`, and a vtable read with `pe.py`.
verdict: holds. confidence: high.

claim: The engine's full re-placement for a placeable is the pair `RemoveFromArea` 0x584950 and `AddToArea` 0x587170. These rebuild the placeable's collision state. SetPosition does not.

`RemoveFromArea` (0x584950, `thiscall`, no arguments, `ret`) does the following:
1. If `[+0x344] >= 0`, it calls `area->0x58FEC0(obj id)` to remove the walkmesh AABB record, then sets `+0x344 = -1`.
2. It calls `area->0x50DC40(obj id)`.
3. It calls `SetArea(0)` (0x4CB160).
4. It calls `SetPosition(&{0,0,0}, 1, 1, 0)`.

`AddToArea` (0x587170, `thiscall(area, const Vector* pos, int)`, `ret 0xC`) does the following:
1. It calls `RemoveFromArea` first.
2. It calls `SetArea(area)`.
3. It calls `SetPosition(pos, 0, 1, 0)`.
4. It re-reads the `placeables.2da` columns `PreciseUse`, `Hostile` and `ModelName`, keyed by `[+0x230]`, and writes `+0x33C` and `+0x340`.
5. If the collision mesh at `+0x3A0` is loaded (0x596670), it copies the position to `+0x3C0` and builds a quaternion from the facing into `+0x3D8`. It transforms the mesh with 0x596D10 and registers the mesh AABB with `area->0x58FD50(id, &min, &max)` (the return value goes to `+0x344`).
6. It calls `area->0x50DFD0(id, 1)`.

referent: `asm.py fn 587170 584950`. The strings at 0x749820, 0x747f78 and 0x749814 were read with `pe.py`. `0x58FD50` appends `{vec, vec}` and an id to `this+0x44/48/4C/50` and returns the new count. `0x58FEC0` finds and removes by id.
checked: listings in this session.
verdict: holds for the call sequence and fields. The semantics of 0x50DC40 and 0x50DFD0 (area object add and remove) are unverified beyond their `(id[, flag])` call shape. The meaning of AddToArea's third argument is unverified. confidence: high for the sequence, medium for the helper semantics.

Engine evidence that these two form the placement API:
- **CreateObject** (243 → 0x52F820): ctor 0x5877E0, then 0x587A70 (template), then `SetPosition(pos,1,1,0)`, then `SetOrientation(loc+0xC)`, then 0x5853C0 (quaternion), then `AddToArea(area,pos,1)`. The call sites are `0052fb6d` through `0052fc0f`.
- **Area GIT loader** 0x50A7B0: it reads `Bearing`, `Z`, `Y` and `X`, calls 0x5853C0, then `AddToArea(area,&pos,flag)` at `0050aa3e`.
- Other callers of AddToArea are `0x4DD270` `004dd451` and the area EventHandler 0x50D6C0 `0050d786` (row `event.area`). Callers of RemoveFromArea are the dtor 0x5854B0 and 0x588290 (twice).

---

## (4) Risks

claim: Raw SetPosition on a placeable leaves its collision behind. The transformed mesh and its AABB record stay at the old spot, so the old spot keeps blocking and the new spot is walk-through.
referent: The section (1) callee set does not touch `+0x344`, `+0x3A0`, `+0x3C0` or `+0x3D8`, or `area+0x44..0x50`. Only AddToArea writes those (section 3).
checked: listings.
verdict: holds as a data-flow fact. Whether creatures and pathfinding actually query `area+0x4C/0x50` for placeable AABBs: unverified. The readers of that list were not traced. confidence: medium on gameplay impact. For placeables without a collision mesh (the 0x596670 branch not taken), this risk is absent.

claim: A rotation through SetFacing or 0x4CD170 changes the visual only. The collision quaternion at `+0x3D8` and the mesh stay stale.
referent: 0x542830 → 0x4CD170 only, and 0x4CD170 touches only `+0x9C` and `+0x1FC`.
verdict: holds. confidence: high.

claim: Save persistence: the placeable save routine 0x586A70 writes `Bearing` (derived from `+0x9C` via 0x4AA0F0 × 0.0174533, also cached to `+0x25C`) and `X`, `Y`, `Z` from `+0x90..+0x98`. A save taken while moved persists the moved pose. When the save loads, the GIT loader re-runs AddToArea, so collision is rebuilt correctly at the saved spot.
referent: `005870ab..00587113` and `0050a928..0050aa3e`.
verdict: holds. confidence: high that the pose is serialized. That the save routine is reached for every area save is unverified. M3 auto-restore before a save matters for exactly this reason.

Other risks, not verified:
- AddToArea re-reads 2DA state and resets `+0x33C`/`+0x340`, and Remove/Add runs area object remove and add, which may re-fire area events or client create and destroy. Using Remove/Add per tick for smooth motion (M4) is unverified as safe. A per-tick SetPosition plus one final Remove/Add "settle" is the cheaper-to-reverse design. Treat it as a proposal only.
- SetPosition's `a2=1` re-sort takes O(n) swaps per call inside the area X-order. Per-tick use in a crowded area has unmeasured cost.
- No Z snap to the walkmesh happens anywhere in SetPosition. The caller must supply a valid Z.

---

## Offsets safe to enter reviewed data

Each item below has the instruction evidence above and belongs to the image with SHA `9c10e045…`. The expected bytes are the first 16 bytes at the VA, which is the existing `expected_bytes` convention. Keep them out of anything else publishable.

| Name (proposed) | VA | Kind and convention | expected_bytes |
|---|---|---|---|
| `server_object.set_position` (exists) | 0x004CD1A0 | thiscall, 4 args, ret 0x10 | `538b5c240856578bf18dbe9000000053` |
| `server_object.set_orientation` | 0x004CD170 | thiscall(`const Vector*`), ret 4 | `8b542404568b328d819c00000089308b` |
| `server.get_placeable_by_object_id` | 0x004AE7A0 | thiscall on CServerExoApp(id), ret via 0x4B18D0 `ret 4` | `8b4904e9283100009090909090909090` |
| `server_object.get_area` | 0x004CB120 | thiscall, 0 args, `ret` | `51a1fc397a00568bf1c7442404000000` |
| `placeable.set_orientation_quat` | 0x005853C0 | thiscall(`const float[4]*`), ret 4 | `83ec188b44241c568bf1578bd08b3a8d` |
| `placeable.remove_from_area` | 0x00584950 | thiscall, 0 args, `ret` | `83ec0c568bf1e8c567f4ff85c074388b` |
| `placeable.add_to_area` | 0x00587170 | thiscall(area, `const Vector*`, int), ret 0xC | `6aff64a10000000068a0047200506489` |
| `client.get_placeable_by_object_id` | 0x005ED5F0 | thiscall on CClientExoApp(id), tail to 0x5F12C0 `ret 4` | `8b4904e9c83c00009090909090909090` |

Field offsets:

| Field | Offset | Notes |
|---|---|---|
| `object.id` (exists) | +0x04 | |
| `object.type` (exists) | +0x08 | Placeable = 9, the byte at 0x746638 |
| area object id | +0x8C | |
| position | +0x90 | 3 floats |
| orientation vector | +0x9C | 3 floats |
| client-sync gate | +0x1F8 | |
| dirty bitset | +0x1FC | Bit 1 = position, bit 2 = orientation |
| placeable walkmesh AABB registration | +0x344 | -1 means none |
| placeable quaternion | +0x428 | Component order unverified |
| placeable vtable | 0x7494D0 | Usable as a type fence alongside type byte 9 |

Keep these out of reviewed data until they have more evidence:
- `+0x3A0`, `+0x3C0` and `+0x3D8`: internal layout only.
- 0x50DC40 and 0x50DFD0: semantics unverified.
- The client `vtbl+0x12C` and `vtbl+0x130`: identified by call shape only.
- The "+0x24" item from the brief: unresolved.

## What live readback M1 must prove

1. **Type fence.** For a known crate id, the typed getter 0x4AE7A0 returns non-null, `[p+8]==9` and `[p]==0x7494D0`. For the PC id it returns null. For a creature, `[p+8]!=9`.
2. **Pose oracle.** `[p+0x90..0x98]` equals NWScript `GetPosition(oCrate)`. `atan2([p+0xA0],[p+0x9C])` in degrees equals `GetFacing(oCrate)` within 0.01°.
3. **Area.** `[p+0x8C]` equals the id of `GetArea(oCrate)`, and 0x4CB120 returns a non-null area.
4. **Sync gate.** `[p+0x1F8] != 0` for an on-screen crate in the player's area, and `[p+0x1FC] & 6 == 0` at rest.
5. **Dirty consumption** (this is M2's first live test, but M1 can prove the reads): after one `SetPosition(p,&v,1,1,0)`, bit 1 is set immediately and clear within one server tick. The client copy shows the new X/Y/Z (client field offset still to be found). A `GetPosition` round-trip returns `v`.
6. **Same-position no-op.** Calling SetPosition with the current value leaves `+0x1FC` unchanged.
7. **Collision state capture.** Capture `[p+0x344]`, `[p+0x3C0..0x3C8]` and `[p+0x3D8..0x3E4]` at rest. After a raw SetPosition they should still equal the old pose, which confirms the risk in section (4). After Remove/Add they should equal the new pose.
8. **Quaternion order.** Read `[p+0x428..0x434]` for a GIT placeable with a non-zero `Bearing` to fix the component order.

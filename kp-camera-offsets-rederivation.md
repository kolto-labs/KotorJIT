# K1 GOG camera offsets: independent re-derivation

Date: 2026-09-27. Read-only static analysis. No game, Wine, Gamescope or FFmpeg was run.

## Image

- Path: `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image`.
  This matches the plan's `~/biodecompwarehouse/...` and `k1_gog_103.json:3729`.
- `sha256sum` = `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`. This matches `reference_sha256` in `k1_gog_103.json:3730`.
- ImageBase is 0x400000. For `.text` and `.rdata`, file offset = RVA.
- Tools: Python 3.12 with pefile and capstone in a uv venv under `camera-rederive-scratch/`. The full linear-sweep listing is `camera-rederive-scratch/text.asm`, and the helper is `kre.py`.

## Part A: independent findings (written before reading the plan's conclusions)

### A1. Chase behaviour property handler: 0x637a30

- The handler is vtable `0x75165c` slot 3 (+0xc). The slot table is:
  `[0x63ad40 dtor, 0x4015a0 ret, 0x63bcb0 Control, 0x637a30 HandleMessage, 0x63a310 TypeId, 0x63e7f0 x3]`.
- `0x63a310: mov eax, 0x106a; ret`. The type id is **0x106a**.
- Handler pattern: `0x463530(msg)` copies the first token to 0x7fbaf8. `0x70acaf` is a string compare. Then `0x4635c0(msg+len(name), &field)` does `sscanf(s, "%f", p)`. The format string at 0x73e2e4 is `%f`.

| name string (VA) | match insn | store insn | field |
|---|---|---|---|
| `m_fDist` (0x7437dc) | 0x637a3f `push 0x7437dc` | 0x637a50 `lea eax,[edi+0x110]` | **+0x110** |
| `m_fSpeed` (0x7437d0) | 0x637a6a | 0x637a7b `lea edx,[edi+0x114]` | **+0x114** |
| `m_fPresetPitch` (0x7514f8) | 0x637a95 | 0x637aa6 `lea ecx,[edi+0x11c]` | **+0x11c** |
| `m_fHeight` (0x7437c4) | 0x637ac0 | 0x637ad1 `add edi,0x120` | **+0x120** |

- +0x118 is not parsed. Both constructors write 100.0 to it (0x63a102 and 0x63ae65).
- The handler does not call any base-class handler. A message that matches no name is dropped (0x637ae4: `ret 4`).

### A2. Camera-style setup: 0x638070 (thiscall, one argument: style row)

- The routine exits early if `[this+0x5c] == row` (0x638095).
- The 2DA comes from `[[0x7a3a28]+0xb8]+0x74`. If that pointer is null, the routine writes defaults (0x6380b9..0x6380d7) and sets `+0x5c = -1`:
  - +0x110 = 0x40c80000 = **6.25**
  - +0x114 = 0x41a00000 = **20.0**
  - +0x11c = 0x42a00000 = **80.0**
  - +0x120 = 0x40600000 = **3.5**
- If the 2DA exists, the routine checks `row <= 2da.rowcount` (`cmp eax,[edi+0x24]; jg`), sets `+0x5c = row`, and calls `C2DA::GetFloatEntry` (0x413430) once per column:
  - DISTANCE -> +0x110
  - SPEED -> +0x114
  - PITCH -> +0x11c
  - HEIGHT -> +0x120
  - TILTUP -> global 0x7a2420
  - TILTDOWN -> global 0x7a2424
  - TILTSPEED -> +0x134
  - ROTATION -> global 0x7a2428
  - VIEWANGLE -> local. If the value is 0.0 it becomes 55.0.
- After the 2DA reads, the routine also does the following (0x638383..0x638393):
  - Sets FOV through `[this+0x1c]->vt[4]()->vt[0x44](viewangle)`.
  - Writes `+0x88 = +0x110`. This is the base distance.
  - Writes `+0x8c = viewangle`. This is the base view angle.
- The default (no-2DA) path does **not** write +0x88 or +0x8c.
- Callers:
  - 0x63a0ae, in ctor 0x639fc0. The row comes from `[[owner]+0x48]+0xb8`.
  - 0x63ae24, in copy-ctor 0x63ad60. It first sets `+0x5c = -1`, then uses row = `rec+0x10`.
  - 0x638fc0, in per-tick helper 0x638f60. See A4.

### A3. Pointer path

```
g_pAppManager      = [0x7a39fc]
client             = [g + 0x4]
client_internal    = [client + 0x4]          (0x5ed530: mov ecx,[ecx+4]; jmp 0x644760)
cam_owner          = [client_internal + 0x18] (0x644760: mov eax,[ecx+0x18])
aur_camera         = [cam_owner + 0x40]
current_behaviour  = [aur_camera + 0x18c]    (= embedded sub-object at +0x4, field +0x188)
chase fields       = current_behaviour + {0x110, 0x114, 0x11c, 0x120}
```

- cam_owner:
  - Allocated as 0x138 bytes at 0x5eea37 or 0x5f8d6d.
  - Ctor is 0x643f40, which sets vtable **0x751848** at 0x643f7e.
  - Stored `[internal+0x18]` at 0x5eea5d and 0x5f8d98.
  - `+0x40` is set at 0x63f6e0 from `0x45d930("camera")`.
  - `+0x48` is a 0x284-byte object. Its `+0xb8` is the style row.
- aur_camera:
  - Factory 0x45d930 allocates 0x234 bytes.
  - Ctor 0x45d800 sets final vtable **0x741b20**. The sub-object at +4 has vtable **0x741988**.
  - +0x1d0 = FOV (default 45.0).
- Behaviour slot:
  - The setter is `aur_camera->vt[0x7c]`, which reaches `0x43f1d0`. It writes `[sub+0x188]` and destroys the old behaviour with `vt[0](1)`.
  - The getter is `vt[0x80]` -> 0x43f130. With -1 it returns the current behaviour. Any other value matches the behaviour's `vt[0x10]` type id.
- Chase guards:
  - `[beh] == 0x75165c`
  - `beh->vt[4]() == 0x106a`
  - Allocation size is 0x138.
  - Base ctor 0x49f110 sets base vtable 0x743864 and `+0x10` = its argument.
- Other behaviour types seen in the mode switch 0x641dc0: 0x106d, 0x106e, 0x1070.
- A sibling class has vtable 0x743924, with the yaw/pitch/dist handler 0x49ee00 and Control 0x49f6d0. The repo codecaves label it CAurBehaviorCameraFollow.
- Caveat: `cam_owner+0x110` is a mode selector in 0x641dc0 (0 builds a chase, 1 builds a 0xc4-byte behaviour). It is a different struct from chase+0x110. Do not confuse the two.

### A4. Other writers of chase +0x110

Whole-text sweep of `.text` for `[reg+0x110]` writes, plus `lea reg,[reg+0x110]` in the camera region 0x636000..0x646000. Only these touch the chase object:

1. Handler 0x637a50: `m_fDist`.
2. Style setup 0x6380b9 (default) and 0x63810f (2DA).
3. **Per-tick recompute in Control (0x63bcb0):** `if ([this+0x84] != 0) +0x110 = tan(+0x8c * pi/360) * +0x88 / tan(aurcam_fov * pi/360)`.
   - Store is at 0x63bcfa: `fstp dword ptr [esi+0x110]`.
   - The constant at 0x741bb4 is 0.0087266 (pi/360).
   - The FOV comes from `[this+0x1c]->vt[4]()->vt[0x48]()`.
   - This keeps on-screen framing constant when FOV changes. It **overwrites any value poked into +0x110 on the next tick** while +0x84 is non-zero.
4. **Pending-style global 0x7a242c**, read in 0x638f60. Control calls 0x638f60 every tick (0x63bd02). If the global is not -1, the helper calls `0x638070(this, [0x7a242c])` and then resets the global to -1.
   - .data initialises it to 0xffffffff.
   - **No retail code writes a value other than -1.** The only xrefs are 0x638fb4 (read) and 0x638fc7 (reset). A tool can write it to force a style reload.
   - The early-exit check means the row must differ from `+0x5c`, or `+0x5c` must be set to -1 first.

Who sets chase +0x84:
- Ctor 0x639fc0 writes 0 at 0x63a2aa.
- The copy-ctor 0x63ad60 **does not initialise +0x84**. The memory comes from `operator new` (0x6fa7e6 calls `_nh_malloc(sz,1)`), which does not zero it.
- The other `+0x84` writers in the region (0x640909/0x640a52/0x640f44/0x64401f/0x64424f) are cam_owner methods, because their `this+0x40` is aur_camera. 0x63e530 and 0x63ce60 are unrelated classes.
- I found **no static retail writer that sets chase+0x84 to non-zero**. For a copy-constructed chase its value is indeterminate. Confidence is medium; a live read would settle it.

Consumers of +0x110:
- 0x6398f0 smooths the current distance toward it (0x639b5b/0x639b6b).
- 0x637af0 and 0x639c30 also read it.
- +0x110 is the **target** distance, not the instantaneous one.

### A5. SetCameraFacing messages and the chase behaviour

- The client "Camera" message handler is 0x64b8e0, reached from dispatch 0x66a735 under the "Camera" major-type string 0x752298.
- For minor 1 it reads a bitmask. Then:
  - bit1 sends `sprintf("yaw %f", (v-pi/2)*57.2958)`
  - bit2 sends `"dist %f"`
  - bit4 sends `"pitch %f"`
- A second sender at 0x622610 sends `dist`, `pitch` and `yaw` in that order.
- Delivery: `aur_camera->vt[0x60]` (0x45c160) goes to 0x43f5a0. That does `beh=[sub+0x188]; jmp beh->vt[0xc]`. The message goes **only to the current behaviour's slot 3**.
- The chase slot 3 is 0x637a30, which recognises only `m_fDist`, `m_fSpeed`, `m_fPresetPitch` and `m_fHeight`. `yaw`, `pitch` and `dist` match none of them, and there is no base-class fallback.
- **Result: the chase behaviour does not handle SetCameraFacing's messages. They are silently dropped.**
- `yaw`, `pitch` and `dist` are parsed by 0x49ee00 in vtable 0x743924 (the Follow class). The `dist` handler starts at 0x49ee58.
- I did not trace the server-side NWScript command to this client message. The link from "SetCameraFacing" to the "Camera" minor 1 message is inferred from content, not traced.

## Part B: claim-by-claim comparison with `kp-camera-api-plan.md`

I read the plan only after Part A was written.

```
claim: CSWCameraOnAStick::Message 0x637a30 maps m_fDist/m_fSpeed/m_fPresetPitch/m_fHeight -> +0x110/+0x114/+0x11c/+0x120 (plan §0.2, §1 row, L372)
referent: A1 table; lea/add immediates at 0x637a50/0x637a7b/0x637aa6/0x637ad1; literal pushes at 0x637a3f/6a/95/c0; parse offsets +7/+8/+0xe/+9
checked: capstone disasm of 0x637a30..0x637ae9; vtable word 0x751668 == 0x637a30
verdict: holds (agree)
confidence: high. Only a different image would change it.

claim: SetCameraStyle 0x638070 seeds 6.25/20/80/3.5, then camerastyle.2da values (plan §0.2)
referent: 0x6380b9..0x6380d7 immediates 0x40c80000/0x41a00000/0x42a00000/0x40600000; C2DA::GetFloatEntry 0x413430 with DISTANCE/SPEED/PITCH/HEIGHT into the same fields
checked: disasm 0x638070..0x6383aa
verdict: holds (agree)
addition: defaults are used only when [[0x7a3a28]+0xb8]+0x74 (the 2DA) is null. The routine exits early if +0x5c == row. Only the 2DA path writes +0x88/+0x8c.
confidence: high

claim: chain [[[[[0x7a39fc]+4]+4]+0x18]+0x40] = camera; active behaviour = [camera+0x18c] (plan L126, L379)
referent: 0x5ed530 `mov ecx,[ecx+4]; jmp 0x644760`; 0x644760 `mov eax,[ecx+0x18]; ret`; 0x64b9b0 `mov esi,[eax+0x40]`; 0x45c160 `add ecx,4; jmp 0x43f5a0`; 0x43f5a0 `mov ecx,[ecx+0x188]; ... jmp [eax+0xc]`
checked: disasm of each. Also: the [internal+0x18] store is at 0x5eea5d and 0x5f8d98, right after ctor 0x643f40, whose object vtable is 0x751848. The +0x40 store is at 0x63f6e0 from factory 0x45d930("camera"), with vtable 0x741b20 set at 0x45d846.
verdict: holds (agree)
addition: two more guards are available. [module] == 0x751848 checks the owner vtable. Setter 0x43f1d0 writes the same +0x188 (camera+0x18c) slot.
confidence: high statically. A live read would confirm that the object is populated in gameplay.

claim: camera vtable 0x741b20, slot +0x60 (word 0x741b80) = 0x45c160 (plan L54, L152)
referent: u32(0x741b20+0x60) = 0x45c160
checked: python read
verdict: holds (agree)
confidence: high

claim: OnAStick vtable 0x75165c, stored at 0x639fee, 0x63a328, 0x63ad96 (plan L70)
referent: xrefs(0x75165c) = [0x639ff0, 0x63a328, 0x63ad96]. Each immediate sits 2 bytes inside a `c706` store, so the 0x639ff0 immediate belongs to the instruction at 0x639fee.
checked: raw xref scan + disasm
verdict: holds (agree)
addition: slot 4 (0x63a310) returns type id 0x106a. Allocation size is 0x138 (0x642080, 0x641b2d).
confidence: high

claim: dolly flag +0x84; when set, Control 0x63bcb0 recomputes m_fDist = tan(+0x8c*pi/360)*(+0x88)/tan(fov*pi/360), stored at 0x63bcfa (plan L72)
referent: 0x63bcb8 `mov eax,[esi+0x84]; test; je 0x63bd00`; 0x63bccc/0x63bcec fmul [0x741bb4]=0.0087266; 0x63bcfa `fstp [esi+0x110]`
checked: disasm 0x63bcb0..0x63bd36
verdict: holds (agree)
confidence: high

claim: pending style global 0x7a242c (-1 = none), read in 0x638f60, which is called only from Control 0x63bd02; no retail writer except the reset (plan L73, E6, R7)
referent: xrefs(0x7a242c) = [0x638fb4, 0x638fc7]. There are no .data pointers to it, and it initialises to 0xffffffff. callers(0x638f60) = [0x63bd02].
checked: raw 4-byte scan of .text and a non-.text pointer scan
verdict: holds (agree). E6 is still open and I cannot close it: no static writer exists.
confidence: high that no absolute-address writer exists. Low that it is never written, because an indirect write through a computed pointer would not show in this scan.

claim: who sets +0x84 is unknown (plan E7)
referent: ctor 0x639fc0 writes 0 at 0x63a2aa. I found no chase-object writer of a non-zero value. The other +0x84 writers in 0x636000..0x646000 belong to cam_owner, whose this+0x40 is the camera, or to unrelated classes.
checked: sweep of text.asm for `[reg+0x84]` in the camera region, plus attribution of each enclosing function
verdict: holds (agree it is open), with a new fact. **The copy-ctor 0x63ad60 never initialises +0x84.** It is reached from mode switch 0x641dc0 at 0x642221, on the restore-from-saved-record path. The memory comes from `operator new` 0x6fa7e6 (`_nh_malloc(sz,1)`, not zeroed), so +0x84 holds heap garbage for that instance. That instance also never gets +0x88/+0x8c if the 2DA is missing. The plan's runtime check that dolly is false at call time is therefore **required**, not optional.
confidence: medium. A live read of +0x84 after a restore-path mode change would settle it.

claim: SetCameraFacing's yaw/pitch/dist strings are inert under OnAStick (plan §0.3, L394)
referent: 0x64b9e3/0x64ba13/0x64ba43 push 0x74fc28/0x74fc3c/0x74fc30 and then `call [eax+0x60]` on the camera. Dispatch reaches only [camera+0x18c]->vt[+0xc]. 0x637a30 has no `yaw`/`pitch`/`dist` compare and no parent call. The strings are parsed only by 0x49ee00 (vtable 0x743924, the Follow class).
checked: disasm of 0x64b8e0, 0x43f5a0, 0x637a30, 0x49ee00
verdict: holds (agree). Like the plan, I have no live read of which behaviour is active in the relevant mode.
confidence: high statically

claim: Control_HitCheckCamera 0x63b050 never writes +0x110 (plan §0.4)
referent: whole-text sweep for writes to `[reg+0x110]`. The only chase-region writers are 0x6380b9 and 0x63bcfa, plus the lea at 0x637a50/0x63810f.
checked: grep text.asm
verdict: holds (agree, for writes)
confidence: high for direct stores

claim: 0x6398f0 uses m_fDist at +0x26b/+0x27b and m_fHeight at +0x30f (plan E8)
referent: 0x639b5b `fsub [esi+0x110]`, 0x639b6b `fadd [esi+0x110]`, 0x639bff `fadd [esi+0x120]`
checked: text.asm
verdict: holds (agree on the reads). The geometry question in E8 is not settled here. The code smooths the current distance toward +0x110 using factor global 0x7a243c.
confidence: high for the offsets

claim: ResetLastPosition 0x637c20 writes a quaternion at +0x28..+0x37 and a vector at +0x38 and +0x50 (plan L74-75)
referent: 0x637c2d..0x637c6d stores into +0x38 and +0x50 (3 dwords each) and into +0x28 (4 dwords)
checked: disasm 0x637c20
verdict: holds (agree). The meaning is still unverified, as the plan says.
confidence: high for the offsets

claim: options = [[client+4]+4], mode byte +0x6d, set by 0x61b6f0 (plan L76)
referent: 0x5ed700 `8b4104 8b4004 c3`; 0x61b6f0 `mov [ecx+0x6d],al` (also writes +0x6e when al is 0 or 1)
checked: disasm
verdict: holds (agree)
confidence: high

claim: 0x463530 = firstword into static buffer 0x7fbaf8; 0x70acaf = __stricmp; 0x4635c0 = sscanf "%f" (plan L77)
referent: 0x463556 `mov [edx+0x7fbaf8],al`; 0x70acaf calls the per-char locale conversion 0x6fb69e on both strings; 0x4635c9 push 0x73e2e4 ("%f")
checked: disasm
verdict: holds (agree)
confidence: high
```

Disagreements: **none**.

Things in the plan I did not re-derive:
- Pitch and height units.
- Quaternion component order.
- Whether +0x38 is the current position.
- Live-state claims (§4 framing numbers, CAL shot).

These are marked unverified in the plan too.

## Re-derivation verdict: CONFIRMS

Offsets safe to enter into reviewed data for image SHA 9c10e045…91435. Every one has two independent static signals:

| item | value | guard bytes |
|---|---|---|
| g_pAppManager | 0x7a39fc | (already adjudicated) |
| appmgr → client | +0x4 | 0x5ed530 `8b4904` |
| client → internal | +0x4 | 0x5ed530 `8b4904` then 0x644760 |
| internal → cam owner ("module") | +0x18 | 0x644760 `8b4118c3` |
| cam owner vtable (guard) | 0x751848 | 0x643f7e `c70648187500` |
| owner → camera | +0x40 | 0x64b9b0 `8b7040` |
| camera vtable (guard) | 0x741b20 | 0x45d846 `c706201b7400` |
| camera → active behaviour | +0x18c (= Gob +4, +0x188) | 0x45c160 `83c104`; 0x43f5a0 `8b8988010000` |
| OnAStick vtable (guard) | 0x75165c | 0x639fee `c7065c167500`; word 0x751668 = 0x637a30 |
| OnAStick type id (guard) | 0x106a | 0x63a310 `b86a100000c3` |
| m_fDist | +0x110 | 0x637a50 `8d8710010000` |
| m_fSpeed | +0x114 | 0x637a7b `8d9714010000` |
| m_fPresetPitch | +0x11c | 0x637aa6 `8d8f1c010000` |
| m_fHeight | +0x120 | 0x637ad1 `81c720010000` |
| dolly flag (read-only gate) | +0x84 | 0x63bcb8 `8b8684000000` |
| dolly base dist / base view angle | +0x88 / +0x8c | 0x63838d / 0x638393; 0x63bcc3 / 0x63bcd8 |
| pending-style global (read-only gate) | 0x7a242c | 0x638fb3 `a12c247a00` |
| cached style row | +0x5c | 0x638095 `39465c` |
| options → camera mode byte | [[client+4]+4] +0x6d | 0x5ed700; 0x61b6f0 `88416d` |

Enter these only as raw, meaning-unverified offsets:
- +0x28 (quaternion)
- +0x38 and +0x50 (vectors)

Keep these open:
- E6 (writer of 0x7a242c).
- E7 (writer of +0x84). This review adds the copy-ctor finding, so dolly must be checked at runtime before every write.

# Motion M0 verification (opposer pass, read-only)

Date: 2026-09-27. Receipt under review: `motion-m0-rederivation.md`.
Method: I re-derived each item from `camera-rederive-scratch/text.asm` before reading the receipt, then compared.
Byte and constant reads came from a standalone stdlib PE reader over the raw image (I did not import `pe.py`).
No Wine or game was run. The live-game lock was not touched. Nothing in the repo was edited.
Retail bytes are not reproduced here; expected_bytes are reported only as match or mismatch.

## Image

claim: image is the k1_gog_103 reference image
referent: `sha256sum raw_image` = 9c10e045…1435; equals `k1_gog_103.json:4041-4042` (reference_sha256, derived_sha256)
checked: command run here
verdict: holds
confidence: high

claim: expected_bytes for all 8 functions in the "safe" table
referent: 16-byte reads at 0x4CD1A0, 0x4CD170, 0x4AE7A0, 0x4CB120, 0x5853C0, 0x584950, 0x587170, 0x5ED5F0 all equal the receipt table, byte for byte
checked: independent python reader over the raw image
verdict: holds
confidence: high

## Functions

claim: 0x4CD1A0 SetPosition is thiscall(this, const Vector* pos, a2, a3, a4), ret 0x10
referent: `004cd1a7 mov esi, ecx`; `004cd23c ret 0x10`. Stack math: at `004cd1a1` one push has happened, so `[esp+8]` = arg1 = pos → ebx; `004cd1bd [esp+0x1c]` with 3 pushes = a4; `004cd212 [esp+0x18]` with 4 pushes = a2. There is no read of a3.
checked: text.asm 004cd1a0..004cd23c
verdict: holds
confidence: high

claim: early return when the new position equals the current one (no write, no flag)
referent: `004cd1b1 call 0x4aa980(this+0x90, pos)`; 0x4AA980 compares 3 floats with fcomp/`test ah,0x44`/jp, and returns 1 only if all three are equal (`004aa9ad`); `004cd1bb jne 0x4cd239` goes straight to the pop/ret. Exact float equality only; NaN never counts as equal.
checked: text.asm 004aa980..004aa9b5
verdict: holds
confidence: high

claim: a4==0 sets dirty bit 1 (`|= 2`) at +0x1FC; a4!=0 is silent
referent: `004cd1c4 cmp eax(a4), ebp(0)`; `jne` skips `004cd1c8 or dword ptr [esi+0x1fc], 2`
checked: text.asm
verdict: holds. The receipt says bit 1 (value 2), which is correct. The task brief says "a4==0 sets bit 2", which is wrong if read as a bit index. Bit index 2 (value 4) belongs to orientation (0x4CD170).
confidence: high

claim: no type check in SetPosition
referent: nothing reads `[esi+8]` in 004cd1a0..004cd23c (grep count 0). The only type-dependent call is `vtbl+0x30` (`004cd21e`/`004cd229`), and its result is discarded. The placeable vtable 0x7494D0 slot 0x30 = 0x63E7F0 = `xor eax,eax; ret`.
checked: grep on the listing, plus a vtable read
verdict: holds
confidence: high

claim: 0x4CD170 SetOrientation writes +0x9C..+0xA4, sets `|= 4`, ret 4, and does no equality check
referent: `004cd177 lea eax,[ecx+0x9c]`, 3 dword copies, `004cd18b or [ecx+0x1fc], 4`, `004cd193 ret 4`. No compare and no calls.
checked: text.asm
verdict: holds
confidence: high

claim: 0x4AE7A0 is the server typed getter: tail call to 0x4B18D0, type byte == [0x746638] (9), returns vtbl+0x48, ret 4
referent: `004ae7a0 mov ecx,[ecx+4]; jmp 0x4b18d0`; `004b18d5 [ecx+0x1005c]`; `004b18fe mov al,[ecx+8]; cmp al,[0x746638]`; `004b190b call [edx+0x48]`; `ret 4`. The byte at 0x746638 is 09. Placeable vtable slots 0x10 and 0x48 are the only slots in 0x00..0x5C that return `this` (`mov eax,ecx; ret`).
checked: text.asm plus a raw-image read
verdict: holds
confidence: high

claim: 0x4CB120 GetArea: thiscall, 0 args, ret; resolves +0x8C through the object array and vtbl+0x28
referent: `004cb139 mov edx,[esi+0x8c]` → `call 0x4d8230` → `004cb157 call [eax+0x28]`; `ret` with no immediate. 0x4AED70 = `[[ecx+4]+0x1005c]`.
checked: text.asm
verdict: holds
confidence: high

claim: 0x5853C0 stores the quaternion at +0x428 (16 bytes), derives the facing, and calls 0x4CD170; ret 4
referent: `005853cf lea ecx,[esi+0x428]` plus 4 dword copies; float math; `0058542e call 0x4ab180`; `00585451 call 0x4cd170`; `0058545b ret 4`
checked: text.asm
verdict: holds. Component order is not settled by this listing (the receipt agrees).
confidence: high for the call shape, low for the component order

claim: 0x584950 RemoveFromArea: thiscall, 0 args, ret. If +0x344 >= 0 it calls area->0x58FEC0(id) and sets +0x344=-1, then area->0x50DC40(id), then 0x4CB160(0), then SetPosition(&{0,0,0},1,1,0)
referent: `0058495f..0058497b` (`test; jl`; `call 0x58fec0`; `mov [esi+0x344],0xffffffff`); `00584992 call 0x50dc40`; `0058499b call 0x4cb160` with push 0; the pushes 0,1,1,&zero then `005849c5 call 0x4cd1a0`; `005849ce ret`. 0x58FEC0 scans `area+0x50` (count `+0x48`) for the id, ret 4.
checked: text.asm
verdict: holds. A side effect the receipt does not state: because a4=0, RemoveFromArea itself sets position dirty bit 1, unless the position is already exactly 0,0,0.
confidence: high

claim: 0x587170 AddToArea(area, const Vector* pos, int): ret 0xC. It calls Remove, then SetArea(area), then SetPosition(pos,0,1,0). If the mesh at +0x3A0 is loaded, it copies +0x90 to +0x3C0, builds a quaternion from +0x9C into +0x3D8, transforms the mesh, and registers it through area->0x58FD50, which returns the handle stored in +0x344. Then area->0x50DFD0(id,1).
referent: SEH frame 0xC plus `sub 0x54` plus 4 pushes = 0x70, so `[esp+0x74]`=area and `[esp+0x78]`=pos. `0058718e call 0x584950`; `005871a4 call 0x4cb160`; pushes 0,1,0,pos then `005871b8 call 0x4cd1a0`; `005872f0 call 0x596670` gate; `005872fd..16` copy +0x90 to +0x3c0; `00587319 lea edx,[esi+0x9c]` → `0x4aa0f0`; `00587377` writes +0x3d8; `0058739d call 0x596d10`; `005873cc call 0x58fd50` then `005873d1 mov [esi+0x344],eax`; `005873e6 call 0x50dfd0` with (id,1); `0058740e ret 0xc`
checked: text.asm
verdict: holds
confidence: high for the sequence. Medium for what 0x50DC40 and 0x50DFD0 mean (the receipt keeps them out of reviewed data, which is correct).

claim: 0x5ED5F0 is the client typed getter: tail call to 0x5F12C0, client array at internal+0x14, type 9, returns vtbl+0x4C, ret 4
referent: `005ed5f0 mov ecx,[ecx+4]; jmp 0x5f12c0`; `005f12c5 mov ecx,[ecx+0x14]`; `005f12ee cmp al,[0x746638]`; `005f12f8 call [edx+0x4c]`; `005f12fc ret 4`
checked: text.asm
verdict: holds
confidence: high. The brief's "+0x24" is still unresolved; the receipt already says so.

## Fields

claim: +0x4 is the id and +0x8 is the type byte; placeable type == 9
referent: `004d7d70 mov [eax+4],ecx(id)`; `004d7d73 mov byte [eax+8],dl(type)`; placeable ctor `00587803 mov cl,[0x746638]` → `00587815 call 0x4cfcb0`; the byte at 0x746638 is 09
checked: text.asm plus a raw-image read
verdict: holds
confidence: high

claim: +0x8C holds the area object id
referent: `004cd1e0` and `004cb139` both load `[esi+0x8c]` as the id passed to 0x4D8230, followed by vtbl+0x28
checked: text.asm
verdict: holds
confidence: high

claim: +0x90 is the position (3 floats) and +0x9C is the orientation vector (3 floats)
referent: SetPosition writes via `lea edi,[esi+0x90]`; SetOrientation via `lea eax,[ecx+0x9c]`; the save routine reads +0x90/+0x94/+0x98 under the strings "X"/"Y"/"Z" (0x7476e8, 0x74699c, 0x747a88) and +0x9C under "Bearing" (0x747a8c); the consumer pushes `lea ecx,[esi+0x90]` and `lea ecx,[esi+0x9c]`
checked: text.asm plus string reads
verdict: holds
confidence: high

claim: +0x1F8 is the per-object gate on the client push in 0x4B0B70
referent: `004b1098 mov eax,[esi+0x1f8]; test; je 0x4b116b` skips the whole bit-consumer block. The writer is `005780a6 mov [esi+0x1f8],eax` after `call 0x56dc60`, and the ctor zeroes it at `004d00de`.
checked: text.asm
verdict: holds as a gate. What 0x56DC60 decides is still unverified. Name the field for its role as a gate, not as "visible to player".
confidence: high for the gate, low for its meaning

claim: +0x1FC is the dirty bitset: bit 0 animation, bit 1 position, bit 2 orientation; consumed and cleared per server tick in 0x4B0B70
referent: helpers 0x4CC1F0/0x4CC220/0x4CC250 do `1 << (n & 31)` on `[this + (n>>5)*4 + 0x1fc]`. Consumer `004b10c6` tests bit 0, which feeds `[esi+0xd4]`/`[esi+0xd8]` to vtbl+0x134. Bit 1 (`004b10fe`) pushes `&[esi+0x90]` to vtbl+0x12C and is cleared at `004b1138`. Bit 2 (`004b113d`) pushes `&[esi+0x9c]` to vtbl+0x130 and is cleared at `004b1166`. There is no ret between 0x4B0B70 and 0x4B1166. The only caller is `004bac73` in MainLoop, gated by `[[0x7a39fc]+0x14]->[0]==0` and `word [internal+0x10008]==2` (the receipt says dword-ish "==2"; it is a word compare, which does not matter for the claim).
checked: text.asm
verdict: holds
confidence: high

claim: +0x344 is the placeable walkmesh AABB registration handle; -1 means none
referent: written from the 0x58FD50 return at `005873d1`; set to 0xffffffff at `0058497b`; the `jl` guard at `00584967`
checked: text.asm
verdict: holds. The ctor initialises it to -1 (see the block below).
confidence: high

claim: the placeable vtable is 0x7494D0
referent: `00587824 mov dword ptr [esi], 0x7494d0` in the ctor; slots 0x10 and 0x48 are `mov eax,ecx; ret`, slot 0x30 is `xor eax,eax; ret`, slot 0x78 is 0x587BA0, slot 0xC0 is 0x60E760 (`ret 4`)
checked: text.asm plus a raw-image read
verdict: holds
confidence: high

## Behaviour

claim: placeables sit in the AI-master lists that the dirty-bit consumer walks
referent: ctor `005878d3 call 0x4aed80` (= `[[ecx+4]+0x10044]`, the AI master) then `005878da call 0x4b0850(this, 0)`. 0x4B0850 appends `obj+4` to the list at `master + 4 + prio*0x10` and sets `[obj+0x78]=prio` (`004b087b..88`). The consumer loop starts `004b103b lea ebp,[edi+0x48]` (edi = master, from `004b0b77`) with counter 5, reads count `[ebp]` and array `[ebp-4]`, and steps `004b1183 sub ebp,0x10`. So it walks counts at +0x48/+0x38/+0x28/+0x18/+0x08, and that includes prio 0 (array +0x04, count +0x08). Each id is resolved through `0x4ae750` before the gates.
checked: text.asm
verdict: holds. So "SetPosition(a4=0) / SetOrientation, then the next tick pushes to the client" needs no explicit sync call, provided +0x1F8 != 0.
confidence: high. It assumes 0x6449D0's list layout is {array, count}, which the consumer's own `[ebp-4]`/`[ebp]` reads agree with.

claim: `this` for the typed getters
referent: server: callers load `ecx=[[0x7a39fc]+8]` (for example `004cd1cf..d8`), and the thunk does `[ecx+4]`, then `+0x1005c`. Client: the caller at `005fd9ec..f5` loads `ecx=[[0x7a39fc]+4]`, then `call 0x5ed5f0`.
checked: text.asm
verdict: holds as "app object at [[0x7a39fc]+8]" and "app object at [[0x7a39fc]+4]". The class names CServerExoApp and CClientExoApp are naming only.
confidence: high for the pointer source, low for the class names

claim: +0x344 initial value
referent: placeable ctor `005879b4 mov dword ptr [esi+0x344], 0xffffffff`
checked: text.asm
verdict: -1 from construction. 0x58FD50 returns the new list count, and 0x58FEC0 removes by id, not by this value. So +0x344 is a registered/not-registered marker checked with `>= 0`, not an index to dereference.
confidence: high

claim: JumpToLocation (313) and ActionJumpToLocation (214) are no-ops on placeables
referent: the table stores `0054e1c7 [tbl+0x4e4]=0x52cdc0` (0x4E4/4 = 313) and `0054ca86 [tbl+0x358]=0x52cdc0` (214). In 0x52CDC0, both the 1-arg and the 2-arg (`0052ce5e cmp eax,2; jge 0x52ceea` → rejoins `0052ce74`) paths reach `0052cead call [eax+0x30]; je 0x52cfe5`. That path does `xor eax,eax` then `0052cfec ret 8`. For a placeable, slot 0x30 returns 0.
checked: text.asm
verdict: holds for 313/214. 385/196 (0x52CCE0) was not read by either of us.
confidence: high

claim: RemoveFromArea and AddToArea move the collision; SetPosition does not
referent: the callee set of SetPosition is exactly 0x4AA980, 0x4AED70, 0x4D8230, vtbl+0x28, vtbl+0x30, 0x506FE0. Nothing in 004cd1a0..004cd23c touches +0x344, +0x3A0, +0x3C0 or +0x3D8. AddToArea rewrites all of them (above).
checked: text.asm
verdict: holds as data flow. Whether pathing actually reads the area+0x44..0x50 AABB list is untraced (the receipt already says so).
confidence: high for the data flow, medium for the gameplay effect

claim: the save at 0x586A70 writes the current fields
referent: 0x586A70 is a function start (nop padding at 00586a6d..6f; no ret before 00587113). `005870ab lea edx,[esi+0x9c]` → `0x4aa0f0` → Bearing (0x747a8c) with a cache to `+0x25c`; `005870dc/f0/104` read +0x90/+0x94/+0x98 under X/Y/Z
checked: text.asm plus string reads
verdict: holds. The claim that every area save reaches this routine is unverified (the receipt already says so).
confidence: high

## Differences from the receipt

- None on substance. Every "safe" item re-derived to the same instruction evidence.
- Nit: the MainLoop gate is `cmp word ptr [esi+0x10008], 2`, not a dword compare.
- Addition: placeable AI-list membership re-derived independently (ctor → 0x4B0850 prio 0, walked by the 5-list consumer).
- Addition: RemoveFromArea's own SetPosition(…,a4=0) sets position dirty bit 1.
- The task brief's "a4==0 sets bit 2" is wrong; it is bit 1 (value 2). The receipt is right.

Motion M0 verification: CONFIRMS

Safe to enter reviewed data (image sha 9c10e045…):
- functions: 0x4CD1A0 (set_position, exists), 0x4CD170, 0x4AE7A0, 0x4CB120, 0x5853C0, 0x584950, 0x587170, 0x5ED5F0
- fields: +0x04 id, +0x08 type (placeable == 9), +0x8C area id, +0x90 position vec3, +0x9C orientation vec3, +0x1F8 client-push gate (meaning of its value unverified), +0x1FC dirty bitset with bit1 = position (value 2) and bit2 = orientation (value 4), +0x344 AABB-registered marker (>=0 registered, -1 none; ctor sets -1; do not dereference as an index)
- vtable: 0x7494D0 (placeable)
- +0x428 quaternion: offset only, no component order
- keep out: +0x3A0, +0x3C0, +0x3D8, 0x50DC40, 0x50DFD0, client vtbl+0x12C/+0x130/+0x134, 0x506FE0's reverse pass, 0x52CCE0, "+0x24"

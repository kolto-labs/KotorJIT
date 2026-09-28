# Win K1 actual projectile model-load hook contract

Private research summary, 2026-09-22. No game attachment, execution, build, source edits or recovery jobs. Independently hashed `/home/brunner56/krayt/tmp/k1_harness/swkotor.exe`: SHA256 `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`. PE i386, preferred image base0x400000. Addresses below are preferred VAs; runtime addressing is loadedBase+(VA-0x400000). Do not substitute another retail image or Mac ABI. Corpus func names supplied labels; original executable bytes verified the control flow and layouts described as proved below. Raw disassembly remains in private scratch, not public/browser payloads.

## Proved load dispatch and ABI

CSWCProjectile constructor0x6d57b0 is called by the projectile receiver at0x6504e3 after allocating0x1c8 bytes. It installs vtable0x757cc8 at object offset0. Independently read the original PE vtable: slot+0x78 contains0x6d2c50 (LoadModel), slot+0x8c contains0x63f340 (SetPosition), slot+0x94 contains0x63d820 (AttachToScene).

Receiver0x6501b0 reaches the first projectile model-load dispatch at0x650551, returning to0x650554. At the dispatch ECX=ESI=the newly constructed CSWCProjectile. Three stack slots are passed in logical order: CResRef pointer,0xff,0. LoadModel0x6d2c50 returns EAX0/1 and callee-pops12 bytes on inspected exits. Thus the callable physical contract is x86 thiscall with three4-byte stack slots; preserve the original flags. The descriptive names/semantics of the two flags are not proved. Third stack argument is not used by this inspected implementation but still belongs to the ABI and must not be omitted.

LoadModel reads projectile+0x68 as its animation/model wrapper, constructs a0xf0-byte wrapper when absent and stores it back. It calls wrapper virtual+0x0c with the CResRef pointer and second original argument; on success it obtains a model object through wrapper virtual+8 and associates that model with the projectile through model virtual+0x74. This is the actual engine-owned projectile model path, not a spawned placeable imitation.

The wrapper implementation0x6ea4e0 reads the resource through CResRef, loads a model via0x449cc0, stores the result at wrapper+0xb8, returns0 on failure/1 on success, and copies the resource reference into wrapper+0x2c. That copy supports a caller-owned temporary CResRef for the synchronous load call; resource/model lifetime afterward belongs to the engine wrapper. It does not justify writing raw model pointers or freeing wrappers manually. CResRef comparisons at0x406dc0 compare four DWORDs (16-byte value); use an existing verified constructor/copy contract rather than treating it as CExoString. The receiver constructs its original local CResRef at0x65053c via0x406d60 from a CExoString.

## Source and target available at the load boundary

Define S as the receiver's steady stack pointer immediately before its three LoadModel argument pushes at0x650543. Earlier at0x6501dd and0x6501ed the receiver calls ReadOBJECTIDClient0x692630 twice. The first returned client object ID is stored at[S+0x8c]; the second at[S+0x14]. The first ID is resolved through manager global0x7a39fc -> manager+4 client app -> GetCreatureByGameObjectID0x5ed5b0 at0x650267; null goes to the receiver's exit. EDI becomes that creature and is retained through0x650551.

The receiver uses this first creature for equipment/model/socket selection and the source/muzzle vector before constructing the projectile (paths around0x6502ae–0x650420). This establishes it as the source creature rather than the victim. The second ID is subsequently passed into SetDesiredTargetObject0x6d42d0 (e.g.0x650761/0x6507e0), establishing its target role. That setter resolves a client object and eventually stores the supplied ID at projectile+0x124; failed resolution writes an invalid-ID sentinel instead. Target setup happens AFTER LoadModel. A branch stores the first decoded ID at projectile+0x1c4 around0x6507b1, but it is branch-specific and also AFTER load: it is not a universal shooter field.

At LoadModel entry, prior to its own prologue, original ESP=S-16. Therefore the saved decoded source and target are at entryESP+0x9c and entryESP+0x24 respectively, ONLY for return address0x650554 in this verified receiver/callsite. Stack slots+4/+8/+12 are the normal three loader arguments. These are caller-frame relationships, not persistent object fields. Any hook helper must capture them using a verified assembly boundary/original-SP contract before its own prologue, and validate the callsite; a generic C++ local-stack guess is not acceptable.

The cleanest ownership capture is this specific receiver load callsite, retaining EDI/source ID and second decoded target ID, not a global replacement of every LoadModel call. A generic loader detour must fail closed for other callers and preserve original behavior. Source ID is client-space: compare it to the freshly resolved current PC's client ID using the existing verified server-to-client resolver. Never compare directly with a server NWScript object ID, cache the source raw pointer for later callbacks, or substitute NPC/spell projectiles accidentally.

## Ordering before scene attachment

After successful model load, receiver configures projectile position at0x65063f through slot+0x8c, orientation, timer and animation, then target/behavior and SetProjectileType0x6d6ee0 at0x6509cc. Only later does it call slot+0x94 at0x6509f4; independently read vtable proves that slot is AttachToScene0x63d820. Thus substitution at this load boundary precedes this receiver path's explicit scene attachment and positional/behavior finalization.

This is strong static support for replacement before the first displayed projectile. It is not live proof that no constructor/loader side path can expose a transient stock frame; first-render acceptance still requires a real capture. Preserve original position, orientation, attack outcome, timer and behavior setup. Do not change projectile type merely to select a different mesh.

## Bounded implementation brief

1. Bind only this image/architecture, verify loaded executable identity, projectile vtable and receiver callsite/loader guard windows against private authoritative bytes. Preserve relocatable absolute-address handling in guard checks. Do not publish bulk disassembly or proprietary instruction payloads as browser assets.
2. Add a native typed scoped hook at the validated receiver load boundary. Capture source client ID, target client ID, original CResRef, flags and the transient projectile identity. Consult an immutable validated console configuration snapshot on the owning thread. Unknown source/build/type/config leaves stock arguments untouched.
3. For current-PC blaster candidates, pass an engine-compatible selected local model CResRef to the original LoadModel and preserve both flags and EAX result. Preflight resource existence/type. Existing failure path destroys the newly constructed projectile on loader failure; do not claim automatic fallback unless retry/partial-wrapper cleanup is independently verified. Avoid manually unloading a possibly half-created wrapper.
4. Emit bounded structured diagnostic metadata (configuration version, source/target IDs, original/selected resource, successful load, transient projectile token). No Lua invocation or blocking resource scan inside the native hook. Console configuration updates remain in the existing engine-owned service.
5. First prove observed receiver coverage on stock firing, then replace one validated model. Test NPC exclusion, misses and both hands before claiming all-PC-blaster support. Preserve lifecycle and damage authority unchanged.

## Still unresolved

- Mapping decoded ammunition/model-table and other discriminator fields to specific blaster classes, both hands, burst count and hit/miss/deflection. The first receiver ID/source-role and second target-role are proved; full per-bolt attack identity is not.
- Whether every requested PC blaster visual traverses this receiver once per bolt. A single receiver invocation is not assumed to represent a combat round or every repeated visual.
- Selected footlocker model compatibility with CSWCAnimBaseProjectile model/animation assumptions; no retail model name was guessed or asset read in this pass.
- Safe scale/orientation/tumbling configuration of arbitrary projectile meshes after load, and fallback cleanup if substitution loading fails.
- Hit-authoritative knockback dispatch and target root/bone physics remain separate. This load hook does not establish ragdoll/tumbling or safe stronger force push.
- Exact production hook stub/trampoline stack preservation, reentrancy and exceptions need implementation review and synthetic ABI tests. Original loader uses SEH; preserve its call/cleanup semantics and all required nonvolatile registers.

## Private extraction files

Controller inputs: `/home/brunner56/kp-live-20260922/projectile-research/load-model.asm`, `receiver.asm`, `initial-byte-observations.md`.
Additional private objdump excerpts:
- `/tmp/kp-projectile-constructor.asm` SHA256159181e13f067f983988189a8c6ade864ebceff71952031460c7ae4d001f8b20
- `/tmp/kp-projectile-wrapper.asm` SHA256a4ee9b2865fa75377d2971d40c1efac11476b25d4c0fe786cf6d321b59c4c6f7
- `/tmp/kp-projectile-target.asm` SHA2565f01e798dec071d3fb46faf0cd5b924404802080d2e47a6a07004db9fc1eb0dc
- `/tmp/kp-projectile-target-tail.asm` SHA2567c885f7a480221aefe966b05971f220bfeabed14fa7bf6c9a6b17d815e99e5f1
- `/tmp/kp-projectile-resref.asm` SHA256b24e57f2f38fabeb4c1282008200717d182ae5699d3576477cfde4d27aa2ec52

The summary records mechanics and provenance; raw bytes remain private. No callable Mac projectile contract or live firing result is claimed.

# Checked native actor scale

`kp.model` changes an actor's actual rendered model scale through the engine's
child-propagating Gob setter. It does not use a disguise or write raw scale fields.
NWScript remains a separate bridge for scene setup. The module does not call it.

```lua
local available = kp.model.capabilities()
assert(available.available, available.abi)
local original = assert(kp.model.snapshot(nwscript.call('GetFirstPC')))
local enlarged = assert(kp.model.resize(original, 2.0))
assert(math.abs(enlarged.base - 2.0) < 0.001)
local restored = assert(kp.model.restore(original))
assert(math.abs(restored.base - original.base) < 0.001)
```

`snapshot(server_id)` returns a protected native capture with read-only `id`,
`base`, `effective`, `creature` and `model` fields. The last two are diagnostic
hexadecimal identities, not script-writable addresses. `resize(capture, base)`
and `restore(capture)` return a new readback capture on success or `nil, reason`
on operational failure. Retain the **original** capture for restoration; the
result from resize describes the newly scaled state. Invalid capture types raise
an argument error. Allocation length and module magic are checked independently
of the Lua metatable, including when the debug library is available.

Requested base scale must be finite and in `[0.125,4]`. Effective scale is read
separately; the setter preserves its ratio to base scale and propagates to child
models. Restoration uses the captured original base, not an assumed1.0. Each
mutation is followed by a new resolution and base/effective readback, and logs
object/model identity, requested value, before/after values, setter result and
verification result. A failed setter/readback can mean a mutation occurred;
callers must attempt restoration and retain failure evidence.

Every access re-resolves the manager/client, invokes the engine's
ServerToClientObjectId, invokes its typed creature wrapper, and gets the current
model with selector0xff and force-update0. Null/unreadable roots, absent animation,
wrong creature type, absent model guard, unsupported setter vtable, invalid scale,
code-guard drift and changed capture identity refuse the operation. Capture
identity includes the binding epoch, client ID/pointer, creature and model.
No generation counter has been recovered: reuse of all these same addresses in
one binding cannot be detected. Do not retain captures across module/save loads;
scene orchestration also checks module/area context before cleanup.

The checked core is shared across four exact-image profiles:

| Profile | Calling adapter | Runtime availability |
|---|---|---|
| K1 Mac i386 | Darwin stack-this cdecl | Adapter source implemented; Darwin loader absent, no live proof |
| K2 Mac i386 | Darwin stack-this cdecl | Adapter source implemented; Darwin loader absent, no live proof |
| K2 Mac x86-64 | Darwin SysV, RDI=this/ESI=id or Boolean/XMM0=float | Adapter source implemented; Darwin loader absent, no live proof |
| K1 Windows GOG | i386 ECX-this, callee stack cleanup | Bound by existing runtime only for the verified original image |

Addresses, exact SHA256 identities and recovered field layouts are documented in
[the corpus research](research/mac-model-memory.md). Each profile additionally
contains16original bytes at the conversion, typed lookup, getter and setter
entries, extracted from those exact original PE/Mach-O images. Binding checks
identity, OS/ABI, width, loaded base/slide and all four code guards. Operations
recheck the guards. Windows uses setter slot0xcc, Mac i3860xd0 and Mac x64 0x1a0.
Unsupported vtable implementations are refused even on a known image.

The explicit C++ `bind_native` seam accepts a **previously verified executable
SHA**, loaded image base, fallible memory reader and required mutation logger.
The current Windows/Linux runtime supplies its image loader's verified identity.
An eventual Darwin loader must supply its independently verified identity and
slide plus a Darwin-safe reader; compiling the adapter alone does not provide
injection, startup, hooks, protection handling or a complete Mac runtime.
Linux cannot activate a Darwin adapter merely because pointer width matches.
Calls belong on the existing engine script thread, not arbitrary worker threads.

Offline `kp_modeltest` exercises actual checked operations and the Lua binding
against a controlled memory/engine backend for all four layouts. It checks exact
identity/width/ABI/code refusal, nonidentity ID conversion, readable spans, stale
captures, replaced models, scale rejection, actual setter-call routing, ratio
readback, restoration, mismatches and forged userdata. These tests establish the
core contract, not the machine ABI in a real Mac process. The MinGW DLL build
checks the Windows calling adapter compiles. Mac adapter code has not been built
with a Darwin toolchain or run on Mac.

Position/orientation remain outside this API. Corpus evidence shows coupled
server/client transforms and dirty/area-update behavior; a later motion slice
needs a verified shared resolver/setter path and interaction at the destination.
Raw XYZ writes are not a substitute.

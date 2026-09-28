# Mac model memory evidence

The intended public Lua surface uses native, named operations with build-specific backends. NWScript remains an explicit bridge for scene setup. Harness TOML owns execution and recording, not memory layouts. The linked [Phasor catalogue](https://pastebin.com/z4eqrjVN) motivates named typed fields; its Halo offsets are not KOTOR evidence.

These findings were checked against the local original Mach-O images on 2026-09-22. They establish field accesses and call candidates, not live Mac compatibility. The existing runtime currently builds 32-bit Windows/Linux libraries and has no complete Darwin runtime adapter.

| Identity | Corpus binary ID | Original image SHA-256 | Preferred `__TEXT` address |
|---|---:|---|---|
| K1 Mac i386 | 5 | `aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032` | `0x1000` |
| K2 Mac i386 | 19 (84 duplicate) | `f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d` | `0x1000` |
| K2 Mac x86-64 KOTOR2sub | 83 | `469067c416f1a3ff391df73c7ace2d44a8d0a246253e8ad5752f6413ea033be4` | `0x100000000` |

Catalog: `/home/brunner56/agentdecompile-nvme/corpus-work/corpus.sqlite`. K1/K2 i386 originals are the corresponding `artifacts/raw_image` under `/home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_mac_swkotor.app/` and `TSL__k2_mac_swkotor2.app/`. K2 x86-64 is the `KOTOR2sub.x86_64` slice under AgentDecompile `target/imports/2026-09-08-nwn-kotor/slices/1c536c3ef2e8bed348b38934b381e3dc427f3ebee21faddfbd7524fbb2388d77/`. Launcher images KOTOR2 are different executables.

All function addresses below are preferred virtual addresses. Add the verified loaded-image slide to obtain runtime addresses; they are not file offsets. An RVA relative to `__TEXT` subtracts the preferred address above.

| Scale operation or field | K1 i386 | K2 i386 | K2 x86-64 |
|---|---:|---:|---:|
| Gob scale setter | `0x328524` | `0xb0324` | `0x1000a4a98` |
| Scene scale setter | `0x352bdc` | `0xc9e14` | `0x1000bc954` |
| Scene scale getter | `0x352c2a` | `0xc9e68` | `0x1000bc990` |
| Effective float scale | `+0x1b4` | `+0x1e0` | `+0x264` |
| Base float scale | `+0x1b8` | `+0x1e4` | `+0x268` |
| Child array pointer | `+0x1bc` | `+0x1e8` | `+0x270` |
| Child count (u32) | `+0x1c0` | `+0x1ec` | `+0x278` |
| Model-present guard | `+0x58` | `+0x84` | `+0x98` |
| Scale virtual slot, byte offset | `+0xd0` | `+0xd0` | `+0x1a0` |

The setter preserves the effective/base ratio when setting base scale, and recursively propagates effective scale through child models. A raw write to effective scale is not equivalent. i386 uses stack arguments, including `this`, despite the decompiler's `__thiscall` label; do not use Windows ECX-this ABI. The x86-64 Scene wrapper receives object in RSI and scale in XMM0, moves object to RDI, sets ESI to true and tailcalls the virtual slot. The getter returns float through x87 on i386 and XMM0 on x86-64.

Sources: K1 `source/asm/libsource/AURORA/aurmodel.cpp.S:471` and `aurscene.cpp.S:165`; K2 i386 `analysis/ghidra_cexport/TSL__k2_mac_swkotor2.app.c:122015` and `:141450`; x86-64 original bytes at the recorded VAs. Named Ghidra Gob/Scene/Model/client object structs are one-byte, zero-field placeholders. Their names do not establish layout confidence.

| Resolution component | K1 i386 | K2 i386 | K2 x86-64 |
|---|---:|---:|---:|
| `_g_pAppManager` global slot | `0x481190` | `0x5edcb8` | `0x1005d18a0` |
| Client GetGameObject | `0x1e56a` | `0x1c02dc` | `0x1001a3366` |
| Client to internal pointer | `+4` | `+4` | `+8` |
| Internal to object-array pointer | `+0x14` | `+0x14` | `+0x28` |
| Creature to animation pointer | `+0x68` | `+0x68` | `+0x80` |
| Base animation to model | `+0xb8` | `+0xb8` | `+0xc0` |
| Creature GetModel | `0x73134` | `0x28693e` | `0x10026097e` |
| Base animation GetModel | `0x58048` | `0x21efec` | `0x1001fde02` |

The base animation getter accepts selector `0xff`. Prefer virtual engine getters because subclasses and appearance changes can replace the model. Manager-to-client offsets are independently evidenced for K1/K2 i386 (`+4`) and K2 x86-64 (`+8`). Re-resolve IDs and current model identity on every operation. Never restore captured data into a replacement object/model after a reload, appearance change or destruction.

| Transform operation | K1 i386 | K2 i386 | K2 x86-64 |
|---|---:|---:|---:|
| Server SetPosition | `0x25dfa0` | `0x3dfabe` | `0x1003ae1dc` |
| Server SetOrientation | `0x25df74` | `0x3dfb3c` | `0x1003ae27c` |
| Client SetPosition | `0xc218c` | `0x22cbf0` | `0x10020b75e` |

K2 i386 server position is a three-float vector at `+0x94`; its setter marks dirty bit 2 at `+0x224` and can update the area's position array. Orientation at `+0xa0` marks dirty bit 4. Client position at `+0x24` has separate animation/fade propagation. These are vectors, not degree-valued facing. Reliable placeable motion requires server/client agreement and interaction at the destination, followed by restoration. Raw XYZ writes alone do not prove that behavior.

The first acceptance scenes should use bounded positive scale changes with unchanged appearance, and a disposable placeable moved a short distance and used at its destination. More elaborate choreography builds on those verified operations. Unknown builds, absent models, unsupported ABI, stale identities and incomplete backends must report unsupported/failure before mutation. Live Mac footage remains required.


## Complete actor scale resolution

Incoming Lua/NW object IDs belong to the server ID space. The demonstrated engine path calls `ServerToClientObjectId` before client lookup; no inferred bitwise replacement is justified.

| Site | K1 Mac i386 | K2 Mac i386 | K2 Mac x86-64 | K1 Windows GOG |
|---|---:|---:|---:|---:|
| Manager global | `0x481190` | `0x5edcb8` | `0x1005d18a0` | `0x7a39fc` |
| Manager client pointer | `+4` | `+4` | `+8` | `+4` |
| Server-to-client ID wrapper | `0x1eac0` | `0x1c0ade` | `0x1001a37d8` | `0x5eda50` |
| Typed creature wrapper | `0x1e5a0` | `0x1c0350` | `0x1001a33ae` | `0x5ed5b0` |
| Creature model getter | `0x73134` | `0x28693e` | `0x10026097e` | `0x6179c0` |

Windows original PE SHA-256 is `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`, preferred base `0x400000`. Original bytes are under `K1__k1_win_gog_swkotor.exe/artifacts/raw_image` beside the Mac corpus originals. Windows calls use ECX-this; the scale setter returns a Boolean in AL and pops eight stack bytes. Its scale virtual slot is `+0xcc`, not Mac's `+0xd0`. Concrete setter `0x444d90`, Scene setter `0x44fcf0`, getter `0x44fd40`; effective/base/guard fields match K1 Mac (`+0x1b4/+0x1b8/+0x58`). These Windows sites were independently checked against original bytes, upgrading earlier catalog mapping candidates to instruction evidence.

The typed creature wrappers preserve engine lookup semantics: object-array status zero means success, then a non-null and creature type check, then virtual base-to-creature conversion. On Windows type byte `+8` is 5 and conversion slot `+0x2c`; Mac i386 uses type byte `+8` and slot `+0x30`; Mac x86-64 uses type byte `+0x10` and slot `+0x60`. Use the wrapper rather than reimplementing the bucket table. The x86-64 ID domain is still 32-bit despite register width. Each model getter takes selector `0xff` and force-update zero. These sites support a native operation adapter; they do not establish a complete Mac loader or live execution.

# Native projectile observation and visual-selection slice

## Scope and implementation

New independent `kp.projectiles` module exposes observe/configure/status/records/disable through the existing Lua registration and engine command pump. The runtime binds only the verified Windows K1 GOG image. Native APIs are distinct from the explicit NWScript bridge. No harness dependency, extra scheduler, browser surface, game assets or alternate interpreter were added.

The exact image's projectile vtable LoadModel slot is guarded and atomically redirected to an explicit naked i386 entry. It captures original ESP before any C++ prologue, preserves EFLAGS and registers, delegates to an aligned C++ dispatcher, places the original loader's result into saved EAX and returns with the proved 12-byte cleanup. The original function itself remains unmodified, including its SEH prologue and model-wrapper lifetime. A vtable data-pointer exchange avoids overwriting an executing instruction. Uninstall requires existing runtime quiescence; if page protection prevents restoration, the binding is retained disabled so a still-callable hook is not orphaned.

Only return address 0x650554 in the verified receiver authorizes caller-frame source/target/ammunition decoding. Other callers keep their original arguments. Original ESP+0x9c/+0x24 holds source/target client IDs, +0x21/+0x22 the ammunition row/model variant. No C++ local-stack guesses are used. Source identity is freshly resolved from native GetPlayerCreatureId and server-to-client conversion, with a live client-creature type check. No cached actor pointer or Lua call occurs in the hook.

Configuration uses native CResRef construction, engine CExoResMan::Exists for MDL2002/MDX3008, and native C2DA string lookup/destruction on the loaded ammunition table. The five supported row labels and two variants derive from independently inspected local ammunition resources and the receiver's actual Model%d lookup. Installed model values are read before publishing configuration; load-time row/variant/resource must match. A changed table or unclassified projectile stays stock. A copied immutable configuration owns the chosen 16-byte ResRef for each synchronous original loader call. Failed loading is returned unchanged, with no unsafe fallback retry or manual wrapper destruction.

Fixed 128-record retention includes epoch, config version, IDs, row/variant, original/selected resource, replacement decision, original result and exclusion reason. Sequence tokens identify load observations, never persistent object pointers or impacts. Counters are bounded by the ring retention with explicit dropped records. Configuration/version changes do not mutate in-flight engine-owned models. Resource scans run only in configuration, not inside the hook.

## Evidence and guard provenance

Supplied contract: adjacent `projectile-hook-contract.md`. Additional exact-original-PE inspections and guards: private `/home/brunner56/kp-live-20260922/projectile-research/native-prerequisites.md` and `.json`. These verify resource Exists ABI and manager global, CResRef constructor/copy, CExoString constructor/destructor, C2DA row/column/output API, ammunition table ownership, receiver row/variant capture and fresh-PC native path. Function identities were corroborated with corpus binary8, then checked against original executable bytes. Relocated absolute SEH address bytes are adjusted to the loaded image base. No corpus or game assets were modified.

## Validation and remaining gate

The focused test uses the same actual naked entry in a native i386 executable. A synthetic caller verifies original ESP, source/target slots, this pointer, two flags, original resource, exactly one original call, EAX, EFLAGS carry, nonvolatile registers and final stack cleanup. Service tests cover disabled stock behavior, observation, valid/invalid configuration, fresh-PC switching, exclusion by row/variant/table, failed original load without retry, changing configuration during a load, disable, ring eviction and epoch reset. Actual Lua exercises the same module registration and nil/error/status contract. Assertions remain enabled even in Release builds.

Native32 runtime and MinGW DLL built; projectile, Console and pinned-ImGui tests passed 3/3 before final formatting. Final build/frozen hash recorded below when complete. No game was launched by this agent, and no index operations were performed for this slice. Controller owns stock observation first, native model compatibility, NPC exclusion, visible flight and cleanup acceptance. Independent review is required before acceptance.

Impact authority, knockback, tumbling/ragdoll, arbitrary-model compatibility and all-blaster coverage remain explicitly incomplete. This slice is not advertised as the completed footlocker example. See `docs/projectiles.md` for exact API and limitations.

## Frozen review candidate

Final native32 runtime and MinGW DLL build passed (`/tmp/kp-projectiles-final-build.log`). Final projectile/Console/pinned-ImGui CTest passed 3/3 in 0.07 seconds (`/tmp/kp-projectiles-final-tests.log`). Frozen DLL: `/home/brunner56/kp-validation-20260922-build/kphasor-projectile-visual1.dll`. SHA256 `699bfe4b276656a1d5ae56a32292dcd04c08f9ee49216eff2aca6b4274389f6e`. This candidate is immutable during controller-owned review/live work. No live acceptance is claimed here.

## Independent review fix: transactional vtable ownership

Initial review identified P2 installation/removal bookkeeping defects: a guard followed by unconditional exchange could overwrite a changed slot, and unchecked protection restoration could falsely report success or forget cleanup state. Added a shared `SlotPatch` transaction with injected slot/protection operations, used directly by the Windows adapter. Installation uses CAS against the verified original pointer. Removal uses CAS only while this transaction owns the slot, distinguishes an already changed owner, and never overwrites the foreign value. The original protection token survives every retry; neither install nor removal reports success until protection restoration succeeds. Failed exchanges guarantee no write. Failed cleanup retains the transaction, and the callable backend remains suspended in stock mode with explicit unsupported status/reason; configuration/observation cannot reactivate it. A subsequent quiescent cleanup retries the retained state.

Fault-injection tests cover write-protection failure, exchange failure, installation race, installation protection-restore failure, cleanup protection/exchange/restore failures, changed removal owner, retry after the original pointer has already been restored, and a race combined with protection failure. Assertions verify pointer values, original protection, retained ownership, and that retries do not issue writes against unowned slots. A service test proves suspended-but-callable state executes the original stock loader and rejects configure/observe.

The char* CExoString constructor evidence requested during review is appended to private native-prerequisites.md: corpus signature and independent original PE instructions agree on thiscall+one argument, engine allocation/copy, and ret4. No loader/flight/impact semantics changed in this fix.

### Transaction-fix frozen candidate

Native32 and MinGW final builds passed; ABI/service/Lua projectile, Console and pinned-ImGui tests passed 3/3 in 0.11 seconds. Receipts are `/home/brunner56/kp-validation-20260922-build/projectile-patch-final-build.log` and `projectile-patch-final-tests.log`. Frozen DLL `/home/brunner56/kp-validation-20260922-build/kphasor-projectile-visual2.dll` has SHA256 `165f00008e8633173127de990668f6f93906e461fe96c94833f47a45fff55b9c`. This supersedes visual1 for review/live acceptance; visual1 is preserved unchanged. Independent rereview requested; no game/index actions performed.

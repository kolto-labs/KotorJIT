# Task 5 implementation report

Base: 413d510. A separate documentation commit, 21ebd33, corrects the stale
12 FPS overview to the new 60 FPS default.

No games, Wine sessions, stage modifications, live-driver writes, subagents,
pushes or PRs were performed. The controller owns live proof.

## Native implementation

The new native namespace is `kp.model`, with capabilities, snapshot, resize and
restore. Captures expose read-only ID, base/effective scales and diagnostic
creature/model identities. Allocation size, full-userdata type and module magic
are validated independently of the metatable. Real Lua tests cover forged short
userdata and same-sized userdata with invalid magic. Native model code does not
call the NWScript bridge.

The checked core binds four exact SHA profiles with loaded image base/slide,
pointer width, explicit OS/ABI and sixteen original code bytes at each of four
function entries. The runtime supplies its already-verified executable identity.
Every access rechecks these guards and freshly resolves manager, client and
internal array. It calls the real ServerToClientObjectId, typed creature wrapper
and GetModel with selector 0xff and force-update 0. Type, readability, animation,
model guard and verified scale-setter vtable checks precede mutation.

Resize invokes the child-propagating engine Gob setter, not a raw field write.
It resolves again and verifies identity, base scale and effective/base ratio.
Logs include identity, before/request/after values and verification result.
Restore uses the captured original base. A setter/readback failure stays an error
even if mutation occurred; callers must attempt restoration. Captures include
binding epoch, client ID/pointer, creature and model. Exact same-address reuse
remains undetectable without an engine generation counter.

Explicit adapters implement Windows i386 ECX-this, Darwin i386 stack-this and
Darwin x64 SysV calling conventions. They are gated by OS and architecture. The
Darwin binding seam requires a verified loader identity/slide and fallible reader.
There is no complete Darwin loader/runtime, so Mac live compatibility is not
claimed. Linux cannot activate a Mac adapter because pointer width matches.
Position/orientation are deferred pending verified server/client coupling and an
interaction-at-destination test.

## Authored scenes and routes

Three Lua files under scripts/demos/model-memory provide a reusable state machine
and two finite scenes, outside the original 41-example inventory:

- Player scale cycles 0.35 / 2.4 / 1.0 twice.
- Three owned, command-disabled, friendly humanoids alternate 0.4 / 2.0 / 1.0.

Each phase lasts 90 tick callbacks; restored original scale is held for another
90 ticks. The first visible phase starts on the first ready-model tick after an
explicit trigger. Newly spawned models have a bounded readiness window. The wave
uses facing-relative forward/perpendicular placement with no central actor.
Friendly faction 2 was independently confirmed by the controller in installed
nwscript and in its live GPU prototype. Scripts also read back the faction and
require peaceful gameplay throughout.

Independent native snapshots verify every resize and restore. Completion is
published only after original scale readback and, for the wave, observed removal
of owned actors. Cleanup checks module filename and area before writes/deletion.
Where captures exist, it checks fresh creature/model identities before deletion.
Context changes and replacement actors cause refusal, not deletion. Such refusal
can leave owned actors for diagnosis. Startup before VM binding is retried.

Two existing-dialect TOML routes contain 17 player / 18 wave steps: checkpoint and
peaceful setup, native capability check, original player and area ID capture,
trigger, independent sampling of six phases, final restoration, wave removal and
preservation of existing IDs, plus exact phase/completion log counts. The wave
also checks effective/base ratio continuity independently. These are prepared
routes, not live-pass receipts.

Documentation describes 60 FPS, 1024x768 capture and first-phase markers. Full
video remains evidence; representative MP4 is an initial edit candidate and GIF
is an 8 FPS preview. Actual game cadence and compelling framing require review.

## Original-byte provenance

The exact PE/Mach-O originals named in docs/research/mac-model-memory.md were
read and hashed. Preferred VAs were mapped through PE sections or Mach-O
LC_SEGMENT/LC_SEGMENT_64 commands, then sixteen bytes were extracted at conversion,
typed lookup, getter and setter entries. The literals are in model_profiles.cpp.

- K1 Mac32: aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032
- K2 Mac32: f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d
- K2 Mac64: 469067c416f1a3ff391df73c7ace2d44a8d0a246253e8ad5752f6413ea033be4
- Win K1 GOG: 9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435

The controller independently confirmed Windows internal array offset +0x14 from
original typed lookup 0x5f1180. No Mac-offset extrapolation was needed.

## Validation commands and results

- `cmake -S . -B /home/brunner56/kp-validation-20260922-build -DPython3_EXECUTABLE=/usr/bin/python3`
- `cmake --build /home/brunner56/kp-validation-20260922-build --target kp_modeltest kphasor_dll -j2`
  Passed: native 32-bit runtime/core/Lua executable and MinGW Windows DLL.
  No compiler warnings/errors. Logs: /tmp/kp-model-cmake.log and /tmp/kp-model-build.log.
- `ctest --test-dir /home/brunner56/kp-validation-20260922-build --output-on-failure`
  Passed 21/21 in 84.24 seconds. Log: /tmp/kp-model-ctest.log.
- Focused native, scene and example gates passed 3/3. After additional native
  null/NaN cases, kp_modeltest was rebuilt and the two model gates passed again.
- `luajit tools/model_scene_test.lua scripts/demos/model-memory`
  Passed 12 actual authored-script cases: success, mutation failure, independent
  readback failure, restore failure, unload, module transition and replaced actor.
  Each case also checks startup before the VM binds.
- Native tests exercise all four layouts: wrong identity/width/ABI/slide/code,
  invalid IDs, null actors/models/arrays, unreadable scale, wrong type, absent
  animation, wrong vtable, NaN/Inf/range, setter routing, readback/restoration,
  false setter return, replacement before/after mutation, stale epoch, and forged
  Lua userdata. Controlled nonidentity ID conversion proves the conversion call
  cannot be skipped.
- Both TOML files parsed with actual Scenario.load; marker regexes matched samples.
- Host GCC syntax checks passed for both Darwin conditional branches:
  `g++ -std=c++20 -m32/-m64 -D__APPLE__ -Isrc -Wall -Wextra -fsyntax-only src/api/model_backend.cpp`
  This is host conditional-compilation coverage, not a Darwin toolchain or ABI test.
- `git diff --check` passed. Original 41-example manifest is unchanged.

## Files and self-review limits

New src/api/model header, core, profiles, backend, Lua binding and CMake fragment;
tools/kp_modeltest.cpp and model_scene_test.lua; docs/model-memory-api.md; three
demo Lua files, their README and two routes. Only necessary runtime registration,
binding/unbinding and build glue were modified. Controller research docs remain
untouched.

There is no worker-produced live Mac or Windows model proof. The controller must
run current source/runtime hashes, retain state readbacks and full media, and
review real geometry, child model scaling, restoration and presentation. Fake
backend tests cannot establish engine ABI correctness. No motion API is included.
Same-address reuse and external concurrent memory writers are not excluded by
captures. Calls belong on the existing engine script thread. Scene cleanup may
refuse to remove an actor when identity is uncertain; this is recorded as failure.
Checkpoint validity, framing and route timing remain live acceptance items.

## Fix round 1: actual PC resolution and independent review

Reviewed /tmp/kp-task5-review.md and the controller's actual run
/home/brunner56/kp-live-20260922/stage-k1/runs/20260922-111932/report.json.
That run reached peaceful gameplay with valid PC ID 2147483647 (0x7fffffff),
then the first snapshot failed before any mutation.

Original PE disassembly shows wrapper 0x5eda50 tailcalls 0x5f2ac0. The complete
27-byte conversion leaf compares only 0x7f000000 as OBJECT_INVALID and otherwise
ORs the high bit. The live PC therefore legitimately converts to 0xffffffff.
The core incorrectly treated this as an additional sentinel. Removed that
rejection for incoming/converted IDs while retaining the real engine conversion
and typed lookup; no replacement bit formula was added to production.

The new offline regression executes the original bounded conversion leaf in an
owned W^X test mapping (no engine reads or calls), checks sentinel, ordinary and
special PC inputs, then uses its results in actual core snapshot/resize/restore.
Compiled against the old HEAD core, this test fails at line 101 PC snapshot;
against the fixed core it passes. This is engine-byte semantic evidence, not a
live game or complete calling-chain proof.

The cleanup P1 is fixed by retaining successful per-actor captures across model
readiness ticks and requiring a retained native identity before every deletion.
Known identities are never replaced with later samples. Missing ownership evidence
refuses deletion and retains the actor with a cleanup error. Added missing-first,
missing-last, partial-model, complete-unavailable, readiness-timeout, partial-spawn
and setup-failure cases, including replacement IDs before unload.

The peaceful-scene P2 is fixed by checking each actor's validity, area and combat
status on every active tick. A transient NPC combat period between phases now
aborts and attempts guarded cleanup. This establishes only tick-level checks.

Controller presentation steering also changed the wave's authored formation to
six metres forward with side offsets -2, 0, 2. Framing still needs live review;
there are no flashes, VFX, or animation-injection claims.

Validation:
- Native model test and MinGW DLL rebuilt with -j2; log /tmp/kp-model-fix-build.log.
- Actual Lua scene suite: 20 cases passed.
- Focused CTest model/core/example gates: 3/3 passed.
- Old-core reproduction /tmp/kp-model-before-sentinel-test: expected failure at
  PC snapshot; fixed kp_modeltest passed.
- git diff --check passed; original example inventory/manifest unchanged.
- Fixed DLL SHA256: 463e1ab0e7f223854dbe2a234e8488b539d9c074d12e04c806acf90770d26d0e.

No worker game launches. The controller has the stable runtime/source snapshot
for serial outdoor live testing; no success is inferred before its new receipt.
The first-ever identity capture cannot identify an object that was already
replaced before any native identity was observed. Captured replacements and all
cleanup lacking an established identity are refused; same-address reuse remains
the documented engine-generation limitation.

## Fix round 2: establish ownership before model readiness

Read /tmp/kp-task5-rereview.md. The remaining P1 was real: an initially unreadable
model could become readable only after its ID referred to a replacement, which
the first model capture then adopted. Retaining partial model captures did not
solve ownership for the actor that had never produced a model.

Added native `kp.model.identify(id)` and `kp.model.matches(ownership)`. Identity
capture is separate from animation/model readiness. On Windows it uses the
existing harness's verified server GetGameObject chain: manager server pointer
+8, server internal pointer +4, internal object array +0x1005c, wrapper0x4ae750
(tailcall0x4b1700), returned ID+4 and creature type+8. The original PE was inspected
with bounded objdump ranges; the wrapper's sixteen original bytes are a fifth
code guard in the Windows profile. No NWScript aliases or calls were introduced.

Mac profiles use the already-verified client typed creature path without requesting
its animation/model. If that initial client identity is absent, identify refuses;
there is no guessed Mac server fallback or later identity adoption. Full Mac
server identity recovery remains a future extension, not a claimed capability.

`snapshot(id, ownership)` validates the retained identity before adopting a model
and embeds it in the capture. Resize and restore then revalidate it automatically.
Ownership tokens have separate native userdata type, exact allocation length and
magic checks. The optional argument preserves existing player snapshot behavior.

The wave captures ownership immediately after CreateObject returns, before its
setup calls and before any model wait. Every later active tick checks that owner.
Cleanup requires that same owner and additionally checks any model capture already
obtained. An unchanged owned actor can safely warm up or be deleted after a setup
failure even without a model; a replacement or missing initial owner is never
adopted. The original same-address/generation limitation remains explicit.

Regression evidence:
- New actual-scene test allows a model to warm up on ticks1–4, replaces the server
  actor on tick5, then makes the model available. It asserts no resize/deletion of
  the replacement and no completion. The current scene passes.
- The same targeted test with HEAD's previous model_scene.lua fails at line91:
  `partial/error scene published completion` (expected red reproduction).
- Separate positive case proves legitimate model warmup still completes.
- Missing initial identity refuses adoption and deletion.
- Full authored-scene suite passes23 cases, including all earlier failures.
- Native ownership tests cover all four profiles with absent animation, identity
  capture/matching, attached snapshot, replacement refusal before resize/restore,
  changed server-code guard, wrong returned server ID/type and forged ownership
  userdata. Native/core tests pass.
- Native and Windows targets rebuilt with -j2. Focused model/core/example CTest
  gates pass3/3; after final additional native negatives, model gates pass2/2.
- Logs: /tmp/kp-model-ownership-build.log, /tmp/kp-model-ownership-win-build.log,
  /tmp/kp-model-ownership-final-tests.log. Diff checks clean.
- Frozen DLL SHA256: 1e69620ade0bd40eb811426d5cf52d4b9da2e41008c2288d2b2a4f7acc8d120a.

No worker game launch. Controller notified when source/runtime bytes froze for
its one owned outdoor wave run. This report does not infer that live result or
visual acceptance from passing host tests. Player scene source is unchanged;
shared helper uses ownership only for its spawned actors.

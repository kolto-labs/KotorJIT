# Console-configurable object blasters

User request: all the PC's blasters shoot an object chosen by the player and changeable through the console during play; footlockers are the initial gag, with substantial knockback and enemies tumbling/ragdolling. This is a high-priority replacement for weak examples, after the current input-reliability fix.

## Observable acceptance

- An ordinary player blaster fires a recognisable footlocker from its firing origin along the shot's actual flight, including misses. A box spawned beside the player or at the victim on an attacked callback is not equivalent.
- Cover single pistol, dual wield, rifle and multi-shot combat animations. Resolve whether the engine represents one projectile per bolt or attack sequence; instrument this and document supported behavior precisely.
- F12 changes the next newly fired projectile to another valid locally available object/model without restarting/reloading the scene. In-flight projectiles retain their already selected identity; invalid input preserves the prior working selection and reports the reason.
- Targeted scope is the player character's blasters; NPC and party fire remain distinguishable. Character switching/equipment changes must resolve the current player and weapon, rather than retaining a stale pointer.
- Knockback visibly displaces struck enemies away from the impact direction with a readable knockdown/tumble response. Apply it once per appropriate hit, not every visual burst callback. A miss must not knock back the aimed-at target. Derive displacement and hit timing independently from the demo's own counters.
- Preserve actual engine damage/accuracy semantics unless an explicit separately documented control changes them. Track native lifetime and cancellation across load, area change, shutdown, disable and missing targets/models.
- Add genuine articulated ragdoll support if stock behavior lacks it; retain this as an explicit unmet requirement until collision, bone ownership, recovery/death handling and visual evidence exist. Do not relabel Force Push or rigid root rotation as physical ragdoll simulation.
- Use a fixed readable camera, immediately show the launched object and its impact, show a console change and different next shot, retain continuous source recording, and export a smooth short video/GIF only after behavior checks succeed. Verify cleanup and subsequent unmodified blaster fire.

## Architecture constraints

Native capabilities belong in an independently testable kp module using verified image profiles, ownership and bounded native guards. Explicit NWScript setup remains under nwscript.call. Demo configuration and scene state must be separate from engine hooks; harness TOML only orchestrates tests and recording. Reuse the existing runtime command pump and Console result pipeline. No Lua execution on renderer/input threads and no new scheduler solely for this example. Local model/resource access must not cause game assets to enter source or published artifacts.

## Evidence still required before native implementation

Read-only findings from `/tmp/kp-object-blaster-feasibility.md` must distinguish named corpus locators from verified executable bytes and ABI. Verify projectile construction/model loading, attacker ownership, launch position, per-shot/impact correlation, model lifetime and model compatibility. Existing generic OnCreatureAttacked and SafeProjectile events are insufficient evidence of exact bolt semantics. The initial K1 GOG implementation needs reusable variant profiles and explicit unsupported status on unverified K1/K2/Mac images; profile presence is not live platform acceptance.

## Implementation handoff evidence

Verified WinK1 projectile-load boundary and ownership context: `projectile-hook-contract.md` adjacent to this brief (copied from independent `/tmp/kp-projectile-hook-contract.md`). Raw executable/disassembly remains private. The controller read the installed override `placeables.2da`: Footlocker row39 maps to `PLC_FootLker`; wooden crate row25 to `PLC_Crate`. Private receipt `/home/brunner56/kp-live-20260922/projectile-research/local-placeable-models.json` records the installed table hash and parser limitations. These names are locally observed resources, not assets to redistribute. Resource availability and compatibility must still be validated for each install/runtime.

Implement native projectile observation and optional visual replacement as the first executable vertical slice, with actual console configuration and a disabled-by-default stock path. This is a prerequisite to the complete requested example, not completion of impact/tumbling or all-blaster coverage. Reuse exact-build guards and current-PC client identity resolution. Capture receiver callsite context at an explicit assembly boundary; do not read guessed C++ stack offsets. Preserve original loader ABI, flags, all nonvolatile state and stock projectile lifecycle. Review synthetic ABI stack/register tests before live observation/replacement. Keep post-hit impulse/physics as the next coupled implementation stage, retaining the full example acceptance above.

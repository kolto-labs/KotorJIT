# Object blaster Stages 2, 3 and 5: host authoring report

Date: 2026-09-27. Scope: host authoring only. No Wine, game, capture, live-game lock,
`src/**`, `scripts/harness/kpharness/*.py` or existing example was touched. Nothing
was staged or committed.

## Files (all new, untracked)

| File | sha256 |
| --- | --- |
| `scripts/harness/scenarios/object-blaster/observe.toml` (Stage 2, 39 steps) | `b64357e918e179ff56cd0e7963d3e019c57df1c658b707983ca097e2ace1a62a` |
| `scripts/harness/scenarios/object-blaster/replace.toml` (Stage 3, 70 steps) | `cc55271411f95bb84eedd05f281ff949e664a1951623b3bea1e86e1cf5f81752` |
| `scripts/harness/scenarios/object-blaster/knockback.toml` (Stage 5, 53 steps) | `e4e04b6785b6d8e704b09c6ce381aea8de15875d4fef01caeb7f2141f0c3fa62` |
| `scripts/demos/object-blaster/object_blaster.lua` | `2df3467e60fa88741f19cebcfe23bf1a4c85d1ba4acc321b7e4ecea3e07687eb` |
| `tools/tests/examples/object_blaster.lua` | `119cfb3854d845eed6af71cb1b97ffb0423032d77efbb0a0fb821b2713eeacdf` |

## Routes

All three routes share the owned-save prefix and the borrowed-weapon fixture from
`projectile-research/blaster-fixture-baseline.toml`. They add a runtime check, require
a disruptor pistol (base item 16, ammunition row 3), and end with the Stage 1
restoration gate. The frozen DLL (`165f0000…5b9c`, verified with `sha256sum` today)
appears only in the header comment as a declared input: `--build-dir` points at
`frozen-projectile-visual2`, and `session.log` must report `runtime 165f00008e86`.
The TOML schema rejects unknown top-level fields, so the hash cannot be a parsed field.
No retail file is copied.

- **observe.toml (Stage 2).** F12 `observe(true)`, then a harness check that marks
  `observed` and `epoch`. F12 fires, and stock damage is checked. Pass needs at least
  one new record with a nonempty `original`, `load_ok`, `ammo_row == 3` and reason
  `stock_observation`.
  - Every new PC record must be row 3, unreplaced, in the same epoch, and share one
    nonzero `source_client`.
  - An F12 `records()` summary string is kept in the kp.console.v1 receipt.
  - Teardown runs `observe(false)`, and an independent check confirms both flags are off.
- **replace.toml (Stage 3).** F12 `configure{model='PLC_FootLker'}`, and the harness
  marks `version` and `observed`. After firing, every new row-3 record at that version
  must be `selected`, `replaced=true`, `selected=PLC_FootLker` and `load_ok`.
  - `load_ok=false` is an explicit error, never a retry.
  - Then stop, heal the target, and `configure{model='PLC_Crate'}`. The same check runs
    for the crate.
  - Then `disable()`. New row-3 loads must be `stock_observation`, `replaced=false` and
    `selected==original`.
  - Screenshots are for visual review only. The route does not assert the muzzle frame.
- **knockback.toml (Stage 5), labelled "engine force-push, interim".** It needs the demo
  deployed to `kotorphasor/scripts`.
  - The route waits for demo state 4, then writes request 1 and waits for state 1 and
    the footlocker selection. It marks the target and PC positions, then fires.
  - Pass: displacement projected on the PC→target line is at least 2.0 m. The demo
    counters must stay equal (locals 7 == 8, or it errors).
  - The log must show `push n=1 event=1` exactly once, with zero mismatched push lines
    and zero ignored, teardown-problem or failure lines.
  - A 180-tick quiet window must leave counters, HP and position unchanged.
  - Teardown: request 3 must give state 3, with selection and observation off.
  - After a heal, stock damage after teardown must give no new push, no new projectile
    record, and less than 0.5 m of movement.
  - The route and the demo header both say it: this is not tumbling or ragdoll, and it
    is not arrival-timed.

## Demo

`object_blaster.lua` is a host script driven by PC local numbers: 5 request, 6 state,
7 pushes, 8 player damage events. It arms 200 ticks after a load, the same pattern as
`20_fus_ro_dah.lua`.

- Start calls `kp.projectiles.configure{model='PLC_FootLker'}` and verifies `enabled`
  and `model`. Then it runs `kp.events.register(kp.events.OnCreatureDamaged, blaster.on_damaged)`.
- The handler reads `GetLastDamager` under `nwscript.with_caller(creature, …)`, because
  the K1 routine takes no argument (catalog `{346, "GetLastDamager", Type::Object, kP_346, 0, 0}`).
- It ignores a non-PC damager, a party member or the PC, an invalid target, and
  conversation.
- Otherwise it applies exactly one `nwscript.with_caller(pc, ApplyEffectToObject(0, EffectForcePushed(), creature, 0.0))`.
  It returns nothing, so the stock damaged script still runs.
- Stop unregisters the handler, calls `disable()`, and puts observation back to what it
  found. It is idempotent. It also runs on module load, area enter and script unload.
- Any failure publishes state 9 and tears down.
- No Lua name reuses a NWScript routine name. The test caught `log`, which is routine
  `"log"`, and the helper is now `note`.

## Test results

- Host mock test, run the way the multiplayer example test runs (standalone luajit;
  the container has no `/usr/bin/luajit`, so the host binary was used):
  `/run/host/usr/bin/luajit tools/tests/examples/object_blaster.lua`. Result: exit 0,
  `CASES 16`, `all checks passed`.
  - Cases: arming ignores a stale request; start selects the footlocker and binds; switch
    selects the crate.
  - One damage event gives exactly one push, with the PC as caller for both constructor
    and apply, an instant duration, the damaged creature as target, and a nil return.
    Three events give three pushes.
  - No push for a non-PC or invalid damager, a party victim, or conversation.
  - A miss (no damaged event, 300 ticks) gives no push.
  - Damage before start gives no push.
  - Teardown unbinds, disables and restores observation off. Damage after teardown gives
    no push, and a second stop is a no-op. Stop leaves observation on if it was on before.
  - Restart resets the counters. Module load and script unload tear down.
  - A refused model, a missing `kp.projectiles` or a refused registration each fail
    closed.
  - No Lua names shadow routines, and every `q('X')` is in `src/generated/routines_k1.inc`.
- Compile: `luajit -e 'assert(loadfile("scripts/demos/object-blaster/object_blaster.lua"))'`
  gave exit 0.
- TOML: `PYTHONPATH=scripts/harness python3` with `kpharness.scenario.Scenario.load` on
  each route gave observe 39, replace 70 and knockback 53 steps.
  - `list_scenarios()` discovers `object-blaster/{knockback,observe,replace}.toml`.
  - `find_scenario('object-blaster/knockback')` resolves.
  - Every `q('X')` and `nwscript.call('X')` in the route code is in the K1 catalog, and
    every `await_log` pattern compiles with `re`.
- Offline gate: from `tools/`, `PYTHONPATH=../scripts/harness python3 -m unittest
  kpharness_offline_test.TestScenario.test_shipped_scenarios_parse
  kpharness_offline_test.TestConfigurationContracts.test_resource_normalization_preserves_shipped_step_semantics`
  gave `Ran 2 tests in 296.389s`, `OK`. Both tests iterate every shipped route,
  including the three new ones.

## Notes for the runner

- `mark_log` and `await_log` exist only in `CreativeRunner` (`creative_steps.py`) and
  the private `live_example_gpu.py`. The plain `ScenarioRunner` rejects them.
  `observe.toml` and `replace.toml` use `mark_log` only, and `knockback.toml` uses both.
- The private `live_example_gpu.py` deploys host scripts only from `scripts/examples/`.
  The demo lives in `scripts/demos/object-blaster/`, so a runner has to deploy it
  explicitly.
- `tools/example_validation.py` hashes every `tools/tests/examples/*.lua`. The new
  test file enters future receipts' `validation_sources`, but it is not wired into
  `run.lua` or the manifest (both out of scope).

## Grill me

1. **Is there a reason to trust that `OnCreatureDamaged` fires for the fixture's
   `g_sithtroop01`?** Unverified. The hook is `vm.run_script` on the ScriptDamaged
   slot, at medium confidence (`data/events.toml:310-322`). If the template's slot is
   empty, the engine may never call RunScript. The route then fails at the displacement
   step, with locals 7 and 8 both 0. The first live run is the check.
2. **How come a forced miss is not staged live?** A miss applies no damage, so the
   handler is never called. The live route only has a "no damage, no push" quiet window
   (knockback.toml, the step after the log gates). The forced-miss case is covered in
   the host test only ("a miss raises no damaged event and so no push").
   `GetLastAttackResult` exists (catalog 725), but no deterministic miss setup was
   authored.
3. **Why is `reason == 'stock_observation'` enough for `source_client == PC`?** Lua has
   no client-id conversion. The native `intercept` sets that reason only when
   `current_pc()` (server PC → client id, type 5) equals `c.source`
   (`src/api/projectiles.cpp:127-133`, `projectiles_native.cpp:61-76`). The route adds
   one shared, nonzero source across records. This is still a native-derived claim, not
   an independent readback.
4. **Will the force-push move an uncommandable target?** Unverified. The fixture calls
   `SetCommandable(0)` on the target. The contract says the push drives native quickwalk
   through the effect pipeline (`projectile-impact-contract.md`, native force-push
   contract), not the action queue. The original41 audit recorded missing displacement
   for `20_fus_ro_dah`. The ≥2.0 m step is the check.
5. **Is there a reason the routes end with the restoration gate that already failed in
   143031?** The plan runs Stages 2–5 only after Stage 1. The gate stays so teardown is
   always checked. Until Stage 1 lands, each route's report shows the stage steps `ok`
   and the final gate failing (`report.json` per step).

Unsettled question to hand off: does ScriptDamaged dispatch reach Lua for this target?
One live knockback run would settle it: read locals 7 and 8 and the `[object-blaster]`
log lines.

## Round 2 (Grill me)

Date: 2026-09-27. Scope unchanged: host authoring only, same three allowed files, no
Wine, no game, no `src/**`, no `scripts/harness/kpharness/*.py`. The review above
(`blaster-authoring-review.md`) is FAIL, F1 blocking: `kp.events.OnCreatureDamaged` is
dead in this runtime (`src/runtime/hook_bodies.cpp:655,706` raise only
`OnRunScript`/`OnRunScriptDone`; `src/generated/events.inc:168` gives
`OnCreatureDamaged` an `outer_event_id` of `-1`, and `events::find_by_site` returns
null for that; `docs/user/api-status.md` lists it under "Dead names"). Registration
still returns `true` (`src/api/compat.cpp` `l_register_callback` only rejects an empty
`lua_name`), which is exactly why the old design looked armed and never fired.

### Trigger chosen

`kp.events.OnCreatureAttacked`, not `OnRunScript` filtered by resref. Referents:
- `docs/user/api-status.md:120`: "`OnCreatureAttacked` | Live (NPC victims only: it
  never dispatched for the player creature as `creature`...)". The blaster's targets
  are NPCs, so this is exactly the covered case.
- `data/events.toml:266-272`: hook site `event.creature`, args `creature` (this,
  the victim) and `attacker` (caller). Two arguments, matching the handler signature
  now used: `blaster.on_attacked(creature, attacker)`.
- `scripts/examples/cursed/20_fus_ro_dah.lua:96` already reads this event from
  inside a hook live (its own header cites a 2026-09-16 verification), so the event
  path itself is not a new risk — only the confirmed-hit filter added on top of it is.
- The F1 fix-direction option (a), `OnRunScript` filtered to `k_def_damage01`,
  was not taken: it depends on that resref actually being wired into
  `g_sithtroop01`'s ScriptDamaged slot, which the review marked as its own unknown
  ("this is the writer's original worry, and it now applies to the fix"). Option (b),
  `OnCreatureAttacked` plus a route-side HP check, has no such per-target authoring
  dependency, so it was chosen.

### Never-on-a-miss, independently countable

`OnCreatureAttacked` fires on every attack, hit or miss. The handler in
`scripts/demos/object-blaster/object_blaster.lua` now confirms each attack against
the target's own `GetCurrentHitPoints`, sampled and stored per creature in
`status.hp_seen`. A miss cannot lower hit points, so it can never pass
`hp_now < hp_before`; F1's dead-event bug cannot recur as a live false-positive
because a real engine value gates the push, not just an event firing. The one
disclosed edge: the very first attack this script ever sees against a given
creature has no `hp_before` sample, so it can only record a baseline and never
pushes — a documented under-count on first sighting, never an over-count (a miss
still can't look like a hit). `tools/tests/examples/object_blaster.lua` now has a
direct case for this ("a confirmed hit gives exactly one push from the player,
after a baseline sighting") and for a miss after the baseline ("a miss lowers no
hit points and so gives no push, even after a baseline").

`knockback.toml` was updated to match: the route now expects two stock hits before
checking Stage 5 pass (the first is the demo's baseline, the second is its first
counted push), and it keeps its own independent hit-point-drop counter (`route_hits`)
sampled every poll from `GetCurrentHitPoints(target)`, entirely separate from the
demo's own locals. The checked invariant is `route_hits == pushes + 1` (the "+1" is
the one baseline hit the demo itself never counts) at the Stage 5 pass step, at the
"exactly one push..." step, and again folded into `kb_quiet` for the quiet-window
checks. This answers F2 (the old "7 == 8" was true by construction, from the same
code path) with a genuinely independent source: the route's own polling loop, not
anything the demo publishes about itself.

### Slot collision (minor note in the review)

`scripts/demos/object-blaster/object_blaster.lua` moved its counters off locals 7/8
onto 10/11. Every script in `scripts/examples/cursed/` (`10_rancor_roulette.lua`,
`20_fus_ro_dah.lua`, `30_necromancer.lua`, `40_chain_reaction.lua`,
`70_doppelganger.lua`, `80_loot_pinata.lua`, `90_bullet_time.lua`,
`100_item_airstrike.lua`) defines `local COUNTER_SLOT = 7` on the PC; `object_blaster`
previously used 7 for pushes and 8 for events, so 7 collided if both were ever
deployed together (`grep -n "COUNTER_SLOT *=" scripts/examples/cursed/*.lua`,
8 hits, all `= 7`). `knockback.toml` and `tools/tests/examples/object_blaster.lua`
were updated to read/write 10 and 11 accordingly. Locals 5 (request), 6 (state), 10
(pushes) and 11 (events) are all on the PC and persist into a save the same as any
other PC local; the demo's header now says so explicitly and notes that a save/load
mid-run reads back the last-published values rather than resuming a push, since the
in-memory `status.hp_seen` baseline table (not save-persisted) is lost across a
reload regardless.

### Host mock: dispatches only what the runtime raises

`tools/tests/examples/object_blaster.lua`'s fixture now has exactly one event
source, `w.attack(creature, attacker, damage)`, modeling `OnCreatureAttacked` the way
`hook_bodies.cpp` actually raises it (`damage` optional/zero models a miss: the
attack happens, hit points do not move). `kp.events.OnCreatureDamaged` still exists
as a registerable constant in the mock (`w.env.kp.events.register` still returns
`true` for it, matching real `compat.cpp` behavior for any real event constant), but
nothing in the fixture ever calls a handler bound to it — there is no `w.damage()`
any more. A dedicated case, "OnCreatureDamaged is registerable but this fixture
never dispatches it: the dead-event design fails here", registers a bare handler on
it directly (bypassing the demo entirely), then drives two real, confirmed hits
through `w.attack`, and asserts the handler's call count stayed 0. That is F1,
reproduced positively: the same harness that gives the demo every chance to push
gives the old design no chance at all.

### Mutation coverage

Reran, ad hoc, against the fixed demo (not committed anywhere; the reviewer's
`review-probes-blaster/mut_*.lua` files are the reviewer's own artifacts and were not
touched — this is an independent re-derivation, run from a scratch copy under
`/tmp`, to check the same three mutations the review named would still be caught by
the *new* trigger and the *new* test file):
- drop the attacker check (`elseif attacker ~= pc then ...` replaced with a no-op
  branch): `/run/host/usr/bin/luajit tools/tests/examples/object_blaster.lua` exits 1
  at "non-player attacker, party victim and conversation give no push" — a stranger's
  attack now pushes, which the test catches.
- push twice (duplicated the `ApplyEffectToObject` block, one counter bump): exits 1
  at "a confirmed hit gives exactly one push from the player, after a baseline
  sighting" — `exactly one push` fails, two `ApplyEffectToObject` calls for one
  confirmed hit.
- skip unregister (drop the `pcall(kp.events.unregister, ...)` call, keep
  `status.bound = false`): exits 1 at "stop unbinds the handler and restores stock
  bolts" — `handler unbound` fails, since `w.bound[ON_ATTACKED]` is still set.
- The restored original then reruns clean: `CASES 17`, `all checks passed`, exit 0.

### Verification commands run this round

- `/run/host/usr/bin/luajit tools/tests/examples/object_blaster.lua` — `CASES 17`,
  `all checks passed`, exit 0 (17, up from 16: one new case for the dead-event
  fixture, one new case split out of the old "one damage event" case for the
  baseline/miss distinction).
- `/run/host/usr/bin/luajit -e 'assert(loadfile("scripts/demos/object-blaster/object_blaster.lua"))'`
  — exit 0.
- `python3` with `kpharness.scenario.Scenario.load` on `knockback.toml` — 54 steps (up
  from 53: the added "second stock hit" step for the route's independent count).
  Every `q('X')`/`nwscript.call('X')` name used in the route resolved against
  `src/generated/routines_k1.inc`; every `await_log`/regex `pattern` in the file
  compiled under `re`.
- The three ad hoc mutations above, run and reverted from a `/tmp` scratch copy —
  never staged, never committed.

### Grill me, weakest first

1. **Does `OnCreatureAttacked` actually fire for `g_sithtroop01` when hit by the
   borrowed disruptor, and does the engine apply damage before the hook runs (so
   `GetCurrentHitPoints` already reflects it)?** Unverified by anything other than
   `docs/user/api-status.md`'s "Live (NPC victims only)" line and
   `20_fus_ro_dah.lua`'s working use of the same event from inside a hook. The HP-read
   ordering (damage applied before or after the `EventHandler` callback fires) is the
   one live unknown this fix carries forward from F1, just relocated: if damage is
   *not* yet applied when the hook runs, every attack looks like a miss and the route
   times out at "a second stock hit gives the route its own, independent
   hit-point-drop count", not at the old failure point (still 0/0, but for a new
   reason). One live knockback run settles it: watch whether `route_hits` ever
   reaches 1.
2. **Why does the very first attack against a target never push, even if it is a
   real hit?** Because there is no way to tell a first-ever hit from a first-ever
   miss without a hit-point sample from strictly before that attack, and this script
   has no observation point earlier than the attack event itself. The alternative —
   assuming the first attack is always a hit — would have reintroduced exactly the
   "never fires on a miss" failure mode this fix exists to close. Documented as a
   deliberate under-count in the demo header and exercised by
   `tools/tests/examples/object_blaster.lua`'s baseline case.
3. **Is `route_hits == pushes + 1` the right invariant, or an artifact of this
   particular route's timing?** It holds because `request(1)`/local 5 = 1 is the only
   thing that can reset the demo's `status.hp_seen` table for this target, and the
   route requests start (and thus the reset) strictly before the fixture's first
   `fire()` call. If the fixture ever landed a hit between `start()` returning and the
   route's own poll step reading it, the offset could shift; the route's "independent
   demo running..." step polls until state 1 is observed before seeding
   `route_hp_last`, which narrows but does not eliminate that window. Not verified
   live.
4. **Does `EffectForcePushed` move the uncommandable `g_sithtroop01`?** Unchanged
   from the original report: unresolved, still the same open question, still settled
   only by the `kb_away >= 2.0` step.
5. **Was moving to locals 10/11 tested for its own regressions (e.g. any other script
   in this repo already claiming 10 or 11)?** `grep -rn "SetLocalNumber.*,1[01],'` across
   `scripts/` found no other use of 10 or 11 on the PC; the demos in
   `scripts/demos/animation-memory` and `scripts/demos/model-memory` use 5-9, and the
   cursed pack uses only `COUNTER_SLOT = 7`. Not exhaustive beyond `scripts/`.

Unsettled question to hand off (same shape as before, narrowed): does
`GetCurrentHitPoints(target)` read a post-damage value by the time
`OnCreatureAttacked` dispatches for a real hit? One live knockback run settles it —
watch `route_hits` reach 1 at the "second stock hit" step, not just `baselinehp`
being beaten at the first one.

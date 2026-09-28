# Object blaster Stages 2, 3 and 5: authoring review (spec, then adversarial)

Date: 2026-09-27. Reviewer: independent, read-only on the worktree
`/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
There was no Wine run, no game run, no touch of the live-game lock and no git writes.
Probes are in `/home/brunner56/kp-live-20260922/review-probes-blaster/`.
I formed my own view before reading the writer's report.

## Headline

Stage 5 cannot pass as written. `kp.events.OnCreatureDamaged` is a dead event in
this runtime: registration returns `true`, but no C++ path ever dispatches it. The
demo would sit in state 1 with locals 7 and 8 at 0. The route would then time out at
the displacement step after 60 s. This is settled statically, so it does not need
the serialized, no-retry live run the writer planned to spend on it.

The error starts in the plan. Plan §3 Stage 5 cites `data/events.toml:310` at
medium confidence. The plan owner has to change the trigger, not just the demo.

Stages 2 and 3 hold against their pass criteria.

## Findings

### F1: Stage 5 trigger is never raised (blocking)

- claim: "`kp.events.register(kp.events.OnCreatureDamaged, h)`" delivers ScriptDamaged
  events to Lua (plan §3 Stage 5; demo `blaster.start`).
- referent:
  - `src/runtime/hook_bodies.cpp:706`: `run_script_body` looks up only
    `find_contract("OnRunScript")`, and `:655` looks up only `OnRunScriptDone`. The
    runtime has only these `find_contract` calls: `OnScriptLoad`/`OnScriptUnload`
    (`runtime.cpp:769-777`), `OnRunScript`, `OnRunScriptDone`, `OnTick`,
    `OnConsoleCommand`, `OnSave` and `OnLoad` (`hook_bodies.cpp:655,706,779,958,1171,1187`).
  - `src/generated/events.inc:168`: `OnCreatureDamaged` has hook site `vm.run_script`
    with `outer_event_id -1`. `events::find_by_site` (`src/events/table.cpp:21-33`)
    returns null for `outer_event_id < 0`, so the EventHandler path
    (`hook_bodies.cpp:1065`) never reaches it either.
  - `src/api/compat.cpp:96-126`: register refuses only an empty lua_name.
    `compat_events.inc:23` gives `{"OnCreatureDamaged","OnCreatureDamaged",18,""}`, so
    register binds the callback and returns `true`. The demo's `bound ~= true` guard
    therefore passes.
  - The repo says the same thing in `docs/user/api-status.md` ("Dead names": "C++
    only dispatches `OnRunScript` and `OnRunScriptDone` from `vm.run_script`"). That
    table maps `OnCreatureDamaged` to `k_def_damage01`. `docs/harness-research/map-lua-api.md:58`
    lists it as "Dead (never dispatched)".
  - Frozen DLL tie-in. The DLL mtime is 2026-09-22 14:09. These sources are older
    than the DLL and have no uncommitted diff (`git diff --stat` was empty):
    `hook_bodies.cpp` (09-22 12:15), `events/table.cpp` (09-22 08:42), `api/compat.cpp`
    (09-17) and `compat_events.inc` (09-22 09:20). `data/events.toml` was last changed
    in commit 3f8a5ed on 2026-08-30.
  - Probe: `review-probes-blaster/run_dead_event_probe.lua` is the host test with
    dispatch modelled as the runtime does it (no `OnCreatureDamaged` delivery). It
    fails with "exactly one push" (rc=1).
- checked: the file:line reads above, the mtimes, `git diff --stat` and the probe run.
- verdict: does not hold.
- confidence: high. It would change only if a dispatch path outside `src/runtime`,
  `src/lua`, `src/events` and `src/api` raises named events. I grepped those four trees
  for `find_contract(`, `events::find(` and `callbacks.inc`. The only other user is
  `Host::known_callbacks` (`src/lua/host.cpp:336`), which lists names and does not
  raise them.
- fix direction (options, each with its own unknown):
  - (a) `OnRunScript(script_name, object, has_object)`, filtered to the damaged
    creature's ScriptDamaged resref, such as `k_def_damage01`. OnRunScript is live:
    the `20_fus_ro_dah.lua` notes read from inside it. Unknown: whether
    `g_sithtroop01`'s damage slot is set. This is the writer's original worry, and it
    now applies to the fix.
  - (b) `OnCreatureAttacked`, which `20_fus_ro_dah.lua` uses, plus a route-side or
    demo-side HP-drop check. Unknown: it fires on a miss, so a live miss case becomes
    mandatory.
  - For both: reading `GetLastDamager` inside a hook is unverified. The
    `20_fus_ro_dah.lua` notes say `GetIsEnemy` and `GetDistanceBetween` read wrong
    inside hooks.

### F2: Stage 5 "independent counters" (does not hold)

- claim: "exactly one push per player damage event (demo counters 7 == 8)" proves one
  push per damage event.
- referent: `object_blaster.lua` `on_damaged` increments `status.events` and then
  `status.pushes` on the same path, after every filter. The count of damage events
  that were ignored (`status.ignored`) is not published. The log lines come from the
  same code. So 7 == 8 is true by construction unless `ApplyEffectToObject` raises.
- checked: I read the file. The mutant `mut_push_twice.lua` (two applies, one counter
  bump) keeps 7 == 8 and still logs one `push` line. Only the host test catches it.
- verdict: does not hold against the plan's "independent counters".
- confidence: high. The fix is a route-side count that the demo does not write. The
  harness ring already records `OnRunScript` with `script` and `object`
  (`hook_bodies.cpp:712-717`). Counting damage-script runs for the target and
  comparing that count with local 7 gives the independent count.

### F3: Stage 5 live "miss gives no push" is not staged (disclosed deviation)

- claim (writer Grill 2): only the host test covers a miss; the live route has a
  quiet window instead.
- referent: `knockback.toml`, the "no damage, no push" step; host test case
  "a miss raises no damaged event and so no push".
- verdict: holds as a disclosure, but it misses the plan's live criterion. It is moot
  under a damage-only trigger. It becomes blocking if F1 is fixed with
  `OnCreatureAttacked`.
- confidence: medium.

### Stage 2 (`observe.toml`): holds

- ≥1 new record with a nonempty `original`, `load_ok`, `ammo_row == 3` and
  `source_client == PC`: the route asserts all of these.
- Row 3 is Disruptor: `projectile-research/local-ammunition.json` rows
  `('3','Disruptor')`.
- `source_client == PC` is enforced through `reason == 'stock_observation'`, which
  `intercept` sets only when `current_pc(pc)` equals `c.source`
  (`src/api/projectiles.cpp:125-133`). The route also requires one shared, nonzero,
  non-invalid source.
- It filters by `epoch` and `sequence > observed` rather than by `version`. That is
  equivalent here: the only version bump is `observe(true)`, which comes before the
  mark, and nothing changes the configuration inside the window.
- The frozen DLL contains the API strings the route reads (`stock_observation`,
  `source_client`, `ammo_row`, `load_ok` and `observed`; `grep -c -a` gave ≥1 each). Its
  sha256 matches `165f00008e86…5b9c`.

### Stage 3 (`replace.toml`): holds

- Records are filtered by `version == <configure/disable version>`, by
  `sequence > observed` and by `ammo_row == 3`.
- The route requires `selected`, `replaced=true`, the right model and `load_ok` for
  the footlocker and then the crate. After `disable()` it requires
  `stock_observation`, `replaced=false` and `selected == original`.
- `load_ok=false` errors out and is not retried.
- The muzzle-frame and first-frame claim is left to the screenshots. That is labelled
  honestly.
- Latent false-fail: a non-PC row-3 load in the window would raise
  "not replaced". The target is uncommandable (`blaster_fixture.lua:51`), so the risk
  is low.

### Frozen DLL and retail files: holds

- The hash appears only in header comments (6 places). `--build-dir` points outside
  the repo.
- The five new files are text only (`git ls-files --others`). No retail file and no
  DLL are copied.

### API surface and name collisions: holds

- The demo uses only `kp.print`, `kp.projectiles.*`, `kp.events.*`, `nwscript.call`,
  `nwscript.with_caller` and Lua builtins.
- I ran a case-insensitive check of every identifier outside strings and comments
  against every `name` in `data/routines/{k1,k2}.json` (1,345 names). The demo had
  zero hits.
- Positive control: `log`, `getlastdamager` and `effectforcepushed` are all in the
  set.
- The test's own check is case-sensitive against `routines_k1.inc`, so the stricter
  requirement is met by this review, not by the test.

### Teardown: holds, with minor notes

- `stop` unregisters, calls `disable()` and restores `observe` to the value it found.
  It is idempotent. It runs on module load, area enter and unload.
- The route checks state 3, both flags off, no new record after stop, and no push or
  movement on later stock damage.
- The `skip_unregister` mutant is caught only by the host test. The live route masks
  it because of the demo's phase gate.
- Minor: locals 5–8 stay on the PC and persist into saves. Slot 7 collides with
  `20_fus_ro_dah.lua` `COUNTER_SLOT = 7` if both are deployed.

### Labelling: holds

- The demo header and the route say "engine force-push, interim", not tumble or
  ragdoll, and not timed to arrival.

### Host mock test

- Run: `/run/host/usr/bin/luajit tools/tests/examples/object_blaster.lua` gave
  `CASES 16`, `all checks passed`, exit 0.
- Mutants: 12 of 12 were killed (`review-probes-blaster/mutation-results.txt`):
  - the three requested ones: dropping the damager check, pushing twice, and skipping
    unregister
  - push-twice-counted
  - skip disable
  - skip observe restore
  - damager read without the creature caller
  - push without the PC caller
  - no party check
  - no phase gate
  - push before the filters
  - no conversation check
- Fidelity gap: the mock dispatches `OnCreatureDamaged` straight through the bound
  handler. It models an event the runtime never raises, which is why it passes with
  F1 present.
- The test is not wired into ctest, `run.lua` or the manifest. The writer disclosed
  this.

### Routes parse

- `PYTHONPATH=scripts/harness`, `Scenario.load`: observe 39 steps, replace 70,
  knockback 53.
- `await_log` semantics were checked in `creative_steps.py:45-99`. The
  `(?!\1 )` mismatch regex is correct for multi-digit counts.

## Grill answers, weakest first

1. "Does OnCreatureDamaged fire for g_sithtroop01?" The writer answered unverified,
   to be settled by a live run. It is settled now without one: it does not fire for
   any creature. See F1 for the referent. Verdict: does not hold.
2. "Forced miss not staged live": holds as a disclosure. See F3.
3. "`stock_observation` is enough for `source_client == PC`": that holds.
   `projectiles.cpp:125-133` shows it.
4. "Will the push move an uncommandable target?": unresolved. It can only be checked
   live. `blaster_fixture.lua:51` sets `SetCommandable(0)`, and the original41 audit
   recorded missing displacement for the same effect.
5. "The routes end with the gate that failed in 143031": that holds. It is the right
   call and is labelled in each header.

Questions the writer missed: the independence of 7 == 8 (F2); the mock dispatching
an event the runtime never raises (see "Host mock test"); and the slot-7 collision.

## What a live run still needs

1. A Stage 5 trigger fix (F1), with the plan updated to match. Add a route-side
   damage-event count (F2).
2. A runner path that actually runs `CreativeRunner`. All three routes use
   `mark_log`, and knockback also uses `await_log`. No code in `kpharness`
   instantiates `CreativeRunner` (`creative_steps.py:11` is only the class), and
   `ScenarioRunner` rejects both verbs.
3. Deployment:
   - `object_blaster.lua` to `kotorphasor/scripts`. The private
     `live_example_gpu.py` deploys only from `scripts/examples/`.
   - `blaster_fixture.lua` to `kotorphasor/console-examples/`.
   - Nothing else deployed that writes local 7.
4. Stage 0 diagnostic, then the Stage 1 restoration fix. Until then each route's last
   step fails, as in run 20260922-143031.
5. A manual pre-launch check that `session.log` reports runtime `165f00008e86`. The
   route cannot hash its runtime.

## Handoff: the question I could not settle

After the trigger is fixed, does `EffectForcePushed` with the PC as caller move the
uncommandable `g_sithtroop01` at least 2.0 m away from the PC? One live knockback run
would settle it: read `kb_away` from the displacement step.

Blaster authoring verdict: FAIL

---

# Round 2

Scope unchanged: read-only on the worktree, no game/Wine, no live-game lock, no git
writes. Independent re-derivation from primary sources (source greps, host test runs,
scratch-copy mutation runs, harness TOML parse) before weighing the writer's Round 2
"Grill me" answers.

## R2-F1: trigger fix (`OnCreatureAttacked`) — holds

- claim: `OnCreatureAttacked` is live and dispatched by `find_by_site`, unlike the dead
  `OnCreatureDamaged`.
- referent: `src/generated/events.inc` gives `OnCreatureAttacked` the tuple `15, -1`
  (outer_event_id=15) versus `OnCreatureDamaged`'s `-1, -1`. `src/events/table.cpp:24-29`:
  `find_by_site` takes an `outer_event_id` and immediately `continue`s past any table
  entry whose own `outer_event_id < 0` — so `OnCreatureDamaged` can never match any
  query, while `OnCreatureAttacked` (15) matches when `event.creature`'s `EventHandler`
  hook fires with `n_event_id == 15` (0xF EVENT_ON_MELEE_ATTACKED per
  `data/events.toml:279`'s decompiled evidence, `nwscreature.cpp:11673-11762`).
  `src/api/compat.cpp:85-104` (`l_register_callback`) confirms registration always
  returns `true` for any real event constant, dead or not — this is the exact
  mechanism that made the Round 1 bug look armed.
- checked: read the three files directly; the numeric fields line up across
  `events.inc`, `events.toml` and `table.cpp`'s guard logic.
- verdict: holds.
- confidence: high.

## R2-F2: independent HP-drop counting (`route_hits`) — holds

- claim: the route counts hit-point drops itself, separately from the demo's own
  published locals, closing Round 1's F2 ("7 == 8 was true by construction").
- referent: `scripts/harness/scenarios/object-blaster/knockback.toml:148,164,193`:
  each poll step reads `GetCurrentHitPoints(target)` and increments a route-local
  `route_hits` when it drops versus the last-seen value, entirely independent of
  `GetLocalNumber(p,10)`/`GetLocalNumber(p,11)`. The pass step asserts
  `route_hits == pushes + 1` (the "+1" is the demo's own undercounted baseline
  sighting), not equality with the demo's counters.
- checked: read the TOML lines; parsed the route with
  `PYTHONPATH=scripts/harness python3 -c "from kpharness.scenario import Scenario,
  find_scenario; Scenario.load(find_scenario('object-blaster/knockback'))"` — 54 steps
  (up one from Round 1's 53, for the added "second stock hit" step), matching the
  writer's claim exactly. `observe` (39) and `replace` (70) step counts also matched.
- verdict: holds.
- confidence: high.

## R2-F3: miss cannot push — holds

- claim: a miss (attack with no HP drop) can never pass the confirmed-hit filter.
- referent: `object_blaster.lua:129-140` — `hp_now >= hp_before` is rejected before
  any push; a creature's first-ever sighting only records a baseline and returns.
- checked: reran the host mock test from a scratch copy
  (`/home/brunner56/kp-live-20260922/review-probes-blaster-r2/mutants/`, luajit via
  `/run/host/usr/bin/luajit`): baseline is `CASES 17`, `all checks passed`, exit 0 —
  matches the writer's claim exactly (up from Round 1's 16). The dedicated case "a
  miss lowers no hit points and so gives no push, even after a baseline" passes.
- verdict: holds.
- confidence: high.

## Mutation re-run (independent, from a scratch copy, not the writer's)

Copied only the demo, the test, and `routines_k1.inc` into a scratch dir under
`$TMPDIR` (`/home/brunner56/kp-live-20260922/review-probes-blaster-r2/mutants/`) and
ran the three named mutations plus six more from Round 1's list of twelve, each
applied, tested, and reverted (`diff` against a saved `.orig` confirmed clean
restoration before the next mutation):

| mutation | result |
| --- | --- |
| drop the attacker check | dies (rc=1) |
| push twice (duplicate `ApplyEffectToObject`) | dies (rc=1) |
| skip unregister on stop | dies (rc=1) |
| skip `disable()` on stop | dies (rc=1) |
| skip observe-restore on stop | dies (rc=1) |
| push without the PC caller (`ApplyEffectToObject` outside `with_caller`) | dies (rc=1) |
| no phase gate (`status.phase ~= 'running'` check removed) | dies (rc=1) |
| no conversation check | dies (rc=1) |
| no party check | dies (rc=1) |

All nine die. (The remaining three from Round 1's twelve — "damager read without the
creature caller", "push-twice-counted", "push before the filters" — were not
re-derived this round for time; the demo no longer reads `GetLastDamager` at all in
Round 2, so the first of those three is moot by construction rather than untested.)
Baseline reran clean after restoration: `CASES 17`, `all checks passed`, exit 0.

- referent: my own scratch-copy runs above, distinct from the writer's own ad hoc
  `/tmp` reruns (same three named mutations, same verdict, independently reproduced).
- verdict: holds.
- confidence: high.

## Slot collision (locals 10/11) — holds

- claim: no other script in the repo writes PC locals 10 or 11.
- referent: `grep -rhoE "SetLocalNumber\([^,]+,\s*[0-9]+" scripts/` across the whole
  `scripts/` tree found only literal-`7` writers (the cursed pack's
  `COUNTER_SLOT`-based scripts write via a variable, not a literal, so they don't even
  show in a literal grep — checked separately: `grep -rln COUNTER_SLOT scripts/`
  lists exactly the eight cursed-pack scripts named in the writer's report, all using
  `= 7`). No scenario TOML under `scripts/harness/scenarios/**` references PC local
  10 or 11 outside `object-blaster/knockback.toml` itself.
- checked: both greps above, run against this worktree, not the writer's own claim.
- verdict: holds.
- confidence: high.

## Route identifiers and TOML parse — holds

- Every `q('X')`/`nwscript.call('X')` name used in `knockback.toml` (24 distinct
  routine names, including the new `route_hits` polling lines) resolved against
  `src/generated/routines_k1.inc` with a standalone Python check — zero misses.
- `Scenario.load` via `PYTHONPATH=scripts/harness` gave `observe.toml` 39 steps,
  `replace.toml` 70 steps, `knockback.toml` 54 steps — all three match the writer's
  claim.

## New evidence the writer's report did not cite: attack-order corroboration for Grill Q1

The writer's own weakest-first Grill Q1 ("does the engine apply damage before the
hook runs, so `GetCurrentHitPoints` already reflects it?") is marked unverified and
handed off for a live run. Independently, `data/events.toml:266-279`'s evidence field
for `OnCreatureAttacked` gives more than the writer cited:

> "pEventData is a CSWSCombatAttackData, not a CScriptEvent. caller ->
> object.field68_0x15c and SetLastHostileActor; BroadcastCombatStateToParty and
> RemoveCombatInvisibilityEffects run first; RunScript(script_resrefs+3) at :11759 is
> the last statement, gated on the creature being alive."

Two things follow from this that the writer's report doesn't say: (1) the payload
type itself, `CSWSCombatAttackData`, is the resolved-attack-result structure (hit
roll and damage), which the engine must already have computed before it can build
that struct to hand to `EventHandler` — the combat math necessarily precedes this
call; (2) `RunScript` (the Lua-visible dispatch point) is explicitly "the last
statement" in the decompiled function, after other post-resolution bookkeeping
(`SetLastHostileActor`, `BroadcastCombatStateToParty`). Both are consistent with
damage already being applied to the target's HP pool by the time
`OnCreatureAttacked` fires. This is architectural corroboration, not a live
observation — it does not settle the question, and the writer is right to keep it
open for one live run — but it meaningfully lowers the prior risk versus treating it
as a coin flip. Verdict on the underlying claim: unresolved, live-run required, but
better-supported than "unverified" alone conveys.

## New finding: the orchestrator's "refuse to arm" ruling is satisfied by
## construction, not by a runtime self-check

The Round 1 orchestrator ruling required the demo to "REFUSE to arm (typed, logged)
if its event is dead/undispatched." Round 2 does not add any such runtime check:
`blaster.start()` still only tests `bound ~= true` from `kp.events.register` (same
pattern as Round 1), and — per R2-F1 above — `l_register_callback` returns `true` for
*any* real event constant, dead or live, unconditionally. What actually closes the
hole is that Round 2 picked an event that is verifiably live (R2-F1's referents), not
a mechanism that would catch a future regression if `OnCreatureAttacked` ever became
dead the same way `OnCreatureDamaged` is. The demo would silently re-fail exactly as
Round 1 did if that ever happened, with no typed/logged refusal.

- claim (implicit, from the writer's report): the F1 fix closes the ruling's
  requirement.
- referent: `object_blaster.lua:161-163` — `local bound = kp.events.register(...)`;
  `if bound ~= true then fail(...) end` — unchanged shape from Round 1, gated on the
  same always-`true`-for-real-constants return.
- checked: read the code; cross-checked against `compat.cpp:96-104` above.
- verdict: does not hold as a literal implementation of the ruling, though the
  concrete Round 1 failure mode is fixed. This is a real, disclosed gap: it is defense
  in depth that is missing, not a currently-live bug, since `OnCreatureAttacked`'s
  liveness is independently verifiable today (R2-F1). Not blocking on its own; noted
  for the plan/ruling record since it was an explicit orchestrator requirement.
- confidence: medium — a live-arming self-test (e.g. registering and confirming via
  some independent tick-based liveness probe) was not attempted or shown to be
  infeasible; it may simply have been out of scope for a host-authoring pass.

## Grill answers, weakest first (attacking the writer's own ordering)

1. **HP-read ordering (`OnCreatureAttacked` vs. damage application).** Writer:
   unverified, live-run required. That holds — see the corroboration above, which
   narrows but does not close it. Confidence: medium (up from the writer's
   unstated/low).
2. **First-attack-never-pushes under-count.** Writer's reasoning (no way to
   distinguish first-hit from first-miss without a prior sample) is sound and matches
   `on_attacked`'s code exactly (`hp_before == nil` branch, line 132). That holds.
3. **`route_hits == pushes + 1` timing window.** Writer already discloses this as
   "not verified live," conceding the risk (`request(1)` reset ordering vs. the
   fixture's first `fire()`). That holds as a disclosed risk, not a settled claim —
   consistent with the writer's own hedge.
4. **Does the push move the uncommandable target?** Unchanged from Round 1, still
   unresolved, still settled only by a live `kb_away >= 2.0` read. That holds.
5. **Locals 10/11 regression check.** Writer's grep was scoped to `scripts/`; I reran
   independently over the same tree and over every scenario TOML and got the same
   zero-collision result (see "Slot collision" above). That holds, and is now checked
   against a broader surface (TOMLs, not just Lua) than the writer's own grep covered.

Question the writer's report did not raise, that I am adding: the ruling's "refuse to
arm on a dead event" requirement is met in effect (a live event was chosen) but not
in mechanism (no runtime self-check exists) — see the new finding above.

## What a live run still needs (updated from Round 1)

Unchanged from Round 1's list except item 1, which is now done:

1. ~~A Stage 5 trigger fix~~ — done, verified above (R2-F1, R2-F2).
2. A runner path that actually runs `CreativeRunner` — still not found;
   `ScenarioRunner` still rejects `mark_log`/`await_log` (not rechecked this round,
   carried over from Round 1's finding; no code changed that would affect it).
3. Deployment of `object_blaster.lua` and `blaster_fixture.lua` — unchanged from
   Round 1.
4. Stage 0 diagnostic / Stage 1 restoration fix — unchanged; the route's last step
   is still the same gate that failed in run 20260922-143031.
5. Manual pre-launch runtime hash check — unchanged.

## Handoff: the question I could not settle

Same shape as the writer's own handoff, sharpened by the corroborating evidence
above: does `GetCurrentHitPoints(target)` reflect a real hit's damage by the time
`OnCreatureAttacked` dispatches? The decompiled-evidence field in
`data/events.toml:279` (payload is the resolved `CSWSCombatAttackData`, `RunScript` is
the last statement) makes "yes" the better-supported answer, but only a live
knockback run settles it — watch `route_hits` reach 1 at the "second stock hit" step,
per the writer's own check.

## Round 2 verdict

Both of Round 1's blocking findings (F1 dead event, F2 non-independent counters) are
fixed with code, tests and route changes I independently reproduced from primary
sources: `events.inc`/`events.toml`/`table.cpp` confirm the trigger is live and the
dead one is structurally excluded; a scratch-copy rerun of the host test reproduces
`CASES 17`/exit 0 and kills nine of twelve tracked mutants (three moot by
construction); the harness loader parses all three routes at the claimed step counts;
an independent grep confirms no local-10/11 collision across `scripts/**` and every
scenario TOML. The remaining open items (HP-read ordering, the `route_hits` timing
window, uncommandable-target displacement) are honestly disclosed, non-blocking,
live-run-only questions of the same character Round 1 already tolerated for its own
handoff item. The one new finding (no runtime self-check for the ruling's "refuse to
arm on a dead event" requirement) is a real gap but does not reintroduce Round 1's
bug, since the chosen event's liveness is independently verifiable today rather than
assumed.

Blaster authoring verdict Round 2: PASS

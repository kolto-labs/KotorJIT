# Cursed KotOR

Nine retained Lua scripts that rewrite the rules of a fight from inside the engine, each
tied to an engine event. They are demos of what the event layer plus the full
NWScript routine table can do, not gameplay mods. Every one is a single file
with no dependencies, so drop any of them into `scriptforge/scripts/` and play.

| Script | Trigger | What happens |
|---|---|---|
| `10_rancor_roulette.lua` | enemy perceives you (`k_def_percept01` via OnRunScript) | requests a humanoid disguise: Malak, Bastila, Canderous, Carth, Jolee or Juhani; applied from a 50ms timer |
| `20_fus_ro_dah.lua` | you hit something (OnCreatureAttacked) | the target is Force-pushed with a force-wave burst and a white flash; every fifth hit requests a sweep within 10m |
| `30_necromancer.lua` | an enemy's death script runs (OnRunScript) | 800ms later it rises as Darth Malak, full health, hostile, wreathed in lightning; once per corpse |
| `40_chain_reaction.lua` | any death script (OnRunScript) | the corpse is a thermal detonator. Everyone else within 7m takes fire damage, and deaths from the blast detonate too. The player and the party are left out: before each hit the script asks whether the victim is `GetFirstPC` or a party member (`IsObjectPartyMember`). A yes, or no clear answer, skips that creature, and a party member's death never detonates. The script keeps no IDs between blasts and never changes a creature's min-one-HP flag, so there is nothing to put back after a swap, a load or an unload. A corpse detonates once; the list resets on a module load or a save-game load |
| `70_doppelganger.lua` | the first time you attack a living non-party creature (OnCreatureAttacked with you as the attacker; with you as the victim it was not seen firing, verified 2026-09-16) | you become Malak, and each creature you attack takes the look you had before. Once you have been in combat, 40 ticks out of combat remove only the script's own disguises. An area enter or module load starts the same cleanup. A creature that is dead or gone by then keeps its disguise; the log says so, and the next area enter or module load stops trying. If a removal fails, the script retries it on later ticks and starts no new copies until cleanup ends. It re-arms 200 ticks after cleanup ends. Nothing happens during a conversation |
| `80_loot_pinata.lua` | enemy death script (OnRunScript) | a ring of credit piles around the corpse; every second corpse releases a hostile gizka |
| `90_bullet_time.lua` | HP drops to at most 70% (OnTick, every fifth tick) | `kp.game_speed(0.25)` for 2.5s, blue tint, haste aura on you; a timer restores speed |
| `100_item_airstrike.lua` | you acquire any item (OnModuleAcquireItem); level up (OnModulePlayerLevelUp, not yet seen firing live) | space laser + 60 damage on every living non-party creature in 20m that `GetIsEnemy` marks hostile to you; neutrals are spared. On level-up you ascend as Revan |
| `110_footlocker_blaster.lua` | PC fires a ranged weapon (`OnCreatureBroadcastSafeProjectile`, falls back to `OnCreatureAttacked`) | each bolt becomes a flying footlocker crate along the PC→target line; on arrival the target is Force-pushed hard (twice) with whirlwind/force-wave VFX and tumbles. `footammo [<placeable>]` retargets the crate blueprint from the console |

Chaos roulette and rave were removed from the public tree on 2026-09-22.
Their unchanged regression sources are under
`tools/tests/examples/fixtures/legacy/cursed/`. This retained collection is
not a featured gallery or a blanket live/visual pass; the separate
[native scene catalog](../../demos/catalog.json) records candidates explicitly.

## How they are built

These retained scripts use an event-driven skeleton:

- `priority = 30` so they answer before the negative-priority passive probes.
- `q(name, ...)`: every engine call goes through a pcall by name. The
  engine bridge may be unbound, and a routine can be missing on
  another build; the guard makes the script inert instead of faulting.
- `yes(v)`: NWScript TRUE arrives as `1` or `true` depending on the marshaller.
- A `kp.print("[cursed:<tag>] ...")` oracle line per firing, so
  the log records the Lua decision and requested operation. It does not prove
  that an effect landed, an action completed, or the displayed model changed.
- A counter in **local number 7 on the PC** (`SetLocalNumber(pc, 7, n)`), which
  is how the route's `assert_lua` gates read progress from a different Lua
  state. Harness `lua` steps run in their own state; script globals are not
  visible to them, engine state is.

Things the event layer forced (see `docs/user/api-status.md`):

- `OnCreatureDeath`, `OnCreatureEndCombatRound`, `OnCreatureSpawn` are dead
  names. Death and end-of-round are caught with `OnRunScript` by script name
  (`k_def_death01` / `*dead*` / `*death*` and `k_def_combend01`); the script
  runs on the corpse, so `object_id` is the creature.
- `DelayCommand` and `AssignCommand` are not bound. Delays are
  `kp.registertimer(ms, "global_callback_name", data)` (return `true` to
  repeat); acting as another creature is `nwscript.with_caller(obj, function() ... end)`.
- Screen flashes are `SetGlobalFadeOut(0, 0.08, r, g, b)` then
  `SetGlobalFadeIn(hold, 0.35)`. There is no other full-screen tint routine.
- `EffectDisguise(row)` takes an `appearance.2da` row. Useful rows: 21 Malak,
  22 Revan, 80 rancor, 77 krayt dragon, 69 gizka.
- `CreateObject(OBJECT_TYPE_ITEM=2, "g_i_credits00N", loc)` puts an item on
  the floor; global creature templates like `g_gizka01` come from
  `templates.bif`, so they spawn in any module.

## Routes and recordings

`scripts/harness/scenarios/cursed/<name>.toml` drives each demo as a
state-gated route from the `endar_room3` checkpoint at 1x: load, reset the
counter, `clear_room`, then `assert_lua ... poll = true` gates on the counter
and on visible engine state (appearance rows, items on the floor, no hostiles
left). `scripts/harness/record_cursed.sh <name|all>` deploys the script,
runs the route, records the Xvfb display with x11grab, cuts a gif from the
first curse, and writes `tmp/demos/cursed/<name>.{mp4,gif,oracle.txt,report.json}`.

Current-byte host and live statuses are tracked in [example validation](../../../docs/example-validation.md). Retained recordings without source hashes are historical evidence only. Death matching deliberately accepts `*dead*` and `*death*`, including broad substring matches. The retired rave fixture still tests a polling timer across temporarily absent/dead PCs.

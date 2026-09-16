# Cursed demos

Ten event-driven Lua scripts that break a KotOR fight on purpose, each run as
a state-gated route and recorded. Scripts: `scripts/examples/cursed/`.
Routes: `scripts/harness/scenarios/cursed/`. Runner:
`scripts/harness/record_cursed.sh <name|all>`.

Each route loads the `endar_room3` checkpoint (six Sith hostile to the
party) at retail speed, proves the counter plumbing with a round-trip
`assert_lua`, fights the room with `clear_room`, then gates on the curse's
counter (PC local number 7) and on visible engine state. The runner records
the Xvfb display with x11grab and cuts a gif from the first `[cursed:*]`
oracle line in `kotorphasor.log`.

| Demo | Proof gate | Status |
|---|---|---|
| 10 rancor roulette | >= 3 transformations; >= 3 creatures whose `GetAppearanceType` is a monster row | wip |
| 20 fus ro dah | >= 5 pushes | ship |
| 30 necromancer | >= 2 resurrections; no live hostile left in 40m | ship |
| 40 chain reaction | >= 3 detonations; party damage >= 10 and PC alive | ship |
| 50 chaos roulette | >= 8 spins | ship |
| 60 rave | >= 12 beats before the fight, >= 40 after | ship |
| 70 doppelganger | >= 3 copies; `GetAppearanceType(pc) == 21` | ship |
| 80 loot pinata | >= 3 bursts; >= 5 unowned items in the area | ship |
| 90 bullet time | >= 1 entry; read-back speed in [0.20, 0.30]; speed restored | ship |
| 100 item airstrike | strike fired after `CreateItemOnObject`; room dead | wip |

"ship" means the route passed every gate and the mp4 shows it; "wip" means
not yet run or a gate failed (the failure is noted here).

## Notes from running them

Batch of 2026-09-16 04:05-05:00, host load 60-120, retail speed, recorded at 10 fps:

- **10 rancor roulette**: first batch: the client hung when disguises applied during Trask's bark on load; scripts now arm 200 ticks after a load and never in conversation; re-running.
- **20 fus ro dah**: 9/9; the every-fifth-hit room shout found 0 targets because GetDistanceBetween misreports inside hooks; now position-based.
- **30 necromancer**: 11/11; 18 oracle lines incl. `verify: valid=1 dead=0 hp=25 app=21` for each rebirth.
- **40 chain reaction**: 11/11; 6 detonations, party damage published.
- **50 chaos roulette**: 10/10; 132 spins.
- **60 rave**: 10/10; 104 beats through the fight.
- **70 doppelganger**: 11/11; `GetAppearanceType(pc) == 21` held.
- **80 loot pinata**: 11/11; credit piles enumerated as unowned items in the area.
- **90 bullet time**: 12/12; read-back `kp.game_speed()` 0.25 during, 1.0 after.
- **100 item airstrike**: first batch passed 12/12 but weakly: the acquire event replays 11 inventory items on load and the medpac strike hit 1 of 6; now armed after load, position-based radius, gate on >= 3 targets; re-running.

Things every route needed before anything passed (all in
`docs/harness-research/engine-facts-k1.md` section 9): the `endar_room3`
checkpoint has no live hostiles, so the routes summon six `g_sithtroop01`;
`GetIsEnemy` and `GetDistanceBetween` are not trustworthy inside hooks;
`OnCreatureDeath` never dispatches (death is `OnRunScript` + `k_def_death01`
on the corpse); a lootless corpse is gone ~3 s after death and
`EffectResurrection` does not revive it; `OnCreatureAttacked` never fires
with the player as victim; effects applied from a hook during a load or a
bark hang the client; `kp.speed` cannot slow the game, `kp.game_speed` can.

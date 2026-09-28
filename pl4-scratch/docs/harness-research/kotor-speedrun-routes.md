# KotOR speedrun routes as a non-visual TAS

Research checked 2026-09-10. The community route pages are the source for the
route and conversation sequences; the harness design below is an engineering
translation of those routes, not a claim that every speedrun glitch is already
implemented.

## What the route evidence says

The K1 Any% NMG guide starts timing at Play and explicitly uses V-Sync and
Auto-Level. Its Endar Spire route is:

1. Skip the introductory cutscene with a hard buffer.
2. Loot the first footlocker, equip the main character's clothes, and finish
   Trask's conversation twice.
3. Equip Trask's offhand blaster. Open-buffer toward the locked door and use
   Security; mash through Carth's conversation while the unlock runs.
4. Use Trask's Power Blast on two Sith, loot the next footlocker, open the next
   door, and kill the front three Sith with a frag grenade. The guide records a
   72.9% chance that the grenade kills all three, so a deterministic TAS must
   branch on the live enemy states and let Trask finish survivors.
5. Open the Jedi/Sith door, use Trask's Power Blast on two Sith, loot the Jedi,
   open the bridge, and kill the two front bridge soldiers.
6. When level-up becomes available, take level 2 with saved skills and
   Two-Weapon Fighting. Open the next two doors, then use the long open buffer
   at the Starboard Section door to suppress Trask's death cutscene.
7. In Starboard, loot the terminal-room footlocker, answer the terminal `2,3`,
   loot the Sith Commander for the Prototype Vibroblade, then take the escape
   pod. This completes the Endar Spire objective.

These steps and the timing/glitch terminology are documented in the guide's
[Endar Spire section](https://kotor-speedruns.github.io/kotor1/Route%20Guides/Any%25%20NMG#endar-spire),
including the combat-roll branch and the exact terminal sequence. The guide
defines QS/QL, hard/open buffers, and the route's allowed NMG tricks in its
[rules and notation](https://kotor-speedruns.github.io/kotor1/Route%20Guides/Any%25%20NMG#nmg-ruleset).

The legal, no-glitch fallback is the same physical route with ordinary door
interaction, waiting for each cutscene, and normal combat. It is preferable
for the first harness proof because it removes buffer timing and save-state
semantics. The speedrun page also documents that Scouts always receive an
Alacrity on the Spire, while Scoundrels have a different random-loot profile;
the TAS should record the seed/drop state and branch its inventory plan rather
than assume a particular drop. See the guide's [build and initial skill
notes](https://kotor-speedruns.github.io/kotor1/Route%20Guides/Any%25%20NMG#character-build).

For K2, the practical speedrun prologue is shorter and has a clean deterministic
sequence: create the recommended female Jedi Guardian, start the prologue,
loot the container for a spike, use the console repeatedly to open Main Hold,
loot the droid for parts, bash the footlocker for two spikes, then return to
the cockpit and choose dialogue option 2 to skip the remaining prologue. The
route then transitions to Peragus. This is recorded in the K2 guide's
[Prologue](https://kotor-speedruns.github.io/kotor2/Route%20Guides/Any%25%20Glitchless#prologue)
and [Ebon Hawk](https://kotor-speedruns.github.io/kotor2/Route%20Guides/Any%25%20Glitchless#ebon-hawk)
sections. The longer K2 route visits Peragus, Telos, Korriban, Dantooine,
Dxun/Onderon, Nar Shaddaa, Onderon, Ravager, and Malachor in that order
([route overview](https://kotor-speedruns.github.io/kotor2/Route%20Guides/Any%25%20Glitchless#route-overview)).
Because that sequence intentionally returns to the cockpit to skip the
remaining prologue, it is **ineligible as a full K2-prologue proof**. A full
prologue profile must enumerate and complete every mandatory Ebon Hawk
interaction and cutscene using engine state, with the completion transition
verified against the installed binary.

## Non-visual TAS strategy

The driver should be a closed-loop action machine. It never chooses an action
from pixels and never asks a model to steer. Each action has a precondition,
an engine command, a bounded completion predicate, and a checkpoint:

| Action | Engine evidence | Completion predicate |
| --- | --- | --- |
| Walk to an object | object tag/position + movement command | distance threshold, `move_pending=0` |
| Use a door/console/container | object identity and interaction call | module/object state changes or dialog opens |
| Talk | active dialog state | `dialog.active=1`, then select a valid reply index |
| Fight | party/enemy object IDs and combat state | target dead or encounter flag cleared |
| Cutscene | cutscene/GUI state | panel/cutscene flag clears; never infer from time alone |
| Area transition | module and load state | module tag changes, then `area_not_ready=0` |
| Save/restore | save/load state | stable module + player creature + server idle |

The route should be represented as named checkpoints rather than a stream of
mouse coordinates: `spire.command.start`, `spire.command.bridge_clear`,
`spire.starboard.terminal`, `spire.escape_pod`, and `tar1.apartment`. At every
checkpoint the driver reads the engine state, selects the next target by tag or
stable object identity, and retries only an idempotent action. A failed
precondition becomes a branch (for example, a surviving Sith) or a diagnostic
failure; it must not blindly repeat an interaction that can duplicate a quest,
trigger a second transition, or deadlock the load state.

For the first useful live proof, use the legal fallback and deliberately keep
the session in active Endar Spire gameplay for at least 120 seconds. A useful
sequence is: enter Command Module, loot/equip, clear the first two encounters,
clear the bridge, operate the Starboard terminal, and continue moving,
interacting, fighting, looting, or progressing through live cutscenes until
the two-minute threshold is reached. A paused game, menu, loading screen,
static camera, or screenshot interval does not count as gameplay. The
recording must contain active play throughout the measured interval;
screenshots are only periodic sanity checks. Afterward, complete the
escape-pod interaction and verify the actual destination module from the
target's resource/state data, a valid player creature, and Endar Spire journal
completion. Do not hard-code `end_m01ab` as the pod destination: in the current
K1 corpus it is the Starboard playable section, so the pod transition must be
resolved from installed module transition data and checked live.

The RPGClassics walkthrough independently describes ordinary completion: equip
the starting gear, follow Trask, clear the Sith groups, loot the Jedi, cross
the bridge, enter Starboard, speak with Carth, and use the escape pod; it
estimates roughly 10--20 minutes for a normal tutorial ([walkthrough,
Endar Spire](https://shrines.rpgclassics.com/pc/kotorpc/801.shtml)). This is
the source-backed normal route. The NMG route above is an optimization guide,
not evidence that simply deleting its buffers yields a complete normal route.
Maintain separate `k1_endar_normal` and `k1_endar_nmg` route profiles.

The NMG buffers and save teleports should be a second TAS profile. They require
frame-accurate save/load and cutscene cancellation, so expose them as explicit
commands only after the ordinary route is proven. Displaced Loading Zones,
menu glitches, coordinate warps, and door clipping are useful research targets
but should not be mixed into the first route: the K1 guide explicitly bans
those techniques in NMG. The unrestricted guide documents their existence and
uses, including the Endar Spire skip, in its [unrestricted route](https://kotor-speedruns.github.io/kotor1/Route%20Guides/Any%25%20Unrestricted).

## Harness implications

The minimum missing capability is not vision. It is a small deterministic
action vocabulary and state oracle: enumerate nearby interactables by tag,
issue movement toward a selected object, select a dialog reply by index, start
or stop an attack, and wait for an explicit engine predicate. The existing
dialog, phase, movement, screenshot, and softlock primitives can supply the
oracle side; route-specific object tags and movement/interaction calls are the
next implementation boundary. Keep the route data declarative so K1 and K2
can share the state machine while their object tags, offsets, and ABI-backed
commands remain per-binary.

## Confidence and limits

The route order, Endar Spire actions, K2 prologue actions, dialogue indices, and
the 72.9% grenade statistic come directly from the linked community guides.
Exact world coordinates, object tags, and frame timings are not provided by
those pages and must be measured from each installed binary/save corpus. Do not
turn the guide's visual route maps or timing advice into universal absolute
addresses. A live proof is complete only when the recorded gameplay interval,
engine predicates, final module, and quit/report result all agree.

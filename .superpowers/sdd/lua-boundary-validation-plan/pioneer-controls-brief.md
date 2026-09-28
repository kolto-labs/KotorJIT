# Pioneer playback implementation contract

Status: approved implementation direction under the user request, not a delivered-feature claim. The transaction foundation is in progress; native controls and live acceptance remain open.

## Interaction

Keep the existing init / step / commit / discard / status authoring pipeline. Add play, pause, fastforward, rewind and stop in the same pioneer command family. Every command accepts --out ROUTE.toml. Play accepts --until STEP; fastforward additionally accepts --speed 4; rewind accepts --to CHECKPOINT_OR_BOUNDARY and defaults to the preceding ready checkpoint. A boundary is a completed route step, not an advertised frame-accurate position. Exact-frame input capture and replay remain a separate capability until proven.

The default authoring interaction is pause, propose one step, inspect its result, commit or restore the pre-step boundary. Commands must distinguish an authored edit from its live effects. Existing discard is metadata-only; document that truth during migration. Change it to live rollback only with a verified checkpoint path, retaining explicit --edit-only for intentionally abandoning recording while keeping world changes.

A changed choice after rewind creates a new branch. Preserve the prior branch, checkpoints and evidence. Executing an unchanged committed route does not append it again. A failed action or uncertain timeout preserves the journal and stops scheduling; do not retry mutations automatically.

## Shared owner

Use one attached-session playback owner and one Channel. Its service receives ordered commands from CLI, eventual editor and tests. It schedules ScenarioRunner.run_step and owns execution lifecycle; do not create another Lua interpreter or copy the scenario verb dispatch. The game process remains owned by GameSession. Stopping playback never terminates the game.

Expose authored cursor, verified executed cursor, route revision/hash, branch, session identity, active operation, pending dirty edit, checkpoint readiness, requested/effective speed, and native pause ownership separately. Pausing only the scheduler is reported as scheduler-paused, never as a frozen game. Runtime and F12 commands continue through the existing engine-thread request queue.

Long commands expose job identity and terminal results. Control requests remain responsive while the worker is in a state wait. Native calls are serialized; a save/load already issued cannot be safely interrupted or redispatched. Pause/stop requests become pending until an appropriate engine boundary. Active wait deadlines exclude deliberate tool pause; hard operation deadlines still detect hangs.

## Native control

Implement capability-checked symmetric pause ownership. Play releases only this tool's pause; preexisting or newly acquired dialog/combat/game pauses survive. Validate world and animation clock readbacks and F12 responsiveness. Timer-pointer or module epoch changes invalidate stale references. Positive bounded speed overrides restore prior policy on completion, pause, stop and failure. No ordinary playback path uses recovery commands that indiscriminately unpause the game.

## Checkpoints and rewind

Use the existing checkpoint manager, strengthened transactionally rather than duplicated. Ready checkpoints contain validated complete retail save artifacts, content hashes, native build/session/module identity, route and script/config revision and independent expected game-state predicates. Publish copied artifacts atomically and preserve the last ready snapshot on failure. Never publish retail save data or assets to GitHub.

A load request receipt is not restoration. Require a newly observed load epoch/transition, complete stable world and checkpoint-specific state agreement. Then update the executed cursor. Replay to a later boundary uses the common runner and every original predicate. State domains absent from native saves, including arbitrary console globals/closures/timers, must be explicitly declared unrestored until a real mod-state serializer exists. Arbitrary midcombat or mid-dialog saves are not implied by idle-world native checkpoint support.

## Ordered implementation slices

1. Transactional step recording and attached execution-policy parity; atomic idempotent commit, stale route/session rejection and reliable speed cleanup. Freeze, independent review, then integrate.
2. Persistent owner with attach/status/play/stop and fastforward through the common runner; ordered controls, process restart/uncertain-operation handling, no duplicated actions.
3. Native pause ownership and shared pause/play wiring; real timer and console acceptance.
4. Immutable checkpoint publication and verified restore, rewind/replay, pending edit rollback and branching.
5. Live proof: choose A and observe its side effect, restore the pre-choice checkpoint, choose B and show both branch histories. Capture continuous smooth footage with clear controls and observable state changes.

Each slice requires focused failure tests and independent review. Host tests are not native pause, deterministic TAS or live rewind proof. Mac K1/K2 remain priority targets; adapters must report unsupported capabilities honestly while the available owned WinK1 session provides initial runtime evidence.

## Research grounding

Ren'Py records interaction checkpoints and supports restoring prior choices and rolling forward with recorded results. Its model motivates choice-boundary navigation here, without assuming KotOR can serialize the same state domains. Source: https://www.renpy.org/doc/html/save_load_rollback.html

libTAS coordinates input at frame boundaries and uses savestates with movie input history. Its documentation also describes limitations from state outside recoverable game memory. This motivates separating verified route-boundary playback from future exact-frame TAS claims. Sources: https://clementgallet.github.io/libTAS/guides/how/ and https://clementgallet.github.io/libTAS/guides/options/

## Verified current checkpoint integration points

The native adapter already tracks a load state machine internally: fields.hpp LoadStep {Idle, Armed, Sent, Placed, Done, GaveUp}; engine_k1.cpp arms it at load_save completion and step_load_completion observes native server placement followed by client area readiness. Expose an operation sequence and terminal status from this existing mechanism before inventing a new polling-only load epoch. Correlate the request sequence with Done and independent stable-world predicates; a previous Done must never satisfy a new request. Also consider failed-before-armed and later native/user loads when defining invalidation.

Existing fields.hpp save_erf_members and savenfo_last_module parsers have synthetic C++ tests in tools/kp_harnesstest.cpp. Reuse that validation contract for checkpoint readiness rather than treating stable file size as a complete archive. Current Python Checkpoints.store/restore destructively replaces directories; CreativeCheckpoints adds root containment and symlink rejection but inherits replacement behavior. Strengthen the common manager once and retain those containment checks. The native Lua model epoch currently changes on unbind; it is not a demonstrated per-save-load epoch.

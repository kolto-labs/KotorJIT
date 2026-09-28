# Pioneer native pause contract — bounded K1 GOG research

2026-09-22. Read-only native-source/corpus and installed-PE inspection. **No existing exposed pause/resume pair meets tool ownership requirements. The minimal grounded next mechanism is an engine-thread pause lease that observes both native PauseWorldTimer and UnpauseWorldTimer requests and composes game intent with tool ownership.** A snapshot of paused bits, the existing recovery unpause command, or an invented native reason bit is insufficient. This is an implementation contract with explicit prerequisites, not a verified full-world freeze.

## Exact authority and ABI

Original input `/home/brunner56/kp-live-20260922/stage-k1/swkotor.exe`; independently recomputed SHA256 `9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435`, PE i386 preferred image base 0x400000. Read-only corpus `/home/brunner56/agentdecompile-nvme/corpus-work/corpus.sqlite`, binary8 `K1__k1_win_gog_swkotor.exe`, corroborates names/signatures. Original instructions, rather than corpus identity alone, establish the following:

| Site | ABI / observed semantics |
|---|---|
| CWorldTimer::PauseWorldTimer 0x004adff0 | thiscall, ECX=timer, no stack arguments, plain ret at0x4ae027. Reads DWORD+0x24; if nonzero returns without incrementing anything. Otherwise calls GetWorldTime0x4ade40, stores day/ms at+0x28/+0x2c, writes+0x24=1. Entry bytes `83ec08568bf18b462485c07526`. |
| CWorldTimer::UnpauseWorldTimer 0x004ae030 | thiscall, ECX=timer, no arguments, plain ret at0x4ae080. Acts only if DWORD+0x24==1, clears it and recomputes base offsets+0x30/+0x34 from saved world time/current snapshot. Entry `83ec08568bf1837e24017540`. A raw bit clear skips required rebasing. |
| GetSnapshotTimeDifference 0x004adc80 | no args, ECX timer; returns 64-bit EDX:EAX zero if paused, otherwise snapshot+0xc minus previous+0x14. |
| GetSnapshotTime 0x004adc70 | returns raw snapshot+0xc in EDX:EAX without checking pause. Pausing therefore does NOT prove every time consumer freezes. |
| Server SetPauseState thunk0x004ae9a0 -> internal0x004b8110 | thiscall(server/internal, int reason, uint32 enabled), ret8. Internal reason byte+0x10078 is ORed on acquire, ANDed with inverse reason on release. Native synchronization/unpause logic has special branches for reasons1 and2, not a generic arbitrary-reason release. It also sends pause-state messages. |
| Client SetPauseState thunk0x005ed650 -> internal0x005f7fa0 | corpus signature thiscall(client/internal, byte reason, int enabled, linked-list pointer). Internal reason byte+0x1cc; original instructions show special reason1/reason2 timer synchronization, GUI side effects, exclusion-list handling and destruction of a supplied list. Do not pass a borrowed list or invent a reason. |

The timer functions provide an idempotent Boolean, NOT a nesting count. A second game Pause call while Pioneer holds the timer produces no observable bit change. Consequently the later game acquisition cannot be recovered from before/after bit reads. Native reason bits exist but are not an extensible owner registry: choosing a spare bit would enter only some pause branches and skip required generic release behavior. Neither reason1 nor2 is exclusively owned by Pioneer.

## Clock coverage

Existing `src/harness/engine_k1.cpp:2598` fixed-step code touches five known clocks. Original getters confirm:

- Client GetWorldTimer0x5ed4f0 -> client internal+0x24.
- Client GetPauseTimer0x5ed500 -> internal+0x2c.
- Client GetAnimationTimer0x5ed510 -> internal+0x30.
- Server GetWorldTimer0x4aede0 -> server internal+0x10048.
- Server GetPauseTimer0x4aee00 -> internal+0x10050.

There are **additional native pause-related clocks**: server GetTimestopTimer0x4aedf0 -> internal+0x1004c, and client internal+0x28, touched repeatedly by SetPauseState (consistent with its corresponding timestop clock, but client name not independently established here). Client pause-state synchronization touches+0x24,+0x28,+0x2c,+0x30; server touches+0x10048,+0x1004c,+0x10050. Therefore copying only the existing five-clock loop must not be advertised as all relevant clock coverage. Resolve/check and deduplicate the relevant identities before acquisition; do not scan or pause every CWorldTimer globally.

Pausing pause/UI clocks may stall GUI animations or modal transitions. Pausing world/animation alone may leave time-stop/exclusion paths moving. The exact supported set must be established by a bounded live clock/pose matrix, keeping renderer, input and transport iteration running. Raw snapshot consumers, audio, movie playback, particles and special animation paths remain unproven. No claim of freezing wall clock or the render loop is appropriate.

## Existing behavior that cannot serve as owned resume

`engine_k1.cpp:1622` clear_auto_pause writes server pause_state=0 then calls unpause_timers. `:2076` unpause_timers unpauses client/server world plus animation and explicitly clears paused-by-combat and auto-paused state. These are recovery tools, not an ownership-preserving release API. Pioneer must not call them to resume.

`engine_k1.cpp:2598` set_fixed_step captures existing pause around a synchronous timer-rate change. That very short bracket is different from an arbitrarily long interactive lease during which game/modal pause requests arrive. Reusing its saved Boolean for interactive resume loses later ownership. SetFixedSnapshotRate also resets snapshot values; it is not a pause substitute.

## Minimal implementation contract

1. Add one runtime-owned native pause service shared by Pioneer/Console adapters, operating only on the engine command thread. A lease/token carries runtime generation, load generation and unique request identity. Repeated acquire/release is idempotent; multiple tool clients compose through their own lease set. No separate VM, scheduler or harness-only pause state.
2. Install guarded hooks for BOTH exact timer Pause and Unpause before leases are allowed. Use verified existing inline-hook machinery with transactional install/uninstall and real i386 thiscall tests. These are function entries rather than a proved vtable boundary; the projectile vtable patch cannot be transplanted blindly. No ownership mode if either hook is unavailable.
3. Track for each validated timer identity: latest game-requested paused Boolean and tool lease presence. Seed game intent from a validated paused value before acquiring. External Pause updates game intent=true even if physically paused already; external Unpause updates it=false. Compose effective pause as game intent OR tool ownership. Tool-origin native calls must use the original/trampoline or explicit origin guard so they do not become game ownership. Preserve the stock idempotent semantics rather than inventing a game nesting counter.
4. While tool-owned, suppress external native unpause that would advance the clock, but remember the game release. Forward required pause/original transitions only once. On final tool release, call original Unpause only when latest game intent is unpaused. Never clear combat, autopause, modal or native reason fields. Other/untracked timer calls stay stock. Keep hooks bounded and free of Lua, filesystem work, waits or allocation-heavy work.
5. Treat unknown/direct timer mutations or mismatched identities as an explicit capability failure. Hooks see calls, not arbitrary field writes, timer reconstruction or copied world-time data. Native SetPauseState contains CopyWorldTime/snapshot synchronization in addition to pause calls, so its interaction with the composed pause needs focused tests/live evidence; do not claim intercepting two calls alone proves all engine state transitions are transparent.
6. Return separate fields for requested tool pause, effective per-clock pause, known game pause intent, capability/epoch and lease status. Acknowledgment is not proof until readback and independent motion/time predicates match. Keep the original flag values untouched through cleanup failures; expose pending cleanup instead of silently reporting resumed.

## Load epochs and lifecycle

Existing model epoch in `src/api/model.cpp` changes on binding/unbinding; the inspected path does not establish a save/module-load generation. Timer pointer equality alone is inadequate: a load may reconstruct/reset a timer at the same address. Acquire is unsupported while loading; release before an owned load begins while identities are still valid, then invalidate all leases/queued operations and advance generation. Do not dereference old pointers after destruction. External game loads require an actual pre-load/reset boundary, not merely polling a changed module name after the fact. At post-load readiness, resolve fresh timer identities and game intent; require explicit new acquire. Do not carry a historical pause lease through a load by default.

Until external-load invalidation and all relevant reset/write paths are grounded, expose any first implementation as a constrained same-loaded-session candidate rather than safe pause across arbitrary loads. Cancellation/disconnect needs an engine-thread release of only that client's leases. Shutdown must release owned pauses at a quiescent valid boundary before removing ownership hooks; failed cleanup must retain safe callable code/state. Arbitrary DLL unload is not supported.

## Responsiveness and script semantics

`src/runtime/hook_bodies.cpp:768` pumps overlay/Console and harness drain at the server loop entry before the original; `:1277` does the same after the client loop returns. Client comments establish idle iterations run even at menus; server fallback drains while client module loading stalls. Pausing timer state rather than blocking either loop should preserve this command path, but F12/edit/evaluate/resume must be proven while the selected clocks are paused.

The same server hook dispatches OnTick and pumps kp timers from now_ms at:785. Thus mod callbacks may continue mutating the world even when native world timers are paused. Pioneer playback stepping should pause independently, while command servicing remains live. If whole mod-scene state must freeze, define an explicit policy for scene-owned OnTick/timers; do not indiscriminately stop Console/control timers or claim native clock pause freezes arbitrary Lua side effects.

## Meaningful acceptance

Offline state-machine tests: initially running/paused; game Pause after tool acquire; game Unpause while held; pause/unpause/pause sequences; two tool leases; repeated release; unknown timer passthrough; no ownership capture from tool-origin calls; failed hook install; pending cleanup; epoch reset including same-address reuse; queued old release rejected; no native call on an expired timer. Assert exact original native call counts and effective states.

Actual i386 entry/trampoline ABI tests: ECX and nonvolatile preservation, no stack-argument cleanup, original-call routing, recursion/origin guard and both installed hooks. Native timestamp tests must prove resume rebasing has no catch-up jump; use the actual originals in controlled live acceptance, not only a Boolean fake.

Live oracle: independently sample client/server world time, pause/time-stop time, animation clip clocks/visible poses and client frame counters while held. Verify F12 input/edit/evaluation/cancel/resume remains responsive. Acquire from normal, combat/autopause and modal-pause states; acquire before a new game pause then release Pioneer and require the game pause to persist; dismiss a modal during tool pause and require tool pause to persist. Exercise release and reacquire around a real save/module load, including same timer addresses if observed. State/video should distinguish stationary poses from a blocked whole application. Resource-neutral owned fixtures only; no broad game modifications.

## Research limits and process status

No source edits, builds, games, index mutations or active-process manipulation. Only this requested private report was written. Original PE was read but never executed or modified. No full corpus scan or variant expansion. All owned stalled read sessions completed (rg48468 exit130 after Ctrl+C; cached read34557 exit0; scoped rg5310 exit0); no research jobs remain. Initial login-shell delay was avoided with login:false. Full reason ownership/direct-write coverage, client extra timer semantics and safe external-load generation remain explicit prerequisites, not guessed offsets to ship immediately.


## Bounded follow-up: compose a tool lease through legitimate native reason1?

**Not safe as a SetPauseState-only interception slice.** The existing native reason1 workflow is a useful reusable boundary, but the proposed simple rule (tool sets reason1; suppress game reason1 release while held; release native reason1 on final lease) has concrete logical-toggle, reason2 timer-state and unload gaps. This conclusion is from additional original-PE instructions, not an assumption that reason flags are unusable.

### ABI and propagation

Server wrapper0x4ae9a0 forwards to CServerExoAppInternal::SetPauseState0x4b8110. ABI thiscall(ECX server/internal, int reason, uint32 enabled), ret8. Hook the internal entry if covering wrapper and direct calls. Capture game intent before its existing-state early return: another reason1 acquire while the tool already sets the bit would otherwise do nothing physically and disappear from ownership accounting. Tool-origin calls need an original/trampoline origin marker, not recursion through the intent hook.

At server0x4b8176 and0x4b82e9 the normal state transition calls CSWSMessage::SendServerToPlayerModule_SetPauseState0x56c9f0. Despite its name, inspected K1 GOG code performs synchronous local client propagation: it obtains server exclusion entries, allocates an engine-owned list if needed, converts object IDs to client IDs, then calls client wrapper0x5ed650 at0x56ca9a. Client internal setter0x5f7fa0 takes reason, enabled and an owned exclusion-list pointer, then returns ret12 at0x5f8285. Client code updates native reason state, performs timer copying/synchronization, calls module/GUI-related virtual operations, rebuilds exclusions and frees the supplied list.

A server-level suppression occurs before list allocation and is safer than dropping a client setter invocation. A client-side hook that simply returns would skip list ownership/destruction and side effects. Do not manually manufacture or duplicate a client list, or call both server and client setters for a single tool transition: normal server propagation already reaches the client.

### Concrete blockers to the simple composition

1. **Game toggles consult the physical tool-held bit.** CServerExoAppInternal::TogglePauseState0x4ba610 reads reason byte+0x10078, masks the argument, computes the opposite state and calls0x4b8110 at0x4ba628; thiscall(reason), ret4. With physical reason1 held by the tool, repeated game toggle requests become repeated release requests even when the separately tracked game intent is false. Merely observing SetPauseState therefore cannot preserve logical game-toggle semantics independently of the tool. A composed implementation must account for toggle intent before it reads the contaminated physical bit, or use a different verified authority. Do not globally falsify all GetPauseState results: other consumers need the actual effective pause.

2. **Preserving reason2's bit does not preserve all its clock effects.** Server reason1 release branch0x4b821c..0x4b82de unconditionally rebases and calls UnpauseWorldTimer on world+0x10048, time-stop+0x1004c and pause+0x10050. Client reason1 release0x5f8143..0x5f81ff similarly unpauses+0x24,+0x28,+0x2c,+0x30 without a remaining-reason2 test in that branch. Therefore calling original SetPauseState(1,0) while reason2 remains set cannot be justified solely by saying the bitmask still preserves reason2. Native reason2 handling elsewhere may continue to gate some simulation, but the requested timer-pause preservation has not been established and these clocks demonstrably receive unpause calls. Avoid inventing a temporary reason2 clear/reapply sequence: that adds native synchronization and GUI/exclusion side effects rather than proving preservation.

3. **Reason2 has a real focus owner.** Original DeactivateRenderWindow0x401d90 tests server GetPauseState(2), records it in manager+0x1c, and only if absent calls SetPauseState(2,1) at0x401dc6. ActivateRenderWindow0x401e00 conditionally calls SetPauseState(2,0) at0x401e2a. Tool resume while unfocused is thus a concrete overlap case, not hypothetical external modification. Do not overwrite this saved focus ownership or turn tool pause into focus state.

4. **Native unload bypasses a server-wrapper-only model and resets pause state.** Corpus direct-call edges were checked against original unload instructions: server UnloadModule0x4b9240 calls internal SetPauseState directly at0x4b92b1(reason2) and0x4b92bb(reason1); client UnloadModule0x5f8290 directly calls client internal setter at0x5f834a(reason2) and0x5f8355(reason1). An outstanding tool lease must be released/invalidated at a verified pre-unload boundary rather than suppressing the engine's teardown clears or waiting for reused timer pointers afterward.

5. **Legitimate native pause is not proof of every animation clock being stopped.** Reason1 acquisition pauses the world clock; client code pauses its extra+0x28 clock only when reason2 is active. Animation/pause clocks are involved in later synchronization and native pause exclusions. Native workflow reuse is valuable, but raw clock coverage and scene/mod side effects still need independent observation rather than assuming this one setter freezes all clocks.

### Direct-call evidence scope

Read-only corpus binary8 direct callers of server wrapper0x4ae9a0 include DeactivateRenderWindow, ActivateRenderWindow, HandlePlayerToServerInputMessage0x5254c0, door EventHandler0x58b850 and trigger EventHandler0x58f140. Internal server0x4b8110 has direct wrapper, UnloadModule and TogglePauseState callers. Client wrapper0x5ed650 is reached directly from0x56c9f0; internal client0x5f7fa0 has wrapper and client UnloadModule callers. This is direct-call evidence, not a complete proof excluding indirect dispatch or raw state writes. Only focus, propagation, toggle and unload callsites were expanded in this bounded follow-up.

### Minimum later acceptance if this route is chosen

Compose explicit reason1 game intent AND logical toggle events with tool leases, preserve reason2/native desired timer state, use server propagation once, and invalidate leases before either teardown/reset path. Add state-machine cases for game toggles while tool-owned, explicit later game acquire, tool release during focus reason2, focus reacquire/release during a lease, preexisting reason1, client exclusion-list ownership, reentrant server-to-client propagation, and unload/reload with the same addresses. Verify exact native side effects and all selected clock/pose predicates live. A combination of native reason workflow and desired timer-state observation may be needed; no validated minimal final architecture is claimed from this bounded inspection.

Research frozen after this append. No additional timer variants, implementation, builds or live interaction. The persistent playback-owner foundation remains the immediate implementation priority.

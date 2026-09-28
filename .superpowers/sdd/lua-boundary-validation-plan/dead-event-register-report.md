# kp.events.register refuses undispatchable events

## Referent (round 1 + round 2)
`/home/brunner56/kp-live-20260922/blaster-authoring-review.md`: `l_register_callback`
(`src/api/compat.cpp:85`, now moved a few lines down by this change) returned
`true` for `kp.events.OnCreatureDamaged`. `OnCreatureDamaged` has a non-empty
lua_name (`src/generated/events.inc:168`) but `outer_event_id == -1`, so
`events::find_by_site` (`src/events/table.cpp`) can never return it and no
hook body ever raises it. A script believed its handler was armed; it never
ran.

## Ruling implemented
Registration of any event no dispatch site can raise now returns `false` and
logs the same one-line `Warn` the empty-lua_name case already used, naming the
event. Derived from the contract table, not a hardcoded per-name list.

## Why "no hardcoded names" needed one small exception
The literal rule "derive from the table find_by_site uses" cannot, by itself,
separate `OnCreatureDamaged` (dead) from `OnScriptLoad`/`OnRunScript`/`OnTick`/
`OnConsoleCommand`/`OnRunScriptDone`/`OnSave`/`OnLoad` (all live, all with
`outer_event_id == -1` too). Those eight are dispatched by hook bodies calling
`find_contract("Name")`/`events::find("Name")`/`Host::set_lifecycle(...)`
directly, by name, never through `find_by_site`. That fact lives in the C++
call sites, not in the table, so it cannot be derived from table data alone.

- `src/events/table.cpp`: new `bool dispatchable(const EventContract&)`.
  - `outer_event_id >= 0` → delegates to `find_by_site` itself (`find_by_site(ev.hook_site, ev.outer_event_id, ev.event_type) == &ev`), the literal single source of truth for that half, catching a contract shadowed by an earlier one with the same key too.
  - `outer_event_id == -1` → checked against `kDirectDispatchNames[]`, an 8-entry list built from `grep -rn 'find_contract(\|events::find(\|set_lifecycle' src/` (checked, referent below) — this is the live set the runtime already hardcodes at its call sites, not a new dead-name list, and it is identical for K1 and K2 since both link the same hook bodies.
- `src/api/compat.cpp` `l_register_callback`: after the existing empty-lua_name check, looks up `events::find(event)` and rejects (same Warn, different wording) when the contract is null or `!events::dispatchable(*contract)`.
- `src/events/table.hpp`: declares `dispatchable()` with a comment explaining the two-part derivation so the exception doesn't look accidental later.

## Referent for the 8-name direct-dispatch set
```
$ grep -rn 'find_contract(\|events::find(\|set_lifecycle' src/ --include=*.cpp --include=*.hpp
```
Hits only in `src/runtime/runtime.cpp` and `src/runtime/hook_bodies.cpp`, naming
exactly: `OnScriptLoad`, `OnScriptUnload`, `OnConsoleCommand`, `OnRunScriptDone`,
`OnSave`, `OnLoad`, `OnTick`, `OnRunScript`. No hits in `src/lua/`,
`src/multiplayer/`, `src/devtools/`, or `src/harness/`.

## K1 vs K2
`data/events.toml` has a single `[meta] game = "k1"` table; there is no
separate K2 event contract table, and `kDirectDispatchNames` names call sites
in `src/runtime/*.cpp` that are shared by both game builds. So `dispatchable()`
is the same function, same table, same answer for both games today. If a K2-only
divergent contract table is ever added, this helper needs a second look --
noted rather than assumed away.

## Tests (red-first, confirmed)
`tools/kp_namespacetest.cpp` (offline, no game/Wine; runs under both
`argv[0]` == K1 default and `k2` arg):
- Table-wide assertion: for every contract in `events::table()`, `dispatchable()`
  agrees with a hardcoded 14-name expected-dead list taken from
  `docs/user/api-status.md` "Dead names", and all 14 are present in the table.
- `kp.events.register(kp.events.OnCreatureDamaged, fn) == false` (dead, `vm.run_script` site, outer -1).
- `kp.events.register(kp.events.OnDialogConditional, fn) == false` (dead; shares `OnRunScript`'s arg shape `arg1 CExoString*`, proving the check is not an arg-source heuristic).
- `kp.events.register(kp.events.OnCreatureAttacked, fn) == true` (live, `find_by_site` path, outer id 15, no signal-event type check).
- `kp.events.register(kp.events.OnModuleHeartbeat, fn) == true` (live, `find_by_site` SIGNAL_EVENT path, outer 10 + type 0).

Red-first, checked: with the new `contract == nullptr || !events::dispatchable(*contract)`
block temporarily `#if 0`'d out, the same binary produced:
```
FAIL: [string "assert(kp.events.register(kp.events.OnCreatur..."]:1: assertion failed!
FAIL: [string "assert(kp.events.register(kp.events.OnDialogC..."]:1: assertion failed!
namespace contract: 2 failure(s)
```
Restored the block, rebuilt, reran: `namespace contract: 0 failure(s)` for
both K1 (no arg) and K2 (`k2` arg) invocations.

## Build (checked)
- Native 32-bit (`-m32`, this repo's whole-project standard): `cmake --build tmp/lifecycle-cfg --target kp_namespacetest` — built and ran clean both ways above. Ran through `/home/brunner56/.local/bin/host-cmd` since the binary is a 32-bit ELF the container can't exec directly.
- Windows cross-compile of the two changed files, direct `i686-w64-mingw32-g++ -std=c++20 -Wall -Wextra -O2` invocations (via `host-cmd`, matching the flags `src/runtime/runtime.cmake` uses for the win32 object list) against `src/api/compat.cpp` and `src/events/table.cpp`: both exit 0, no warnings. Did not complete a full `kphasor_dll` mingw relink (that target rebuilds ~100 unrelated translation units and the shared build host was intermittently slow/flaky today with stray hung `g++` processes from concurrent sessions); the targeted per-file mingw compiles are the direct evidence for "these two files parse and compile under the Windows toolchain," which is what changed.

## Callers checked (not edited)
```
grep -rln '\bOnCreatureHeartbeat\b|\bOnCreatureSpawn\b|...' scripts/examples scripts/demos tools/tests
```
one name at a time for all 14 dead names. Findings:
- No script anywhere calls `kp.events.register` on a dead name. Every hit in
  `scripts/examples/**` (`probe/00_probe.lua`, `cursed/30_necromancer.lua`,
  `cursed/40_chain_reaction.lua`, `cursed/README.md`) is either a legacy
  global `function OnCreatureDeath(...)` definition (the discovery path this
  ruling doesn't touch) or prose already documenting the name as dead and
  matching on `script_name` via `OnRunScript` instead.
- `scripts/demos/object-blaster/object_blaster.lua` mentions `OnCreatureDamaged`
  only in a comment; it registers `OnCreatureAttacked`, not the dead name.
- `tools/tests/examples/object_blaster.lua` (a Lua-level mock harness, not the
  real compat.cpp) is the one file that actually exercises the *old* contract:
  its mock `kp.events.events.register` (lines 72-80) always returns `true` "to
  model" the pre-fix behavior, and a test at lines 208-224 titled
  `"OnCreatureDamaged is registerable but this fixture never dispatches it..."`
  asserts `ok == true` with a comment citing the exact bug this change fixes.
  Both the mock and the assertion are now stale documentation of a bug that no
  longer exists. Left untouched per scope (`tools/tests/**` callers are to be
  reported, not edited); flagged as a background task
  (`task_16ed1d58`, "Update object_blaster mock to match fixed dead-event
  register()") for a follow-up session to align the mock and invert the
  assertion.

## Counts / files
- Dead names: 14 (unchanged from `docs/user/api-status.md`, cross-checked
  programmatically in the new test).
- Files touched: `src/api/compat.cpp`, `src/events/table.hpp`,
  `src/events/table.cpp`, `tools/kp_namespacetest.cpp`,
  `docs/user/api-status.md`, `docs/lua-api.md`.
- Dead-name callers found: 0 in `scripts/**`; 1 in `tools/tests/**`
  (`tools/tests/examples/object_blaster.lua`, mock only, flagged not edited).
- No git writes made; worktree left dirty as instructed.

## Grill me

**Q: Why is `kDirectDispatchNames` not itself a violation of "do not hardcode names"?**
A: It hardcodes the *live* set (8 names the runtime already hardcodes as
literal string arguments at its own call sites — `find_contract("OnTick")` etc.
in `src/runtime/hook_bodies.cpp`/`runtime.cpp`), not a *dead* list someone has
to keep in sync with 14+ growing dead names. Adding a 9th event dispatched by
name would need a 9th call site in the runtime anyway, and `dispatchable()`
would need updating alongside it — same coupling that already exists, not new
coupling. Referent: `grep -rn 'find_contract(\|events::find(\|set_lifecycle' src/`
— checked, matches the 8-name list exactly, confirmed no hits outside
runtime.cpp/hook_bodies.cpp.

**Q: Could `find_by_site` itself change behavior since `dispatchable()` now calls it from `l_register_callback`'s hot path?**
A: No: `find_by_site` was already called on every real dispatch (`event_handler_common`
in `hook_bodies.cpp:1065`); `dispatchable()` calls it once per `register()`
call, which happens at script load, not per-frame. Unverified for actual
runtime perf since this was checked with the offline `kp_namespacetest` only,
no live game — but the call graph makes a measurable cost implausible.

**Q: Does the table-wide test in `kp_namespacetest.cpp` hardcode the exact same
information `dispatchable()` computes, making it circular?**
A: No — the test's `kExpectedDead[]` is transcribed from `docs/user/api-status.md`
prose (an independent, human-curated document derived from decompiled-engine
evidence in `data/events.toml`), not from `table.cpp`'s `kDirectDispatchNames`.
If someone edits `dispatchable()` to (wrongly) mark a 15th event dead,
or a doc-list name diverges from the table, the test's cross-check catches
it. Referent: `tools/kp_namespacetest.cpp` table-wide assertion block, checked
green in this session.

**Q: Full mingw `kphasor_dll` relink was not completed — is that a real gap?**
A: Weakest point. I did confirm the two changed files compile clean under
`i686-w64-mingw32-g++` with the project's exact flags, but I did not confirm
the full DLL still links (symbol visibility, ODR across TUs) under mingw.
The shared build host had stray hung `g++`/mingw processes from concurrent
sessions today (`ps aux` showed zombies from 11:32 and 19:19 predating this
session), and a from-scratch `kphasor_dll` rebuild is ~100 files; I killed my
attempt after per-file compiles gave a fast, high-confidence signal instead
of continuing to fight the shared host. Unverified: whether `kphasor_dll`
links clean end-to-end after this change on this host, right now.

Grill me.

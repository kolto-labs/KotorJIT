# KotorPhasor client/server side audit

KotorPhasor binds both logical halves of the game. Its primary Lua event hooks are server-side; its rendering, camera/model/animation, GUI and capture paths reach client-side objects. In an ordinary embedded game these objects share one process. Native split Client/Server process roles and the external harness TCP client are separate concepts.

Audited checkout: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`, branch `codex/lua-boundary-validation`, HEAD `ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2` plus its current dirty working tree. This is a current-source classification, not a claim that HEAD alone contains the audited implementation. No live game, Wine, display, or network-session acceptance test was run for this audit.

## Authoritative inventory

[Combined 201-name Lua function and userdata inventory](/home/brunner56/kp-live-20260922/side-audit/lua-functions.md). [Automated coverage receipt](/home/brunner56/kp-live-20260922/side-audit/coverage-check.json).

- [Native Lua functions and userdata operations](/home/brunner56/kp-live-20260922/side-audit/lua-api.md), [JSON](/home/brunner56/kp-live-20260922/side-audit/lua-api.json): native API entries, typed wrappers, value helpers, NWScript bridge and speed controls. Explicitly separates direct native object access from semantic-only or unresolved per-routine routing.
- [Generated native routine boundary](/home/brunner56/kp-live-20260922/side-audit/native-routines.md), [all names](/home/brunner56/kp-live-20260922/side-audit/native-routines.json): every callable K1/K2 signature, with exact native-handler routing explicitly unresolved.
- [Auxiliary Lua API](/home/brunner56/kp-live-20260922/side-audit/auxiliary-api.md), [JSON](/home/brunner56/kp-live-20260922/side-audit/auxiliary-api.json): script lifecycle, event registration, harness Lua convenience functions and compatibility utilities.
- [Every event](/home/brunner56/kp-live-20260922/side-audit/runtime-events.md), [JSON](/home/brunner56/kp-live-20260922/side-audit/runtime-events.json): 111 public event names; 94 server hooks, one client console hook, two process-local lifecycle callbacks, and 14 dead names with no dispatch.
- [Every Lua script](/home/brunner56/kp-live-20260922/side-audit/scripts.md), [JSON](/home/brunner56/kp-live-20260922/side-audit/scripts.json): 55 files under scripts/ and tools/, including 38 under scripts/ and 17 under tools/. Script purpose/route, test-only and retired status, hashes, named helper definitions, callback definitions, and native call literals are retained. Internal helpers are inventoried by containing file, not falsely claimed as individually traced native implementations.
- [Every harness command](/home/brunner56/kp-live-20260922/side-audit/harness.md), [JSON](/home/brunner56/kp-live-20260922/side-audit/harness.json): all 46 TCP commands, six devtools operations, external CLI, and 37 Python modules containing 776 top-level/class function definitions. Python functions execute outside the game; invoked native command/Lua/input route determines game-side effects.
- [Accuracy review](/home/brunner56/kp-live-20260922/side-audit/quality-review.md): independent source checks and corrected thread-label distinction.
- [Completeness review](/home/brunner56/kp-live-20260922/side-audit/spec-review.md): source-to-inventory reconciliation and corrections.

Public Lua functions means the functions/methods exposed to scripts by KotorPhasor. The hundreds of generated NWScript routine signatures describe native engine functions; they are not hundreds of separate KotorPhasor implementations. `nwscript.call` proves VM dispatch, not the exact side of every native routine. The same caution applies to a script's fade or speech request: client-visible purpose is not proof that the Lua code directly accesses a client object.

`*-extracted.json` are discovery notes, not authoritative inventories. Their initial lexical scans omitted common q/pcall wrappers; the final scripts.json replaces them. `build-root-inventory.py` reproduces the root script/harness inventories from source.

## Important distinctions

- `kp.speed`: server MainLoop repetition; `kp.game_speed` / harness `speed`: client game-speed path.
- Model/animation writes target client models. Optional ownership checks can read server identity. Identity lookup itself is profile-dependent (K1 GOG server lookup, macOS client fallback).
- Motion relocation targets a server placeable; its observation is not a verified client-position read.
- A Lua function is not automatically forwarded to a remote authoritative server merely because split transport exists. Direct memory and the captured VM belong to the process containing the injected library.
- The avatar-sync Lua example uses its own symmetric UDP side channel and local ghost creatures. It is separate from native split-process transport and does not synchronize full gameplay/world state.
- Published event names with no dispatch remain unimplemented even when examples define callbacks with those names.

## Review result

Completeness and source-accuracy reviews are approved after correcting omitted utility registrations, harness wrapper side labels, optional model ownership checks, console-buffer routing, and Lua caller-thread semantics. Coverage checks pass. The remaining unresolved entries describe absent native-handler evidence; they are not silently classified by their names.

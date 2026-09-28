# Side audit specification review

Date: 2026-09-27. Read-only review of the corrected side-audit artifacts against the current worktree source. No build, engine, Wine, display, harness, or lock action was run. This review wrote only this report and the subsequent `quality-review.md`.

## Specification completeness verdict: APPROVED

The corrected artifact set is complete as an inventory specification. The auxiliary JSON now contains 65 callable rows, including the three compat registrations previously missing from the main API manifest. Its complete callable union has no remaining source-registration omissions.

The raw native API surface is 139 names: 136 in `lua-api.json` (107 normal names plus 29 metamethod names) plus these three direct compat callables:

- `kp.print` — [src/api/compat.cpp:948](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:948)
- `kp.gamedir` — [src/api/compat.cpp:958](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:958)
- `kp.time` — [src/api/compat.cpp:960](/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/api/compat.cpp:960)

The full callable union is 201 names after adding the 65 auxiliary rows to the 136 main-manifest names. The auxiliary artifact’s union check reports zero remaining missing source callable registrations.

## Independent coverage checks

| Surface | Source referent | Artifact | Result |
|---|---|---|---|
| Lua files | `scripts/**/*.lua`, `tools/**/*.lua` | `scripts.json` | Exact: 55 source files, 55 listed, no missing or extra paths. |
| External Python harness | `scripts/harness/kpharness/*.py` | `harness.json` | Exact: 37 modules and 776 top-level/class function definitions. |
| TCP command dispatch | `src/harness/commands.cpp` | `harness.json` | Exact: all 46 command names match the dispatch chain. |
| Devtools protocol | `src/harness/console_protocol.cpp` | `harness.json` | Six operations listed: status, submit, outcome, output, complete, cancel. |
| Runtime event catalog | `data/events.toml` | `runtime-events.json` | Exact: all 111 event names match. |
| Native callable registrations | `src/api`, `src/runtime` registration paths | `lua-api.json` + corrected `auxiliary-api.json` | Exact source union: 139 raw native names and 201 callable names including auxiliary namespaces. |
| NWScript callable catalog | generated K1/K2 routine arrays | `lua-api.json` | K1 769 callable / 772 catalog; K2 803 callable / 877 catalog. Unsupported action-closure routines remain explicitly outside the callable set. |

The runtime-event artifact now reports 97 implemented rows—94 server, one client, and two process-local lifecycle rows—and 14 unimplemented/dead rows, for 111 catalog rows total. This is a status count; it does not imply live profile resolution or runtime success.

The 14 dead public event names are retained as generated constants but rejected by registration because they have no dispatch site. The artifact identifies them explicitly rather than treating their constants as implementation.

## Architecture scope accepted

The corrected artifacts distinguish:

- Lua process/registry ownership from logical engine object side.
- Caller/execution thread from the side of the object or UI being accessed.
- Direct client-to-server requests from server mutations and from process-local stored-result polling.
- Embedded client/server state from split-role transport and authority.
- Event registration time from later callback dispatch side.

The corrected auxiliary rows trace `kp.harness.*` to the same adapter implementations as `harness.json`, including client GUI, server mutation, mixed, client-to-server request, process-local result, and process-local metadata cases. `kp.scripts` lifecycle requests are marked deferred where `Host::request` queues work for later service. The artifact does not count event constants or generated routine signatures as callable implementations.

## Remaining boundary

Completeness is approved for the static specification. Accuracy and wording risks are handled separately in [quality-review.md](/home/brunner56/kp-live-20260922/side-audit/quality-review.md); they do not represent missing inventory rows. The specification remains source/static evidence and does not claim a bound profile, installed hook, successful engine call, live callback, or external-client acceptance.

## Grill me, weakest first

1. The strongest completeness evidence is the corrected source-registration union: zero missing callable names, 139 raw native names, and 201 including auxiliary callable namespaces.
2. The event total is exact, but 97 implemented means 94 server + 1 client + 2 process-local lifecycle rows; the 14 remaining rows are deliberately unimplemented/dead.
3. Static registration and catalog matches do not prove runtime behavior. That limitation is explicit and is the subject of the separate quality pass.

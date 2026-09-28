# Shared console service contract

`kp::devtools::Console` is the single native F12 console interpreter and engine-thread queue. This contract adds structured results and request-specific cancellation for native clients and future transports. There is no second evaluator, browser transport, browser runtime, expandable object registry or JSON dependency in the service.

The current F12 overlay and legacy harness continue using their existing APIs. The additive C++ API is available in `src/devtools/console.hpp`:

| Operation | Contract |
| --- | --- |
| `status()` | Atomic snapshot of session, submitted/completed IDs, running flag, queue count and output counters. |
| `submit(session, source)` | Receipt containing current session, accepted request ID, or `StaleSession`, `QueueFull`, `SourceLimit` rejection. Rejection does not create an accepted request. |
| `outcome(session, request)` | `Found` with an explicit request state, or `StaleSession`, `Expired`, `Unavailable`. |
| `snapshot(session, after_sequence)` | Bounded output after a cursor, current sequence, cumulative dropped-line count and dropped-through sequence. A stale session is rejected. |
| `cancel(session, request)` | Exact-request queued cancellation or cooperative running cancellation, with explicit status described below. |
| `complete(prefix)` | Existing bounded owner-generated raw-table name snapshot. It never evaluates an expression or invokes getters. |
| `reset()` | Owner-thread lifecycle operation, with no pump on the stack. Invalidates the previous session, drops its queued work/results/output/completion names and closes its Lua state. |

Each Console instance and reset receives a fresh process-local session epoch. Request IDs are monotonically increasing for the lifetime of an instance, including across reset. Epochs distinguish independent instances in the same process; a future transport must additionally identify its runtime instance across process restarts. A matching request number never overrides a stale-session check. `Unavailable` means the ID was not accepted in this session; `Expired` means its terminal outcome was evicted. Accepted pending/running outcomes are retained independently of terminal eviction.

`completed` is the legacy contiguous terminal watermark within the current session. It advances only below the earliest pending/running request, so cancelling a later queued request cannot make an earlier request appear finished. The bounded queue and active request determine this watermark independently of terminal-outcome eviction. Zero means no terminal prefix in this epoch. It still does **not** establish success or replace `outcome()`; use the explicit state for the exact session/request.

## Request states and errors

Accepted requests start `Pending`, become `Running` only when the engine owner dequeues them, and publish one terminal outcome: `Succeeded`, `Failed` or `Cancelled`. A queued cancellation transitions directly from `Pending` to `Cancelled`. The existing engine pump remains the only interpreter executor. There are no blocking waits on the engine thread in this service.

An outcome contains session/request, state, typed return values, original return count, truncation flag, structured error and first/last associated output sequence. Structured error codes are `lua_syntax`, `lua_runtime`, `instruction_budget`, `cancelled` and `allocation`. Runtime errors retain a bounded Lua traceback; parse errors retain their parser text. Result consumers never parse the overlay's readable text to determine state or data.

Output continues to have `kind`, `text` and `request`, now with `session` and monotonic `sequence`. Request zero is explicitly unattributed output. Submission rejections and diagnostics from another thread never borrow an executing command's ID. A request's first/last output span may include intervening rows from another source; filter by session/request. Output can be evicted independently while an outcome remains retained. `dropped_through` lets a cursor client detect that part of its requested range is no longer available; repeated identical text still has distinct sequence numbers.

## Typed return values

Values come directly from the live Lua stack before it is cleared:

- `Nil`: retains its exact tuple position. An empty return list is `values=[]` with `return_count=0`, distinct from one nil return.
- `Boolean`: stores the boolean directly, including false.
- `Number`: stores a finite Lua number as a C++ double, or an explicit `NaN`, `PositiveInfinity`, `NegativeInfinity` tag. Finite signed zero remains available in the double. No integer precision beyond the actual LuaJIT numeric value is invented.
- `String`: stores raw bytes with original byte length and truncation flag. Embedded NUL, invalid UTF-8 and arbitrary byte sequences are valid. These are not implicitly converted to text.
- `Opaque`: stores only the Lua type name, such as table, function, userdata, thread or cdata. `inspection_available=false`. There is no address, object handle, registry retention or getter evaluation in this descriptor. The existing human-readable overlay formatter remains unchanged.

At most 64 leading values are retained, preserving those positions. `return_count` reports the original tuple length, and `returns_truncated` marks omitted values or truncated strings. Each stored string is capped at 8192 bytes; strings in one outcome share a 32768-byte budget. Error text is capped at 8192 bytes with an explicit truncation flag.

Terminal retention is capped independently at 128 outcomes and a 256 KiB accounted-content budget (outcome/value record sizes plus their stored strings). Container bookkeeping is separately bounded by that count. Pending/running metadata is bounded by the existing 16-entry queue and one execution. Output remains capped at 512 rows/256 KiB with existing per-row truncation. An evicted terminal becomes `Expired`; a missing outcome never implies success.

## Cancellation and lifecycle

`cancel(session, request)` returns:

- `Cancelled`: that queued request was removed and has a confirmed terminal cancelled outcome. Other queued requests keep their order.
- `Requested`: that exact running request received a cooperative cancellation flag. This is acknowledgement of a request, **not** confirmation that execution stopped.
- `AlreadyTerminal`, `StaleSession`, `Expired` or `Unavailable`: explicit non-action statuses.

The owner clears cancellation before publishing `Running`, under the same mutex used by cancellation and outcomes. It never clears it afterward inside the evaluator. A cancellation cannot spill into the next request. Legacy `cancel()` requests cancellation only for the currently active request; it does not cancel a future command.

A running cancellation becomes confirmed only through the terminal outcome. If a command finishes before observing the flag it can still succeed. Lua instruction hooks distinguish cancellation from instruction-budget exhaustion. The existing one-million-instruction budget disables/flushed LuaJIT traces; neither mechanism preempts blocking native calls or intentionally bypassed hooks. A synchronous future Wasm worker cannot receive an ordinary message while blocked unless it yields; transporting this API does not solve that scheduling limit.

`pump()` and `reset()` require the established engine owner; reset must not run concurrently or reentrantly with pump. Thread-safe observation, submission and cancellation do not touch Lua. Reset invalidates pending observations by changing epoch; clients must reject/reconcile old pending operations rather than silently replaying mutations. This does not add reusable overlay hot-restart/unload support.

## Future serialization boundary

No wire transport is implemented in this slice. Any JSON/JavaScript adapter must encode sessions, request IDs, sequence counters and original byte counts as decimal strings, avoiding JavaScript integer precision loss. Raw strings must use a lossless byte representation such as base64 plus byte length. Nonfinite numbers require explicit tags; signed negative zero needs an explicit representation if the chosen JSON encoding would discard its sign. Opaque descriptors must remain non-inspectable until a real bounded reference service exists. Adapters must preserve the state/error distinctions above and must not infer terminal outcomes from output text or watermarks.

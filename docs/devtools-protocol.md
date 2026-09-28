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

## Harness wire protocol: `kp.console.v1`

The existing `devtools` command accepts an explicit `protocol="kp.console.v1"` opt-in. Requests without `protocol` retain the shipped legacy response shapes and cancellation behavior. Unknown or malformed protocol values refuse; they never fall through to legacy cancellation. The adapter is in `src/harness/console_protocol.cpp`; it uses the same Console queue, outcomes and Lua state. It does not evaluate, pump, reset, or block waiting for execution.

Begin with `{"cmd":"devtools","protocol":"kp.console.v1","op":"status"}`. The usual harness transport `id`/`ok` envelope is unchanged. The result contains `protocol`, `runtime`, `status="Found"`, `session`, `submitted`, `completed`, `running`, `queued`, `last_line`, `dropped_lines`, `open`, and `input_calls`. Every ID, counter and byte length is a canonical unsigned64 decimal **string**. `running` and `open` are booleans. Runtime is an opaque process-instance nonce, not a pointer or authentication credential. Entropy initialization failure disables only the versioned adapter with an explicit error; legacy remains available.

All subsequent operations require that exact `runtime` and a nonzero decimal-string `session`. A supplied mismatching runtime returns `status="StaleRuntime"` before any Console mutation. Status can omit runtime for initial discovery, or include it to detect restart. Reset is not a wire operation. Session resets are detected by the service's `StaleSession`; never silently replay an old mutation against a fresh identity.

| `op` | Additional request fields | Result beyond `protocol` and `runtime` |
| --- | --- | --- |
| `status` | None; optional runtime | Snapshot fields above. No session precondition: compare returned session with the captured baseline. |
| `submit` | `code`: JSON source string | `status`: None/StaleSession/QueueFull/SourceLimit; `session`, `request` strings. None means accepted, not executed. Rejection request is zero. |
| `outcome` | `request`: nonzero decimal string | `status`: Found/StaleSession/Expired/Unavailable; Found adds `outcome` object. |
| `output` | `after_sequence`: decimal string, zero allowed | `status`, `session`, `last_sequence`, `dropped_lines`, `dropped_through`, `lines`. |
| `complete` | `prefix`: string, at most16384 bytes | `status`: Found/StaleSession; Found adds `names` byte objects. No getters/evaluation. |
| `cancel` | `request`: nonzero decimal string | `status`: Cancelled/Requested/AlreadyTerminal/StaleSession/Expired/Unavailable. Requested is not terminal proof. |

Malformed numeric IDs, leading zeros, signs, whitespace, overflow, missing required fields and numeric JSON IDs refuse with the existing `ok=false` envelope. Exact strings above2^53 are preserved. Service lookup/rejection states are ordinary `ok=true` results whose `status` must be inspected.

A Found `outcome` contains `session`, `request`, `state`, `values`, `return_count`, `returns_truncated`, `error`, `first_line`, `last_line`. State is Pending/Running/Succeeded/Failed/Cancelled. `error` has `code`, byte-object `text`, and boolean `truncated`. All outcome field semantics and retention limits are those described above; a completed watermark never replaces this exact lookup.

Each raw byte object is `{"encoding":"base64","data":"...","byte_length":"N"}`, where N is the number of retained decoded bytes. Output lines carry session/request/sequence decimal strings and byte-object `kind` and `text`. Error messages and completion names also use byte objects; embedded NUL and non-UTF8 therefore remain valid lossless JSON. `String` values additionally have `original_bytes` and `truncated`, distinguishing retained bytes from original length. Existing output-line truncation remains the Console's readable truncation marker plus retained line bytes; the adapter does not invent an unavailable original line length.

Typed values:

- `{"type":"Nil"}` retains tuple position; no-return is an empty array and return_count zero.
- `{"type":"Boolean","value":false}` preserves false.
- `{"type":"Number","kind":"Finite","value":42}` carries the actual finite Lua double. NaN/PositiveInfinity/NegativeInfinity/NegativeZero use explicit `kind` with no numeric `value`.
- `{"type":"String","bytes":{"encoding":"base64","data":"AP9B","byte_length":"3"},"original_bytes":"3","truncated":false}` is bytes00ff41.
- `{"type":"Opaque","lua_type":<byte object>,"inspection_available":false}` has no address, handle or object expansion.

For physical-console correlation capture runtime/session/submitted before keyboard input, demand exactly one newly submitted request in that identity, and inspect that request's outcome. Query output from the prior last_line cursor and filter by session/request; check dropped_through before requiring complete output. Cancelled, expired, stale, missing output, duplicate submission and timeout remain separate failures. No direct submit or Lua channel call substitutes for actual keyboard input in a physical-console test. A timeout never authorizes automatic replay.

Transport scheduling: harness commands are serviced on the engine owner thread. The thread-safe Console cancellation API does not make this wire endpoint preempt an engine/native call that blocks that thread. Exact cancellation semantics apply when the command is serviced. Native service concurrency tests do not establish live RPC preemption. Ordinary Lua remains subject to its existing instruction budget; no network-thread execution bypass is added.

## Browser bridge

`kpharness devtools-bridge --standalone --port PORT` serves a dependency-free
page and an authenticated HTTP transport over the same `kp.console.v1` ops.
It binds only to `127.0.0.1`, creates a 256-bit bearer token in the private
state directory, and prints the URL and token-file path without printing the
token. `POST /v1/console` accepts only `status`, `submit`, `outcome`, `output`,
`complete` and `cancel`; it forces `cmd=devtools` and
`protocol=kp.console.v1`, validates the canonical Host and Origin first, and
does not retry or replay an upstream request. Static files are restricted to
the checked-in `web/devtools/MANIFEST` allowlist.

The bridge is a transport adapter only: the native Console remains the sole
Lua evaluator, and decimal IDs and byte objects retain their wire forms. A
token grants the same authority as F12, including the existing Lua `os` and
`io` capabilities; use it only on a trusted local machine. Playback-owner
attachment is currently explicit unsupported mode because `playback.py` does
not yet publish a devtools forwarding API. Standalone mode owns one Channel
and exits on a busy engine; it never opens a second connection or retries.

`evaluate()` returns the accepted `runtime`, `session`, and `request` strings
alongside the native outcome. Target cancellation explicitly:
`await kotor.console.cancel({runtime, session, request})`. A bare request ID
is refused because request numbers can repeat in a different session. A
`Requested` cancellation response does not mean the outcome is terminal.
The client preserves native cancellation and completion statuses without
inventing session/request fields in those replies.

For publication, stage only the two files named in `web/devtools/MANIFEST`
into a separate directory, then run
`python3 -m scripts.harness.kpharness.devtools_bridge --check-publication STAGED_DIRECTORY`
from the source checkout. This compares the staged file set against the
source manifest and refuses missing files, extra files, and symlinks. Do not
copy the source directory wholesale: it also contains host tests and the
manifest itself, which are not publication files.

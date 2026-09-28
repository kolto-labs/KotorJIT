# Supported harness console integration audit

Read-only, bounded audit of task-7 brief, Console implementation/header, devtools protocol, command adapter and Python Channel. No builds or game runs.

## Main finding

Task12 is implemented as the C++ Console API, not yet exposed as a complete harness wire protocol. `src/harness/commands.cpp:711` cmd_devtools still implements only legacy status/submit/output/complete/global cancel. It does not expose session, outcome lookup, output sequence/cursor/drop metadata, or exact-request cancellation. Python-only extraction of the private driver cannot satisfy Task7; a small serialization adapter is necessary.

Existing supported wire examples (IDs and counters below illustrative):

    request: {"id":1,"cmd":"devtools","op":"status"}
    response: {"id":1,"ok":true,"result":{"submitted":4,"completed":4,"running":false,"queued":0,"open":true,"input_calls":50}}
    request: {"id":2,"cmd":"devtools","op":"submit","code":"return 42"}
    response: {"id":2,"ok":true,"result":{"request":5,"submitted":5,"completed":4,"running":false,"queued":1,"open":true,"input_calls":50}}

Output adds `lines:[{request,kind,text}]`; complete adds `names`; cancel has no target and acts only on currently running work. `op:outcome` currently fails with `unknown devtools operation`. The submit result proves queue acceptance, never evaluation success.

`Channel` lives in `scripts/harness/kpharness/client.py:49`. Use `ch.request("devtools", op="status")`; it allocates a transport ID, sends one newline-delimited JSON object, skips unrelated reply IDs while collecting events, returns result for ok=true or raises ChannelError for ok=false. Its transport ID is distinct from the Console request ID. Generic requests intentionally do not reconnect/replay mutations. Read-only wait helpers have session-owned reconnect support. Do not silently replay physical input or submit after timeout.

## Actual service semantics

`src/devtools/console.hpp` and console.cpp174 onward implement:

- status(): session, submitted, completed, running, queued, last_line, dropped_lines.
- submit(session, source): receipt session/request and rejection None/StaleSession/QueueFull/SourceLimit. Source max16384 bytes, queue16. Rejected requests allocate no request ID.
- outcome(session, request): Found with Pending/Running/Succeeded/Failed/Cancelled, or StaleSession/Expired/Unavailable. Expired is evicted accepted terminal data; Unavailable is never accepted in this epoch. Pending/running records are retained.
- terminal outcome: typed values, original return_count, returns_truncated, structured error(code/text/truncated), first_line/last_line. Error codes lua_syntax/lua_runtime/instruction_budget/cancelled/allocation.
- snapshot(session, after_sequence): session lookup, lines with session/request/sequence, last_sequence, dropped_lines, dropped_through. Filter lines by both session and request; output spans may include other sources. Request0 is unattributed. Missing output after eviction is not proof of no output.
- cancel(session, request): queued Cancelled is terminal; running Requested is only acknowledgement, must observe final outcome. Also AlreadyTerminal/StaleSession/Expired/Unavailable. A race with natural completion may still succeed.
- reset(): owner-thread only with no active pump; changes epoch, clears queue/results/output and Lua state; IDs remain increasing. Old session remains stale even when an ID resembles another result. Process restarts additionally need runtime instance identity.

The completed watermark is a contiguous terminal prefix, not success. Terminal retention128/256KiB; output512rows/256KiB; return64 values, each string8192 bytes and32768 total; errors8192 bytes. Strings are raw bytes, nil retains tuple position, booleans preserve false, numbers include explicit nonfinite tags, opaque results expose type only.

## Minimal proposed adapter examples — NOT existing wire syntax

Preserve legacy fields for existing clients; add lossless structured operations. New ID/counter fields must be decimal strings per docs/devtools-protocol.md; raw strings must carry base64+original byte count, explicit truncation, and finite negative zero/nonfinite handling.

    {"id":3,"cmd":"devtools","op":"outcome","session":"7","request":"5"}
    {"id":3,"ok":true,"result":{"lookup":"Found","session":"7","request":"5","state":"Succeeded","values":[{"type":"Number","kind":"Finite","value":42}],"return_count":"1","returns_truncated":false,"error":{"code":"","text":"","truncated":false},"first_line":"12","last_line":"12"}}

    {"id":4,"cmd":"devtools","op":"outcome","session":"6","request":"5"}
    {"id":4,"ok":true,"result":{"lookup":"StaleSession"}}

    {"id":5,"cmd":"devtools","op":"cancel_request","session":"7","request":"8"}
    {"id":5,"ok":true,"result":{"cancellation":"Requested"}}

Exact new wire naming should be fixed by implementation and documented, rather than claimed to exist today. Do not expose reset as an arbitrary concurrent operation.

Physical-console correlation: capture runtime/session and submitted watermark before input; ensure owned window/focus, perform actual F12 text submission, require exactly one newly accepted request in that same epoch, then poll its outcome. More than one new request is an ambiguous/duplicate-submission failure, not permission to select the latest. Verify expected typed result/error and request-scoped output. Missing output, expiration, stale session, cancellation, timeout, or unexpected extra submission must produce distinct failure receipts including last observed state. No direct channel submit/lua call may replace physical input for physical-console acceptance.

## Focused validation cases

1. Success with nil/false/42/raw embedded-NUL string and opaque type; no display-text parsing.
2. Syntax/runtime/budget errors are terminal failures even though completed advances; distinguish cancellation.
3. Queued exact cancellation never executes or affects its neighbors; running Requested waits for actual terminal result.
4. Reset between baseline/input/poll invalidates correlation; never retry mutation automatically. Runtime restart cannot reuse old process-local epoch assumptions.
5. Expired outcome and independently dropped output fail required evidence; Pending survives terminal churn.
6. Reject malformed/overflow IDs, stale submit, source limit and full queue without claiming accepted request.
7. Physical duplicate submission, unrelated request, missed Enter, timeout and reconnect ambiguity retain diagnostics and fail honestly.
8. Existing status/output consumers remain compatible; new serialization preserves counters above2^53 and arbitrary Lua string bytes.

Existing tools/kp_consoletest.cpp covers substantial service semantics already; add wire encoding/dispatch and supported Python driver tests. Those do not replace physical K1/K2 keyboard acceptance.

## advance_ticks

Already supported in repository CreativeRunner, `scripts/harness/kpharness/creative_steps.py:26–64`, selected by `creative.py:107`. It is not a native channel command nor a base ScenarioRunner verb. TOML: do="advance_ticks", ticks=integer1..100000, clock="server" or "client", timeout in(0,600]. It observes state tick progression, checks rollback, watchdog and timeout every0.2s. It does not force engine ticks or pause/resume. Reuse/extract this existing behavior; do not call it private-only or invent a native advance endpoint.

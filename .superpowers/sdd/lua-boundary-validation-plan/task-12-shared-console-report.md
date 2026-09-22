# Task 12: shared console outcomes

Implemented the native service prerequisite in the existing `Console`; F12, legacy submissions and the optional harness continue using the same engine-owned state and queue. No browser transport, second interpreter, JSON service dependency, object inspector, Wasm execution layer or additional editor UI was added.

## Changes

- Additive session-aware submission receipts, explicit pending/running/succeeded/failed/cancelled outcomes, stale/expired/unavailable lookup statuses and targeted cancellation.
- Typed values copied directly from the actual Lua stack: nil positions, booleans, finite/nonfinite numbers, arbitrary string bytes and type-only non-inspectable opaque descriptors. Independent tuple/string/error truncation metadata.
- Terminal retention bounded to 128 outcomes/256 KiB accounted content, independent of the existing output ring. Output lines now carry session/sequence; snapshots expose cursors and dropped counters.
- Reset invalidates the session, old queued work/outcomes/completion names/output, safely closes the state on its documented owner-thread boundary and preserves monotonic request IDs.
- Cancellation flag initialization moved under the request-state mutex before Running publication. Queued cancellation removes only its target; running cancellation distinguishes requested from confirmed. Concurrent rejection output is explicitly unattributed instead of borrowing the active command.

## Tests and limits

Expanded `kp_consoletest` uses real LuaJIT for interleaved logical-client state/order, exact typed tuples, nonfinite numbers, binary strings/truncation, opaque descriptors, no returns, structured parser/runtime/budget failures and recovery, outcome/output eviction, queued cancellation without side effects, stale-session reset and monotonic IDs. A synchronized Lua C-function gate plus second client thread verifies Running observation, a full-queue rejection attributed to request zero, exact running cancellation and successful execution of the following command. The C gate is test-only and bounded by a three-second timeout; production adds no blocking wait.

Focused test passed in 0.03 seconds. Native32 and MinGW shipping targets built. Final frozen hash/build receipt follows after final verification. Controller owns later live acceptance and independent review. No browser execution proof is claimed. Native-call cancellation and deliberate Lua-hook bypass remain unsupported; overlay hot restart and reference inspection remain outside scope. Protocol documentation specifies decimal-string wire IDs and lossless binary/nonfinite representations for future adapters.

## Final candidate

Native32 `kphasor`, MinGW `kphasor_dll` and expanded focused `kp_consoletest` passed after final source edits. CTest elapsed 0.04 seconds. Build receipt: `/tmp/kp-task12-final-build.log`.

Frozen DLL: `/home/brunner56/kp-validation-20260922-build/kphasor-task12.dll`.

SHA256: `42285b0c2d640472ebc8db61e2c0b881d74e3de545b6fb5d2aa693fcf56a0b62`.

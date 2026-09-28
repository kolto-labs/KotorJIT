# Review findings: review-threading-safety

Independent read-only review of the harness, run 2026-09-09 against the
implementation in src/harness/ and scripts/harness/kpharness/. Findings are
ranked most severe first. Items already fixed are noted in the repository
history; the rest stand as known issues.

1. **`src/runtime/hook_bodies.cpp:233-254, 293-315, 641-675, 749-772`; `src/harness/commands.cpp:541-675`; `src/api/routines.cpp:298-327` — blocker.** Armed guards enclose Lua dispatch, reload callbacks, and `kotor.*` VM calls. A script engine call faults, the guard claims it, and `longjmp` exits through engine/VM state without destructors. **Fix:** keep all Lua/host work that can reach the engine outside armed guards; guard only pure parsing, serialization, and safe probes.

2. **`src/runtime/runtime.cpp:545-565`; `src/lua/host.cpp:260-266, 290-294` — blocker.** `Runtime::start()` runs on the bootstrap worker, but `Host::load_all()` and `OnScriptLoad` execute Lua there. A callback calling `kotor.*` reaches the game VM from the wrong thread; `live` is also published before `OnScriptLoad` completes. **Fix:** perform script loading/callbacks on the game thread and publish `active_host`/`live` only after lifecycle initialization.

3. **`src/runtime/runtime.cpp:620-631`; `src/harness/commands.cpp:946-976, 995-1002` — blocker.** The worker publishes non-atomic `g_channel` while the client-loop hook reads it. Startup can race with `drain()`, producing a C++ data race or invalid pointer access. **Fix:** publish through synchronized ownership/atomic shared state, or initialize/publish the channel from the game thread.

4. **`src/harness/channel.cpp:247-258` — blocker.** Native Linux `FD_SET()` is used without checking descriptors against `FD_SETSIZE`. An inherited high-numbered descriptor writes past `fd_set`, corrupting memory. **Fix:** reject descriptors at startup or use `poll`/`epoll`.

5. **`src/harness/channel.cpp:269, 315, 325` — blocker.** Linux `send()` omits `MSG_NOSIGNAL`; a peer disconnect between `select()` and `send()` can deliver `SIGPIPE` and terminate the game. **Fix:** use `MSG_NOSIGNAL` or install an appropriate process-wide `SIGPIPE` policy.

6. **`src/harness/channel.cpp:177-189, 230-240, 299-310` — blocker.** Request and reply queues have no aggregate bound. A client can enqueue unlimited valid lines, or stop reading while replies accumulate in `replies_`/`outbuf_`, exhausting process memory. **Fix:** enforce byte/count limits and disconnect or reject when full.

7. **`src/harness/fields.hpp:325-374, 410-454`; `src/harness/engine_k1.cpp:496-500` — blocker.** GFF/ERF offsets are added before bounds checks. On a crafted save, 32-bit addition wraps, validation passes, and `bytes.data() + offset`/`write()` accesses outside the vector. **Fix:** validate with subtraction (`offset <= size && length <= size - offset`) before every addition and copy.

8. **`src/harness/channel.cpp:223-334` — blocker.** Allocation failures from `inbuf_.append`, queue `push_back`, `outbuf_ +=`, or logging escape the listener thread and invoke `std::terminate`, killing the game. **Fix:** bound allocations and catch/report failures at the thread boundary without touching engine state.

9. **`src/harness/channel.cpp:132, 269-272` — blocker.** `set_nonblocking()` failures are ignored. The accepted client remains blocking, and the busy-client `send()` is explicitly performed on a blocking socket; a non-reading second client can hang the listener and make `stop()` block in `join()`. **Fix:** check every nonblocking conversion and use bounded/nonblocking busy responses.

10. **`src/harness/channel.cpp:201-220, 230-240, 324-331` — major.** `wait_flushed()` checks only `replies_`, not listener-private `outbuf_`. It can return after the reply has moved into `outbuf_` but before transmission; `stop()` then joins and exits without flushing it, losing the `quit` reply. **Fix:** expose an acknowledged flush condition covering both queues and `outbuf_`.

11. **`src/runtime/runtime.cpp:221-235, 249-250, 556, 589, 660`; `src/runtime/runtime.hpp:70-72` — major.** `phase_` and related runtime strings are read by hook/status/log threads while startup/shutdown writes them without synchronization. **Fix:** protect lifecycle fields with a mutex or atomics/snapshots.

12. **`src/runtime/runtime.cpp:228-234` — major.** The log spin lock is held across file I/O while callers may be inside an armed guard. A fault or non-local exit during logging skips the unlock; fault recovery then logs and spins forever. **Fix:** avoid lock-protected fallible I/O inside guarded regions, or use an RAII-independent/nonblocking logging path.

13. **`src/harness/json.cpp:56-60`; callers at `src/harness/commands.cpp:604-607, 711, 737, 767` — major.** Finite JSON numbers outside `int64_t` range are directly cast, which is undefined behavior. A request such as `1e20` can produce arbitrary slots, indices, or rates. **Fix:** check `INT64_MIN <= number <= INT64_MAX` before conversion, and range-check subsequent `int` conversions.

14. **`src/harness/commands.cpp:870-883` — major.** `parse_error` is written inside an armed guard and read after it. If a fault occurs during that write, its `std::string` state is indeterminate under the documented `longjmp` contract. **Fix:** reset `parse_error` in the guard fallback and use only fallback-owned state after recovery.

15. **`src/harness/commands.cpp:132-138` — major.** `engine()` increments hook-body depth but is not exception-safe. An adapter allocation/standard-library exception exits without `leave_hook_body()`, leaving the thread’s fault-frame state poisoned for later calls. **Fix:** use an RAII `HookBodyScope` around the callable.

16. **`src/harness/engine_k1.cpp:328, 335, 345, 352, 359, 402-404, 1060-1070, 1137-1144` — major.** Numerous 32-bit base-plus-offset/index expressions wrap before `read_*()` probes. A stale or corrupt engine pointer can therefore probe and read an unrelated low address instead of refusing. **Fix:** centralize checked address arithmetic and reject overflow before every pointer calculation.

17. **`src/harness/commands.cpp:397-405` — minor.** `fprintf`, `fwrite`, and `fclose` failures are ignored; a full disk or interrupted write still returns a successful screenshot reply. **Fix:** check each operation and return an error, removing partial output when appropriate.

18. **`src/harness/channel.cpp:91-103, 113-123` — minor.** `WSAStartup()` is not paired with `WSACleanup()` on socket/bind/listen failure. Repeated failed starts leak Winsock reference counts. **Fix:** call `WSACleanup()` on every post-startup failure path.

All three severity categories have findings.

**Correctly implemented invariants checked:** loopback-only binding; `winsock2.h` before `windows.h`; listener thread does not parse JSON or touch engine/Lua; poison gating is independent of `live()`; request batches leave the queue before guards; replies are queued after guards; thread-local drain reentrancy protection; client-generation filtering; bounded line framing and parser depth; fixed-capacity ring slot wrap-around; adapter calls use unarmed `HookBodyScope`; raw field reads generally probe spans before copying.



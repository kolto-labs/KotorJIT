# Browser/WASM fan-out plan (read-only planner, LOWER PRIORITY), 2026-09-27

Worktree read: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation` (HEAD `ca329e5`). WT below means that path. Nothing in the repo was edited. No game, Wine, Gamescope or FFmpeg was run.

Directive: "Browser/WASM remains lower priority, requires users' local installed assets, and shares the Lua/devtools command pipeline without publishing game assets."

## 0. Framing (read this first)

- `WT/docs/user-directive-audit.md:8` says the browser objective must "deliver playable games, not a console page". `WT/docs/devtools-design.md:145` says the same thing.
- So options A and B below do **not** advance the browser/WASM objective. They advance a different audit row, "Chrome DevTools and Lua console share pipelines" (`user-directive-audit.md:56`).
- After A lands, `WT/docs/capability-cells.md:130-131` (K1/K2 browser/WASM, C1..C8) stays `not attempted`. Only option C can move those cells.
- The recommended order below puts A first because it is small, reuses the shipped pipeline unchanged, and becomes the transport contract a future in-browser game will need. It is not browser-game progress, and reports must not describe it that way.

## 1. What exists (with referents)

| Fact | Referent |
|---|---|
| One native Console service: one evaluator, one engine-thread pump, session/request IDs, typed outcomes, output cursors, targeted cancel. "There is no second evaluator, browser transport, browser runtime." | `WT/docs/devtools-protocol.md:3`, `WT/src/devtools/console.hpp:84-110` |
| `kp.console.v1` wire adapter over the harness `devtools` command: ops `status/submit/outcome/output/complete/cancel`, decimal-string IDs, base64 byte objects, `StaleRuntime`/`StaleSession`. Reset is not a wire op. | `WT/docs/devtools-protocol.md:57-90`, `WT/src/harness/console_protocol.{hpp,cpp}` (293 lines) |
| Live use of `kp.console.v1` with physical F12 | Pioneer plan §1: "Console service + kp.console.v1 LIVE (K1 runs 20260927-003752, -014019)"; capability-cells E4/E6. Not re-run here. |
| Python client for the adapter already exists | `WT/scripts/harness/kpharness/console_protocol.py` (`ConsoleClient`, `decode_bytes`, `canonical_u64`), `WT/scripts/harness/kpharness/client.py` (`Channel`) |
| Proposed JS surface `await kotor.lua.evaluate("kp.obj.pc()")`, explicitly "proposed interface until its adapter is implemented" | `WT/docs/devtools-design.md:134` (not in the protocol doc) |
| Required cross-client acceptance: F12 assigns, browser reads and modifies, F12 observes, same session | `WT/docs/devtools-design.md:140` |
| Harness transport: loopback-only TCP, one client at a time, a second client gets `busy` and is closed | `WT/src/harness/channel.hpp:1-19`, `channel.cpp:97-101,380-392` |
| Harness is off unless `harness_port` (ini) or `KOTORPHASOR_HARNESS_PORT` (env) is set | `WT/src/runtime/runtime.cpp:145-152,807-810` |
| Harness is **unauthenticated**: "the harness runs unauthenticated Lua in the game's process" | `WT/src/harness/channel.hpp:16-17` |
| After a JSON parse failure the harness sends an error reply and **keeps the connection open**, so the next line still dispatches | `WT/src/harness/commands.cpp:1245-1268` (`execute_line`) |
| Console Lua state gets `luaL_openlibs`; no removal of `os`/`io` found by grep in `src/lua`, `src/devtools`, `src/runtime`, `src/api`. The docs say "This is not a sandbox" | `WT/src/devtools/console.cpp:382-385`, `WT/docs/devtools-console.md:17`. So a submit can reach host `os.execute`/`io.popen` (static reading; not exercised). |
| Console is LuaJIT | `WT/docs/devtools-console.md:17` (JIT traces, instruction hook) |
| Pioneer Stage 6: "devtools on kp.console.v1 unchanged; Console::reset releases session leases; overlay status strip", after Stage 1 | `/home/brunner56/kp-live-20260922/fanout-pioneer-devtools-plan.md` §3 |
| Pioneer Stage 0 fix (5): the owner holds the route lock for life, so route step/commit goes through the owner. Fix (6): move the engine lock from `/tmp` to a user-private state dir. | same file §3; `playback.py:282`, `playback.py:63` as cited there |
| Browser file-provider and publish rules: visible "Choose game folder", read lazily and locally, never upload, saves in separate local storage, explicit allowlist validated on the actual output package | `WT/docs/devtools-design.md:147-151` |
| Browser F12 stays Chrome DevTools; the embedded tools get a visible button | `WT/docs/devtools-design.md:151`, `user-directive-audit.md:9` |
| Ideation doc mentions browser/wasm | `grep -c -i -E "wasm|browser|webassembly" WT/docs/ideation/*.html` returned `0` |
| Research docs mention browser/wasm | only `WT/docs/research/object-blaster-feasibility.md:58`, which is unrelated (host-test fixtures) |
| "Corpus, CPU/backend and KotOR.js comparator research completed" | `user-directive-audit.md:55`, capability-cells N7. **Referenced, not located.** I searched `/home/brunner56/kp-live-20260922`, the project memory dir and the WT docs for `KotOR.js`/`wasm` in `.md`. Only the audit, the design doc and `package-readiness-audit.md:15` turned up. |
| `docs/wasm-browser.md` (phasing: asset-picker shell first) | Exists only in the **main** checkout, untracked (`git status` shows `??`). It is not in WT. It carries lower authority and conflicts with the audit, so this plan does not follow its phase-1 ordering. |
| Toolchain on this host | `node` v26.3.0 and `python3` present. No `emcc`. No JS package infrastructure in WT (no `package.json`). |

## 2. The three options

### A. Browser devtools client for a running native/Wine game over an authenticated loopback bridge

- **What it is.** A page served from loopback that calls `kp.console.v1` on the running game. There are no game assets in the browser at all. Chrome's own F12 console can call `kotor.lua.evaluate(...)`.
- **Pipeline.** One pipeline. The native Console stays the only evaluator, and the bridge forwards the existing wire ops untouched.
- **Feasibility.** High. It is mostly transport and security work, with no native change needed beyond hardening H0.
- **Legal/IP.** Nothing retail crosses the bridge except runtime values the user's own Lua returns.
- **Effort.** Small. One Python module, one static JS/HTML client, tests, plus one small native hardening fix (H0).
- **Directive fit.** It meets "shares the Lua/devtools pipeline". It does not meet "playable in browser" (§0).

### B. Browser-hosted Lua editor/sandbox with `kp.*` mocked (no game)

- **Drift is a fact here.** The game Console is LuaJIT (`devtools-console.md:17`), and the wire contract already has a LuaJIT-only type: `cdata` is listed as an Opaque Lua type (`devtools-protocol.md:37`), and that is FFI, which no browser Lua has. Any in-browser Lua is a different language version (Fengari ≈ Lua 5.3 and wasmoon ≈ Lua 5.4 are `unverified` here), with different integer semantics, `goto`/bit ops, `ffi`/`jit` absence, error text and traceback shape. A mocked `kp.*` would also report success where the live build refuses (for example K2 `kp.model.capabilities()` returns `unsupported`, capability-cells K3).
- **Conflicts.** A second evaluator contradicts `devtools-protocol.md:3` and `devtools-design.md:132` ("none creates a second gameplay Lua state").
- **Verdict.** Do not build a browser Lua VM. Keep B only as a **JS protocol fake** that replays recorded `kp.console.v1` request/response transcripts. It exists to test the JS client offline. It is a test fixture, not a product.

### C. Actually running K1/K2 in the browser from the user's local install

This is the only option that satisfies the browser objective. There are three sub-paths.

| Sub-path | What it means | Pipeline reuse | Feasibility / effort | Legal/IP |
|---|---|---|---|---|
| C1. Engine reimplementation in WASM/JS (KotOR.js-class) | New renderer, GFF/2DA/MDL/module loader, NWScript VM, combat and dialog | None. The `kp.*` sites are hooks into the retail binary, so a reimplementation needs a new `kp.*` backend. That is a second semantics source. | Very high effort (multi-year class). KotOR.js is the comparator and is not adopted (`devtools-design.md:145`). Its completeness is `unverified` here. | Clean if assets are read only from the user's folder. |
| C2. Emulate the user's own retail x86 PE plus a Wine-like layer and GL→WebGL in the browser, with `kphasor.dll` injected inside | The same retail game and the same DLL, running under an x86 emulator in WASM | **Literal single pipeline.** The same Console and the same `kp.console.v1` run inside the emulated process. The A client would attach through a MessagePort instead of TCP. | Performance for a 2003 fixed-function OpenGL 3D game under an in-browser x86 emulator plus Win32 layer is `unverified`. Exposing Wine's ws2_32 inside the emulator is `unverified`. Effort is high but mostly integration. It has the best reuse of the existing per-build profiles (`wasm-browser.md` non-negotiable 3, lower authority). | The executable and assets come only from the granted folder. The emulator image must be built from redistributable code only. No retail bytes may be precached or served. |
| C3. Static recompilation of the retail exe to WASM | Lift x86 → WASM | Partial | Extreme effort and fragile (self-modifying code, SteamStub, DRM `.text` decipher seen in E7). The output would be a derivative of the retail binary, so it could only be produced client-side and must never be published. | Highest IP risk. |

**Rules that hold for any C path:**
- Read access comes through File System Access `showDirectoryPicker({mode:"read"})` behind a visible **Choose game folder** button, which requires a secure context (`devtools-design.md:149`).
- No upload. No service-worker or CDN caching of retail bytes.
- Any OPFS or IndexedDB copy is local-only, labelled, and user-deletable.
- Saves and mod output go to separate local storage with explicit export.
- The publish step validates the actual output package against an allowlist. Ignore patterns alone are not enough (`devtools-design.md:147`).

**C gate.** Before any C commitment, run one time-boxed probe of cell **C1 boot/inject only**. For C2 the question is: can the user's own K1 GOG exe reach the main menu in a browser emulator, from a user-granted folder, at a measured frame rate, with `kphasor.dll` logging `hooks installed`? The probe records FPS with its source. If it fails, C2 is dropped and C1 (reimplementation) goes back to the user as a scope decision. Performance numbers do not exist today (`unverified`).

## 3. Recommended order

Criteria: what the user asked for, native lines touched (blast radius), and reversibility.

1. **H0: harness hardening (native, small, first).** It is a prerequisite of A. See §4.1.
2. **A1: authenticated loopback bridge, the JS `kotor.lua.evaluate` client, and a B-style transcript fake for tests.** Zero Console or adapter changes.
3. **A-live: cross-client proof** (`devtools-design.md:140`) on K1 GOG under the canonical lock. This is later work, owned by the live controller, not by this planner.
4. **C-gate probe:** one C1-cell probe of path C2, time-boxed. Its result decides whether C continues.
5. **B beyond the fake: never.** Revisit only if the user asks for offline authoring. Even then, the editor would be a text editor that submits to A, not a Lua VM.

All of this stays behind the foreground items: capture C7, native Windows, K2 and Mac (`capability-cells.md:184-194`).

## 4. Recommended first slice (A1, with H0)

### 4.1 H0: close the cross-protocol hole in the raw harness port

- **Why.** The harness is unauthenticated (`channel.hpp:16-17`). It answers parse errors and keeps the connection (`commands.cpp:1261-1264`). So an HTTP POST's header lines fail, but a body line `{"cmd":"devtools","protocol":"kp.console.v1","op":"submit",...}` still dispatches. With `os`/`io` present (`console.cpp:382`, static reading), that is host code execution.
- **What is unverified.** Whether a browser actually delivers such a request to a loopback port. Chrome Local Network Access / Private Network Access gating and the blocked-ports list apply. The harness port is only open when a developer sets it (`runtime.cpp:807`), not in the player package.
- **Why a plain "close on bad line" is not enough.** The listener splits every newline in one `recv` and enqueues them all (`channel.cpp` recv loop, ~`:425-450`). The drain takes a whole batch (`commands.cpp:1447`) and runs every request in it. It does **not** skip requests whose client generation is stale; only their replies are dropped later in `push_reply`. The only early exit is `g_poison` (`commands.cpp:1450-1462`). The main thread also cannot close sockets: per the `overflow_` comment in `channel.hpp`, only the listener closes. So an HTTP POST that arrives in one segment queues its header lines and its body line in one batch, and closing "after the first bad line" still runs the body line.
- **Fix, single mechanism (main-thread condemn plus listener close).**
  - (1) Add `std::atomic<std::uint64_t> condemned_gen_` to `Channel`, with `condemn(gen)` and `condemned()`. On the listener side, when the current client's generation equals `condemned_gen_`, it sends any queued error reply and closes the client, reusing the `overflow_` pattern.
  - (2) In the drain loop (`commands.cpp` ~`:1450`): before `execute_line`, skip any request whose `rq.client` is condemned **or** is not `ch->current_client()`. The second condition also fixes stale-generation execution.
  - (3) In `execute_line`, a line that is not a JSON object, or that begins with an HTTP method token (`GET `, `POST `, `PUT `, `HEAD `, `OPTIONS `, `DELETE `, `PATCH `, `CONNECT `, `TRACE `), gets one error reply and then `condemn(client)`. Every later request of that generation, in this batch and in later batches, is skipped.
  - This keeps the listener's "never parses a request" contract intact.
  - Existing Python clients never send a non-JSON line (confirm by rerunning `tools/kpharness_*_test.py`).
- **Later, separately reviewed.** An optional `harness_token` ini/env: the first line must be `{"cmd":"hello","token":...}`, compared in constant time.
- **Test.** New cases in `WT/tools/kp_harnesstest.cpp`. That file already drives a real in-process `Channel` over a POSIX socket (`kp_harnesstest.cpp:4,195-211,275-299`).
  - (a) Send `POST / HTTP/1.1\r\nHost: x\r\n\r\n{"cmd":"devtools","protocol":"kp.console.v1","op":"submit","code":"1"}\n` in **one** `send`. Assert one error reply, then the connection closes, and a fresh client's `status.submitted` is unchanged. Written red-first, this fails on today's code.
  - (b) Invalid JSON then valid JSON in one `send`: the valid line is not dispatched.
  - (c) A request queued by a client that disconnected before the drain is not executed.
  - (d) Valid JSON behaviour is unchanged.
- **Scheduling.** `commands.cpp` carries uncommitted K2 load-completion work (Pioneer plan §3 parallel rules), so H0 lands after that commit.

### 4.2 Channel ownership (blocking decision, needs the user or orchestrator)

- **The problem.** The Channel is exclusive. The Pioneer playback owner (`playback.py`, Stage 0 fix 5), the physical-console scenario driver and the bridge all want it.
- **The rule.** Per the user's rule, a `busy` refusal is a crash, not a join. Only one process owns the Channel, and every other client attaches to that owner.
- **Recommendation.** The **Pioneer playback owner** stays the single Channel owner once Stage 0 lands. The bridge attaches to it by forwarding `devtools` `kp.console.v1` ops only. It never opens its own Channel while an owner is running.
- **Interim, before Stage 0 lands.** The bridge may own the Channel directly only in a documented standalone mode. On `busy` it exits non-zero with the message and does not retry.
- **Consequence for the live proof.** The F12 outcome observer (physical-console driver) and the browser client must go through that same owner. Otherwise the proof cannot run.
- Mark the owner API that the bridge calls as a dependency on Pioneer Stage 0/6: `unverified` until that API exists.

### 4.3 Files (all new unless marked)

| File | Content |
|---|---|
| `WT/scripts/harness/kpharness/devtools_bridge.py` | Stdlib-only (`http.server`, `hmac`, `secrets`, `json`) loopback HTTP bridge. It holds an upstream connection (owner attach or standalone `Channel`), and has endpoints `POST /v1/console` (one wire op per request) and `GET /` (allowlisted static files). No WebSocket in slice 1; output is polled via the `output` op cursor. |
| `WT/scripts/harness/kpharness/cli.py` (modified, additive) | `kpharness devtools-bridge [--attach OWNER \| --standalone --port N] [--listen 127.0.0.1:0]` prints the bound URL **without** the token and the token-file path |
| `WT/web/devtools/index.html`, `WT/web/devtools/kotor-console.mjs` | Dependency-free ES module. `window.kotor.lua.evaluate(code)` does submit → poll `outcome` → return a JS object with `state`, typed `values` (strings decoded from base64 to `Uint8Array` plus a UTF-8 view), `error`, and `output` lines filtered by session/request. It also exposes `status()`, `cancel(request)` and `complete(prefix)`. It never monkey-patches `console` or replaces globals (`devtools-design.md:134`). It includes a minimal textarea plus output view, as a visible embedded-tools control, not bound to F12. |
| `WT/web/devtools/MANIFEST` | Exact allowlist of served and publishable files, used by the bridge and by the publish check |
| `WT/tools/kpharness_devtools_bridge_test.py` | See §4.6 |
| `WT/web/devtools/kotor-console.test.mjs` plus `WT/web/devtools/fixtures/*.jsonl` | B-style transcript fake. `node --test` with an injected `fetch`. Fixtures are synthetic or recorded **wire** transcripts with no retail strings. |
| `WT/docs/devtools-protocol.md` (modified) | New section "Browser bridge", stating that it is a transport over the same ops and adding no semantics |
| `WT/docs/devtools-console.md` (modified) | One paragraph on how to start the bridge and its limits |

### 4.4 Protocol reuse (single pipeline, no drift)

- **Forwarding.** The bridge forwards the request body's `op` plus op fields verbatim inside `{"cmd":"devtools","protocol":"kp.console.v1", ...}`. It **forces** `cmd` and `protocol`, and rejects any other `cmd` (`lua`, `load_save`, `quit`, `subscribe`, ...) before forwarding.
- **Allowlisted ops:** `status`, `submit`, `outcome`, `output`, `complete`, `cancel`. Nothing else is accepted.
- **No reinterpretation.** Responses pass through byte-identical, minus the harness `id` envelope. Decimal-string IDs (including values above 2^53), byte objects, `StaleRuntime`, `StaleSession` and `Requested` (not terminal) all reach the JS client as-is.
- **No retries.** The bridge never retries or replays. An upstream timeout or disconnect gives an explicit `upstream_lost` error, and the JS client surfaces it (`devtools-protocol.md:88`: "A timeout never authorizes automatic replay").
- **No new semantics.** No new Lua, Console or adapter semantics. `console_protocol.cpp` and `console.cpp` are unchanged in this slice.
- **Where values come from.** The JS client computes nothing about Lua values. It decodes the wire only.

### 4.5 Security

- **Bind.** Loopback only, with the same 127/8 rule as `channel.cpp:96-101`. Refuse otherwise, do not narrow. Default port is 0, and the bound port is printed.
- **Token.**
  - 256-bit from `secrets.token_bytes`, written 0600 to the user-private state dir (the same dir Pioneer fix 6 introduces; `$XDG_STATE_HOME/kotorphasor/devtools-bridge.token`).
  - Compared with `hmac.compare_digest`.
  - Sent as an `Authorization: Bearer` header. Never in the query string or the URL.
  - The bridge **never prints the token**. It prints only the URL `http://127.0.0.1:<port>/` and the token-file path. The user pastes the token into the page, which keeps it in `sessionStorage` only. No fragment URL is used, which avoids scrollback and log leakage.
- **Canonical host.** It is `127.0.0.1` only.
  - Origin: require `Origin` to equal exactly `http://127.0.0.1:<port>` on every POST. Answer CORS preflight only for that origin. Never send `Access-Control-Allow-Origin: *`.
  - Host: `Host` must equal exactly `127.0.0.1:<port>`. `localhost` is rejected with a message that names the canonical URL, so a page loaded through `localhost` cannot end up with a mismatched Origin. This blocks DNS rebinding.
- **Serving.** The page is served by the bridge itself (same origin).
- **Order of checks.** Host → Origin → token → body size → JSON → op allowlist, all **before** anything goes upstream.
- **Limits.**
  - Request body: 16 KiB for code, matching Console's `SourceLimit`, plus envelope margin; reject larger bodies.
  - Response size is bounded by Console caps.
  - One upstream in-flight request at a time; queue depth ≤ 16, matching the Console queue.
- **Static files.** Only files named in `web/devtools/MANIFEST`. Paths are normalized and `..` is rejected. The bridge never serves the game directory, saves or logs.
- **Honest warning.** The token grants the same power as the F12 console: arbitrary Lua with `os`/`io` in the game process (`devtools-console.md:17`). The docs must say so.

### 4.6 Tests (host-only; red first where a behaviour is new)

`WT/tools/kpharness_devtools_bridge_test.py` runs the bridge as a real subprocess against a **fake harness TCP server** that replays `kp.console.v1` responses and records every line it receives.

1. A missing or wrong token gets 401, and the fake upstream received **0** lines.
2. A wrong `Origin`, or a missing `Origin` on a POST, gets 403 with 0 upstream lines. Preflight from another origin gets no ACAO header.
3. A wrong `Host` (rebinding, or `localhost:<port>`) is rejected with 0 upstream lines.
4. A non-loopback `--listen 0.0.0.0` is refused at start with a non-zero exit.
5. `cmd:"lua"`, `load_save` or an unknown op is rejected. A body `protocol:"x"` is overwritten or refused, never forwarded as-is.
6. Pass-through fidelity: an ID `"18446744073709551615"`, a byte object with NUL/0xFF, and a `Requested` cancel all come back byte-identical.
7. Upstream drop mid-request gives an explicit error, and exactly one upstream line was sent (no replay).
8. The upstream answers `busy`: the bridge exits non-zero with that message (standalone mode).
9. An oversize body gets 413 with 0 upstream lines.
10. Static: a traversal path (`/../`, `%2e%2e`) gets 404. Only MANIFEST files are served.
11. The token file has mode 0600, and the token never appears in stdout, stderr, the bridge log or the served HTML.
12. Publish check: the set of files a packaging step would ship from `web/devtools` equals MANIFEST exactly. This is a negative test with a planted `*.bif`/`*.tga` in a temp copy, which must fail.

`node --test WT/web/devtools/kotor-console.test.mjs` (transcript fake):
- `evaluate("1+1")` → `Succeeded`, `Number` 2.
- A `Failed` `lua_runtime` error surfaces with its traceback bytes.
- `StaleSession` rejects the pending promise and does not resubmit.
- Output is filtered by session/request, and `dropped_through` is surfaced.
- A cancel that returns `Requested` stays non-terminal until the outcome arrives.

Also rerun the existing `tools/kpharness_physical_console_test.py`, `kp_consoleprotocoltest`, and (after H0) `kp_harnesstest`.

### 4.7 Minimal proof

- **Host (the slice's done condition).** All §4.6 tests pass, with test names and output recorded, plus the H0 `kp_harnesstest` cases. This is host evidence only.
- **Live (later, under the canonical lock, by the live controller, not this planner).**
  - Setup: K1 GOG, owned display, and the bridge attached to the single Channel owner.
  - Steps:
    1. **Physically type** `kp_x = 41` in F12.
    2. The browser runs `await kotor.lua.evaluate("kp_x = kp_x + 1; return kp_x")` → `Number` 42, same `runtime`/`session`.
    3. **Physically type** `kp_x` in F12. The overlay shows 42, and that request's outcome is `Succeeded` with value 42.
  - Both F12 legs must be keyboard input, because a direct submit does not substitute (`devtools-protocol.md:88`).
  - The receipt records the DLL hash, runtime/session/request IDs for all three, and the source/save-unchanged check.
- **After a live pass.** It advances only the "shares pipelines" audit row. Browser/WASM cells stay `not attempted`.

## 5. Open items and unverified claims

- `unverified`: that a browser page can deliver the H0 cross-protocol POST to the harness port (Chrome LNA/PNA and port blocking not tested here). The fix is justified by the code path alone.
- `unverified`: that `os`/`io` are reachable from a Console submit at runtime. This is static reading only (`console.cpp:382` plus no removal found by grep).
- `unverified`: the performance and feasibility of C2 (in-browser x86 emulation of K1 plus DLL injection). There is no measurement.
- `unverified`: KotOR.js completeness. It is a comparator only.
- Referenced, not located: the "Corpus, CPU/backend and KotOR.js comparator research" (`user-directive-audit.md:55`).
- Blocking decision for the orchestrator or user: Channel owner (§4.2). The recommendation is the Pioneer playback owner, with a standalone bridge mode only as the interim.
- Dependency: H0 touches `commands.cpp`/`channel.cpp`, which must wait for the K2 load-completion commit (Pioneer §3 parallel rules).

## 6. Claim blocks (agent-to-agent report shape)

```
claim: A does not advance browser/WASM cells; only C can.
referent: user-directive-audit.md:8; devtools-design.md:145; capability-cells.md:130-131
checked: file reads
verdict: holds
confidence: high; changes only if the user redefines the browser objective

claim: The raw harness port dispatches a JSON line that follows non-JSON lines on the same connection.
referent: commands.cpp:1245-1268 (parse failure -> err_reply, no close); channel.cpp line splitter
checked: source read; not executed
verdict: holds (static)
confidence: medium-high; a kp_harnesstest case (H0 test a, pre-fix) would make it high

claim: A browser Lua VM would drift from game semantics.
referent: devtools-console.md:17 (LuaJIT); devtools-protocol.md:37 (`cdata` Opaque type = LuaJIT FFI)
checked: repo doc read; browser-Lua versions (Fengari 5.3, wasmoon 5.4) unverified here
verdict: holds
confidence: high for "not LuaJIT"; exact browser-Lua versions unverified

claim: The harness drain executes requests from a stale client generation, and a batch cannot be cut short except by poison.
referent: commands.cpp:1447-1462 (loop calls execute_line for every batch entry; only g_poison breaks); stale replies dropped in push_reply (channel.hpp push_reply comment)
checked: source read; not executed
verdict: holds (static)
confidence: medium-high; H0 test (c) makes it high

claim: Only C2 keeps the literal single pipeline in-browser.
referent: kp.* is implemented as hooks into the retail binary (devtools-design.md:51 build adapters; capability-cells E7 "19 hooks installed")
checked: doc read
verdict: holds
confidence: medium; C2 feasibility itself is unverified

claim: KotOR.js/CPU-backend research exists.
referent: user-directive-audit.md:55 only
checked: grep of kp-live-20260922, project memory and WT docs
verdict: unresolved (referenced, not located)
confidence: low
```

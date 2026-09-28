# Browser first implementation slice: local installation and Console adapters

Priority: low, independent of native input/Lua/example completion. User's eventual objective remains playable whole K1/K2 in a browser from an explicitly selected local installation. This first slice establishes reusable file access, a shared Console transport contract, and a no-retail publication boundary. It is not game execution, a WASM port, or a playable browser game.

Prepared read-only from existing reports and current `docs/devtools-protocol.md` / `src/devtools/console.hpp` in `.worktrees/lua-boundary-validation`. No repository changes, downloads, builds, or games. Proposed paths below do not exist yet. No dependency or CPU backend is adopted by this brief.

## Deliverable and ownership

Use a small isolated `browser/` tree with no frontend framework requirement. Keep the three responsibilities separable:

| Owner/responsibility | Proposed files | Boundary |
|---|---|---|
| Local installation provider | `browser/src/install/provider.ts`, `directory-provider.ts`, `synthetic-provider.ts`; `browser/test/install.test.ts` | Files/metadata only; no game API, Lua, renderer or network code. |
| Console protocol/client | `browser/src/console/protocol.ts`, `client.ts`, `message-port.ts`, `endpoint.ts`; `browser/test/console.test.ts` | Mirrors current service through a port; no evaluator, second VM, pointer handles or game aliases. |
| Package and integration | `browser/package.json`, pinned lockfile if dependencies required, `browser/publish-manifest.json`, `browser/tools/check-package.mjs`, `browser/test/package.test.ts`, `browser/README.md` | Synthetic fixtures and explicit input/output allowlist. No deployment step in this slice. |

A tiny local diagnostic page may expose choose-folder, selected-provider status and Console connection status. Its game status must say runtime unavailable; no simulated gameplay/canvas or fake boot progress. Keep source modules independently reusable by a later runtime worker and other corpus variants. Native service remains owned by `src/devtools/console.hpp/.cpp`; this slice must not duplicate or replace its execution logic. Existing report recommendations for new typed native results are superseded by the current implemented protocol document.

## Provider contract

Proposed dependency-free TypeScript interface:

```ts
interface InstallProvider {
  readonly selectionEpoch: string;
  list(path: string, cursor?: string): Promise<DirectoryPage>;
  stat(path: string): Promise<FileInfo>;
  readRange(path: string, offset: bigint, length: number,
            signal?: AbortSignal): Promise<Uint8Array>;
  close(): void;
}
```

`DirectoryPage` is bounded and paginated; `FileInfo` reports original case-preserved relative path, file/directory kind, byte size as bigint, and last-modified metadata where available. Those metadata are not content identity. Explicit optional hashing of a requested file may later produce algorithm/digest/selectionEpoch; do not hash an entire install at selection or infer supported variant from filename. CPU/OS/format/game profiles are separate from this provider.

The UI calls the browser directory picker only after an explicit user gesture, requesting read access. Feature-detect the capability; when unavailable, show unsupported picker with a precise reason. A fallback FileList provider can be a later implementation of the same interface. Do not silently scan machine paths, persist permission requests, select a game directory for the user, or fetch missing retail files. No handle persistence is required initially; reselection makes the first lifecycle simpler.

Resolve resource paths component by component within the selected root, preserving case but supporting the case-insensitive lookup needed by these resources. Reject NUL, absolute paths, drive/UNC forms, traversal, and ambiguous case-fold collisions rather than picking a random file. Do not collapse distinct Unicode names into a silently colliding key. Implement lazy directory indexes with bounded entries/cache and explicit oversized-directory errors, not a whole-install recursive walk. Document fold policy and unsupported ambiguity.

For exact reads validate nonnegative offset and a bounded length (proposed1MiB per call), detect integer precision/range limits before converting bigint to File.slice's number inputs, and reject a request beyond EOF rather than returning an unexplained short read. Read from a retained File snapshot per operation. If later reads detect size/mtime change, invalidate dependent metadata and require a fresh snapshot; this metadata check is not a cryptographic TOCTOU guarantee. Future loaders hash authoritative bytes and bind to content identity.

Selection/permission errors are typed: Closed, StaleSelection, PermissionDenied, NotFound, NotFile, InvalidPath, AmbiguousPath, RangeError, Changed, Unsupported and ResourceLimit. Closing/reselection invalidates pending operations; discard their late results by selectionEpoch. Abort does not imply an underlying browser read was physically preempted. No write API belongs on InstallProvider. Save/config persistence is a separate future user-controlled local store with explicit export; never write into the selected install by default.

Keep all selected bytes inside the browser process/worker/local storage boundary. There is no upload/telemetry payload containing handles, paths, hashes, content, or saves. Passing selected bytes to a local MessagePort is distinct from network transmission; use transfer/copy ownership deliberately, never detach a shared cache buffer accidentally. No retail content becomes a browser build input.

## Console adapter: match the actual current schema

Use version1 envelopes with adapter-owned correlation and runtime identity:

```ts
// IDs/counters are decimal strings on the transport.
{ version: 1, runtimeInstance: string, callId: string,
  op: "status" | "submit" | "outcome" | "snapshot" | "cancel" | "complete",
  args: { /* operation-specific fields */ } }
```

A startup handshake advertises supported operations and `runtimeAvailable`; it is an adapter envelope, not a new native Console capability method. Production endpoint takes a `ConsoleServicePort` dependency exposing exactly the actual service operations. An absent runtime returns RuntimeUnavailable. Test endpoints use an explicitly named synthetic implementation. No default fake evaluator or Lua emulation is allowed.

Preserve these exact native distinctions from `docs/devtools-protocol.md`:

- submit(session,source) returns session/request or StaleSession, QueueFull, SourceLimit; rejection is not an accepted request.
- outcome(session,request): Found with Pending/Running/Succeeded/Failed/Cancelled, or StaleSession/Expired/Unavailable. Never derive success from completed watermark or text.
- snapshot(session,after_sequence): session, last_sequence, dropped_lines, dropped_through and individual lines with kind/text/request/session/sequence. Request0 is unattributed. A request's first_line/last_line span may contain another source's rows; filter by both IDs. Output loss is explicit even when the outcome survives.
- cancel: Cancelled, Requested, AlreadyTerminal, StaleSession, Expired or Unavailable. Requested does not establish stopped execution.
- complete(prefix) returns only the existing cached bounded raw-table names. Native complete has no session argument: adapter associates the response with its current session and checks session before/after access to reject reset races. Never evaluate prefix text or invoke getters.
- reset remains owner-thread lifecycle, not a public freely dispatched message. New sessions invalidate outstanding observations without replaying commands.

Sessions, request IDs, output counters and original byte lengths serialize as decimal strings. Structured values preserve Nil tuple slots; Boolean false; Number Finite/NaN/PositiveInfinity/NegativeInfinity, with explicit negative-zero tag when encoding as JSON; String exact bytes in base64 plus original byte length/truncation; Opaque Lua type name with inspection_available=false. No inspect(ref), registry object handle, table traversal, fake64-bit Lua integer precision, or raw pointer previews are part of this slice. Preserve return_count, returns_truncated, bounded Error code/text/truncated, and first_line/last_line. Existing errors include lua_syntax, lua_runtime, instruction_budget, cancelled and allocation.

Retain current service limits:16 queued/one active, source16384 bytes, at most64 returned values,8192 bytes per string and32768 total string bytes per outcome,8192 error text,128 terminal results/256KiB accounted retention,512 output rows/256KiB. Browser client also bounds pending calls/subscriptions and rejects oversized envelopes before allocation. UTF-8 source byte count, not JS character count, determines source limit. Validate decimals and uint64 range before native conversion; reject malformed/base64-size-inconsistent payloads.

Page facade: `await kotor.lua.evaluate(source)`, `status()`, `complete(prefix)`, `subscribe(fn)`. Evaluate submits then reconciles the exact accepted outcome until terminal or explicit loss, returning a plain typed result suitable for Chrome inspection. Repeated identical output strings remain distinct by sequence. Use one shared bounded polling scheduler initially, not one hot timer per request. Abort/timeout requests exact cancellation but returns an explicit observation-timeout/unknown state unless a terminal confirms cancellation. Disconnect rejects pending observations and never automatically resubmits accepted mutations. Reconnect to the same runtime/session may query the known ID; restart requires a new runtimeInstance.

Transport uses a private transferred MessagePort, version handshake, `port.start()` for listener-based endpoints, bounded message sizes, unsubscribe and close cleanup. A worker runs the same actual engine/Console only when that build exists. Ordinary worker messaging cannot interrupt blocked synchronous WASM; do not advertise that it solves native-call cancellation. CDP Runtime.evaluate can await this JavaScript facade; it does not become a Lua evaluator, and Chrome JS property completion is not Lua-language completion inside strings.

## Tests and acceptance for this slice

Use authored synthetic byte arrays/files and real MessageChannel where available. No proprietary executables, resources, instruction snippets, recovered game source or saves in fixtures.

Provider tests: sliced reads at boundaries and EOF; wrong case lookup; ambiguous names; nested safe path versus traversal/absolute/NUL; missing/revoked permission; oversized directory/read; changed file; selection close/race; buffer transfer ownership. A network spy/interceptor must observe zero requests containing selected content/paths/hashes. Clearly distinguish synthetic handle tests from a real picker/manual browser smoke.

Protocol tests: nil versus zero returns, false, negative zero, nonfinite number, embedded NUL/invalidUTF8 raw strings, opaque inspection unavailable; IDs beyond2^53; unknown versus expired versus stale; queue rejection while another request is active; late old-epoch messages; duplicate responses; output gaps/repeated lines; queued cancellation versus running Requested; timeout followed by eventual success; worker disconnect with no mutation replay; completion response crossing reset. Test endpoint emits actual protocol shapes, but these tests do not prove Lua execution.

Package tests: positive minimal authored package and negative unlisted file, traversal, symlink, case/Unicode collision, synthetic renamed PE/resource/archive/save markers, unexpected JSON byte blob, source map with synthetic forbidden-content marker, compressed/nested archive and extra hidden file. A failed gate must prevent creation/selection of a publishable stage; warnings do not pass.

Done means source/test artifacts, precise API README, passing isolated provider/protocol/package tests, and a receipt listing executed checks and remaining unsupported runtime integration. Do not require a new Emscripten SDK or CPU build merely to complete this adapter slice. An explicit unavailable runtime is correct. A test mock must never be presented as a working shared browser Lua runtime.

## No-retail publication gate

Build into a new dedicated clean output root using a versioned exact manifest of authored inputs and approved pinned dependency versions/licenses. Validate dependency closure and final file membership/hashes/byte counts. No broad repository copy, ignored-file assumption, preloaded assets, native generated address tables, corpus output, recovery data, harness stages, checkpoints, captures or source maps with unreviewed sourcesContent. The prior audit specifically found retail instruction patterns in native text metadata, so extension allowlists alone cannot certify zero-retail content. Keep native data/ and profiles outside the browser dependency closure.

First public pipeline, when separately authorized, must run with synthetic fixtures and no private install/corpus access. Reject unknown output and nested archives/maps initially; deny retail signatures as supplemental tripwires, not as provenance proof. Produce a sanitized manifest and permit a future deploy job to consume only that exact validated stage. This brief performs or authorizes no publication and makes no legal finding about historical source.

## Truthful route to playable K1/K2

1. Complete this provider/protocol/package slice. Evidence: isolated interfaces and synthetic tests only.
2. Compile the actual shared Console/runtime to a worker using a supported pinned Lua/WASM toolchain. Prove one real persistent state and the same session/outcomes through both embedded console and browser facade. No substitute JS Lua VM or separate state. Keep kp facilities and explicit nwscript.call split.
3. Choose and reproduce an actual execution architecture. Existing corpus audit has partial recovered functions and original images, not a complete publishable source engine. Direct recompilation is not currently established. The previous CPU research identifies v86 as permissive but needing exact-budget/register adapter work, Unicorn.js as a convenient GPL TCI API, and Boxedwine as a heavier GPL Windows stack. These are candidates, not adopted dependencies or proven KOTOR engines. A source-engine alternative needs complete semantic implementation and publishable dependency closure; it cannot embed original byte fallbacks into public WASM.
4. With user-selected local executable/assets, prove hash-bound K1 and independent K2 actual instruction/ABI slices and entry startup with explicit unsupported-import/fault results. CPU execution alone is not game boot. Corpus ISA/format/OS profiles stay distinct; unsupported variants reject explicitly. Guest addresses never become host function pointers.
5. Supply real loader/OS services, rendering, audio/video, input, thread/TLS/exception behavior and save storage. Demonstrate menu, character creation/load, first module, movement/combat/dialogue/module transition, save/reload, then measured extended K1 and K2 coverage. Keep native-versus-browser independent oracles and a limitations ledger. Full-game completeness remains open until those outcomes are established.

Local install bytes, including a user-selected executable if the architecture needs it, can be runtime guest inputs without being shipped by the site. Native screenshots, a resource viewer, Console adapter tests, emulator compilation, a single function, or a menu are all narrower milestones. None completes the user's entire-game browser objective.

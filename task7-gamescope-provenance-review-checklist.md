# Task 7 Gamescope provenance review checklist

Date: 2026-09-27  
Checkout reviewed: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`  
Scope: read-only review of the failed Gamescope attempt, the current Gamescope/Xwayland adapter, and the early boot/cleanup evidence contract.

## Evidence boundary

The requested source report, `/home/brunner56/kp-live-20260922/task7-gamescope-live-attempt-report.md`, was not present at audit time. The available evidence was `task7-gamescope-live-preflight-review.md`, `task7-package-proof-audit.md`, the Gamescope code rereviews and checklist, `scripts/harness/kpharness/gamescope_xwayland.py`, `display_backends.py`, `creative.py`, `creative_wine.py`, `recording.py`, `session.py`, and the host-only Gamescope tests. This checklist therefore records a required receipt contract; it does not promote an absent or historical run into live proof.

Current conclusion: **the implementation has promising ownership checks, but no run is provenance-complete until a fresh snapshot manifest and an independently durable early boot/cleanup receipt satisfy every Critical condition below.** Host-only tests and a final `creative-run.json` are insufficient by themselves.

## Verdict rules

* **Critical** means the evidence could bind the run to foreign, changed, or unauthenticated source/process state, could kill or capture something it does not own, could disclose a secret, or could report success after a missing or ambiguous boot/cleanup fact. Any Critical failure is a refusal.
* **Important** means the evidence is incomplete, non-atomic, weakly correlated, or difficult to audit, while the direct ownership boundary remains intact. Important failures block acceptance until corrected; they do not become harmless because the game or route later passes.
* A receipt may say `refused`, `failed`, or `incomplete`; it must never infer `passed` from a missing field, a process name, a valid MP4, or a route result.

## A. Snapshot source manifest

### Critical conditions

- [ ] **Manifest is a closed allowlist.** It names the exact Task 7 source files, runner import closure, selected route TOML, every Lua input, exact K1 source, address profile, build inputs, generated runtime/proxy artifacts, and tool/interpreter identities. No whole dirty checkout, broad directory hash, private prototype, copied game asset, or unlisted dependency is accepted.
- [ ] **Hunk-only files are materialized.** For files such as `CMakeLists.txt`, `scenario.py`, `session.py`, `commands.cpp`, and `harness.cmake`, the manifest records the declared base revision and the resulting full materialized file hash. A patch or line-range description alone is not a source identity.
- [ ] **Every entry has canonical path, role, byte length, SHA-256, and resolved path.** Relative paths are normalized, reject `..`, and resolve inside the declared snapshot root. Symlinks are either prohibited or recorded and resolved without escaping the snapshot.
- [ ] **Manifest itself is immutable and atomically published.** Write to a same-filesystem temporary file, flush and fsync it, then rename it into place; retain the manifest digest. A reader must never see a partially written manifest, and a changed manifest invalidates the run.
- [ ] **Source equality is checked twice.** Before staging/boot, recompute every listed source and input digest. After teardown, recompute the same set and require exact path, size, and SHA-256 equality. Missing, replaced, newly added, or changed files fail closed.
- [ ] **Built and deployed bytes are bound.** The produced DLL/proxy/runtime and the exact deployed copies have separate hashes. The deployed hashes must equal the selected build hashes and be recorded before boot; a runtime marker or filename is not sufficient.
- [ ] **Interpreter and module resolution are explicit.** Record the absolute Python executable, Python version, `PYTHONPATH`, package root, imported module file paths, and hashes of the imported modules. Record absolute `ffmpeg`, `ffprobe`, `gamescope`, `xdotool`, `glxinfo`, Wine, and wineserver paths plus version/identity output. Refuse ambient `PATH` or an import shadowed by an unlisted directory.
- [ ] **Source and runtime contain no secrets.** Scan manifest paths, command arguments, environment values selected for evidence, logs, and receipts for Xauthority cookies, tokens, passwords, private keys, Steam credentials, or unrestricted environment dumps. Record only that authority exists and its sanitized path/identity, never its contents.
- [ ] **Run paths are owned and disjoint.** Source snapshot, build, stage, Wine prefix, checkpoints, output, and readiness/receipt directories are canonical, pairwise disjoint, newly owned, and free of escaping symlinks. A pre-existing directory is accepted only with a matching ownership sidecar and empty/known contents.
- [ ] **Refusal precedes mutation.** Missing manifest entry, digest mismatch, unresolved interpreter/module, secret finding, path overlap, stale readiness file, or unavailable tool refuses before claiming stage/prefix/output, changing saves, launching Gamescope/Wine, or overwriting a receipt.
- [ ] **No unsupported source substitution.** The manifest distinguishes the selected installed K1 executable from historical candidates and does not relabel an old frozen DLL, MP4, or receipt as evidence for current bytes.

### Important conditions

- [ ] Manifest records repository/worktree revision, dirty-state rationale, snapshot creation time, creator, schema version, and a deterministic sorted entry order.
- [ ] The manifest includes the exact route and Lua bytes copied into the run directory, then verifies their copied hashes before any boot. Deployed Lua basenames remain unique and the route target/settings are recorded.
- [ ] The manifest records compiler/linker/toolchain identity and build command without credentials or unrelated dirty files.
- [ ] Before/after source checks have their own timestamps, status, and error fields rather than being folded into a single final boolean.
- [ ] A stable refusal reason identifies the first failed condition and includes the relevant manifest entry or path without leaking sensitive bytes.
- [ ] The manifest records filesystem/device identity where useful, so a path replacement or cross-device rename cannot silently change the source authority.

## B. Early boot forensic receipt

The early receipt must be created before the first mutable launch step and updated through a monotonic, append-only event sequence. It must be durable even when boot crashes, the parent receives SIGTERM, readiness times out, or the final creative receipt cannot be written.

### Critical conditions

- [ ] **Atomic creation before launch.** Create an exclusive run receipt in the owned run directory before Gamescope, readiness child, Wine, or recorder launch. Publish each complete event through temp-file-plus-rename or an append-only record with flush/fsync. A missing receipt after a failed launch is a failed run, not “no result.”
- [ ] **Ownership is recorded before readiness.** Record lease ID, run ID, owner PID, owner start identity, PGID, session ID, parent PID/start identity, command argv, sanitized environment identity, run directory, and lock identity immediately after each spawn. PID alone is never accepted.
- [ ] **Ancestry is proven from both directions.** For Gamescope and readiness child, retain PID/start, PPID/start, PGID, SID, `/proc` executable identity, and the ancestry walk proving the child descends from the recorded Gamescope owner and remains in the recorded group/session. A process name, matching display number, or unchanged PID is insufficient.
- [ ] **Start identity is revalidated at every destructive action.** Before SIGTERM, SIGKILL, wait, input, capture, and final cleanup, verify PID plus start identity and expected PGID/SID. If identity changes or `/proc` disappears ambiguously, refuse escalation and mark cleanup unresolved rather than killing by recycled PID.
- [ ] **Private authority is bound to the lease.** Record sanitized `DISPLAY`, Xauthority path/presence, optional Wayland endpoint, and child environment authority. Prove it differs from caller authority and is the same authority used by xdotool, glxinfo, Wine, window discovery, and FFmpeg. Never record cookies or unrestricted environment content.
- [ ] **Readiness publication is atomic and schema-closed.** The helper readiness file is created only after valid PID/start/environment data are collected, atomically renamed, and rejected for stale files, malformed JSON, unexpected keys, missing authority, dead owner/child, or timeout. The parent must record the refusal and cleanup attempt.
- [ ] **Readiness precedes game launch and capture.** Retain ordered timestamps/events proving Gamescope/Xwayland authority, display probe, direct accelerated non-software renderer probe, exact game/Wine launch, mapped PID-owned window discovery, and recorder start. A valid MP4 or route pass cannot backfill skipped ordering.
- [ ] **Source/interpreter identity is repeated in the receipt.** The boot receipt binds the manifest digest, module/import closure, executable paths, runtime/proxy hashes, route/Lua hashes, and selected K1 source hash before launch. It records any mismatch as refusal.
- [ ] **Cleanup is ownership-scoped and ordered.** Record and enforce recorder → game/Wine → display teardown. Each component has PID/start/PGID/SID identity, signal/wait/escalation timestamps, exit status, and post-cleanup absence proof. Foreign processes are never swept by name, display, prefix, or global Wine shutdown.
- [ ] **Failure paths are receipts too.** Boot failure, renderer refusal, readiness timeout, dead child, missing window, recorder exit, route exception, SIGTERM, and double teardown each leave a terminal forensic event and a cleanup result. `finally` execution alone is not evidence that cleanup completed.
- [ ] **No false success.** `passed`/`ok=true` requires an atomic early receipt with complete ownership and ancestry, source/input equality, ordered readiness, route/capture predicates, and all cleanup components passed. Missing or unreadable receipt fields force `failed` or `refused`.

### Important conditions

- [ ] Receipt events use monotonic sequence numbers and UTC wall-clock timestamps, with the clock source and schema recorded. Sequence gaps, duplicate terminal events, or non-monotonic event order fail audit.
- [ ] Record `/proc` start/relationship snapshots at launch, readiness, game boot, window discovery, recorder start, teardown begin, and teardown end. Preserve command argv in a secret-scrubbed form and retain stderr/stdout paths and hashes.
- [ ] Record exact Gamescope geometry, requested/actual display geometry, renderer text hash, Xauthority presence, readiness elapsed time, and capability admission/refusal separately.
- [ ] Record game/Wine launcher PID and start identity plus all owned descendants used for teardown; include the reason if Wine server cleanup is intentionally skipped or refused.
- [ ] Record stale artifact checks for readiness files, lock files, stage/prefix/output sidecars, and prior receipts before launch; preserve the refusal if any stale artifact is found.
- [ ] Record window ID, owner PID/start, lease ID, geometry, title, and exact FFmpeg `-window_id` command correlation. Window replacement, resize, lease loss, or identity-query failure must become capture failure and trigger the same cleanup receipt.
- [ ] Record recorder process identity, start/exit status, continuous media path/hash, and FFprobe metadata independently of route status. Encoded FPS is not proof of distinct game-frame cadence.
- [ ] Record source-before and source-after snapshots as separate immutable artifacts, each bound to the manifest digest; an equality boolean without the snapshots is weak evidence.
- [ ] Cleanup receipt is written before deleting readiness/lock sidecars, then a final fsync/rename publishes the terminal result. Repeated close is idempotent and records that no second destructive action occurred.
- [ ] Logs and receipts are readable without privileged access where possible, but their permissions prevent unrelated writers from altering evidence. Any permission failure is explicit and fail closed.

## C. Refusal matrix

| Condition | Required result | Evidence required |
|---|---|---|
| Requested live-attempt report absent | `refused` for historical promotion | Missing-path observation in review; no inferred run result |
| Dirty source not materialized into allowlisted snapshot | `refused` before launch | Manifest refusal naming base/hunk ambiguity |
| Any source, runtime, route, Lua, or deployed byte mismatch | `refused`/`failed` | Expected and observed digest, no secret bytes |
| Python/module/tool resolves outside manifest | `refused` | Absolute path and sanitized version identity |
| Caller display/authority reused or private authority absent | `refused` | Admission and lease refusal event |
| Gamescope/child PID start or PGID/SID ancestry mismatch | `refused`; no cleanup escalation by name | Identity snapshots and refusal reason |
| Renderer not direct, accelerated, and non-software | `refused` before Wine/game | Renderer probe artifact/hash |
| Window absent, foreign, replaced, resized, or identity query fails | `failed` capture; cleanup continues | Window/lease identity events |
| Receipt write, fsync, rename, or cleanup verification fails | `failed` with unresolved status | Filesystem error and last durable event |
| Secret detected in command/env/log/receipt | `refused`; do not publish the secret | Redacted finding and scrub status |
| Any cleanup identity changes or foreign process appears in target set | `failed` and stop escalation | Before/after identities and exact ownership set |

## Acceptance decision

Do not accept a Gamescope live result until a reviewer can start with the manifest digest, follow the durable early receipt through ownership and readiness, correlate the exact source/runtime/interpreter bytes to the boot, and end at recorder → game/Wine → display cleanup with identity-safe absence proof. The current host-only `24/24` Gamescope backend test result is useful lifecycle coverage, but it does not satisfy the live evidence contract. The absent requested live-attempt report and the previously recorded package-readiness failure remain blockers for any claim of a completed live Gamescope run.


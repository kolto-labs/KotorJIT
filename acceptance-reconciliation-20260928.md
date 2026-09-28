# Acceptance reconciliation — 2026-09-28 (READ-ONLY)

Worktree: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`
(branch `codex/lua-boundary-validation`, HEAD `ca329e5`, ~177 uncommitted files — implementation lives in the
working tree, not HEAD). Evidence root E = `/home/brunner56/kp-live-20260922/`.
Ledger: `<worktree>/.superpowers/sdd/lua-boundary-validation-plan/progress.md` (386 lines, read in full,
end-to-end, 2026-09-22 → 2026-09-28). Handoffs read: `client-server-audit-host-integration.md`,
`task7-sonnet-fanout-pause.md`. No file was launched, built, staged, committed, or deleted while producing
this report; every finding below is read-only (`ls`/`stat`/`sha256sum`/`pgrep`/`grep`).

## 1. Remaining acceptance obligations

### O1 — Live display/capture diagnostic (the single authorized attempt)
- **Obligation:** ledger line 367: *"Prepared, unexecuted one-attempt invocation:
  `.../resume-diagnostic-prepared-invocation.md`; foreign Wine and explicit launch authorization remain
  gates."* Round-12 correctness+adversarial both PASS (ledger:271) formally "met the diagnostic gate," but
  a narrow round 13 (barcode-index Critical, ledger:300) and round 14/15 policy work followed — round 15
  host reviews PASS (ledger:341), R15 PTS fix PASS (ledger:361), offline family gate accepted (ledger:363-365).
- **Evidence today:** offline/synthetic media only, under `E/r15-offline-media-review/` and
  `E/task7-capture-r15-*-review.md`. This is explicitly **not** live-display proof (ledger:365, :367).
- **Prepared diagnostic relation:** would **fully discharge** O1's live-display leg if it ran and passed —
  that is exactly what it is for. It does **not** discharge K1/K2 gameplay acceptance by itself (media-content
  gate only, no game).
- **Preconditions checked (read-only, this session):**
  | Precondition (from `resume-diagnostic-prepared-invocation.md`) | Status |
  |---|---|
  | `/usr/bin/python3.14 -S -B` | **UNMET / STALE** — host has only `/usr/bin/python3.12`; `/usr/bin/python3.14` does not exist (`ls`, `which` both fail). |
  | `/usr/bin/ffmpeg` | **UNMET / STALE** — path does not exist. A wrapper `/home/brunner56/.local/bin/ffmpeg` exists; the ledger explicitly distrusts `~/.local/bin` wrappers for capture (round-9/round-13 findings, ledger:187,197,209). |
  | `/home/linuxbrew/.linuxbrew/bin/ffprobe` | **UNMET / STALE** — path does not exist. Only `/home/brunner56/.local/bin/ffprobe` (wrapper) is present. The whole capture-cadence design (rounds 9-15) is keyed on distinguishing a real ffprobe ELF from a wrapper; the invocation's hard-coded "real" binary is currently the missing one. |
  | `kpharness.capture_diagnostic` module reachable via given `PYTHONPATH` | **MET** — `scripts/harness/kpharness/capture_diagnostic.py` exists in the worktree. |
  | No foreign Wine/capture process signaling required | Foreign processes present: wineserver pid `407438` (tied to the user's PotPlayer, `/home/brunner56/.local/share/wineprefixes/default-nvme/...PotPlayer...`) and an idle headless `mpv` (pid `1451616`, `--vo=null --ao=null --idle=yes --input-ipc-server=/tmp/mpvtest.sock`) — this matches the task's "known drift" exactly; neither was touched. |
  | New unused run/snapshot/commitment-log paths | Not pre-existing under E (checked: no `r15-authorized-diagnostic*` paths present) — **MET** as a precondition (nothing to collide with), but the invocation's binary paths make it non-runnable as written regardless. |
  | Canonical live-game lock (`tmp/harness-locks/live-game.lock`) | Present, 0 bytes, not visibly held (no `lsof` holder found, though the sandbox's overlay-fs warnings limit that check's confidence). |

  **Net: the prepared invocation as literally written cannot execute on this host today** — three of its
  four hard-coded binary paths (python3.14, /usr/bin/ffmpeg, linuxbrew ffprobe) are absent. This is new drift
  beyond what the task briefed (which only flagged `/tmp/lifecycle-cfg` ownership and the idle mpv). Whoever
  runs this must first re-resolve real (non-wrapper) ffmpeg/ffprobe binaries and a python3.14 (or update the
  invocation to the actual interpreter/tooling now on the host) — this is exactly the kind of silent
  path-drift the round-9/13 findings warned about, just at the shell level instead of inside the diagnostic.

### O2 — K1 acceptance (live gameplay route + framing)
- **Obligation:** ledger:279,291,299,312: K1 scale attempt-2 prep requires (a) `KP_MAX_BOOT_ATTEMPTS=1`,
  (b) a mechanical `postrun-gate.py --require-l1 <l1-run-dir>` binding L1 (camera diagnostic) before any V1
  (acceptance) run by hash, (c) a fresh `kp.camera` build/snapshot, (d) a user-authorized L1 launch. Ledger:312:
  *"K1 prep READY pending new kp.camera build + fresh snapshot + user-authorized L1 launch."*
- **Evidence today:** camera Stage 1 closed host-only (ledger:263); the runtime-integration work that wires
  camera/motion/vec/scripts into `runtime.cpp`/CMake landed later and is reported closed (handoff
  "Resumed actual runtime integration seam verified", ledger:369-373). `k1_gog_103.json` current sha256
  `5749fbf0…` matches the ledger's regenerated-table value (verified by `sha256sum` this session) — the
  address table is current, not drifted.
- **Gap:** no deployed/current Windows DLL was found anywhere under E reflecting the post-integration source.
  The most recent live Wine K1 run (`private-gpu-runs/20260927-003752`) predates the same day's runtime
  integration, GOG regen, and H0 work (which landed ~22:1x-22:2x). No fresh MinGW build or L1 camera-diagnostic
  run exists in E from after the integration closed. **This is an artifact-identity mismatch worth flagging
  explicitly**: any K1 acceptance attempt right now would either need a fresh DLL build first, or would be
  running acceptance against stale binaries while claiming current-source coverage.
- **Prepared diagnostic relation:** does not touch O2 directly (no game, no L1 camera route) — it only
  proves the capture pipeline. O2's L1 launch is a separate, still-unauthorized live attempt, sequenced
  *after* O1 by the diagnostic's own design intent (diagnostic proves capture works before spending a live
  attempt on it) but the ledger's L1-before-V1 gate is otherwise independent of O1.
- **Preconditions:** `postrun-gate.py`/`validate.py` referenced in the ledger for K1 prep were not found
  inside the worktree by filename search — they most likely live only under a private prep location not
  captured in this evidence root snapshot, or under a path this session didn't have search access to; this
  reconciliation could not verify their current content/hash.

### O3 — L1 (camera diagnostic) before V1 (acceptance) receipt gating
- **Obligation:** ledger:299: *"make it mechanical — `postrun-gate --require-l1 <l1-run-dir>` verifying a
  passing L1 result bound by hash"* — implemented per writer report and re-reviewed PASS (ledger:299,312).
- **Evidence:** host-only; `validate.py` rerun on a scratch copy reported rc=0 with 13 cases (ledger:299) —
  not independently re-verified this session (file not located).
- **Discharge by prepared diagnostic:** none — O3 is a receipt-gating mechanism for O2's live route, not
  related to the capture-cadence diagnostic.

### O4 — GOG/H0 host-integration closure (runtime integration, GOG table regen, H0 drain regression)
- **Obligation:** handoff "Resumed GOG and H0 host integration closed" (ledger:378-382): GOG-only
  regeneration 283/283 resolved, H0 durable regression test linked to real library, mutant fails at intended
  assertion only.
- **Evidence:** `E/resume-gog-regeneration.md`, `E/gog-regen-current-20260928/root-semantic-check.json`,
  `E/resume-h0-build-final.log`, `E/resume-h0-green.log`, `E/resume-h0-mutant/receipt.md`,
  `E/resume-h0-real-commands-report.md` — all present, all read this session. **This satisfies the host-only
  obligation as stated.** It is explicitly not live/gameplay proof and doesn't claim to be.
- **Prepared diagnostic relation:** not touched; O4 is closed independently of O1.

### O5 — External-client / browser acceptance (Browser A1 devtools bridge)
- **Obligation:** ledger's `fanout-browser-wasm-plan.md` order H0→A1→live cross-client proof→C2; H0 is
  closed (ledger:249,269+). Handoff: *"Browser A1 root fixes... no live/browser-game claim; playback attach
  remains explicitly unsupported."* (client-server-audit handoff, ledger:337).
- **Evidence:** `E/browser-a1-root-verification/`, `E/browser-a1-root-fixes-review.md`,
  `<worktree>/.superpowers/.../browser-a1-report.md` — Python/Node/physical-console host tests pass. No live
  cross-client run exists.
- **Offline evidence does NOT satisfy this live obligation.** Explicitly still open; not touched by O1.

### O6 — Release-builder patch (scanner/publication-boundary hardening)
- **Obligation:** ledger:244,286,309,318: proposed external `release-builder` patch to close the same
  publication-boundary scanner gaps fixed in-tree; repeatedly noted as **UNAPPLIED**.
- **Evidence:** `E/release-builder-proposed.patch` exists (confirmed present, 21478 bytes). Worktree-side
  scanner/packager fixes are done and reviewed PASS (ledger:318,324: "package74/export17"). The external
  patch itself remains a proposal only — this session did not apply, and was told not to touch, any file.
- **Not related to O1.**

### O7 — Pause R6 wiring into production
- **Obligation:** ledger:353: *"This confirms the private snippet contract; production pause wiring remains
  excluded from this integration."* Root authorized `motion_review` as sole shared-integration writer for
  scripts/vector/motion/engine-gate/CMake/namespace (ledger:355) — pause itself is not listed in that
  integration scope.
- **Evidence:** `E/pause-lease-r5-review.md`, `E/pause-lease-r6-review.md` — both are private-snippet-scope
  confirmations, not product wiring.
- **Gap:** production pause wiring (playback pause/rewind hooked into the real engine loop) has **no**
  integration writer assigned in the ledger's last integration-scope statement (ledger:355 lists scripts,
  vector, motion, engine-gate, CMake, namespace, address diagnostics — not pause). This looks like a
  **dropped obligation**, not a closed one: it was carried since Task 5/Pioneer work and the R6 confirmation
  language ("production pause wiring remains excluded") reads as still-open, but nothing in the ledger's
  tail assigns a next owner for it.
- **Not related to O1.**

### O8 — Side audit (client/server Lua surface inventory)
- **Obligation:** user-directed read-only audit of all public Lua surfaces/events/scripts/harness
  (ledger:384).
- **Evidence:** `E/side-audit/` — README.md, coverage-check.json, spec/quality reviews, all present and
  dated 2026-09-27 22:2x-22:49; ledger:386 records it complete with independent review PASS.
- **This obligation is closed** as stated (source-evidence inventory only; explicitly disclaims
  live/game/network acceptance, per its own README).

## 2. Artifact-identity check (explicit ask)

- `data/addresses/k1_gog_103.json` in the worktree: sha256 `5749fbf0b3f90b71296319fd5bebf94aca7f2bfd5f27d110934eaaa1089ecbf3` — **matches** the ledger's recorded regenerated-table hash (ledger:380). No drift here.
- `/tmp/lifecycle-cfg`: owned by `brunner56:ubuntu` (mode 755), **not root** as the handoff's "Workspace and
  fragile state" section claims (*"Current shared build is machine-local `/tmp/lifecycle-cfg` (root-owned...)"*).
  This is the exact drift the task briefed as already known — confirmed still true, unresolved. Build outputs
  inside it (libkphasor.so, kp_*test binaries) are all timestamped 21:53-22:22 on 2026-09-27, i.e. **after**
  the last tracked source edits checked (`CMakeLists.txt` 21:45, `engine_k1.cpp` 00:15 same day) — so this
  particular Linux host-test build is not stale relative to those files, but it is a Linux `.so`/CTest build,
  not the Windows DLL that any K1/K2 Wine acceptance run actually needs.
- No KotorPhasor-built Windows DLL was found anywhere under the evidence root newer than
  `private-gpu-runs/20260927-003752` (00:37, pre-integration). **This is the real artifact-identity gap**:
  O2 (K1 acceptance) cannot proceed on the currently-integrated source without a fresh MinGW build first —
  none exists in evidence.

## 3. Minimal ordered path to live acceptance

1. **Fix the prepared diagnostic's binary paths** (not a code change — an environment/invocation fix): resolve
   a real, non-wrapper ffmpeg and ffprobe (the `/home/brunner56/.local/bin/*` pair are wrappers the ledger's
   own design explicitly distrusts) and a python3.14, or repoint the invocation at whatever interpreter this
   host actually has (`python3.12`) after confirming `capture_diagnostic` runs under it.
2. **Get explicit user authorization** for the one capture attempt (still required per the prepared doc and
   ledger:357: *"paused under the handoff host-isolation requirement"*), plus a fresh foreign-process recheck
   at attempt time (PotPlayer/wineserver 407438 and mpv 1451616 must stay untouched and must not collide with
   new run/snapshot paths).
3. **Run O1** (the single authorized diagnostic) under the canonical lock. If it passes, it closes the
   live-display leg only.
4. **Rebuild the Windows DLL from current integrated source** (post GOG-regen/H0/runtime-integration) — no
   such build currently exists in evidence; O2 cannot honestly proceed without it.
5. **Run the L1 camera-diagnostic launch** (one authorized attempt, `KP_MAX_BOOT_ATTEMPTS=1`), gated by
   `postrun-gate.py --require-l1` before any V1 route (O2/O3).
6. **Run the K1 V1 acceptance route** referencing the L1 receipt by hash.
7. Everything else (O4 host-integration, O6 release-builder patch, O7 pause production wiring, O5 browser
   live cross-client proof, K2/native Windows/Mac acceptance) is either already closed host-only or explicitly
   deferred/low-priority per the ledger's own ordering, and does not block steps 1-6.

## 4. Single blocking item most needing a user decision

**Step 1 above** — the prepared diagnostic literally cannot run on this host as written (missing
`python3.14`, missing `/usr/bin/ffmpeg`, missing the linuxbrew `ffprobe`). Someone has to decide whether to
(a) install/restore those exact binaries to match the invocation, or (b) have a writer re-verify
`capture_diagnostic` against the wrapper `ffmpeg`/`ffprobe` that actually exist now and accept the residual
risk the ledger's rounds 9-13 spent effort ruling out (wrapper vs. real-ELF ambiguity), or (c) target a
different available interpreter/toolchain and update the invocation doc. This is a user-level tooling
decision, not something safely made unilaterally given how much of rounds 9-13 was specifically about not
trusting substitute binaries.

## 5. Stale or wrong items in the prepared invocation

- `/usr/bin/python3.14` does not exist on this host (`/usr/bin/python3.12` is what's installed).
- `/usr/bin/ffmpeg` does not exist (only `/home/brunner56/.local/bin/ffmpeg`, a wrapper).
- `/home/linuxbrew/.linuxbrew/bin/ffprobe` does not exist (only `/home/brunner56/.local/bin/ffprobe`, a
  wrapper) — this contradicts the invocation's own stated intent to use "brew ffprobe" and avoid the
  `~/.local/bin` wrapper (a distinction the ledger fought hard to establish in rounds 9/13).
- The doc's PID-based warning ("last read-only check found foreign PotPlayer and two wineservers") is
  correctly hedged ("Recheck rather than relying on those historical PID values") — this session's recheck
  found only **one** wineserver (pid `407438`, tied to PotPlayer) plus the mpv, not two wineservers; the doc's
  own caveat already anticipates this drift, so no action needed beyond rechecking at run time as it says.

## Grill me

- **Weakest first:** did I actually confirm the prepared diagnostic's ffmpeg/ffprobe paths are wrong, or did
  I just fail to find them due to a sandboxed/restricted `$PATH`? — I ran `ls -la` directly on both absolute
  paths (`/usr/bin/ffmpeg`, `/home/linuxbrew/.linuxbrew/bin/ffprobe`) and both returned "No such file or
  directory" from the shell tool available in this session; I did not attempt this from a different shell or
  as a different user, so if this sandbox's filesystem view differs from the "real" host the diagnostic would
  run on, my finding could be an artifact of the sandbox rather than genuine host drift. Confidence: medium.
- Did I verify the `/tmp/lifecycle-cfg` build is actually current (not just newer than two sampled files)? —
  No; I checked only `CMakeLists.txt` and `engine_k1.cpp` mtimes against the build directory's newest
  binaries. I did not diff every one of the ~177 dirty files against build timestamps. Referent:
  `stat -c '%Y %y %n'` on those two files vs `ls -la /tmp/lifecycle-cfg` (this session). Confidence: medium.
- Is the O7 (pause production wiring) "dropped obligation" call solid, or did I miss an assignment elsewhere
  in the ledger? — I read all 386 lines once, sequentially, and did not find a pause-integration owner in the
  final integration-scope statement (ledger:355). I did not grep the ledger a second time specifically for
  "pause" as a targeted check. Referent: progress.md:355 lists "scripts Host registration/lifetime, vector,
  motion and its server-MainLoop owner latch, CMake targets, namespace coverage, and reviewed address
  diagnostics" with no mention of pause. Confidence: medium-high.
- Did I confirm no live-game.lock holder, or could the sandbox's overlay-fs warnings from `lsof` be hiding a
  real holder? — `lsof` on the lock file printed only overlay-fs stat warnings and no PID lines; I could not
  cross-check with `fuser` (not installed) or `flock -n` (would itself attempt to acquire the lock, which I
  was told not to do). Confidence: low-medium; treat "not held" as provisional, recheck at run time as the
  prepared doc itself instructs.
- Is the "no fresh Windows DLL since integration" claim solid? — I searched the evidence root and worktree
  for `*.dll` and found only third-party/system DLLs inside Wine prefixes and one old `third_party/luajit`
  DLL; I did not search outside `/home/brunner56/kp-live-20260922` and the worktree (e.g. a private build
  output directory elsewhere on disk could exist that I didn't know to look for). Confidence: medium.

**One question I could not settle:** whether a fresh MinGW Windows DLL build already exists somewhere outside
the two trees I searched (evidence root + worktree) — the single check that would settle it is asking the
user directly, or a full-disk `find / -iname 'kphasor*.dll' -newer <CMakeLists.txt>` (not run here to respect
the read-only/no-build-artifact-touching scope of this task; also would require broader filesystem access
than this sandbox may have).

---
## Root correction (2026-09-28, coordinator)

claim: "prepared diagnostic is stale/unrunnable — /usr/bin/python3.14, /usr/bin/ffmpeg, /home/linuxbrew/.linuxbrew/bin/ffprobe do not exist"
referent: agent shell ran inside the ubuntu-dev distrobox (/run/.containerenv present, os-release Ubuntu 24.04). The invocation's paths are Fedora-host paths.
checked: `ls -l /run/host/usr/bin/python3.14 /run/host/usr/bin/ffmpeg /run/host/usr/bin/ffprobe` all present; `/run/host/home/linuxbrew/.linuxbrew/bin/ffprobe -> ../Cellar/ffmpeg/9.0.1_1/bin/ffprobe` present.
verdict: does not hold. The invocation is runnable as written ON THE HOST (not inside the distrobox). Add to preconditions: run from a host shell; tool hashes must be taken from host paths.
confidence: high; would change if the host-side binaries fail to execute.

claim: "no post-integration Windows DLL build exists"
referent: newest kphasor.dll under the KotorPhasor tree is 2026-09-22 16:51 (build/, tmp/k1_harness/); runtime.cpp mtime 2026-09-27 22:09.
checked: `find <repo> -maxdepth 5 -iname '*phasor*.dll'`
verdict: holds. Fresh build dispatched to /home/brunner56/kp-live-20260922/dll-build-20260928/ (no deploy).

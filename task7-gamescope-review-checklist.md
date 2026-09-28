# Task 7 Gamescope exact-window backend: review checklist

## Review verdict contract

This is a task-scoped review of the implementation defined by
`task7-gpu-window-implementation-brief.md`.  It is not a support declaration
for native Wayland, Windows, macOS, ChromeOS, K2, or every GNOME/KDE release.

The smallest proof referent is a single immutable chain:

`owned Gamescope lease -> exact game PID/start identity -> exact mapped X11 window/geometry -> ffmpeg -window_id target -> continuous media -> physical console semantic result -> recorder-first cleanup -> explicit visual decision`

Any broken or inferred link is a failed acceptance, even when the route passes
or FFmpeg produces a valid MP4.  Host-only tests prove lifecycle logic only;
they do not prove a live GPU, installed game, physical input, visual behavior,
or platform support.

Verdicts:

* **Critical**: permits foreign desktop/process/window/input/capture access,
  kills a process it does not own, emits authentication material, publishes a
  false success/support claim, or allows a passing receipt without the exact
  identity/evidence chain.
* **Important**: violates the specified lifecycle, failure handling, immutable
  receipt, or regression contract but does not directly cross a host ownership
  boundary.
* Minor observations do not block this slice unless they make the required
  evidence ambiguous.

## 1. Scope and product boundary

- [ ] **Critical — owned-file scope:** The diff changes only the files named in
  the implementation brief.  It contains no private prototype imports,
  absolute local paths, copied game assets, routes, controller scripts, or
  build artifacts.
- [ ] **Critical — explicit backend selection:** `linux-wine-k1-gamescope` is a
  separate adapter.  `linux-wine-k1` remains the Xvfb/software adapter.  No
  environment auto-detection silently changes an existing run to Gamescope.
- [ ] **Critical — admission before mutation:** An unsupported/missing
  capability fails before claiming stage/prefix/output directories, prompting
  for permissions, launching Wine/game, or touching saves.
- [ ] **Critical — support wording:** Interface records for Windows, macOS,
  ChromeOS, or native/shared Wayland are `refused`/unimplemented.  Source-level
  protocols do not become support claims.
- [ ] **Important — target wording:** This slice names Linux K1/Wine only.  It
  does not imply K2, native Linux ELF, or cross-platform runtime support.

## 2. Host semantics: X11, Wayland, GNOME, and KDE

- [ ] **Critical — layers stay distinct:** Receipts separately record host
  session protocol (`x11`/`wayland`), desktop (`GNOME`/`KDE`/other), and the
  game-facing nested display (`gamescope-xwayland`).  They never serialize a
  Wayland host as proof of native Wayland game control/capture.
- [ ] **Critical — private display only:** The Gamescope backend constructs a
  child environment allowlist.  It does not inherit or reuse the caller's
  `DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY`, desktop D-Bus address, portal
  variables, or desktop-session authority.
- [ ] **Critical — GNOME/KDE are host conditions:** Both GNOME and KDE X11 or
  Wayland hosts may admit the owned Gamescope/Xwayland adapter when its probes
  pass.  Neither desktop name substitutes for a successful nested-display,
  renderer, input, or capture probe.
- [ ] **Critical — no portal substitution:** Failure to create the owned
  nested display does not fall back to `xdg-desktop-portal`, `wtype`,
  `ydotool`, root capture, or the user's compositor session.
- [ ] **Important — detected facts are factual:** `HostFacts` distinguishes
  session type, desktop/compositor, container/Crostini markers, OS/version,
  architecture, executable availability, and probe results.  `DISPLAY` or
  `WAYLAND_DISPLAY` presence alone never admits a backend.
- [ ] **Important — X11-host coverage:** Host-only tests exercise an X11 host
  environment and prove Gamescope still creates/uses its own Xwayland authority
  instead of borrowing the host X server.
- [ ] **Important — GNOME/KDE Wayland coverage:** Host-only tests exercise
  representative GNOME-Wayland and KDE-Wayland facts and prove both select the
  same private Gamescope/Xwayland semantics, with receipts retaining the
  different host desktop facts.
- [ ] **Important — ChromeOS refusal:** Crostini and Borealis/Steam are detected
  distinctly and refused unless a future separately named adapter proves its
  full owned path.  Forwarded X11/Wayland and `/dev/dri` presence are facts,
  not admission.

## 3. Immutable contracts and capability admission

- [ ] **Critical — immutable records:** `HostFacts`, `BackendCapabilities`,
  lease identity, process identity, and `OwnedWindow` are immutable values;
  there are no class-level/per-run mutable attributes or mutable receipt
  aliases that can be changed after capture starts.
- [ ] **Critical — target is mandatory:** Input and window recording accept an
  `OwnedWindow`/capture-source record, never a bare display integer, arbitrary
  window ID, root window, or screen tuple.
- [ ] **Critical — capability gate:** `OwnedX11Input` refuses a target/lease
  lacking `x11_input`; the exact-window recorder refuses one lacking the
  declared exact-window capture capability.
- [ ] **Important — refusal is explicit:** Every absent required capability has
  a stable refusal reason suitable for a preflight receipt.  Detection and
  admission are distinct fields.
- [ ] **Important — no fabricated target:** Game/session code obtains window
  identity only through verified discovery bound to the active lease.  It
  cannot construct an admitted `OwnedWindow` from CLI/user values.

## 4. Gamescope/Xwayland lease lifecycle

- [ ] **Critical — owned process group:** Gamescope and readiness child are
  launched in a new, recorded process group.  Teardown signals only identities
  recorded by this lease and revalidates PID/start identity before escalation.
- [ ] **Critical — no broad cleanup:** There is no `pkill gamescope`, kill by
  display number/name, global Wine kill, desktop scan, or process-name-only
  teardown.
- [ ] **Critical — authority secrecy:** Receipts/logs record only sanitized
  display identity and whether Xauthority exists.  They never emit an Xauthority
  cookie, environment dump, token, or other authentication contents.
- [ ] **Critical — atomic readiness:** The child writes temporary JSON and
  atomically renames it only after collecting the allowed keys.  The parent
  rejects malformed JSON, unexpected keys, missing/invalid `DISPLAY`, absent
  authority, dead parent/child, stale ready files, and timeout.
- [ ] **Important — command contract:** The launch is argument-array based and
  contains `gamescope --backend headless`, requested input/output dimensions,
  refresh rate, and a helper child with no hardcoded filesystem path.
- [ ] **Important — readiness probes:** The lease verifies the exact published
  X11 endpoint with bounded commands/timeouts before launching Wine.
- [ ] **Important — idempotent close:** Normal close, partial-start failure,
  SIGTERM path, and repeated close release only lease-owned resources and leave
  a complete cleanup result.
- [ ] **Important — cleanup residue test:** Fake-process tests assert no owned
  child/group remains after success, readiness timeout, renderer refusal,
  boot failure, recorder failure, and double teardown.

## 5. Renderer and game environment

- [ ] **Critical — renderer proof binds the lease:** `glxinfo -B` runs with the
  same exact nested display authority later used for Wine, input, discovery,
  and capture.  A host GPU probe is insufficient.
- [ ] **Critical — software renderers refused:** Failed probe, indirect
  rendering, `Accelerated: no`, llvmpipe, softpipe, or other recognized
  software renderer strings refuse the backend before game launch.
- [ ] **Critical — environment isolation:** Game environment starts from the
  isolated session environment, removes only `LIBGL_ALWAYS_SOFTWARE`,
  `GALLIUM_DRIVER`, and `LP_NUM_THREADS` for the GPU adapter, then overlays the
  lease values.  It does not import desktop D-Bus/portal/X11/Wayland authority.
- [ ] **Important — Xvfb unchanged:** The software adapter retains its current
  forced-software behavior and does not remove those variables as a side
  effect of adding the GPU adapter.
- [ ] **Important — bounded raw evidence:** Raw renderer output is retained;
  parsed receipt includes direct/accelerated decision and renderer string but
  does not claim game FPS or game-context renderer identity.

## 6. Window/PID/start identity

- [ ] **Critical — exact process identity:** Discovery binds the game PID to a
  non-empty process start identity and to the owned Wine prefix/stage/process
  tree.  PID equality alone is insufficient because of reuse.
- [ ] **Critical — exact display/lease:** Every X11 query runs against the
  lease's exact sanitized environment.  The resulting target carries the same
  lease ID; cross-lease targets are refused.
- [ ] **Critical — exactly one visible window:** Zero, multiple, foreign,
  hidden, root, missing-owner, non-positive-geometry, and query-failure cases
  fail closed.  Selection is not "largest window" or title/regex based.
- [ ] **Critical — immutable first target:** The first verified mapped game
  window is frozen.  A replacement window is a typed terminal failure; the
  recorder/input path never follows it silently.
- [ ] **Critical — revalidation:** Before input and throughout capture, the
  implementation rechecks window ID, owner PID, PID start identity, lease,
  visibility, and positive geometry.
- [ ] **Important — actual geometry:** Requested Gamescope geometry and actual
  mapped game-window geometry are separate.  A K1 fallback to 800x600 is
  captured as 800x600 rather than rejected solely for differing from 1024x768.
- [ ] **Important — query bounds:** Every `xdotool`/X11 query has a finite
  timeout and typed failure evidence.  A stuck query cannot leave the route
  reporting success.

## 7. FFmpeg exact-window capture

- [ ] **Critical — exact command:** GPU capture argv contains `-f x11grab`, the
  target's exact X11 input, target discovery-time `-video_size`, and
  `-window_id <canonical target id>`.  It never uses a shell string.
- [ ] **Critical — no root substitution:** GPU capture cannot issue root-only
  `-i :N.0` without `-window_id`; configured screen size cannot substitute for
  actual game geometry.
- [ ] **Critical — reject root/invalid IDs:** Missing, root, malformed,
  noncanonical, foreign-lease, odd, zero, or negative geometry targets fail
  before FFmpeg starts.
- [ ] **Important — start ordering:** GPU recording starts only after the first
  mapped owned window is verified.  Receipt states
  `after_first_mapped_owned_window`.
- [ ] **Important — bounded resources:** Capture preserves configured sampling
  FPS bounds, no interpolation, existing bounded thread counts, continuous
  landscape master, and argument-array receipt.
- [ ] **Important — single start:** Recorder restart/double start is rejected.
  Stop is idempotent and cannot signal an old/replaced process.

## 8. Asynchronous watch, resize/loss, and route integration

- [ ] **Critical — full-route watch:** At no more than 250 ms intervals, the
  watcher validates lease parent/child liveness, FFmpeg liveness, window
  identity, PID/start identity, visibility, positive geometry, and unchanged
  width/height for the entire route.
- [ ] **Critical — early zero exit fails:** FFmpeg exiting before deliberate
  finalization is terminal even with return code 0 or a playable MP4.
- [ ] **Critical — resize/loss fails:** Resize, disappearance, replacement,
  owner change/reuse, lease death, or X11 query error/timeout becomes one typed
  terminal capture failure.  This slice does not restart/reframe capture.
- [ ] **Critical — route observes failure:** Thread-safe failure state is
  consumed before and after every route step and before success/media
  publication.  A late watcher failure cannot race into `route=passed` or
  `ok=true`.
- [ ] **Important — failure receipt:** `capture-failure.json` includes initial
  identity, last verified identity, elapsed time, FFmpeg status, and stable
  error class.  Partial MP4/logs remain available.
- [ ] **Important — no representative success on failure:** Capture failure
  blocks representative rendering and visual-success publication while
  retaining partial media with `retained_failure_recording`.
- [ ] **Important — finalization exception is narrow:** FFmpeg 255 is accepted
  only when SIGINT was sent during orderly stop to a process known live at
  that moment.  Natural/early 255 and all other nonzero exits fail.

## 9. Teardown and failure paths

- [ ] **Critical — teardown order:** For success, route failure, boot failure
  after display creation, SIGTERM, and recorder failure: mark recorder stopping;
  stop/join watcher and FFmpeg; close channel/game; stop matching owned
  Wine/prefix/stage processes and its Wine server; close readiness child and
  Gamescope group; then release locks and write final identities.
- [ ] **Critical — ownership on every signal:** Every signal/kill target is
  checked against stored PID/start/process-group/prefix/stage identity at the
  point of cleanup.  PID reuse causes refusal rather than a kill.
- [ ] **Important — all cleanup attempted:** A recorder error does not skip
  game/display cleanup; a game cleanup error does not skip display cleanup.
  The receipt retains each component result plus aggregate failure.
- [ ] **Important — watcher cannot self-report stop as failure:** Deliberate
  recorder/display teardown is ordered and marked so the watcher does not race
  with it and manufacture a capture-loss error.
- [ ] **Important — double teardown:** Repeated teardown is safe, does not
  signal anything twice, and preserves the first failure instead of replacing
  it with a clean result.

## 10. Schema-2 receipt and success semantics

- [ ] **Critical — atomic identity chain:** One schema-2 receipt binds backend,
  host facts/admission, lease owner PID/start identities, requested display
  geometry, renderer probe, exact game window PID/start/geometry/lease,
  FFmpeg argv/window ID, route/physical-console result, media, and cleanup.
- [ ] **Critical — immutable evidence:** Receipt data is copied/frozen at event
  time; later mutation of a capability, target, command list, or nested dict
  cannot rewrite prior evidence.
- [ ] **Critical — `ok` cannot self-certify:** `ok` remains false until route,
  exact physical-console correlation, capture, cleanup, source/input
  preservation, and a separately recorded explicit human visual acceptance all
  pass.  `media.status=retained_for_visual_review` is not final success.
- [ ] **Critical — failures preserve identities:** Capture or cleanup failure
  retains all known identity fields and typed failure evidence; it does not
  fall back to schema 1 or omit the failed component.
- [ ] **Important — cadence separation:** Requested sampling FPS, encoded
  average/nominal FPS and frame count, FFmpeg duplicate/drop diagnostics,
  distinct-frame analysis, and visual review are separate fields.  Encoded
  60 FPS is never described as 60 distinct game frames.
- [ ] **Important — path/secrets policy:** Only user-selected run/stage/prefix/
  artifact absolute paths are emitted.  No full environment, Xauthority data,
  portal tokens, or credentials enter receipts/logs.
- [ ] **Important — visual scope:** Visual acceptance explicitly covers native
  behavior, framing, readability, cadence, defining effect, and absence of
  misleading transitions.  It does not replace route correctness.

## 11. Preserve the Xvfb/software backend

- [ ] **Critical — existing constructibility:** `linux-wine-k1` still builds an
  Xvfb `LinuxWineCreativeSession` plus `X11Recorder`; its backend ID and CLI
  behavior remain stable.
- [ ] **Critical — root recorder remains scoped:** Xvfb continues root/display
  capture with `-i :N.0`, and its receipt explicitly identifies software/Xvfb
  root capture.  It is never relabeled as exact-window or GPU proof.
- [ ] **Important — existing ordering:** Xvfb recorder still starts after Xvfb
  readiness and before game launch, and stops before game/Xvfb teardown.
- [ ] **Important — existing gates:** All pre-existing creative tests pass
  unchanged or with only necessary schema-aware assertions.  New tests exercise
  both backends side by side.
- [ ] **Important — interface extraction does not weaken checks:** Moving
  window discovery preserves single-visible-window, PID ownership, positive
  geometry, replacement, timeout, and exact-display checks for existing users.

## 12. Required host-only test evidence

The focused test must use injected process/time/readiness/environment/probe/
X11/FFmpeg seams and launch no real Wine, game, Xvfb, Gamescope, or recorder.

- [ ] Backend capability table and pre-mutation refusals.
- [ ] X11, GNOME-Wayland, and KDE-Wayland host facts with private nested
  Gamescope/Xwayland semantics; native/shared Wayland remains refused.
- [ ] Environment allowlist and authentication-value redaction.
- [ ] Missing dependencies; readiness timeout/death/stale/malformed file;
  invalid display; X11 probe failure.
- [ ] Direct/accelerated renderer pass and indirect/software/failure refusals.
- [ ] Zero/one/multiple/foreign/root/hidden/replaced/lost/resized windows,
  PID reuse, cross-lease targets, and X11 timeout.
- [ ] GPU FFmpeg argv proves `-window_id` plus actual geometry; software argv
  proves unchanged root capture.
- [ ] FFmpeg early exit 0/nonzero/255, watcher failure, lease death, partial
  MP4 retention, and representative-media suppression.
- [ ] Route checks asynchronous capture failure before and after every step.
- [ ] Normal, boot-error, SIGTERM-equivalent, recorder-error, and double
  teardown prove recorder -> game/Wine -> Gamescope order and no foreign kill.
- [ ] Schema-2 nested immutability, failure completeness, cadence separation,
  visual-pending semantics, and `ok=false` until explicit visual acceptance.
- [ ] Existing Xvfb assertions remain and the complete focused script passes.
- [ ] Existing CTest `kpharness_creative_test` label gate passes after the
  focused test.  Report exact commands, counts, and outputs.

## 13. Live acceptance required before the scoped support claim

- [ ] The run uses a clean materialization of the frozen Task 7 source
  allowlist and fresh build/runtime/proxy, with before/after hashes.
- [ ] The installed K1 source, stage, prefix, build, output, and checkpoints are
  pairwise disjoint as required; one global live-game lock is held.
- [ ] The named host is recorded precisely, for example “Fedora KDE Wayland
  host”; the claim remains “K1/Wine Gamescope-Xwayland backend,” not generic
  Wayland/GNOME/KDE support.
- [ ] Renderer evidence proves accelerated non-software rendering inside the
  exact lease used by the game.
- [ ] One mapped game window binds PID/start/lease/actual geometry, and the
  receipt's FFmpeg argv contains that exact `-window_id` and geometry.
- [ ] Continuous landscape MP4 is playable, hashed, probed, and survives the
  complete route without target resize/loss or recorder exit.
- [ ] F12/Enter uses the physical owned input path and proves exact
  console-session/submission/request correlation, semantic return values, and
  the in-game DirectInput counter delta.
- [ ] Recorder-first cleanup leaves zero owned game, Wine, readiness-child, and
  Gamescope processes; source and all frozen inputs retain hashes.
- [ ] A reviewer explicitly accepts the unaltered native-behavior master for
  behavior, framing, readability, and cadence.  GIF/short output is secondary
  presentation, not acceptance evidence.
- [ ] Final claim cites this exact host/backend/target/artifact identity and
  lists all unaccepted platform cells as refused or unimplemented.

## 14. Immediate reject patterns

Reject without spending review time on presentation polish if any appears:

1. Gamescope backend reuses a caller/desktop display, D-Bus, portal, or
   Xauthority.
2. Window selection is largest/title/regex based, or capture accepts a bare ID.
3. PID is not paired with start identity and the owned process tree/lease.
4. GPU FFmpeg command lacks `-window_id` or captures the X11 root.
5. A target replacement, resize, query error, lease death, or early FFmpeg exit
   can still yield `ok=true`.
6. Teardown kills by name/display or can signal a PID after start-identity
   mismatch.
7. Schema 2 calls encoded FPS distinct game FPS, treats a valid MP4 as visual
   acceptance, or omits failure identities.
8. Xvfb behavior/regressions are removed to make the Gamescope tests pass.
9. Documentation says native Wayland, GNOME, KDE, Windows, macOS, ChromeOS, K2,
   or general cross-platform support from this Linux K1/Wine slice.

## Review conclusion template

* Spec verdict: PASS / FAIL
* Quality verdict: PASS / BLOCKED
* Critical findings: count and exact file:line evidence
* Important findings: count and exact file:line evidence
* Xvfb regression gate: command and result
* Gamescope host-only gate: command and result
* CTest gate: command and result
* Live acceptance: not run / failed / passed, with immutable run receipt path
* Accepted support cell: exact target + backend + host desktop/session
* Refused/unimplemented cells: native/shared Wayland, Windows, macOS, ChromeOS,
  K2, and any GNOME/KDE host combination not actually accepted

The implementation is review-clean only when both verdicts pass with no open
Critical or Important findings.  It is support-accepted only after the separate
live run and visual decision satisfy section 13.

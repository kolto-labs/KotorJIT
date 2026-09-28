# Cross-platform display, input, and capture audit

Audit date: 2026-09-27  
Repository snapshot inspected: `ca329e52dd27d1a3f5a56748d93c8ab0fd7f24f2` plus the 53-path dirty worktree at `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`  
Method: read-only source, documentation, and private-receipt review. No build, game, recorder, or platform session was started.

## Verdict

KotorPhasor does not currently have a cross-platform display/input/capture subsystem. It has a strong, narrow Linux controller path around a Windows PE32 game running under Wine:

* **Proven now:** K1 GOG under Wine, inside an owned Linux Gamescope/Xwayland environment, accepted one physical F12/typing/Enter transaction against one PID-owned game window. The exact request correlation, DirectInput activity, visible overlay, source preservation, and clean teardown were reviewed in `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-014019` and summarized by `task7-supported-console-live-review.md`.
* **Implemented in the worktree:** the reusable console protocol/driver and an X11 input adapter; an owned Xvfb/Wine session; an X11 root recorder; Win32 in-process overlay/input interception. These pieces are useful but do not form a platform-neutral backend.
* **Prototype evidence only:** an isolated headless Gamescope/Xwayland lease reached an accelerated AMD renderer, and private media runs observed GPU frames. The checked-in worktree has no Gamescope backend, no exact-window GPU recorder, and no atomic acceptance receipt binding acceleration, game-window identity, physical console, continuous capture, cadence, and teardown.
* **Unimplemented as native support:** Windows, macOS, ChromeOS, native Wayland, GNOME-specific and KDE-specific portal paths. Wine execution is not native Windows evidence. A Mach-O metadata parser is not a Darwin loader or runtime. A Wayland desktop hosting Xwayland is not a native Wayland backend.

The fastest truthful route is to turn the already demonstrated private Gamescope/Xwayland boundary into a checked-in Linux backend, finish exact-window recording, and accept K1 end to end. Native Windows comes next because the game runtime and overlay are already Win32. Native macOS requires a new loader/runtime/present/input stack and exact modern game images. ChromeOS must remain variant-specific and refused until a real device proves an admissible execution boundary.

## Evidence strength and support vocabulary

The matrix below uses these meanings:

| Label | Meaning |
| --- | --- |
| **Accepted** | A named binary and host/backend combination passed a real-machine end-to-end gate, including physical input, exact ownership, semantic correlation, capture where claimed, and cleanup. |
| **Narrowly proven** | A real-machine result proves only the listed capability. It cannot be generalized to another host, protocol, desktop, game, binary, or recorder. |
| **Implemented, host-tested** | Source and synthetic/host tests exist, but the named live acceptance has not passed. |
| **Prototype** | Private or experimental code/evidence exists outside the supported checked-in path. |
| **Static only** | Parsing, profiles, source presence, or compilation exists without loader/runtime/live proof. |
| **Refused** | The controller must reject the combination before staging or launch. |

`docs/release-platform-status.md:3-12` is the controlling release statement: K1 and K2 evidence is Wine-based, while the Mac corpus images are static-only legacy i386 images. Its shared contract at lines 14-24 correctly assigns image format, relocation, ABI, object layout, memory protection, input, and rendering to platform adapters. Its Mach-O statement at lines 26 and 32 explicitly excludes runtime loading.

## Current architecture and what can be reused

### Controller/session layer

`scripts/harness/kpharness/session.py` is a Linux X11/Wine session implementation presented as a general `GameSession`:

* It strips desktop D-Bus and Wayland authority, forces X11, and starts Xvfb.
* `SessionInfo` carries `display` and `xvfb_pid`, which embeds one backend in the public session shape.
* Ownership and locks depend on `/proc`, Linux `fcntl`, display-number lock files, a Wine prefix, and a staged working directory.
* Window capture uses `xdotool` against the current Xvfb display and requires exactly one visible window owned by a session PID.
* The environment forces `LIBGL_ALWAYS_SOFTWARE=1` and `GALLIUM_DRIVER=llvmpipe`.
* Teardown knows Wine, `wineserver`, Xvfb, a native Linux process, and optional Steam/mwm processes.

That lifecycle should be decomposed. Adding macOS and Windows branches to this class would make ownership and cleanup unverifiable.

`scripts/harness/kpharness/creative.py` admits only `linux-wine-k1`. `creative_wine.py` adds valuable ownership rules: private source/stage/prefix separation, PID selection by Wine prefix plus working directory, recorder-before-display teardown, and source receipts. Its `fcntl` lock, `/proc` ownership, and Xvfb assumptions are Linux-specific.

### Console and input layer

`scripts/harness/kpharness/physical_console.py` is the most reusable boundary already present:

* `ConsoleProtocolPort` observes protocol state and request/output rows.
* `OwnedInputPort` exposes focus, F12, select-all, text, Enter, and Escape without embedding the host mechanism.
* `PhysicalConsoleDriver` requires an exact runtime/session identity, a single physical submit, `submitted + 1`, the exact request outcome, and undropped request-filtered input/result rows.

`scripts/harness/kpharness/owned_x11.py` is a good first adapter, not a generic implementation. It binds input to a live `GameSession`, the exact display, a live Xvfb owner, and a revalidated PID-owned window, then uses `xdotool`. `tools/kpharness_physical_console_test.py` covers clean/already-open console states, stale identities, duplicate submission, timeouts, malformed responses, dropped/foreign output, multiline input, non-Linux refusal, and window/display replacement. Those tests should become the common conformance suite for every host input adapter.

### Recording layer

`scripts/harness/kpharness/recording.py` has correct process ownership and conservative proof language, but `X11Recorder.start(display, screen, ...)` captures an entire X11 root with FFmpeg `x11grab`. It starts before the game window exists and has no immutable game-window target, replacement/resize detection, or acceleration identity. `probe_video()` explicitly records render cadence as unvalidated. This is an owned Xvfb recording utility, not GPU exact-window capture.

The private Task 7 audit confirms that no checked-in Gamescope/Xwayland adapter exists and the inherited environment forces llvmpipe. The newer implementation brief proposes the right next shape: an immutable display lease, immutable owned window, and `x11grab -window_id` recorder with continuous liveness/identity checks.

### In-process platform and overlay layer

`src/platform/platform.hpp:1-81` is a useful minimal runtime seam for page protection, executable allocation, readable mapping checks, instruction-cache flush, module base, and logging. It currently describes two targets. `src/hooks/hooks.cmake:23-29` selects Win32 on `WIN32` and Linux for everything else; macOS would incorrectly compile the Linux backend.

`src/devtools/overlay.cpp` is a Win32/WGL/DirectInput implementation:

* subclasses the game `HWND` and handles F12, keyboard, text, focus, and cursor messages;
* detours `IDirectInputDevice8A::GetDeviceState` and `GetDeviceData` so overlay capture can suppress game input;
* uses Dear ImGui Win32 plus OpenGL2 backends;
* hooks `SwapBuffers`, preserves graphics state, and restores hooks on shutdown;
* compiles to no-op functions outside `_WIN32`.

This proves the overlay belongs behind a second platform interface distinct from memory management. A Darwin memory backend alone would still provide no Cocoa events, IME, focus, OpenGL present hook, clipboard, or capture suppression.

### Build and target layer

`scripts/harness/kpharness/targets.py` defines K1 Wine, K2 Wine, and K2 native Linux. There are no native Windows, Darwin, ChromeOS, Wayland, or desktop-variant controller targets.

`src/runtime/runtime.cmake:5-10` defines only a 32-bit Windows DLL and 32-bit Linux shared object. Lines 15-24 include only ImGui Win32/OpenGL2 backend sources. The Windows artifact is cross-linked with i686 MinGW and static GCC/C++ runtimes; there is no native Windows test execution. `.github/workflows/cmake-multi-platform.yml` runs Ubuntu jobs only, including MinGW cross-compilation. Its name does not constitute host-platform coverage.

### Mach-O layer

`src/image/macho.cpp:27-103` safely parses bounded, thin, little-endian Mach-O 32/64 headers, segments, and sections and refuses fat and big-endian containers. `tools/kp_machotest.cpp` supplies extensive synthetic coverage, and the private report records 1,095 synthetic checks plus four checks against the two private images.

The parser intentionally consumes a complete on-disk image and reports unslid virtual addresses. The live image path still recognizes only PE32 and ELF32 (`src/image/parse.cpp:172-177`), and `src/image/load.cpp:47-74` has only Windows module lookup or a non-PIE ELF base. Missing Darwin work includes fat-slice selection, loaded-image enumeration, ASLR slide, mapped-section parsing, code-signing/hardened-runtime behavior, architecture-specific detours, loader entry, and live ABI validation.

## Platform/backend matrix

GNOME and KDE are desktop/compositor implementations. X11, Wayland, and Xwayland are display protocols. The matrix keeps those axes separate.

| Host / desktop | Game-facing protocol and execution | Physical console input | GPU/window capture | Current status | Gate before support claim |
| --- | --- | --- | --- | --- | --- |
| Linux, isolated headless Gamescope; host desktop unspecified | K1 PE32 under Wine; private Xwayland | Production X11 adapter physically sent F12/text/Enter to one PID-owned window; DirectInput count and exact protocol result advanced | Accelerated Gamescope renderer proven separately; checked-in exact-window recorder absent | **Narrowly proven input path; capture prototype** | Check in lease/window recorder; one atomic K1 receipt binding artifact, renderer, exact window, input, capture, cadence, visual review, and cleanup |
| Linux X11, GNOME | K1/K2 PE32 under Wine on a fresh Xvfb or nested Gamescope Xwayland | XTEST through `xdotool` is implemented for the owned Xvfb path | Root Xvfb software capture only; Gamescope exact-window path unimplemented | **Implemented software path; GNOME combination unaccepted** | Real GNOME/Xorg machine, named GPU/driver, owned nested display, exact-window video and physical-console acceptance |
| Linux X11, KDE Plasma | Same as GNOME X11 | Same XTEST adapter | Same limitations | **Implemented software path; KDE combination unaccepted** | Real Plasma/Xorg acceptance; do not infer it from GNOME or a desktop-neutral unit test |
| Linux Wayland, GNOME Shell | Current K1/K2 Wine game would still use private Xwayland under Gamescope; no native Wayland game adapter | X11 input inside owned nested Xwayland is feasible; host Wayland global input is forbidden without portal permission | Nested Xwayland window capture is proposed; host/native Wayland capture unimplemented | **No GNOME-Wayland acceptance** | Test owned Gamescope/Xwayland as a host-compatibility cell; separately test portal ScreenCast/RemoteDesktop if shared-desktop Wayland is claimed |
| Linux Wayland, KDE Plasma/KWin | Same private Xwayland distinction | Same; KDE portal behavior must be tested independently | Same; no KWin-native capture backend | **No KDE-Wayland acceptance** | Same two gates, using `xdg-desktop-portal-kde`; GNOME portal results do not transfer |
| Native Linux K2 ELF, X11 | 32-bit native ELF uses X11/OpenGL directly | Runtime overlay is a non-Windows stub, and K2 native lacks the demonstrated console path | Xvfb recording utility could record the root; no accepted GPU window capture | **Runtime target exists; console/capture unsupported** | Implement native overlay/input boundary and accept exact K2 binary on real X11/GPU |
| Native Linux, native Wayland client | No target; KOTOR binaries are not native Wayland clients | No adapter | No adapter | **Refused** | A distinct target and owned surface are prerequisites; a Wayland host running Xwayland does not satisfy this cell |
| Native Windows | K1/K2 PE32 runtime and Win32 overlay source exist; artifacts are cross-built on Linux | In-process Win32/DirectInput capture exists; out-of-process owned input/session backend does not | No Windows Graphics Capture backend or native receipt | **Unimplemented native host** | Real Windows build/install/launch, Job ownership, HWND identity, `SendInput`, WGC capture, semantic receipt, cleanup/removal |
| macOS Intel, current Steam x86_64 candidate | Exact current K1/K2 images and a Darwin runtime are absent; K2 has partial source-level API profile work only | No Cocoa/CoreGraphics input adapter | No ScreenCaptureKit adapter | **Refused** | Acquire/hash exact image, implement Darwin runtime/ABI/overlay, then real-machine TCC/input/capture acceptance |
| macOS Intel, legacy i386 corpus | Static thin Mach-O parsing and some profiles exist | No runnable backend on current macOS | No backend | **Static only** | Requires an Intel Mac on macOS 10.14 or earlier plus architecture-matched runtime; modern macOS cannot run this target |
| macOS Apple Silicon | No arm64 game/runtime target; possible Rosetta x86_64 execution is a distinct ABI/loader case | No adapter | No adapter | **Refused** | Exact Rosetta-compatible game image, x86_64 injected runtime behavior, TCC, capture, and real machine proof; never infer arm64 support |
| ChromeOS Linux container (Crostini) | Linux userspace forwarded through Sommelier; no proven KOTOR/Wine target | Container X11/Wayland input cannot control arbitrary ChromeOS host windows | Container capture does not imply host-compositor capture; `/dev/dri` and nested compositor availability vary | **Refused by default** | Detect Crostini, prove an entirely container-owned game/display/GPU/input/capture path on a named Chromebook, and label it Crostini-only |
| ChromeOS Steam/Borealis VM | Managed gaming VM/container, separate from Crostini | No ownership/injection adapter | No capture adapter or surface authority | **Refused** | Establish permitted deployment/injection, owned process/window, GPU capture, and cleanup inside the actual managed environment |
| ChromeOS host/browser/PWA | Existing native runtime cannot execute there | Browser synthetic DOM events are not physical native-game input | `getDisplayMedia()` or `chrome.desktopCapture` is user-mediated browser capture only | **Different product, unsupported** | Requires a browser-specific client/product; it cannot be represented as KotorPhasor native-game support |

Desktop compatibility claims should name both layers. For example, “K1/Wine Gamescope-Xwayland backend accepted on Fedora GNOME 49 Wayland host” would be a valid scoped claim. “Wayland supported” would be false because the game-facing input and captured surface remain X11/Xwayland.

## Reusable interface boundary

Keep the existing `PhysicalConsoleDriver` orchestration and replace host facts around it. The following immutable interfaces are sufficient.

### `HostFacts` and `BackendCapabilities`

`HostFacts` records OS/version/build, CPU architecture, container/VM markers, session protocol, desktop/compositor and version, available APIs/tools, GPU/driver, and permission state. Detection reports facts only; it cannot admit a backend merely because `DISPLAY` or `WAYLAND_DISPLAY` exists.

`BackendCapabilities` records a stable backend ID and separately answers:

* target IDs and binary architectures accepted;
* owned display/session creation;
* process ownership mechanism;
* exact window/surface identity mechanism;
* physical input method;
* capture source/method;
* acceleration proof method;
* required user authorization and whether it is session-scoped;
* explicit refusal reason for every absent capability.

Admission must occur before stage, prefix, save, permission prompt, or game mutation.

### `ProcessLease`

The stable identity is more than a PID:

* Linux: PID plus `/proc/<pid>/stat` start time, process group, namespace identity, stage cwd, and Wine prefix.
* Windows: process handle, PID, `GetProcessTimes` creation time, and assigned Job Object.
* macOS: `audit_token_t` or PID plus start time from `proc_pidinfo`, and the launched `NSRunningApplication` identity.
* ChromeOS container/VM: host variant plus container/VM identity and the inner process identity.

`close()` may stop only identities recorded by that lease. It must never kill by executable name, display number, or compositor name.

### `DisplayLease`

Returns an opaque host connection and a sanitized receipt, not `display: int`:

* backend/run/lease IDs;
* owner identities;
* protocol and compositor;
* authority/environment keys without authentication cookies;
* requested and actual geometry/scale;
* GPU adapter, driver, renderer, and proof command/API;
* `is_alive()`, `snapshot_identity()`, and idempotent `close()`.

The child environment is an allowlist. Do not inherit the user's Xauthority, desktop D-Bus, portal session, `DISPLAY`, or `WAYLAND_DISPLAY` into a supposedly isolated run.

### `OwnedWindow` / `OwnedCaptureSource`

An immutable record binds native window/surface ID, process identity, display lease ID, discovery time, visibility, client/content geometry, scale, and admitted input/capture capabilities. Every operation revalidates the identity. Replacement, loss, resize, display migration, or PID reuse is a typed failure in the first implementation; silently following another window would break evidence continuity.

### `OwnedInputPort`

Retain the existing action-level interface (`focus`, `press_f12`, `select_all`, `type_text`, `press_enter`, `press_escape`). Add:

* `preflight(target)` and permission receipt;
* `revalidate(target)` before every action group;
* a monotonically numbered action receipt with host timestamps;
* `restore()` to release modifiers and restore game input/focus state after failures.

The protocol driver, not the host adapter, continues to prove exactly one submission and the matching semantic result.

### `WindowRecorder`

`start(OwnedCaptureSource, fps, output)` accepts no display integer or generic root. It records:

* exact source/window/process/lease identity and actual geometry;
* API and GPU adapter;
* requested sampling rate, encoder rate, frame count, duplicates/drops, and separately measured distinct-frame cadence;
* permission/session identity where applicable;
* asynchronous liveness, resize/loss, and early-exit status;
* an owned graceful finalization and media hash.

Recorder failure blocks route/media success but does not erase partial logs or media. A valid MP4 proves encoding only. Visual review and semantic protocol state remain independent gates.

### `RuntimePlatform` and `OverlayPlatform`

Keep `kp::platform` for memory/module primitives and add an explicit Darwin implementation. Create a separate overlay interface for:

* present/context hook;
* native event intake and text/IME;
* focus and clipboard;
* game-input suppression/restoration;
* DPI/scale and window identity;
* renderer identity and graphics-state preservation.

Build selection must use explicit `WIN32`, `APPLE`, and Linux branches. An `else()` Linux fallback is unsafe.

## Exact APIs and security/ownership boundaries

### Linux X11 and Gamescope/Xwayland

Use an owned `gamescope --backend headless` process group with a small readiness child that publishes only its nested `DISPLAY`, `XAUTHORITY` presence, and `WAYLAND_DISPLAY`. Probe that exact environment with `xdpyinfo` and `glxinfo -B`. Admission requires direct/accelerated rendering and rejects llvmpipe, softpipe, and other software renderer strings. The renderer probe proves the lease environment, so the final receipt must also bind the launched game and captured window to the same lease.

For window ownership, the current CLI path may continue initially:

* `xdotool search --onlyvisible --pid <pid>`;
* `xdotool getwindowpid` and `getwindowgeometry`;
* exact display authority and PID/start-time revalidation.

The durable library implementation should use Xlib (`XQueryTree`, `XGetWindowAttributes`) and `_NET_WM_PID`, then cross-check the PID start identity. `_NET_WM_PID` is a client property, so it is evidence only when tied to the owned process tree and isolated display.

Physical input is XTEST (`XTestFakeKeyEvent`/`XTestFakeButtonEvent`; currently reached through `xdotool`). XSendEvent is not equivalent and does not satisfy the DirectInput path. Focus activation must stay inside the private display. Never point XTEST at the user's desktop.

Capture the immutable game window with FFmpeg X11 grab using `-window_id <id>` and the verified actual geometry. Root capture `-i :N.0` remains the software/Xvfb recorder and cannot be called exact-window GPU capture. Poll Gamescope, game, window identity/geometry, and FFmpeg liveness through the entire route.

Security boundary: the nested X server is the trust boundary. Any client with its Xauthority can observe/inject into that X server, so keep the cookie private, do not emit it in receipts, and expose no host desktop authority. Bubblewrap PID/network isolation and explicit `/dev/dri` binding strengthen ownership, but a namespace receipt is not itself proof of game capture.

### Native/shared Wayland on GNOME and KDE

Wayland deliberately prevents arbitrary clients from enumerating windows, focusing them, capturing them, or injecting global input. Cross-desktop support must use xdg-desktop-portal and must preserve user consent:

* capture: D-Bus `org.freedesktop.portal.ScreenCast` methods `CreateSession`, `SelectSources`, and `Start`, then `OpenPipeWireRemote`; consume the PipeWire/SPA stream;
* input: D-Bus `org.freedesktop.portal.RemoteDesktop` methods `CreateSession`, `SelectDevices`, and `Start`; where supported, obtain an EIS file descriptor through `ConnectToEIS` and inject with libei/EIS;
* portal implementations: `xdg-desktop-portal-gnome` and `xdg-desktop-portal-kde` are distinct acceptance cells.

The selected portal source and stream/node ID become the capture identity. The compositor, not KotorPhasor, owns the authoritative surface selection. Permission may require a visible chooser; restoration tokens and unattended reuse are implementation/policy dependent and must not be assumed. Remote-desktop input and screencast capture may need separate sessions or combined portal negotiation.

Do not use `zwlr_screencopy_manager_v1` as the common GNOME/KDE API; it is a wlroots protocol and is not the portable contract for Mutter/KWin. Do not treat `wtype` or `ydotool` as an ownership-safe replacement: one depends on compositor protocol support, while the other injects below the compositor and broadens the trust boundary.

The fastest KOTOR path on a Wayland desktop remains an owned Gamescope/Xwayland session. That is a Wayland-host compatibility result with Xwayland game input/capture. A portal backend is needed only for a separately named shared/native-Wayland mode.

### Native Windows

Session/process ownership:

* launch with `CreateProcessW` using an explicit environment and working directory;
* immediately assign the process to a `CreateJobObjectW` Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` before allowing untrusted descendants to escape; a suspended launch followed by assignment and `ResumeThread` is safer;
* retain process handles and `GetProcessTimes` creation time; enumerate descendants through the job rather than executable names;
* use a named mutex or locked run directory for the live-session slot.

Window identity:

* enumerate top-level windows with `EnumWindows`;
* bind `HWND` to the owned PID with `GetWindowThreadProcessId`;
* verify `IsWindow`, visibility, `GetClientRect`, `ClientToScreen`, DPI, and process creation identity before each operation;
* record resize, replacement, minimization, cloaking, session change, and device loss as failures.

Physical input:

* use `SendInput` with keyboard scan codes after verifying the foreground owned `HWND`;
* use `SetForegroundWindow`/`AttachThreadInput` only within Windows foreground-policy limits and verify the result with `GetForegroundWindow`;
* retain the runtime DirectInput call counter and protocol submission as the in-game proof.

UIPI and integrity levels are hard boundaries: a medium-integrity controller cannot inject into a higher-integrity game. Different user sessions and secure desktops are out of scope. The controller must refuse instead of asking for blanket elevation. `PostMessage`/`SendMessage` keyboard messages are not physical DirectInput proof.

Capture:

* target Windows 10 1903 or later for the programmatic window path;
* create a `Windows.Graphics.Capture.GraphicsCaptureItem` for the verified `HWND` through `IGraphicsCaptureItemInterop::CreateForWindow`;
* use `IDirect3DDevice`, `Direct3D11CaptureFramePool`, and `GraphicsCaptureSession`; copy timestamped frames to an encoder and monitor size/device changes;
* record the D3D adapter LUID/description and independently record the game's active OpenGL renderer from the in-process overlay (`glGetString(GL_VENDOR/GL_RENDERER/VERSION)`).

Windows Graphics Capture may display a capture border or be controlled by enterprise/privacy policy. Protected content and minimized/occluded behavior need explicit live tests. `PrintWindow`, GDI `BitBlt`, screenshots, and DXGI desktop duplication do not provide the same exact-window contract; desktop duplication is acceptable only for an explicitly output-scoped backend with crop/occlusion limits.

### Native macOS

Runtime/image layer:

* enumerate loaded images with `_dyld_image_count`, `_dyld_get_image_header`, `_dyld_get_image_name`, and `_dyld_get_image_vmaddr_slide`;
* select the exact architecture slice before parsing; retain UUID (`LC_UUID`) and code-signing identity in the receipt;
* use `mach_vm_region`/`mach_vm_protect` or in-process `mprotect`, `mmap`/`mach_vm_allocate`, and `sys_icache_invalidate` for the `kp::platform` contract;
* implement architecture-specific detours and calling conventions; i386, x86_64, and arm64/Rosetta are separate targets.

Loading/injection is a feasibility gate. `DYLD_INSERT_LIBRARIES` can serve a development acceptance only where the launched game and OS honor it. Hardened runtime, library validation, code signing, sandboxing, and SIP can block injection. KotorPhasor must not weaken global host security or modify the retail application signature as an implicit installer step. A shipping approach needs an explicit, reversible, game-specific loader and signing model.

Process/window/input:

* launch and track the app with `NSWorkspace`/`NSRunningApplication`; retain PID and process start identity;
* enumerate/bind visible windows using `CGWindowListCopyWindowInfo` and the owner PID/window number, then cross-check application/window state;
* activate only the owned application with `NSRunningApplication.activate` and verify focus;
* create keyboard events with `CGEventCreateKeyboardEvent` and post with `CGEventPost(kCGHIDEventTap)`; text/IME needs a Cocoa `NSEvent`/`NSTextInputClient` path in the in-process overlay rather than assuming US-keyboard scan codes.

Accessibility TCC authorization is required for global event injection on current macOS. Input Monitoring is a separate permission needed only if the controller also installs a global event tap or observes hardware input. Authorization belongs to the exact signed controller binary and user. It is not silently transferable across rebuilds, paths, or CI users. Refuse with a preflight result if the permission required by the selected operations is absent; never treat a synthesized Cocoa message as proof that the game consumed physical input.

Capture:

* on macOS 12.3+, use ScreenCaptureKit: `SCShareableContent`, an `SCWindow` matched to the owned PID/window, `SCContentFilter(desktopIndependentWindow:)`, `SCStreamConfiguration`, `SCStream`, and `SCStreamOutput` sample buffers;
* retain `CGWindowID`, PID, content size/scale, frame timestamps, dropped-frame metadata, and GPU/renderer identity;
* require Screen Recording TCC authorization and handle user denial, window loss, resize, display migration, sleep, and stream error.

For the KOTOR OpenGL renderer, record `glGetString` from the active game context and hook the exact binary's present boundary (`CGLFlushDrawable`, `aglSwapBuffers`, or another verified call site). Do not assume a Metal renderer merely because ScreenCaptureKit uses GPU surfaces. Older macOS needed for i386 requires a separately maintained legacy capture/input stack; it cannot inherit the ScreenCaptureKit support claim.

### ChromeOS variants

ChromeOS is not one Linux host target.

**Crostini:** detect `/dev/.cros_milestone` plus container/host markers and record the VM/container identity. Sommelier forwards Wayland/X11 applications, but a container client has no authority over arbitrary Ash/ChromeOS windows. A Crostini backend may be admitted only if it creates and owns the game, Wine/Proton, nested compositor, GPU render nodes, input path, and capture entirely inside the container. `/dev/dri`, Vulkan/OpenGL, nested Gamescope, audio, and pointer-lock availability must be probed. Package it as a Crostini Linux-container build, not ChromeOS host support.

**Borealis/Steam:** treat the managed gaming VM as a distinct host. Access to the game directory, proxy DLL loading, process/job control, compositor surface identity, and recording APIs is not established. Refuse unless an allowed deployment path exists and the same ownership/acceptance contract can run inside that environment.

**ChromeOS host/browser:** browser `getDisplayMedia()` and extension `chrome.desktopCapture` are consented browser capture APIs. They cannot inject trusted physical input into a native game; synthetic DOM events are untrusted browser events. Supporting a browser companion would be a separate product and protocol client, not a native KotorPhasor runtime target.

Developer Mode, disabling verification, privileged containers, or host-wide input devices must not be prerequisites for a normal support claim. If a research-only mode uses them, label it separately and record the security change and restoration.

## Feasibility blockers

### Cross-cutting blockers

1. The session object, ownership, locks, and cleanup are Linux/Xvfb/Wine-specific.
2. Recording takes a display number and screen size instead of an immutable capture source.
3. Backend admission is a string switch with one accepted creative backend rather than capability negotiation.
4. Proof receipts do not yet bind host/desktop/protocol/GPU/window/input/capture/semantic/cleanup identities atomically.
5. CI executes no Windows, macOS, Wayland compositor, Gamescope, ChromeOS, game, or recorder acceptance.
6. Product targets and support claims are not versioned by host backend and exact game build.

### Linux blockers

* The proven Gamescope setup is private; no `gamescope_xwayland.py` or generic display backend exists in the inspected worktree.
* The checked-in recorder is X11-root capture and the normal environment explicitly forces software rendering.
* GNOME and KDE portal behavior is untested. No portal, PipeWire, or EIS integration exists.
* Native Linux K2 has no working non-Windows overlay/physical console path.

### Windows blockers

* Builds are Linux cross-builds; there is no native runner, installer/rollback, Windows CI, Job ownership, HWND discovery, SendInput, or WGC implementation.
* Native DPI, focus policy, UIPI, multi-monitor, device loss, and capture policy have no tests.
* Wine evidence cannot close any of these gates.

### macOS blockers

* Current private images are legacy i386, while the current Steam candidates are different 64-bit images.
* Thin static metadata parsing is not connected to live mapped-image loading.
* No Darwin `kp::platform`, runtime entry, hook ABI, overlay/present backend, controller, installer, signing model, or TCC flow exists.
* Modern macOS cannot execute the legacy i386 images; old Intel and current Intel/Apple-Silicon acceptance are separate maintenance commitments.

### ChromeOS blockers

* No product target or admissible injection/loader path exists for host, Crostini, or Borealis.
* Container display forwarding does not grant host window/input ownership.
* Hardware/GPU and Steam availability vary by device/channel/policy, so generic Linux detection is insufficient.

## Packaging and dependency model

Keep retail executables, assets, saves, and private receipts outside every package. Package capabilities in layers so a runtime release does not acquire desktop-control dependencies.

| Package/component | Contents | External dependencies | Claim boundary |
| --- | --- | --- | --- |
| `kotorphasor-runtime-win32` | `kphasor.dll`, validated proxy, exact profiles/manifest | Windows/Wine system DLLs; game-owned OpenGL/DirectInput | Runtime only; host support requires separate acceptance |
| `kotorphasor-runtime-linux32` | `libkphasor.so`, exact K2 ELF profiles/manifest | 32-bit libc/OpenGL/X11/game dependencies | Native Linux runtime only; current overlay remains absent |
| `kpharness-core` | protocol client, scenario runner, oracle, receipts, `PhysicalConsoleDriver` | Python stdlib/current declared Python baseline | No display/input support by itself |
| `kpharness-linux-x11` | Xvfb and Gamescope leases, X11 owned-window/input/recording adapters | Xvfb, Gamescope, Xwayland, Xlib/XTest or `xdotool`, FFmpeg/ffprobe, `glxinfo`, Wine, bubblewrap where isolation is selected, Mesa/Vulkan and `/dev/dri` | Exact backend IDs only |
| `kpharness-linux-portal` | portal session/input/capture adapters | session D-Bus, xdg-desktop-portal, GNOME/KDE portal, PipeWire/SPA, libei/EIS | Shared Wayland mode; interactive consent |
| `kpharness-windows` | native launcher/Job/window/input/WGC recorder | Windows 10 1903+ for the selected WGC path; D3D11/WinRT | Native Windows controller, independent of Wine |
| `kotorphasor-runtime-darwin-*` | architecture-specific dylib/runtime/overlay and exact profiles | Explicit macOS/architecture floor, signing and loader model | One exact architecture/game build at a time |
| `kpharness-macos` | app/window/input/ScreenCaptureKit controller | macOS 12.3+ for modern capture, TCC grants, signed stable controller identity | Modern macOS controller; legacy i386 is separate |
| ChromeOS variant package | None until a variant passes feasibility and live gates | Device/variant-specific | Do not ship a generic ChromeOS label |

Every backend must have `preflight --json` that reports exact missing commands/libraries/APIs, OS and desktop facts, permissions, GPU identity, and refusal reasons without starting or modifying the game. Dependencies should be detected, not copied opportunistically from the workstation. Credentials, Xauthority cookies, portal tokens, signing keys, and user paths beyond selected artifacts must not enter manifests.

## Host and synthetic test plan

### Common conformance suite

Run the current physical-console cases unchanged against fake implementations of every `OwnedInputPort`. Add:

* admission/refusal before mutation;
* stable process identity and PID-reuse rejection;
* zero/one/multiple/foreign/lost/replaced/resized window behavior;
* permission denied/revoked/expired and focus refusal;
* exactly one submit despite retries/timeouts;
* modifier release and game-input restoration on every exception;
* recorder early exit, graceful finalization, idempotent stop, partial-media retention;
* capture-source and lease mismatch refusal;
* distinct fields for requested sampling, encoded FPS, drops/duplicates, distinct frames, and visual review;
* teardown order and proof that no foreign PID/window/session was touched.

### Linux host tests

* Xvfb fixture with two fake X11 windows and PIDs; prove exact selection, XTEST delivery, root-vs-window command construction, replacement/resize failure, and cleanup.
* Fake Gamescope/readiness child, fake renderer output, environment allowlist, missing dependency, lease death, and software-renderer refusal.
* Optional real host integration using a tiny OpenGL X11 fixture under nested Gamescope, never the retail game. Check renderer, `-window_id` capture, distinct changing frames, and process-group cleanup.
* Mock portal D-Bus responses, PipeWire node/sample delivery, EIS events, denial, cancellation, portal restart, and token expiry.
* Real compositor integration on both GNOME/Mutter and KDE/KWin because mocks cannot prove chooser, focus, scaling, or portal behavior.

### Windows host tests

Use a signed or stable-path 32-bit fixture that opens an OpenGL window and records DirectInput/Raw Input plus a semantic counter. Test Job containment, suspended launch, HWND/PID/creation-time binding, SendInput, focus refusal, DPI/resize/minimize, WGC frames, device loss, recorder failure, and Job cleanup. Execute on a real Windows runner; Wine is a separate compatibility test.

### macOS host tests

Use architecture-specific test apps with an OpenGL window, event counter, text input, and changing GPU frames. Test dyld image/slide mapping, memory protection/W^X, present hook, CGEvent delivery, Accessibility denial/revocation, Screen Recording denial/revocation, ScreenCaptureKit resize/loss, Retina scaling, sleep/display change, and process cleanup. Run modern x86_64 and Apple Silicon/Rosetta cells only if each is a named supported target; keep legacy i386 on an actual compatible Intel/macOS host.

### ChromeOS tests

Begin with detection/refusal tests for ordinary Linux, Crostini, Borealis, and host/browser. A real-device feasibility probe must establish filesystem deployment, executable architecture, game/runtime loading, GPU render node, nested display ownership, exact capture, physical input, and teardown before adding a support backend. Emulator/container-only results do not replace the Chromebook gate.

Host/synthetic tests prove contracts and failure handling. They never prove retail game compatibility, GPU behavior, security prompts, visual correctness, or a support claim.

## Required real-machine/live acceptance

Each support matrix cell needs its own immutable receipt. The minimum acceptance is:

1. **Identity:** OS/build, architecture, desktop/compositor/version, session protocol, container/VM status, GPU/driver, exact game executable hash/format/architecture, runtime/proxy/profile hashes, controller source/package hash.
2. **Clean install:** start from an intact supported game install or a receipt-bound copy; install through the platform package; verify deployed hashes; retain original/save hashes.
3. **Ownership:** one controller-owned process/session/display and one verified visible game window/surface; stable process start identity; no borrowed desktop/window.
4. **Acceleration:** game-bound renderer/vendor/version and capture-adapter identity. A compositor probe alone is insufficient.
5. **Physical console:** use the platform OS input API to send F12, type a boundary expression, and press Enter. The channel has no submit operation. Prove exact runtime/session, one `submitted` increment, the exact successful request, typed outputs, no drops, and an input-call/event counter showing the game's real input path.
6. **Input behavior:** while the console owns input, gameplay does not receive it; after close, gameplay input resumes. Exercise focus loss/reacquisition and release all modifiers on failure.
7. **Capture:** start after the exact window/surface is bound; record at least two minutes spanning menu-to-world or world gameplay, console open/close, movement, and a changing scene. Retain the continuous master, API command/config, timestamps, geometry, frame/drop data, distinct-frame analysis, audio scope, and media hash. No black/protected/stale frames, silent source switches, or unreported resize.
8. **Semantic oracle:** synchronize video/input events with in-process world/menu/module/console state. A screenshot or visual clip does not prove semantic predicates.
9. **Visual review:** a reviewer inspects the continuous master for correct world, console, focus, scaling, clipping, color, cadence, and transitions. Record the decision separately from encoder/route success.
10. **Failure exercises:** deny permission, close/replace/resize the window, stop the recorder, and interrupt the game. Each must fail closed, retain evidence, and touch no foreign process/session.
11. **Cleanup/removal:** recorder stops and finalizes first, then game/runtime namespace, then display/capture session. Zero owned processes and sessions remain; source/save receipts match; uninstall restores only files owned by the package.

Coverage must be explicit:

* GNOME X11, KDE X11, GNOME Wayland-hosted nested Xwayland, KDE Wayland-hosted nested Xwayland, and any portal modes are separate cells.
* K1 and K2, Wine and native host, and every executable hash are separate cells.
* Native Windows means a real Windows machine and installed artifact.
* macOS cells name CPU architecture, OS range, exact game image, and native versus Rosetta execution.
* ChromeOS cells name device model, ChromeOS channel/version, Crostini/Borealis/host variant, and policy/developer-mode state.

## Prioritized implementation slices

### P0: freeze the current truth

Add a machine-readable support matrix and make every unimplemented backend refuse before mutation. Preserve these statements in release output:

* K1/K2 current live proof is Wine-based.
* K1 physical console on the private owned Gamescope/Xwayland path is narrowly proven.
* checked-in GPU exact-window recording is absent;
* native Windows, macOS, ChromeOS, and native Wayland are unsupported.

This is documentation/admission work and must not be presented as new platform support.

### P1: productize Linux Gamescope/Xwayland for K1

Extract immutable `HostFacts`, `BackendCapabilities`, `DisplayLease`, `OwnedWindow`, and `WindowRecorder` records. Keep the existing Xvfb backend unchanged. Check in the Gamescope lease and exact-window `x11grab -window_id` recorder, strip host authority, prove an accelerated renderer, and make recorder failure route-fatal. Run the common host suite, then one atomic K1 installed-game acceptance.

This gives the fastest real coverage because the physical-console driver and private GPU environment already worked. It closes the largest proof gap without inventing a second input protocol.

### P2: accept Linux host variants and K2 Wine

Run the same nested Gamescope/Xwayland backend on real GNOME Wayland, KDE Wayland, GNOME Xorg, and KDE Xorg hosts. These are host-compatibility cells; keep the game-facing protocol labeled Xwayland. Then accept K2 GOG under Wine with the exact final profile, movement/input restoration, and GPU capture. Do not generalize from the existing one-save read-only K2 console bridge.

### P3: native Windows controller and capture

Implement `ProcessLease` with Job Objects, owned `HWND` discovery, `SendInput`, WGC exact-window recording, and a native installer/rollback path. Reuse the Win32 overlay and common physical-console driver. Add Windows-host tests and accept K1 first, then K2. This is likely the next fastest native host because the runtime artifact, proxy path, WGL overlay, and DirectInput suppression already exist.

### P4: optional Wayland portal backend and native Linux overlay

Implement portal ScreenCast/RemoteDesktop/PipeWire/EIS only if shared-desktop native Wayland control is a product requirement. Test GNOME and KDE separately. In parallel or afterward, port the in-process overlay to the native Linux K2 X11/OpenGL target; Wayland-host execution for that old X11 game remains Xwayland unless the game itself changes.

### P5: Darwin foundation, then one modern Mac target

Acquire and hash the current Steam Mac images before coding profiles. Implement fat-slice selection, live dyld mapped-image support, Darwin memory/module primitives, architecture-specific hook entry/detours, Cocoa/OpenGL overlay/input, process/window ownership, ScreenCaptureKit, signing/loader model, and TCC preflight. Choose one realistic x86_64 target for first acceptance. Treat legacy i386 as a separate old-Mac preservation target, not a shortcut to modern support.

### P6: ChromeOS feasibility before implementation

Run read-only/contained feasibility probes on one Crostini-capable Chromebook and one actual Steam/Borealis environment if available. Stop if an allowed owned loader/process/window/capture boundary does not exist. Only then decide whether a Crostini-specific nested Gamescope backend is maintainable. A browser companion, if desired, should be planned as a separate product.

## Terse release decision

* **Ship/claim today:** the exact combined K1/K2 Wine preview claims in `docs/release-platform-status.md`; K1 physical-console support only within the reviewed Linux/Wine receipt scope.
* **Do not claim today:** checked-in GPU exact-window capture, native Windows, native macOS, ChromeOS, native Wayland, or generic GNOME/KDE support.
* **First executable slice:** checked-in Linux K1 Gamescope/Xwayland lease plus exact-window recorder and one atomic live acceptance.
* **First native-host slice:** Windows Job/HWND/SendInput/WGC backend.
* **Highest-risk slice:** macOS loader/ABI/signing/TCC/overlay integration.
* **Research-only until proven feasible:** ChromeOS Borealis and host-level integration.

## Local evidence consulted

Repository:

* `docs/release-platform-status.md`
* `docs/devtools-design.md`
* `docs/creative-runner.md`
* `docs/harness-driver.md`
* `docs/harness-workflow-status.md`
* `docs/model-memory-api.md`
* `docs/native-animation-api.md`
* `scripts/harness/kpharness/session.py`
* `scripts/harness/kpharness/creative.py`
* `scripts/harness/kpharness/creative_wine.py`
* `scripts/harness/kpharness/recording.py`
* `scripts/harness/kpharness/owned_x11.py`
* `scripts/harness/kpharness/physical_console.py`
* `scripts/harness/kpharness/targets.py`
* `tools/kpharness_physical_console_test.py`
* `tools/kpharness_creative_test.py`
* `tools/kpharness_offline_test.py`
* `src/platform/platform.hpp`, `platform_linux.cpp`, `platform_win32.cpp`
* `src/devtools/overlay.cpp`
* `src/hooks/hooks.cmake`, `src/runtime/runtime.cmake`, `src/harness/harness.cmake`
* `src/image/macho.hpp`, `macho.cpp`, `parse.cpp`, `load.cpp`
* `tools/kp_machotest.cpp`, `tools/kp_imagetool_macho_test.py`
* `.github/workflows/cmake-multi-platform.yml`

Private evidence and prior audits:

* `/home/brunner56/kp-live-20260922/task7-supported-console-live-review.md`
* `/home/brunner56/kp-live-20260922/task7-supported-live-driver-report.md`
* `/home/brunner56/kp-live-20260922/task7-package-proof-audit.md`
* `/home/brunner56/kp-live-20260922/task7-gpu-window-implementation-brief.md`
* `/home/brunner56/kp-live-20260922/private-gpu-controller-report.md`
* `/home/brunner56/kp-live-20260922/macho-parser-report.md`
* `/home/brunner56/kp-live-20260922/macho-cli-report.md`
* `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-014019/`
* `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-001824/`

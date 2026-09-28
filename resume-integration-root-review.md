# Resume integration root review — in progress

The sole integration writer owns production edits. This review compares new source against required lifecycle and thread ownership semantics. Acceptance remains open until frozen current-source builds and focused tests finish.

Findings sent to writer:

1. New VM layout diagnostic passed a string to %d and a count to %s. Corrected source now places the count first, layout string second.
2. Initial scripts Host binding was after load_all; top-level kp.scripts calls would see a null binding. Corrected source binds the owned host before load_all.
3. Unbinding scripts before Host destruction would deny kp.scripts to OnScriptUnload callbacks. Required ordering is explicit unload_all while bound, then unbind, then destroy the empty Host under the existing quiescent stop contract. Current source contains that order; focused lifecycle proof pending.
4. Client mismatch diagnostic originally treated an unlatched owner as mismatch. Current source checks engine_thread_latched first and resets the diagnostic on lifecycle reset; direct latch tests pending.
5. The reset-client-log helper was defined in an anonymous namespace but declared/called externally. The shared library linked with that unresolved symbol; the namespace executable link then failed with undefined reference. Writer notified; final fixed build required.

The /tmp/lifecycle-cfg cache points to the authorized validation worktree. Earlier target runs precede the latest source edits and are not final integrated receipts. No clean-first is permitted. Manual namespace registrations prove the host API surface, not execution of Runtime::boot_scripts; preserve this distinction unless the actual boot seam is exercised.

No live game, Wine, Gamescope, display capture, process signaling, commit, or publication was performed by this review.

## Root corrective verification

The intermittent owner failures were traced to the runtime ELF constructor, not a demonstrated CAS/identity defect. `latch-reset-debug.log` records hidden thread2 calling reset_engine_thread through Runtime::start/run_startup/worker while the host probe's contenders run. It resets both at start and failed-start cleanup. The intermediate hash and monotonic-token replacements were withdrawn; exact atomic<std::thread::id> is restored.

Root added exact Linux constructor opt-out KOTORPHASOR_NO_AUTOSTART=1; absent/other values retain production autostart and Windows DllMain is unchanged. All four CTest cases directly linking kphasor now set that environment variable (routine, vector, namespace K1/K2). Namespace also exercises eight simultaneous two-thread owner races. Root private linked probe passes100 races; isolated GDB trace contains300 resets, all from test thread1, and exits normally. Source, ELF binaries, probes and receipts are bound in resume-runtime-root-manifest.json.

Root rebuilt current library/test targets without cleaning. Ten selected CTest entries pass (integration-root-ctest.log). The actual private Runtime::boot_scripts probe executes the real initializer, initial kp.scripts.list, vector construction, motion capabilities, and OnScriptUnload scripts access. Runtime::stop invokes one unload callback and clears Host/binding/live state. A second mode seeds a partial Host using that same seam, then invokes Runtime::start on the unsupported native test ELF: PhaseFailed, one unload callback, null binding/Host. This is actual failed-start cleanup of synthetic partial state; it does not prove target-image resolution or successful hooks/native motion.

The autostart opt-out is mandatory when directly invoking these linked native host probes; setting it inside main is too late. The earlier direct probe receipts without isolation are superseded.

Remaining authorized integration work: K1 GOG-only regeneration of seven accepted motion rows (two proposed rows remain excluded), and durable H0 regression target linking actual commands.cpp. These are separately owned and do not reopen the accepted lifecycle/owner seam.

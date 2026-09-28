# K2-native loop probe (2026-09-09)

The corrected K2 client-loop hook now uses the measured cdecl ABI (`int
(*)(void*)`) and calls the original loop before draining the harness. The
build and all offline tests pass.

A bounded `k2_smoke` run installed 15 hooks and opened the listener. The
listener accepted repeated client connections, but no `client loop cave: 100
frames` heartbeat was emitted and every connection closed without a reply.
The process remained alive but sleeping until the 150-second bound was
stopped. No gameplay phase, save load, screenshot, report, or proof video was
produced. This is diagnostic evidence only.

The next live investigation should verify the native launch/display path and
identify the actual per-frame entry reached by this binary before adding more
engine calls. Do not claim K2 gameplay proof until a report records gameplay
state and the paired video shows the corresponding rendered frame.

Follow-up: the harness target root is `tmp/k2-native_harness` (the earlier
`tmp/k2_harness` tree was a stale manual staging tree). After synchronizing
the corrected table and runtime into the real target root, the bounded probe
installed **16 hooks**, confirming that the alternate frame-wrapper binding
resolves. It still produced no frame heartbeat before the bound expired, so
the binary has not yet yielded a gameplay proof.

The real Steam client can be launched from `~/.local/share/Steam/steam.sh`,
but in this headless account it remains unauthenticated (`steamid=0`) and
does not provide a usable Steam API endpoint. K2 consequently shows its
Steam-required modal and exits/blocks before the frame loop. The harness now
starts this client automatically when available; it must not treat the
presence of the process as Steam API readiness.

An attached GDB snapshot of the live process shows the main thread blocked in
`XWindowEvent`/`XReadEvents` inside the native executable, while the harness
worker is idle in `Channel::run_loop`. This places the stall before the game
frame loop and points to window-manager/X11 initialization, not command
dispatch or hook resolution.

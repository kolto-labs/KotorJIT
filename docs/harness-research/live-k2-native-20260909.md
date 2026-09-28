# K2-native bring-up, 2026-09-09

Command: `./scripts/harness/kpharness.sh boot --target k2-native --boot-timeout 120`.

The native ELF launched and loaded `libkphasor.so`. The runtime installed
14 hooks and opened the harness listener on `127.0.0.1:56055`, proving the
ELF dependency staging and preload path work.

The adapter reported `99 site(s) missing of 99`: the regenerated
`k2_steam_linux.json` now inventories all 173 manifest sites and carries
30 verified VM/loop adjudications, but none of the engine app/client/server
fields and load-side calls required by the adapter. Requests connected and
were then closed without replies because the client-loop drain has no
resolved adapter host on this build. The process was terminated after the
bounded attempt; no gameplay claim is made.

The table was regenerated for this build alone, then reviewed against the
live result. The client loop remains `reference` in the checked-in table:
temporarily marking it `detour` installed a fifteenth hook but caused status
timeouts on two launches, so that hypothesis was reverted.

This is a corpus-binding gap, not a K2 engine crash. The next K2 task is to
produce a separate adjudicated harness-binding file for the Linux ELF from
the readable Mac/Android donors and verified ELF consumers, then regenerate
the address table with expected-byte signatures. Copying K1 or K2 PE offsets
would violate the fail-closed design.

The runtime now also selects the native cdecl shape for the server-loop hook
and has a fallback drain when no client-loop detour is available. The bounded
retry still receives no status reply, so those changes are compile-verified but
not live-validated as a working K2 control path.

# Native routine routing boundary

The bridge has 769 K1 and 803 K2 callable signature initializers, covering 806 distinct names. [Every name, per-game ID, and source line](/home/brunner56/kp-live-20260922/side-audit/native-routines.json) is recorded. Every exact native-handler side is conservatively unresolved here: the generated signature is not its engine implementation. Public wrappers and scripts can still have a clear semantic world/presentation purpose; direct pointer-based APIs are traced separately.

AssignCommand, DelayCommand, and ActionDoCommand are explicitly refused because their NWScript action closures cannot be represented by the bridge. Unsupported catalog rows are not callable functions. No arbitrary server-call forwarding or client/server replication guarantee follows from nwscript.call.

# Live softlock recovery crash — 2026-09-09

The corrected `k1_softlock_detect` scenario was run after a successful K1
smoke boot. The detector behaved correctly: the locked-door wait produced the
expected `softlock` verdict after 60 seconds with the gameplay fingerprint
unchanged. The following explicit harness warp to `end_m01ab` returned an
acknowledgement, then the game crashed while processing the transition.

Evidence is in `tmp/k1_harness/runs/20260909-202100`:

- `report.json` records 5 successful steps, 1 expected softlock, and 1 crash.
- `kotorphasor.log` records `warp: move to 'end_m01ab' pending`.
- Wine reports an unhandled read at `0x004127C5` (`0x000000A4`), immediately
  after an `OnSave` event.

This means the detector is live-proven, while warp recovery is not. The
failure is distinct from the earlier invalid door-click recovery: the current
warp setters reach the engine, but the transition overlaps a save callback or
otherwise supplies an invalid transition state. Do not claim full recovery
until this is reproduced with a debugger or corrected through an engine path
that survives the save boundary.

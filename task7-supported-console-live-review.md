# Task 7 supported physical-console live acceptance

Verdict: PASS for the checked-in Linux K1/Wine physical-console boundary.

Run: `/home/brunner56/kp-live-20260922/private-gpu-runs/20260927-014019`

The run used the read-only 95-file snapshot at
`/home/brunner56/kp-live-20260922/harness-snapshots/task7-supported-console-20260927`.
The wrapper recorded the snapshot before and after the run and reported it
unchanged. The candidate DLL/proxy hashes were checked against
`/home/brunner56/kp-console-protocol-20260927/build-artifacts.json` before
staging and after deployment.

Production `GameSession.capture_owned_game_window()` selected exactly one
visible 1024x768 window (`0xc00004`) owned by game PID 236 on the owned `:0`
display. Production `OwnedX11Input` and `PhysicalConsoleDriver` opened F12 and
typed `return "supported-physical",nil,false,42`; no wire submit operation was
available to the physical path.

The console identity remained runtime
`52e2bc543d223ea7db3f7e5833a5b5983a46da9d699d3f8de4a0eb2b09b1c6d4`,
session `1`. Submitted advanced exactly `0 -> 1`; request `1` completed
`Succeeded` with four exact typed values: the byte string
`supported-physical`, nil, false and finite number 42. DirectInput calls
advanced by 30. Output was undropped and retained distinct exact-request
`input` and `result` rows.

Root visually inspected `supported-console.png`: the F12 overlay and all four
results are legible over the actual Upper City South gameplay world. This is
console integration evidence, not an advertisement-quality creative clip.

Original source receipts matched, the frozen snapshot matched, the display
parent was reaped, and both inner and outer teardown receipts recorded zero
remaining owned processes.

Scope limit: this does not prove K2, native Windows, native macOS, the GPU
window recorder, smooth representative example media, or the full creative
package. Those remain open.

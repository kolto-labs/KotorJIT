# Task 7 supported physical-console private live driver

Prepared only; syntax checks passed. No product changes, build, staging, snapshot update, or game launch.

Files:
- task7_supported_console_gpu.py SHA256 9eb29387f5b64f4f4318d725db1c700c41a10ab499ed0eb261aace45cf077663
- private_task7_supported_controller.py SHA256 028bac4df5f3fbb21193abb2925abbb0593dda57381a75e8f24e02ea92b17cdd

Root invocation after reviewed exact-path harness snapshot freeze:

    KP_PRIVATE_HARNESS_SNAPSHOT=<reviewed snapshot> /usr/bin/python3 /home/brunner56/kp-live-20260922/private_task7_supported_controller.py run

Candidate is fixed to /home/brunner56/kp-console-protocol-20260927/build with both files checked against that release root's build-artifacts.json before boot and after deployment. Address data comes from that candidate's clean source. Existing Session staging is reused from the private k1_protocol_gpu.py; its capture method is asserted identical to production GameSession.capture_owned_game_window. No capture_window assignment, custom discovery, input timing workaround, or monkeypatch is used. Production OwnedX11Input.from_session and PhysicalConsoleDriver execute the physical route.

Driver readiness requires gameplay, main_menu zero and bound VM. The exact production window capture is independently recorded with X11 PID and geometry; PID must match session-owned game PIDs and capture's stored owner. Production module hashes are recorded for console_protocol, physical_console, owned_x11, console_steps and session. The namespace wrapper hashes the entire required frozen harness snapshot before and after and backs up/hashes all private driver dependencies.

One physical source is typed: return "supported-physical",nil,false,42. A read-only channel wrapper permits only v1 status/outcome/output and fails if any wire submit or mutation is attempted. The immutable production receipt is checked for the same baseline runtime/session, exactly submitted+1, terminal Succeeded, all four typed returns, open=true, positive DirectInput input_calls delta, undropped cursor output, distinct input/result sequences, and every line matching the same session/request. Wire requests/responses, receipt and final owned-window PNG are retained.

Teardown verifies source receipt equality, no remaining owned game PIDs, and reaped display parent. The outer PID/network/mount namespace wrapper additionally writes teardown.json with remaining_owned_pids; successful acceptance requires it empty and controller exit zero. The inner supported-result.json alone does not establish outer namespace teardown.

Integration concerns to resolve honestly in live acceptance:
- Production discovery demands exactly one visible game window owned by the session PID and exact DISPLAY equality. Wine/gamescope may expose multiple windows or a different PID convention. Such a refusal must remain a failed gate; do not manually assign capture_window.
- Required snapshot must include the reviewed production capture and adapter modules; root alone prepares it. Recorded hashes establish which files ran.
- This is happy-path integration only. Reset/duplicate/stale/dropped-output/timeout refusal remains covered by deterministic production host tests, not inferred from this run.
- Existing task7-supported-console-proof-gate.md describes the pre-extraction state; this driver exercises the now-present production implementation but does not independently revalidate all host fixtures.

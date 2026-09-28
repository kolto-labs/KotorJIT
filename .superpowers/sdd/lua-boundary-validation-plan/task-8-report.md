# Task8 implementation report

Base requested7ec5bef; controller research-only commit987ea2c arrived during work and was preserved. Scoped implementation, no games, live processes, stages, subagents, pushes or PRs used.

## Delivered

- Native animation core/profile/OS adapters/Lua boundary in src/api/animation*; registered and bound beside native model API.
- Exact existing model SHA/image binding;32byte animation code guards for all4profiles, including exact rebased MacK2i386 canary operand atbyte19. Explicit Win32thiscall, Darwin32cdecl and Darwin64SysV adapters. Darwin loader still absent.
- Model internal refresh/checked-capture facade reused existing protected userdata, identity and epoch checks. No duplicate model offsets or NW aliases.
- Inspect distinguishes available/inactive/absent and seconds; initializes float outputbuffers and immediately consumes returned runpointer asBoolean without retaining/dereferencing.
- Fixed flags2, rates0..2, bounded ASCII identifiers, finite start below duration, no seek/restart/negative reverse/current/NULL/arbitrary flags. Pause/resume preserves existing clock; immediate readback failure propagated.
- Actual finite2actor Lua scene, known pause1baseline, dance halfspeed, one actor held at33%, comparison actor continues to80%, resumed actor advances12%clip, reset knownbaseline then destroy ownedactors. Initial ownership before modelready, per-tick context/identity/peace/death guards; cleanup refuses replacements/contextchange. No VFX/camera assumption.
-17step independent route with both native clocks sampled over12clientticks, resume/reset/removal checks. Bounded optional advance_ticks clock client/server helper and regression; defaultserver unchanged.
- Native controlled tests4layouts plus actualLua boundary; extracted existing modelFake fixture to reuse without altering modeltest assertions.15actualscene executions cover successful clock trajectory, warmup, late replacement, modelreplacement, context, combat, partialsetup, noidentity, absentclip, cuefailure, pauseignored, override, stalledclock, deletionfailure, unload.
- API/demo docs and narrow creativehelper documentation.

## Commands and results

1. cmake -S . -B /home/brunner56/kp-validation-20260922-build -DPython3_EXECUTABLE=/usr/bin/python3
2. cmake --build /home/brunner56/kp-validation-20260922-build --target kp_animationtest kp_modeltest kphasor_dll -j2
   Native32 sharedruntime/coretests and MinGW DLL built. Initial misleading-indentation warnings split into separate statements, subsequent build warning-free.
3. kp_animationtest and kp_modeltest executables: PASS. Animation tests rejectwrongSHA/ABI/width/codeguard/relocatedoperand, malformednames, rates,start,duration, absentclip, stale/forgedcapture, controlleroverride/readbackreset; clockadvanced independently betweenqueries and pause/resume3calls preservedclock.
4. luajit tools/animation_scene_test.lua scripts/demos/animation-memory/two_actor_freeze.lua:15cases PASS.
5. /usr/bin/python3 tools/kpharness_creative_test.py:25tests PASS (expected cleanupfailure diagnostic appears for regression).
6. Production Scenario.load parses newroute17steps. Initial bookkeeping assertion incorrectly expected18; correctedcount to17, no routeparsererror.
7. ctest --test-dir /home/brunner56/kp-validation-20260922-build --output-on-failure:23/23PASS,75.47sec. Includes original41example validation.
8. git diff --check:PASS.

## Frozen minimal API handoff

DLL /home/brunner56/kp-validation-20260922-build/kphasor.dll
SHA2561ba35210b9874c5f1433125e835683b7edd1da300898cf53b8397549fbf2a0b6
Scene f146855a7411f157014d0b3354807fdb955fef1694bd075160879b04ab911a30
Route9847e347d90e4cafdc72c81b827c7b164aeed8cd60cdf7e814340ec0952bfa37

Parent owns live probe and recording; no live result is inferred in this report. Source model demos and original41examples unchanged.

## Self-review / limits

- Nativequery/output ABI and guardbytes grounded in supplied byteaudit; fixtures exercise contracts, not real Darwin execution. No Mac loader claimed.
- Immediate query verifies clock/duration only, not actual pose/blendweight. Live controller can override nextframe; scene detects loss/restart/ignoredpause and fails, never retriescue to mask it.
- Pointer/context identity is bounded; no engine generation guarantee invented. Missing ownership or changedidentity forbids deletion, so cleanup may intentionally leave actors rather than delete replacements.
- Prior arbitrary animationstack not restored; ownedactors reset to knownpause1 and removed. Clip availability queried permodel, no silentfallback.
- Short livephase windows may produce route timingfailure; independent diagnosis required before attributing scriptdefect. Baseline/reset hold90ticks for observation; dance windows driven by clipclock, not walltime.
- Raw60fps recording, clientclock progression, and clipclock progression do not independently prove visiblepose or usefulpresentation. Controller must review continuousfootage and attach runtime/source/route hashes.

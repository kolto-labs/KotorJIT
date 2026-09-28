# Task 7 resumed provenance review

## Final narrow rereview — supersedes the changes-required verdict below

**Spec verdict: PASS for the bounded provenance/import/early-evidence repair. Quality verdict: PASS; no remaining load-bearing finding in the two requested rereview items.** This does not promote Task 7 to live acceptance.

- **P1 ADDRESSED.** `readiness_child_command()` in `gamescope_xwayland.py:67-72` now uses the resolved absolute Python executable with `-I -S -B` and explicitly prepends the resolved snapshot runtime. `start()` uses that helper for its actual Gamescope child command. The fresh child therefore suppresses bytecode independently of its parent, ignores caller Python environment/CWD injection, and avoids site initialization. The new test executes that production bootstrap against a real snapshot from a shadow-package CWD/PYTHONPATH, omitting only the final readiness arguments so it exits without waiting. It checks the expected exit code, unchanged snapshot verification, and absence of `.pyc` files. That covers the reported import/bytecode defect without a game/display launch.
- **Pre-authority observed-child evidence ADDRESSED.** Positive integer PID/string-start validation and observed start/relationship capture now occur before authority validation, followed by an evidence publication. The DISPLAY-only rejection fixture asserts observed start and parent PID survive while `owner.ready_child` remains null. The repair gathers forensic facts without promoting the rejected candidate into cleanup authority.

This rereview inspected source and the two focused tests only. The writer reports 35/35 Gamescope cases passing; the suite was not rerun. No source edits, process launches, or signals were performed by this review. Previously documented broader provenance/scrub limitations and separate live authority/zombie-cleanup issues remain as stated below.

Date: 2026-09-27. Checkout: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.

Scope: previous provenance findings and new breakage in the resumed fix. Read the prior review, original provenance report, appended host-only repair section of `task-7-gamescope-live-attempt-report.md`, current implementation, focused tests, and the separately tracked actual-boot diagnosis. No source edits, test reruns, game/display launches, or signals. Reported 33/33 Gamescope and 28/28 creative results were not independently rerun.

## Verdict

**Changes required.** The bounded run provenance contract is substantially implemented, and the real driver/helper/curation tests address the former snapshot-layout/import blocker. However, the production readiness child writes bytecode into the supposedly closed snapshot, making the new full-file verification fail after a real boot attempt. This is a concrete runtime interaction missed by the passing driver-only tests.

This verdict does not require a complete build-input/retail/toolchain closure or broad new infrastructure. Those limitations are explicitly documented and are outside the narrowed selected-input/source-preservation contract.

## Load-bearing finding

### P1 — Readiness child invalidates its own snapshot with bytecode files

`gamescope_snapshot.py:300` sets `sys.dont_write_bytecode=True` only in the driver interpreter. `GamescopeXwaylandLease.start()` at `gamescope_xwayland.py:168-174` starts a new interpreter as `sys.executable -m kpharness.gamescope_xwayland --ready-child ...`, setting its `PYTHONPATH` to that same snapshot runtime. It supplies neither `-B` nor an isolated bootstrap. The environment allowlist excludes `PYTHONDONTWRITEBYTECODE`, and a parent's `sys.dont_write_bytecode` setting does not propagate to a new interpreter.

On the normal writable snapshot produced by `create_snapshot()`, the fresh interpreter therefore writes `runtime/kpharness/__pycache__/*.pyc` while importing the package and helper dependencies. `verify_snapshot()` at `gamescope_snapshot.py:229-239` now rejects every unlisted runtime file. `creative.py` invokes run verification after boot and again after teardown; thus the readiness helper itself causes `Gamescope snapshot runtime file list differs from manifest`, including on an otherwise successful boot. The retained snapshot also ceases to pass later verification.

The new real-subprocess tests at `tools/kpharness_gamescope_backend_test.py:266-296` exercise only the driver bootstrap, whose bytecode suppression works. They do not exercise the independently launched readiness interpreter.

Required repair: apply bytecode suppression to the actual readiness-child command and give that child the same controlled import boundary as the driver. Add a focused host-only check of the generated child command/import path which verifies the snapshot remains unchanged; no Gamescope/Wine/game launch is required. This review establishes the call chain statically and does not claim a newly executed reproduction.

## Previous-findings disposition

| Finding | Scoped disposition |
| --- | --- |
| C1 / I4 complete provenance and source lock | The narrowed contract now binds route, selected Lua, built runtime hashes, existing bounded source receipt, snapshot digest, interpreter identity and resolved harness module hashes before stage/prefix claims. It rechecks snapshot/external repository identities and selected inputs after boot/teardown, with existing deployed-runtime comparison. Acceptable for the explicitly bounded contract after the P1 repair; it is not complete build-source closure or an adversarial concurrent-mutation guarantee. |
| C2 / I6 driver import isolation and real test | Driver uses absolute interpreter, `-I -S`, explicit snapshot import root, disabled bytecode, and actual package/module shadowing tests. Repository root binding repairs discovery and curation in snapshot layout; production creative `--help` is exercised. These close the original driver blocker. Readiness-child isolation remains part of P1. |
| C3 rejected child evidence | Candidate PID/start/sanitized display plus raw size/hash are retained before authority validation. Changed-identity and later rejection paths retain observed identity/relationship. Partial remaining gap: DISPLAY-only invalid authority is rejected before `_start_reader`/relationship capture (authority check precedes lines 231-238), so the exact previously observed failure still retains only claimed child identity, not available observed relationship. This does not authorize using the rejected PID for cleanup. |
| I1 directory durability | Lease and manifest atomic writes now fsync the containing directory. Original per-receipt issue closed. |
| I2 cleanup failure terminal evidence | `close()` now catches exceptions, persists failed terminal phase, and retains the first cleanup exception. Failed repeated attempts remain failed. A later successful retry retains earlier failure in event history; that is materially better evidence. Original terminal ambiguity repaired. |
| I3 unlisted snapshot data | Complete file-list, symlink and special-file checks added. Correct direction, but interacts with readiness child as P1 describes. |
| I5 broad secret scrub | Narrow credential-shaped evidence rejection added for manifest/lease. Arbitrary external logs and final creative evidence remain outside a comprehensive scrub gate, as the report explicitly states. Do not claim this older broad finding fully closed; do not expand this scoped repair into a new log infrastructure project. |

## Remaining live boundary

The appended report correctly claims no new live proof. The separately diagnosed missing-XAUTHORITY policy and zombie-leader reaping behavior remain unresolved in the reviewed source and still block treating the old failure as a successful boot. This review neither asks to relax ownership checks nor authorizes another launch. Once P1 is repaired, the provenance slice can be assessed on its bounded host-only merits; full Task 7 live acceptance still requires its separate boot/capture/console evidence.

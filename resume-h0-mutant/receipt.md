# H0 old-admission mutant receipt

Date: 2026-09-27. This is private red-control evidence outside the worktree.
No product files, shared build files, game, Wine, or display were changed.

## Inputs

- Shared production library: `/tmp/lifecycle-cfg/libkphasor.so`
- Frozen fixture source: `/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/tools/kp_harnessdrain_test.cpp`
- Mutant source: `channel_push_reply_old.cpp`
- Build/run wrapper: `run_mutant.sh`
- Runtime environment: `KOTORPHASOR_NO_AUTOSTART=1`
- Timeout: 15 seconds

The mutant source defines exactly `kp::harness::Channel::push_reply` and restores the pre-fix admission body:
`if (client == 0 || client != current_client()) return;`.
The queue ceiling and mutex handling remain the production behavior. The fixture is linked once against the shared production library; no duplicate channel or command object is linked.

## Evidence

| claim | referent | checked | verdict | confidence |
|---|---|---|---|---|
| The old-admission mutant compiles against the current typed channel header. | `channel_push_reply_old.cpp`, `compile_mutant.stderr` | `g++ -m32 -std=c++20 -Wall -Wextra -I <worktree>/src -fsyntax-only` rc 0; wrapper object compile rc 0. | holds | high |
| The executable exports the mutant method used for interposition. | `symbols.txt` | `nm -C -D kp_harnessdrain_mutant` contains `T kp::harness::Channel::push_reply(...)`; wrapper checks this before running. | holds | high |
| The old admission behavior leaks a post-condemn event frame. | `run.stdout`, `run.rc` | Executable rc file is `1`; stdout contains `[FAIL] the error is the final line; no post-condemn event follows`; wrapper returned 0 only after both checks passed. | holds | high |
| The red failure is targeted rather than a general harness failure. | `run.stdout` | Healthy subscriber, reconnect subscriber, good-before-bad reply, post-bad refusal, and EOF checks all passed; only the condemned error-final invariant failed. | holds | high |

Exact run result: `run.rc` contains `1`; `run.stdout` ends with `1 failure(s)`; `run.stderr` contains only expected harness connection/disconnect logs. The wrapper printed `mutant invariant failure verified` and returned 0.

## Hashes

- `channel_push_reply_old.cpp`: `b79dd0690d2d1d40e0d339048ab8c3740f9800bd367fc09a10ef2c6e0d758a74`
- `run_mutant.sh`: `c5a846a3d508d8c2ae2d821536c0f18e23d994f2c896ee86d9232ee9d4d26c2f`
- `kp_harnessdrain_mutant`: recorded by the run directory; generated from the frozen fixture, the private mutant object, and `/tmp/lifecycle-cfg/libkphasor.so`.

## Grill me, weakest first

1. The red run proves interposed old admission against the shared library, but green execution of the production target remains root's gate and must be retained separately.
2. The method is interposed through `-Wl,--export-dynamic`; `symbols.txt` verifies the executable export. A platform that ignores executable interposition would invalidate this red-control route, so the symbol check is mandatory.
3. The test intentionally asserts error-final ordering rather than absence of a label anywhere in the receipt, because an event can be queued before the malformed request is processed.

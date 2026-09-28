# Task 7 Gamescope provenance and early-boot forensic report

Date: 2026-09-27

## Scope

This change addresses the two failures called out by the private Gamescope
preflight record: a dirty harness could not bind a live run to an immutable
driver, and a failure before readiness could leave no durable ownership receipt.
It does not launch a game, copy any retail asset, change the ordinary Xvfb
backend, relax cleanup, or claim live GPU proof.

## Delivered boundary

`kpharness.gamescope_snapshot` now materializes a self-contained import closure
for `linux-wine-k1-gamescope` with a canonical sorted `path`/`sha256` manifest.
Creation hashes sources before and after copying and refuses a changing source.
Verification checks copied-module bytes and, when supplied `--source-root`,
also rejects any changed, missing, or newly imported source module. The driver
then runs `kpharness.creative` with the snapshot runtime as its only harness
import root. The snapshot contains Python harness modules only; a K1 install,
runtime DLL/proxy, saves, routes, Wine prefix, media, and all retail data remain
external identities that the existing run receipt must record separately.

`GamescopeXwaylandLease` writes `gamescope-lease.json` atomically before
`Popen`, immediately after the Gamescope leader identity/process-group/session
is known, after the readiness child is verified, after renderer readiness, and
on every boot or cleanup failure. The record keeps the run ID, non-secret argv,
leader PID/start/PGID/session, readiness child PID/start/sanitized display, boot
phase, cleanup phase, and failure text. It never includes Xauthority paths,
cookies, or a general environment dump. Every atomic version retains a
numbered monotonic/UTC event history, including cleanup actions. Cleanup
retains the record and still signals only an identity-verified owned process
group.

## Focused host evidence

`tools/kpharness_gamescope_backend_test.py` adds checks for a complete
module-only snapshot, changed-source refusal, and an early Gamescope-exit
receipt that retains leader identity without calling `killpg`. The pre-existing
PID-reuse test continues to assert that a mismatched leader identity receives
no signal. These are host-only fakes; no display, Gamescope, Wine, FFmpeg, or
game process is started by them.

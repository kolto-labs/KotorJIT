"""Headless driver for the KotorPhasor harness channel.

The runtime inside the game opens a loopback listener (see
docs/harness-design.md). This package is the side outside the process: it
stages a writable game tree, boots Xvfb plus Wine or the native ELF, connects,
and then drives the game by request and state read, never by keypress or
pixel. Everything except the optional screenshot conversion and OCR is the
standard library, so it runs under the system interpreter as it is.

Modules:
  targets      per-game facts (exe, ini, save dir, start module, build ids)
  discover     find the install and the build tree, never a hard-coded path
  session      GameSession: stage, boot, connect, tear down
  client       Channel: JSON lines with ids, timeouts, and an event cursor
  waits        wait_until and the named engine-state predicates
  oracle       Watchdog: crash, hang, load-stuck, softlock, refusal
  shots        periodic screenshots, PPM to PNG, optional OCR cross-check
  checkpoints  named save folders copied in and out of the save dir
  scenario     TOML step files and the runner that executes them
  cli          kpharness boot|status|state|exec|events|run|shots|down
"""

__all__ = [
    "targets", "discover", "session", "client", "waits", "oracle",
    "shots", "checkpoints", "scenario", "cli",
]

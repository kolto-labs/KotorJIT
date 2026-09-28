---
name: binary-harness-bringup
description: Get a headless harness running against a real binary under Xvfb and Wine, and diagnose the boot failures, hangs and stale-state traps that make a working harness look broken. Use when a harness that builds and passes its unit tests will not drive the live application.
---

# Bring-up: the failures that are not in your code

A harness fails its first live run for environmental reasons far more
often than for logical ones. Each item here cost real time to find. Check
them before reading your own code again.

## Launch

**Launch the executable directly.** Wrapping it in a virtual desktop
(`wine explorer /desktop=name,WxH`) is a common recipe and it killed the
process within seconds with an empty stderr, while the same tree launched
with plain `wine app.exe` ran and installed every hook. The virtual
display already provides a root window of the right size. Keep the
wrapper behind an environment switch for debugging, not as the default.

**Skip prefix initialisation when the prefix exists.** `wineboot -i`
against an initialised prefix hung for ten minutes and ate an entire run
budget. Test for the prefix's registry file, skip it, and put a short
timeout on it when you do run it so a stall degrades to a warning.

**Strip the desktop session environment.** The session bus and Wayland
variables leak into the child and its portal calls register against your
real session. Unset them before launch.

## Stale state

The most confusing bugs are the ones where the thing you are testing is
not the thing you built.

- **A stale artifact.** The runtime in the game tree was a day older than
  the one in the build tree, so a whole run tested yesterday's code. Copy
  the freshly built artifact at the start of every run and compare
  checksums when a result makes no sense.
- **Stale locks.** Per-display lock files outlive their owners. Reclaim
  a lock whose recorded process is dead, and delete an empty one.
- **Orphan displays.** A leftover virtual framebuffer holds its lock file
  and its display number even though its owner is gone, and reclaiming
  the harness lock does not kill it. Skip display numbers whose system
  lock file exists, rather than trying to take them.
- **Overwritten evidence.** Do not write logs to a fixed path that the
  next run truncates. One directory per run, nothing deleted.

## Configuration files

**Preserve line endings.** A Windows application's configuration file
uses CRLF. Reading it with a tool that normalises to LF and writing it
back can leave a parser that silently ignores the file. Read bytes, write
bytes, and check the file type afterwards.

**Set every occurrence of a key.** These files repeat the same key in
several sections with different values. Setting the first one is a
coin flip.

**Do not assume the file is well formed.** A shipped configuration file
had a section header missing its opening bracket. Diff against a backup
before blaming your own edit.

## Diagnosing a hang

When a command never replies and the process stays alive:

1. **Find the last thing it logged.** Log before and after each call in a
   sequence, not just at the start. "Entering call 2" versus "call 2
   returned" is the difference between a diagnosis and a guess.
2. **Check whether the whole loop is wedged or just that command.** Send
   an unrelated cheap request. If that also times out, the drain is
   blocked and every later symptom is downstream of one call.
3. **Get a stack.** Attach a debugger to the stuck process and dump all
   thread stacks. Resolve the addresses against your own module's symbol
   table by subtracting the module base. This tells you in one shot
   whether it is spinning on a message pump, blocked on a socket, or
   looping in application code.
4. **Only then form a theory.**

## Timeouts

Give every request a generous ceiling and treat expiry as a report, not a
retry. A ten-second reply budget on a call that legitimately takes longer
produces "no reply" and hides the real behaviour. Separately: a timeout
that fires and then leaves the connection in an undefined state will make
every later request look broken too, so drop stale replies by request id.

## Resource limits

Software rendering and a large application will use what you give them.
Cap the renderer's thread count, run one instance at a time, and check
free memory before a run on a loaded machine. A harness that trips its
own hang detector because the host is swapping teaches nothing.

## What "it works" means

Not a green build and not a passing unit suite. One live run in which the
application reached the state the scenario asked for, reported by the
application itself, with no synthetic input anywhere in the path. Until
that exists, say what has been proven and what has not.

# Task 7 supported physical-console re-review — fix round 3

## Scope and method

Reviewed only the requested round-three serialization fix in
`scripts/harness/kpharness/physical_console.py`,
`scripts/harness/kpharness/console_steps.py`, and
`tools/kpharness_physical_console_test.py`, against the round-two review and
the task report.  No files in the worktree were edited, staged, or committed;
no game was launched and no broad suite was run.

One attempted narrow unittest invocation used the singular class name
`PhysicalConsoleTest`; the file defines `PhysicalConsoleTests`, so unittest
failed discovery before executing the target test.  It provides no behavioral
validation and was not retried, to keep within the one-focused-probe limit.
The conclusions below are therefore source and test-structure review, not an
independent passing-test claim.  The task report records the implementer's
separate 22-test focused run.

## R2-I1 — ADDRESSED

The defect was that `_console_command` created an ordinary list from the
frozen `receipt.lines`, while the old `thaw_receipt` converted mappings and
tuples only.  The list therefore retained its nested `FrozenMapping` entries,
and `json.dumps(..., default=str)` serialized each line as a Python object
description rather than protocol evidence.

The current implementation closes both parts of that path:

* `physical_console.py:78-84` recursively converts every mapping and every
  list or tuple.  A scenario receipt's `list(receipt.lines)` is now traversed,
  so each frozen line mapping and the nested `kind` and `text` byte mappings
  become ordinary JSON containers.
* `console_steps.py:25-33` calls ordinary `json.dumps(thaw_receipt(body))`
  without `default=str`.  Any unsupported receipt value now fails at the
  writing boundary instead of being silently replaced with an object
  representation.
* `tools/kpharness_physical_console_test.py:475-499` runs the actual
  `console_command` scenario path, opens the written receipt with
  `json.loads`, requires two line objects, checks the exact
  `(session, request, sequence)` identity, and requires `kind` and `text` to
  remain base64 byte-object mappings.  This is a real serialization round
  trip rather than an in-memory check.

The regression would fail on the round-two corruption: after the prior
`default=str` path, each `body["lines"]` item would be a string, causing the
`dict` assertion (and subsequent key access) to fail.  With the new removal
of `default=str`, the old incomplete thaw would instead fail serialization;
the scenario could not return its expected successful result.  Either form
of the former defect is rejected.

## New-breakage scan

No new Critical or Important breakage was found in the three scoped files.
The recursive conversion maintains the receipt's expected JSON container
shape and affects only the explicit file-materialization boundary.  Removing
the string fallback intentionally makes malformed evidence observable; the
existing `OSError` handling remains limited to actual filesystem failures.

## Verdict

**R2-I1: ADDRESSED.**

**Task-spec compliance: PASS for the supported host-side console boundary.**
The prior review's I1, I5, M1, and N1 findings remain addressed, and this
round repairs the only newly introduced Important issue without adding a new
Critical or Important issue.

**Task quality: READY for its separate owned installed-K1 acceptance gate.**
This host-side result does not establish the pending live-game acceptance
receipt identified in the task report; it establishes that a successful host
scenario now retains structured output evidence when it is written.

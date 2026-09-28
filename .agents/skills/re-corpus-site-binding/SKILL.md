---
name: re-corpus-site-binding
description: Turn a decompiled or reverse-engineered corpus into an address table a runtime can safely call, with per-build resolution, evidence, and honest confidence. Use when binding functions, struct fields or offsets in a closed-source binary for injection, hooking or a test harness.
---

# From a decompiled corpus to a call you can trust

Recovered source is a hypothesis with a line number. It is good enough to
find a function and bad enough to crash a process. This skill is how to
cross that gap without either paralysis or a hang.

## Name logically, resolve per build

A site is a logical name (`app.create_server`, `dialog.select_reply`),
never an address in code. Addresses live in per-build data, resolved at
load time against the identified build. Adding support for another build
of the same application is then a data change.

Carry a byte signature next to the address and treat the address as a
hint. If the bytes at the hint do not match, scan for the signature. A
build that shifted by a patch still binds.

## Field sites are not function sites

A field is an address plus an offset and a size, reached either from a
global or by walking a chain of pointers. Two consequences people miss:

- A byte-signature scan is meaningless for a field, and running one will
  either fail to resolve it or, worse, relocate it to whatever code
  happens to match. Skip signature resolution for fields.
- A field must be optional. A required field that fails to resolve
  aborts the whole install, and the point of the mechanism is that a
  build you have not fully mapped still runs with less capability.

Read every field through a probe that checks the address is mapped
before dereferencing. A stale pointer is the normal case, not the
exception.

## Two independent signals

Bind a name only when two sources agree: the recovered source and the
symbol or identity database, or a byte pattern and a cross-build match.
Where only one exists, bind it anyway but lower its confidence and keep
it optional, and say so in the record. A binding with an honest
confidence is useful; a binding that claims certainty it does not have
will be trusted at exactly the wrong moment.

Write findings back to the shared corpus with a method that names the
project and the technique, so a later reader can weigh them. A finding
that stays in one consumer's data directory gets rediscovered by the
next person.

Assign corpus curation to a dedicated agent whenever parallel agents are
available. That agent inspects the durable corpus and its provenance before it
writes, validates each consumer-side finding against the exact binary and the
best existing project state, and rejects stale or weaker replacements. Keep
advisory decompiler output, readable source, compiling source, and byte-verified
source in their proper claim tiers.

When a writable shared Ghidra repository and a local project represent the same
Odyssey corpus, keep them synchronized. Pull and reconcile the shared project
before mutation, check in validated names/types/comments through the supported
repository workflow, update the paired local project, then reopen or query both
sides and retain a receipt proving program identity, version, and curated state.
Neither side is a disposable cache, and the shared repository is not read-only.
Never re-analyze an already analyzed program merely to synchronize it.

## Calling conventions are not data

Do not read the convention from a corpus column and dispatch on it. The
column is advisory and it has been observed wrong: a function recorded as
taking no `this` was a thunk that read it from a register. Hardcode the
call shape per function at the call site, where a human decided it.

The one thing that must be parameterised is the platform. The same
function compiled for Windows takes `this` in a register and compiled by
a Unix compiler takes it as the first stack argument. Pick the shape from
the identified platform, not from the architecture.

## Never pass a null object pointer

If the decompiler shows `this` unused on the path you care about, that
is one path. Passing null is a hang or a corruption you cannot see into
from outside. Prefer, in order:

1. Reimplement the behaviour yourself. Archive extraction, a file copy,
   a string build: all cheap and all yours.
2. Find a static or free-function variant of the same operation.
3. Obtain a real instance.

When you reimplement, verify against the original: run the application's
own path once, keep its output, and assert your implementation produces
the same bytes. That check turns a plausible reimplementation into a
proven one.

## Struct offsets

Derive an offset from the type definition by summing field sizes, and
check it against a size assertion in the same header. Then confirm it
against a function body that uses the field. Two derivations that agree
is the bar; a single sum is where off-by-one-field errors live.

Offsets differ between builds of the same application far more than
function addresses do. Never copy an offset from one build to another
because the function addresses matched.

## Prefer the application's own sequence

When you need a complex operation, find where the application does it
and replay that call sequence rather than inventing one. Read the whole
function, including the branch you are not taking, and note every
argument it computes from state you would have to fake. That reading is
what tells you whether the operation is replayable at all, or whether it
depends on objects only the real path creates.

If it turns out not to be replayable, that is a finding, not a failure.
Record it and choose another route.

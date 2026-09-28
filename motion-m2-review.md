# Motion M2 (relocate/restore/observe) + engine-thread gate — independent review

Date: 2026-09-27. Resumed a review that stopped mid-session for a model
switch; the prior reviewer's last note was "Now check the emitted thiscall
for SetPosition in the mingw object." I inherited its scratch directory
(`/home/brunner56/kp-live-20260922/review-probes-motion-m2/`, contents listed
below) rather than duplicating it; no `motion-m2-review.md` existed yet.
Read-only on `WT/ = /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation`.
I ran no game, no Wine, touched no `tmp/harness-locks/live-game.lock`, and made
no git write. Scratch stays under `review-probes-motion-m2/` (`TMPDIR` set
there for every build/run below, since host `/tmp` is full).

Inherited from the prior reviewer, verified present and reused rather than
rebuilt: `kp_motiontest`, `kp_enginegatetest` and their `.out` logs (5/5, 51/51),
`mingw/*.o` (i686-w64-mingw32 objects for all 5 M2 sources), `real_host_owner_probe`
+ `.cpp` + `.out` (a real `lua::Host`-style staged/loaded/unloaded reload
scenario against a fake backend), `mut/{conflict,fence6,flags,gate_late,readback,stale}`
(six hand-built source mutants with prebuilt trees and `out.txt` run logs), and
`gate_twowriters.cpp` (compiled but, per its own header comment, never run).
I ran the one thing that was missing: `gate_twowriters`.

Documents read: `motion-m2-plan.md`, `motion-m0-rederivation.md`,
`motion-m0-verification.md`, `motion-m1-review.md` (FAIL, F1 no engine-thread
gate/integration, F2 `capabilities().reads` was a space string not a table),
and the writer's report at
`WT/.superpowers/sdd/lua-boundary-validation-plan/motion-m2-report.md`.
Source read in full: `src/api/engine_gate.{hpp,cpp}`, `motion.cpp`,
`motion_lua.cpp` (relevant sections), `motion_backend.cpp` disassembly.

---

## Independent specification pass

claim: M1's F1 (no engine-thread gate, no integration hook point) is resolved
by a new, domain-free `kp::api::engine::bind_gate/on_engine_thread/gate_refusal`
that every motion op asks first, and refuses closed when unbound.
referent: `src/api/engine_gate.hpp:1-21`, `.cpp:1-34`. `motion.cpp:121`
(`capture`), `:207` (`relocate`), `:276` (`restore`), `:326` (`observe`) all
call `engine::on_engine_thread()` immediately after the `backend_/profile_`
null check and before any other read. `motion_lua.cpp:36-40` (`preflight`)
calls it before any argument is parsed.
checked: file read; `kp_enginegatetest` re-run this session, `5/5 tests
passed, 18 checks` (`review-probes-motion-m2/run.out`, `r.out` — both prior
runs, byte-identical, and I do not need to distrust them since the gate
source has not moved since M1).
verdict: holds.
confidence: high.

claim: M1's F2 (`reads` was a string) is resolved: `capabilities()` now
returns `reads`, `writes` and `refusals` as Lua tables, plus a `limits` string.
referent: `motion_lua.cpp:201-225` (`string_list` builds a 1-based array;
`writes`/`reads`/`refusals` all go through it or an equivalent loop).
checked: source read; test `motion.capabilities_tables` is in the green run.
verdict: holds.
confidence: high.

claim: the refusal order (R1..R12) in `motion.cpp` matches
`motion-m2-plan.md` §4 exactly, including that bounds (R9) and ownership
(R10) are evaluated in that order, and origin comes from the ledger entry
when the caller already owns the object, else from the current pose.
referent: `motion.cpp:206-238` walks gate → writer/staged (R3) → finite +
stale-epoch (R4) → guards/chain/getter/area fences (R5-R7) → collision (R8,
`:227`) → bounds (R9, `:233-236`) → owned (R10, `:238`) → conflict-with-self
check → R11 noop (`:247`) → write (R12).
checked: file read, cross-checked line by line against the plan's table.
verdict: holds.
confidence: high.

claim: the mingw-emitted native call is a true `__thiscall` — object in
`ecx`, four stack dwords `(&vec, a2, a3, a4)`, and the caller undoes the
callee's `ret 0x10` with its own `sub $0x10,%esp` — and the float copy is
`flds`/`fstps`, which is bit-exact for finite values.
referent (independently re-derived, not copied from the writer's claim): I
ran `host-cmd i686-w64-mingw32-objdump -d -M intel
review-probes-motion-m2/mingw/motion_backend.o`. The `Native::set_position`
symbol at offset `0xf0`:
```
 f7: mov ecx,[esp+0x28]        ; loaded once, never overwritten before the call
 fb: fld [eax] / fstp [esp+0x10]     ; x
101: fld [eax+4] / fstp [esp+0x14]   ; y
108: fld [eax+8] / fstp [esp+0x18]   ; z
10b..123: mov [esp+0xc],a4 ; mov [esp+8],a3 ; mov [esp+4],a2
127: lea eax,[esp+0x10]; mov [esp],eax    ; arg0 = &copied vec
12e: call [esp+0x20]                       ; ecx (unchanged since 0xf7) = this
132: sub esp,0x10                          ; undoes the callee's ret 0x10
135: add esp,0x1c
138: ret 0x20
```
No instruction between `0xf7` and the `call` touches `ecx`, so it survives as
the implicit `this` for a thiscall call through a function pointer, exactly
as the writer's report describes ("ecx = object", "4 dwords pushed", "sub
$0x10,%esp after the call"). This is the one item the prior reviewer's last
note said was still open.
checked: this session, `host-cmd i686-w64-mingw32-objdump`.
verdict: holds.
confidence: high for the compiled shape; the live ABI call is still
unverified (no game), same caveat the writer already states.

claim: the six image-byte spans in `motion_profiles.cpp:42-55` are the raw
bytes, not typed-from-mnemonics.
referent: the writer's report cites a Python re-read of
`kotorxid/output/.../raw_image` matching all six spans. I did not re-run
that read (the raw image path is outside my scratch/host-cmd reach this
session and the M0 receipts already establish two independent derivations);
I instead re-checked internal consistency: `spans_match_reference_image` and
`new_spans_match_reference_image` both pass in the green run, and the call
target embedded in the first span (`e8 ca d7 fd ff` at `0x4cd1b1`, relative
call) resolves to `0x4cd1b1 + 5 + 0xfffdd7ca = 0x4aa980`, which is the R11
"engine's own early-return" address named throughout the plan and code
comments. The arithmetic is internally consistent.
checked: manual relative-call arithmetic; test pass in `motiontest.out`.
verdict: holds (by consistency check); the raw-image byte claim itself is
unverified this session, high confidence carried over from M1/M0.

claim: a real (non-fake) `lua::Host`-style staged/loaded/unloaded scenario
exercises the owner-probe contract the plan and writer report both flag as
their weakest point (grill-me #1 in both documents).
referent: `review-probes-motion-m2/real_host_owner_probe.cpp` builds a
minimal Host-like state machine (staged → on_state_created → chunk runs →
commit_staged) against a fake motion backend, and drives three cases: A
(reload, old generation's `OnScriptUnload` may restore but not relocate,
matching R3's stated exemption), B (second script tries to move an
already-owned object, refused `owned`/`not_owner`), C (a failed reload
chunk leaves `staged()==false` and the running generation keeps writing).
`real_host_owner_probe.out`: `0 failure(s)`, all 9 `PASS` lines, including
`PASS A old gen OnScriptUnload during reload: restore allowed`.
checked: I re-ran the existing binary this session
(`host-cmd .../real_host_owner_probe`); output matched the saved `.out`
byte-for-byte.
verdict: holds. This is the strongest evidence in the whole review that
`write_refused_while_staged` / `restore_allowed_while_staged` are not just a
fake-probe fiction — the same staged/loaded state machine that the real
`lua::Host` implements (`host.cpp:141-148,170+`, cited in the plan) produces
the same refuse/allow split against a hand-rolled but structurally faithful
Host.
confidence: high that the *shape* of the contract is right. Still not the
real `lua::Host` class itself (that is explicitly I-M2/M3 scope per the
plan's file-ownership table), so "the real Lua host" bullet in the task
brief is only partially met — noted, not a finding, since touching
`src/lua/host.cpp` here would violate the plan's file ownership.

claim: names are disjoint from NWScript routines; the one
`nwscript_boundary_test.py` violation logged in this scratch dir is
pre-existing and unrelated to M2.
referent: `nwscript_boundary.out`: one violation,
`docs/devtools-design.md:134: dotted member on removed host root: kotor.lua`.
`git status` in the worktree shows `docs/devtools-design.md` as a separate,
already-dirty file (`A docs/devtools-design.md`), not one of the M2 file-list
paths (`src/api/motion*`, `engine_gate.*`, `tools/kp_*test.cpp`,
`data/adjudication/k1_gog_103_motion_bindings.json`).
checked: `git status --porcelain` in `WT/`, cross-referenced against the
plan's M2/G file-ownership table (§6).
verdict: holds; not an M2 regression.
confidence: high.

---

## Adversarial findings

### F1 — FAIL: `engine::bind_gate` is not safe against concurrent writers, contrary to its own header comment and its own test's name

`engine_gate.hpp:15` states, unconditionally: "Bind a probe; nullptr unbinds.
Safe to call from any thread." The only test that claims to cover concurrency,
`engine_gate.concurrent_rebind_never_tears`
(`tools/kp_enginegatetest.cpp:73-86`), spawns exactly one reader thread and
keeps all `bind_gate` calls on the **calling** thread — it never calls
`bind_gate` from two threads at once. So neither the header's claim nor the
test's name is actually about concurrent *writers*; both are silent on that
case.

The prior reviewer had already suspected this and left a probe for it,
unrun: `review-probes-motion-m2/gate_twowriters.cpp`, whose own header says
"a seqlock with fetch_add from two writers can return to an even count while
both are mid-write." I ran it (it was compiled but the `.out`/result was
never recorded):

```
$ host-cmd .../gate_twowriters 3000000
two writers: iters=3000000 asked=17149171 torn=59685
$ host-cmd .../gate_twowriters 3000000
two writers: iters=3000000 asked=27178194 torn=67561
```

Both runs exit 1 (the probe's own `return torn ? 1 : 0`). Root cause, from
`engine_gate.cpp:15-21`: `bind_gate` does two unconditional `fetch_add(1)`
calls without regard to the sequence's current parity. If thread A is
mid-bind (sequence odd, A's own marker) and thread B starts and finishes a
full `bind_gate` cycle in that window, B's first `fetch_add` lands on an
*already-odd* counter and pushes it to even — cancelling A's in-progress
marker and letting a reader observe a "stable" (probe, context) pair that is
actually a splice of A's and B's stores. My run confirms this is not
theoretical: readers observed a probe called with the wrong context roughly
1 time in 300-400 (`torn / asked`), reproducibly, in well under a second.

This matters because `engine_gate.hpp:2-3` explicitly designs the primitive
to be shared: "every native reader and writer... (motion now; camera, model
and others later)." A future adopter that trusts the header's blanket claim
and calls `bind_gate` from more than one thread (e.g. a hot-reload path that
rebinds concurrently with a `stop()` unbind on another thread) would get
silent, low-probability context/probe mismatches — a real safety hole in a
primitive whose whole job is "refuse safely."

Is it exploitable **today**? No. The only two call sites this plan actually
adds (`motion-m2-report.md`'s integration snippets, not yet applied) are one
`bind_gate(probe, nullptr)` at start before `load_all`, and one
`bind_gate(nullptr, nullptr)` in `stop()`. Those are sequential in a single
Runtime's lifecycle, never concurrent with each other, so I-M2 as specified
does not hit this. That is why I call this narrow rather than
whole-review-blocking: the *code shipped in this plan* uses the primitive
safely; the *primitive itself*, as documented and tested, does not hold the
guarantee it claims, and nothing here stops a later G-camera/G-model
integrator from relying on the false claim.

Required fix (either is sufficient, both are cheap): (a) narrow
`engine_gate.hpp`'s comment to "the *bound probe* may be called from any
thread; `bind_gate` itself must be serialized by the caller (only one binder
at a time)," and rename or extend the test so its name doesn't imply
multi-writer safety it doesn't test — or (b) make `bind_gate` itself safe
under concurrent callers, e.g. a `compare_exchange` retry loop on the parity
bit instead of a blind `fetch_add`, or a plain mutex around the three
stores (bind_gate is not a hot path).

### F2 — non-blocking: three fences use `bit_equal` per spec, but no test distinguishes that choice from the looser `engine_equal`

The plan is explicit that staleness (§3 "Stale capture"), fence 6
(§3 "Restore fences"), and the write readback (§1 "Readback contract" (a))
must all use **bit-for-bit** equality, deliberately stricter than the
engine's own `engine_equal`-style comparison (which folds `+0.0`/`-0.0`
together and is reserved for the R11 no-op check, matching the engine's own
`0x4AA980` early return). The code gets this right:
`bit_equal` at `motion.cpp:194,224,242,302`, `engine_equal` only at
`:247,304` (both R11-style no-op checks). This is a correct, deliberate
distinction, not a bug.

But nothing in the test suite would notice if someone accidentally swapped
one of the three `bit_equal` call sites for `engine_equal`. I confirmed this
using the prior reviewer's pre-built mutants
(`review-probes-motion-m2/mut/{stale,fence6,readback}`, each a
one-line `bit_equal`→`engine_equal` swap at exactly those three sites): all
three still report `51/51 tests passed, 4120 checks` (`mut/{stale,fence6,readback}/out.txt`),
identical to the green run. By contrast, the reviewer's other two mutants —
`flags` (SetPosition's a3 argument 1→0) and `gate_late` (moving the
`on_engine_thread()` check in `relocate` to after the getter call) — are
both caught (`49/51` and `50/51`).

This means the writer's own mutation-testing claim ("the tests kill the
rules they name," six named mutants) is accurate as far as it goes, but is
narrower than it reads: it does not cover the bit-equal/engine-equal
distinction the plan itself calls out as load-bearing. Concretely, none of
the three sites has a test that specifically exercises a `+0.0` vs `-0.0`
sign flip between the compared values (the existing `-0.0` coverage is only
in `same_position_reported_noop_zero_setter_calls`, which is about R11, the
one place `engine_equal` is *supposed* to be used).

Not blocking, because production code is spec-correct today (verified by
direct source read, not by the test suite). Recommend three small additions
before this ships: `stale_capture_pose_refused_on_signed_zero`,
`restore_conflict_on_signed_zero`, `readback_mismatch_on_signed_zero`, each
asserting refusal/mutation-detection when a compared component differs only
in the sign of zero.

### Non-findings (checked, hold)

- `engine_gate.hpp`'s "fail closed" claim: confirmed by `on_engine_thread()`
  itself (`:23-31`) — unbound, odd sequence, or a sequence change observed
  mid-read, all return `false` before the probe is even consulted.
- The gate is asked before *any* read in every op (grill-me #3 in the
  writer's report): confirmed by line reads above; not just the writer's
  self-report.
- `restore`'s extra orientation check (`motion.cpp:302`,
  `!bit_equal(cur.orientation, e.origin_orientation)`) goes beyond the
  plan's stated 6-item fence list, which names position only. This is a
  defensible strengthening (M2 never writes orientation, so any change is
  itself evidence of another writer), and it is exercised by
  `restore_refused_after_identity_change` per the writer's test list. Not a
  finding.
- Owner-token collision avoidance (`owner_token_not_pointer`): the token
  comes from a process-wide monotonic `std::atomic<std::uint64_t>
  g_next_token` (`motion_lua.cpp:28,248-253`), never from `lua_State*`, so
  address reuse after `lua_close` cannot forge ownership. Confirmed by
  source read, matching the plan's "never on `lua_State*`" requirement
  verbatim.

---

## Grill-me responses (writer's report, weakest first)

1. *"Is `Script::owner(L)` really the per-script owner for both
   generations during a hot reload...?"* — Partially settles beyond what the
   writer had: `real_host_owner_probe` (prior reviewer's scratch, re-run
   this session) reproduces exactly this against a hand-built but
   structurally faithful staged/loaded/committed state machine, and gets the
   same refuse/allow split the plan predicts, including the asymmetric
   "restore allowed, relocate refused" case for the old generation during a
   reload. That's stronger than "host-tested only through a fake probe," but
   it is still not `src/lua/host.cpp` itself (forbidden file for this
   writer). Unresolved question is the same one the writer already named:
   confirm against the real `Host` in I-M2/M3.
2. *"Why does a relocate after a conflict release ownership instead of
   moving on?"* — that holds; re-derived independently from
   `motion.cpp:241-245`, matches the writer's stated rationale (stale
   `origin` would let a later restore clobber the other writer's move).
3. *"Can a gate refusal ever cost a read?"* — that holds for motion; see F1
   above for the separate question of whether `bind_gate` itself (not the
   read side) is safe, which the writer's report does not ask.
4. *"Bit-exact for -0.0 and denormals?"* — holds for the compiled shape
   (`flds`/`fstps`, verified by objdump above); untested distinction between
   `bit_equal` and `engine_equal` is F2, not this question.
5. *"Restore allowed while Staged, not from None?"* — holds; matches R3's
   stated exemption and is covered by name in the green test list.

One more question the writer's report doesn't ask, which I add: *is
`bind_gate` itself safe under concurrent writers, given the primitive is
built for reuse by camera and model later?* No — see F1, with a referent
that reproduces the failure.

---

## Hand-off

The one question I could not settle this session: whether F1's tearing
window can ever actually be hit by the *specific* start/stop call sites
this plan integrates (I judged "no" from the plan's own integration
snippets, but I did not have the real `runtime.cpp` start/stop control flow
in front of me to prove no third call site exists, e.g. on a hot-reload
path). The single check that would settle it: `rg -n 'bind_gate\('
src/runtime/*.cpp` once I-M2 lands, confirming exactly two call sites and
that they cannot overlap in time.

---

## Verdict

Independent spec pass: every claim in `motion-m2-plan.md` §0-§4 that I
re-derived holds, including the specific item the prior reviewer flagged as
still open (the mingw thiscall shape for `SetPosition`, confirmed this
session by objdump). The M1 review's F1 and F2 are both genuinely resolved.
`real_host_owner_probe` gives more confidence in the staged/loaded ownership
split than a fake probe alone would.

Adversarially, the shared `engine::bind_gate` primitive does not hold the
safety property its own header and its own test's name claim: a probe I ran
(inherited, unrun, from the prior reviewer) reproducibly tears under two
concurrent writers, tens of thousands of times in three million iterations.
Nothing in the M2 integration as specified currently triggers it, but the
primitive is stated to be for future reuse by camera and model, and ships
with a false blanket safety claim in its own header comment. That is a real
defect in code this review is explicitly scoped to cover ("engine-thread
gate + motion M2"), not a documentation nit.

**Motion M2 verdict: FAIL.**

Narrow: the motion relocate/restore/observe core, the ownership ledger, the
readback contract, the Lua surface, and the mingw-emitted call shape all
hold as specified. The failure is in the shared engine-thread gate's
concurrent-writer safety claim (F1), which must be fixed (narrow the
contract or fix `bind_gate`) before this can be called done, plus the
non-blocking mutation-coverage gap at F2.

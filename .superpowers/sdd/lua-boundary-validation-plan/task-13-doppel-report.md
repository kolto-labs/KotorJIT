# Task 13 Doppelganger report

## Result

DONE_WITH_CONCERNS

The retained `cursed/70_doppelganger.lua` now captures the PC row before
applying Malak, uses that frozen value for every eligible hostile, and treats
each permanent disguise as a handle-owned transaction. It tracks the exact
post-apply effect-handle delta per actor, removes only those handles, verifies
the row restoration, and retries known failed rollbacks during transition
cleanup. Normal combat settling, module load, and area entry all use the same
idempotent restoration path.

The controlled fixture now has per-object current/base appearances and
actor-owned effect handles. The enhanced host cases cover capture ordering,
multiple copies after the PC changed to row 21, invalid/dead/party/duplicate
guards, constructor and thrown-apply failures, post-apply enumeration rollback,
retry, exact owned-handle cleanup with a pre-existing disguise, normal settle,
module load, and area entry.

The live route records PC P, marks exactly three living hostile fixtures,
records every E row and baseline disguise count, observes all three copies
while alive, ends combat without killing them, and checks P/each E plus the
baseline disguise-count restoration after the settle window.

## Changed paths

- `scripts/examples/cursed/70_doppelganger.lua`
- `tools/tests/examples/fixture.lua`
- `tools/tests/examples/cursed.lua`
- `scripts/harness/scenarios/cursed/70_doppelganger.toml`
- `tools/tests/examples/manifest.json`

Fixed original41 SHA-256: `8ddca28a915b83c7cf432acf9dc2fbed76bfff80750a37417f3824c5e0958cd7`.

## Validation

Commands run from the assigned worktree:

    /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /tmp/kp-doppel-example-validation.json

Result: PASS: 41 original syntax/host regression sources, 82 per-file cases;
8 retired from public catalog; 0 live receipts attached; no public quality
promotion.

    ctest --test-dir /home/brunner56/kp-validation-20260922-build -R '^example_validation$' --output-on-failure

Result: 1/1 Test #25: example_validation passed.

    /usr/bin/luajit -e "assert(loadfile('scripts/examples/cursed/70_doppelganger.lua')); print('doppel syntax: PASS')"
    git diff --check

Result: syntax passed; no whitespace errors. A Python 3 tomllib probe also
passed the manifest hash and the 12-step scenario's explicit `nwscript.call`
and no-`kp` shape.

## Concerns

- No game was launched. The route and manifest remain live obligations until a
  fresh serialized K1 run binds current deployed/runtime hashes and retains
  the required row, effect, trace, and video artifacts.
- `python3 tools/nwscript_boundary_test.py` currently fails outside this task's
  ownership on the pre-existing dirty file `docs/devtools-design.md:134`
  (dotted member on removed host root: `kotor.lua`). The fixed Doppelganger
  source and scenario use explicit `nwscript.call`; the CTest build registers
  no separate nwscript_boundary test.

## Round 1 correction

BLOCKED

The previous implementation was unsafe. It compared Lua effect wrapper values
from separate K1 enumerations as table keys. The native bridge materializes a
fresh opaque effect value for each enumeration, so that comparison cannot
separate a just-added disguise from any pre-existing effect. The old
before/after delta could therefore remove baseline effects.

The allowed K1 routines expose only GetEffectType, GetEffectDurationType,
GetEffectSubType, and GetEffectCreator; none is a unique effect instance
identity. K1 does not expose GetEffectID, RemoveEffectByID, or
RemoveEffectByExactMatch. A matching type/duration/creator tuple is unsafe
because an actor may already carry an identical disguise. The missing primitive
is an engine-stable effect instance ID returned during enumeration, together
with removal of that exact ID or an equivalent exact-match operation.

The script now fails closed before any permanent disguise mutation. It records
the original PC row only for diagnostics, emits one explicit blocked oracle,
and applies/removes no effect. The fixture now rematerializes a fresh wrapper
for each effect enumeration. Its focused cases prove that wrapper identity is
not stable and that pre-existing identical disguises and injected
apply/enumeration/readback failure stimuli leave all rows/effects untouched.
This prevents the reviewed baseline-deletion and stranded-cleanup defects, but
does not satisfy active Doppelganger behavior without the missing native
primitive.

Updated source SHA-256: 078f9660472f85d93cb4db5406ae33d1e2750c37dc38bf69e38e4205fe97d1cb.

Round-1 command:

    /usr/bin/python3 tools/example_validation.py --luajit /usr/bin/luajit --host /home/brunner56/kp-validation-20260922-build/kp_luatest --receipt /tmp/kp-doppel-round1-validation.json

Result: PASS: 41 original syntax/host regression sources, 81 per-file cases;
8 retired from public catalog; 0 live receipts attached; no public quality
promotion.

The retained live route is marked as a future oracle and must not be executed
or accepted while this capability is absent. Its earlier row/count checks
cannot prove exact handle ownership.

The unavailable-wrapper, apply-succeeded/enumeration-failed, rollback-failed,
cleanup-retry, and unavailable-actor paths cannot safely be exercised as
mutation/recovery cases without the same missing identity primitive. The
fail-closed source proves the stronger safe invariant for all of them: none can
start a permanent transaction, overwrite recovery bookkeeping, remove a
baseline effect, or claim restoration.

An additional timeout 15s python3 tools/nwscript_boundary_test.py attempt
timed out (exit 124) in the shared dirty worktree after the example gates had
passed, so no boundary-suite pass is claimed for round 1. git diff --check
passed.

## Round 2 retained-token correction

Implemented the exact engine-token transaction identified by the subsequent
K1 audit. Every actor receives one fresh EffectDisguise constructor userdata.
The script stores that userdata before ApplyEffectToObject, uses it exactly once
for that actor, and later passes the same retained userdata to RemoveEffect.
It never uses GetFirstEffect/GetNextEffect to decide ownership and never
compares Lua wrappers.

The native evidence is specific: CGameEffect begins with a uint64 ID;
ApplyEffectToObject copies the effect without rewriting that ID; and K1
RemoveEffect compares both ID halves against the target effect list. This makes
the retained constructor userdata an exact removal token while fresh enumeration
wrappers remain irrelevant. The supporting audit is
/home/brunner56/kp-live-20260922/doppel-effect-identity-audit.md.

The implementation keeps a strong token reference in each pending actor record.
It records before-row before mutation, attempts exact-token rollback after every
apply/readback failure, holds cleanup-pending tokens through removal/readback
retry, blocks further mutation/rearming while unresolved, and reports an
invalid/dead actor as unavailable until a module/area transition terminally
hands its lifecycle back to the engine without claiming restoration.

The fixture now assigns stable internal token IDs to applied copies while every
enumeration returns a fresh wrapper. The new controlled cases cover a baseline
identical disguise surviving exact-token cleanup, three frozen-row copies,
post-apply mutation plus throw, failed cleanup retry, and unavailable actor
terminal transition.

Current source SHA-256: 0dd331aff9116aea6ccf29d5ef0048e6eeb405aecbb1e9163f77509e7695a737.

Focused controlled command and result:

    /usr/bin/luajit tools/tests/examples/run.lua /tmp/kp-token-sources.lua

Result: 71 cases passed.

The full hash-bound command was started with the current source and receipt
path /tmp/kp-doppel-token-validation.json, but it remained running beyond the
interactive tool window in the shared worktree. Do not treat it as passed.
The focused suite is controlled-backend evidence only. Per the audit, enabling
the scene for a release still requires a fresh serialized K1 proof that a
retained constructor token removes only its installed copy while an identical
baseline disguise remains.

## Round 3 final exact-token and transition correction

DONE_WITH_CONCERNS

The final implementation retains one freshly constructed `EffectDisguise`
userdata for every successful attempted apply. It stores the token before the
void apply, never derives ownership from effect enumeration, and passes that
same strongly retained token to `RemoveEffect` during rollback and normal
cleanup. A failed apply/readback or failed removal leaves its record and token
pending; `OnTick` retries cleanup and cannot rearm or apply another transaction
while any record remains.

The transition path was corrected after review: before an area/module transition
can clear a run, it attempts retained-token cleanup. If an actor (including the
PC across an area change) cannot be restored, it retains the record/token,
disarms, and reports exact cleanup unresolved. Invalid/dead actors are recorded
as unavailable and are never counted as restored. Appearance row zero is valid
and is covered by the host test.

The fixture models native-style copied effect IDs and fresh wrappers on every
enumeration. The final tests cover three frozen-row living copies, guards,
row zero, fresh-wrapper rematerialization, identical baseline preservation,
apply-that-mutates-then-throws, removal failure followed by retry, and an
unavailable actor through transition. The live scenario seeds baseline
disguises, keeps exactly three marked hostiles alive through cleanup, verifies
P/E rows during and after the scene, requires count exactly three, and verifies
baseline disguise counts after exact-token cleanup.

Final source SHA-256:

    2de760ebc0e3a7bd07d18c60f46c4a7d0a3ab08901638344e0fd14d11bd04d9a

Focused final command and result:

    timeout 15s python3 -c 'from tools.example_inventory import validate_inventory,lua_source_map; import json; print(lua_source_map(validate_inventory(json.load(open("tools/tests/examples/manifest.json"))))' > /tmp/kp-token-sources.lua && timeout 30s /usr/bin/luajit tools/tests/examples/run.lua /tmp/kp-token-sources.lua; result=$?; printf 'focused-suite-exit=%s\n' "$result"

Result: `CASES 71`; `focused-suite-exit=0`.

Final static consistency command and result:

    python3 - <<'PY'
    import hashlib, json, tomllib
    from pathlib import Path
    manifest = json.loads(Path('tools/tests/examples/manifest.json').read_text())
    entry = next(item for item in manifest['examples'] if item['path'] == 'cursed/70_doppelganger.lua')
    assert hashlib.sha256(Path(entry['source_path']).read_bytes()).hexdigest() == entry['sha256']
    scenario = tomllib.loads(Path('scripts/harness/scenarios/cursed/70_doppelganger.toml').read_text())
    assert scenario['name'] == 'cursed: doppelganger'
    for step in scenario['step']:
        code = step.get('code', '')
        assert 'kp.' not in code
        assert 'nwscript.' not in code.replace('nwscript.call', '')
    print('manifest hash and scenario boundary shape: PASS')
    PY
    /usr/bin/luajit -e "assert(loadfile('scripts/examples/cursed/70_doppelganger.lua')); print('doppel syntax: PASS')"
    git diff --check

Result: manifest hash and scenario boundary shape passed; syntax passed; no
whitespace errors.

The bounded broad receipt at `/tmp/kp-doppel-token-validation.json` completed
at 2026-09-27T07:23:17.596858+00:00 with 50 commands and zero nonzero exits.
It predates the final 02:24 local transition/row-zero source edit, so it is
recorded only as a successful earlier broad snapshot and is not claimed as
validation of the final SHA. Per the coordinator's bounded-gate instruction,
no further broad gate was started.

Remaining concern: no game was launched. The current manifest correctly keeps
the serialized K1 requirement open: prove after fresh wrapper enumeration/GC
pressure that the retained constructor token removes only its installed copy
while an identical baseline disguise survives. Host evidence proves the modeled
bridge semantics, not that live-engine predicate.

## Final route-oracle tightening

Only `scripts/harness/scenarios/cursed/70_doppelganger.toml` changed in this
pass; the Lua source did not change, so the manifest SHA was intentionally not
updated. Each marked hostile now records an exactly-one same-P baseline, must
read exactly two disguise effects during the owned active state, exactly one
after owned-token cleanup, and zero after removal with its retained baseline
constructor token. The existing P/E appearance, three-survivor, and exact
counter gates remain in each phase.

Command and result:

    timeout 15s python3 - <<'PY'
    import tomllib
    from pathlib import Path
    path=Path('scripts/harness/scenarios/cursed/70_doppelganger.toml')
    scenario=tomllib.loads(path.read_text())
    assert scenario['name']=='cursed: doppelganger'
    assert len(scenario['step']) >= 10
    print('toml-parse: PASS; steps=%d' % len(scenario['step']))
    PY
    timeout 15s git diff --check -- scripts/harness/scenarios/cursed/70_doppelganger.toml

Result: `toml-parse: PASS; steps=13`; `toml-parse-exit=0`;
`diff-check-exit=0`.

# Task 1 implementation report

Status: DONE. All required offline build and validation gates passed.

## Changes

The bridge registers only `nwscript.call`, `nwscript.with_caller`, and
`nwscript.last_trace`. It no longer creates `kp`. Native diagnostic output is
`kp.diagnostic`, with no log alias. Existing caller implementation, VM guards,
argument dispatch and error propagation remain in place; only module ownership
and public names changed. Active harness code, examples, catalog metadata,
generator output and user docs follow the new names. Historical evidence and
accepted pre-migration plans remain unchanged.

Native object conveniences remain distinct and explicitly consume the C++
`api::find`/`api::call` bridge. This dependency is documented in entity.cpp and
the generated migration guide. Native output's feedback helper retains its
existing protected calls to the Lua bridge; native registration itself does not
create that bridge. The shared production script/console initializer is unchanged.

Production-registration tests enumerate every selected game's routine table
with no same-name exceptions, check all three bridge exports, reject removed
native members, and test fresh bridge-only/native-only roots. Existing tests
still check standard global preservation, repeated registration and both
native compatibility installation orders; the bridge is always registered
before native facilities in the combined test. Fake-VM tests now check nested caller restoration,
variadic forwarding including nil, multiple results and original error-object
propagation, as well as the existing invalid-context guard and trace behavior.

The lexical checker adds catalog-derived literal dotted/bracket calls and
rawget lookups on explicit kp/nwscript receivers, including parenthesized and
_G receivers. It deliberately does not prove arbitrary aliases, computed keys,
plain reads or Lua execution semantics. Runtime registration tests cover actual
exported routine names. The checker documents this scope and accepts absence
assertions and standard math.log.

## Research grounding

Read the [Lua 5.1 Reference Manual](https://www.lua.org/manual/5.1/manual.html),
including global environments and luaL_register table ownership. Implementation
uses real separately owned global tables and preserves existing table identity;
it does not install an alias or metatable redirect between roots.

## Commands and results

- `/usr/bin/python3 tools/gen_compat.py`: regenerated migration docs and unchanged event/alias includes (0 aliases, 111 events).
- `/usr/bin/python3 tools/nwscript_boundary_test.py --self-test`: 23 forbidden and 7 allowed forms passed.
- `/usr/bin/python3 tools/nwscript_boundary_test.py`: final scan checked 276 active files, zero covered violations.
- `/usr/bin/python3 tools/kpharness_offline_test.py`: 144 tests passed in 52.121 seconds. All fixtures temporary; no game launched.
- Hostapi TOML parse, unique names and removed/new name assertions: passed.
- `git diff --check`: passed.
- `cmake --build /home/brunner56/kp-validation-20260922-build -j3`: passed, including native library/tools and Windows kphasor.dll. Full log: `/home/brunner56/kp-validation-20260922-build/task1-build.log`. Existing clobbered-variable and missing-field-initializer warnings remain.

The first CTest attempt was interrupted before test output because the configured
external-disk Python interpreter stalled in uninterruptible I/O. The owned CTest
process stopped; its interpreter received termination and kill signals. This is
an interrupted infrastructure attempt, not a test assertion failure. Reconfigured
with `cmake -S . -B /home/brunner56/kp-validation-20260922-build -DPython3_EXECUTABLE=/usr/bin/python3`
(success), then ran the full suite with system Python.

Full `ctest --test-dir /home/brunner56/kp-validation-20260922-build --output-on-failure`:
**16/16 passed**, 68.56 seconds, including both game namespace catalogs,
routine caller/trace tests, native support and all harness tests. Log:
`/home/brunner56/kp-validation-20260922-build/task1-ctest-system-python.log`.

## Self-review and limits

Reviewed changed registration code, removed the previous native log exception,
checked migration guards for absent nwscript roots, and kept historical research
outside active migration. Fake-VM and registration tests are offline proof;
they do not establish live game behavior. Existing stale-VM error semantics are
unchanged, including refusal to write caller fields after context replacement.
No game, push, PR, canonical checkout change or dependency mutation was performed.

## Generated-file restoration

The Python interpreter reconfigure invalidated the `structs_k1.inc` custom
command output: its command embeds `Python3_EXECUTABLE` (src/api/structs.cmake),
so changing that value changes CMake's rule hash. The source-tree output was
absent after reconfiguration. It was restored from the verified baseline;
`git hash-object src/generated/structs_k1.inc`, the index blob and baseline
`5cffd0f:src/generated/structs_k1.inc` all equal
`f53b78ec27fae1f71acc6fea351ff5fb22235af5`.
The successful build preceded that reconfigure, and its log shows the
`kp_structs_generated` target already current (no gen_structs invocation).
Therefore compilation used the baseline content; restoring identical bytes
does not require repeating compilation or the passed tests.

## Files

- `README.md`
- `data/hostapi.toml`
- `docs/api-dialects.md`
- `docs/coverage-harness.md`
- `docs/harness-design.md`
- `docs/lua-api-complete.md`
- `docs/lua-harness-api.md`
- `docs/user/api-status.md`
- `docs/user/scripts.md`
- `scripts/examples/coverage/10_cover.lua`
- `scripts/examples/cursed/10_rancor_roulette.lua`
- `scripts/examples/cursed/20_fus_ro_dah.lua`
- `scripts/examples/cursed/30_necromancer.lua`
- `scripts/examples/cursed/50_chaos_roulette.lua`
- `scripts/examples/cursed/60_rave.lua`
- `scripts/examples/cursed/70_doppelganger.lua`
- `scripts/examples/cursed/80_loot_pinata.lua`
- `scripts/examples/cursed/README.md`
- `scripts/examples/harness/110_loot_container.lua`
- `scripts/examples/harness/30_move_to.lua`
- `scripts/examples/harness/40_attack_nearest.lua`
- `scripts/examples/harness/50_doors.lua`
- `scripts/examples/harness/README.md`
- `scripts/examples/multiplayer/10_avatar_sync.lua`
- `scripts/harness/kpharness/scenario.py`
- `scripts/harness/scenarios/k1_dialog_walk.toml`
- `scripts/harness/scenarios/k1_endar_room3_onward.toml`
- `scripts/harness/scenarios/k1_endar_starboard_to_taris.toml`
- `scripts/harness/scenarios/k1_endar_trask_begin_diag.toml`
- `scripts/harness/scenarios/k1_endar_trask_opening.toml`
- `scripts/harness/scenarios/k1_endar_trask_range_diag.toml`
- `scripts/harness/scenarios/k1_fresh_trask_quest.toml`
- `scripts/harness/scenarios/k1_getfacing_diag.toml`
- `scripts/harness/scenarios/k1_softlock_detect.toml`
- `scripts/harness/scenarios/k1_trask_approach_diag.toml`
- `src/api/enginestruct.hpp`
- `src/api/entity.cpp`
- `src/api/output.cpp`
- `src/api/output.hpp`
- `src/api/routines.cpp`
- `src/api/routines.hpp`
- `tools/gen_compat.py`
- `tools/kp_namespacetest.cpp`
- `tools/kp_routinetest.cpp`
- `tools/kp_supporttest.cpp`
- `tools/kpharness_offline_test.py`
- `tools/nwscript_boundary_test.py`

## Review correction round 1

Fixed the review's P2 trace-contract finding in data/hostapi.toml,
tools/gen_compat.py and generated docs/api-dialects.md. Metadata now permits nil,
limits initialization to GetFacing routine 28 after context and argument-count
checks, and disclaims an arbitrary latest-dispatch receipt. Runtime behavior is
unchanged. Clarified the native compatibility registration-order test wording
above. No full build rerun was needed for these documentation-only corrections.

Exact validation commands and results:

```sh
/usr/bin/python3 tools/gen_compat.py
```
Output: `0 aliases over 0 functions, 111 event constants (111 mapped) -> compat_aliases.inc, compat_events.inc, docs/api-dialects.md`

```sh
/usr/bin/python3 tools/nwscript_boundary_test.py --self-test
```
Output: `NWScript boundary pattern self-test: 23 forbidden and 7 allowed forms passed`

```sh
/usr/bin/python3 - <<'CHECK'
import tomllib
from pathlib import Path
with Path('data/hostapi.toml').open('rb') as f: data=tomllib.load(f)
trace=next(f for f in data['function'] if f['lua_name']=='nwscript.last_trace')
assert trace['returns']=='table or nil'
assert all(t in trace['doc'] for t in ['GetFacing', 'routine 28', 'nil', 'argument-count', 'not a receipt'])
assert 'or nil before a trace exists' in Path('docs/api-dialects.md').read_text()
print('last_trace nullable metadata and generated scope checks passed')
CHECK
```
Output: `last_trace nullable metadata and generated scope checks passed`

```sh
/usr/bin/python3 tools/nwscript_boundary_test.py
git diff --check
```
Output: `NWScript bounded lexical receipt: checked 276 active files; 0 covered dotted, bracket, rawget, single-target alias, or comma-assignment receiver paths on kotor/_G-kotor receivers, or literal routine calls/rawget on kp/nwscript`
Whitespace check exited 0 with no output.

# Scenario TOML contract

A route records execution policy, materialized resources, and ordered steps.
Replay reads it without modification. Operator paths and listener options belong
to the separate [driver contract](harness-driver.md).

```toml
schema_version = 1
name = "K1 smoke"
target = "k1"

[execution]
game_speed = 16.0
load_timeout = 300

[[step]]
do = "load_checkpoint"
name = "endar_room3"

[[step]]
wait = "phase"
equals = "gameplay"
timeout = 300

[[step]]
do = "quit"
```

`schema_version` is the integer 1. Omission selects the supported legacy form.
`name` is a non-empty string, defaulting to the filename stem. `target` is
`k1`, `k2-wine`, or `k2-native`; the existing `k2` alias normalizes to `k2-native`.
Unknown top-level fields are rejected. Replay requires at least one `[[step]]`;
Pioneer permits an empty step array while authoring but applies every other
header/resource validation rule.

## Execution policy

`[execution]` overrides only the built-in defaults below. Legacy `[settings]`
normalizes to the same execution model. Declaring both is an error, even if one
is empty. Unknown settings are errors. Numbers must be finite and non-negative;
`game_speed` additionally must be greater than zero and at most 16. Booleans are
not numbers. `authored_barks` is an array of integer dialog entry IDs.

| Key | Default | Meaning |
| --- | --- | --- |
| `game_speed` | 16 | Requested simulation speed before the first step |
| `authored_barks` | `[]` | Tutorial dialog entries whose terminator reply may be answered during unrelated waits |
| `default_timeout` | 120 | Ordinary step ceiling in seconds |
| `load_timeout` | 300 | Load step ceiling in seconds |
| `events_timeout` | 60 | Expected-event ceiling in seconds |
| `hang_seconds` | 20 | Frozen tick watchdog threshold |
| `dialog_grace` | 10 | Dialog driver grace before intervention |
| `load_seconds` | 300 | Loading watchdog threshold |
| `load_tick_seconds` | 60 | Loading tick watchdog threshold |
| `stagnation_seconds` | 120 | Progress stagnation watchdog threshold |
| `shot_interval` | 120 | Periodic screenshot interval; zero disables periodic shots |

Per-step timeouts retain their existing precedence over execution defaults.
Header normalization creates fresh settings and bark arrays for each scenario.

## Resources

Resources are named top-level tables, independent of step order:

```toml
[resources.endar_walkmesh]
kind = "walkmesh"
source = "data/models.bif/m01aa_01a.wok"
file = "harness-resources/m01aa_01a.wok"
size = 26404
sha256 = "afd30f4154e5761bcd41223bc000b21422650928c7a5e56691bc2dffad4c88ba"
```

All five fields are required, and unknown resource fields are rejected.
`walkmesh` is the currently implemented resource kind. `source` is a relative
POSIX `container/resource.wok` path for extraction from the selected install.
`file` is a relative POSIX path under the staged game's `harness-resources/`.
Absolute paths, parent traversal, Windows drive/backslash paths are rejected.
`size` is a non-negative integer (not a boolean); `sha256` is exactly 64 hex digits
and normalizes to lowercase. Conflicting declarations for the same output file
fail during parsing, before boot. The driver stages all declared resources,
including declarations not referenced by a step.

A `door_transaction` names `resource = "endar_walkmesh"`. Its route geometry
(`walkmesh_face`, `walkmesh_path`, `walkmesh_approach_face`, centroids, destination,
and tolerances) stays on the step because it describes this particular action.
See [the complete Endar door route](../scripts/harness/scenarios/k1_endar_door01.toml).
The runner verifies the artifact's bytes and the connected walkmesh geometry
before queueing the same ordinary door/movement actions as before.

Legacy inline `walkmesh_resource`, `walkmesh_file`, `walkmesh_size`, and
`walkmesh_sha256` are accepted together and normalize into the typed resource
collection plus a step reference. Partial declarations and combining inline
fields with `resource` are errors. Duplicate identical artifacts are reused.
Unknown references fail parsing. No serialized legacy route is rewritten.

## Steps and discovery

Each `[[step]]` has exactly one action kind: a non-empty string `do` or `wait`,
an array of event names or match tables `expect_events`, or `screenshot = true`. `screenshot` must
be a boolean. Step-specific fields retain their existing verb semantics;
this format change does not impose a new catalog of all verb arguments.
`label` is optional. Actions use engine requests; waits observe independent
state predicates. `expect_error`, `expect_verdict`, unsupported-command skips,
dialog guards, and event sequencing retain their existing behavior.

See [scenario.py](../scripts/harness/kpharness/scenario.py) for the implemented
verb/wait list and [user examples](user/harness.md) for their operation. Lua chunks
use `nwscript.call` for engine routines and `kp.*` for native host facilities.

## Pioneer TAS transport

Ren'Py-like transport verbs share the same `do` dispatch as replay:

| Verb | Meaning |
|---|---|
| `pause` | Near-freeze via harness `speed` (default `scale = 0.001`; engine rejects 0) |
| `play` | `speed` 1x + best-effort `clear_auto_pause` / `unpause_timers` |
| `ff` | Fast-forward (`scale` default 4, max 16) |
| `rewind` | Restore named checkpoint + `load_save` |

```sh
kpharness pioneer pause  --target k1
kpharness pioneer play   --target k1
kpharness pioneer ff     --target k1 --scale 8
kpharness pioneer rewind --target k1 --checkpoint endar_start
# With --out ROUTE.toml the action is also held as a pending pioneered step.
```

The parser accepts ordinary TOML and the existing semicolon shorthand outside
strings/comments. Discovery recursively lists every `scenarios/**/*.toml`,
including `cursed/`. List output preserves the relative nested name, so
`cursed/10_rancor_roulette` resolves unambiguously; direct nested filesystem paths
also work. Every shipped route is loaded by the offline CTest gate. Successful
parsing proves configuration compatibility, not live gameplay behavior.

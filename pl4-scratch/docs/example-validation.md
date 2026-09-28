# Lua example validation

The original **41 Lua sources remain regression obligations**; they are not a
public showcase count. Eight retired public examples now live under
`tools/tests/examples/fixtures/legacy/`; 33 sources remain in their original
locations. The schema-2 `tools/tests/examples/manifest.json` preserves each
original `path` identity and records its current repository-relative
`source_path`, disposition and SHA-256 hash. Each
entry records a host tier, a syntax requirement, an explicit live status,
required live predicates and unmet preconditions. Moving, editing, adding or removing an
inventoried Lua file requires reviewing that entry and updating its source hash.
Do not automatically accept inventory changes or copy old pass flags.

Run from the repository root after building the native tools:

```sh
/usr/bin/python3 tools/example_validation.py \
  --host /absolute/build/kp_luatest \
  --receipt /absolute/build/example-validation.json
ctest --test-dir /absolute/build -R example_validation --output-on-failure
```

The gate compiles all 41 files using LuaJIT without executing their top-level
code during syntax validation. It then executes the actual scripts in fresh
Lua environments. Tests resolve stable example IDs through a validated source map. Retired
fixtures execute the same source bytes and behavioral cases as before. Unexpected NW routine names fail even if the script catches the
error; literal calls are also checked against the generated K1 catalog. Native
functions such as `kp.registertimer` are not NW routines.

The generated receipt contains explicit syntax/host/live results for every
original identity and current source path, retirement counts, named behavioral cases, complete command output, source hashes, test and
manifest hashes, the real host executable hash, Git HEAD and a dirty-diff hash.
It is written atomically only when every assertion passes. An earlier receipt
is stale whenever its source or test hashes differ from current bytes; a failed
run does not turn a retained receipt into a new pass.

| Files | Host evidence | What it does not establish |
|---|---|---|
| Six arbitration and three edge fixtures | real Lua host output assertions, ordering/coercion/fallback and fourth-call quarantine suppression | engine hooks are outside these host contracts |
| Ten cursed, six showcase, two probes, coverage director | controlled backend decision, request, caller, timer, persistence and negative branch assertions | engine event arrival, actual effects/actions/audio/rendering/timer clocks |
| Eleven harness snippets | returned world shapes and configured request arguments/caller; missing target and empty world cases | live engine truth or action completion; edited local configuration branches are identified by case name |
| Two multiplayer files | existing assertion-based LuaJIT framing/socket/engine mock regression | generated UTC acceptance or real sockets between game clients |

The fixture's successful `ApplyEffectToObject` returns **zero values**, matching
the bridge's void semantics. A counted protected call is a successful request;
independent engine effect inspection remains necessary. Timers are captured
and explicitly invoked without sleeping. The test environment does not emulate
the engine or export NW routines beneath native `kp`.

Coverage includes all ten chaos choices, cursed arming at 200 ticks,
conversation rejection, timer caller targets, party and invalid-object guards,
meditation absent/dead/nonparty Bastila and void calls, retry failures,
showcase sidecar reload, probe abstention/throttling, coverage command parsing,
and harness inspect/action configurations. This is bounded branch coverage;
it is not an assertion that every possible routine failure or malformed engine
value is exhaustively tested.

## Public curation and historical evidence

The six former text/buff showcase scripts and cursed rave/chaos are retired
from the public tree and default recording/deployment. Their exact Lua bytes,
host cases and open live obligations remain internal. Retirement never means
live passed or not applicable. The [scene catalog](../scripts/demos/catalog.json)
separates native candidates from regression sources; this migration promotes no
candidate to featured. Historical evidence still uses original `path` IDs,
including `showcase/...`, while readers use `source_path` for file access.

Run the complete Python validator above; it supplies the validated source map
to the Lua suites. Direct `tools/tests/examples/run.lua` invocation now requires
that map argument. Inventory checks reject escaped/symlinked paths, unexpected
Lua files, stale hashes and restored public copies of retired sources. Reports
show original regression counts and public retirements separately.

## Current live acceptance

All **31 engine-dependent files** begin **unvalidated**. The nine real-host
fixtures and the standalone multiplayer regression are **10 host-only files**
whose live tier is `not_applicable`. The production multiplayer script retains
its separate real two-game obligations. September 16 recordings and oracle
logs lacked current-source hashes and cannot supply a current pass. In
particular, the retained coverage attempt had no oracle lines; the documented
`end_m01ab/from_01a` transition did not reach its target; meditation's historical
`steadied 0` lines did not establish buffs. An isolated environment preflight
only establishes that a game can boot into a measured state.

To attach fresh evidence, create a JSON list and pass `--live-evidence FILE`.
Each entry must have this shape. Use each manifest entry's exact
`live.required_predicates` IDs as the `predicates` keys; the corresponding
`live.predicate_obligations` text defines the independently observed outcome.
Every required ID must be true; a missing outcome prevents promotion. These
checklists separately identify requests, engine results and guard behavior:

```json
{
  "schema": 1,
  "path": "showcase/30_battle_meditation.lua",
  "source_sha256": "current manifest hash",
  "deployed_sha256": "independently hashed staged Lua file",
  "run_id": "unique session identity",
  "started_utc": "ISO-8601 start",
  "completed_utc": "ISO-8601 completion",
  "checkpoint": "save identity and hash",
  "runtime_sha256": "deployed runtime hash",
  "git_commit": "source commit",
  "dirty_diff_sha256": "source changes hash",
  "clean_session": true,
  "predicates": {"each exact required predicate ID": true},
  "artifacts": [{"path": "/absolute/report.json", "sha256": "artifact hash"}]
}
```

The importer rejects stale or missing source/deployment hashes, missing
predicates, unclean sessions and missing/changed artifacts. It checks evidence
structure and provenance, not whether an observation was honestly measured.
A reviewer must inspect the state predicates and recordings. Never infer a
live pass from a request result, script counter, screenshot, or oracle alone.
For a configured snippet, retain the original manifest hash as `source_sha256`.
Add `configured_sha256`, set `deployed_sha256` to that effective-source hash,
and attach a `configuration` object with four `{path, sha256}` artifacts:
`artifact` (configuration JSON), `diff` (exact generated unified diff),
`effective_source` (generated Lua), and `deployed_source` (an independently
captured copy of the actual deployed Lua). All artifact paths are absolute.
The importer derives the effective bytes from the hash-checked stock source and
reviewed configuration values, then compares the diff, effective artifact,
deployment artifact and declared hashes. A rehashed unrelated edit still fails.

Configuration JSON for the documented transition is:

```json
{
  "schema": 1,
  "path": "harness/100_module_transition.lua",
  "values": {"INSPECT": false}
}
```

Generate the reviewed effective source and diff with
`tools.example_configuration.effective_source(entry, stock_bytes, configuration)`
from the repository root. The return values are `(effective_bytes, diff_bytes)`.
`entry` is the matching checked manifest entry. Store these bytes exactly and
hash the retained files. Deploy the effective Lua in the isolated live session;
after deployment capture its bytes independently. Original and effective
hashes must not be substituted for each other.

The finite transformation allowlist changes only documented local constants:

| Example | Reviewed fields |
|---|---|
| world probe | `RADIUS` |
| dialog state | `PARTNER_TAG` |
| move | `TARGET_TAG` (tag or null), `RANGE`, `OFFSET` with exactly x/y/z |
| attack | `RADIUS` |
| doors | `TAG`, `OPEN` |
| area dump | `OBJECT_TYPE`, `MAX` |
| signal event | `TARGET`, `EVENT` |
| run script | `SCRIPT`, `TARGET_TAG` (tag or null) |
| transition | `DOOR_TAG`, `MODULE`, `WAYPOINT`, `INSPECT` |
| loot | `TAG` |
| production multiplayer | `LOCAL_NAME`, `LISTEN_PORT`, `PEERS` |

Tags contain up to64 ASCII letters/digits/underscores; resrefs up to16. Radii
are0..250, offset coordinates -1000..1000, dump limits1..1000, event IDs0..255,
and object types are the documented1/2/4/8/32/64 values. Multiplayer accepts
up to3 distinct IPv4 host/port peers, ports1..65535 and a bounded printable
player name. Unknown fields, wrong types, injected Lua and source declaration
drift fail closed. A value outside those reviewed bounds needs a separately
reviewed allowlist change; an arbitrary patch is never an accepted configuration.

For a controlled one-game peer, the reviewed production multiplayer values can
be `{"LOCAL_NAME":"Validation Peer","LISTEN_PORT":39131,"PEERS":[{"host":"127.0.0.1","port":39132}]}`.
That configuration does not relax its `two_game_clients` live obligation.
Retain observed socket/template/actor results as partial evidence; do not mark
the production script fully passed until all its required outcomes are met.

## Reproduced defects and intentional boundaries

The suite reproduced and corrected meditation's void count and missing/nonparty
Bastila acceptance, coverage invalid-target dispatch, missing-position loot
retry poisoning, unrelated-owner item deduplication, failed-clock permanent
push suppression, failed-disguise copy counting, dead-PC rave startup and a
transient missing-PC chain-reaction retry. The catalog audit also corrected
native timers being called as NW routines and seven misspelled conversation
queries.

Death scripts intentionally match broad `*dead*`/`*death*` names as documented.
The position probe uses the NWScript integer validity contract; a mock boolean
is not grounds for changing it. Rave retains one inert polling timer while no
valid gameplay PC exists; module cancellation/restart behavior needs real
runtime evidence. Wounded warnings last for the Lua-state/object lifetime.
Ambient barks do not select a named speaker. These limits remain explicit and
are not silently changed into stronger gameplay promises.

Custom showcase `SpeakString` lines are speech/text operations. Their live
checklists require observed text delivery and caller identity, not invented
voiced audio. Rave's explicit battle-music operation retains its audio outcome.

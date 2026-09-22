# Lua example validation

There are exactly **41 shipped Lua files**. The checked
`tools/tests/examples/manifest.json` fixes their paths and SHA-256 hashes. Each
entry records a host tier, a syntax requirement, an explicit live status,
required live predicates and unmet preconditions. Editing, adding or removing a
shipped Lua file requires reviewing that entry and updating its source hash.
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
Lua environments. Tests live outside `scripts/examples`, preserving the exact
inventory. Unexpected NW routine names fail even if the script catches the
error; literal calls are also checked against the generated K1 catalog. Native
functions such as `kp.registertimer` are not NW routines.

The generated receipt contains explicit syntax/host/live results for every
file, named behavioral cases, complete command output, source hashes, test and
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

## Current live acceptance

All 32 engine-dependent files begin **unvalidated**. Nine real-host-only files
are `not_applicable` for the engine tier. September 16 recordings and oracle
logs lacked current-source hashes and cannot supply a current pass. In
particular, the retained coverage attempt had no oracle lines; the documented
`end_m01ab/from_01a` transition did not reach its target; meditation's historical
`steadied 0` lines did not establish buffs. An isolated environment preflight
only establishes that a game can boot into a measured state.

To attach fresh evidence, create a JSON list and pass `--live-evidence FILE`.
Each entry must have this shape (use each manifest entry's exact predicate
strings as the `predicates` keys):

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
  "predicates": {"each exact required predicate": true},
  "artifacts": [{"path": "/absolute/report.json", "sha256": "artifact hash"}]
}
```

The importer rejects stale or missing source/deployment hashes, missing
predicates, unclean sessions and missing/changed artifacts. It checks evidence
structure and provenance, not whether an observation was honestly measured.
A reviewer must inspect the state predicates and recordings. Never infer a
live pass from a request result, script counter, screenshot, or oracle alone.
Record the exact configuration when changing `INSPECT`, `OPEN` or targets in
harness snippets; a configured-source hash must be retained alongside the
original-source hash and configuration change. The stock inspect-mode source
hash alone does not prove the configured transition executed.

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

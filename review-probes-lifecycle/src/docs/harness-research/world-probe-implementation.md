# World probe implementation

This is an offline-verified observation foundation, not live game proof.

`kpharness.world.observe_world` sends one bounded `lua` command, which the
harness executes on its existing main-thread drain. The Lua uses the generated
K1/K2 routines `GetModuleName() -> string`, `GetFirstPC() -> object`,
`GetArea(object) -> object`, `GetFirstObjectInArea(object, int) -> object`,
`GetNextObjectInArea(object, int) -> object`, `GetIsObjectValid(object) -> int`,
`GetObjectType(object) -> int`, `GetTag(object) -> string`, and
`GetPosition(object) -> vector`. Creatures add current/max HP and dead state;
doors and placeables add locked/open state; creatures, placeables, and stores
receive a separately bounded inventory walk. Inventory records are flat at the
snapshot root so their tables remain below the harness serializer's depth-four
cutoff.

Area and inventory walks share a work budget (default 1024, hard ceiling 2048),
stop at caller limits, and reject repeated IDs. The measured 221-area-object,
156-inventory-item snapshot consumes well under the default. The
snapshot reports `truncated`, `errors`, and invalid-object counts. A missing PC
or area is an error. Python consumes the real `Channel.lua` shape,
`{"values": [snapshot]}`, validates identities and object rows, and fails on a
malformed envelope.

Tags and module names strip trailing NUL bytes for matching while retaining the
engine values in `tag_raw` and `module_raw`. IDs and object types reject
booleans, non-finite/fractional values, out-of-range values, and
`OBJECT_INVALID` (`0x7f000000`). Positions, work accounting, errors, PC
metadata, and nested container shapes are validated before use.

Selection requires exactly one matching tag and optional object type. Distance,
target-death, and door-change predicates return false when the target is absent,
ambiguous, lacks required observations, or came from a truncated area walk. No
routine in the probe queues an action or writes game state.

Offline fake-channel coverage is in `tools/kpharness_world_test.py`; it covers
the response envelope, caller bounds/truncation, malformed and invalid object
rows, missing and ambiguous targets, and fail-closed predicates.

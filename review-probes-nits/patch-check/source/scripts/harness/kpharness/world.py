"""Bounded, read-only world observations through the harness Lua command."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Sequence

from .client import Channel


class WorldProbeError(RuntimeError):
    pass


# Odyssey exposes the idle action as either 0 or its unsigned-16-bit invalid
# sentinel (0xfffe).  The latter was measured after the completed K1 Endar
# door transaction: the selected door was open and the PC was exactly at the
# far-side walkmesh centroid, while GetCurrentAction returned 65534.  Treating
# only zero as idle makes a completed action look like a softlock.
IDLE_ACTIONS = frozenset((0, 0xfffe))


def _lua_probe_code(max_objects: int, max_inventory: int, max_work: int,
                    facing_ids: Sequence[int] = ()) -> str:
    # This is a membership set consumed as FACING[object], not a Lua array.
    # `{71}` gives the value key 1, silently skipping object id 71; emit
    # explicit numeric keys so high-bit Odyssey object IDs also round-trip.
    wanted_facing = "{" + ",".join(f"[{i}]=true" for i in facing_ids) + "}"
    return f"""
local MAX_OBJECTS, MAX_INVENTORY, MAX_WORK = {max_objects}, {max_inventory}, {max_work}
local FACING = {wanted_facing}
local ALL, CREATURE, DOOR, PLACEABLE, STORE = 32767, 1, 8, 64, 128
local work = 0
local function spend()
  if work >= MAX_WORK then return false end
  work = work + 1
  return true
end
local function valid(o) return o ~= nil and nwscript.call(\"GetIsObjectValid\",o) == 1 end
local function tagged(o)
  local raw = nwscript.call(\"GetTag\",o)
  return string.gsub(raw, "%z+$", ""), raw
end
local function pos(o)
  local p = nwscript.call(\"GetPosition\",o)
  return {{x=p.x, y=p.y, z=p.z}}
end
local function inventory(owner, flat)
  local seen, count = {{}}, 0
  if not spend() then return count, true, "observation work budget exhausted" end
  local item = nwscript.call(\"GetFirstItemInInventory\",owner)
  while valid(item) and count < MAX_INVENTORY do
    if seen[item] then
      return count, true, "repeated inventory object id"
    end
    seen[item] = true
    count = count + 1
    local tag, raw_tag = tagged(item)
    flat[#flat + 1] = {{owner_id=owner, id=item, tag=tag, tag_raw=raw_tag,
                        type=nwscript.call(\"GetObjectType\",item)}}
    if not spend() then return count, true, "observation work budget exhausted" end
    item = nwscript.call(\"GetNextItemInInventory\",owner)
  end
  return count, valid(item), valid(item) and "inventory limit reached" or nil
end

local module_raw, pc = nwscript.call(\"GetModuleFileName\"), nwscript.call(\"GetFirstPC\")
local module = string.gsub(module_raw, "%z+$", "")
if not valid(pc) then error("world probe: no valid first PC") end
local area = nwscript.call(\"GetArea\",pc)
if not valid(area) then error("world probe: PC has no valid area") end

local pc_tag, pc_raw_tag = tagged(pc)
local area_tag, area_raw_tag = tagged(area)
local out = {{module=module, module_raw=module_raw,
             pc={{id=pc, tag=pc_tag, tag_raw=pc_raw_tag, type=nwscript.call(\"GetObjectType\",pc), position=pos(pc),
                 current_action=nwscript.call(\"GetCurrentAction\",pc), in_combat=nwscript.call(\"GetIsInCombat\",pc) == 1}},
             area={{id=area, tag=area_tag, tag_raw=area_raw_tag}}, objects={{}}, inventory={{}}, truncated=false,
             errors={{}}, invalid_objects=0, work_limit=MAX_WORK, work_used=0}}
local seen = {{}}
local object = nil
if spend() then object = nwscript.call(\"GetFirstObjectInArea\",area, ALL)
else out.truncated = true; out.errors[#out.errors + 1] = "observation work budget exhausted" end
while valid(object) and #out.objects < MAX_OBJECTS do
  if seen[object] then
    out.truncated = true
    out.errors[#out.errors + 1] = "repeated area object id"
    break
  end
  seen[object] = true
  local kind = nwscript.call(\"GetObjectType\",object)
  local tag, raw_tag = tagged(object)
  local row = {{id=object, tag=tag, tag_raw=raw_tag, type=kind, position=pos(object)}}
  if kind == DOOR and FACING[object] then row.facing = nwscript.call(\"GetFacing\",object) end
  if kind == CREATURE then
    row.hp = nwscript.call(\"GetCurrentHitPoints\",object)
    row.max_hp = nwscript.call(\"GetMaxHitPoints\",object)
    row.dead = nwscript.call(\"GetIsDead\",object) == 1
  elseif kind == DOOR or kind == PLACEABLE then
    row.locked = nwscript.call(\"GetLocked\",object) == 1
    row.open = nwscript.call(\"GetIsOpen\",object) == 1
  end
  if kind == CREATURE or kind == PLACEABLE or kind == STORE then
    local why
    row.inventory_count, row.inventory_truncated, why = inventory(object, out.inventory)
    if why then out.errors[#out.errors + 1] = tostring(object) .. ": " .. why end
  end
  out.objects[#out.objects + 1] = row
  if not spend() then
    out.truncated = true
    out.errors[#out.errors + 1] = "observation work budget exhausted"
    break
  end
  object = nwscript.call(\"GetNextObjectInArea\",area, ALL)
end
if valid(object) and not out.truncated then
  out.truncated = true
  out.errors[#out.errors + 1] = "area object limit reached"
elseif object ~= nil then
  out.invalid_objects = out.invalid_objects + 1
end
out.work_used = work
return out
"""


def _normalise_response(response: Any, *, facing_ids: Sequence[int] = ()) -> Dict[str, Any]:
    if not isinstance(response, dict) or not isinstance(response.get("values"), list):
        raise WorldProbeError("lua reply lacks the Channel.lua values envelope")
    values = response["values"]
    if len(values) != 1 or not isinstance(values[0], dict):
        raise WorldProbeError("world probe must return exactly one object")
    world = values[0]
    for key, kind in (("module", str), ("module_raw", str), ("pc", dict), ("area", dict),
                      ("objects", list), ("inventory", list),
                      ("truncated", bool), ("errors", list)):
        if not isinstance(world.get(key), kind):
            raise WorldProbeError(f"world probe field {key!r} is absent or invalid")
    def valid_id(value: Any) -> bool:
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and value == int(value)
                and 0 <= value <= 0xffffffff and value != 0x7f000000)

    def valid_type(value: Any) -> bool:
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and value == int(value)
                and 1 <= value <= 16384 and int(value) & (int(value) - 1) == 0)

    def valid_position(value: Any) -> bool:
        return (isinstance(value, dict) and all(
            not isinstance(value.get(axis), bool)
            and isinstance(value.get(axis), (int, float))
            and math.isfinite(value[axis]) for axis in "xyz"))

    if world["module"] != world["module_raw"].rstrip("\0"):
        raise WorldProbeError("world probe module normalization is inconsistent")
    if (not isinstance(world.get("invalid_objects"), int)
            or isinstance(world["invalid_objects"], bool) or world["invalid_objects"] < 0):
        raise WorldProbeError("world probe invalid_objects is invalid")
    if (not isinstance(world.get("work_used"), int) or isinstance(world["work_used"], bool)
            or not isinstance(world.get("work_limit"), int) or isinstance(world["work_limit"], bool)
            or not 0 <= world["work_used"] <= world["work_limit"]):
        raise WorldProbeError("world probe work accounting is invalid")
    if any(not isinstance(error, str) for error in world["errors"]):
        raise WorldProbeError("world probe errors must be strings")

    for identity in (world["pc"], world["area"]):
        if not valid_id(identity.get("id")) or not isinstance(identity.get("tag"), str):
            raise WorldProbeError("world probe contains an invalid PC/area identity")
    if not valid_type(world["pc"].get("type")) or not valid_position(world["pc"].get("position")):
        raise WorldProbeError("world probe contains invalid PC metadata")
    if (isinstance(world["pc"].get("current_action"), bool)
            or not isinstance(world["pc"].get("current_action"), int)
            or not isinstance(world["pc"].get("in_combat"), bool)):
        raise WorldProbeError("world probe contains invalid PC action metadata")
    for row in world["objects"]:
        if not isinstance(row, dict) or not valid_id(row.get("id")):
            raise WorldProbeError("world probe contains an invalid object row")
        if not isinstance(row.get("tag"), str) or not valid_type(row.get("type")):
            raise WorldProbeError("world probe object lacks tag/type")
        p = row.get("position")
        if not valid_position(p):
            raise WorldProbeError("world probe object lacks a position")
        if "facing" in row and (isinstance(row["facing"], bool)
                                or not isinstance(row["facing"], (int, float))
                                or not math.isfinite(row["facing"])):
            raise WorldProbeError("world probe object has invalid facing")
        if row["id"] in facing_ids and "facing" not in row:
            # Keep this diagnostic bounded to the requested object.  The
            # caller needs enough identity to distinguish a Lua reply shape
            # bug from a wrong target, but never an arbitrary world dump.
            keys = ",".join(sorted(str(key) for key in row.keys()))
            raise WorldProbeError(
                "world probe requested door facing is absent "
                f"(requested_facing_ids={list(facing_ids)!r}, "
                f"row=id={row['id']!r},tag={row['tag']!r},type={row['type']!r},keys=[{keys}])")
    for item in world["inventory"]:
        if (not isinstance(item, dict) or not valid_id(item.get("owner_id"))
                or not valid_id(item.get("id")) or not isinstance(item.get("tag"), str)
                or not valid_type(item.get("type"))):
            raise WorldProbeError("world probe contains an invalid inventory row")
    return world


def observe_world(channel: Channel, *, max_objects: int = 512,
                  max_inventory: int = 128, max_work: int = 1024,
                  facing_ids: Sequence[int] = (),
                  timeout: Optional[float] = None) -> Dict[str, Any]:
    if not isinstance(max_objects, int) or not 1 <= max_objects <= 4096:
        raise ValueError("max_objects must be an integer from 1 through 4096")
    if not isinstance(max_inventory, int) or not 1 <= max_inventory <= 4096:
        raise ValueError("max_inventory must be an integer from 1 through 4096")
    if isinstance(max_work, bool) or not isinstance(max_work, int) or not 1 <= max_work <= 2048:
        raise ValueError("max_work must be an integer from 1 through 2048")
    if isinstance(max_objects, bool) or isinstance(max_inventory, bool):
        raise ValueError("observation limits cannot be booleans")
    if any(isinstance(value, bool) or not isinstance(value, int)
           or not 0 <= value <= 0xffffffff for value in facing_ids):
        raise ValueError("facing_ids must contain unsigned object ids")
    return _normalise_response(channel.lua(
        _lua_probe_code(max_objects, max_inventory, max_work, facing_ids),
        facing_ids=tuple(facing_ids), timeout=timeout), facing_ids=tuple(facing_ids))


def require_complete(world: Dict[str, Any]) -> None:
    if (world.get("truncated") is not False or world.get("errors") != []
            or not isinstance(world.get("objects"), list)):
        raise WorldProbeError("object selection requires a complete world snapshot")


def select_object(world: Dict[str, Any], *, tag: str, object_type: Optional[int] = None) -> Dict[str, Any]:
    require_complete(world)
    tag = tag.rstrip("\0")
    matches = [row for row in world.get("objects", [])
               if isinstance(row, dict) and row.get("tag") == tag
               and (object_type is None or row.get("type") == object_type)]
    if len(matches) != 1:
        reason = "missing" if not matches else "ambiguous"
        raise WorldProbeError(f"{reason} object tag={tag!r} type={object_type!r}")
    return matches[0]


def select_route_object(world: Dict[str, Any], *, module: str, tag: str, object_type: int,
                        position: Sequence[float], tolerance: float = 0.25,
                        occurrence: Optional[int] = None) -> Dict[str, Any]:
    """Resolve one corpus-addressed object from a complete local snapshot.

    A tag alone is deliberately insufficient: later Endar rooms reuse tags.
    ``occurrence`` is only an explicit escape hatch for genuinely coincident
    instances; leaving it out keeps ambiguous route data fail-closed.
    """
    require_complete(world)
    if str(world.get("module") or "").lower() != module.rstrip("\0").lower():
        raise WorldProbeError(f"route object requires module {module!r}, got {world.get('module')!r}")
    if (len(position) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                  or not math.isfinite(v) for v in position)):
        raise ValueError("position must contain three finite numbers")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number")
    if occurrence is not None and (isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0):
        raise ValueError("occurrence must be a non-negative integer")
    wanted = tuple(float(v) for v in position)
    matches = [row for row in world["objects"]
               if isinstance(row, dict) and row.get("tag") == tag.rstrip("\0")
               and row.get("type") == object_type
               and math.dist(tuple(row["position"][axis] for axis in "xyz"), wanted) <= tolerance]
    if occurrence is None:
        if len(matches) != 1:
            raise WorldProbeError("missing" if not matches else
                                  f"ambiguous route object tag={tag!r} type={object_type!r}; specify occurrence")
        return matches[0]
    if occurrence >= len(matches):
        raise WorldProbeError(f"missing route object tag={tag!r} type={object_type!r} occurrence={occurrence}")
    return matches[occurrence]


def revalidate_route_object(world: Dict[str, Any], selected: Dict[str, Any], *, module: str,
                            tag: str, object_type: int, position: Sequence[float],
                            tolerance: float = 0.25, occurrence: Optional[int] = None) -> Dict[str, Any]:
    """Return the same selected route object, or reject an id reuse/update."""
    current = select_route_object(world, module=module, tag=tag, object_type=object_type,
                                  position=position, tolerance=tolerance, occurrence=occurrence)
    if current.get("id") != selected.get("id"):
        raise WorldProbeError("selected route object id changed after action queue")
    return current


def stable_gameplay(state: Dict[str, Any], world: Dict[str, Any],
                    previous_state: Optional[Dict[str, Any]] = None) -> bool:
    """A checkpoint-safe idle boundary, assembled from independent reads."""
    try:
        require_complete(world)
    except WorldProbeError:
        return False
    pc = state.get("pc")
    dialog = state.get("dialog")
    ticks = (state.get("server_tick"), state.get("client_tick"))
    progressed = previous_state is None or all(
        isinstance(previous_state.get(key), int) and not isinstance(previous_state.get(key), bool)
        and state[key] > previous_state[key] for key in ("server_tick", "client_tick"))
    return (state.get("phase") == "gameplay" and isinstance(pc, dict)
            and isinstance(pc.get("id"), int) and not isinstance(pc.get("id"), bool)
            and pc["id"] != 0x7f000000 and world.get("pc", {}).get("id") == pc.get("id")
            and all(isinstance(t, int) and not isinstance(t, bool) and t > 0 for t in ticks)
            and dialog is None and world["pc"].get("current_action") in IDLE_ACTIONS
            and world["pc"].get("in_combat") is False and progressed)


def door_open_unlocked(world: Dict[str, Any], target: Dict[str, Any]) -> bool:
    """Read back the selected instance, never another matching tag."""
    try:
        require_complete(world)
        now = next(row for row in world["objects"] if row.get("id") == target.get("id"))
        return now.get("open") is True and now.get("locked") is False
    except (StopIteration, WorldProbeError):
        return False


def within_distance(tag: str, distance: float, *, object_type: Optional[int] = None) -> Callable[[Dict[str, Any]], bool]:
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance < 0:
        raise ValueError("distance must be a finite non-negative number")
    def predicate(world: Dict[str, Any]) -> bool:
        try:
            target = select_object(world, tag=tag, object_type=object_type)
            a, b = world["pc"]["position"], target["position"]
            return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"])) <= distance
        except (KeyError, TypeError, ValueError, WorldProbeError):
            return False
    return predicate


def within_object_distance(world: Dict[str, Any], target: Dict[str, Any], distance: float) -> bool:
    """Distance to the already-resolved instance, safe when tags repeat."""
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance < 0:
        raise ValueError("distance must be a finite non-negative number")
    try:
        require_complete(world)
        current = next(row for row in world["objects"] if row.get("id") == target.get("id"))
        a, b = world["pc"]["position"], current["position"]
        return math.dist(tuple(a[axis] for axis in "xyz"), tuple(b[axis] for axis in "xyz")) <= distance
    except (KeyError, StopIteration, WorldProbeError):
        return False


def target_dead(tag: str, *, object_type: int = 1) -> Callable[[Dict[str, Any]], bool]:
    def predicate(world: Dict[str, Any]) -> bool:
        try:
            return select_object(world, tag=tag, object_type=object_type).get("dead") is True
        except WorldProbeError:
            return False
    return predicate


def door_changed(before: Dict[str, Any], tag: str, *, object_type: int = 8) -> Callable[[Dict[str, Any]], bool]:
    try:
        old = select_object(before, tag=tag, object_type=object_type)
        expected = (old["locked"], old["open"])
    except (KeyError, WorldProbeError):
        expected = None

    def predicate(world: Dict[str, Any]) -> bool:
        if expected is None:
            return False
        try:
            now = select_object(world, tag=tag, object_type=object_type)
            return (now["locked"], now["open"]) != expected
        except (KeyError, WorldProbeError):
            return False
    return predicate

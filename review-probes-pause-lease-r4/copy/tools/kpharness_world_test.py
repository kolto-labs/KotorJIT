#!/usr/bin/env python3
from __future__ import annotations

import sys
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "harness"))

from kpharness.world import (WorldProbeError, _lua_probe_code, door_changed, observe_world,  # noqa: E402
                             select_object, target_dead, within_distance)


def snapshot(objects=None, **changes):
    value = {
        "module": "end_m01aa", "module_raw": "end_m01aa\0",
        "pc": {"id": 2147483649, "tag": "player",
        "type": 1, "position": {"x": 0, "y": 0, "z": 0},
        "current_action": 65534, "in_combat": False},
        "area": {"id": 3, "tag": "end_m01aa"}, "objects": objects or [], "inventory": [],
        "truncated": False, "errors": [], "invalid_objects": 0,
        "work_used": 377, "work_limit": 1024,
    }
    value.update(changes)
    return value


class FakeChannel:
    def __init__(self, result): self.result, self.calls = result, []
    def lua(self, code, timeout=None, **_):
        self.calls.append((code, timeout))
        return self.result


class WorldProbeTests(unittest.TestCase):
    def test_actual_lua_envelope_and_bounds_are_used(self):
        world = snapshot(truncated=True, errors=["area object limit reached"])
        channel = FakeChannel({"values": [world]})
        self.assertIs(observe_world(channel, max_objects=7, max_inventory=3,
                                    max_work=11, timeout=4), world)
        code, timeout = channel.calls[0]
        self.assertIn("MAX_OBJECTS, MAX_INVENTORY, MAX_WORK = 7, 3, 11", code)
        self.assertIn("repeated area object id", code)
        self.assertEqual(timeout, 4)
        self.assertTrue(world["truncated"])
        with self.assertRaisesRegex(WorldProbeError, "complete"):
            select_object(world, tag="anything")

    def test_bad_serialization_and_invalid_rows_fail_closed(self):
        invalid = {"id": 0x7f000000, "tag": "bad", "type": 1,
                   "position": {"x": 0, "y": 0, "z": 0}}
        bad_type = {"id": 9, "tag": "bad", "type": float("nan"),
                    "position": {"x": 0, "y": 0, "z": 0}}
        cases = ({"objects": []}, {"values": []},
                 {"values": [snapshot([{"id": 1}])]},
                 {"values": [snapshot([invalid])]},
                 {"values": [snapshot([bad_type])]},
                 {"values": [snapshot(pc="table")]},
                 {"values": [snapshot(errors=[{}])]},
                 {"values": [snapshot(invalid_objects=True)]},
                 {"values": [snapshot(pc={"id": 1, "tag": "pc", "type": 1})]})
        for reply in cases:
            with self.subTest(reply=reply), self.assertRaises(WorldProbeError):
                observe_world(FakeChannel(reply))
        with self.assertRaises(ValueError): observe_world(FakeChannel({}), max_objects=0)
        with self.assertRaises(ValueError): observe_world(FakeChannel({}), max_work=True)

    def test_unique_missing_and_ambiguous_selection(self):
        door = {"id": 4, "tag": "door", "type": 8,
                "position": {"x": 3, "y": 4, "z": 0}, "locked": True, "open": False}
        world = snapshot([door])
        self.assertIs(select_object(world, tag="door", object_type=8), door)
        nul_door = dict(door, tag="door", tag_raw="door\0")
        self.assertIs(select_object(snapshot([nul_door]), tag="door\0", object_type=8), nul_door)
        with self.assertRaisesRegex(WorldProbeError, "missing"):
            select_object(world, tag="nope")
        with self.assertRaisesRegex(WorldProbeError, "ambiguous"):
            select_object(snapshot([door, dict(door, id=5)]), tag="door", object_type=8)

    def test_predicates_require_complete_unambiguous_data(self):
        creature = {"id": 7, "tag": "sith", "type": 1,
                    "position": {"x": 3, "y": 4, "z": 0}, "dead": True}
        door = {"id": 4, "tag": "door", "type": 8,
                "position": {"x": 1, "y": 0, "z": 0}, "locked": True, "open": False}
        before = snapshot([creature, door])
        self.assertTrue(within_distance("sith", 5, object_type=1)(before))
        self.assertTrue(target_dead("sith")(before))
        self.assertTrue(door_changed(before, "door")(snapshot([dict(door, open=True)])))
        self.assertFalse(target_dead("absent")(before))
        self.assertFalse(door_changed(snapshot([]), "door")(before))
        self.assertFalse(within_distance("door", 2)(snapshot([door, dict(door, id=9)])))
        with self.assertRaises(ValueError): within_distance("door", float("nan"))

    def test_snapshot_fits_harness_serializer_depth(self):
        item = {"owner_id": 7, "id": 8, "tag": "medpac", "tag_raw": "medpac\0", "type": 2}
        world = snapshot([], inventory=[item])
        def check(value, depth=0):
            if isinstance(value, (dict, list)):
                self.assertLess(depth, 4, "commands.cpp would serialize this table as 'table'")
                values = value.values() if isinstance(value, dict) else value
                for child in values: check(child, depth + 1)
        check(world)

    def test_emitted_lua_enforces_shared_work_budget(self):
        probe = _lua_probe_code(20, 20, 6)
        stub = r'''
local routines = {}
nwscript = {call = function(name, ...)
  assert(routines[name], "unknown fake routine " .. tostring(name))
  return routines[name](...)
end}
local area_i, inv_i = 0, 0
local objects = {10, 11, 12}
local items = {101, 102, 103, 104, 105, 106}
function routines.GetIsObjectValid(o) return o and o ~= 0x7f000000 and 1 or 0 end
function routines.GetModuleFileName() return "end_m01aa\0" end
function routines.GetFirstPC() return 1 end
function routines.GetArea(_) return 2 end
function routines.GetTag(o) return tostring(o) .. "\0" end
function routines.GetObjectType(o) if o >= 100 then return 2 else return 1 end end
function routines.GetPosition(_) return {x=0, y=0, z=0} end
function routines.GetCurrentAction(_) return 65534 end
function routines.GetIsInCombat(_) return 0 end
function routines.GetCurrentHitPoints(_) return 10 end
function routines.GetMaxHitPoints(_) return 10 end
function routines.GetIsDead(_) return 0 end
function routines.GetFirstObjectInArea(_, _) area_i=1; return objects[area_i] end
function routines.GetNextObjectInArea(_, _) area_i=area_i+1; return objects[area_i] end
function routines.GetFirstItemInInventory(_) inv_i=1; return items[inv_i] end
function routines.GetNextItemInInventory(_) inv_i=inv_i+1; return items[inv_i] end
'''
        script = stub + "\nlocal function probe()\n" + probe + "\nend\n" + r'''
local w = probe()
assert(w.work_used == 6)
assert(w.work_limit == 6)
assert(w.truncated == true)
assert(#w.objects == 1)
assert(#w.inventory == 5)
assert(string.find(table.concat(w.errors, "|"), "work budget exhausted", 1, true))
'''
        result = subprocess.run(["lua", "-"], input=script, text=True,
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

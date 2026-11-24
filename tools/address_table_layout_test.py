#!/usr/bin/env python3
"""Every shipped address table that hooks the VM must also carry its VM layout.

The runtime binds the NWScript VM from the first script the game runs. That
capture reads two struct fields from the per-build table, and
src/runtime/runtime.cpp (the `sites.layout_resolved` block after "vm: %d of 13
stack sites resolved") accepts the table only when both are present:

  vm.wrapper_internal              CVirtualMachine -> CVirtualMachineInternal*
  vm.internal_command_implementer  CVirtualMachineInternal -> command implementer

Each must be kind "field" with a size equal to the pointer width (4 on every
32-bit build shipped today). src/hooks/registry.cpp parse_field_extent marks a
field resolved only when `size` is a nonzero JSON number, and it leaves a
missing `offset` at 0, which is silently wrong for the command implementer. So
this test also demands a numeric offset.

When the layout is missing, capture_vm returns early on every script, logs
nothing, and every routine call fails with "live VM context or command slot is
unavailable". The Steam K1 tables shipped that way after the 22 September
migration (see the Steam K1 VM binding RCA). This test catches it offline.

Three more ways to ship a table that loads but never binds the VM:

  1. Wrong layout *values*. `layout_resolved` has no value check, so a K1 table
     carrying the K2 wrapper offset (0x1c) binds nothing useful. The expected
     values come from the adjudication files the generator reads
     (gen_address_tables.load_overlay), and each build's values must equal its
     game's GOG donor (K1 k1_gog_103, K2 k2_gog_aspyr).
  2. Missing VM stack sites. api::bind_sites (src/api/enginestruct.cpp) refuses
     to bind unless every site it `need(...)`s resolved. The set is parsed from
     that function, not copied here.
  3. A hook pack. runtime.cpp Runtime::resolve reads `hookpack.json` before any
     address table, so a pack in the repo would shadow every table checked
     here. None may be committed; `hookpack_problems` checks a given pack
     against the same rules.

    python3 tools/address_table_layout_test.py
"""
from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDRESSES = ROOT / "data" / "addresses"
MANIFEST = ROOT / "data" / "hooksites.toml"
ENGINESTRUCT = ROOT / "src" / "api" / "enginestruct.cpp"
RUNTIME = ROOT / "src" / "runtime" / "runtime.cpp"
HOOKPACK_FORMAT = "agentdecompile.hookpack/v1"   # registry.cpp AddressTable::parse

LAYOUT_SITES = ("vm.wrapper_internal", "vm.internal_command_implementer")
# 64-bit tables would carry "pointer_size" or a 64-bit format; none ship yet.
POINTER_SIZE = {"pe": 4, "elf": 4, "macho": 4, "elf64": 8}


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def layout_problems(table: dict) -> list[str]:
    """Why the runtime would leave `layout_resolved` false for this table."""
    sites = table.get("sites") or {}
    width = POINTER_SIZE.get(table.get("format") or "pe", 4)
    problems = []
    for name in LAYOUT_SITES:
        s = sites.get(name)
        if not isinstance(s, dict):
            problems.append(f"{name}: absent")
            continue
        if s.get("kind") != "field":
            problems.append(f"{name}: kind {s.get('kind')!r}, want 'field'")
        size = s.get("size")
        if not _is_number(size) or size == 0:
            problems.append(f"{name}: unresolved (size {size!r}, source {s.get('source')!r})")
        elif size != width:
            problems.append(f"{name}: size {size}, want pointer width {width}")
        if not _is_number(s.get("offset")):
            problems.append(f"{name}: offset {s.get('offset')!r} is not a number")
    return problems


def vm_tables() -> list[Path]:
    out = []
    for path in sorted(ADDRESSES.glob("*.json")):
        table = json.loads(path.read_text())
        if "vm.run_script" in (table.get("sites") or {}):
            out.append(path)
    return out


# ---------------------------------------------------------------------------
# 1. Layout values, per game
# ---------------------------------------------------------------------------

# The donor per game. K1 Steam's adjudication restates GOG (its bindings carry
# `evidence.restated_from: data/adjudication/k1_gog_103_harness_bindings.json`),
# and k2_steam_aspyr_vm_bindings.json names `donor.slug`
# TSL__k2_win_gog_aspyr_swkotor2.exe, which is alias k2_gog_aspyr. Only build
# names live here; every offset is read from the adjudication files.
DONOR = {"K1": "k1_gog_103", "K2": "k2_gog_aspyr"}


def _gen():
    """The generator module, imported at call time so its failures are test errors."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import gen_address_tables  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    return gen_address_tables


@functools.cache
def layout_keys() -> dict[str, str]:
    """Site name -> adjudication key ("Class::method"), from hooksites.toml."""
    doc = tomllib.loads(MANIFEST.read_text())
    out = {}
    for site in doc.get("site", []):
        if site.get("name") in LAYOUT_SITES:
            cls, method = site.get("class", "") or "", site["method"]
            out[site["name"]] = f"{cls}::{method}" if cls else method
    return out


def adjudicated_layout(alias: str) -> dict[str, tuple[int, int]]:
    """(offset, size) per layout site, as the generator would bind `alias`."""
    return dict(_adjudicated_layout(alias))


@functools.cache
def _adjudicated_layout(alias: str) -> tuple:
    overlay = _gen().load_overlay(alias)
    out = {}
    for name, key in layout_keys().items():
        row = overlay.get(key)
        if row is not None and row.get("kind") == "field":
            out[name] = (row.get("offset"), row.get("size"))
    return tuple(sorted(out.items()))


def layout_value_problems(table: dict, expected: dict[str, tuple[int, int]]) -> list[str]:
    """Where the table's layout offsets/sizes differ from `expected`."""
    sites = table.get("sites") or {}
    problems = []
    for name in LAYOUT_SITES:
        if name not in expected:
            problems.append(f"{name}: no adjudicated value to check against")
            continue
        s = sites.get(name)
        if not isinstance(s, dict):
            continue   # layout_problems reports absence
        want_off, want_size = expected[name]
        if s.get("offset") != want_off:
            problems.append(f"{name}: offset {s.get('offset')!r}, adjudicated {want_off:#x}")
        if s.get("size") != want_size:
            problems.append(f"{name}: size {s.get('size')!r}, adjudicated {want_size}")
    return problems


# ---------------------------------------------------------------------------
# 2. VM stack sites api::bind_sites needs
# ---------------------------------------------------------------------------

def bind_sites_required() -> list[str]:
    """Site names api::bind_sites refuses to bind without.

    Parsed from the body of `bool bind_sites(` up to its `if (!ok) return
    false;` in src/api/enginestruct.cpp (lines 154-162 on 2026-09-27), so a
    site added there is required here without an edit.
    """
    text = ENGINESTRUCT.read_text()
    start = text.index("bool bind_sites(")
    end = text.index("if (!ok) return false;", start)
    return re.findall(r'need\(\s*s\.\w+\s*,\s*"([^"]+)"\s*\)', text[start:end])


def runtime_vm_lookups() -> set[str]:
    """Names runtime.cpp hands to VmSites via at("...")."""
    return set(re.findall(r'\bat\("([^"]+)"\)', RUNTIME.read_text()))


def _site_resolved(s: dict) -> bool:
    if "_resolved" in s:            # a flattened hook-pack site carries the runtime's flag
        return bool(s["_resolved"])
    addr = s.get("addr")
    # Stricter than the runtime: a null addr that has expected_bytes can still be
    # found at load time by resolve_from_signatures -> find_unique. A shipped
    # table should not depend on that.
    return _is_number(addr) and addr != 0


def stack_site_problems(table: dict, required: list[str]) -> list[str]:
    sites = table.get("sites") or {}
    problems = []
    for name in required:
        s = sites.get(name)
        if not isinstance(s, dict):
            problems.append(f"{name}: absent")
        elif not _site_resolved(s):
            problems.append(f"{name}: unresolved (addr {s.get('addr')!r}, "
                            f"source {s.get('source')!r})")
    return problems


# ---------------------------------------------------------------------------
# 3. Hook packs
# ---------------------------------------------------------------------------

def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                         capture_output=True, check=True)
    return [f for f in out.stdout.decode().split("\0") if f]


def committed_hookpacks() -> list[str]:
    """Repo files the runtime could read as a hook pack.

    runtime.cpp Runtime::resolve reads <game>/scriptforge/hookpack.json,
    $SCRIPTFORGE_HOOKPACK, and $SCRIPTFORGE_ADDRESSES/hookpack.json, and
    registry.cpp AddressTable::parse treats any file whose `format` is the
    hook-pack format as a pack. The harness copies data/addresses into
    <game>/scriptforge/addresses, and SCRIPTFORGE_ADDRESSES may point at it.
    """
    found = [f for f in _tracked_files() if Path(f).name == "hookpack.json"]
    if (ADDRESSES / "hookpack.json").exists():
        found.append(str((ADDRESSES / "hookpack.json").relative_to(ROOT)))
    for path in sorted(ADDRESSES.glob("*.json")):
        try:
            fmt = json.loads(path.read_text()).get("format")
        except (ValueError, AttributeError):
            continue
        if fmt == HOOKPACK_FORMAT:
            found.append(str(path.relative_to(ROOT)))
    return sorted(set(found))


def flatten_hookpack(pack: dict, build: str, overlay: dict | None = None) -> dict:
    """The per-build site view the runtime builds from a hook pack.

    Replicates registry.cpp AddressTable::parse (hook-pack branch),
    pick_instance and merge_overlay. Raises ValueError where the runtime fails
    the load.
    """
    if pack.get("format") != HOOKPACK_FORMAT:
        raise ValueError(f"format {pack.get('format')!r}, want {HOOKPACK_FORMAT!r}")
    sites_in = pack.get("sites")
    if not isinstance(sites_in, dict):
        raise ValueError('hookpack has no "sites" object')
    game = None
    for b in pack.get("binaries") or []:
        if isinstance(b, dict) and b.get("slug") == build:
            game = b.get("game")
            break

    def extent(obj, s):
        if _is_number(obj.get("offset")):
            s["offset"] = int(obj["offset"])
        if _is_number(obj.get("size")):
            s["size"] = int(obj["size"])
        if s["kind"] == "field" and s.get("size"):
            s["_resolved"] = True

    out: dict[str, dict] = {}
    for name, entry in sites_in.items():
        if not isinstance(entry, dict):
            continue
        key = name
        if "adapter_key" in entry:
            k = entry["adapter_key"]
            if not isinstance(k, str) or not k.strip():
                raise ValueError(f"hookpack adapter_key must be a nonempty string: {name}")
            key = k
        if key in out:
            raise ValueError(f"duplicate hookpack runtime key: {key}")
        kind = entry.get("kind")
        s = {"kind": kind if kind in ("detour", "reference", "call", "field") else None,
             "addr": 0, "_resolved": False, "source": "hookpack"}
        extent(entry, s)
        inst = entry.get("instances")
        picked = None
        if isinstance(inst, list) and inst:
            picked = next((r for r in inst if isinstance(r, dict) and r.get("binary") == build),
                          None) if build else inst[0]
        if picked is not None:
            if _is_number(picked.get("addr")):
                s["addr"] = int(picked["addr"])
                s["_resolved"] = s["addr"] != 0
            extent(picked, s)
        out[key] = s

    if overlay is not None:
        osites = overlay.get("sites") or {}
        for key, s in out.items():
            o = osites.get(key)
            if not isinstance(o, dict):
                continue
            if o.get("kind") in ("detour", "reference", "call", "field"):
                s["kind"] = o["kind"]
            oaddr = o.get("addr") if _is_number(o.get("addr")) else 0
            if s["addr"] == 0 and oaddr:
                s["addr"], s["_resolved"] = int(oaddr), True
            osize = o.get("size") if _is_number(o.get("size")) else 0
            if not s.get("size") and osize:
                s["offset"] = int(o["offset"]) if _is_number(o.get("offset")) else 0
                s["size"] = int(osize)
                if s["kind"] == "field":
                    s["_resolved"] = True
        for key, o in osites.items():
            if key not in out and isinstance(o, dict):
                out[key] = dict(o)
        game = game or overlay.get("game")
    return {"format": "pe", "game": game, "build": build, "sites": out}


def table_problems(table: dict, build: str) -> list[str]:
    """Every offline reason the runtime would not bind the VM from `table`."""
    game = table.get("game")
    problems = list(layout_problems(table))
    sites = table.get("sites") or {}
    for name in LAYOUT_SITES:   # a flattened pack field can have size but no resolve
        s = sites.get(name)
        if isinstance(s, dict) and s.get("_resolved") is False and s.get("size"):
            problems.append(f"{name}: runtime leaves it unresolved")
    if game not in DONOR:
        problems.append(f"game {game!r} has no donor build")
    else:
        expected = adjudicated_layout(build) or adjudicated_layout(DONOR[game])
        problems += layout_value_problems(table, expected)
    problems += stack_site_problems(table, bind_sites_required())
    return problems


def hookpack_problems(pack: dict, build: str, overlay: dict | None = None) -> list[str]:
    """Validate a hook pack for `build` against the rules the address tables pass."""
    try:
        table = flatten_hookpack(pack, build, overlay)
    except ValueError as e:
        return [f"runtime rejects the pack: {e}"]
    return table_problems(table, build)


class ShippedTables(unittest.TestCase):
    def test_some_tables_hook_the_vm(self):
        self.assertTrue(vm_tables(), f"no table under {ADDRESSES} has vm.run_script")

    def test_every_vm_table_carries_the_vm_layout(self):
        for path in vm_tables():
            with self.subTest(table=path.name):
                problems = layout_problems(json.loads(path.read_text()))
                self.assertEqual(problems, [],
                                 f"{path.name}: runtime would not bind the VM: "
                                 + "; ".join(problems))

    def test_every_vm_table_carries_its_games_layout_values(self):
        for path in vm_tables():
            table = json.loads(path.read_text())
            alias = path.stem
            with self.subTest(table=path.name):
                own = adjudicated_layout(alias)
                expected = own or adjudicated_layout(DONOR[table["game"]])
                problems = layout_value_problems(table, expected)
                self.assertEqual(problems, [], f"{path.name}: " + "; ".join(problems))

    def test_every_build_agrees_with_its_games_donor(self):
        games = {json.loads(p.read_text())["game"] for p in vm_tables()}
        self.assertEqual(games - DONOR.keys(), set(), "a VM game has no donor build")
        for path in vm_tables():
            table = json.loads(path.read_text())
            donor = adjudicated_layout(DONOR[table["game"]])
            with self.subTest(table=path.name):
                self.assertEqual(sorted(donor), sorted(LAYOUT_SITES),
                                 f"donor {DONOR[table['game']]} lacks an adjudicated layout")
                own = adjudicated_layout(path.stem)
                if own:
                    self.assertEqual(own, donor,
                                     f"{path.stem} adjudication disagrees with donor "
                                     f"{DONOR[table['game']]}")

    def test_k1_derivation_matches_the_disassembly(self):
        # StackPopInteger 0x5d1000 `8b 09` = mov ecx,[ecx] (internal at +0);
        # RunScript `8b 8e d4 03 00 00` = mov ecx,[esi+0x3d4]. Guards the derivation.
        self.assertEqual(adjudicated_layout(DONOR["K1"]),
                         {"vm.wrapper_internal": (0x0, 4),
                          "vm.internal_command_implementer": (0x3d4, 4)})

    def test_bind_sites_set_is_parsed_and_runtime_looks_each_up(self):
        required = bind_sites_required()
        self.assertTrue(required, f"parsed no need(...) sites from {ENGINESTRUCT}")
        missing = set(required) - runtime_vm_lookups()
        self.assertEqual(missing, set(), f"runtime.cpp never looks these up: {sorted(missing)}")

    def test_every_vm_table_resolves_every_bind_sites_site(self):
        required = bind_sites_required()
        for path in vm_tables():
            with self.subTest(table=path.name):
                problems = stack_site_problems(json.loads(path.read_text()), required)
                self.assertEqual(problems, [],
                                 f"{path.name}: api::bind_sites would refuse: "
                                 + "; ".join(problems))

    def test_no_hookpack_is_committed(self):
        self.assertEqual(committed_hookpacks(), [],
                         "a hook pack here shadows every address table (runtime.cpp resolve)")

    def test_every_vm_table_passes_the_full_check(self):
        for path in vm_tables():
            with self.subTest(table=path.name):
                self.assertEqual(table_problems(json.loads(path.read_text()), path.stem), [])


class Predicate(unittest.TestCase):
    """The replica must reject each way the runtime rejects."""

    GOOD = {"kind": "field", "addr": 0, "offset": 0, "size": 4, "source": "adjudicated"}

    def table(self, **over):
        sites = {"vm.run_script": {"kind": "detour", "addr": 1},
                 "vm.wrapper_internal": dict(self.GOOD),
                 "vm.internal_command_implementer": dict(self.GOOD, offset=0x3d4)}
        for name, value in over.items():
            key = name.replace("__", ".")
            if value is None:
                sites.pop(key)
            else:
                sites[key] = value
        return {"format": "pe", "sites": sites}

    def test_complete_layout_passes(self):
        self.assertEqual(layout_problems(self.table()), [])

    def test_absent_field_fails(self):
        self.assertTrue(layout_problems(self.table(vm__wrapper_internal=None)))

    def test_unresolved_field_fails(self):
        unresolved = {"kind": "field", "addr": None, "offset": None, "size": None,
                      "source": "unresolved"}
        self.assertTrue(layout_problems(self.table(vm__internal_command_implementer=unresolved)))

    def test_wrong_kind_fails(self):
        self.assertTrue(layout_problems(
            self.table(vm__wrapper_internal=dict(self.GOOD, kind="reference"))))

    def test_wrong_size_fails(self):
        self.assertTrue(layout_problems(
            self.table(vm__wrapper_internal=dict(self.GOOD, size=8))))

    def test_missing_offset_fails(self):
        field = dict(self.GOOD)
        field.pop("offset")
        self.assertTrue(layout_problems(self.table(vm__internal_command_implementer=field)))


class HookpackHelper(unittest.TestCase):
    """hookpack_problems must pass a correct pack and fail each bad one."""

    BUILD = "k1_gog_103"

    def good_pack(self):
        table = json.loads((ADDRESSES / f"{self.BUILD}.json").read_text())
        sites = {}
        for name, s in table["sites"].items():
            entry = {"kind": s.get("kind")}
            inst = {"binary": self.BUILD, "addr": s.get("addr") or 0}
            if s.get("kind") == "field":
                entry.update(offset=s.get("offset"), size=s.get("size"))
            sites[name] = dict(entry, instances=[inst])
        return {"format": HOOKPACK_FORMAT,
                "binaries": [{"slug": self.BUILD, "game": table["game"]}],
                "sites": sites}

    def test_good_pack_passes(self):
        self.assertEqual(hookpack_problems(self.good_pack(), self.BUILD), [])

    def test_wrong_game_offset_fails(self):
        pack = self.good_pack()
        pack["sites"]["vm.wrapper_internal"]["offset"] = 0x1c
        self.assertTrue(hookpack_problems(pack, self.BUILD))

    def test_wrong_offset_is_not_rescued_by_overlay(self):
        pack = self.good_pack()
        pack["sites"]["vm.wrapper_internal"]["offset"] = 0x1c
        overlay = json.loads((ADDRESSES / f"{self.BUILD}.json").read_text())
        self.assertTrue(hookpack_problems(pack, self.BUILD, overlay))

    def test_missing_stack_site_fails(self):
        pack = self.good_pack()
        del pack["sites"]["vm.stack_pop_object"]
        self.assertTrue(hookpack_problems(pack, self.BUILD))

    def test_instances_for_another_binary_fail(self):
        pack = self.good_pack()
        for s in pack["sites"].values():
            s["instances"][0]["binary"] = "K1__k1_win_gog_swkotor.exe"   # slug, not alias
        self.assertTrue(hookpack_problems(pack, self.BUILD))

    def test_bad_adapter_key_fails(self):
        pack = self.good_pack()
        pack["sites"]["vm.run_script"]["adapter_key"] = "  "
        self.assertTrue(hookpack_problems(pack, self.BUILD))

    def test_duplicate_adapter_key_fails(self):
        pack = self.good_pack()
        pack["sites"]["vm.run_script"]["adapter_key"] = "vm.execute_command"
        self.assertTrue(hookpack_problems(pack, self.BUILD))


class ValuePredicate(unittest.TestCase):
    EXPECTED = {"vm.wrapper_internal": (0x0, 4), "vm.internal_command_implementer": (0x3d4, 4)}

    def test_k2_wrapper_offset_in_k1_fails(self):
        table = {"sites": {"vm.wrapper_internal": {"kind": "field", "offset": 0x1c, "size": 4},
                           "vm.internal_command_implementer":
                               {"kind": "field", "offset": 0x3d4, "size": 4}}}
        self.assertTrue(layout_value_problems(table, self.EXPECTED))

    def test_missing_expectation_fails(self):
        self.assertTrue(layout_value_problems({"sites": {}}, {}))

    def test_null_addr_stack_site_fails(self):
        table = {"sites": {"vm.stack_pop_object": {"kind": "call", "addr": None}}}
        self.assertTrue(stack_site_problems(table, ["vm.stack_pop_object"]))


class RedTemporaryCopy(unittest.TestCase):
    """Exercise the two new table guards against a mutated on-disk copy."""

    def test_k1_wrong_layout_and_missing_required_stack_site_fail(self):
        source = ADDRESSES / "k1_gog_103.json"
        with tempfile.TemporaryDirectory(prefix="kp-layout-red-") as directory:
            copy = Path(directory) / source.name
            table = json.loads(source.read_text())
            table["sites"]["vm.wrapper_internal"]["offset"] = 0x1c
            table["sites"]["vm.stack_pop_object"]["addr"] = None
            copy.write_text(json.dumps(table))
            mutated = json.loads(copy.read_text())

        self.assertTrue(layout_value_problems(mutated, adjudicated_layout("k1_gog_103")))
        self.assertTrue(stack_site_problems(mutated, bind_sites_required()))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=2).result.wasSuccessful() else 1)

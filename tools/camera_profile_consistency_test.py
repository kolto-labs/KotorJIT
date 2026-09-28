#!/usr/bin/env python3
"""kp.camera Stage 1: the C++ profile, the adjudication overlay and the
regenerated K1 GOG address table must agree, and every guard span must match
the reference image when it is present.

Also checks that no kp.camera Lua name duplicates an NWScript routine name.
The image part is skipped, with a message, when the reference is absent.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "src/api/camera_profiles.cpp"
LUA = ROOT / "src/api/camera_lua.cpp"
TABLE = ROOT / "data/addresses/k1_gog_103.json"
OVERLAY = ROOT / "data/adjudication/k1_gog_103_camera_bindings.json"
SHA = "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435"
IMAGE = Path(os.environ.get(
    "KP_K1_GOG_EXE",
    Path.home() / "biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image"))

# address-table site -> (profile label, table key, expected size or None)
FIELDS = {
    "g.app_manager": ("manager_slot", "addr", 4),
    "appmgr.client": ("manager_client", "offset", 4),
    "client.internal": ("client_internal", "offset", 4),
    "client.module": ("internal_module", "offset", 4),
    "client.options": ("internal_options", "offset", 4),
    "client_options.camera_mode": ("options_mode", "offset", 1),
    "client_module.camera": ("module_camera", "offset", 4),
    "camera.active_behavior": ("camera_behavior", "offset", 4),
    "g.camera_style_pending": ("pending_style", "addr", 4),
    "camera_chase.distance": ("dist", "offset", 4),
    "camera_chase.speed": ("speed", "offset", 4),
    "camera_chase.preset_pitch": ("pitch", "offset", 4),
    "camera_chase.height": ("height", "offset", 4),
    "camera_chase.dolly": ("dolly", "offset", 4),
    "camera_chase.base_distance": ("base_distance", "offset", 4),
    "camera_chase.base_view_angle": ("base_view_angle", "offset", 4),
    "camera_chase.style_row": ("style_row", "offset", 4),
    "camera_chase.raw_28_unverified": ("raw_28", "offset", 16),
    "camera_chase.raw_38_unverified": ("raw_38", "offset", 12),
    "camera_chase.raw_50_unverified": ("raw_50", "offset", 12),
}
REFERENCES = {
    "client_module.vtable": "module_vtable",
    "camera.vtable": "camera_vtable",
    "camera_chase.vtable": "chase_vtable",
}


def profile():
    text = PROFILE.read_text()
    labels = {k: int(v, 16) for k, v in re.findall(r"/\*(\w+)\*/\s*(0x[0-9a-fA-F]+)", text)}
    spans = [(int(va, 16), hx) for va, hx in re.findall(r'\{(0x[0-9a-f]+),"([0-9a-f]*)"\}', text)]
    slots = [(int(a, 16), int(b, 16)) for a, b in re.findall(r"\{(0x[0-9a-f]+),(0x[0-9a-f]+)\}", text)]
    return labels, spans, slots


class CameraConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels, cls.spans, cls.slots = profile()
        cls.table = json.loads(TABLE.read_text())
        cls.overlay = json.loads(OVERLAY.read_text())

    def test_profile_parsed(self):
        self.assertEqual(len(self.spans), 31)
        self.assertEqual(len(self.slots), 4)
        self.assertEqual(self.labels["preferred_base"], 0x400000)
        self.assertEqual(self.labels["chase_type_id"], 0x106A)
        for va, hx in self.spans:
            self.assertTrue(0 < len(hx) <= 32 and len(hx) % 2 == 0, hex(va))

    def test_table_matches_profile(self):
        sites = self.table["sites"]
        self.assertEqual(self.table["derived_sha256"], SHA)
        for name, (label, key, size) in FIELDS.items():
            row = sites[name]
            self.assertEqual(row["kind"], "field", name)
            self.assertEqual(row["source"], "adjudicated", name)
            self.assertEqual(row[key], self.labels[label], name)
            self.assertEqual(row["size"], size, name)
            self.assertFalse(row["required"], name)
        for name, label in REFERENCES.items():
            row = sites[name]
            self.assertEqual(row["kind"], "reference", name)
            self.assertEqual(row["addr"], self.labels[label], name)
            self.assertFalse(row["required"], name)

    def test_overlay_records_guards_and_derivations(self):
        derivations = self.overlay["derivations"]
        self.assertEqual(len(derivations), 2)
        self.assertEqual({d["role"] for d in derivations}, {"plan", "independent re-derivation"})
        guards = [(int(g["va"], 16), g["bytes"]) for g in self.overlay["guards"]]
        self.assertEqual(guards, self.spans)
        slots = [(int(s["va"], 16), int(s["target"], 16)) for s in self.overlay["slots"]]
        self.assertEqual(slots, self.slots)
        for b in self.overlay["bindings"]:
            self.assertEqual(b["verdict"], "accept")
            self.assertGreaterEqual(len(b["evidence"]["signals"]), 2, b["name"])
        self.assertEqual(self.overlay["counts"]["accept"], len(self.overlay["bindings"]))

    def test_image_bytes(self):
        if not IMAGE.is_file():
            self.skipTest(f"reference image absent: {IMAGE}")
        data = IMAGE.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), SHA)
        base = self.labels["preferred_base"]
        for va, hx in self.spans:
            off = va - base
            self.assertEqual(data[off:off + len(hx) // 2].hex(), hx, hex(va))
        for va, target in self.slots:
            self.assertEqual(struct.unpack_from("<I", data, va - base)[0], target, hex(va))
        for label in ("module_vtable", "camera_vtable", "chase_vtable"):
            va = self.labels[label]
            self.assertEqual(self.table["sites"][{v: k for k, v in REFERENCES.items()}[label]]
                             ["expected_bytes"], data[va - base:va - base + 16].hex())
        # .data initial value of the pending-style global is -1.
        off = self.labels["pending_style"] - base
        self.assertEqual(struct.unpack_from("<i", data, off)[0], -1)

    def test_lua_names_are_not_routines(self):
        names = set()
        for path in (ROOT / "data/routines").glob("*.json"):
            names.update(r["name"].lower() for r in json.loads(path.read_text())["routines"])
        self.assertGreater(len(names), 700)
        exported = re.findall(r'\{"(\w+)",\w+\}', LUA.read_text())
        self.assertEqual(sorted(exported), ["capabilities", "snapshot"])
        for name in exported:
            self.assertEqual(name, name.lower())
            self.assertNotIn(name.lower(), names)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=2).result.wasSuccessful() else 1)

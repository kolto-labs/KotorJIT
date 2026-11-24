#!/usr/bin/env python3
"""Report signature-binding coverage for every canonical KotOR corpus target."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path


MULTIPLAYER_SIGNATURE_SITES = {
    "net.initialize",
    "net.shutdown",
    "net.send_message_to_player",
    "net.process_received_frames",
    "net.non_window_messages",
    "net.start_server_mode",
    "net.start_connect_to_session",
    "client.area_get_server_area",
    "module.get_area",
    "client_area.attach_from_server",
    "server_area.attach_from_client",
    "creature.add_move_to_point_action",
    "server.get_player_creature_id",
    "server.get_game_object",
    "server_object.set_position",
}

MULTIPLAYER_RESOLVED_SITES = MULTIPLAYER_SIGNATURE_SITES | {
    "g.app_manager",
    "appmgr.server",
    "app.get_module",
    "net.destination_net_layer",
    "object.id",
}


def report(db_path: Path, tables_dir: Path) -> dict[str, object]:
    tables: dict[str, list[dict[str, object]]] = {}
    for path in sorted(tables_dir.glob("*.json")):
        data = json.loads(path.read_text())
        source = data.get("symbol_source")
        if source:
            tables.setdefault(source, []).append(data)

    uri = f"file:{db_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute(
            "SELECT id, slug, game, platform, variant, arch, bits, format, md5, "
            "func_count, named_count FROM binary WHERE game IN ('K1', 'K2') ORDER BY id"
        ).fetchall()

    targets = []
    for row in rows:
        (binary_id, slug, game, platform, variant, arch, bits, image_format,
         md5, func_count, named_count) = row
        bindings = []
        multiplayer_bound = False
        for table in tables.get(slug, []):
            sites = table.get("sites", {})
            signed = {name for name, site in sites.items() if site.get("expected_bytes")}
            resolved_names = {
                name for name, site in sites.items()
                if bool(site.get("resolved", site.get("addr") or site.get("size")))
            }
            resolved = len(resolved_names)
            mp = (MULTIPLAYER_SIGNATURE_SITES <= signed and
                  MULTIPLAYER_RESOLVED_SITES <= resolved_names)
            multiplayer_bound |= mp
            bindings.append({
                "build": table.get("build"),
                "site_count": len(sites),
                "resolved_count": resolved,
                "signature_count": len(signed),
                "multiplayer_sites_bound": mp,
                "sha256": (table.get("identity", {}).get("sha256")
                           or table.get("derived_sha256") or table.get("reference_sha256")),
            })
        state = "multiplayer_bound" if multiplayer_bound else "runtime_bound" if bindings else "unbound"
        targets.append({
            "binary_id": binary_id,
            "slug": slug,
            "game": game,
            "platform": platform,
            "variant": variant,
            "arch": arch,
            "bits": bits,
            "format": image_format,
            "md5": md5,
            "function_count": func_count,
            "named_count": named_count,
            "state": state,
            "bindings": bindings,
        })

    counts = {state: sum(target["state"] == state for target in targets)
              for state in ("multiplayer_bound", "runtime_bound", "unbound")}
    return {
        "schema": "hyperstim.corpus-coverage.v1",
        "required_multiplayer_signature_sites": sorted(MULTIPLAYER_SIGNATURE_SITES),
        "required_multiplayer_resolved_sites": sorted(MULTIPLAYER_RESOLVED_SITES),
        "target_count": len(targets),
        "counts": counts,
        "targets": targets,
    }


def selftest() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        db_path = root / "corpus.sqlite"
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE binary (id INTEGER, slug TEXT, game TEXT, platform TEXT, "
                       "variant TEXT, arch TEXT, bits INTEGER, format TEXT, md5 TEXT, "
                       "func_count INTEGER, named_count INTEGER)")
            db.execute("INSERT INTO binary VALUES (8,'K1__fixture','K1','win','fixture','x86',32,"
                       "'PE','abc',10,9)")
        tables = root / "tables"
        tables.mkdir()
        sites = {name: {"addr": 1, "expected_bytes": "00", "resolved": True}
                 for name in MULTIPLAYER_RESOLVED_SITES}
        (tables / "fixture.json").write_text(json.dumps({
            "build": "fixture", "symbol_source": "K1__fixture", "sites": sites,
        }))
        value = report(db_path, tables)
        assert value["target_count"] == 1
        assert value["counts"] == {"multiplayer_bound": 1, "runtime_bound": 0, "unbound": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    parser.add_argument("--tables", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data" / "addresses")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        print("OK")
        return 0
    if args.db is None:
        parser.error("--db is required unless --selftest is used")
    value = report(args.db, args.tables)
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

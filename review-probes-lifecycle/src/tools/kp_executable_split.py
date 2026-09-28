#!/usr/bin/env python3
"""Create and verify role-labelled client/server artifacts from one known image.

This is the artifact boundary, not multiplayer proof: both outputs initially
retain the source image bytes so KotorPhasor's exact-image and signature checks
still apply.  The manifest says so explicitly until a server bootstrap patch is
implemented and validated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


SCHEMA = "kotorphasor.executable-split.v1"


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def known_build(source: Path, tables: Path) -> tuple[dict[str, object], dict[str, str]]:
    actual = {"sha256": digest(source, "sha256"), "md5": digest(source, "md5")}
    matches: list[dict[str, object]] = []
    for table_path in sorted(tables.glob("*.json")):
        table = json.loads(table_path.read_text())
        identity = dict(table.get("identity", {}))
        expected_sha256 = (identity.get("sha256") or table.get("derived_sha256")
                           or table.get("reference_sha256"))
        if not expected_sha256:
            continue
        identity["sha256"] = expected_sha256
        if all(actual.get(name) == value for name, value in identity.items()):
            matches.append(table)
    if len(matches) != 1:
        names = [str(table.get("build", "?")) for table in matches]
        detail = "unrecognised" if not matches else "ambiguous: " + ", ".join(names)
        raise ValueError(f"source image is {detail} ({actual['sha256']})")
    return matches[0], actual


def role_path(executable: Path) -> Path:
    return executable.with_name(executable.name + ".kotorphasor-role.json")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def split(source: Path, output: Path, tables: Path) -> Path:
    if not source.is_file():
        raise ValueError(f"source is not a regular file: {source}")
    if output.exists():
        raise ValueError(f"output already exists: {output}")

    table, identity = known_build(source, tables)
    build = str(table.get("build"))
    suffix = source.suffix
    stem = source.stem
    if not suffix:
        suffix = ".exe" if table.get("format") in {"pe", "PE"} else ".elf"
        stem = "swkotor2" if str(table.get("game", "")).upper() == "K2" else "swkotor"
    names = {
        "client": f"{stem}-client{suffix}",
        "server": f"{stem}-server{suffix}",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        artifacts = []
        for role, name in names.items():
            target = staging / name
            shutil.copy2(source, target)
            role_record = {
                "schema": SCHEMA,
                "build": build,
                "role": role,
                "source_sha256": identity["sha256"],
                "bootstrap_only": True,
            }
            write_json(role_path(target), role_record)
            artifacts.append({
                "role": role,
                "path": name,
                "role_record": role_path(target).name,
                "sha256": digest(target, "sha256"),
            })

        manifest = {
            "schema": SCHEMA,
            "build": build,
            "source": {
                "path": str(source.resolve()),
                **identity,
            },
            "artifacts": artifacts,
            "runtime_role_selector": "executable-basename",
            "authoritative_server_validated": False,
            "claim_boundary": (
                "Role-labelled exact-image bootstrap artifacts only; this manifest does "
                "not claim cross-process transport or an authoritative server."
            ),
        }
        write_json(staging / "split-manifest.json", manifest)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output / "split-manifest.json"


def verify(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported split manifest schema")
    root = manifest_path.parent
    root_resolved = root.resolve()
    def member(name: str) -> Path:
        candidate = (root / name).resolve()
        if candidate.parent != root_resolved:
            raise ValueError(f"manifest path escapes artifact directory: {name}")
        return candidate
    roles = set()
    source_sha256 = manifest.get("source", {}).get("sha256")
    if not source_sha256:
        raise ValueError("manifest has no source sha256")
    source_path = Path(manifest["source"].get("path", ""))
    if source_path.is_file() and digest(source_path, "sha256") != source_sha256:
        raise ValueError(f"source hash mismatch: {source_path}")
    targets = set()
    for artifact in manifest.get("artifacts", []):
        role = artifact.get("role")
        target = member(artifact["path"])
        record_path = member(artifact["role_record"])
        if target in targets:
            raise ValueError(f"roles share one executable: {target}")
        targets.add(target)
        if digest(target, "sha256") != artifact.get("sha256"):
            raise ValueError(f"artifact hash mismatch: {target}")
        if manifest.get("authoritative_server_validated") is False and artifact.get("sha256") != source_sha256:
            raise ValueError(f"bootstrap artifact differs from source image: {target}")
        record = json.loads(record_path.read_text())
        if record.get("schema") != SCHEMA or record.get("role") != role:
            raise ValueError(f"role record mismatch: {record_path}")
        if record.get("build") != manifest.get("build"):
            raise ValueError(f"build mismatch: {record_path}")
        if record.get("source_sha256") != source_sha256:
            raise ValueError(f"source identity mismatch: {record_path}")
        roles.add(role)
    if roles != {"client", "server"}:
        raise ValueError(f"expected client and server roles, got {sorted(roles)}")


def selftest() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        source = root / "swkotor.exe"
        source.write_bytes(b"MZ" + bytes(range(256)))
        tables = root / "tables"
        tables.mkdir()
        write_json(tables / "fixture.json", {
            "build": "fixture",
            "identity": {"sha256": digest(source, "sha256")},
            "format": "pe",
            "game": "K1",
        })
        manifest = split(source, root / "out", tables)
        verify(manifest)
        server = root / "out" / "swkotor-server.exe"
        server.write_bytes(server.read_bytes() + b"corrupt")
        try:
            verify(manifest)
        except ValueError as error:
            assert "hash mismatch" in str(error)
        else:
            raise AssertionError("verification accepted a modified artifact")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data" / "addresses")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("split")
    create.add_argument("source", type=Path)
    create.add_argument("output", type=Path)
    check = sub.add_parser("verify")
    check.add_argument("manifest", type=Path)
    sub.add_parser("selftest")
    args = parser.parse_args()
    try:
        if args.command == "split":
            print(split(args.source, args.output, args.tables))
        elif args.command == "verify":
            verify(args.manifest)
            print("OK")
        else:
            selftest()
            print("OK")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Package KotorJIT as a KotOR Patch Manager (KPM) DLL-only .kpatch archive."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KPATCH_DIR = ROOT / "kpatch"
HEX64_UPPER = re.compile(r"^[0-9A-F]{64}$")


def validate_kpatch_inputs(manifest_path: Path, hooks_path: Path) -> None:
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    patch = manifest.get("patch")
    if not isinstance(patch, dict):
        raise ValueError("manifest.toml missing [patch] table")
    for field in ("id", "name", "version", "author"):
        val = patch.get(field)
        if not isinstance(val, str) or not val:
            raise ValueError(f"manifest.toml [patch].{field} must be a non-empty string")
    versions = patch.get("supported_versions")
    if not isinstance(versions, dict) or not versions:
        raise ValueError("manifest.toml missing [patch.supported_versions]")
    for ver_name, digest in versions.items():
        if not isinstance(digest, str) or not HEX64_UPPER.match(digest):
            raise ValueError(
                f"supported_versions.{ver_name}={digest!r} must be uppercase 64-char SHA-256"
            )

    hooks = tomllib.loads(hooks_path.read_text(encoding="utf-8"))
    if hooks.get("hooks"):
        raise ValueError("hooks.toml must declare zero [[hooks]] tables for a KPM DLL-only patch")


def collect_binaries(build_dir: Path, mac_build_dir: Path | None) -> dict[str, Path]:
    found: dict[str, Path] = {}
    win_dll = build_dir / "kotorjit.dll"
    if win_dll.is_file():
        found["binaries/windows_x86.dll"] = win_dll
    linux_so = build_dir / "libkotorjit.so"
    if linux_so.is_file():
        found["binaries/linux_x86.so"] = linux_so

    mac_candidates = []
    if mac_build_dir is not None:
        mac_candidates.append(mac_build_dir / "libkotorjit.dylib")
    mac_candidates.extend([
        build_dir / "libkotorjit.dylib",
        ROOT / "build-mac/libkotorjit.dylib",
    ])
    for cand in mac_candidates:
        if cand.is_file():
            found["binaries/macos_x86_64.dylib"] = cand
            break
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("build_dir", nargs="?", type=Path, default=ROOT / "build")
    ap.add_argument("--mac-build-dir", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=ROOT / "dist/kotorjit.kpatch")
    args = ap.parse_args(argv)

    manifest_path = KPATCH_DIR / "manifest.toml"
    hooks_path = KPATCH_DIR / "hooks.toml"
    validate_kpatch_inputs(manifest_path, hooks_path)

    binaries = collect_binaries(args.build_dir, args.mac_build_dir)
    if not binaries:
        print(
            f"package_kpatch: no built runtime libraries found in {args.build_dir} "
            "(build kotorjit.dll, libkotorjit.so, or libkotorjit.dylib first)",
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, "manifest.toml")
        zf.write(hooks_path, "hooks.toml")
        for arcname, src in sorted(binaries.items()):
            zf.write(src, arcname)

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(str(args.output))
    print(f"sha256 {digest}")
    for arcname, src in sorted(binaries.items()):
        print(f"  {arcname} <- {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

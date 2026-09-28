"""Materialize and verify a self-contained Gamescope harness-module snapshot.

The snapshot contains only the Python module closure needed by
``linux-wine-k1-gamescope``. It does not copy a game install, Wine prefix,
built DLL, route, save, or any retail/runtime asset.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = 1
BACKEND = "linux-wine-k1-gamescope"
PACKAGE = "kpharness"
MANIFEST = "gamescope-harness-manifest.json"
RUN_MANIFEST = "gamescope-run-manifest.json"
RUNTIME = "runtime"
DEFAULT_ENTRIES = ("kpharness.creative", "kpharness.gamescope_snapshot")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name("." + path.name + ".tmp-" + os.urandom(8).hex())
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


_SECRET = __import__("re").compile(
    r"(?i)(?:bearer\s+\S+|(?:password|token|secret)\s*[:=]\s*\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"MIT-MAGIC-COOKIE-\d+\s+\S+|xauth\s+add\s+\S+)")


def assert_persistable_evidence(value: object) -> None:
    """Refuse evidence that contains credential-shaped values without echoing it."""
    def walk(current: object) -> None:
        if isinstance(current, str):
            if _SECRET.search(current):
                raise ValueError("persisted evidence contains prohibited secret material")
        elif isinstance(current, dict):
            for key, item in current.items():
                walk(key); walk(item)
        elif isinstance(current, (tuple, list)):
            for item in current:
                walk(item)
    walk(value)


def _module_path(source_root: Path, module: str) -> Path:
    if module == PACKAGE:
        path = source_root / PACKAGE / "__init__.py"
    else:
        if not module.startswith(PACKAGE + "."):
            raise ValueError("not a harness module: " + module)
        path = source_root.joinpath(*module.split(".")).with_suffix(".py")
    if not path.is_file() or path.is_symlink():
        raise ValueError("required Gamescope harness module is missing or linked: " + str(path))
    return path


def _imported_modules(module: str, path: Path) -> set[str]:
    """Return static package imports; dynamic imports in this driver are stdlib-only."""
    result: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE or alias.name.startswith(PACKAGE + "."):
                    result.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".") if package else []
                if node.level > len(base_parts) + 1:
                    continue
                base = ".".join(base_parts[:len(base_parts) - node.level + 1])
                target = (base + "." + node.module).strip(".") if node.module else base
            else:
                target = node.module or ""
            if target == PACKAGE or target.startswith(PACKAGE + "."):
                result.add(target)
                if node.module is None:
                    result.update(target + "." + alias.name for alias in node.names)
    return result


def runtime_module_paths(source_root: Path, entries: Iterable[str] = DEFAULT_ENTRIES) -> list[Path]:
    """Resolve the exact local import closure for the Gamescope driver."""
    source_root = Path(source_root).resolve()
    pending = list(entries)
    seen: set[str] = set()
    files: list[Path] = []
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        path = _module_path(source_root, module)
        seen.add(module)
        files.append(path)
        pending.extend(sorted(_imported_modules(module, path) - seen))
    package_init = _module_path(source_root, PACKAGE)
    if package_init not in files:
        files.append(package_init)
    return sorted(files, key=lambda item: item.relative_to(source_root).as_posix())


def _file_entries(source_root: Path, entries: Iterable[str] = DEFAULT_ENTRIES) -> list[dict[str, str]]:
    source_root = Path(source_root).resolve()
    return [{"path": path.relative_to(source_root).as_posix(), "sha256": _sha256(path)}
            for path in runtime_module_paths(source_root, entries)]


def create_snapshot(source_root: Path, snapshot: Path, *, entries: Iterable[str] = DEFAULT_ENTRIES) -> Path:
    """Copy a stable module closure atomically, refusing a changing source tree."""
    source_root, snapshot = Path(source_root).resolve(), Path(snapshot).resolve()
    if snapshot.exists():
        raise ValueError("refusing existing Gamescope snapshot destination: " + str(snapshot))
    before = _file_entries(source_root, entries)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".gamescope-snapshot-", dir=snapshot.parent))
    try:
        runtime = temporary / RUNTIME
        for entry in before:
            source = source_root / entry["path"]
            destination = runtime / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if _sha256(destination) != entry["sha256"]:
                raise RuntimeError("snapshot copy digest mismatch: " + entry["path"])
        after = _file_entries(source_root, entries)
        if after != before:
            raise RuntimeError("Gamescope harness source changed while snapshotting; refusing mixed snapshot")
        manifest = {"schema": SCHEMA, "backend": BACKEND, "package": PACKAGE,
                    "entrypoint": "kpharness.creative", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "files": before}
        if source_root.name == "harness" and source_root.parent.name == "scripts":
            repository = source_root.parents[1]
            selected = [repository / "tools/kpdiscover.py", repository / "tools/tests/examples/manifest.json",
                        repository / "data/app_signatures.toml", *sorted((repository / "data/addresses").glob("*.json"))]
            manifest["repository_root"] = str(repository)
            manifest["repository_inputs"] = [{"path": str(path), "sha256": _sha256(path)} for path in selected]
        assert_persistable_evidence(manifest)
        _atomic_write(temporary / MANIFEST, _canonical_json(manifest))
        _atomic_write(temporary / (MANIFEST + ".sha256"),
                      (_sha256(temporary / MANIFEST) + "  " + MANIFEST + "\n").encode("ascii"))
        os.replace(temporary, snapshot)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return snapshot


def _load_manifest(snapshot: Path) -> dict:
    manifest_path = snapshot / MANIFEST
    try:
        raw = manifest_path.read_bytes()
        value = json.loads(raw)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid Gamescope snapshot manifest: " + str(manifest_path)) from error
    if raw != _canonical_json(value):
        raise ValueError("Gamescope snapshot manifest is not canonical")
    if value.get("schema") != SCHEMA or value.get("backend") != BACKEND or value.get("package") != PACKAGE:
        raise ValueError("Gamescope snapshot manifest has incompatible identity")
    files = value.get("files")
    if not isinstance(files, list) or not files or files != sorted(files, key=lambda item: item.get("path", "")):
        raise ValueError("Gamescope snapshot manifest has no canonical file list")
    if any(set(item) != {"path", "sha256"} or not isinstance(item["path"], str)
           or Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts
           or len(item["sha256"]) != 64 for item in files):
        raise ValueError("Gamescope snapshot manifest has unsafe file entries")
    digest_file = snapshot / (MANIFEST + ".sha256")
    expected = _sha256(manifest_path) + "  " + MANIFEST + "\n"
    if digest_file.read_text(encoding="ascii") != expected:
        raise ValueError("Gamescope snapshot manifest digest mismatch")
    return value


def verify_snapshot(snapshot: Path, *, source_root: Path | None = None,
                    entries: Iterable[str] = DEFAULT_ENTRIES) -> dict:
    """Verify copied bytes and, when requested, the current source closure too."""
    snapshot = Path(snapshot).resolve()
    manifest = _load_manifest(snapshot)
    for entry in manifest.get("repository_inputs", []):
        path = Path(entry["path"])
        if not path.is_file() or _sha256(path) != entry["sha256"]:
            raise ValueError("Gamescope snapshot repository input changed")
    expected_files = manifest["files"]
    runtime = snapshot / RUNTIME
    for entry in expected_files:
        path = runtime / entry["path"]
        if not path.is_file() or path.is_symlink() or _sha256(path) != entry["sha256"]:
            raise ValueError("Gamescope snapshot module digest mismatch: " + entry["path"])
    actual = []
    if runtime.is_symlink() or not runtime.is_dir():
        raise ValueError("Gamescope snapshot runtime is not a regular directory")
    for path in runtime.rglob("*"):
        if path.is_symlink():
            raise ValueError("Gamescope snapshot contains a prohibited symlink")
        if path.is_file():
            actual.append(path.relative_to(runtime).as_posix())
        elif not path.is_dir():
            raise ValueError("Gamescope snapshot contains an unexpected file type")
    actual.sort()
    listed = [entry["path"] for entry in expected_files]
    if actual != listed:
        raise ValueError("Gamescope snapshot runtime file list differs from manifest")
    if source_root is not None and _file_entries(Path(source_root), entries) != expected_files:
        raise ValueError("Gamescope snapshot source mismatch; create a new snapshot from the selected source")
    return manifest


def runtime_resolution_receipt(snapshot: Path) -> dict:
    """Import every listed module and prove its origin is the sealed runtime."""
    snapshot = Path(snapshot).resolve()
    manifest = verify_snapshot(snapshot)
    runtime = (snapshot / RUNTIME).resolve()
    result = []
    for entry in manifest["files"]:
        module = entry["path"][:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        loaded = importlib.import_module(module)
        origin = Path(str(getattr(loaded, "__file__", ""))).resolve()
        expected = (runtime / entry["path"]).resolve()
        if origin != expected or not origin.is_relative_to(runtime) or _sha256(origin) != entry["sha256"]:
            raise ValueError("Gamescope snapshot import resolved outside manifest closure")
        result.append({"module": module, "path": str(origin), "sha256": entry["sha256"]})
    return {"snapshot": str(snapshot), "interpreter": {"path": str(Path(sys.executable).resolve()),
            "version": sys.version, "sha256": _sha256(Path(sys.executable).resolve())}, "modules": result}


def create_run_manifest(run_dir: Path, *, snapshot: Path, inputs: dict,
                        source: Path, source_before: dict) -> dict:
    """Bind the existing creative input and source-preservation contracts."""
    snapshot = Path(snapshot).resolve()
    value = {"schema": 1, "kind": "gamescope-run-manifest", "backend": BACKEND,
             "snapshot": str(snapshot), "manifest_sha256": _sha256(snapshot / MANIFEST),
             "import_resolution": runtime_resolution_receipt(snapshot),
             "inputs": dict(inputs), "source": str(source), "source_before": source_before,
             "scope": "creative inputs and bounded source-preservation contract"}
    assert_persistable_evidence(value)
    _atomic_write(Path(run_dir) / RUN_MANIFEST, _canonical_json(value))
    return value


def verify_run_manifest(run_dir: Path) -> dict:
    path = Path(run_dir) / RUN_MANIFEST
    raw = path.read_bytes(); value = json.loads(raw)
    if raw != _canonical_json(value) or value.get("kind") != "gamescope-run-manifest":
        raise ValueError("invalid Gamescope run manifest")
    snapshot = Path(value["snapshot"])
    verify_snapshot(snapshot)
    if _sha256(snapshot / MANIFEST) != value["manifest_sha256"]:
        raise ValueError("Gamescope run snapshot identity changed")
    for name, expected in value["inputs"].items():
        if not Path(name).is_file() or _sha256(Path(name)) != expected:
            raise ValueError("Gamescope run input identity changed")
    from .creative_wine import source_receipt
    if source_receipt(Path(value["source"])) != value["source_before"]:
        raise ValueError("Gamescope run source-preservation identity changed")
    return value


def driver_command(snapshot: Path, creative_args: list[str], *, python: str = sys.executable) -> list[str]:
    snapshot = Path(snapshot).resolve()
    manifest = verify_snapshot(snapshot)
    bootstrap = ("import runpy,sys;sys.dont_write_bytecode=True;sys.path.insert(0," + repr(str(snapshot / RUNTIME)) + ");" +
                 ("import os;os.environ['KP_GAMESCOPE_REPO_ROOT']=" + repr(manifest["repository_root"]) + ";"
                  if "repository_root" in manifest else "") +
                 "runpy.run_module('kpharness.creative',run_name='__main__')")
    return [str(Path(python).resolve()), "-I", "-S", "-c", bootstrap, *creative_args]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]))
    create.add_argument("--snapshot", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--snapshot", required=True)
    verify.add_argument("--source-root")
    driver = commands.add_parser("driver")
    driver.add_argument("--snapshot", required=True)
    driver.add_argument("creative_args", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if options.command == "create":
        snapshot = create_snapshot(Path(options.source_root), Path(options.snapshot))
        print(json.dumps({"ok": True, "snapshot": str(snapshot), "manifest": str(snapshot / MANIFEST)}))
        return 0
    if options.command == "verify":
        manifest = verify_snapshot(Path(options.snapshot), source_root=None if options.source_root is None else Path(options.source_root))
        print(json.dumps({"ok": True, "snapshot": str(Path(options.snapshot).resolve()), "modules": len(manifest["files"])}))
        return 0
    arguments = options.creative_args[1:] if options.creative_args[:1] == ["--"] else options.creative_args
    command = driver_command(Path(options.snapshot), arguments)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(options.snapshot).resolve() / RUNTIME)
    environment["KP_GAMESCOPE_HARNESS_SNAPSHOT"] = str(Path(options.snapshot).resolve())
    # The snapshot root has no top-level package; keeping it as CWD prevents a
    # caller-provided working-directory package from shadowing the sealed one.
    return subprocess.run(command, env=environment, cwd=str(Path(options.snapshot).resolve()), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

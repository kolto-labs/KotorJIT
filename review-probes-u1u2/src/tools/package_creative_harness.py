#!/usr/bin/env python3
"""Build a creative harness package candidate, or list what it would hold.

The package is a repository-shaped tree with the harness import closure, the
public cursed and probe examples, the K1 GOG 1.03 address table and the user
docs. It never holds retail assets, saves, media or run evidence.

A build writes into a new folder and never publishes anything. --dry-run
writes nothing and prints the file list and the path-scan hits.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts/harness'))
from kpharness.gamescope_snapshot import DEFAULT_ENTRIES, runtime_module_paths  # noqa: E402  (import only)

KIND = 'kpharness.creative-harness-package.v1'
TOP = 'kotorphasor-creative-harness'
ZIP_NAME = TOP + '.zip'
SCOPE = ('K1 GOG 1.03, Linux, Wine inside a private Gamescope display, KDE Plasma Wayland '
         'evidence host only. Capture (C7) is known-failing. Other hosts not attempted.')
# Plan entries plus the two user-facing helpers the guide tells people to run.
ENTRIES = ('kpharness.creative', 'kpharness.gamescope_snapshot', 'kpharness.creative_accept',
           'kpharness.creative_export', 'kpharness.capture_diagnostic',
           'kpharness.commit_inputs', 'kpharness.export_verify')
# `gamescope_snapshot create` freezes only this closure; a user run's manifest lists exactly it.
SNAPSHOT_ENTRIES = tuple(DEFAULT_ENTRIES)
HARNESS = 'scripts/harness'
PACKAGE_DIR = 'scripts/harness/kpharness'
UNFINISHED = ('playback', 'pioneer', 'cli')
FIXED = (
    'tools/kpdiscover.py',                 # loaded dynamically by discover.py
    'tools/creative_host_check.py',        # first step of the user guide
    'tools/tests/examples/manifest.json',  # read by creative.py; hashed by gamescope_snapshot create
    'data/app_signatures.toml',            # hashed by gamescope_snapshot create
    'data/addresses/k1_gog_103.json',
    'LICENSE', 'ATTRIBUTION.md',
    'docs/user/creative-harness.md', 'docs/creative-runner.md',
)
SCENARIOS = 'scripts/harness/scenarios/cursed'
EXAMPLES = ('scripts/examples/cursed', 'scripts/examples/showcase', 'scripts/examples/probe')
WALKED = (PACKAGE_DIR, SCENARIOS, *EXAMPLES, 'data/addresses')

RETAIL_SUFFIXES = frozenset({'.bif', '.key', '.mdl', '.mdx', '.rim', '.erf', '.sav', '.ncs', '.nss',
                             '.tlk', '.2da', '.utp', '.utc', '.uti', '.dlg', '.tga', '.dds', '.tpc',
                             '.txi', '.gff', '.res', '.pth', '.lip'})
MEDIA_SUFFIXES = frozenset({'.bik', '.wav', '.mp3', '.mp4', '.gif', '.png', '.jpg', '.jpeg',
                            '.webm', '.mkv'})
BUILD_SUFFIXES = frozenset({'.pyc', '.o', '.obj', '.a', '.so', '.dll', '.exe', '.d'})
RUN_EVIDENCE = ('creative-run.json', 'continuous.mp4', 'executed-route.toml', 'ffprobe-*.json',
                'gamescope-lease.json', 'gamescope-*-manifest.json', 'commitments.log', 'driver.log',
                'ffmpeg.log', 'report.json', 'capture*.json', 'diagnostic-*.json', 'preflight.json',
                'accepted-media-*', 'sources')
PRIVATE_PREFIXES = ('data/adjudication/', 'data/research/', '.superpowers/', 'tmp/')
PATH_MARKERS = ('/home/', '/run/media/', '/Users/')
PRIVATE_JSON_KEYS = ('signature_source', 'source_path', 'corpus_path')


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def closure_files_sha256(files: list[dict]) -> str:
    """Hash the snapshot `files` list. Unlike the snapshot manifest, it has no time or local path."""
    return _sha256(_canonical([{'path': item['path'], 'sha256': item['sha256']} for item in files]))


def deny_reason(rel: str) -> str | None:
    """Return why a path may never be packaged, or None."""
    path = PurePosixPath(rel)
    parts = path.parts
    if any(part in ('.git', '__pycache__') for part in parts):
        return 'cache or version control'
    if any(any(fnmatch.fnmatch(part, pattern) for pattern in RUN_EVIDENCE) for part in parts):
        return 'run evidence'
    if rel.startswith(PRIVATE_PREFIXES):
        return 'private evidence'
    if any(part in ('Saves', 'saves') for part in parts):
        return 'retail save'
    suffix = path.suffix.lower()
    if suffix in RETAIL_SUFFIXES:
        return 'retail asset suffix'
    if suffix in MEDIA_SUFFIXES:
        return 'media suffix'
    if suffix in BUILD_SUFFIXES:
        return 'build output or cache'
    return None


def _walk(root: Path, rel_dir: str):
    base = root / rel_dir
    if base.is_symlink():
        raise ValueError('source contains a symlink; review before packaging: ' + rel_dir)
    if not base.is_dir():
        return
    for current, directories, files in os.walk(base, followlinks=False):
        for name in sorted(directories + files):
            path = Path(current) / name
            if path.is_symlink():
                raise ValueError('source contains a symlink; review before packaging: '
                                 + path.relative_to(root).as_posix())
        for name in sorted(files):
            yield (Path(current) / name).relative_to(root).as_posix()


def select_files(source_root: os.PathLike | str) -> dict:
    """Return the allowlisted files and every walked file left out, with a reason."""
    root = Path(source_root).resolve()
    closure_paths = runtime_module_paths(root / HARNESS, ENTRIES)
    closure = [path.relative_to(root).as_posix() for path in closure_paths]
    reached = sorted(PurePosixPath(rel).stem for rel in closure if PurePosixPath(rel).stem in UNFINISHED)
    if reached:
        raise ValueError('import closure reaches unfinished module(s) ' + ', '.join(reached)
                         + '; stop and review before packaging')
    selected: set[str] = set(closure)
    exclusions: list[dict] = []
    public_stems = {PurePosixPath(rel).stem for rel in _walk(root, 'scripts/examples/cursed')
                    if rel.endswith('.lua') and deny_reason(rel) is None}
    for rel_dir in WALKED:
        for rel in _walk(root, rel_dir):
            if rel in selected:
                continue
            reason = deny_reason(rel)
            if reason is None:
                path = PurePosixPath(rel)
                if rel_dir == PACKAGE_DIR:
                    reason = 'not in import closure'
                elif rel_dir == SCENARIOS:
                    if path.suffix != '.toml':
                        reason = 'not allowlisted'
                    elif path.stem not in public_stems:
                        reason = 'retired: no matching public example'
                elif rel_dir in EXAMPLES:
                    if path.suffix != '.lua' and path.name != 'README.md':
                        reason = 'not allowlisted'
                elif rel not in FIXED:
                    reason = 'not allowlisted'
            if reason is None:
                selected.add(rel)
            elif rel not in FIXED:
                exclusions.append({'path': rel, 'reason': reason})
    for rel in FIXED:
        path = root / rel
        if path.is_symlink():
            raise ValueError('source contains a symlink; review before packaging: ' + rel)
        if not path.is_file():
            raise ValueError('required package file is missing: ' + rel)
        if deny_reason(rel):
            raise ValueError('required package file matches the denylist: ' + rel)
        selected.add(rel)
    for rel in selected:
        if deny_reason(rel):  # Deny wins even when an allow rule matched.
            raise ValueError('allowlisted file matches the denylist: ' + rel)
    return {'selected': sorted(selected), 'closure': closure,
            'exclusions': sorted(exclusions, key=lambda item: item['path'])}


def clean_bytes(rel: str, data: bytes) -> tuple[bytes, list[str]]:
    """Remove private metadata from JSON, using the release builder's rule."""
    if not rel.endswith('.json'):
        return data, []
    value = json.loads(data)
    removed: list[str] = []

    def walk(item):
        if isinstance(item, dict):
            for key in list(item):
                if key == 'reference_image' or (key in PRIVATE_JSON_KEYS and isinstance(item[key], str)
                                                and item[key].startswith(('/home/', '/run/media/', '/Users/'))):
                    removed.append(key)
                    del item[key]
                else:
                    walk(item[key])
        elif isinstance(item, list):
            for element in item:
                walk(element)

    walk(value)
    if not removed:
        return data, []
    return (json.dumps(value, indent=2) + '\n').encode(), sorted(set(removed))


def path_scan(rel: str, data: bytes) -> list[dict]:
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return []
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for marker in PATH_MARKERS:
            if marker in line:
                hits.append({'path': rel, 'line': number, 'marker': marker})
                break
    return hits


def _git_blob_matches(root: Path, base: str, rel: str) -> bool:
    try:
        expected = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', '-q', f'{base}:{rel}'],
                                  capture_output=True, text=True, timeout=10)
        actual = subprocess.run(['git', '-C', str(root), 'hash-object', '--', rel],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return (expected.returncode == 0 and actual.returncode == 0
            and expected.stdout.strip() == actual.stdout.strip() != '')


def check_provenance(root: Path, selected: list[str], provenance: dict) -> dict:
    """Bind every file to the overlay map, or to the base commit through git."""
    base = provenance.get('base_commit')
    overlay = provenance.get('overlay_sha256')
    if not isinstance(overlay, dict) or (base is not None and not isinstance(base, str)):
        raise ValueError('provenance needs overlay_sha256 (object) and base_commit (string or null)')
    for rel in overlay:
        if not isinstance(rel, str) or PurePosixPath(rel).is_absolute() or '..' in PurePosixPath(rel).parts:
            raise ValueError('provenance has an unsafe path: ' + repr(rel))
    mismatched, unbound, by_base = [], [], []
    for rel in selected:
        digest = _sha256((root / rel).read_bytes())
        if rel in overlay:
            if overlay[rel] != digest:
                mismatched.append(rel)
        elif base and _git_blob_matches(root, base, rel):
            by_base.append(rel)
        else:
            unbound.append(rel)
    return {'base_commit': base, 'overlay_sha256': {rel: overlay[rel] for rel in selected if rel in overlay},
            'bound_by_base': by_base, 'mismatched': mismatched, 'unbound': unbound}


def _write_zip(package: Path, destination: Path, files: list[str]) -> None:
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            info = zipfile.ZipInfo(TOP + '/' + rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (package / rel).read_bytes())


def verify_zip(destination: Path, manifest: dict) -> dict:
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        names = set(archive.namelist())
        expected = {TOP + '/' + rel for rel in manifest['files']} | {TOP + '/manifest.json'}
        if names != expected:
            raise ValueError('ZIP entry list differs from manifest')
        for rel, digest in manifest['files'].items():
            if _sha256(archive.read(TOP + '/' + rel)) != digest:
                raise ValueError('ZIP entry hash differs from manifest: ' + rel)
    return {'zip_crc': 'PASS', 'manifest_hashes': 'PASS', 'files_checked': len(manifest['files']),
            'zip_sha256': _sha256(destination.read_bytes())}


def build(source_root: os.PathLike | str, out: os.PathLike | str | None, *,
          provenance: os.PathLike | str | None = None, dry_run: bool = False) -> dict:
    root = Path(source_root).resolve()
    chosen = select_files(root)
    staged: dict[str, bytes] = {}
    sanitizations, hits = [], []
    for rel in chosen['selected']:
        data, removed = clean_bytes(rel, (root / rel).read_bytes())
        if removed:
            sanitizations.append({'path': rel, 'removed_metadata_keys': removed})
        hits.extend(path_scan(rel, data))
        staged[rel] = data
    # Same list, order and hashes `gamescope_snapshot create` records for the extracted tree.
    snapshot_files = [{'path': path.relative_to(root / HARNESS).as_posix(),
                       'sha256': _sha256(staged[path.relative_to(root).as_posix()])}
                      for path in runtime_module_paths(root / HARNESS, SNAPSHOT_ENTRIES)]
    bound = None
    if provenance is not None:
        bound = check_provenance(root, chosen['selected'], json.loads(Path(provenance).read_text()))
    if dry_run:
        return {'dry_run': True, 'selected': chosen['selected'], 'closure': chosen['closure'],
                'exclusions': chosen['exclusions'], 'sanitizations': sanitizations, 'path_scan': hits,
                'snapshot_files_sha256': closure_files_sha256(snapshot_files),
                'provenance': bound if bound is not None else 'not given'}
    if hits:
        raise ValueError('absolute local paths in packaged text: '
                         + ', '.join(f"{hit['path']}:{hit['line']}" for hit in hits))
    if bound is None:
        raise ValueError('a build needs --provenance (base commit plus overlay_sha256)')
    if bound['mismatched']:
        raise ValueError('provenance mismatch: ' + ', '.join(bound['mismatched']))
    if bound['unbound']:
        raise ValueError('unbound files (not in overlay_sha256 or equal to base commit): '
                         + ', '.join(bound['unbound']))
    if out is None:
        raise ValueError('a build needs --out')
    out = Path(out)
    try:
        out.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise ValueError('output folder already exists; choose a new one: ' + out.name) from error
    package = out / 'package'
    package.mkdir()
    for rel, data in staged.items():
        destination = package / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    receipt = {'kind': KIND, 'scope': SCOPE, 'entries': list(ENTRIES),
               'snapshot_entries': list(SNAPSHOT_ENTRIES),
               'snapshot_files': snapshot_files, 'snapshot_files_sha256': closure_files_sha256(snapshot_files),
               'exclusions': chosen['exclusions'], 'sanitizations': sanitizations, 'path_scan': [],
               'provenance': {'base_commit': bound['base_commit'],
                              'overlay_files': len(bound['overlay_sha256']),
                              'bound_by_base': bound['bound_by_base']},
               'media': 'none; no media, saves or run evidence are packaged'}
    (package / 'packaging-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (package / 'source-provenance.json').write_text(json.dumps(
        {'base_commit': bound['base_commit'], 'overlay_sha256': bound['overlay_sha256']}, indent=2) + '\n')
    files = sorted(path.relative_to(package).as_posix() for path in package.rglob('*') if path.is_file())
    manifest = {'scope': SCOPE, 'files': {rel: _sha256((package / rel).read_bytes()) for rel in files}}
    (package / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    destination = out / ZIP_NAME
    _write_zip(package, destination, files + ['manifest.json'])
    verification = verify_zip(destination, manifest)
    (out / 'zip-sha256.txt').write_text(verification['zip_sha256'] + '  ' + ZIP_NAME + '\n')
    (out / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    return {'dry_run': False, 'zip': str(destination), **verification}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build a creative harness package candidate into a new folder. '
                    'Nothing is published. Use --dry-run to list files without writing.')
    parser.add_argument('--source-root', default=str(HERE.parent), help='repository to package from')
    parser.add_argument('--provenance', help='source-provenance.json with base_commit and overlay_sha256')
    parser.add_argument('--out', help='new folder for the candidate; it must not exist')
    parser.add_argument('--dry-run', action='store_true', help='list what would be packaged; write nothing')
    options = parser.parse_args(argv)
    try:
        result = build(options.source_root, options.out, provenance=options.provenance, dry_run=options.dry_run)
    except (ValueError, OSError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    print(json.dumps({'ok': True, **result}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

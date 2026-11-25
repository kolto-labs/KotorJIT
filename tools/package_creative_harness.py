#!/usr/bin/env python3
"""Build a creative harness package candidate, or list what it would hold.

The package is a repository-shaped tree with the harness import closure, the
public cursed and probe examples, the K1 GOG 1.03 address table and the user
docs. It never holds retail assets, saves, media or run evidence.

A build writes into a new folder and never publishes anything. --dry-run
writes nothing and prints the file list and the path-scan hits.

Every source file is read once, through a descriptor that does not follow
links. Those staged bytes are hashed, checked, bound to provenance and written
into the ZIP. At the end every source is read again and the build refuses if
any file changed. Content and privacy rules come from scan_release_zip.py, and
its full scan runs on the finished ZIP bytes as the last gate: a finding
refuses the build before anything is written.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'scripts/harness'))
from kpharness.gamescope_snapshot import DEFAULT_ENTRIES, runtime_module_paths  # noqa: E402  (import only)
sys.path.insert(0, str(HERE))
import scan_release_zip as _scanner  # noqa: E402  (the final gate calls _scanner.scan_bytes)
from scan_release_zip import (EXCLUDED_FILES, content_problems, name_collisions,  # noqa: E402
                              path_scan as _marker_scan, privacy_markers, private_part, unportable_name,
                              unsafe_name)

KIND = 'kpharness.creative-harness-package.v1'
TOP = 'kotorjit-creative-harness'
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
PRIVATE_PREFIXES = ('data/adjudication/', 'data/research/', '.superpowers/', 'tmp/', 'runs/')
# Examples and scenarios are flat folders; anything in a subfolder is left out.
FLAT = (SCENARIOS, *EXAMPLES)
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
    if rel.lower() in EXCLUDED_FILES:
        return 'held back pending the owner decision on retail instruction bytes'
    if any(part in ('.git', '__pycache__') for part in parts):
        return 'cache or version control'
    if any(any(fnmatch.fnmatch(part, pattern) for pattern in RUN_EVIDENCE) for part in parts):
        return 'run evidence'
    if rel.lower().startswith(PRIVATE_PREFIXES):
        return 'private evidence'
    if private_part(rel):  # any depth, not only the repository root; the name is not repeated
        return 'private evidence folder'
    suffix = path.suffix.lower()
    if suffix in RETAIL_SUFFIXES:
        return 'retail asset suffix'
    if suffix in MEDIA_SUFFIXES:
        return 'media suffix'
    if suffix in BUILD_SUFFIXES:
        return 'build output or cache'
    return None


def name_problems(names) -> list[str]:
    """Names Windows or macOS would change, merge or display falsely (re-review R-3). Empty when all are fine."""
    problems = [f'{name!r}: {reason}' for name in names if (reason := unportable_name(name))]
    problems.extend(f'{name!r}: {reason}' for name, reason in sorted(name_collisions(names).items()))
    return problems


def _refuse_tree_links(root: Path, rel_dir: str) -> None:
    """Refuse a symlink anywhere in rel_dir or under it, before any file there is parsed."""
    for _ in _walk(root, rel_dir):
        pass


def refuse_links(root: Path, rel: str) -> None:
    """Refuse when any part of root/rel is a symlink, or when it resolves anywhere but root/rel."""
    current = root
    for part in PurePosixPath(rel).parts:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return  # a missing path is reported by the caller
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('source contains a symlink; review before packaging: '
                             + current.relative_to(root).as_posix())
    if os.path.realpath(root / rel) != str(root / rel):
        raise ValueError('source path does not resolve to itself; review before packaging: ' + rel)


def _walk(root: Path, rel_dir: str):
    base = root / rel_dir
    refuse_links(root, rel_dir)
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
    # R-5: no module is parsed through a link. Check the package folder before computing the closure.
    _refuse_tree_links(root, PACKAGE_DIR)
    try:
        closure_paths = runtime_module_paths(root / HARNESS, ENTRIES)
    except SyntaxError as error:
        name = PurePosixPath(error.filename or '?').name
        raise ValueError(f'harness module does not parse: {name} line {error.lineno}; review before packaging') \
            from error
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
                elif rel_dir in FLAT and path.parent != PurePosixPath(rel_dir):
                    reason = 'in a subfolder; this folder must be flat'
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
                # The receipt ships, so a private, marked or unportable path is withheld;
                # only its folder is named. Private names and markers match without regard to case.
                if (reason in ('private evidence folder', 'private evidence') or path_scan(rel, rel.encode())
                        or unportable_name(rel)):
                    exclusions.append({'path': rel_dir + '/(name withheld)', 'reason': reason})
                else:
                    exclusions.append({'path': rel, 'reason': reason})
    for rel in FIXED:
        path = root / rel
        refuse_links(root, rel)
        if not path.is_file():
            raise ValueError('required package file is missing: ' + rel)
        if deny_reason(rel):
            raise ValueError('required package file matches the denylist: ' + rel)
        selected.add(rel)
    for rel in selected:
        if deny_reason(rel):  # Deny wins even when an allow rule matched.
            raise ValueError('allowlisted file matches the denylist: ' + rel)
        refuse_links(root, rel)
    problems = name_problems(sorted(selected))
    if problems:
        raise ValueError('package names other systems cannot hold faithfully; review before packaging: '
                         + ', '.join(problems))
    unique = {(item['path'], item['reason']): item for item in exclusions}
    return {'selected': sorted(selected), 'closure': closure,
            'exclusions': sorted(unique.values(), key=lambda item: (item['path'], item['reason']))}


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


def path_scan(rel: str, data: bytes, markers=None) -> list[dict]:
    """Privacy-marker hits in the bytes that will ship. Non-UTF-8 bytes are scanned too."""
    return _marker_scan(rel, data, markers)


def read_source(root: Path, rel: str) -> bytes:
    """Read one source file once: no link in any part, a regular file, one hard link only."""
    reason = unsafe_name(rel)
    if reason:
        raise ValueError(f'unsafe name in source ({reason}); review before packaging: {rel!r}')
    refuse_links(root, rel)
    path = root / rel
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError('source file cannot be opened without following links: ' + rel) from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('source is not a regular file: ' + rel)
        if info.st_nlink == 0:  # R-4: the name was unlinked or replaced after open
            raise ValueError('source file was replaced while reading: ' + rel)
        if info.st_nlink != 1:
            raise ValueError(f'source is a hard link ({info.st_nlink} names); review before packaging: {rel}')
        chunks = []
        while block := os.read(descriptor, 1024 * 1024):
            chunks.append(block)
    finally:
        os.close(descriptor)
    # The path must still name the same file, through the same link-free folders.
    refuse_links(root, rel)
    after = os.lstat(path)
    if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):
        raise ValueError('source file was replaced while reading: ' + rel)
    return b''.join(chunks)


def _git_blob_matches(root: Path, base: str, rel: str, data: bytes) -> bool:
    """True when the staged bytes hash to the base commit's blob (same filters as `git hash-object`)."""
    try:
        expected = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', '-q', f'{base}:{rel}'],
                                  capture_output=True, text=True, timeout=10)
        actual = subprocess.run(['git', '-C', str(root), 'hash-object', '--stdin', '--path=' + rel],
                                input=data, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return (expected.returncode == 0 and actual.returncode == 0
            and expected.stdout.strip() == actual.stdout.decode().strip() != '')


def check_provenance(root: Path, selected: list[str], provenance: dict, staged_raw: dict[str, bytes]) -> dict:
    """Bind every staged file to the overlay map, or to the base commit through git.

    Only the staged bytes are hashed; the source is not read again here.
    """
    base = provenance.get('base_commit')
    overlay = provenance.get('overlay_sha256')
    if not isinstance(overlay, dict) or (base is not None and not isinstance(base, str)):
        raise ValueError('provenance needs overlay_sha256 (object) and base_commit (string or null)')
    for rel in overlay:
        if not isinstance(rel, str) or PurePosixPath(rel).is_absolute() or '..' in PurePosixPath(rel).parts:
            raise ValueError('provenance has an unsafe path: ' + repr(rel))
    mismatched, unbound, by_base = [], [], []
    for rel in selected:
        digest = _sha256(staged_raw[rel])
        if rel in overlay:
            if overlay[rel] != digest:
                mismatched.append(rel)
        elif base and _git_blob_matches(root, base, rel, staged_raw[rel]):
            by_base.append(rel)
        else:
            unbound.append(rel)
    return {'base_commit': base, 'overlay_sha256': {rel: overlay[rel] for rel in selected if rel in overlay},
            'bound_by_base': by_base, 'mismatched': mismatched, 'unbound': unbound}


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    """Build the ZIP in memory from the exact package bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(files):
            info = zipfile.ZipInfo(TOP + '/' + rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, files[rel])
    return buffer.getvalue()


def verify_zip(data: bytes, manifest: dict) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
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
            'zip_sha256': _sha256(data)}


def build(source_root: os.PathLike | str, out: os.PathLike | str | None, *,
          provenance: os.PathLike | str | None = None, dry_run: bool = False) -> dict:
    if not dry_run:
        # Refuse early, so a long build never ends on this.
        if out is None:
            raise ValueError('a build needs --out')
        if os.path.lexists(out):
            raise ValueError('output folder already exists; choose a new one: ' + Path(out).name)
        if provenance is None:
            raise ValueError('a build needs --provenance (base commit plus overlay_sha256)')
    root = Path(source_root).resolve()
    chosen = select_files(root)
    markers = privacy_markers()  # includes this user's name, read at build time
    staged_raw: dict[str, bytes] = {}
    staged: dict[str, bytes] = {}
    sanitizations, hits, refused = [], [], []
    for rel in chosen['selected']:
        raw = read_source(root, rel)  # the only read before the final re-check
        staged_raw[rel] = raw
        problems = content_problems(rel, raw)
        if problems:
            refused.append({'path': rel, 'problems': problems})
            continue
        data, removed = clean_bytes(rel, raw)
        if removed:
            sanitizations.append({'path': rel, 'removed_metadata_keys': removed})
        hits.extend(path_scan(rel, data, markers))
        hits.extend({**hit, 'line': 0} for hit in path_scan(rel, rel.encode(), markers))
        staged[rel] = data
    raw_sha = {rel: _sha256(data) for rel, data in staged_raw.items()}
    bound = None
    if provenance is not None:
        bound = check_provenance(root, chosen['selected'], json.loads(Path(provenance).read_text()), staged_raw)
    if dry_run:
        snapshot = None
        if not refused:
            snapshot = closure_files_sha256(_snapshot_files(root, staged))
        return {'dry_run': True, 'selected': chosen['selected'], 'closure': chosen['closure'],
                'exclusions': chosen['exclusions'], 'sanitizations': sanitizations, 'path_scan': hits,
                'content_refusals': refused, 'snapshot_files_sha256': snapshot,
                'provenance': bound if bound is not None else 'not given'}
    if refused:
        raise ValueError('packaged text must be UTF-8 without media, archive or program bytes: '
                         + ', '.join(f"{item['path']} ({'; '.join(item['problems'])})" for item in refused))
    if hits:
        raise ValueError('absolute local paths or private names in packaged text: '
                         + ', '.join(f"{hit['path']}:{hit['line']}" for hit in hits))
    if bound['mismatched']:
        raise ValueError('provenance mismatch: ' + ', '.join(bound['mismatched']))
    if bound['unbound']:
        raise ValueError('unbound files (not in overlay_sha256 or equal to base commit): '
                         + ', '.join(bound['unbound']))
    # Same list, order and hashes `gamescope_snapshot create` records for the extracted tree.
    snapshot_files = _snapshot_files(root, staged)
    receipt = {'kind': KIND, 'scope': SCOPE, 'entries': list(ENTRIES),
               'snapshot_entries': list(SNAPSHOT_ENTRIES),
               'snapshot_files': snapshot_files, 'snapshot_files_sha256': closure_files_sha256(snapshot_files),
               'exclusions': chosen['exclusions'], 'sanitizations': sanitizations, 'path_scan': [],
               'content_check': 'every file is UTF-8 text with no media, archive or program magic',
               'staging': 'each source read once; provenance and ZIP use those bytes; sources re-read at the end',
               'provenance': {'base_commit': bound['base_commit'],
                              'overlay_files': len(bound['overlay_sha256']),
                              'bound_by_base': bound['bound_by_base']},
               'media': 'none; no media, saves or run evidence are packaged'}
    files = dict(staged)
    files['packaging-receipt.json'] = (json.dumps(receipt, indent=2) + '\n').encode()
    files['source-provenance.json'] = (json.dumps(
        {'base_commit': bound['base_commit'], 'overlay_sha256': bound['overlay_sha256']}, indent=2) + '\n').encode()
    manifest = {'scope': SCOPE, 'files': {rel: _sha256(files[rel]) for rel in sorted(files)}}
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    # Backstop: the generated receipt, provenance and manifest ship too.
    generated = [hit for rel in ('packaging-receipt.json', 'source-provenance.json', 'manifest.json')
                 for hit in path_scan(rel, files[rel], markers)]
    if generated:
        raise ValueError('private names in generated package metadata: '
                         + ', '.join(f"{hit['path']}:{hit['line']}" for hit in generated))
    archive = _zip_bytes(files)
    verification = verify_zip(archive, manifest)
    # Mandatory final gate: the release scanner reads the exact ZIP bytes that would be written.
    # No allow globs: this package holds no binaries.
    gate = _scanner.scan_bytes(archive, name=ZIP_NAME, markers=markers)
    if not gate['ok']:
        raise ValueError('release scan of the finished ZIP found problems; nothing was written: '
                         + ', '.join(f"{item['entry']} ({item['kind']}: {item['detail']})"
                                     for item in gate['findings'][:20]))
    verification['release_scan'] = 'PASS'
    # Re-read every source. Any change since staging refuses the build before anything is written.
    changed = []
    for rel in chosen['selected']:
        try:
            if _sha256(read_source(root, rel)) != raw_sha[rel]:
                changed.append(rel)
        except (OSError, ValueError):
            changed.append(rel)
    if changed:
        raise ValueError('source changed during the build; nothing was written: ' + ', '.join(changed))
    out = Path(out)
    try:
        out.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise ValueError('output folder already exists; choose a new one: ' + out.name) from error
    package = out / 'package'
    package.mkdir()
    for rel, data in files.items():
        destination = package / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, 'xb') as stream:
            stream.write(data)
    destination = out / ZIP_NAME
    with open(destination, 'xb') as stream:
        stream.write(archive)
    if _sha256(destination.read_bytes()) != verification['zip_sha256']:
        raise ValueError('ZIP on disk differs from the verified bytes: ' + ZIP_NAME)
    (out / 'zip-sha256.txt').write_text(verification['zip_sha256'] + '  ' + ZIP_NAME + '\n')
    (out / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    return {'dry_run': False, 'zip': str(destination), **verification}


def _snapshot_files(root: Path, staged: dict[str, bytes]) -> list[dict]:
    return [{'path': path.relative_to(root / HARNESS).as_posix(),
             'sha256': _sha256(staged[path.relative_to(root).as_posix()])}
            for path in runtime_module_paths(root / HARNESS, SNAPSHOT_ENTRIES)]


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
    except (ValueError, OSError, SyntaxError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1
    print(json.dumps({'ok': True, **result}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

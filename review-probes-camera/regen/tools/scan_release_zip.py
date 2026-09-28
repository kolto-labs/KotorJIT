#!/usr/bin/env python3
"""Scan an existing release ZIP for private or unsafe content. Read-only.

It opens the ZIP for reading and never writes, renames or extracts to disk.
Nested .tar.gz, .tgz, .tar and .zip entries are read in memory and checked too.

Checks, per entry:
- symlink or hard link entries, and unsafe names (absolute, `..`, backslash,
  control characters)
- private folder names on any path part (.superpowers, tmp, runs, Saves, ...)
- media, archive, executable or retail file magic, whatever the suffix
- strict UTF-8 and no NUL byte for text suffixes
- privacy markers: home folders, this user's name, private workspace names
  and run IDs

The package builder (package_creative_harness.py) imports these rules, so the
builder and this scanner agree. Standard library only.
"""
from __future__ import annotations

import argparse
import fnmatch
import getpass
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

# Folder names that never ship, matched on any path part.
PRIVATE_PARTS = frozenset({'.superpowers', '.worktrees', 'tmp', 'runs', 'Saves', 'saves',
                           'adjudication', 'research'})
PRIVATE_PART_PATTERNS = ('kp-live*', 'kp-release*', 'kp-runs*')

# Leading bytes of formats that must never ride under a text name.
MAGIC = (
    (b'\x89PNG', 'png'), (b'GIF8', 'gif'), (b'\xff\xd8\xff', 'jpeg'), (b'RIFF', 'riff (wav/avi/webp)'),
    (b'BIKi', 'bink'), (b'BIK', 'bink'), (b'KB2', 'bink2'), (b'\x1aE\xdf\xa3', 'matroska/webm'),
    (b'ID3', 'mp3'), (b'\xff\xfb', 'mp3'), (b'OggS', 'ogg'), (b'fLaC', 'flac'), (b'%PDF', 'pdf'),
    (b'DDS ', 'dds'), (b'PK\x03\x04', 'zip'), (b'PK\x05\x06', 'zip'), (b'\x1f\x8b', 'gzip'),
    (b'BZh', 'bzip2'), (b'\xfd7zXZ', 'xz'), (b'7z\xbc\xaf\x27\x1c', '7z'), (b'Rar!', 'rar'),
    (b'\x28\xb5\x2f\xfd', 'zstd'), (b'\x7fELF', 'elf'), (b'MZ', 'pe/dos'), (b'\xca\xfe\xba\xbe', 'mach-o'),
    (b'\xcf\xfa\xed\xfe', 'mach-o'), (b'\x00asm', 'wasm'), (b'SQLite format 3', 'sqlite'),
)
# BioWare containers and GFF files: four tag bytes, then a version such as "V1.0", "V3.2" or "V1  ".
BIOWARE = re.compile(rb'^[A-Z0-9 ]{4}V\d[. ]')
MP4_BOX = re.compile(rb'^.{4}ftyp', re.S)

TEXT_SUFFIXES = frozenset({'.py', '.lua', '.toml', '.md', '.json', '.txt', '.cfg', '.ini', '.yml',
                           '.yaml', '.sh', '.c', '.h', '.cc', '.cpp', '.hpp', '.cmake', '.rst', '.csv',
                           '.nss', '.xml', '.html', '.css', '.js'})
TEXT_NAMES = frozenset({'LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE', 'AUTHORS', 'README', 'Makefile',
                        'CMakeLists.txt'})

# Home folders and private workspace names. Plain substrings, case-sensitive.
FIXED_MARKERS = ('/home/', '/run/media/', '/Users/', '/root/', '/var/home/', 'C:\\Users', 'C:/Users',
                 'C:\\\\Users', 'Documents and Settings', 'kp-live', 'kp-release', '.superpowers',
                 'MyBook', '.worktrees', 'linuxbrew')
# Run ID shapes: a UTC stamp (20260926-234927), optionally plus 8 hex digits (creative.py).
RUN_ID = re.compile(r'\b\d{8}-\d{6}(?:-[0-9a-f]{8})?\b')
# Names that are too common to treat as a private user name.
COMMON_USERS = frozenset({'root', 'user', 'users', 'ubuntu', 'runner', 'admin', 'nobody', 'build',
                          'builder', 'home', 'guest', 'test', 'debian', 'fedora', 'vagrant', 'ci', 'me'})

NESTED_ARCHIVES = ('.tar.gz', '.tgz', '.tar', '.zip')
MAX_NESTED_DEPTH = 2


def usernames(env: dict | None = None) -> tuple[str, ...]:
    """Build-time user names from $USER, $LOGNAME and the $HOME basename. Common or short names are skipped."""
    env = os.environ if env is None else env
    names = {env.get('USER', ''), env.get('LOGNAME', ''), os.path.basename((env.get('HOME') or '').rstrip('/'))}
    if env is os.environ:
        try:
            names.add(getpass.getuser())
        except Exception:  # noqa: BLE001  (no user name is fine)
            pass
    return tuple(sorted(name for name in names
                        if name and len(name) >= 4 and name.lower() not in COMMON_USERS))


def privacy_markers(env: dict | None = None) -> tuple[str, ...]:
    return FIXED_MARKERS + usernames(env)


def unsafe_name(rel: str) -> str | None:
    """Return why an entry name is unsafe, or None."""
    if not rel:
        return 'empty name'
    if '\\' in rel:
        return 'backslash in name'
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in rel):
        return 'control character in name'
    path = PurePosixPath(rel)
    if path.is_absolute() or re.match(r'^[A-Za-z]:', rel):
        return 'absolute name'
    if '..' in path.parts:
        return 'parent reference in name'
    return None


def private_part(rel: str) -> str | None:
    """Return the private folder name found on any path part, or None."""
    for part in PurePosixPath(rel).parts[:-1] or ():
        if part in PRIVATE_PARTS or any(fnmatch.fnmatchcase(part, pattern) for pattern in PRIVATE_PART_PATTERNS):
            return part
    return None


def magic_kind(data: bytes) -> str | None:
    head = data[:64]
    for prefix, kind in MAGIC:
        if head.startswith(prefix):
            return kind
    if BIOWARE.match(head):
        return 'bioware ' + head[:4].decode('ascii').strip().lower()
    if MP4_BOX.match(head):
        return 'mp4/mov'
    return None


def is_text_name(rel: str) -> bool:
    path = PurePosixPath(rel)
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES or path.suffix == ''


def content_problems(rel: str, data: bytes, *, text: bool = True) -> list[str]:
    """Return content problems. `text` means the entry must be strict UTF-8 with no NUL byte."""
    problems = []
    kind = magic_kind(data)
    if kind:
        problems.append('magic: ' + kind)
    if text:
        try:
            data.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            problems.append('not UTF-8')
        if b'\x00' in data:
            problems.append('NUL byte')
    return problems


def _marker_patterns(markers) -> list[tuple[str, re.Pattern]]:
    patterns = []
    for marker in markers:
        if marker in FIXED_MARKERS:
            patterns.append((marker, re.compile(re.escape(marker))))
        else:  # a user name: whole word only, so "runner" never matches "creative-runner".
            # The label never repeats the name, so reports do not leak it either.
            patterns.append(('user name', re.compile(r'(?<![A-Za-z0-9_])' + re.escape(marker) + r'(?![A-Za-z0-9_])')))
    patterns.append(('run id', RUN_ID))
    return patterns


def path_scan(rel: str, data: bytes, markers=None) -> list[dict]:
    """Return one hit per line that holds a privacy marker. Non-UTF-8 bytes are read as Latin-1."""
    markers = privacy_markers() if markers is None else markers
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('latin-1')
    patterns = _marker_patterns(markers)
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for marker, pattern in patterns:
            if pattern.search(line):
                hits.append({'path': rel, 'line': number, 'marker': marker})
                break
    return hits


# ---------------------------------------------------------------------------
# ZIP scanner


def _finding(entry: str, kind: str, detail: str) -> dict:
    return {'entry': entry, 'kind': kind, 'detail': detail}


def _scan_blob(label: str, rel: str, data: bytes, markers, depth: int, out: list) -> None:
    if private_part(rel):
        out.append(_finding(label, 'private folder', private_part(rel)))
    lower = rel.lower()
    nested = depth < MAX_NESTED_DEPTH and lower.endswith(NESTED_ARCHIVES)
    for problem in content_problems(rel, data, text=is_text_name(rel)):
        kind = 'magic' if problem.startswith('magic') else problem
        out.append(_finding(label, kind, problem))
    if not nested:
        for hit in path_scan(rel, data, markers)[:20]:
            out.append(_finding(label, 'marker', f"line {hit['line']}: {hit['marker']}"))
        return
    try:
        if lower.endswith('.zip'):
            _scan_zip(zipfile.ZipFile(io.BytesIO(data)), label + '!', markers, depth + 1, out)
        else:
            _scan_tar(tarfile.open(fileobj=io.BytesIO(data), mode='r:*'), label + '!', markers, depth + 1, out)
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError) as error:
        out.append(_finding(label, 'unreadable archive', str(error)))


def _scan_tar(archive: tarfile.TarFile, prefix: str, markers, depth: int, out: list) -> None:
    with archive:
        for member in archive.getmembers():
            label = prefix + member.name
            reason = unsafe_name(member.name)
            if reason:
                out.append(_finding(label, 'unsafe name', reason))
            if member.issym():
                out.append(_finding(label, 'symlink', 'link to ' + member.linkname))
                continue
            if member.islnk():
                out.append(_finding(label, 'hard link', 'link to ' + member.linkname))
                continue
            if member.isdir():
                if private_part(member.name + '/x'):
                    out.append(_finding(label, 'private folder', private_part(member.name + '/x')))
                continue
            if not member.isfile():
                out.append(_finding(label, 'special file', f'tar type {member.type!r}'))
                continue
            stream = archive.extractfile(member)
            _scan_blob(label, member.name, stream.read() if stream else b'', markers, depth, out)


def _scan_zip(archive: zipfile.ZipFile, prefix: str, markers, depth: int, out: list) -> None:
    with archive:
        bad = archive.testzip()
        if bad is not None:
            out.append(_finding(prefix + bad, 'crc', 'ZIP CRC failure'))
        for info in archive.infolist():
            label = prefix + info.filename
            reason = unsafe_name(info.filename.rstrip('/') if info.is_dir() else info.filename)
            if reason:
                out.append(_finding(label, 'unsafe name', reason))
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                out.append(_finding(label, 'symlink', 'ZIP entry is a symlink'))
                continue
            if info.is_dir():
                if private_part(info.filename + 'x'):
                    out.append(_finding(label, 'private folder', private_part(info.filename + 'x')))
                continue
            _scan_blob(label, info.filename, archive.read(info), markers, depth, out)


def scan(path: os.PathLike | str, *, markers=None, allow: tuple[str, ...] = ()) -> dict:
    """Scan one ZIP read-only. `allow` globs mark expected magic findings (for example '*.dll')."""
    markers = privacy_markers() if markers is None else tuple(markers)
    path = Path(path)
    findings: list[dict] = []
    with open(path, 'rb') as stream:
        raw = stream.read()
    _scan_zip(zipfile.ZipFile(io.BytesIO(raw)), '', markers, 0, findings)
    expected, rest = [], []
    for item in findings:
        name = item['entry'].rsplit('!', 1)[-1]
        allowed = item['kind'] == 'magic' and any(
            fnmatch.fnmatchcase(item['entry'], pattern) or fnmatch.fnmatchcase(PurePosixPath(name).name, pattern)
            for pattern in allow)
        (expected if allowed else rest).append(item)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = len(archive.infolist())
    return {'zip': path.name, 'zip_sha256': hashlib.sha256(raw).hexdigest(), 'entries': entries,
            'ok': not rest, 'findings': rest, 'expected': expected,
            'markers': len(markers), 'allow': list(allow)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Scan a release ZIP for private or unsafe content. The ZIP is only read.')
    parser.add_argument('zip', nargs='+', help='ZIP files to scan')
    parser.add_argument('--allow', action='append', default=[],
                        help='glob for entries whose binary magic is expected, such as "*.dll"')
    options = parser.parse_args(argv)
    status = 0
    for name in options.zip:
        before = os.stat(name)
        try:
            report = scan(name, allow=tuple(options.allow))
        except (OSError, zipfile.BadZipFile) as error:
            report = {'zip': Path(name).name, 'ok': False, 'error': str(error)}
        after = os.stat(name)
        report['unchanged'] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        print(json.dumps(report, indent=2))
        status |= 0 if report.get('ok') and report['unchanged'] else 1
    return status


if __name__ == '__main__':
    raise SystemExit(main())

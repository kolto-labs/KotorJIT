#!/usr/bin/env python3
"""Scan an existing release ZIP for private or unsafe content. Read-only.

It opens the ZIP for reading and never writes, renames or extracts to disk.
Nested ZIP, tar, gzip, bzip2 and xz entries are read in memory and checked too.
7z, RAR, zstd and other unknown compressed entries are reported as unscanned;
--allow never hides them.

Checks, per archive:
- the ZIP comment, and any bytes no entry covers: before the first entry,
  between entries, after the compressed data of a deflated entry, or after
  the end record; for a tar, nonzero bytes after its end
- names that collide after NFC normalization or case folding, exact
  duplicate names, and a file that shares its name with a folder

Checks, per entry:
- the entry name: privacy markers, unsafe names (absolute, `..`, backslash,
  control characters) and names other systems cannot hold (Windows device
  names, reserved characters, trailing dot or space, Unicode format characters)
- ZIP entry comments and extra fields, including Unix owner fields
  (0x7875, 0x7855, 0x5855 and 0x000d); a NUL in a name is reported, and the
  name after it is scanned too
- tar owner names and ids: the build user's name, any account name, or a
  nonzero uid or gid
- symlink or hard link entries, and encrypted entries
- private folder names (.superpowers, Saves, kp-live*, data/research, and
  tmp/ or runs/ at the repository root)
- files held back pending an owner decision (data/codecaves.toml,
  data/events.draft.toml)
- media, archive, executable or retail file magic at offset 0, after an
  optional UTF-8 BOM, whatever the suffix
- strict UTF-8 and no NUL byte for text suffixes
- privacy markers in the bytes, and in UTF-16 strings whenever NUL bytes are
  present: home folders, /tmp/ and /var/tmp/ paths, this user's name, git
  identities from every config scope, the origin remote's owner, private
  workspace names and run IDs

The creative package builder (package_creative_harness.py) imports these rules
and runs scan_bytes() on its own ZIP as the last gate. Standard library only.
"""
from __future__ import annotations

import argparse
import bz2
import fnmatch
import getpass
import gzip
import hashlib
import io
import json
import lzma
import os
import re
import stat
import struct
import subprocess
import sys
import tarfile
import unicodedata
import zipfile
import zlib
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent

# Folder names that never ship, on any path part. Compared case-insensitively.
PRIVATE_PARTS = frozenset({'.superpowers', '.worktrees', 'saves', 'adjudication'})
PRIVATE_PART_PATTERNS = ('kp-live*', 'kp-release*', 'kp-runs*')
# Folder pairs that never ship at any depth. docs/research is public and allowed.
PRIVATE_PAIRS = frozenset({('data', 'research'), ('data', 'adjudication')})
# Folders that are private only at the repository root (spec section 2: root tmp/; run folders).
PRIVATE_ROOT_PARTS = frozenset({'tmp', 'runs'})
# A lone top folder with one of these names is the repository root itself, not a wrapper folder (S-5).
NOT_WRAPPER_PARTS = PRIVATE_ROOT_PARTS | {'data'}
# Held back from every package until the owner decides on retail instruction bytes.
EXCLUDED_FILES = frozenset({'data/codecaves.toml', 'data/events.draft.toml'})

BOM = b'\xef\xbb\xbf'


def _pe(data: bytes) -> bool:
    """A DOS or PE header: 64 bytes, and either a PE signature at e_lfanew or NUL bytes in the header."""
    if len(data) < 64:
        return False
    offset = struct.unpack_from('<I', data, 60)[0]
    if 64 <= offset <= len(data) - 4 and data[offset:offset + 4] == b'PE\x00\x00':
        return True
    return b'\x00' in data[2:64]


# (signature at offset 0, kind, extra test on the whole head or None). Each needs its full signature.
MAGIC = (
    (b'\x89PNG\r\n\x1a\n', 'png', None), (b'GIF87a', 'gif', None), (b'GIF89a', 'gif', None),
    (b'\xff\xd8\xff', 'jpeg', None), (b'RIFF', 'riff (wav/avi/webp)', lambda d: len(d) >= 12),
    (b'BIK', 'bink', lambda d: len(d) >= 4 and 0x61 <= d[3] <= 0x7a),
    (b'KB2', 'bink2', lambda d: len(d) >= 4 and 0x61 <= d[3] <= 0x7a),
    (b'\x1aE\xdf\xa3', 'matroska/webm', None),
    (b'ID3', 'mp3', lambda d: len(d) >= 5 and d[3] in (2, 3, 4) and d[4] != 0xff),
    (b'\xff\xfb', 'mp3', None), (b'\xff\xf3', 'mp3', None), (b'OggS', 'ogg', None), (b'fLaC', 'flac', None),
    (b'%PDF-', 'pdf', None), (b'DDS |\x00\x00\x00', 'dds', None),
    (b'PK\x03\x04', 'zip', None), (b'PK\x05\x06', 'zip', None),
    (b'\x1f\x8b\x08', 'gzip', None),
    (b'BZh', 'bzip2', lambda d: len(d) >= 10 and 0x31 <= d[3] <= 0x39
     and d[4:10] in (b'\x31\x41\x59\x26\x53\x59', b'\x17\x72\x45\x38\x50\x90')),
    (b'\xfd7zXZ\x00', 'xz', None), (b'7z\xbc\xaf\x27\x1c', '7z', None), (b'Rar!\x1a\x07', 'rar', None),
    (b'\x28\xb5\x2f\xfd', 'zstd', None), (b'\x7fELF', 'elf', None), (b'MZ', 'pe/dos', _pe),
    (b'\xca\xfe\xba\xbe', 'mach-o', None), (b'\xcf\xfa\xed\xfe', 'mach-o', None),
    (b'\xce\xfa\xed\xfe', 'mach-o', None), (b'\x00asm', 'wasm', None), (b'SQLite format 3\x00', 'sqlite', None),
)
# BioWare containers and GFF files: four tag bytes, then a version such as "V1.0", "V3.2" or "V1  ".
BIOWARE = re.compile(rb'^[A-Z0-9 ]{4}V\d[. ]')
MP4_BOX = re.compile(rb'^.{4}ftyp', re.S)

TEXT_SUFFIXES = frozenset({'.py', '.lua', '.toml', '.md', '.json', '.txt', '.cfg', '.ini', '.yml',
                           '.yaml', '.sh', '.c', '.h', '.cc', '.cpp', '.hpp', '.cmake', '.rst', '.csv',
                           '.nss', '.xml', '.html', '.css', '.js'})
TEXT_NAMES = frozenset({'LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE', 'AUTHORS', 'README', 'Makefile',
                        'CMakeLists.txt'})

# Home folders and private workspace names. Substrings, matched without regard to case, except the
# Linux path prefixes in CASE_SENSITIVE_MARKERS: Linux paths are case-sensitive, and "PageDown/Home/End"
# in upstream ImGui is not a home folder.
FIXED_MARKERS = ('/home/', '/run/media/', '/media/', '/Users/', '/Volumes/', '/root/', '/var/home/',
                 'C:\\Users', 'C:/Users', 'C:\\\\Users', 'Documents and Settings', 'kp-live', 'kp-release',
                 '.superpowers', 'MyBook', '.worktrees', 'linuxbrew', '/tmp/', '/var/tmp/')
CASE_SENSITIVE_MARKERS = frozenset({'/home/', '/run/media/', '/media/', '/root/', '/var/home/', '/tmp/',
                                    '/var/tmp/'})
# /tmp/ and /var/tmp/ count only at the start of a path, so scripts/tmp/ is not one. The name right after
# them passes only when it is fixed, the same on every machine and run, and holds no build tree or run
# output: the X11 and ICE socket folders, X server lock files, and the harness's write-probe file.
_PATH_START = r'(?<![A-Za-z0-9_.~$})-])'
TMP_FIXED_NAMES = (r'\.(?:X11|ICE|XIM|font)-unix(?![A-Za-z0-9_.-])'
                   r'|\.t?X(?:\d+|<n>)-lock(?![A-Za-z0-9_./-])'
                   r'|\.kp_harness_write_probe(?:\.(?:\d+|\$\$|\{[^}/\s]*\}))?(?![A-Za-z0-9_./-])')
TMP_PATTERNS = {marker: re.compile(_PATH_START + re.escape(marker) + '(?!' + TMP_FIXED_NAMES + ')')
                for marker in ('/tmp/', '/var/tmp/')}
# Run ID shapes (ruling 1): runs/<UTC stamp>, or a stamp plus 8 hex digits (creative.py run folders).
# A bare stamp such as 20260910-095338 is not a run ID.
RUN_ID = re.compile(r'(?:(?<![A-Za-z0-9])runs/\d{8}-\d{6}(?!\d)|(?<![0-9])\d{8}-\d{6}-[0-9a-f]{8}(?![0-9a-f]))',
                    re.IGNORECASE)
# Names that are too common to treat as a private user name or identity.
COMMON_USERS = frozenset({'root', 'user', 'users', 'ubuntu', 'runner', 'admin', 'nobody', 'build',
                          'builder', 'home', 'guest', 'test', 'debian', 'fedora', 'vagrant', 'ci', 'me',
                          'noreply', 'no-reply', 'steamuser'})
# Public tool and bot names that show up in git config or remotes but name no private person (S-2).
GENERIC_IDENTITIES = frozenset({'copilot', 'github', 'github-actions', 'github-actions[bot]', 'dependabot',
                                'dependabot[bot]', 'actions-user', 'web-flow', 'gitlab', 'bitbucket',
                                'claude', 'codex', 'cursor'})

# Container kind -> suffixes that honestly name it. A matching entry is opened and scanned, so its own
# magic is not a finding (triage R9(a)).
CONTAINER_SUFFIXES = {'zip': ('.zip',), 'tar': ('.tar',), 'gzip': ('.gz', '.tgz'),
                      'bzip2': ('.bz2', '.tbz', '.tbz2'), 'xz': ('.xz', '.txz')}
UNSCANNABLE_KINDS = frozenset({'7z', 'rar', 'zstd'})
UNSCANNABLE_SUFFIXES = ('.7z', '.rar', '.zst', '.zstd', '.cab', '.lz4', '.lz', '.lzh', '.arj', '.z', '.sit')
MAX_NESTED_DEPTH = 3
MAX_EXPANDED_BYTES = 1 << 30  # per nested stream

WINDOWS_RESERVED = frozenset({'CON', 'PRN', 'AUX', 'NUL', *(f'COM{n}' for n in range(1, 10)),
                              *(f'LPT{n}' for n in range(1, 10))})
WINDOWS_RESERVED_CHARS = frozenset('<>:"|?*')


def usernames(env: dict | None = None) -> tuple[str, ...]:
    """Build-time user names from $USER, $LOGNAME and the $HOME basename. Common or short names are skipped."""
    env = os.environ if env is None else env
    names = {env.get('USER', ''), env.get('LOGNAME', ''), os.path.basename((env.get('HOME') or '').rstrip('/'))}
    if env is os.environ:
        try:
            names.add(getpass.getuser())
        except Exception:  # noqa: BLE001  (no user name is fine)
            pass
    return tuple(sorted(name for name in names if _identity_ok(name)))


def _identity_ok(name: str) -> bool:
    return (bool(name) and len(name) >= 4 and name.lower() not in COMMON_USERS
            and name.lower() not in GENERIC_IDENTITIES)


def _git(*args: str) -> str:
    try:
        result = subprocess.run(['git', '-C', str(HERE), *args], capture_output=True, text=True, timeout=10,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, ValueError):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def _git_config(key: str) -> str:
    """Every value of a git config key, one per line, from every scope: repository, global, system (S-2)."""
    return _git('config', '--get-all', key)


def _origin_url() -> str:
    return _git('remote', 'get-url', 'origin')


def owner_from_url(url: str) -> str:
    """The owner (first path part) of a remote URL: https, ssh:// or scp-like `git@host:owner/repo`."""
    url = url.strip()
    match = (re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]+@)?[^/]+/(.+)$', url)
             or re.match(r'^(?:[^@/:]+@)?[^/:]+:(?!//)(.+)$', url))
    if not match:
        return ''
    parts = [part for part in match.group(1).split('/') if part]
    return parts[0] if len(parts) >= 2 else ''


def git_identities() -> tuple[str, ...]:
    """Every scope's git user.name and user.email (and its local part), github.user, and the origin remote's
    owner. Common, short or generic tool names (GENERIC_IDENTITIES, such as Copilot) are skipped."""
    found = set()
    for key in ('user.name', 'user.email', 'github.user'):
        for value in _git_config(key).splitlines():
            value = value.strip()
            if not value:
                continue
            found.add(value)
            if '@' in value:
                found.add(value.split('@', 1)[0])
    found.add(owner_from_url(_origin_url()))
    return tuple(sorted(name for name in found if _identity_ok(name)))


def privacy_markers(env: dict | None = None, *, git: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Fixed markers plus user names and, when env is not given, the git identities read now."""
    identities = set(usernames(env))
    if git is not None:
        identities.update(git)
    elif env is None:
        identities.update(git_identities())
    return FIXED_MARKERS + tuple(sorted(identities, key=str.lower))


def identity_markers(markers) -> frozenset[str]:
    """The user names and identities in a marker list, case-folded."""
    return frozenset(marker.casefold() for marker in markers if marker not in FIXED_MARKERS)


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


def unportable_name(rel: str) -> str | None:
    """Return why Windows or macOS cannot hold this name faithfully, or None (re-review R-3)."""
    if any(unicodedata.category(ch) == 'Cf' for ch in rel):
        return 'Unicode format character (such as a bidi control) in name'
    for part in PurePosixPath(rel).parts:
        if part in ('.', '..'):
            continue
        if WINDOWS_RESERVED_CHARS.intersection(part):
            return 'Windows reserved character in name'
        if part.endswith(('.', ' ')):
            return 'trailing dot or space in name'
        if part.split('.', 1)[0].rstrip(' ').upper() in WINDOWS_RESERVED:
            return 'Windows device name'
    return None


def name_collisions(names, folders=()) -> dict[str, str]:
    """Map each colliding name to the reason: another name equal after NFC normalization and case folding,
    an exact duplicate, or a file that shares its name with a folder (S-7). `folders` names folder entries
    that carry no trailing slash, as in a tar."""
    names = list(names)
    folders = set(folders)

    def key(name: str) -> str:
        return unicodedata.normalize('NFC', name).casefold()
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(key(name), []).append(name)
    out = {}
    for group in groups.values():
        if len(set(group)) > 1:
            for name in group:
                out[name] = 'collides with ' + str(len(set(group)) - 1) + ' other name(s) after NFC and case folding'
        elif len(group) > 1:
            out[group[0]] = f'duplicate name ({len(group)} entries)'
    folder_keys = set()
    for name in names:
        parts = PurePosixPath(name.rstrip('/')).parts
        folder_keys.update(key('/'.join(parts[:end])) for end in range(1, len(parts)))
        if name.endswith('/') or name in folders:
            folder_keys.add(key(name.rstrip('/')))
    for name in names:
        if name.endswith('/') or name in folders or name in out:
            continue
        if key(name) in folder_keys:
            out[name] = 'a file and a folder share this name after NFC and case folding'
    return out


def private_part(rel: str, root_depth: int = 0) -> str | None:
    """Return the private folder name found on a folder part of `rel`, or None.

    `root_depth` is how many leading parts sit above the repository root (1 for a ZIP with one top folder).
    """
    folders = PurePosixPath(rel).parts[:-1]
    lowered = [part.casefold() for part in folders]
    for index, part in enumerate(lowered):
        if part in PRIVATE_PARTS or any(fnmatch.fnmatchcase(part, pattern) for pattern in PRIVATE_PART_PATTERNS):
            return folders[index]
        if index > 0 and (lowered[index - 1], part) in PRIVATE_PAIRS:
            return folders[index]
        if index == root_depth and part in PRIVATE_ROOT_PARTS:
            return folders[index]
    return None


def excluded_file(rel: str, root_depth: int = 0) -> str | None:
    """Return the repository path when `rel` is held back pending an owner decision, or None."""
    repo = '/'.join(PurePosixPath(rel).parts[root_depth:]).lower()
    return repo if repo in EXCLUDED_FILES else None


def magic_kind(data: bytes) -> str | None:
    """Kind of binary format whose full signature sits at offset 0, after an optional UTF-8 BOM."""
    head = data[:4096]
    if head.startswith(BOM):
        head = head[len(BOM):]
    for prefix, kind, test in MAGIC:
        if head.startswith(prefix) and (test is None or test(head)):
            return kind
    if len(head) >= 262 and head[257:262] == b'ustar':
        return 'tar'
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
        if marker in TMP_PATTERNS:
            patterns.append((marker, TMP_PATTERNS[marker]))
        elif marker in FIXED_MARKERS:
            flags = 0 if marker in CASE_SENSITIVE_MARKERS else re.IGNORECASE
            patterns.append((marker, re.compile(re.escape(marker), flags)))
        else:  # a user name or identity: whole word, and `_` is a boundary, so "creative-runner" is safe.
            # The label never repeats the name, so reports do not leak it either.
            patterns.append(('user name', re.compile(r'(?<![A-Za-z0-9])' + re.escape(marker) + r'(?![A-Za-z0-9])',
                                                     re.IGNORECASE)))
    patterns.append(('run id', RUN_ID))
    return patterns


def _scan_text(rel: str, text: str, patterns) -> list[dict]:
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for marker, pattern in patterns:
            if pattern.search(line):
                hits.append({'path': rel, 'line': number, 'marker': marker})
                break
    return hits


def path_scan(rel: str, data: bytes, markers=None) -> list[dict]:
    """Return one hit per line that holds a privacy marker. Non-UTF-8 bytes are read as Latin-1."""
    markers = privacy_markers() if markers is None else markers
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('latin-1')
    return _scan_text(rel, text, _marker_patterns(markers))


def wide_scan(rel: str, data: bytes, markers) -> list[dict]:
    """Markers in UTF-16LE strings, at both byte alignments. Line numbers are not meaningful here."""
    if b'\x00' not in data:
        return []
    patterns = _marker_patterns(markers)
    hits = []
    for start in (0, 1):
        hits.extend(_scan_text(rel, data[start:].decode('utf-16-le', errors='replace'), patterns))
    return hits


# ---------------------------------------------------------------------------
# ZIP scanner


def _finding(entry: str, kind: str, detail: str) -> dict:
    return {'entry': entry, 'kind': kind, 'detail': detail}


def _root_depth(names) -> int:
    """1 when every name sits under one shared top folder, else 0."""
    parts = [PurePosixPath(name.rstrip('/')).parts for name in names if name.strip('/')]
    if not parts or len({p[0] for p in parts}) != 1:
        return 0
    if parts[0][0].casefold() in NOT_WRAPPER_PARTS:  # a lone data/, tmp/ or runs/ is the repository root (S-5)
        return 0
    return 1 if any(len(p) > 1 for p in parts) else 0


def _scan_meta(label: str, kind: str, data: bytes, markers, out: list) -> None:
    for hit in path_scan(label, data, markers)[:5]:
        out.append(_finding(label, kind, f"line {hit['line']}: {hit['marker']}"))


def _scan_name(label: str, name: str, markers, root_depth: int, out: list, *, folder: bool = False) -> None:
    reason = unsafe_name(name.rstrip('/') if folder else name)
    if reason:
        out.append(_finding(label, 'unsafe name', reason))
    reason = unportable_name(name.rstrip('/'))
    if reason:
        out.append(_finding(label, 'unportable name', reason))
    for hit in path_scan(label, name.encode('utf-8', 'surrogateescape'), markers)[:1]:
        out.append(_finding(label, 'marker in name', hit['marker']))
    part = private_part(name.rstrip('/') + '/x' if folder else name, root_depth)
    if part:
        out.append(_finding(label, 'private folder', part))


def _archive_kind(rel: str, kind: str | None) -> str | None:
    lower = rel.lower()
    if kind in ('zip', 'tar', 'gzip', 'bzip2', 'xz'):
        return kind
    if kind in UNSCANNABLE_KINDS or lower.endswith(UNSCANNABLE_SUFFIXES):
        return 'unscannable'
    for container, suffixes in CONTAINER_SUFFIXES.items():
        if lower.endswith(suffixes):
            return container
    return None


def _expand(kind: str, data: bytes) -> bytes:
    source = io.BytesIO(data)
    opener = {'gzip': lambda: gzip.GzipFile(fileobj=source), 'bzip2': lambda: bz2.BZ2File(source),
              'xz': lambda: lzma.LZMAFile(source)}[kind]
    with opener() as stream:
        expanded = stream.read(MAX_EXPANDED_BYTES + 1)
    if len(expanded) > MAX_EXPANDED_BYTES:
        raise ValueError('expands past the size limit')
    return expanded


def _inner_name(rel: str, kind: str) -> str:
    name = PurePosixPath(rel).name
    for suffix in CONTAINER_SUFFIXES[kind]:
        if name.lower().endswith(suffix):
            return name[:-len(suffix)] or name
    return name


def _scan_nested(label: str, rel: str, data: bytes, kind: str, markers, depth: int, out: list) -> bool:
    """Open a nested archive and scan inside it. Return True when it was scanned."""
    try:
        if kind == 'zip':
            _scan_zip(zipfile.ZipFile(io.BytesIO(data)), data, label + '!', markers, depth + 1, out)
            return True
        if kind == 'tar':
            _scan_tar(tarfile.open(fileobj=io.BytesIO(data), mode='r:'), data, label, markers, depth + 1, out)
            return True
        # Expand first, so the tar's end can be checked against the whole stream (S-3).
        expanded = _expand(kind, data)
        try:
            archive = tarfile.open(fileobj=io.BytesIO(expanded), mode='r:')
        except tarfile.ReadError:
            archive = None
        if archive is not None:
            _scan_tar(archive, expanded, label, markers, depth + 1, out)
            return True
        inner = _inner_name(rel, kind)
        _scan_blob(label + '!' + inner, inner, expanded, markers, depth + 1, out, 0)
        return True
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError, ValueError, TypeError, lzma.LZMAError,
            zlib.error, NotImplementedError, RuntimeError) as error:
        out.append(_finding(label, 'unreadable archive', str(error)[:200]))
        return False


def _scan_blob(label: str, rel: str, data: bytes, markers, depth: int, out: list, root_depth: int) -> None:
    held = excluded_file(rel, root_depth)
    if held:
        out.append(_finding(label, 'excluded file', held + ' is held back pending an owner decision'))
    kind = magic_kind(data)
    archive = _archive_kind(rel, kind)
    scanned = False
    if archive == 'unscannable':
        out.append(_finding(label, 'unscanned archive', f"{kind or 'compressed'} content was not opened"))
    elif archive is not None:
        if depth >= MAX_NESTED_DEPTH:
            out.append(_finding(label, 'unscanned archive', 'nested too deep'))
        else:
            scanned = _scan_nested(label, rel, data, archive, markers, depth, out)
    honest = scanned and kind is not None and rel.lower().endswith(CONTAINER_SUFFIXES.get(kind, ('\0',)))
    for problem in content_problems(rel, data, text=is_text_name(rel)):
        if problem.startswith('magic'):
            if honest:
                continue
            out.append(_finding(label, 'magic', problem))
        else:
            out.append(_finding(label, problem, problem))
    if archive is not None:
        return
    hits = path_scan(rel, data, markers)
    # Whenever NUL bytes are present, valid UTF-8 or not (S-1): ASCII in UTF-16 is valid UTF-8 too.
    hits.extend(dict(hit, line=0, marker='utf-16 ' + hit['marker']) for hit in wide_scan(rel, data, markers))
    for hit in hits[:20]:
        out.append(_finding(label, 'marker', f"line {hit['line']}: {hit['marker']}"))


def _owner_problems(owner_ids: frozenset[str], uname: str, gname: str, uid: int, gid: int) -> list[str]:
    reasons = []
    for field, value in (('uname', uname), ('gname', gname)):
        if not value:
            continue
        if value.casefold() in owner_ids:
            reasons.append(field + ' is the build user')
        elif value != 'root':
            reasons.append(field + ' names an account')
    if uid or gid:
        reasons.append(f'uid {uid} gid {gid} (nonzero)')
    return reasons


def _scan_tar(archive: tarfile.TarFile, stream: bytes, label: str, markers, depth: int, out: list) -> None:
    """Scan a tar read from `stream`, the whole uncompressed tar, which is named `label` in findings."""
    prefix = label + '!'
    owner_ids = identity_markers(markers)
    with archive:
        members = archive.getmembers()
        # tarfile stops quietly at an end block or a bad header; GNU tar can still recover what follows (S-3).
        tail = stream[archive.offset:]
        trailing = tail.strip(b'\x00')
        if trailing:
            start = archive.offset + len(tail) - len(tail.lstrip(b'\x00'))
            out.append(_finding(label, 'uncovered bytes', f'{len(trailing)} bytes after the tar end, from offset {start}'))
            _scan_meta(label, 'uncovered bytes', trailing, markers, out)
        root_depth = _root_depth(member.name for member in members)
        total = 0
        for member in members:
            label = prefix + member.name
            _scan_name(label, member.name, markers, root_depth, out, folder=member.isdir())
            reasons = _owner_problems(owner_ids, member.uname, member.gname, member.uid, member.gid)
            if reasons:
                out.append(_finding(label, 'tar owner', '; '.join(reasons)))
            for key, value in sorted(member.pax_headers.items()):
                _scan_meta(label, 'tar header', f'{key}={value}'.encode('utf-8', 'surrogateescape'), markers, out)
            if member.issym():
                out.append(_finding(label, 'symlink', 'link entry'))
                continue
            if member.islnk():
                out.append(_finding(label, 'hard link', 'link entry'))
                continue
            if member.isdir():
                continue
            if not member.isfile():
                out.append(_finding(label, 'special file', f'tar type {member.type!r}'))
                continue
            total += member.size
            if total > MAX_EXPANDED_BYTES:
                out.append(_finding(label, 'unscanned archive', 'tar expands past the size limit'))
                return
            stream = archive.extractfile(member)
            _scan_blob(label, member.name, stream.read() if stream else b'', markers, depth, out, root_depth)
    folders = {member.name for member in members if member.isdir()}
    for name, reason in name_collisions([member.name for member in members], folders).items():
        out.append(_finding(prefix + name, 'name collision', reason))


def _extra_fields(extra: bytes):
    """Yield (header id, payload) from a ZIP extra block."""
    offset = 0
    while offset + 4 <= len(extra):
        header, size = struct.unpack_from('<HH', extra, offset)
        yield header, extra[offset + 4:offset + 4 + size]
        offset += 4 + size


def _unix_owner(header: int, payload: bytes) -> tuple[int, int] | None:
    """Unix uid and gid from a ZIP extra field, or None (S-6).

    0x7875 Info-ZIP 'ux': version 1, uid size, uid, gid size, gid.
    0x7855 Info-ZIP 'Ux': uid, gid (u16, local header only; the central copy is empty).
    0x5855 Info-ZIP 'UX' and 0x000d PKWARE Unix: atime, mtime (u32), then uid, gid (u16) when present.
    """
    if header == 0x7855:
        return struct.unpack_from('<HH', payload) if len(payload) >= 4 else None
    if header in (0x5855, 0x000D):
        return struct.unpack_from('<HH', payload, 8) if len(payload) >= 12 else None
    if header != 0x7875:
        return None
    try:
        if payload[0] != 1:
            return None
        uid_size = payload[1]
        uid = int.from_bytes(payload[2:2 + uid_size], 'little')
        gid_size = payload[2 + uid_size]
        gid = int.from_bytes(payload[3 + uid_size:3 + uid_size + gid_size], 'little')
        return uid, gid
    except IndexError:
        return None


def _local_extra(raw: bytes | None, info: zipfile.ZipInfo) -> bytes:
    if raw is None:
        return b''
    start = info.header_offset
    if raw[start:start + 4] != b'PK\x03\x04' or start + 30 > len(raw):
        return b''
    name_size, extra_size = struct.unpack_from('<HH', raw, start + 26)
    return raw[start + 30 + name_size:start + 30 + name_size + extra_size]


def _descriptor_size(raw: bytes, at: int, info: zipfile.ZipInfo, zip64: bool) -> int:
    """Length of the data descriptor at `at` that matches this entry's CRC and compressed size, or 0.
    Sizes are 8 bytes wide when the local header carries a zip64 extra field."""
    width = 8 if zip64 else 4
    for signature in (4, 0):
        if signature and raw[at:at + 4] != b'PK\x07\x08':
            continue
        if raw[at + signature:at + signature + 4] != struct.pack('<I', info.CRC):
            continue
        field = raw[at + signature + 4:at + signature + 4 + width]
        if len(field) == width and int.from_bytes(field, 'little') == info.compress_size:
            return signature + 4 + 2 * width
    return 0


def _deflate_slack(compressed: bytes) -> bytes:
    """Bytes after the end of a raw deflate stream, inside the entry's compressed size."""
    inflater = zlib.decompressobj(-15)
    pending = compressed
    while pending and not inflater.eof:
        inflater.decompress(pending, 1 << 20)
        pending = inflater.unconsumed_tail
    return inflater.unused_data if inflater.eof else b''


def _zip_uncovered(raw: bytes, infos, start_dir: int) -> list[tuple[int, bytes, str]]:
    """Bytes of a ZIP that no local header, entry data, data descriptor, central directory record, zip64
    record or end record covers, after the first entry (prefix bytes are reported apart) (S-3).
    Returns (offset, bytes, where)."""
    end = raw.rfind(b'PK\x05\x06')
    if end < 0:
        return []
    comment = struct.unpack_from('<H', raw, end + 20)[0] if end + 22 <= len(raw) else 0
    covered = [(end, min(len(raw), end + 22 + comment))]
    slack = []
    for info in infos:
        start = info.header_offset
        if raw[start:start + 4] != b'PK\x03\x04' or start + 30 > len(raw):
            continue
        name_size, extra_size = struct.unpack_from('<HH', raw, start + 26)
        data = start + 30 + name_size + extra_size
        stop = data + info.compress_size
        if info.flag_bits & 0x08:
            local_extra = raw[start + 30 + name_size:data]
            zip64 = any(header == 0x0001 for header, _ in _extra_fields(local_extra))
            stop += _descriptor_size(raw, stop, info, zip64)
        covered.append((start, stop))
        if info.compress_type == zipfile.ZIP_DEFLATED and not info.flag_bits & 0x01:
            extra = _deflate_slack(raw[data:data + info.compress_size])
            if extra:
                slack.append((data + info.compress_size - len(extra), extra,
                              'after the compressed data of ' + info.filename))
    at = start_dir
    for _ in infos:
        if raw[at:at + 4] != b'PK\x01\x02' or at + 46 > len(raw):
            break
        sizes = struct.unpack_from('<HHH', raw, at + 28)
        at += 46 + sum(sizes)
    covered.append((start_dir, at))
    if raw[at:at + 4] == b'PK\x06\x06' and at + 12 <= len(raw):  # zip64 end record, then its locator
        record = at + 12 + struct.unpack_from('<Q', raw, at + 4)[0]
        covered.append((at, record))
        if raw[record:record + 4] == b'PK\x06\x07':
            covered.append((record, record + 20))
    first = min((info.header_offset for info in infos), default=start_dir)
    gaps, cursor = [], first
    for low, high in sorted(covered):
        if low > cursor:
            gaps.append((cursor, raw[cursor:low], 'between records'))
        cursor = max(cursor, high)
    if cursor < len(raw):
        gaps.append((cursor, raw[cursor:], 'after the end record'))
    return gaps + slack


def _scan_zip(archive: zipfile.ZipFile, raw: bytes | None, prefix: str, markers, depth: int, out: list) -> None:
    with archive:
        infos = archive.infolist()
        root_depth = _root_depth(info.filename for info in infos)
        if archive.comment:
            _scan_meta(prefix + '(zip comment)', 'zip comment', archive.comment, markers, out)
        if raw is not None:
            first = min((info.header_offset for info in infos), default=archive.start_dir)
            if first > 0:
                out.append(_finding(prefix + '(prefix bytes)', 'prefix bytes', f'{first} bytes before the first entry'))
                _scan_meta(prefix + '(prefix bytes)', 'prefix bytes', raw[:first], markers, out)
            for offset, data, where in _zip_uncovered(raw, infos, archive.start_dir):
                label = prefix + '(uncovered bytes)'
                out.append(_finding(label, 'uncovered bytes', f'{len(data)} bytes at offset {offset}, {where}'))
                _scan_meta(label, 'uncovered bytes', data, markers, out)
        for info in infos:
            label = prefix + info.filename
            # zipfile cuts a name at its first NUL; orig_filename keeps the rest, which is scanned too (S-4).
            _scan_name(label, info.orig_filename, markers, root_depth, out, folder=info.is_dir())
            if info.comment:
                _scan_meta(label, 'entry comment', info.comment, markers, out)
            for extra in {info.extra, _local_extra(raw, info)}:
                if not extra:
                    continue
                _scan_meta(label, 'extra field', extra, markers, out)
                for header, payload in _extra_fields(extra):
                    owner = _unix_owner(header, payload)
                    if owner and any(owner):
                        out.append(_finding(label, 'zip owner', f'uid {owner[0]} gid {owner[1]} (nonzero)'))
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                out.append(_finding(label, 'symlink', 'ZIP entry is a symlink'))
                continue
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                out.append(_finding(label, 'encrypted', 'encrypted entry; its content was not scanned'))
                continue
            try:
                data = archive.read(info)
            except zipfile.BadZipFile as error:
                out.append(_finding(label, 'crc', str(error)[:200]))
                continue
            except (NotImplementedError, RuntimeError, zlib.error, lzma.LZMAError, EOFError, OSError) as error:
                out.append(_finding(label, 'unreadable entry', str(error)[:200]))
                continue
            _scan_blob(label, info.filename, data, markers, depth, out, root_depth)
        for name, reason in name_collisions(info.filename for info in infos).items():
            out.append(_finding(prefix + name, 'name collision', reason))


def scan_bytes(raw: bytes, *, name: str = '', markers=None, allow: tuple[str, ...] = ()) -> dict:
    """Scan ZIP bytes. `allow` globs mark expected magic findings (for example '*.dll'); nothing else."""
    markers = privacy_markers() if markers is None else tuple(markers)
    findings: list[dict] = []
    _scan_zip(zipfile.ZipFile(io.BytesIO(raw)), raw, '', markers, 0, findings)
    expected, rest = [], []
    for item in findings:
        inner = item['entry'].rsplit('!', 1)[-1]
        allowed = item['kind'] == 'magic' and any(
            fnmatch.fnmatchcase(item['entry'], pattern) or fnmatch.fnmatchcase(PurePosixPath(inner).name, pattern)
            for pattern in allow)
        (expected if allowed else rest).append(item)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = len(archive.infolist())
    counts: dict[str, int] = {}
    for item in rest:
        counts[item['kind']] = counts.get(item['kind'], 0) + 1
    return {'zip': name, 'zip_sha256': hashlib.sha256(raw).hexdigest(), 'entries': entries,
            'ok': not rest, 'finding_counts': dict(sorted(counts.items())), 'findings': rest,
            'expected': expected, 'markers': len(markers), 'allow': list(allow)}


def scan(path: os.PathLike | str, *, markers=None, allow: tuple[str, ...] = ()) -> dict:
    """Scan one ZIP file read-only."""
    path = Path(path)
    with open(path, 'rb') as stream:
        raw = stream.read()
    return scan_bytes(raw, name=path.name, markers=markers, allow=allow)


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
        except Exception as error:  # noqa: BLE001  (any failure is a failed scan, printed as JSON)
            report = {'zip': Path(name).name, 'ok': False, 'error': f'{type(error).__name__}: {error}'[:300]}
        after = os.stat(name)
        report['unchanged'] = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        print(json.dumps(report, indent=2))
        status |= 0 if report.get('ok') and report['unchanged'] else 1
    return status


if __name__ == '__main__':
    raise SystemExit(main())

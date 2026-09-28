"""Original-example identities and their reviewed current source locations."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tools/tests/examples/manifest.json'
PUBLIC = 'scripts/examples/'
INTERNAL = 'tools/tests/examples/fixtures/legacy/'
RETIRED = frozenset({
    'showcase/10_ahto_city_law.lua', 'showcase/20_sith_patrol_alarm.lua',
    'showcase/30_battle_meditation.lua', 'showcase/40_alignment_drift.lua',
    'showcase/50_enclave_arrival.lua', 'showcase/60_party_wounded.lua',
    'cursed/50_chaos_roulette.lua', 'cursed/60_rave.lua',
})


def relative_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', value):
        raise ValueError('invalid source path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != value or path.suffix != '.lua':
        raise ValueError('source path must be a normalized relative Lua file')
    return path


def source_for(entry, root=None):
    root = (ROOT if root is None else Path(root)).resolve()
    identity = relative_name(entry['path']).as_posix()
    source = relative_name(entry['source_path']).as_posix()
    retired = entry['disposition'] == 'retired_public'
    if entry['disposition'] not in {'retained', 'retired_public'}:
        raise ValueError('unknown example disposition')
    if source != (INTERNAL if retired else PUBLIC) + identity:
        raise ValueError('source path disagrees with identity/disposition')
    candidate = root / source
    if any(parent.is_symlink() for parent in [candidate, *candidate.parents] if parent != root and root in parent.parents):
        raise ValueError('source path must not contain symlinks')
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
        raise ValueError('missing or escaped example source')
    return candidate


def validate_inventory(manifest, root=None):
    root = ROOT if root is None else Path(root)
    if type(manifest.get('schema')) is not int or manifest['schema'] != 2:
        raise ValueError('example manifest schema must be 2')
    entries = manifest['examples']
    if type(manifest.get('inventory_count')) is not int or manifest['inventory_count'] != 41 or len(entries) != 41:
        raise ValueError('original41 inventory drift')
    identities = [e['path'] for e in entries]
    sources = [e['source_path'] for e in entries]
    if len(set(identities)) != 41 or len({s.casefold() for s in sources}) != 41:
        raise ValueError('duplicate example identity/source')
    if {e['path'] for e in entries if e['disposition'] == 'retired_public'} != RETIRED:
        raise ValueError('reviewed retirement set drift')
    for entry in entries:
        path = source_for(entry, root)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('source hash drift: ' + entry['path'])
        if entry['disposition'] == 'retired_public':
            note = entry.get('retirement', {})
            if not note.get('date') or not note.get('reason'):
                raise ValueError('retirement reason/date required')
            old = root / PUBLIC / entry['path']
            if old.exists() or old.is_symlink():
                raise ValueError('retired public source still exists')
    actual = {str(p.relative_to(root)) for prefix in (PUBLIC, INTERNAL)
              for p in (root / prefix).rglob('*.lua')}
    if actual != set(sources):
        raise ValueError('unmapped or missing Lua source inventory')
    return entries


def lua_source_map(entries):
    # All names already pass the restricted ASCII path grammar. JSON's quoted
    # strings are therefore also valid Lua literals (no unicode escapes).
    return 'return {\n' + ''.join('  [' + json.dumps(e['path']) + '] = ' + json.dumps(e['source_path']) + ',\n'
                                  for e in entries) + '}\n'


def validate_catalog(catalog, root=None):
    root = ROOT if root is None else Path(root)
    if catalog.get('schema') != 1 or catalog.get('featured') != []:
        raise ValueError('first curation batch does not promote featured demos')
    candidates = catalog.get('candidates')
    if not isinstance(candidates, list):
        raise ValueError('candidate list required')
    ids = set()
    for candidate in candidates:
        if not candidate.get('id') or candidate['id'] in ids or not candidate.get('review'):
            raise ValueError('candidate identity/review required')
        ids.add(candidate['id'])
        for name in [candidate['source_path'], *candidate['support_paths']]:
            relative_name(name)
            if not name.startswith('scripts/demos/'):
                raise ValueError('catalog may only include authored demo sources')
            path = root / name
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to((root / 'scripts/demos').resolve()):
                raise ValueError('missing or escaped catalog source')
    return candidates

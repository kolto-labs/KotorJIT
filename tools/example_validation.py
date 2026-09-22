#!/usr/bin/env python3
"""Hash-bound offline evidence for the exact shipped example inventory."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tools/tests/examples/manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, records):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    records.append({'command': [str(x) for x in command], 'exit_code': result.returncode,
                    'output': result.stdout})
    if result.returncode:
        raise RuntimeError(f'{command}:\n{result.stdout}')
    return result.stdout


def require(output, *patterns):
    for pattern in patterns:
        if not re.search(pattern, output, re.M):
            raise AssertionError(f'Missing assertion {pattern!r}:\n{output}')


def validate_live(evidence, entry):
    """All required predicates and artifact hashes must bind the current Lua bytes.

    This validates provenance structure, not the honesty of measured observations.
    Independent engine predicates and review remain the acceptance authority.
    """
    if evidence.get('schema') != 1 or evidence.get('path') != entry['path']:
        raise ValueError('wrong live schema or example')
    for field in ('source_sha256', 'deployed_sha256'):
        if evidence.get(field) != entry['sha256']:
            raise ValueError(f'stale or missing {field}')
    for field in ('run_id', 'started_utc', 'completed_utc', 'checkpoint', 'runtime_sha256', 'git_commit', 'dirty_diff_sha256'):
        if not evidence.get(field):
            raise ValueError(f'missing {field}')
    if evidence.get('clean_session') is not True:
        raise ValueError('poisoned, crashed or unclean live session')
    predicates = evidence.get('predicates', {})
    if any(predicates.get(p) is not True for p in entry['live']['required_predicates']):
        raise ValueError('unmet live predicates')
    artifacts = evidence.get('artifacts', [])
    if not artifacts:
        raise ValueError('no retained live artifacts')
    for artifact in artifacts:
        path = Path(artifact['path'])
        if not path.is_absolute() or not path.is_file() or digest(path) != artifact['sha256']:
            raise ValueError('missing or stale live artifact')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--luajit', default='luajit')
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--live-evidence', type=Path, help='JSON list of reviewed, current-byte live receipts')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    entries = manifest['examples']
    paths = [e['path'] for e in entries]
    actual = sorted(str(p.relative_to(ROOT / 'scripts/examples')) for p in (ROOT / 'scripts/examples').rglob('*.lua'))
    assert len(entries) == 41 and len(set(paths)) == 41 and sorted(paths) == actual, 'example inventory drift'
    for entry in entries:
        assert digest(ROOT / 'scripts/examples' / entry['path']) == entry['sha256'], f"source hash drift: {entry['path']}"
    # Source-level catalog guard complements runtime fixture assertions. It also
    # catches never-exercised branches using a native function as an NW routine.
    catalog = (ROOT / 'src/generated/routines_k1.inc').read_text()
    for entry in entries:
        source = (ROOT / 'scripts/examples' / entry['path']).read_text()
        for name in re.findall(r"(?:(?:q|nwscript\.call)\(|pcall\(\s*nwscript\.call,)\s*['\"](\w+)", source):
            assert '"' + name + '"' in catalog, f"Unknown K1 routine {name} in {entry['path']}"
    validation_files = [MANIFEST, Path(__file__), *sorted((ROOT / 'tools/tests/examples').glob('*.lua')),
                        ROOT / 'tools/tests/examples/evidence_test.py', ROOT / 'src/generated/routines_k1.inc']
    validation_hashes = {str(p.relative_to(ROOT)): digest(p) for p in validation_files}
    host_hash = digest(args.host.resolve())
    records = []
    # Compile every file in an isolated process without running its top-level code.
    for entry in entries:
        run([args.luajit, '-e', 'assert(loadfile(' + json.dumps('scripts/examples/' + entry['path']) + '))'], records)
    import sys
    run([sys.executable, 'tools/tests/examples/evidence_test.py'], records)
    run([args.luajit, '-v'], records)
    logic = run([args.luajit, 'tools/tests/examples/run.lua'], records)
    cases = {}
    for line in logic.splitlines():
        if line.startswith('PASS\t'):
            _, path, name = line.split('\t', 2)
            cases.setdefault(path, []).append(name)
    # Runtime host output is assertion-checked; a zero process exit is insufficient.
    host = args.host.resolve()
    for directory, event, extra, expectations in [
        ('arbitration', 'OnRunScript', ['k_def_heartbt01', '0', '0'],
         [r'called\s+: 6$', r'abstained\s+: 2$', r'errored\s+: 0$', r'ignored\s+: 3 ', r'claimed by\s+: 25_claims_via_string$', r'value\s+: true$',
          r'\[30_claims_false\].*relevant=false', r'\[40_too_late\].*relevant=false', r'\[50_number_two_is_false\].*relevant=false']),
        ('edge_fallback', 'OnRunScript', ['k_def_heartbt01', '0', '0'],
         [r'called\s+: 1$', r'abstained\s+: 1$', r'no \(fallback applied\)', r'value\s+: true$']),
        ('edge_number_two', 'OnRunScript', ['k_def_heartbt01', '0', '0'],
         [r'claimed by\s+: 50_number_two_is_false$', r'value\s+: false$', 'handler is SUPPRESSED']),
        ('edge_quarantine', 'OnTick', ['0', '--repeat', '4'],
         [r'called\s+: 0$', r'quarantined after 3 errors'])]:
        output = run([host, 'scripts/examples/' + directory, event, *extra], records)
        require(output, *expectations)
        if directory == 'edge_quarantine':
            assert output.count('[always_errors] OnTick:') == 3
        for path in paths:
            if path.startswith(directory + '/'):
                cases[path] = ['real Lua host dispatch assertions: ' + directory]
    output = run([args.luajit, 'scripts/examples/multiplayer/10_avatar_sync_test.lua'], records)
    require(output, 'all checks passed')
    for path in paths:
        if path.startswith('multiplayer/'):
            cases[path] = ['existing multiplayer mocked socket/engine regression']
    assert set(cases) == set(paths), 'missing behavior coverage'
    live = {}
    if args.live_evidence:
        for evidence in json.loads(args.live_evidence.read_text()):
            path = evidence['path']
            entry = next(e for e in entries if e['path'] == path)
            if entry['live']['status'] == 'not_applicable':
                raise ValueError('real-host fixture does not need engine evidence')
            validate_live(evidence, entry)
            if path in live:
                raise ValueError('duplicate live evidence')
            live[path] = evidence
    outputs = []
    for entry in entries:
        path = entry['path']
        outputs.append({**entry, 'syntax': {'status': 'passed', 'evidence': 'loadfile compile in commands'},
                        'host': {'status': 'passed', 'tier': entry['host']['tier'], 'cases': cases[path]},
                        'live': {**entry['live'], **({'status': 'passed', 'evidence': live[path]} if path in live else {})}})
    # Refuse mixed snapshots if a developer changes sources during the run.
    for entry in entries:
        assert digest(ROOT / 'scripts/examples' / entry['path']) == entry['sha256'], 'example changed during validation'
    assert {str(p.relative_to(ROOT)): digest(p) for p in validation_files} == validation_hashes, 'tests changed during validation'
    assert digest(host) == host_hash, 'host executable changed during validation'
    receipt = {'schema': 1, 'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'git_commit': run(['git', 'rev-parse', 'HEAD'], records).strip(),
               'dirty_diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD', '--binary'], cwd=ROOT)).hexdigest(),
               'host_binary': {'path': str(host), 'sha256': digest(host)},
               'validation_sources': validation_hashes,
               'scope': 'offline Lua decisions and requests; no engine proof unless separately attached',
               'examples': outputs, 'commands': records}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=args.receipt.parent, delete=False) as handle:
        json.dump(receipt, handle, indent=2); handle.write('\n'); temporary = Path(handle.name)
    temporary.replace(args.receipt)
    print(f'PASS: 41 syntax, 41 host-covered files, {sum(map(len,cases.values()))} per-file cases; {len(live)} live receipts attached')
    print(args.receipt)


if __name__ == '__main__':
    main()

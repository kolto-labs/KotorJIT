"""Recheck the frozen host adapter executables and their exact source manifests."""
import hashlib
import json
from pathlib import Path
import resource
import subprocess

SCRATCH = Path('/home/brunner56/kp-live-20260922/pl5-review-scratch')
CASES = (
    ('actual_finish_fixture', 0, 'step_load_completion -> finish_load call path: PASS'),
    ('actual_finish_fixture_expectation_mutant', -6, '!adapter.pause_machine_.loading()'),
    ('onfail_fixture', 0, 'load_save -> on_fail call path: PASS'),
    ('onfail_mutant_fixture', -6, '!a.pause_machine_.loading()'),
)

def disable_core_files():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

verified = {}
for manifest_name in ('actual-linkage-manifest.sha256', 'onfail-linkage-manifest.sha256'):
    lines = (SCRATCH / manifest_name).read_text().splitlines()
    for line in lines:
        expected, path = line.split(maxsplit=1)
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    verified[manifest_name] = len(lines)

results = []
for name, expected_rc, marker in CASES:
    result = subprocess.run([str(SCRATCH / name)], cwd=SCRATCH, text=True,
                            capture_output=True, timeout=10, preexec_fn=disable_core_files)
    output = result.stdout + result.stderr
    assert result.returncode == expected_rc, (name, result.returncode, output)
    assert marker in output, (name, output)
    results.append({'binary': name, 'returncode': result.returncode, 'output': output})
    print(name, 'verified', result.returncode)

Path('/home/brunner56/kp-live-20260922/root-pause-linkage-check.json').write_text(
    json.dumps({'verified_manifests': verified, 'cases': results}, indent=2) + '\n')

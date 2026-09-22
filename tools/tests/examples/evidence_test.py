"""Provenance acceptance must fail closed independently of Lua behavior."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('example_validation', Path(__file__).parents[2] / 'example_validation.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class LiveEvidenceTests(unittest.TestCase):
    def test_current_receipt_and_rejections(self):
        with tempfile.TemporaryDirectory() as folder:
            artifact = Path(folder) / 'state.json'
            artifact.write_text('{"measured": true}')
            entry = {'path': 'sample.lua', 'sha256': 'current',
                     'live': {'required_predicates': ['independent state', 'clean recording']}}
            valid = {'schema': 1, 'path': 'sample.lua', 'source_sha256': 'current',
                     'deployed_sha256': 'current', 'clean_session': True,
                     'predicates': {'independent state': True, 'clean recording': True},
                     'artifacts': [{'path': str(artifact), 'sha256': validation.digest(artifact)}]}
            for field in ('run_id', 'started_utc', 'completed_utc', 'checkpoint', 'runtime_sha256', 'git_commit', 'dirty_diff_sha256'):
                valid[field] = 'recorded'
            validation.validate_live(valid, entry)
            mutations = [
                ('source_sha256', 'historical'), ('deployed_sha256', 'historical'),
                ('clean_session', False), ('clean_session', 1), ('runtime_sha256', ''),
                ('predicates', {'independent state': True}),
                ('predicates', {'independent state': 1, 'clean recording': True}),
                ('artifacts', []), ('schema', 0), ('path', 'different.lua'),
            ]
            for field, value in mutations:
                with self.subTest(field=field, value=value):
                    bad = copy.deepcopy(valid); bad[field] = value
                    with self.assertRaises(ValueError):
                        validation.validate_live(bad, entry)
            artifact.write_text('changed after receipt')
            with self.assertRaises(ValueError):
                validation.validate_live(valid, entry)


if __name__ == '__main__':
    unittest.main()

"""Provenance acceptance must fail closed independently of Lua behavior."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
import hashlib
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).parents[2]))

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


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(validation.MANIFEST.read_text())

    def test_exact_retirement_and_regression_inventory(self):
        from example_inventory import RETIRED
        entries = validation.validate_inventory(self.manifest)
        retired = [e for e in entries if e['disposition'] == 'retired_public']
        self.assertEqual({e['path'] for e in retired}, RETIRED)
        self.assertEqual(len(entries), 41)
        self.assertEqual(len(retired), 8)
        for entry in retired:
            self.assertFalse((validation.ROOT / 'scripts/examples' / entry['path']).exists())
            self.assertEqual(validation.digest(validation.source_for(entry)), entry['sha256'])
            self.assertEqual(entry['live']['status'], 'unvalidated')
            self.assertTrue(entry['live']['required_predicates'])
        validation.validate_catalog(json.loads((validation.ROOT / 'scripts/demos/catalog.json').read_text()))

    def test_schema_mapping_and_hash_rejections(self):
        for field, value in [('schema', 1), ('inventory_count', 33)]:
            bad = copy.deepcopy(self.manifest); bad[field] = value
            with self.assertRaises(ValueError): validation.validate_inventory(bad)
        entry = self.manifest['examples'][0]
        for source in ('../outside.lua', '/tmp/outside.lua', 'scripts/examples/../outside.lua',
                       'scripts/examples/wrong.lua', 'scripts/examples/evil\\name.lua'):
            bad = dict(entry, source_path=source)
            with self.subTest(source=source), self.assertRaises(ValueError): validation.source_for(bad)
        bad = copy.deepcopy(self.manifest); bad['examples'][0]['sha256'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'hash drift'): validation.validate_inventory(bad)
        bad = copy.deepcopy(self.manifest); bad['examples'][1]['source_path'] = bad['examples'][0]['source_path']
        with self.assertRaisesRegex(ValueError, 'duplicate'): validation.validate_inventory(bad)

    def test_symlink_and_unmapped_or_public_copy_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for entry in self.manifest['examples']:
                target = root / entry['source_path']; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(validation.source_for(entry), target)
            validation.validate_inventory(self.manifest, root)
            retired = next(e for e in self.manifest['examples'] if e['disposition'] == 'retired_public')
            old = root / 'scripts/examples' / retired['path']; old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text('-- must not return to public tree')
            with self.assertRaisesRegex(ValueError, 'public source'): validation.validate_inventory(self.manifest, root)
            old.unlink()
            extra = root / 'tools/tests/examples/fixtures/legacy/extra.lua'; extra.write_text('-- unmapped')
            with self.assertRaisesRegex(ValueError, 'inventory'): validation.validate_inventory(self.manifest, root)
            extra.unlink()
            target = root / retired['source_path']; target.unlink(); target.symlink_to(validation.source_for(retired))
            with self.assertRaisesRegex(ValueError, 'symlink'): validation.validate_inventory(self.manifest, root)

    def test_retired_deploy_requests_fail_before_game_access(self):
        for script, name in [('deploy_showcase.sh', '10_ahto_city_law'),
                             ('record_showcase.sh', 'all'),
                             ('record_cursed.sh', '60_rave'), ('record_cursed.sh', '50_chaos_roulette')]:
            result = subprocess.run(['bash', str(validation.ROOT / 'scripts/harness' / script), name],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('retired', result.stderr)

    def test_retired_identity_still_requires_live_predicates(self):
        entry = next(e for e in self.manifest['examples'] if e['disposition'] == 'retired_public')
        evidence = {'schema': 1, 'path': entry['path'], 'source_sha256': entry['sha256'],
                    'deployed_sha256': entry['sha256'], 'clean_session': True, 'predicates': {}}
        for field in ('run_id', 'started_utc', 'completed_utc', 'checkpoint', 'runtime_sha256', 'git_commit', 'dirty_diff_sha256'):
            evidence[field] = 'recorded'
        with self.assertRaisesRegex(ValueError, 'unmet live predicates'):
            validation.validate_live(evidence, entry)


class ConfiguredEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.manifest = json.loads(validation.MANIFEST.read_text())['examples']

    def artifact(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return {'path': str(path), 'sha256': validation.digest(path)}

    def evidence(self, path, values):
        entry = next(e for e in self.manifest if e['path'] == path)
        config = {'schema': 1, 'path': path, 'values': values}
        stock = validation.source_for(entry).read_bytes()
        effective, delta = validation.effective_source(entry, stock, config)
        sha = hashlib.sha256(effective).hexdigest()
        receipt = {'schema': 1, 'path': path, 'source_sha256': entry['sha256'],
                   'deployed_sha256': sha, 'configured_sha256': sha, 'clean_session': True,
                   'predicates': dict.fromkeys(entry['live']['required_predicates'], True),
                   'artifacts': [self.artifact('state.json', b'{"observed": true}')],
                   'configuration': {
                     'artifact': self.artifact('configuration.json', json.dumps(config).encode()),
                     'diff': self.artifact('configuration.diff', delta),
                     'effective_source': self.artifact('effective.lua', effective),
                     'deployed_source': self.artifact('deployed.lua', effective)}}
        for field in ('run_id', 'started_utc', 'completed_utc', 'checkpoint', 'runtime_sha256', 'git_commit', 'dirty_diff_sha256'):
            receipt[field] = 'recorded'
        return entry, receipt

    def test_reviewed_transition_import(self):
        entry, receipt = self.evidence('harness/100_module_transition.lua', {'INSPECT': False})
        validation.validate_live(receipt, entry)
        self.assertNotEqual(receipt['source_sha256'], receipt['deployed_sha256'])
        self.assertIn(b'local INSPECT = false', Path(receipt['configuration']['deployed_source']['path']).read_bytes())

    def test_documented_configuration_matrix(self):
        variants = {
            '10_world_probe.lua': {'RADIUS': 25},
            '20_dialog_state.lua': {'PARTNER_TAG': 'bastila'},
            '30_move_to.lua': {'TARGET_TAG': None, 'OFFSET': {'x': 2, 'y': -3, 'z': 0}, 'RANGE': 2},
            '40_attack_nearest.lua': {'RADIUS': 20},
            '50_doors.lua': {'OPEN': True, 'TAG': 'end_door01'},
            '60_area_dump.lua': {'OBJECT_TYPE': 8, 'MAX': 20},
            '80_signal_event.lua': {'TARGET': 'end_door01', 'EVENT': 21},
            '90_run_script.lua': {'TARGET_TAG': None, 'SCRIPT': 'k_pman_npcstart'},
            '100_module_transition.lua': {'MODULE': 'end_m01aa', 'WAYPOINT': 'from_01b', 'DOOR_TAG': 'end_door01', 'INSPECT': False},
            '110_loot_container.lua': {'TAG': 'footlker'},
        }
        for name, values in variants.items():
            with self.subTest(name=name):
                entry, receipt = self.evidence('harness/' + name, values)
                validation.validate_live(receipt, entry)
                configured_path = receipt['configuration']['effective_source']['path']
                subprocess.run(['luajit', '-e', 'assert(loadfile(' + json.dumps(configured_path) + '))'], check=True)
        entry, receipt = self.evidence('harness/30_move_to.lua', {'TARGET_TAG': 'bastila'})
        validation.validate_live(receipt, entry)

    def test_reviewed_multiplayer_loopback_configuration(self):
        entry, receipt = self.evidence('multiplayer/10_avatar_sync.lua', {
            'LOCAL_NAME': 'Validation Peer', 'LISTEN_PORT': 39131,
            'PEERS': [{'host': '127.0.0.1', 'port': 39132}]})
        validation.validate_live(receipt, entry)
        text = Path(receipt['configuration']['effective_source']['path']).read_text()
        self.assertIn('local LOCAL_NAME    = "Validation Peer"', text)
        self.assertIn('{ host = "127.0.0.1", port = 39132 }', text)
        # A single game's loopback peer does not satisfy production acceptance.
        receipt['predicates'].pop('multiplayer.10_avatar_sync.two_game_clients')
        with self.assertRaisesRegex(ValueError, 'unmet live predicates'):
            validation.validate_live(receipt, entry)
        for peers in ([{'host': 'not-an-ip', 'port': 39132}],
                      [{'host': '127.0.0.1', 'port': 0}],
                      [{'host': '127.0.0.1', 'port': True}],
                      [{'host': '127.0.0.1', 'port': 39132}] * 2,
                      [{'host': '127.0.0.1', 'port': 39132, 'code': 'bad'}]):
            with self.subTest(peers=peers), self.assertRaises(ValueError):
                self.evidence('multiplayer/10_avatar_sync.lua', {'PEERS': peers})

    def test_tamper_and_wrong_deployment_rejected(self):
        for target in ('artifact', 'diff', 'effective_source', 'deployed_source'):
            for update_hash in (False, True):
                with self.subTest(target=target, update_hash=update_hash):
                    entry, receipt = self.evidence('harness/100_module_transition.lua', {'INSPECT': False})
                    artifact = receipt['configuration'][target]
                    path = Path(artifact['path'])
                    if target == 'artifact':
                        changed = json.loads(path.read_text()); changed['values']['INSPECT'] = True
                        path.write_text(json.dumps(changed))
                    else:
                        path.write_bytes(path.read_bytes() + b'\n-- unrelated modification\n')
                    if update_hash:
                        artifact['sha256'] = validation.digest(path)
                    with self.assertRaises(ValueError):
                        validation.validate_live(receipt, entry)
        entry, receipt = self.evidence('harness/100_module_transition.lua', {'INSPECT': False})
        receipt['deployed_sha256'] = entry['sha256']
        with self.assertRaises(ValueError):
            validation.validate_live(receipt, entry)
        entry, receipt = self.evidence('harness/100_module_transition.lua', {'INSPECT': False})
        receipt.pop('configuration')
        with self.assertRaises(ValueError):
            validation.validate_live(receipt, entry)

    def test_consistently_rehashed_unrelated_edit_rejected(self):
        entry, receipt = self.evidence('harness/100_module_transition.lua', {'INSPECT': False})
        config = receipt['configuration']
        modified = Path(config['effective_source']['path']).read_bytes() + b'\nnwscript.call("DestroyObject", 1)\n'
        config['effective_source'] = self.artifact('effective.lua', modified)
        config['deployed_source'] = self.artifact('deployed.lua', modified)
        receipt['configured_sha256'] = receipt['deployed_sha256'] = hashlib.sha256(modified).hexdigest()
        with self.assertRaisesRegex(ValueError, 'differs from reviewed transformation'):
            validation.validate_live(receipt, entry)

    def test_ambiguous_configuration_json_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate configuration key'):
            validation.configuration_json(b'{"schema":1,"path":"harness/100_module_transition.lua","values":{"INSPECT":true,"INSPECT":false}}')

    def test_unreviewed_keys_and_lua_injection_rejected(self):
        for values in ({'UNREVIEWED': False}, {'INSPECT': 0}, {'MODULE': 'x"; error("injected")'}, {}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.evidence('harness/100_module_transition.lua', values)
        for values in ({'RADIUS': float('nan')}, {'RADIUS': 251}, {'RADIUS': True}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.evidence('harness/40_attack_nearest.lua', values)

    def test_missing_concrete_outcome_rejected(self):
        entry, receipt = self.evidence('harness/100_module_transition.lua', {'INSPECT': False})
        predicate = next(p for p in entry['live']['required_predicates'] if 'target_module' in p)
        receipt['predicates'].pop(predicate)
        with self.assertRaisesRegex(ValueError, 'unmet live predicates'):
            validation.validate_live(receipt, entry)


if __name__ == '__main__':
    unittest.main()

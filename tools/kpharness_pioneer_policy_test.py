#!/usr/bin/env python3
"""Pioneer attached-policy/transaction regressions, synthetic engine only."""
import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/harness'))
from kpharness import pioneer as P, scenario as S


class Channel:
    def __init__(self):
        self.scale = 4.0
        self.cursor = 0
        self.calls = []
        self.identity = dict(live=True, pid=123, build='synthetic-k1', version='test', uptime_ms=100)
        self.action = None

    def status(self):
        return dict(self.identity)

    def lua(self, code, **kwargs):
        self.calls.append(('lua', code, self.scale))
        if code == 'return kp.game_speed()':
            return {'values': [self.scale]}
        if self.action:
            self.action()
        return {'values': [42]}

    def request(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command == 'speed':
            self.scale = kwargs['scale']
            return {'scale': self.scale}
        raise AssertionError(command)

    def events(self, **kwargs):
        return []


class PioneerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'route.toml'
        self.original = b'# preserve this comment\r\ntarget="k1"\r\n[execution]\r\ngame_speed=1.0\r\n'
        self.out.write_bytes(self.original)
        self.ch = Channel()
        self.session = types.SimpleNamespace(target='k1', started=12.5, port=12345,
            run_dir=str(self.root), game_dir=str(self.root), launcher_pid=99, build='host-build',
            process_name='synthetic', save_dir='')
        self.step = {'do': 'lua', 'code': 'return 42'}

    def execute(self):
        return P.execute_pending(self.out, self.ch, self.session, self.step, log=lambda _: None)

    def test_real_shared_dispatch_applies_one_and_restores_prior_speed(self):
        result = self.execute()
        self.assertEqual(result.status, 'ok')
        self.assertIn(('lua', 'return 42', 1.0), self.ch.calls)
        self.assertEqual([c for c in self.ch.calls if c[0] == 'speed'],
                         [('speed', {'scale': 1.0}), ('speed', {'scale': 4.0})])
        self.assertEqual(self.ch.scale, 4.0)
        pending = P.load_pending(self.out)
        self.assertEqual(pending.phase, 'executed')
        self.assertEqual(pending.provenance['settings_sha256'], P._json_hash(P._load_header_only(self.out).settings))
        self.assertEqual(self.out.read_bytes(), self.original)

    def test_default_acceleration_uses_same_runner_configuration(self):
        self.out.write_text('target="k1"\n')
        self.execute()
        self.assertIn(('lua', 'return 42', 16.0), self.ch.calls)
        self.assertEqual(self.ch.scale, 4.0)

    def test_explicit_step_speed_change_is_not_overwritten(self):
        self.step = {'do': 'speed', 'scale': 3.0}
        self.execute()
        self.assertEqual(self.ch.scale, 3.0)

    def test_explicit_speed_equal_to_route_policy_is_still_retained(self):
        self.step = {'do': 'speed', 'scale': 1.0}
        self.execute()
        self.assertEqual(self.ch.scale, 1.0)

    def test_dispatch_exception_restores_owned_policy_and_leaves_issued_receipt(self):
        with mock.patch.object(S.ScenarioRunner, 'run_step', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(P.PioneerError, 'uncertain'):
                self.execute()
        self.assertEqual(self.ch.scale, 4.0)
        self.assertEqual(P.load_pending(self.out).phase, 'issued')
        with self.assertRaises(P.PioneerError):
            P.commit_pending(self.out, self.ch, self.session, force=True)

    def test_failed_restoration_does_not_produce_committable_success(self):
        original = self.ch.request
        def request(command, **kw):
            if command == 'speed' and kw['scale'] == 4.0:
                raise OSError('lost restoration response')
            return original(command, **kw)
        self.ch.request = request
        with self.assertRaisesRegex(P.PioneerError, 'uncertain'):
            self.execute()
        self.assertEqual(P.load_pending(self.out).phase, 'issued')

    def test_session_change_during_step_prevents_restore_into_foreign_runtime(self):
        self.ch.action = lambda: self.ch.identity.update(pid=456)
        with self.assertRaisesRegex(P.PioneerError, 'session changed'):
            self.execute()
        self.assertEqual([c for c in self.ch.calls if c[0] == 'speed'], [('speed', {'scale': 1.0})])

    def test_commit_preserves_author_text_and_retry_never_duplicates(self):
        self.execute()
        self.assertTrue(P.commit_pending(self.out, self.ch, self.session))
        data = self.out.read_bytes()
        self.assertTrue(data.startswith(self.original))
        self.assertEqual(len(S.Scenario.load(self.out).steps), 1)
        self.assertFalse(P.commit_pending(self.out, self.ch, self.session))
        self.assertEqual(self.out.read_bytes(), data)

    def test_retry_after_route_replace_before_final_receipt(self):
        self.execute()
        original = P.save_pending
        def save(out, pending):
            if pending.phase == 'committed':
                raise OSError('crash after route publish')
            return original(out, pending)
        with mock.patch.object(P, 'save_pending', side_effect=save):
            with self.assertRaises(OSError):
                P.commit_pending(self.out, self.ch, self.session)
        self.assertEqual(P.load_pending(self.out).phase, 'committing')
        self.assertFalse(P.commit_pending(self.out, self.ch, self.session))
        self.assertEqual(len(S.Scenario.load(self.out).steps), 1)

    def test_failed_route_replace_can_retry_once(self):
        self.execute()
        original = P._atomic_write
        def write(path, data):
            if path == self.out:
                raise OSError('replace failure')
            return original(path, data)
        with mock.patch.object(P, '_atomic_write', side_effect=write):
            with self.assertRaises(OSError):
                P.commit_pending(self.out, self.ch, self.session)
        self.assertEqual(self.out.read_bytes(), self.original)
        self.assertTrue(P.commit_pending(self.out, self.ch, self.session))
        self.assertEqual(len(S.Scenario.load(self.out).steps), 1)

    def test_stale_route_and_foreign_session_rejected_even_force(self):
        self.execute()
        for changed in (self.original + b'# changed\n', self.original.replace(b'1.0', b'2.0')):
            self.out.write_bytes(changed)
            with self.assertRaises(P.PioneerError):
                P.commit_pending(self.out, self.ch, self.session, force=True)
            self.assertEqual(self.out.read_bytes(), changed)
        self.out.write_bytes(self.original)
        for key, value in [('pid', 456), ('build', 'different'), ('uptime_ms', 1)]:
            old = self.ch.identity[key]; self.ch.identity[key] = value
            with self.assertRaises(P.PioneerError):
                P.commit_pending(self.out, self.ch, self.session, force=True)
            self.ch.identity[key] = old
        self.session.started += 1
        with self.assertRaises(P.PioneerError):
            P.commit_pending(self.out, self.ch, self.session)

    def test_malformed_and_legacy_pending_cannot_commit(self):
        self.execute()
        valid = P.load_pending(self.out).to_dict()
        for change in [lambda d: d.update(provenance={}),
                       lambda d: d['result'].update(status='imaginary'),
                       lambda d: d['step'].update(code='different'),
                       lambda d: d.update(phase='issued'),
                       lambda d: d['provenance'].pop('candidate_sha256'),
                       lambda d: d['provenance'].update(session=None),
                       lambda d: d.update(recorded_at=float('nan'))]:
            data = copy.deepcopy(valid); change(data)
            P._pending_path(self.out).write_text(json.dumps(data))
            with self.assertRaises(P.PioneerError):
                P.commit_pending(self.out, self.ch, self.session, force=True)
            self.assertEqual(self.out.read_bytes(), self.original)

    def test_route_change_during_live_step_is_not_committable(self):
        self.ch.action = lambda: self.out.write_bytes(self.original + b'# concurrent edit\n')
        with self.assertRaisesRegex(P.PioneerError, 'route or attached session changed'):
            self.execute()
        self.assertEqual(P.load_pending(self.out).phase, 'issued')
        with self.assertRaises(P.PioneerError):
            P.commit_pending(self.out, self.ch, self.session, force=True)

    def test_symlink_route_refused_before_live_calls(self):
        target = self.root / 'original.toml'
        self.out.rename(target)
        self.out.symlink_to(target)
        with self.assertRaisesRegex(P.PioneerError, 'symlink'):
            self.execute()
        self.assertEqual(self.ch.calls, [])
        self.assertEqual(target.read_bytes(), self.original)

    def test_cli_uses_transaction_and_labels_discard_metadata_only(self):
        import contextlib
        import io
        from kpharness import cli
        channel = mock.MagicMock()
        channel.__enter__.return_value = self.ch
        output = io.StringIO()
        with mock.patch.object(cli, '_info', return_value=self.session), \
                mock.patch.object(cli, 'Channel', return_value=channel), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(['pioneer', 'step', '--out', str(self.out), json.dumps(self.step)]), 0)
            self.assertEqual(cli.main(['pioneer', 'commit', '--out', str(self.out)]), 0)
            self.assertEqual(cli.main(['pioneer', 'commit', '--out', str(self.out)]), 0)
            self.assertEqual(cli.main(['pioneer', 'discard', '--out', str(self.out)]), 0)
        self.assertEqual(len(S.Scenario.load(self.out).steps), 1)
        self.assertIn('NOT undone', output.getvalue())
        self.assertIn('no duplicate append', output.getvalue())

    def test_second_step_rejected_until_pending_resolved(self):
        self.execute()
        count = len(self.ch.calls)
        with self.assertRaisesRegex(P.PioneerError, 'existing pending'):
            self.execute()
        self.assertEqual(len(self.ch.calls), count)
        P.discard_pending(self.out)
        self.assertIsNone(P.load_pending(self.out))
        self.assertEqual(len(self.ch.calls), count)  # discard never calls engine/rewind

    def test_issued_receipt_precedes_live_action_and_lock_excludes_other_writer(self):
        def action():
            self.assertEqual(P.load_pending(self.out).phase, 'issued')
            with self.assertRaisesRegex(P.PioneerError, 'owns this route'):
                with P.route_lock(self.out):
                    self.fail('second writer entered')
        self.ch.action = action
        self.execute()

    def test_windows_lock_adapter_and_contention(self):
        import os
        module = types.SimpleNamespace(LK_NBLCK=2, locking=mock.Mock())
        lock_path = self.root / 'windows.lock'
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with mock.patch.object(P.sys, 'platform', 'win32'), mock.patch.dict(sys.modules, msvcrt=module):
                P._lock_file(fd)
                module.locking.assert_called_once_with(fd, 2, 1)
                self.assertEqual(os.fstat(fd).st_size, 1)
                module.locking.side_effect = OSError('locked')
                with self.assertRaisesRegex(P.PioneerError, 'locking failed'):
                    P._lock_file(fd)
        finally:
            os.close(fd)

    def test_windows_atomic_replace_skips_unsupported_directory_fsync(self):
        with mock.patch.object(P.sys, 'platform', 'win32'):
            P._atomic_write(self.out, b'new bytes')
            with mock.patch.object(P.os, 'open') as opening:
                P._sync_directory(self.root)
                opening.assert_not_called()
        self.assertEqual(self.out.read_bytes(), b'new bytes')

    def test_init_cannot_replace_route_while_transaction_lock_held(self):
        with P.route_lock(self.out):
            with self.assertRaisesRegex(P.PioneerError, 'owns this route'):
                P.init_route(self.out, target='k1', name='overwrite', force=True)
        self.assertEqual(self.out.read_bytes(), self.original)

    def test_wrong_target_and_unrenderable_step_fail_before_mutation(self):
        self.session.target = 'k2'
        with self.assertRaises(P.PioneerError):
            self.execute()
        self.assertEqual(self.ch.calls, [])
        self.session.target = 'k1'; self.step['nested'] = {'bad': True}
        with self.assertRaises(P.PioneerError):
            self.execute()
        self.assertEqual(self.ch.calls, [])


if __name__ == '__main__':
    unittest.main()

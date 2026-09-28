#!/usr/bin/env python3
"""Task 7 host-only lifecycle regressions. Never launches a display or game."""
import json
import os
import signal
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/harness'))
from kpharness import gamescope_xwayland as G, gamescope_processes as P, creative_wine as W
from kpharness.display_backends import ProcessIdentity


class LifecycleTests(unittest.TestCase):
    def fixture(self, *, descendant=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        relations = {200: (1, 200, 200, 'leader')}
        states = {200: 'S'}
        if descendant:
            relations[202] = (200, 200, 200, 'descendant'); states[202] = 'S'
        tick = [0.0]
        process = mock.Mock(pid=200)
        def poll():
            if states.get(200) == 'Z':
                relations.pop(200, None); states.pop(200, None)
            return None if 200 in relations else 0
        process.poll.side_effect = poll
        def sleep(seconds): tick[0] += seconds
        lease = G.GamescopeXwaylandLease(root, 800, 600, source_env={},
            monotonic=lambda: tick[0], sleep=sleep, controller_factory=lambda: None,
            relationship_reader=lambda pid: relations[pid],
            start_reader=lambda pid: relations[pid][3],
            pid_reader=lambda: list(relations), state_reader=lambda pid: states[pid])
        lease.process = process; lease.owner = ProcessIdentity(200, 'leader')
        lease.pgid = lease.session_id = 200
        lease.candidate_display = ':9191'
        self.addCleanup(lambda: lease.log.close() if lease.log is not None else None)
        return lease, process, relations, states, tick

    def test_s_to_z_leader_is_reaped_before_survivor_check(self):
        lease, process, relations, states, tick = self.fixture()
        def kill(identity, sig, reader): states[200] = 'Z'
        with mock.patch.object(G, 'signal_identity', side_effect=kill) as killpg:
            lease.close(); lease.close()
        self.assertEqual([(c.args[0].pid, c.args[1]) for c in killpg.call_args_list], [(200, signal.SIGTERM)])
        self.assertNotIn(200, relations)
        self.assertLess(tick[0], 1)
        self.assertEqual(lease.cleanup_attempts, [{'attempt': 1, 'status': 'passed'}])

    def test_live_unpublished_descendant_fails_bounded_cleanup(self):
        lease, process, relations, states, tick = self.fixture(descendant=True)
        def kill(identity, sig, reader):
            if 200 in states: states[200] = 'Z'
        with mock.patch.object(G, 'signal_identity', side_effect=kill) as killpg:
            with self.assertRaisesRegex(RuntimeError, 'survived SIGKILL'): lease.close()
        self.assertEqual([(c.args[0].pid, c.args[1]) for c in killpg.call_args_list], [(200, signal.SIGTERM), (202, signal.SIGTERM), (202, signal.SIGKILL)])
        self.assertLess(tick[0], 11)
        self.assertEqual(states[202], 'S')
        relations.clear(); states.clear()
        lease.close(); lease.close()
        self.assertEqual([item['status'] for item in lease.cleanup_attempts], ['failed', 'passed'])

    def test_recycled_leader_refuses_even_with_live_child(self):
        lease, _, relations, _, _ = self.fixture(descendant=True)
        relations[200] = (1, 200, 200, 'recycled')
        with mock.patch.object(G, 'signal_identity') as killpg:
            with self.assertRaisesRegex(RuntimeError, 'identity changed'): lease.close()
        killpg.assert_not_called()

    def test_unanchored_group_retry_never_promotes_observation_to_ownership(self):
        lease, process, relations, states, _ = self.fixture(descendant=True)
        relations.pop(200); states.pop(200)
        with mock.patch.object(G, 'signal_identity') as killpg:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'surviving owned identity'): lease.close()
        killpg.assert_not_called()
        self.assertNotIn(202, lease._known_members)

    def test_unreadable_recorded_child_fails_closed_then_readable_retry_cleans(self):
        lease, process, relations, states, _ = self.fixture(descendant=True)
        lease._known_members[202] = ProcessIdentity(202, 'descendant')
        relations.pop(200); states.pop(200)
        failure = [None]
        def relationship(pid):
            if pid == 202 and failure[0] is not None:
                raise failure[0]
            return relations[pid]
        lease._relationship_reader = relationship
        with mock.patch.object(G, 'signal_identity') as killpg:
            for error in (PermissionError('denied'), RuntimeError('malformed process relationship'),
                          OSError(5, 'transient I/O failure')):
                failure[0] = error
                with self.assertRaisesRegex(RuntimeError, 'cannot verify recorded Gamescope member PID 202'):
                    lease.close()
                self.assertFalse(lease._closed)
            killpg.assert_not_called()
        failure[0] = None
        def kill(*args): relations.clear(); states.clear()
        with mock.patch.object(G, 'signal_identity', side_effect=kill) as killpg:
            lease.close(); lease.close()
        self.assertEqual([(c.args[0].pid, c.args[1]) for c in killpg.call_args_list], [(202, signal.SIGTERM)])
        evidence = json.loads(lease.evidence_path.read_text())
        self.assertEqual([item['status'] for item in evidence['cleanup_attempts']],
                         ['failed', 'failed', 'failed', 'passed'])
        for attempt, name in zip(evidence['cleanup_attempts'], ('PermissionError', 'RuntimeError', 'OSError')):
            self.assertIn(name, attempt['error'])

    def test_confirmed_recorded_child_disappearance_is_not_unreadable(self):
        for missing in (FileNotFoundError(), ProcessLookupError(), KeyError(202)):
            with self.subTest(missing=type(missing).__name__):
                lease, process, relations, states, _ = self.fixture(descendant=True)
                lease._known_members[202] = ProcessIdentity(202, 'descendant')
                relations.clear(); states.clear()
                def relationship(pid): raise missing
                lease._relationship_reader = relationship
                with mock.patch.object(G, 'signal_identity') as killpg:
                    lease.close()
                killpg.assert_not_called()
                self.assertTrue(lease._closed)

    def test_explicit_authority_refuses_foreign_empty_other_display_and_host_alias(self):
        for kind in ('foreign_endpoint', 'other_display_record', 'host_alias'):
            with self.subTest(kind=kind):
                lease, process, relations, states, _ = self.fixture()
                authority = lease.run_dir / 'candidate-authority'
                host_authority = lease.run_dir / 'host-authority'
                host_authority.write_bytes(b'')
                lease._source_env.update(DISPLAY=':0', XAUTHORITY=str(host_authority))
                if kind == 'host_alias':
                    authority.symlink_to(host_authority)
                elif kind == 'other_display_record':
                    # An unrelated-display record with zero-length auth data;
                    # no cookie or credential is generated or stored in tests.
                    field = lambda value: struct.pack('>H', len(value)) + value
                    authority.write_bytes(struct.pack('>H', 256) + field(b'localhost')
                        + field(b'92') + field(b'UNSUPPORTED') + field(b''))
                else:
                    authority.write_bytes(b'')
                payload = {'pid': 201, 'start': 'child',
                           'environment': {'DISPLAY': ':91', 'XAUTHORITY': str(authority)}}
                relations[201] = (200, 200, 200, 'child'); states[201] = 'S'
                lease.process = None; lease.owner = None
                lease._authority_reader = lambda pid: payload['environment']
                lease._xwayland_verifier = mock.Mock()
                lease._run = mock.Mock()
                def popen(*args, **kwargs):
                    lease.ready_path.write_text(json.dumps(payload)); return process
                lease._popen = popen
                def kill(*args): relations.clear(); states.clear()
                with mock.patch.object(G, 'signal_identity', side_effect=kill):
                    with self.assertRaisesRegex(RuntimeError, 'explicit XAUTHORITY is unsupported'):
                        lease.start()
                lease._run.assert_not_called(); lease._xwayland_verifier.assert_not_called()
                self.assertIsNone(lease.ready_child)
                evidence = json.loads(lease.evidence_path.read_text())
                self.assertIn('explicit XAUTHORITY is unsupported', evidence['boot_error'])
                self.assertNotIn(str(authority), json.dumps(evidence))

    def test_host_display_alias_is_rejected_before_access_probe(self):
        lease, process, relations, states, _ = self.fixture()
        lease.process = None; lease.owner = None; lease._source_env['DISPLAY'] = ':0'
        relations[201] = (200, 200, 200, 'child'); states[201] = 'S'
        def popen(*args, **kwargs):
            lease.ready_path.write_text(json.dumps({'pid': 201, 'start': 'child',
                                                   'environment': {'DISPLAY': ':0.1'}}))
            return process
        lease._popen = popen; lease._xwayland_verifier = mock.Mock(); lease._run = mock.Mock()
        def kill(*args): relations.clear(); states.clear()
        with mock.patch.object(G, 'signal_identity', side_effect=kill):
            with self.assertRaisesRegex(RuntimeError, 'invalid X11 authority'): lease.start()
        lease._xwayland_verifier.assert_not_called(); lease._run.assert_not_called()

    def test_retained_display_only_payload_requires_independent_access_proof(self):
        for admitted in (False, True):
            with self.subTest(admitted=admitted):
                lease, process, relations, states, _ = self.fixture()
                # Exact retained payload, including its original process identity.
                payload = {'pid': 486796, 'start': '59098686', 'environment': {'DISPLAY': ':1'}}
                relations[486796] = (200, 200, 200, '59098686'); states[486796] = 'S'
                lease.process = None; lease.owner = None
                lease._source_env.update(HOME='/host/home', XAUTHORITY='/host/auth')
                lease._authority_reader = lambda pid: payload['environment']
                verifier = mock.Mock(return_value={'pid': 202, 'start': 'xwayland',
                    'access_model': 'owned-endpoint-host-local-no-cookie'})
                if not admitted: verifier.side_effect = RuntimeError('invalid X11 authority')
                lease._xwayland_verifier = verifier
                def popen(*args, **kwargs):
                    lease.ready_path.write_text(json.dumps(payload)); return process
                lease._popen = popen
                lease._run = mock.Mock(return_value=types.SimpleNamespace(returncode=0,
                    stdout='direct rendering: Yes\nAccelerated: yes\nOpenGL renderer string: AMD\n', stderr=''))
                def kill(*args): relations.clear(); states.clear()
                with mock.patch.object(G, 'signal_identity', side_effect=kill):
                    if admitted:
                        lease.start(); self.assertEqual(lease.environment['DISPLAY'], ':1')
                        self.assertEqual(lease.environment['XAUTHORITY'], os.devnull)
                        self.assertFalse(lease.receipt()['x11']['xauthority_present'])
                        self.assertEqual(lease.receipt()['x11']['xauthority_mode'], 'no-cookie-sentinel')
                        self.assertEqual(lease._run.call_args.kwargs['env']['XAUTHORITY'], os.devnull)
                        lease.close()
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'invalid X11 authority'): lease.start()
                        lease._run.assert_not_called()
                        evidence = json.loads(lease.evidence_path.read_text())
                        self.assertIn('invalid X11 authority', evidence['boot_error'])
                verifier.assert_called_once()

    def test_rejected_verified_child_anchors_cleanup_after_leader_reap(self):
        lease, process, relations, states, _ = self.fixture()
        relations[201] = (200, 200, 200, 'child'); states[201] = 'S'
        lease.process = None; lease.owner = None
        payload = {'pid': 201, 'start': 'child', 'environment': {'DISPLAY': ':9191'}}
        def popen(*args, **kwargs):
            lease.ready_path.write_text(json.dumps(payload)); return process
        def reject(*args, **kwargs):
            states[200] = 'Z'
            raise RuntimeError('invalid X11 authority')
        lease._popen = popen; lease._authority_reader = lambda pid: payload['environment']
        lease._xwayland_verifier = reject; lease._run = mock.Mock()
        def kill(*args): relations.clear(); states.clear()
        with mock.patch.object(G, 'signal_identity', side_effect=kill) as killpg:
            with self.assertRaisesRegex(RuntimeError, 'invalid X11 authority'): lease.start()
        self.assertEqual([(c.args[0].pid, c.args[1]) for c in killpg.call_args_list], [(201, signal.SIGTERM)])
        self.assertIsNone(lease.ready_child)
        evidence = json.loads(lease.evidence_path.read_text())
        self.assertTrue(evidence['rejected_ready_child']['cleanup_identity_verified'])
        self.assertEqual(evidence['cleanup_phase'], 'passed')
        lease._run.assert_not_called()

    def test_unreaped_nonadopted_zombie_fails_absence_proof(self):
        lease, process, relations, states, _ = self.fixture(descendant=True)
        states[202] = 'Z'
        def kill(*args): states[200] = 'Z'
        with mock.patch.object(G, 'signal_identity', side_effect=kill):
            with self.assertRaisesRegex(RuntimeError, 'survived SIGKILL'): lease.close()
        self.assertEqual(states[202], 'Z')

    def test_lease_boot_and_cleanup_errors_remain_distinct(self):
        lease, process, relations, states, _ = self.fixture()
        lease.process = None; lease.owner = None
        lease._popen = mock.Mock(return_value=process)
        lease._run = mock.Mock()
        lease.deadline = 0
        with mock.patch.object(G, 'signal_identity', side_effect=RuntimeError('cleanup sentinel')):
            with self.assertRaisesRegex(RuntimeError, 'readiness timed out'): lease.start()
        evidence = json.loads(lease.evidence_path.read_text())
        self.assertIn('readiness timed out', evidence['boot_error'])
        self.assertIn('cleanup sentinel', evidence['cleanup_attempts'][0]['error'])
        self.assertEqual(evidence['failure'], evidence['boot_error'])
        relations.clear(); states.clear()
        with self.assertRaisesRegex(RuntimeError, 'candidate display unknown'): lease.close()
        lease.log.close()

    def test_session_boot_error_persists_and_retries_only_unfinished_display(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = object.__new__(W.LinuxWineGamescopeCreativeSession)
            session.run_dir = Path(temporary)
            session.acquire_stage_lock = mock.Mock(); session.stage = mock.Mock()
            session.requested_port = 1234; session.game_dir = Path(temporary)
            session._launch_and_connect = mock.Mock()
            session.recorder = types.SimpleNamespace(stop=mock.Mock())
            session.lease = types.SimpleNamespace(start=mock.Mock(side_effect=RuntimeError('boot sentinel')),
                close=mock.Mock(side_effect=[RuntimeError('cleanup sentinel'), None]))
            session._recorder_closed = session._session_closed = session._lease_closed = False
            session._cleanup_errors = []
            session.cleanup_receipt = {'status': 'not_started', 'order': [],
                'recorder': 'not_started', 'game_wine': 'not_started', 'display': 'not_started'}
            with mock.patch.object(W, 'write_runtime_ini'), mock.patch.object(W.GameSession, 'teardown') as game:
                with self.assertRaisesRegex(RuntimeError, '^boot sentinel$'): session.boot()
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, 'cleanup sentinel'): session.teardown()
            game.assert_called_once(); session.recorder.stop.assert_called_once()
            session._launch_and_connect.assert_not_called()
            self.assertEqual(session.lease.close.call_count, 2)
            evidence = json.loads((Path(temporary) / 'gamescope-session-cleanup.json').read_text())
            self.assertEqual(evidence['boot_error'], 'RuntimeError: boot sentinel')
            self.assertEqual(evidence['order'], ['recorder', 'game_wine', 'display'])
            self.assertEqual([item['order'] for item in evidence['attempts']],
                [['recorder', 'game_wine', 'display'], ['display']])
            self.assertEqual(len(evidence['errors']), 1)

    def test_reaper_ancestry_accepts_shared_identity_and_rejects_changed_topology(self):
        relations = {200: (1, 200, 200, 'leader'), 201: (200, 200, 200, 'reaper'),
                     202: (201, 200, 200, 'ready')}
        self.assertEqual(len(P.verify_ancestry(202, ProcessIdentity(200, 'leader'), 200, 200,
                                             lambda pid: relations[pid])), 3)
        for relation in ((200, 201, 200, 'reaper'), (200, 200, 201, 'reaper')):
            bad = dict(relations); bad[201] = relation
            self.assertEqual(len(P.verify_ancestry(202, ProcessIdentity(200, 'leader'), 200, 200,
                                                    lambda pid: bad[pid])), 3)
        reads = {201: 0}
        def recycled(pid):
            if pid == 201:
                reads[201] += 1
                if reads[201] > 1: return (200, 200, 200, 'recycled')
            return relations[pid]
        with self.assertRaisesRegex(RuntimeError, 'identity changed'):
            P.verify_ancestry(202, ProcessIdentity(200, 'leader'), 200, 200, recycled)


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('kpharness.gamescope_socket.capture_socket_node', return_value={'fixture': 'node'})
        patcher.start(); self.addCleanup(patcher.stop)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for pid, parent, start in ((200, 1, 50), (201, 200, 51), (202, 201, 52)):
            path = root / str(pid); path.mkdir()
            fields = ['S', str(parent), '200', '200'] + ['0'] * 15 + [str(start)]
            (path / 'stat').write_text(f'{pid} (test) ' + ' '.join(fields))
            (path / 'cmdline').write_bytes(b'helper\0')
            (path / 'exe').symlink_to('/usr/bin/helper')
            (path / 'ns').mkdir(); (path / 'ns/net').symlink_to('/proc/self/ns/net')
        (root / 'self').symlink_to('/proc/self')
        target = root / '202'; (target / 'exe').unlink(); (target / 'exe').symlink_to('/usr/bin/Xwayland')
        (target / 'cmdline').write_bytes(b'\0'.join([b'Xwayland', b':1', b'-rootless', b'-listenfd', b'3', b'-listenfd', b'4', b'']))
        (target / 'fd').mkdir()
        (target / 'fd/3').symlink_to('socket:[70]'); (target / 'fd/4').symlink_to('socket:[71]')
        (root / 'net').mkdir()
        (root / 'net/unix').write_text('header\n0: 2 0 00010000 0001 01 70 /tmp/.X11-unix/X1\n0: 2 0 00010000 0001 01 71 @/tmp/.X11-unix/X1\n')
        for table in ('tcp', 'tcp6'): (root / 'net' / table).write_text('header\n')
        connection = mock.MagicMock(); connection.__enter__.return_value = connection
        connection.getsockopt.return_value = struct.pack('3i', 200, os.getuid(), 0)
        connection.recv.return_value = b'\x01\x00\x0b\x00\x00\x00\x00\x00'
        factory = mock.Mock(return_value=connection)
        return root, factory, connection

    def test_owned_sockets_and_credential_free_handshake_are_required(self):
        root, factory, connection = self.fixture()
        result = P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
            proc_root=root, socket_factory=factory)
        self.assertEqual(result['access_model'], 'owned-endpoint-host-local-no-cookie')
        self.assertEqual(result['pid'], 202)
        self.assertEqual([item.args[0] for item in connection.connect.call_args_list],
                         ['/tmp/.X11-unix/X1', '\0/tmp/.X11-unix/X1'])
        self.assertEqual([peer['transport'] for peer in result['peers']], ['pathname', 'abstract'])
        self.assertEqual(len(result['ancestry']), 3)
        self.assertEqual(connection.sendall.call_args.args[0], struct.pack('<BBHHHHH', 108, 0, 11, 0, 0, 0, 0))

    def test_displayfd_uses_owned_socket_and_ancestry_binding(self):
        root, factory, connection = self.fixture()
        (root / '202/cmdline').write_bytes(b'\0'.join([b'Xwayland', b'-displayfd', b'7', b'']))
        result = P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
            proc_root=root, socket_factory=factory)
        self.assertEqual(result['display_selection'], 'displayfd')

    def test_socket_process_and_peer_identity_are_rechecked_after_handshake(self):
        for mutation in ('inode', 'process', 'peer'):
            with self.subTest(mutation=mutation):
                root, factory, connection = self.fixture()
                def recv(size):
                    if mutation == 'inode':
                        path = root / '202/fd/4'; path.unlink(); path.symlink_to('socket:[72]')
                        table = root / 'net/unix'; table.write_text(table.read_text().replace(' 71 ', ' 72 '))
                    else:
                        path = root / ('202/stat' if mutation == 'process' else '200/stat')
                        fields = path.read_text().split(); fields[-1] = '999'; path.write_text(' '.join(fields))
                    return b'\x01\x00\x0b\x00\x00\x00\x00\x00'
                connection.recv.side_effect = recv
                with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                    P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                        proc_root=root, socket_factory=factory)

    def test_admission_rejects_foreign_and_changed_network_namespace(self):
        for failure in ('foreign', 'changed'):
            root, factory, connection = self.fixture()
            if failure == 'foreign':
                ns = root / '202/ns/net'; ns.unlink(); ns.symlink_to('/proc/self/ns/mnt')
                with self.assertRaisesRegex(RuntimeError, 'network namespace'):
                    P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                        proc_root=root, socket_factory=factory)
                factory.assert_not_called()
            else:
                namespace = {'dev': 4, 'ino': 55}; calls = [0]
                def reader(*args):
                    calls[0] += 1
                    return namespace if calls[0] <= 2 else {'dev': 4, 'ino': 56}
                with mock.patch.object(P, 'network_namespace', side_effect=reader):
                    with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                        P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                            proc_root=root, socket_factory=factory)

    def test_handshake_has_one_absolute_deadline(self):
        root, factory, connection = self.fixture()
        tick = [0.0]
        def clock(): tick[0] += .6; return tick[0]
        with self.assertRaisesRegex(RuntimeError, 'no unique'):
            P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                proc_root=root, socket_factory=factory, monotonic=clock)
        self.assertLessEqual(connection.recv.call_count, 1)

    def test_foreign_socket_tcp_listener_auth_failure_and_recycled_peer_refuse(self):
        for failure in ('foreign_socket', 'path_socket', 'tcp', 'denied', 'foreign_peer', 'foreign_uid', 'abstract_peer', 'ac'):
            with self.subTest(failure=failure):
                root, factory, connection = self.fixture()
                if failure == 'foreign_socket':
                    (root / '202/fd/4').unlink()
                elif failure == 'path_socket':
                    (root / '202/fd/3').unlink()
                elif failure == 'tcp':
                    (root / 'net/tcp').write_text('header\n0: addr addr 0A 0 0 0 0 0 70\n')
                elif failure == 'ac':
                    path = root / '202/cmdline'; path.write_bytes(path.read_bytes() + b'-ac\0')
                elif failure == 'foreign_uid':
                    connection.getsockopt.return_value = struct.pack('3i', 200, os.getuid() + 1, 0)
                elif failure == 'abstract_peer':
                    connection.getsockopt.side_effect = [struct.pack('3i', 200, os.getuid(), 0),
                                                        struct.pack('3i', 999, os.getuid(), 0)]
                elif failure == 'denied':
                    connection.recv.side_effect = [b'\x00' * 8]
                else:
                    connection.getsockopt.return_value = struct.pack('3i', 999, os.getuid(), 0)
                with self.assertRaises(RuntimeError):
                    P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                        proc_root=root, socket_factory=factory)
                if failure in ('foreign_socket', 'path_socket', 'tcp', 'ac'): factory.assert_not_called()


class TopologyTests(unittest.TestCase):
    def relations(self):
        return {100: (90, 100, 100, '10'), 200: (100, 200, 200, '20'),
                202: (100, 200, 200, '22')}

    def boundary(self):
        return dict(pid=100, start='10', subreaper=True, dedicated_single_launch=True)

    def test_double_fork_adoption_and_recorded_normal_chain(self):
        relations = self.relations()
        chain = P.verify_ancestry(202, ProcessIdentity(200, '20'), 200, 200,
                                  relations.__getitem__, controller=self.boundary())
        self.assertEqual([p for p, _ in chain], [202, 100])
        recorded = {816785: (816778, 816616, 816616, '59550878'),
                    816778: (816616, 816616, 816616, '59550869'),
                    816616: (816495, 816616, 816616, '59550695')}
        self.assertEqual(len(P.verify_ancestry(816785, ProcessIdentity(816616, '59550695'),
                                             816616, 816616, recorded.__getitem__)), 3)

    def test_adopted_xwayland_endpoint_admission_keeps_listener_node_binding(self):
        root, factory, connection = AuthorityTests.fixture(self)
        target = root / '100'; target.mkdir()
        (target / 'stat').write_text('100 (controller) S 90 100 100 ' + '0 ' * 15 + '10')
        (target / 'cmdline').write_bytes(b'controller\0')
        (target / 'exe').symlink_to('/usr/bin/python')
        leader = root / '200/stat'; leader.write_text(leader.read_text().replace('S 1 ', 'S 100 '))
        child = root / '202/stat'; child.write_text(child.read_text().replace('S 201 ', 'S 100 '))
        result = P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
            proc_root=root, socket_factory=factory, controller=self.boundary(),
            node_capture=lambda path: {'captured_path': path})
        self.assertEqual([r['pid'] for r in result['ancestry']], [202, 100])
        self.assertEqual(result['pathname_node']['captured_path'], '/tmp/.X11-unix/X1')
        self.assertEqual(len(result['peers']), 2)

    def test_external_adopter_controller_reuse_and_unestablished_boundary_refuse(self):
        for failure in ('external', 'recycled', 'unverified', 'wrong_group', 'controller_endpoint'):
            with self.subTest(failure=failure):
                relations = self.relations(); boundary = self.boundary(); pid = 202
                if failure == 'external':
                    relations[202] = (900, 200, 200, '22'); relations[900] = (1, 900, 900, '90')
                if failure == 'recycled': relations[100] = (90, 100, 100, 'reused')
                if failure == 'unverified': boundary['subreaper'] = False
                if failure == 'wrong_group': relations[202] = (100, 202, 202, '22')
                if failure == 'controller_endpoint': pid = 100
                with self.assertRaises(P.AncestryError) as caught:
                    P.verify_ancestry(pid, ProcessIdentity(200, '20'), 200, 200,
                                      relations.__getitem__, controller=boundary)
                self.assertEqual(caught.exception.evidence['status'], 'rejected')

    def test_second_observation_parent_race_missing_cycle_and_unreadable(self):
        for failure in ('recycled_controller', 'parent_race', 'missing', 'cycle', 'unreadable'):
            with self.subTest(failure=failure):
                relations = self.relations(); reads = {}
                if failure == 'cycle': relations[202] = (202, 200, 200, '22')
                def reader(pid):
                    reads[pid] = reads.get(pid, 0) + 1
                    if pid == 100 and failure == 'missing': raise FileNotFoundError()
                    if pid == 100 and failure == 'unreadable': raise PermissionError()
                    if pid == 100 and reads[pid] == 2 and failure == 'recycled_controller':
                        return (90, 100, 100, 'reused')
                    if pid == 202 and reads[pid] == 2 and failure == 'parent_race':
                        return (900, 200, 200, '22')
                    return relations[pid]
                with self.assertRaises(P.AncestryError) as caught:
                    P.verify_ancestry(202, ProcessIdentity(200, '20'), 200, 200,
                                      reader, controller=self.boundary())
                self.assertTrue(caught.exception.evidence['first'])
                if failure in ('parent_race', 'recycled_controller'):
                    self.assertTrue(caught.exception.evidence['second'])

    def test_failed_candidate_is_persisted_before_cleanup_and_boot_error_survives(self):
        lease, process, relations, states, _ = LifecycleTests.fixture(self)
        relations[201] = (200, 200, 200, 'child'); states[201] = 'S'
        lease.process = None; lease.owner = None
        payload = {'pid': 201, 'start': 'child', 'environment': {'DISPLAY': ':9191'}}
        def launch(*args, **kwargs):
            lease.ready_path.write_text(json.dumps(payload)); return process
        def reject(*args, evidence_callback, **kwargs):
            evidence_callback([{'pid': 202, 'start': '22', 'phase': 'ancestry',
                                'failed_chain': {'first': [{'pid': 900, 'start': '90'}]}}])
            saved = json.loads(lease.evidence_path.read_text())
            self.assertEqual(saved['xwayland_candidates'][0]['pid'], 202)
            self.assertEqual(saved['candidate_display'], ':9191')
            self.assertEqual(saved['cleanup_phase'], 'not_started')
            raise RuntimeError('endpoint ownership rejected')
        lease._popen = launch; lease._authority_reader = lambda pid: payload['environment']
        lease._xwayland_verifier = reject
        with mock.patch.object(G, 'signal_identity', side_effect=RuntimeError('cleanup rejected')):
            with self.assertRaisesRegex(RuntimeError, 'endpoint ownership rejected'): lease.start()
        evidence = json.loads(lease.evidence_path.read_text())
        self.assertIn('endpoint ownership rejected', evidence['boot_error'])
        self.assertIn('cleanup rejected', evidence['cleanup_attempts'][0]['error'])
        if lease.log: lease.log.close()

    def test_early_rejected_readiness_preserves_display_and_never_unlinks_unadmitted_node(self):
        import socket
        for failure in ('explicit_authority', 'environment', 'ancestry'):
            for endpoint in ('pathname_node', 'abstract_row', 'connected_row'):
                with self.subTest(failure=failure, endpoint=endpoint):
                    lease, process, relations, states, _ = LifecycleTests.fixture(self)
                    relations[201] = (900 if failure == 'ancestry' else 200, 200, 200, 'child')
                    states[201] = 'S'; lease.process = None; lease.owner = None
                    authority = {'DISPLAY': ':9191'}
                    if failure == 'explicit_authority':
                        auth = lease.run_dir / 'authority'; auth.write_bytes(b'')
                        authority['XAUTHORITY'] = str(auth)
                    payload = {'pid': 201, 'start': 'child', 'environment': authority}
                    node = lease.run_dir / 'X9191'
                    sock = socket.socket(socket.AF_UNIX); sock.bind(str(node)); sock.close()
                    original_inode = node.lstat().st_ino
                    def launch(*args, **kwargs):
                        lease.ready_path.write_text(json.dumps(payload)); return process
                    lease._popen = launch
                    lease._authority_reader = lambda pid: {} if failure == 'environment' else authority
                    lease._xwayland_verifier = mock.Mock()
                    def terminate(*args): relations.clear(); states.clear()
                    def path(value):
                        return node if str(value) == '/tmp/.X11-unix/X9191' else Path(value)
                    rows = [] if endpoint == 'pathname_node' else [
                        '0: 2 0 00000000 0001 03 70 ' + ('@' if endpoint == 'abstract_row' else '')
                        + '/tmp/.X11-unix/X9191']
                    with mock.patch.object(G, 'signal_identity', side_effect=terminate), \
                         mock.patch.object(G, 'Path', side_effect=path), \
                         mock.patch('kpharness.gamescope_socket.socket_rows', return_value=rows), \
                         mock.patch('kpharness.gamescope_socket.os.unlink') as unlink:
                        with self.assertRaises(RuntimeError): lease.start()
                    lease._xwayland_verifier.assert_not_called()
                    # Atomic evidence writers unlink only their temporary names;
                    # the unadmitted socket path must never receive unlink.
                    self.assertFalse(any(str(call.args[0]) in (str(node), 'X9191') for call in unlink.call_args_list))
                    evidence = json.loads(lease.evidence_path.read_text())
                    self.assertEqual(evidence['candidate_display'], ':9191')
                    self.assertEqual(evidence['socket_cleanup']['status'], 'unadmitted')
                    self.assertEqual(evidence['cleanup_phase'], 'failed')
                    self.assertNotIn('unadmitted candidate', evidence['boot_error'])
                    self.assertEqual(node.lstat().st_ino, original_inode)
                    lease.log.close()

    def test_malformed_or_missing_display_after_launch_never_claims_socket_absence(self):
        for payload in ('not-json', json.dumps({'pid': 201, 'start': 'child', 'environment': {}})):
            lease, process, relations, states, _ = LifecycleTests.fixture(self)
            relations[201] = (200, 200, 200, 'child'); states[201] = 'S'
            lease.process = None; lease.owner = None
            def launch(*args, **kwargs):
                lease.ready_path.write_text(payload); return process
            lease._popen = launch
            def terminate(*args): relations.clear(); states.clear()
            with mock.patch.object(G, 'signal_identity', side_effect=terminate):
                with self.assertRaises(RuntimeError): lease.start()
            evidence = json.loads(lease.evidence_path.read_text())
            self.assertIsNone(evidence['candidate_display'])
            self.assertEqual(evidence['socket_cleanup']['status'], 'unknown')
            self.assertEqual(evidence['cleanup_phase'], 'failed')
            self.assertFalse(lease._closed)
            lease.log.close()

    def test_subreaper_is_set_and_verified_without_spawning(self):
        task = mock.Mock(); child_file = mock.Mock(); child_file.read_text.return_value = ''
        task.__truediv__ = mock.Mock(return_value=child_file)
        libc = mock.Mock(); libc.prctl.return_value = 0
        with mock.patch.object(P, 'subreaper_enabled', side_effect=[False, True]), \
             mock.patch.object(P.Path, 'iterdir', return_value=iter([task])), \
             mock.patch.object(P, 'process_relationship', return_value=(1, 100, 100, '10')), \
             mock.patch.object(P.ctypes, 'CDLL', return_value=libc), mock.patch.object(P.os, 'getpid', return_value=100):
            self.assertEqual(P.establish_subreaper()['start'], '10')
        libc.prctl.assert_called_once_with(36, 1, 0, 0, 0)
        with mock.patch.object(P, 'subreaper_enabled', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'already a subreaper'): P.establish_subreaper()

    def test_unknown_same_group_never_gains_signal_authority_beside_anchor(self):
        lease, process, relations, states, _ = LifecycleTests.fixture(self)
        relations[299] = (900, 200, 200, 'unknown'); states[299] = 'S'
        relations[900] = (1, 900, 900, 'foreign'); states[900] = 'S'
        def terminate(identity, *args):
            relations.pop(identity.pid); states.pop(identity.pid)
        with mock.patch.object(G, 'signal_identity', side_effect=terminate) as signal_one, \
             mock.patch.object(G.os, 'killpg') as signal_group:
            with self.assertRaisesRegex(RuntimeError, 'surviving owned identity'): lease.close()
        self.assertEqual([c.args[0].pid for c in signal_one.call_args_list], [200])
        signal_group.assert_not_called()
        self.assertNotIn(299, lease._known_members)
        self.assertEqual(lease.unknown_members[0]['pid'], 299)
        self.assertEqual(states[299], 'S')

    def test_adopted_zombie_reaped_without_stealing_popen_status(self):
        lease, process, relations, states, _ = LifecycleTests.fixture(self)
        lease.controller = self.boundary()
        relations[100] = (90, 100, 100, '10'); states[100] = 'S'
        relations[202] = (100, 200, 200, '22'); states[202] = 'Z'
        def wait(pid, flags):
            self.assertEqual((pid, flags), (202, os.WNOHANG))
            relations.pop(pid); states.pop(pid); return pid, 0
        def terminate(identity, *args): states[identity.pid] = 'Z'
        with mock.patch.object(G.os, 'waitpid', side_effect=wait) as reap, \
             mock.patch.object(G, 'signal_identity', side_effect=terminate) as signal_one:
            lease.close()
        reap.assert_called_once_with(202, os.WNOHANG)
        self.assertEqual([c.args[0].pid for c in signal_one.call_args_list], [200])
        self.assertEqual(lease.reaped_children[0]['start'], '22')
        self.assertNotIn(200, relations)

    def test_pidfd_reuse_refuses_signal_and_closes_descriptor(self):
        with mock.patch.object(P.os, 'pidfd_open', return_value=9), \
             mock.patch.object(P.os, 'close') as close, \
             mock.patch.object(signal, 'pidfd_send_signal') as send:
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                P.signal_identity(ProcessIdentity(200, '20'), signal.SIGTERM,
                                  lambda pid: (1, 200, 200, 'reused'))
        send.assert_not_called(); close.assert_called_once_with(9)

    def test_candidate_failure_retains_redacted_command_listener_and_rejected_link(self):
        root, factory, connection = AuthorityTests.fixture(self)
        stat_path = root / '202/stat'; stat_path.write_text(stat_path.read_text().replace('S 201 ', 'S 900 '))
        target = root / '900'; target.mkdir()
        (target / 'stat').write_text('900 (external) S 1 900 900 ' + '0 ' * 15 + '90')
        retained = []
        with self.assertRaises(P.AncestryError):
            P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                proc_root=root, socket_factory=factory, evidence_callback=lambda value: retained.append(json.loads(json.dumps(value))))
        candidate = retained[-1][0]
        self.assertEqual(candidate['pid'], 202)
        self.assertEqual(candidate['start'], '52')
        self.assertEqual(candidate['listeners']['/tmp/.X11-unix/X1'], '70')
        self.assertEqual(candidate['failed_chain']['first'][-1]['pid'], 900)
        self.assertEqual(candidate['executable'], '/usr/bin/Xwayland')
        self.assertEqual(len(candidate['socket_fds']), 2)
        factory.assert_not_called()
        argv = root / '202/cmdline'; argv.write_bytes(argv.read_bytes() + b'-auth\0/private/authority\0')
        with self.assertRaisesRegex(RuntimeError, 'access flags'):
            P.verify_private_xwayland(':1', ProcessIdentity(200, '50'), 200, 200,
                proc_root=root, socket_factory=factory, evidence_callback=lambda value: retained.append(value))
        self.assertNotIn('/private/authority', json.dumps(retained[-1]))


class SocketCleanupTests(unittest.TestCase):
    def fixture(self):
        from kpharness import gamescope_socket as S
        import socket
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); root.chmod(0o1777)
        live = []
        for number in (0, 1, 94, 100):
            sock = socket.socket(socket.AF_UNIX); sock.bind(str(root / ('X' + str(number))))
            if number == 1: sock.close()
            else: live.append(sock); self.addCleanup(sock.close)
        record = S.capture_socket_node(root / 'X1', parent_uid=os.getuid())
        record['network_namespace'] = {'controller': S.network_namespace(), 'xwayland': S.network_namespace()}
        return S, root, record

    def clean(self, S, record, **kwargs):
        return S.cleanup_socket_node(record, owned_absent=kwargs.pop('owned_absent', lambda: None),
            lock_guard=kwargs.pop('lock_guard', lambda: {'exclusive': True}),
            rows_reader=kwargs.pop('rows_reader', lambda path: []),
            namespace_reader=kwargs.pop('namespace_reader', S.network_namespace), **kwargs)

    def test_stale_node_removal_protected_siblings_and_idempotence(self):
        S, root, record = self.fixture()
        result = self.clean(S, record)
        self.assertEqual(result['status'], 'removed'); self.assertFalse((root / 'X1').exists())
        self.assertEqual(result['siblings_before'], result['siblings_after'])
        self.assertEqual(set(result['siblings_after']), {'X0', 'X94', 'X100'})
        self.assertEqual(self.clean(S, record)['status'], 'already_absent')
        (root / 'X1').write_text('replacement')
        with self.assertRaisesRegex(RuntimeError, 'identity'): self.clean(S, record)
        self.assertEqual((root / 'X1').read_text(), 'replacement')

    def test_pathname_abstract_and_established_rows_refuse_even_if_path_absent(self):
        for kind in ('pathname', 'abstract', 'established', 'absent_abstract'):
            with self.subTest(kind=kind):
                S, root, record = self.fixture()
                if kind == 'absent_abstract': (root / 'X1').unlink()
                rows = [f"0: 2 0 00000000 0001 {'03' if kind == 'established' else '01'} 70 "
                        + ('@' if 'abstract' in kind else '') + record['path']]
                with self.assertRaisesRegex(RuntimeError, 'still active'):
                    self.clean(S, record, rows_reader=lambda path: rows if path == record['path'] else [])
                self.assertEqual((root / 'X1').exists(), kind != 'absent_abstract')

    def test_owned_process_pid_reuse_namespace_and_unreadable_table_refuse(self):
        for failure in ('live_process', 'pid_reuse', 'namespace', 'unreadable_namespace', 'unreadable_table', 'lock'):
            with self.subTest(failure=failure):
                S, root, record = self.fixture(); evidence = {}
                def unknown(*args): raise PermissionError('unreadable evidence')
                def owned(): raise RuntimeError('owned process live or identity changed')
                options = {'namespace': {'namespace_reader': lambda: {'dev': 99, 'ino': 99}},
                           'live_process': {'owned_absent': owned}, 'pid_reuse': {'owned_absent': owned},
                           'unreadable_namespace': {'namespace_reader': unknown},
                           'unreadable_table': {'rows_reader': unknown}, 'lock': {'lock_guard': unknown}}[failure]
                with self.assertRaises(RuntimeError): self.clean(S, record, evidence=evidence, **options)
                self.assertTrue((root / 'X1').is_socket()); self.assertEqual(evidence['status'], 'unknown')
                self.assertEqual(evidence['recorded'], record)

    def test_replacement_and_final_check_races_preserve_every_replacement(self):
        import socket
        for kind in ('socket', 'symlink', 'file', 'directory', 'uid', 'mode', 'parent'):
            with self.subTest(kind=kind):
                S, root, record = self.fixture()
                def replace():
                    if kind in ('uid', 'mode'):
                        record['node'][kind] += 1; return
                    if kind == 'parent': root.chmod(0o755); return
                    # Keep the old inode alive to ensure the replacement has a
                    # distinct identity even on aggressive inode-reuse filesystems.
                    (root / 'X1').rename(root / 'old-node')
                    if kind == 'socket':
                        sock = socket.socket(socket.AF_UNIX); sock.bind(str(root / 'X1')); sock.close()
                    elif kind == 'symlink': (root / 'X1').symlink_to(root / 'X0')
                    elif kind == 'file': (root / 'X1').write_text('replacement')
                    else: (root / 'X1').mkdir()
                with self.assertRaises(RuntimeError): self.clean(S, record, before_final=replace)
                self.assertTrue((root / 'X1').exists() or (root / 'X1').is_symlink())
                self.assertTrue((root / 'X0').is_socket())

    def test_capture_refuses_wrong_type_uid_parent_and_stat_errors(self):
        from kpharness import gamescope_socket as S
        for kind in ('file', 'symlink', 'uid', 'parent', 'missing'):
            with self.subTest(kind=kind):
                _, root, record = self.fixture()
                if kind == 'file': (root / 'X1').unlink(); (root / 'X1').write_text('not a socket')
                if kind == 'symlink': (root / 'X1').unlink(); (root / 'X1').symlink_to(root / 'X0')
                if kind == 'parent': root.chmod(0o755)
                if kind == 'missing': (root / 'X1').unlink()
                with mock.patch.object(S.os, 'getuid', return_value=os.getuid() + (kind == 'uid')):
                    with self.assertRaises((OSError, RuntimeError)):
                        S.capture_socket_node(root / 'X1', parent_uid=record['parent_identity']['uid'])

    def test_current_host_unreadable_pid1_does_not_block_scoped_endpoint_cleanup(self):
        S, root, record = self.fixture()
        try:
            list(Path('/proc/1/fd').iterdir())
            host_pid1_unreadable = False
        except PermissionError:
            host_pid1_unreadable = True
        # This host reproduces I1. Still exercise the endpoint path on hosts
        # where PID 1 is readable; arbitrary descriptor enumeration is forbidden.
        original = Path.iterdir
        def reject_foreign(path):
            if path == Path('/proc') or path == Path('/proc/1/fd'):
                raise PermissionError('unrelated /proc/1/fd remains unreadable')
            return original(path)
        with mock.patch.object(Path, 'iterdir', reject_foreign):
            result = self.clean(S, record, rows_reader=S.socket_rows)
        self.assertEqual(result['status'], 'removed')
        self.assertEqual(result['network_namespace']['controller'], S.network_namespace())
        self.assertEqual(result['endpoint_absence_scope'], 'admitted-controller-network-namespace')
        self.assertNotIn('fd_users', result)
        print('Current-host /proc/1/fd unreadable:', host_pid1_unreadable)

    def test_complete_socket_table_parser_retains_listening_and_connected_names(self):
        S, root, record = self.fixture()
        proc = root / 'proc'; (proc / 'net').mkdir(parents=True)
        table = proc / 'net/unix'
        header = 'Num RefCount Protocol Flags Type St Inode Path\n'
        for state, prefix in (('01', ''), ('03', ''), ('01', '@'), ('03', '@')):
            table.write_text(header + f'0: 2 0 00010000 0001 {state} 70 {prefix}{record["path"]}\n')
            rows = S.socket_rows(record['path'], proc)
            self.assertEqual(len(rows), 1)
            with self.assertRaisesRegex(RuntimeError, 'still active'):
                self.clean(S, record, rows_reader=lambda path: S.socket_rows(path, proc))
            self.assertTrue((root / 'X1').is_socket())
        for malformed in ('', 'not a table\n', header + 'truncated-row\n'):
            table.write_text(malformed)
            with self.assertRaisesRegex(RuntimeError, 'incomplete evidence'):
                self.clean(S, record, rows_reader=lambda path: S.socket_rows(path, proc))
            self.assertTrue((root / 'X1').is_socket())

    def test_namespace_change_on_recheck_and_wrong_admitted_namespace_preserve_node(self):
        for failure in ('changed', 'wrong_admitted'):
            S, root, record = self.fixture(); current = S.network_namespace(); reads = [0]
            if failure == 'wrong_admitted': record['network_namespace']['xwayland'] = {'dev': 99, 'ino': 99}
            def namespace():
                reads[0] += 1
                return {'dev': 99, 'ino': 99} if failure == 'changed' and reads[0] > 2 else current
            with self.assertRaisesRegex(RuntimeError, 'namespace'):
                self.clean(S, record, namespace_reader=namespace)
            self.assertTrue((root / 'X1').is_socket())

    def test_canonical_lock_capability_required_and_contention_preserves_node(self):
        import fcntl
        S, root, record = self.fixture()
        lock = root / 'tmp/harness-locks/live-game.lock'; lock.parent.mkdir(parents=True)
        with mock.patch.dict(os.environ, KP_GAMESCOPE_REPO_ROOT=str(root)):
            with lock.open('a') as owner:
                with self.assertRaisesRegex(RuntimeError, 'not held'): S.canonical_lock_guard()
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(S.canonical_lock_guard()['fd'], owner.fileno())
                # A distinct open file description cannot take the same lock.
                with lock.open('a') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(owner, fcntl.LOCK_UN)
                with self.assertRaises(RuntimeError):
                    self.clean(S, record, lock_guard=S.canonical_lock_guard)
                self.assertTrue((root / 'X1').is_socket())


if __name__ == '__main__':
    unittest.main()

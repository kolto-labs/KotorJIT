#!/usr/bin/env python3
"""Offline regressions for creative receipts/capture; no game, Wine or display."""
import argparse
import contextlib
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts/harness'))
from kpharness import creative as C, creative_wine as W, recording as R
from kpharness.creative_steps import CreativeRunner
from kpharness.creative_checkpoints import CreativeCheckpoints, CheckpointError
from kpharness.scenario import _StepFailure


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class OwnershipTests(TempCase):
    def test_claim_refuses_source_alias_nonempty_and_source_children(self):
        source = self.root / 'source'; source.mkdir()
        (source / 'keep').write_text('user')
        alias = self.root / 'alias'; alias.symlink_to(source)
        occupied = self.root / 'occupied'; occupied.mkdir(); (occupied / 'keep').write_text('user')
        for path in (source, alias, source / 'stage', occupied):
            with self.subTest(path=path), self.assertRaises(ValueError):
                W.claim_directory(path, source)
        owned = self.root / 'owned'
        W.claim_directory(owned, source); (owned / 'keep').write_text('owned')
        self.assertEqual(W.claim_directory(owned, source), owned)
        self.assertEqual((occupied / 'keep').read_text(), 'user')

    def test_private_tree_dereferences_without_changing_source(self):
        source = self.root / 'source'; source.mkdir(); (source / 'data').write_text('original')
        link = self.root / 'stage'; link.symlink_to(source)
        W.private_tree(link); (link / 'data').write_text('local')
        self.assertFalse(link.is_symlink()); self.assertEqual((source / 'data').read_text(), 'original')

    def test_pid_requires_both_prefix_and_stage(self):
        prefix, stage = self.root / 'prefix', self.root / 'stage'
        prefix.mkdir(); stage.mkdir()
        proc = self.root / 'proc'; proc.mkdir()
        for pid, env, cwd in [(1, prefix, stage), (2, prefix, self.root), (3, self.root, stage)]:
            directory = proc / str(pid); directory.mkdir()
            (directory / 'environ').write_bytes(f'WINEPREFIX={env}\0'.encode())
            (directory / 'cwd').symlink_to(cwd)
        self.assertEqual([pid for pid in (1,2,3) if W.owned_pid(pid, prefix, stage, proc)], [1])

    def test_teardown_stops_recorder_before_parent_even_on_error(self):
        session = object.__new__(W.LinuxWineCreativeSession)
        session._recorder_closed = False; session._session_closed = False; session._cleanup_errors = []
        calls = []
        def stop():
            calls.append('recorder'); raise RuntimeError('recorder failed')
        session.recorder = types.SimpleNamespace(stop=stop)
        with mock.patch.object(W.GameSession, 'teardown', side_effect=lambda **kw: calls.append('game/xvfb')):
            with self.assertRaises(RuntimeError): session.teardown()
            with self.assertRaises(RuntimeError): session.teardown()
        self.assertEqual(calls, ['recorder', 'game/xvfb', 'recorder'])

    def test_staging_logs_are_current_run_only(self):
        source = self.root / 'source'; source.mkdir(); script = self.root / 'example.lua'; script.write_text('priority=1')
        stage = self.root / 'stage'; stage.mkdir()
        run = self.root / 'run'; run.mkdir()
        session = W.LinuxWineCreativeSession(source=source, scripts=[script], recorder=mock.Mock(),
            run_dir=run, staged=str(stage), wineprefix=str(self.root / 'prefix'))
        def staged(resources):
            session.game_dir=stage
            (stage / 'scriptforge/scripts').mkdir(parents=True)
            (stage / 'scriptforge.log').write_text('[cursed:wheel] stale success\n')
        with mock.patch.object(W.GameSession, 'stage', side_effect=staged): session.stage()
        self.assertEqual((stage / 'scriptforge.log').read_bytes(), b'')
        prior = json.loads((run / 'prior-log-identities.json').read_text())
        self.assertGreater(prior['scriptforge.log']['bytes'], 0)


class CheckpointTests(TempCase):
    def test_actual_store_and_restore_reject_symlink_escape(self):
        saves=self.root/'saves';(saves/'slot').mkdir(parents=True)
        (saves/'slot/SAVEGAME.sav').write_text('save')
        source=self.root/'source';source.mkdir();(source/'keep.utc').write_text('protected')
        cp=CreativeCheckpoints(C.targets.get('k1'),saves,self.root/'checkpoints')
        (cp.root/'escape').symlink_to(source)
        with self.assertRaises(CheckpointError):cp.store('escape','slot')
        cp.store('valid','slot')
        (saves/'slot/SAVEGAME.sav').write_text('changed')
        self.assertEqual(cp.restore('valid'),'slot')
        self.assertEqual((saves/'slot/SAVEGAME.sav').read_text(),'save')
        meta=cp.root/'valid/meta.json'
        data=json.loads(meta.read_text());data['folder']='../../source';meta.write_text(json.dumps(data))
        with self.assertRaises(CheckpointError):cp.restore('valid')
        self.assertEqual((source/'keep.utc').read_text(),'protected')


class RecordingTests(TempCase):
    def test_actual_screen_and_owned_stop(self):
        log = self.root / 'native.log'; log.write_text('[cursed:wheel] old\n')
        process = mock.Mock(returncode=0); process.poll.return_value=None
        recorder = R.X11Recorder(self.root)
        with mock.patch.object(R.subprocess, 'Popen', return_value=process) as popen, mock.patch.object(R.threading, 'Thread'):
            recorder.start(123, (800, 600), log)
            command = popen.call_args.args[0]
            self.assertEqual(command[command.index('-video_size')+1], '800x600')
            self.assertEqual(command[command.index('-i')+1], ':123.0')
            self.assertEqual(command[command.index('-framerate')+1], '60')
            self.assertFalse(recorder.capture['interpolation'])
            self.assertEqual(recorder.capture['initial_native_log_offset'], len(log.read_bytes()))
            recorder.stop(); recorder.stop()
        process.send_signal.assert_called_once_with(signal.SIGINT)
        process.kill.assert_not_called()

    def test_configurable_capture_rate_and_invalid_values(self):
        options=C.parser().parse_args(['--backend','linux-wine-k1','--script','demo.lua','--route','demo','--capture-fps','30'])
        self.assertEqual(options.capture_fps,30)
        recorder=R.X11Recorder(self.root,fps=options.capture_fps)
        process=mock.Mock(returncode=0);process.poll.return_value=0
        with mock.patch.object(R.subprocess,'Popen',return_value=process) as popen, mock.patch.object(R.threading,'Thread'):
            recorder.start(123,(800,600),self.root/'absent.log')
            command=popen.call_args.args[0]
            self.assertEqual(command[command.index('-framerate')+1],'30')
            recorder.stop()
        for fps in (0,121,1.5,True):
            with self.subTest(fps=fps),self.assertRaises(ValueError):R.X11Recorder(self.root,fps=fps)

    def test_stop_escalates_only_its_recorder(self):
        process=mock.Mock(returncode=-9); process.poll.return_value=None
        process.wait.side_effect=[subprocess.TimeoutExpired('ffmpeg',15),0]
        recorder=R.X11Recorder(self.root); recorder.process=process
        recorder.stop()
        process.kill.assert_called_once(); self.assertIn('forced kill',recorder.error)

    def test_fresh_marker_clock_and_threshold_selection(self):
        path=self.root/'native.log'; path.write_text('[cursed:wheel] stale\n')
        recorder=R.X11Recorder(self.root); recorder.started=100; recorder._offset=path.stat().st_size
        with path.open('a') as f: f.write('[cursed:strike] armed\n[cursed:rave] the beat drops\n')
        recorder.observe(path,105); self.assertIsNone(recorder.marker)
        with path.open('a') as f: f.write('[meditation] round 1: steadied 3\n')
        recorder.observe(path,112.5)
        selection=R.clip_window(60,recorder.marker)
        self.assertEqual(selection['start_seconds'],11.5)
        self.assertEqual(selection['duration_seconds'],10)
        self.assertIn('steadied 3',selection['marker']['line'])
        self.assertIn('fallback',R.clip_window(60,None)['selection'])

    def test_probe_rejects_missing_or_zero_video(self):
        bad={'streams':[{'width':800,'height':600}], 'format':{'duration':'0'}}
        with mock.patch.object(R.subprocess,'check_output',return_value=json.dumps(bad)):
            with self.assertRaises(ValueError): R.probe_video(self.root/'bad.mp4')

    def test_render_failed_route_never_publishes_success(self):
        (self.root/'report.json').write_text('{"ok":false,"steps":[]}')
        with mock.patch.object(R.subprocess,'run') as command:
            with self.assertRaises(ValueError):R.render(self.root,marker=None)
            command.assert_not_called()

    def test_render_validates_media_and_limits_threads(self):
        (self.root/'report.json').write_text('{"ok":true,"steps":[{"status":"ok"}]}')
        (self.root/'continuous.mp4').write_bytes(b'video')
        def write(command, **kwargs):Path(command[-1]).write_bytes(b'rendered')
        with mock.patch.object(R,'probe_video',return_value={'duration_seconds':20,'width':800,'height':600}), mock.patch.object(R.subprocess,'run',side_effect=write) as run:
            receipt=R.render(self.root,marker={'capture_seconds':5,'line':'[cursed:wheel] spin'})
        self.assertEqual(receipt['start_seconds'],4)
        self.assertEqual(set(receipt['artifacts']),{'representative.mp4','representative.gif'})
        for call in run.call_args_list:
            args=call.args[0]
            self.assertTrue(all(args[i+1]=='2' for i,x in enumerate(args[:-1]) if x=='-threads'))


class RouteHelperTests(TempCase):
    def runner(self):
        runner=object.__new__(CreativeRunner); runner.run_dir=self.root
        runner.session=types.SimpleNamespace(runtime_log=self.root/'native.log')
        runner.ch=mock.Mock(cursor=3); runner.ch.state.return_value={'server_tick':10}
        runner.watchdog=mock.Mock(); runner.watchdog.check.return_value=None
        return runner

    def test_continuous_events_use_one_watermark_without_drain(self):
        runner=self.runner(); runner.ch.status.return_value={'events_seq':200}
        runner.ch.events.return_value=[{'seq':201,'event':'OnTick'}]  # Never empty.
        self.assertEqual(runner.sync_cursor(),200)
        runner.ch.status.assert_called_once(); runner.ch.events.assert_not_called()
        # An event after the watermark remains eligible to the inherited waits.
        from kpharness.client import events_after
        self.assertEqual(events_after([{'seq':201}],runner.ch.cursor),[{'seq':201}])

    def test_client_tick_gate_uses_client_progress_and_rejects_reset(self):
        runner=self.runner()
        step=types.SimpleNamespace(index=1,raw={'do':'advance_ticks','clock':'client','ticks':3})
        runner.ch.state.side_effect=[{'server_tick':90,'client_tick':10},
                                    {'server_tick':90,'client_tick':13}]
        self.assertEqual(runner._do(step),'observed client ticks 10 -> 13')
        runner.ch.state.side_effect=[{'client_tick':10},{'client_tick':9}]
        with self.assertRaisesRegex(_StepFailure,'client tick reset'):runner._do(step)
        step.raw['clock']='wall'
        with self.assertRaisesRegex(_StepFailure,'clock must'):runner._do(step)

    def test_log_mark_excludes_prior_run_and_detects_new_lines(self):
        runner=self.runner(); runner.session.runtime_log.write_text('[meditation] old\n')
        step=lambda do,**kw:types.SimpleNamespace(index=1,raw={'do':do,**kw})
        runner._do(step('mark_log'))
        with runner.session.runtime_log.open('a') as stream:stream.write('[meditation] current\n')
        runner._do(step('await_log',pattern='meditation',minimum=1,maximum=1))
        receipt=json.loads((self.root/'log-gate-1.json').read_text())
        self.assertEqual(receipt['lines'],['[meditation] current'])
        runner.session.runtime_log.write_bytes(b'')
        with self.assertRaises(_StepFailure):runner._do(step('await_log',pattern='meditation'))


class DriverTests(TempCase):
    def test_unsupported_mac_backend_fails_before_any_mutation(self):
        for name in ('macos-k1','macos-k2'):
            with mock.patch.object(C.Path,'mkdir') as mkdir:
                with self.assertRaises(C.UnsupportedBackend):C.run_creative(types.SimpleNamespace(backend=name))
                mkdir.assert_not_called()

    def test_script_basename_collision_and_missing_input(self):
        first=self.root/'a';second=self.root/'b';first.mkdir();second.mkdir()
        for directory in (first,second):(directory/'same.lua').write_text('')
        with self.assertRaises(ValueError):C.script_inputs([str(first/'same.lua'),str(second/'same.lua')],self.root)
        with self.assertRaises(ValueError):C.script_inputs(['absent.lua'],self.root)

    def test_retired_scripts_rejected_before_discovery_or_staging(self):
        manifest=json.loads((ROOT/'tools/tests/examples/manifest.json').read_text())
        retired=[entry for entry in manifest['examples'] if entry['disposition']=='retired_public']
        alias=self.root/'retired-alias.lua';alias.symlink_to(ROOT/retired[0]['source_path'])
        names=[str(alias)]
        for entry in retired:
            names.extend([entry['path'], 'scripts/examples/'+entry['path'], entry['source_path'],
                          str(ROOT/'scripts/examples'/entry['path']), str(ROOT/entry['source_path'])])
        for name in names:
            with self.subTest(name=name):
                options=C.parser().parse_args(['--backend','linux-wine-k1','--script',name,'--route','unused'])
                adapter=mock.Mock(return_value=(None,None,mock.Mock(),None,None))
                with mock.patch.object(C.discover,'repo_root',return_value=ROOT), \
                     mock.patch.object(C.discover,'data_dir') as game, \
                     mock.patch.object(C.discover,'build_dir') as build, \
                     mock.patch.object(C,'find_scenario') as route, \
                     mock.patch.object(C,'live_lock') as lock, \
                     mock.patch.object(C.Path,'mkdir') as mkdir:
                    with self.assertRaisesRegex(ValueError,'retired public example'):
                        C.run_creative(options,adapter_factory=adapter)
                    game.assert_not_called();build.assert_not_called();route.assert_not_called()
                    lock.assert_not_called();mkdir.assert_not_called();adapter.return_value[2].assert_not_called()

    def test_examples_shorthand_symlink_rejected_before_game_access(self):
        target=self.root/'tools/tests/examples/fixtures/legacy/cursed/60_rave.lua'
        target.parent.mkdir(parents=True);target.write_text('-- synthetic retired fixture')
        examples=self.root/'scripts/examples';examples.mkdir(parents=True)
        (examples/'__kp_retired_alias_test.lua').symlink_to(target)
        options=C.parser().parse_args(['--backend','linux-wine-k1','--script',
                                      '__kp_retired_alias_test.lua','--route','unused'])
        adapter=mock.Mock(return_value=(None,None,mock.Mock(),None,None))
        with mock.patch.object(C.discover,'repo_root',return_value=self.root), \
             mock.patch.object(C.discover,'data_dir') as game, \
             mock.patch.object(C.discover,'build_dir') as build, \
             mock.patch.object(C,'find_scenario') as route, \
             mock.patch.object(C,'live_lock') as lock, \
             mock.patch.object(C.Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'retired public example'):
                C.run_creative(options,adapter_factory=adapter)
            game.assert_not_called();build.assert_not_called();route.assert_not_called()
            lock.assert_not_called();mkdir.assert_not_called();adapter.return_value[2].assert_not_called()

    def test_retained_custom_and_other_internal_scripts_are_allowed(self):
        custom=self.root/'60_rave.lua';custom.write_text('-- independently authored custom script')
        internal=self.root/'tools/tests/examples/fixtures/other.lua'
        internal.parent.mkdir(parents=True);internal.write_text('-- not a retired example')
        retained=ROOT/'scripts/examples/cursed/30_necromancer.lua'
        self.assertEqual(C.script_inputs([str(custom),str(retained),str(internal)],ROOT),
                         [custom.resolve(),retained.resolve(),internal.resolve()])
        self.assertEqual(C.script_inputs(['cursed/30_necromancer.lua'],ROOT),[retained.resolve()])


class DriverIntegrationTests(TempCase):
    def exercise(self, *, route_ok=True, render_error=False, mutate_source=False, checkpoint_alias=None,
                 checkpoint_escape=False, boot_cleanup_failure=False, gamescope=False,
                 capture_fail_after_route=False, commitment_log='default',
                 launch_count=1, boot_record=True, dev_budget=None):
        source=self.root/'source';source.mkdir(exist_ok=True)
        build=self.root/'build';build.mkdir(exist_ok=True)
        for name in ('scriptforge.dll','binkw32.dll'):(build/name).write_bytes(name.encode())
        script=self.root/'demo.lua';script.write_text('priority=1')
        route=self.root/'route.toml';route.write_text('name="test"\ntarget="k1"\n[settings]\ngame_speed=1.0\n[[step]]\ndo="lua"\ncode="return true"\n')
        options=C.parser().parse_args(['--backend','linux-wine-k1','--script',str(script),'--route',str(route),'--output',str(self.root/'output')]
                                      +([] if dev_budget is None else ['--dev-max-boot-attempts',str(dev_budget)]))
        if gamescope:
            options.backend = 'linux-wine-k1-gamescope'
            if commitment_log == 'default':
                operator = self.root / 'operator'; operator.mkdir(exist_ok=True)
                commitment_log = operator / 'commitments.log'; commitment_log.touch()
            options.cleanup_commitment_log = None if commitment_log is None else str(commitment_log)
        self.boot_heads = []
        if checkpoint_alias:
            options.checkpoint_root = str({'source':source,'stage':self.root/'output/stage-k1',
                'prefix':self.root/'output/wineprefix-k1','build':build}[checkpoint_alias])
            (source/'Override').mkdir(); (source/'Override/keep.utc').write_text('protected')
        if checkpoint_escape:
            checkpoints=self.root/'checkpoints';checkpoints.mkdir()
            (checkpoints/'escape').symlink_to(source)
            options.checkpoint_root=str(checkpoints)
            route.write_text('name="test"\ntarget="k1"\n[settings]\ngame_speed=1.0\n[[step]]\ndo="save"\ncheckpoint="escape"\n')
        calls=[]; case=self
        class Recorder:
            def __init__(self,run_dir,**kwargs):
                assert kwargs['fps'] == 60
                inherited = kwargs.get('inherited_fds', ())
                case.recorder_inherited = [(fd, os.fstat(fd).st_ino) for fd in inherited]
                self.run_dir=run_dir;self.error=None;self.marker={'capture_seconds':1};self.started=0
                self.process=mock.Mock();self.process.poll.return_value=None
            def stop(self):calls.append('recorder-stop')
            def receipt(self):
                return {'media': {'status': 'retained_for_visual_review',
                                 'continuous': R.artifact(self.run_dir/'continuous.mp4')}}
        class Session(W.LinuxWineCreativeSession):
            def __init__(self,source,scripts,recorder,run_dir,**kwargs):
                self.recorder=recorder;self.run_dir=run_dir;self.game_dir=Path(kwargs['staged'])
                self.target=C.targets.get('k1');self.save_dir=self.game_dir/'Saves';self.build='verified-test-build';self.deployed=[]
                self.owned_window=mock.Mock();self.lease=mock.Mock()
                case.session_budget=kwargs.get('max_boot_attempts')
            def boot(self,resources):
                if boot_record:
                    # Stand-in for GameSession._launch_and_connect's receipt.
                    (self.run_dir/'boot-attempts.json').write_text(json.dumps({
                        'max_boot_attempts':case.session_budget,'max_boot_attempts_source':'kwarg',
                        'launch_count':launch_count,'outcome':'channel',
                        'attempts':[{'attempt':n+1,'outcome':'channel' if n+1==launch_count else 'crash'}
                                    for n in range(launch_count)]}))
                if gamescope:
                    # The launch head must already be outside the run before any child starts.
                    lines = [json.loads(line) for line in Path(options.cleanup_commitment_log).read_text().splitlines()]
                    ledger = (self.run_dir/'ffprobe-cleanup-ledger.json').read_bytes()
                    case.boot_heads.append((lines, hashlib.sha256(ledger).hexdigest()))
                self.save_dir.mkdir();(self.run_dir/'continuous.mp4').write_bytes(b'failed or passed raw video')
                for name in ('scriptforge.dll','binkw32.dll'):(self.game_dir/name).write_bytes((build/name).read_bytes())
                if boot_cleanup_failure:
                    self._recorder_closed=False;self._session_closed=False;self._cleanup_errors=[]
                    self.teardown()
                    raise RuntimeError('boot failed')
                return mock.Mock()
            def teardown(self):
                if boot_cleanup_failure:
                    return W.LinuxWineCreativeSession.teardown(self)
                self.recorder.stop();calls.append('game-stop')
            def check_capture(self):
                if capture_fail_after_route:
                    raise RuntimeError('capture_binding_changed: late capture failure')
        class Runner:
            def __init__(self,scenario,session,channel,**kwargs):self.session=session;self.scenario=scenario
            def run(self):
                if mutate_source:(source/'swkotor.ini').write_text('unexpected write')
                report={'ok':route_ok,'steps':[{'status':'ok' if route_ok else 'failed'}]}
                (self.session.run_dir/'report.json').write_text(json.dumps(report))
                step = self.scenario.steps[0]
                result = types.SimpleNamespace(status=report['steps'][0]['status'], index=step.index,
                                               description=step.describe())
                return types.SimpleNamespace(ok=route_ok, steps=[result], scenario=self.scenario.name,
                    target=self.scenario.target, build=self.session.build)
        renderer=mock.Mock(return_value={'artifacts':{'representative.mp4':{},'representative.gif':{}}})
        if render_error:renderer.side_effect=RuntimeError('encoder failed')
        adapter=lambda _: (Session,Recorder,W.claim_directory,W.disjoint,W.source_receipt)
        with contextlib.ExitStack() as stack, mock.patch.object(C.discover,'repo_root',return_value=self.root), mock.patch.object(C.discover,'data_dir',return_value=source), mock.patch.object(C.discover,'build_dir',return_value=build), mock.patch.object(C,'shared_lock_path',return_value=self.root/'live.lock'), mock.patch('kpharness.session.pids_by_name',return_value=[]), mock.patch.object(C.shutil,'which',return_value='/usr/bin/fake'):
            if gamescope:
                def manifest(run_dir, **kwargs):
                    (run_dir/'gamescope-run-manifest.json').write_text('{}')
                    return {}
                stack.enter_context(mock.patch.dict('os.environ', {'KP_GAMESCOPE_HARNESS_SNAPSHOT': str(self.root/'snapshot')}))
                stack.enter_context(mock.patch('kpharness.gamescope_snapshot.create_run_manifest', side_effect=manifest))
                stack.enter_context(mock.patch('kpharness.gamescope_snapshot.verify_run_manifest'))
                stack.enter_context(mock.patch('kpharness.display_backends.detect_host'))
                stack.enter_context(mock.patch('kpharness.display_backends.admit_backend'))
                stack.enter_context(mock.patch('kpharness.display_backends.schema2_receipt', side_effect=lambda **kw:
                    {'schema': 2, 'ok': False, 'visual_review': {'status': 'pending'},
                     'media': kw['recorder']['media']}))
            if checkpoint_escape:
                with mock.patch.object(Session,'boot') as boot:
                    with self.assertRaises(CheckpointError):
                        C.run_creative(options,adapter_factory=adapter,runner_factory=Runner,renderer=renderer)
                    boot.assert_not_called()
                self.assertFalse((self.root/'output').exists())
                return
            if checkpoint_alias:
                with mock.patch.object(Session,'boot') as boot, mock.patch.object(W,'claim_directory') as claim:
                    with self.assertRaisesRegex(ValueError,'checkpoint root overlaps'):
                        C.run_creative(options,adapter_factory=adapter,runner_factory=Runner,renderer=renderer)
                    boot.assert_not_called(); claim.assert_not_called()
                self.assertEqual((source/'Override/keep.utc').read_text(),'protected')
                self.assertFalse((self.root/'output').exists())
                return
            if boot_cleanup_failure:
                with mock.patch.object(W.GameSession,'teardown',side_effect=[RuntimeError('parent cleanup failed'),None]) as parent:
                    receipt=C.run_creative(options,adapter_factory=adapter,runner_factory=Runner,renderer=renderer)
                    self.assertEqual(parent.call_count,2)
                self.assertEqual(calls,['recorder-stop'])
                self.assertEqual(receipt['cleanup']['status'],'failed')
                self.assertIn('parent cleanup failed',receipt['cleanup']['error'])
                self.assertFalse(receipt['ok']);renderer.assert_not_called()
                return receipt,renderer
            self.launch_stderr = io.StringIO()
            with contextlib.redirect_stderr(self.launch_stderr):
                receipt=C.run_creative(options,adapter_factory=adapter,runner_factory=Runner,renderer=renderer)
        self.assertEqual(calls,['recorder-stop','game-stop'])
        self.assertTrue((Path(receipt['run_dir'])/'creative-run.json').is_file())
        self.assertEqual(receipt['runtime']['scriptforge.dll']['sha256'],R.sha256(build/'scriptforge.dll'))
        return receipt,renderer

    def test_checkpoint_overlaps_rejected_before_claim_or_boot(self):
        for alias in ('source','stage','prefix','build'):
            with self.subTest(alias=alias):
                case=DriverIntegrationTests();case.setUp()
                try: case.exercise(checkpoint_alias=alias)
                finally: case.doCleanups()

    def test_checkpoint_symlink_escape_rejected_before_boot(self):
        self.exercise(checkpoint_escape=True)

    def test_boot_cleanup_failure_remains_failed_after_retry(self):
        receipt,_=self.exercise(boot_cleanup_failure=True)
        saved=json.loads((Path(receipt['run_dir'])/'creative-run.json').read_text())
        self.assertEqual(saved['cleanup']['status'],'failed')

    def test_success_has_current_identity_and_separate_statuses(self):
        result,renderer=self.exercise()
        self.assertTrue(result['ok']);self.assertTrue(result['source_unchanged']);self.assertTrue(result['inputs_unchanged'])
        self.assertEqual(result['route']['status'],'passed');self.assertEqual(result['media']['status'],'passed')
        renderer.assert_called_once()

    def test_gamescope_defers_all_derivatives_until_acceptance(self):
        result, renderer = self.exercise(gamescope=True)
        renderer.assert_not_called()
        self.assertEqual(result['schema'], 2)
        self.assertFalse(result['ok'])
        self.assertEqual(result['visual_review']['status'], 'pending')
        self.assertEqual(result['media']['status'], 'retained_for_visual_review')
        run = Path(result['run_dir'])
        self.assertTrue((run/'continuous.mp4').is_file())
        for name in ('representative.mp4', 'representative.gif', 'media.json'):
            self.assertFalse((run/name).exists())

    def test_gamescope_launch_emits_unique_initial_head_before_any_child(self):
        result, _ = self.exercise(gamescope=True)
        run = str(Path(result['run_dir']).resolve())
        (lines, ledger_head), = self.boot_heads
        self.assertEqual(len(lines), 1)
        head = lines[0]
        self.assertEqual((head['kind'], head['event'], head['run_dir'], head['sequence'], head['failure_id']),
                         ('kpharness.cleanup-ledger-head.v1', 'run_initialized', run, 0, None))
        self.assertEqual(head['cleanup_ledger_sha256'], ledger_head)
        emitted = [json.loads(line) for line in self.launch_stderr.getvalue().splitlines()
                   if line.startswith('{') and '"kind"' in line]
        self.assertEqual(emitted, [head])
        self.assertEqual(result['cleanup_ledger_launch'], {'sha256': head['cleanup_ledger_sha256'],
                                                           'nonce': head['nonce']})
        case = DriverIntegrationTests(); case.setUp()
        try:
            other, _ = case.exercise(gamescope=True)
        finally:
            case.doCleanups()
        self.assertNotEqual(other['cleanup_ledger_launch']['sha256'], head['cleanup_ledger_sha256'])
        self.assertNotEqual(other['cleanup_ledger_launch']['nonce'], head['nonce'])

    def test_gamescope_recorder_children_inherit_the_held_live_lock(self):
        # R10-3: FFprobe and xwininfo children of the recorder inherit the live lock descriptor.
        self.exercise(gamescope=True)
        (descriptor, inode), = self.recorder_inherited
        self.assertEqual(inode, (self.root / 'live.lock').stat().st_ino)
        case = DriverIntegrationTests(); case.setUp()
        try:
            case.exercise()
            self.assertEqual(case.recorder_inherited, [])
        finally:
            case.doCleanups()

    def test_gamescope_launch_refuses_missing_or_inside_commitment_log_before_run_directory(self):
        inside = self.root / 'output'; inside.mkdir()
        for log in (None, self.root / 'absent.log'):
            with self.subTest(log=log):
                with self.assertRaisesRegex(ValueError, 'commitment log'):
                    self.exercise(gamescope=True, commitment_log=log)
                self.assertEqual([path.name for path in inside.iterdir()], [])

    def test_late_capture_failure_preserves_successful_route_result(self):
        result, renderer = self.exercise(gamescope=True, capture_fail_after_route=True)
        self.assertEqual(result['route']['status'], 'passed')
        self.assertEqual(result['capture_gate']['status'], 'failed')
        self.assertIn('capture_binding_changed', result['capture_gate']['error'])
        self.assertFalse(result['ok'])
        renderer.assert_not_called()

    def test_failed_route_keeps_video_and_does_not_render_success(self):
        result,renderer=self.exercise(route_ok=False)
        self.assertFalse(result['ok']);renderer.assert_not_called()
        self.assertTrue(Path(result['media']['continuous']['path']).is_file())
        self.assertEqual(result['route']['status'],'failed')

    def test_media_failure_does_not_relabel_route(self):
        result,_=self.exercise(render_error=True)
        self.assertFalse(result['ok']);self.assertEqual(result['route']['status'],'passed')
        self.assertEqual(result['media']['status'],'failed');self.assertIn('encoder failed',result['media']['error'])

    def test_single_launch_budget_is_passed_and_evidence_embedded(self):
        result,_=self.exercise()
        self.assertEqual(self.session_budget,1)
        boot=result['boot_attempts']
        self.assertEqual((boot['max_boot_attempts'],boot['budget_source'],boot['launch_count'],
                          boot['acceptance_eligible']),(1,'default_single',1,True))
        self.assertEqual(boot['evidence']['sha256'],R.sha256(Path(result['run_dir'])/'boot-attempts.json'))
        self.assertEqual(boot['record']['launch_count'],1)
        self.assertTrue(result['ok'])

    def test_relaunch_refuses_acceptance(self):
        result,_=self.exercise(launch_count=2)
        self.assertEqual(result['route']['status'],'passed')
        self.assertFalse(result['boot_attempts']['acceptance_eligible'])
        self.assertIn('launch_count',result['boot_attempts']['refusal'])
        self.assertFalse(result['ok'])

    def test_missing_boot_evidence_refuses_acceptance(self):
        result,_=self.exercise(boot_record=False)
        self.assertIsNone(result['boot_attempts']['evidence'])
        self.assertFalse(result['boot_attempts']['acceptance_eligible'])
        self.assertFalse(result['ok'])

    def test_dev_override_passes_budget_but_is_never_acceptance(self):
        result,_=self.exercise(dev_budget=3)
        self.assertEqual(self.session_budget,3)
        self.assertEqual(result['boot_attempts']['budget_source'],'dev_override')
        self.assertFalse(result['boot_attempts']['acceptance_eligible'])
        self.assertFalse(result['ok'])

    def test_gamescope_single_launch_stays_pending(self):
        result,_=self.exercise(gamescope=True)
        self.assertTrue(result['boot_attempts']['acceptance_eligible'])
        self.assertEqual(result['visual_review']['status'],'pending')

    def test_gamescope_relaunch_blocks_visual_acceptance(self):
        result,_=self.exercise(gamescope=True,launch_count=2)
        self.assertFalse(result['ok']);self.assertFalse(result['acceptance_ready'])
        self.assertEqual(result['visual_review']['status'],'refused_boot_budget')
        saved=json.loads((Path(result['run_dir'])/'creative-run.json').read_text())
        self.assertEqual(saved['visual_review']['status'],'refused_boot_budget')
        # creative_accept.accept() only proceeds from a pending review.
        from kpharness import creative_accept as A
        operator=self.root/'operator';operator.mkdir(exist_ok=True)
        log=operator/'accept.log';log.touch()
        with self.assertRaisesRegex(ValueError,'not pending visual acceptance'):
            A.accept(Path(result['run_dir']),reviewer='r',media_sha256='0'*64,route_sha256='0'*64,
                     ffprobe_sha256='0'*64,cleanup_ledger_sha256='0'*64,commitment_log=str(log))

    def test_source_change_prevents_overall_pass(self):
        result,_=self.exercise(mutate_source=True)
        self.assertFalse(result['ok']);self.assertFalse(result['source_unchanged'])


if __name__=='__main__':unittest.main()

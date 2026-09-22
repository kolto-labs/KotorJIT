#!/usr/bin/env python3
"""Offline regressions for creative receipts/capture; no game, Wine or display."""
import argparse
import json
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
            (stage / 'kotorphasor/scripts').mkdir(parents=True)
            (stage / 'kotorphasor.log').write_text('[cursed:wheel] stale success\n')
        with mock.patch.object(W.GameSession, 'stage', side_effect=staged): session.stage()
        self.assertEqual((stage / 'kotorphasor.log').read_bytes(), b'')
        prior = json.loads((run / 'prior-log-identities.json').read_text())
        self.assertGreater(prior['kotorphasor.log']['bytes'], 0)


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
            self.assertEqual(recorder.capture['initial_native_log_offset'], len(log.read_bytes()))
            recorder.stop(); recorder.stop()
        process.send_signal.assert_called_once_with(signal.SIGINT)
        process.kill.assert_not_called()

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


class DriverIntegrationTests(TempCase):
    def exercise(self, *, route_ok=True, render_error=False, mutate_source=False, checkpoint_alias=None, checkpoint_escape=False, boot_cleanup_failure=False):
        source=self.root/'source';source.mkdir()
        build=self.root/'build';build.mkdir()
        for name in ('kphasor.dll','binkw32.dll'):(build/name).write_bytes(name.encode())
        script=self.root/'demo.lua';script.write_text('priority=1')
        route=self.root/'route.toml';route.write_text('name="test"\ntarget="k1"\n[settings]\ngame_speed=1.0\n[[step]]\ndo="lua"\ncode="return true"\n')
        options=C.parser().parse_args(['--backend','linux-wine-k1','--script',str(script),'--route',str(route),'--output',str(self.root/'output')])
        if checkpoint_alias:
            options.checkpoint_root = str({'source':source,'stage':self.root/'output/stage-k1',
                'prefix':self.root/'output/wineprefix-k1','build':build}[checkpoint_alias])
            (source/'Override').mkdir(); (source/'Override/keep.utc').write_text('protected')
        if checkpoint_escape:
            checkpoints=self.root/'checkpoints';checkpoints.mkdir()
            (checkpoints/'escape').symlink_to(source)
            options.checkpoint_root=str(checkpoints)
            route.write_text('name="test"\ntarget="k1"\n[settings]\ngame_speed=1.0\n[[step]]\ndo="save"\ncheckpoint="escape"\n')
        calls=[]
        class Recorder:
            def __init__(self,run_dir,**kwargs):
                self.run_dir=run_dir;self.error=None;self.marker={'capture_seconds':1};self.started=0
                self.process=mock.Mock();self.process.poll.return_value=None
            def stop(self):calls.append('recorder-stop')
        class Session(W.LinuxWineCreativeSession):
            def __init__(self,source,scripts,recorder,run_dir,**kwargs):
                self.recorder=recorder;self.run_dir=run_dir;self.game_dir=Path(kwargs['staged'])
                self.target=C.targets.get('k1');self.save_dir=self.game_dir/'Saves';self.build='verified-test-build';self.deployed=[]
            def boot(self,resources):
                self.save_dir.mkdir();(self.run_dir/'continuous.mp4').write_bytes(b'failed or passed raw video')
                for name in ('kphasor.dll','binkw32.dll'):(self.game_dir/name).write_bytes((build/name).read_bytes())
                if boot_cleanup_failure:
                    self._recorder_closed=False;self._session_closed=False;self._cleanup_errors=[]
                    self.teardown()
                    raise RuntimeError('boot failed')
                return mock.Mock()
            def teardown(self):
                if boot_cleanup_failure:
                    return W.LinuxWineCreativeSession.teardown(self)
                self.recorder.stop();calls.append('game-stop')
        class Runner:
            def __init__(self,scenario,session,channel,**kwargs):self.session=session
            def run(self):
                if mutate_source:(source/'swkotor.ini').write_text('unexpected write')
                report={'ok':route_ok,'steps':[{'status':'ok' if route_ok else 'failed'}]}
                (self.session.run_dir/'report.json').write_text(json.dumps(report))
                return types.SimpleNamespace(ok=route_ok,steps=[types.SimpleNamespace(status=report['steps'][0]['status'])])
        renderer=mock.Mock(return_value={'artifacts':{'representative.mp4':{},'representative.gif':{}}})
        if render_error:renderer.side_effect=RuntimeError('encoder failed')
        adapter=lambda _: (Session,Recorder,W.claim_directory,W.disjoint,W.source_receipt)
        with mock.patch.object(C.discover,'repo_root',return_value=self.root), mock.patch.object(C.discover,'data_dir',return_value=source), mock.patch.object(C.discover,'build_dir',return_value=build), mock.patch.object(C,'shared_lock_path',return_value=self.root/'live.lock'), mock.patch('kpharness.session.pids_by_name',return_value=[]), mock.patch.object(C.shutil,'which',return_value='/usr/bin/fake'):
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
            receipt=C.run_creative(options,adapter_factory=adapter,runner_factory=Runner,renderer=renderer)
        self.assertEqual(calls,['recorder-stop','game-stop'])
        self.assertTrue((Path(receipt['run_dir'])/'creative-run.json').is_file())
        self.assertEqual(receipt['runtime']['kphasor.dll']['sha256'],R.sha256(build/'kphasor.dll'))
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

    def test_failed_route_keeps_video_and_does_not_render_success(self):
        result,renderer=self.exercise(route_ok=False)
        self.assertFalse(result['ok']);renderer.assert_not_called()
        self.assertTrue(Path(result['media']['continuous']['path']).is_file())
        self.assertEqual(result['route']['status'],'failed')

    def test_media_failure_does_not_relabel_route(self):
        result,_=self.exercise(render_error=True)
        self.assertFalse(result['ok']);self.assertEqual(result['route']['status'],'passed')
        self.assertEqual(result['media']['status'],'failed');self.assertIn('encoder failed',result['media']['error'])

    def test_source_change_prevents_overall_pass(self):
        result,_=self.exercise(mutate_source=True)
        self.assertFalse(result['ok']);self.assertFalse(result['source_unchanged'])


if __name__=='__main__':unittest.main()

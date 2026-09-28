"""Portable creative-run receipts with an explicit host launch/capture adapter.

    PYTHONPATH=scripts/harness python3 -m kpharness.creative --help

macOS is a distinct backend, not a Wine alias. Unsupported backends fail before
creating directories or touching a game. Current executable adapter: Linux K1/Wine.
"""
from __future__ import annotations

import argparse
import copy
import contextlib
import datetime
import json
import os
import math
import re
import signal
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import discover, targets
from .creative_checkpoints import CreativeCheckpoints, CheckpointError, child
from .creative_steps import CreativeRunner
from .recording import CREATIVE_MARKER, artifact, render, sha256
from .scenario import Scenario, ScenarioError, find_scenario


class UnsupportedBackend(ValueError):
    pass


_CAPTURE_MARKER_NAME = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


def marker_configuration(options) -> tuple[dict[str, str], str | None, str | None]:
    """Validate portable marker declarations before any run resource is claimed."""
    markers = {'effect_start': options.marker}
    try:
        re.compile(options.marker)
    except re.error as error:
        raise ValueError(f'invalid effect_start marker regex: {error}') from error
    for declaration in options.capture_marker:
        if '=' not in declaration:
            raise ValueError('capture marker must use NAME=REGEX')
        name, pattern = declaration.split('=', 1)
        if not _CAPTURE_MARKER_NAME.fullmatch(name):
            raise ValueError(f'invalid capture marker name: {name}')
        if name in markers:
            raise ValueError(f'duplicate capture marker name: {name}')
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f'invalid capture marker regex for {name}: {error}') from error
        markers[name] = pattern
    start, end = options.cadence_start_marker, options.cadence_end_marker
    if (start is None) != (end is None):
        raise ValueError('cadence start and end markers must be provided together')
    if start is not None and (start not in markers or end not in markers):
        raise ValueError('cadence start/end marker must name a configured capture marker')
    return markers, start, end


def backend(identifier: str):
    if not sys.platform.startswith('linux'):
        raise UnsupportedBackend(f'{identifier}: no validated launch/memory/capture adapter on this host; no files changed')
    from .creative_wine import (DeferredGamescopeRecorder, LinuxWineCreativeSession,
                                LinuxWineGamescopeCreativeSession, claim_directory,
                                disjoint, source_receipt)
    from .recording import X11Recorder
    if identifier == 'linux-wine-k1':
        return LinuxWineCreativeSession, X11Recorder, claim_directory, disjoint, source_receipt
    if identifier == 'linux-wine-k1-gamescope':
        from .display_backends import admit_backend, detect_host
        admission = admit_backend(identifier, detect_host(), reuse_display=bool(os.environ.get('KP_HARNESS_REUSE_DISPLAY')))
        if admission.status != 'admitted':
            raise UnsupportedBackend(f'{identifier}: {admission.reason}; no files changed')
        return LinuxWineGamescopeCreativeSession, DeferredGamescopeRecorder, claim_directory, disjoint, source_receipt
    raise UnsupportedBackend(f'{identifier}: no validated launch/memory/capture adapter on this host; no files changed')


def shared_lock_path(root: Path) -> Path:
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                            capture_output=True, text=True, timeout=5)
    common = Path(result.stdout.strip()) if result.returncode == 0 else root / '.git'
    canonical = common.parent if common.name == '.git' else root
    return canonical / 'tmp/harness-locks/live-game.lock'


@contextlib.contextmanager
def live_lock(path: Path):
    import fcntl  # Only the Linux adapter reaches this lock implementation.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('another live harness owns ' + str(path)) from error
        yield stream


def retired_script_paths(root: Path) -> tuple[set[str], set[Path]]:
    # Public curation follows the checked manifest, not a basename ban. This
    # reads repository metadata only; never inspect a game to validate scripts.
    metadata_root = Path(os.environ['KP_GAMESCOPE_REPO_ROOT']) if os.environ.get('KP_GAMESCOPE_REPO_ROOT') else Path(__file__).resolve().parents[3]
    manifest_path = metadata_root / 'tools/tests/examples/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema') != 2:
        raise ValueError('creative runner requires example manifest schema 2')
    names, paths = set(), set()
    for entry in manifest['examples']:
        if entry['disposition'] != 'retired_public':
            continue
        identity, source = entry['path'], entry['source_path']
        for name in (identity, 'scripts/examples/' + identity, source):
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('invalid retired example path in manifest')
            names.add(relative.as_posix())
        paths.add((root / 'scripts/examples' / identity).resolve())
        paths.add((root / source).resolve())
    return names, paths


def script_inputs(names: list[str], root: Path) -> list[Path]:
    retired_names, retired_paths = retired_script_paths(root)
    scripts = []
    for name in names:
        path = Path(name).expanduser()
        if (path.as_posix() in retired_names or path.resolve() in retired_paths
                or (not path.is_absolute() and (root / path).resolve() in retired_paths)):
            raise ValueError('retired public example; use internal regression tests: ' + name)
        if not path.is_file():
            path = root / 'scripts/examples' / name
        if not path.is_file() or path.suffix != '.lua':
            raise ValueError('script must identify an existing Lua file: ' + name)
        resolved = path.resolve()
        if resolved in retired_paths:
            raise ValueError('retired public example; use internal regression tests: ' + name)
        scripts.append(resolved)
    if not scripts or len({p.name.casefold() for p in scripts}) != len(scripts):
        raise ValueError('supply scripts with unique deployed basenames')
    return scripts


def boot_budget(dev_max_boot_attempts=None) -> dict:
    """Creative runs launch the game once. Validate before any run resource is claimed.

    KP_MAX_BOOT_ATTEMPTS is checked even though the explicit budget below wins,
    so a bad operator value is refused rather than ignored. Only the dev flag
    raises the budget above 1, and such a run is never acceptance-eligible.
    """
    from .session import MAX_BOOT_ATTEMPTS_ENV, resolve_max_boot_attempts
    resolve_max_boot_attempts()
    if dev_max_boot_attempts is None:
        n, source = resolve_max_boot_attempts(1)[0], 'default_single'
    else:
        n, source = resolve_max_boot_attempts(dev_max_boot_attempts)[0], 'dev_override'
    return {'max_boot_attempts': n, 'budget_source': source,
            'env': os.environ.get(MAX_BOOT_ATTEMPTS_ENV)}


def boot_evidence(run_dir: Path, budget: dict) -> dict:
    """Copy the session's boot-attempts.json into the run receipt and judge it."""
    from .session import BOOT_ATTEMPTS_EVIDENCE
    result = {**budget, 'evidence': None, 'record': None, 'launch_count': None,
              'acceptance_eligible': False, 'refusal': None}
    path = run_dir / BOOT_ATTEMPTS_EVIDENCE
    try:
        if path.is_symlink() or not path.is_file():
            result['refusal'] = f'{BOOT_ATTEMPTS_EVIDENCE} missing'
            return result
        result['evidence'] = artifact(path)
        record = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        result['refusal'] = f'{BOOT_ATTEMPTS_EVIDENCE} unreadable: {error}'
        return result
    result['record'] = record
    if not isinstance(record, dict):
        result['refusal'] = f'{BOOT_ATTEMPTS_EVIDENCE} is not an object'
        return result
    count = record.get('launch_count')
    result['launch_count'] = count
    if budget['budget_source'] != 'default_single' or budget['max_boot_attempts'] != 1:
        result['refusal'] = 'dev boot budget override; not an acceptance run'
    elif record.get('max_boot_attempts') != 1:
        result['refusal'] = f"session budget {record.get('max_boot_attempts')!r} != 1"
    elif type(count) is not int or count != 1:
        result['refusal'] = f'launch_count {count!r} != 1'
    else:
        result['acceptance_eligible'] = True
    return result


def run_creative(options, *, adapter_factory=backend, runner_factory=CreativeRunner, renderer=render) -> dict:
    session_type, recorder_type, claim, disjoint, snapshot = adapter_factory(options.backend)
    # Before any lock, run directory, ledger head or stage/prefix claim.
    budget = boot_budget(getattr(options, 'dev_max_boot_attempts', None))
    if not 0 < options.boot_timeout <= 600 or not math.isfinite(options.boot_timeout):
        raise ValueError('boot timeout must be finite and in (0,600] seconds')
    if any(n <= 0 or n > 4096 or n % 2 for n in (options.width, options.height)):
        raise ValueError('screen dimensions must be positive even values up to4096')
    if not 1 <= options.capture_fps <= 120:
        raise ValueError('capture FPS must be an integer in [1,120]')
    named_markers, cadence_start_marker, cadence_end_marker = marker_configuration(options)
    root = discover.repo_root()
    originals = script_inputs(options.script, root)
    route = find_scenario(options.route).resolve()
    scenario = Scenario.load(route)
    if scenario.target != 'k1' or options.target not in (None, scenario.target):
        raise UnsupportedBackend(f'{options.backend} does not support route target {scenario.target}')
    if scenario.settings['game_speed'] != 1.0:
        raise ValueError('creative routes require explicit game_speed=1.0 for recorded behavior')
    source = discover.data_dir(targets.get(scenario.target), options.source)
    build = discover.build_dir(options.build_dir)
    for name in targets.get(scenario.target).runtime_files:
        if not (build / name).is_file():
            raise ValueError('runtime not built: ' + str(build / name))
    if not shutil.which(options.ffmpeg) or not shutil.which(options.ffprobe):
        raise ValueError('ffmpeg and ffprobe must be available before launching')
    output = Path(options.output).expanduser().resolve() if options.output else root / 'tmp/creative-runs'
    run_dir = output / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    commitment_log = getattr(options, 'cleanup_commitment_log', None)
    if options.backend == 'linux-wine-k1-gamescope':
        from .creative_accept import validate_commitment_log
        # Refuse before claiming a run directory if the launch head cannot leave it.
        validate_commitment_log(commitment_log, run_dir)
    stage = Path(options.staged).expanduser() if options.staged else output / 'stage-k1'
    prefix = Path(options.wineprefix).expanduser() if options.wineprefix else output / 'wineprefix-k1'
    if not all(disjoint(a, b) for a, b in [(source, stage), (source, prefix), (source, output),
                                          (stage, prefix), (run_dir, stage), (run_dir, prefix),
                                          (build, stage), (build, prefix)]):
        raise ValueError('source/build/stage/prefix/run paths overlap unsafely')
    checkpoint_root = (Path(options.checkpoint_root).expanduser() if options.checkpoint_root
                       else root / 'tmp/checkpoints' / scenario.target).resolve()
    if not all(disjoint(checkpoint_root, path) for path in (source, stage, prefix, build, run_dir)):
        raise ValueError('checkpoint root overlaps source/stage/prefix/build/run paths')
    # Validate every declared destination before claiming directories or booting.
    for step in scenario.steps:
        name = step.raw.get('checkpoint') if step.raw.get('do') == 'save' else (
            step.raw.get('name') if step.raw.get('do') == 'load_checkpoint' else None)
        if name is not None:
            child(checkpoint_root, name)
    lock = shared_lock_path(root)
    with live_lock(lock) as lock_stream:
        # Never use a name match to kill another game. Refuse a concurrent K1,
        # even in another prefix; actual teardown filters owned prefix AND cwd.
        from .session import pids_by_name
        if pids_by_name('swkotor.exe'):
            raise RuntimeError('an existing K1 game is running; refusing concurrent creative launch')
        run_dir.mkdir(parents=True, exist_ok=False)
        cleanup_ledger_launch = None
        if options.backend == 'linux-wine-k1-gamescope':
            from .creative_accept import _load_cleanup_ledger, initialize_cleanup_ledger
            # Prints and commits the per-run launch head before any child starts.
            launch_head = initialize_cleanup_ledger(run_dir, commitment_log=commitment_log)
            cleanup_ledger_launch = {'sha256': launch_head,
                                     'nonce': _load_cleanup_ledger(run_dir)[0]['nonce']}
        source_before = snapshot(source)
        input_before = {str(p): sha256(p) for p in [route, *originals, *(build / f for f in targets.get(scenario.target).runtime_files)]}
        run_manifest = None
        if options.backend == 'linux-wine-k1-gamescope':
            from .gamescope_snapshot import create_run_manifest, verify_run_manifest
            snapshot_root = os.environ.get('KP_GAMESCOPE_HARNESS_SNAPSHOT')
            if not snapshot_root:
                raise RuntimeError('Gamescope run requires a verified snapshot driver')
            run_manifest = create_run_manifest(run_dir, snapshot=Path(snapshot_root),
                inputs=input_before, source=source, source_before=source_before)
            verify_run_manifest(run_dir)
        stage, prefix = claim(stage, source), claim(prefix, source)
        input_dir = run_dir / 'sources'
        input_dir.mkdir()
        frozen = []
        for path in originals:
            destination = input_dir / path.name
            shutil.copy2(path, destination)
            if sha256(destination) != input_before[str(path)]:
                raise ValueError('script changed during input snapshot: ' + str(path))
            frozen.append(destination)
        route_copy = run_dir / 'executed-route.toml'
        shutil.copy2(route, route_copy)
        if sha256(route_copy) != input_before[str(route)]:
            raise ValueError('route changed during input snapshot')
        scenario = Scenario.load(route_copy)
        recorder = recorder_type(run_dir, ffmpeg=options.ffmpeg, fps=options.capture_fps,
            marker_pattern=options.marker, named_markers=named_markers,
            cadence_start_marker=cadence_start_marker, cadence_end_marker=cadence_end_marker,
            # The recorder's FFmpeg, FFprobe, and xwininfo children inherit the held live lock.
            **({'ffprobe': options.ffprobe, 'inherited_fds': (lock_stream.fileno(),)}
               if options.backend == 'linux-wine-k1-gamescope' else {}))
        driver_log = (run_dir / 'driver.log').open('w')
        def log(message):
            print(message, flush=True); driver_log.write(message + '\n'); driver_log.flush()
        session = session_type(source=source, scripts=frozen, recorder=recorder, run_dir=run_dir,
                               build_dir=str(build), staged=str(stage), wineprefix=str(prefix),
                               boot_timeout=options.boot_timeout, screen=(options.width, options.height), log=log,
                               max_boot_attempts=budget['max_boot_attempts'])
        route_info = route_copy.stat()
        route_source = {**artifact(route_copy), 'identity': {
            'device': route_info.st_dev, 'inode': route_info.st_ino, 'size': route_info.st_size,
            'mtime_ns': route_info.st_mtime_ns, 'ctime_ns': route_info.st_ctime_ns,
            'links': route_info.st_nlink}}
        receipt = {'schema': 2 if options.backend == 'linux-wine-k1-gamescope' else 1,
                   'backend': options.backend, 'target': scenario.target,
                   'run_dir': str(run_dir), 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'source': str(source), 'stage': str(stage), 'wineprefix': str(prefix), 'shared_lock': str(lock),
                   'inputs': input_before, 'route_source': route_source,
                   'route': {'status': 'not_started'}, 'media': {'status': 'not_started'},
                   'cleanup': {'status': 'not_started'}, 'source_preservation_scope': list(source_before),
                   'scope': 'route and media execution; no automatic per-example semantic/live predicate promotion', 'ok': False}
        if cleanup_ledger_launch is not None:
            receipt['cleanup_ledger_launch'] = cleanup_ledger_launch
        if run_manifest is not None:
            receipt['run_manifest'] = {'path': str(run_dir / 'gamescope-run-manifest.json'),
                                       'sha256': sha256(run_dir / 'gamescope-run-manifest.json')}
        (run_dir / 'source-before.json').write_text(json.dumps(source_before, indent=2) + '\n')
        route_start = 0.0
        try:
            channel = session.boot(resources=list(scenario.resources.values()))
            receipt['build'] = session.build
            receipt['deployed_scripts'] = session.deployed
            receipt['runtime'] = {name: artifact(session.game_dir / name) for name in targets.get(scenario.target).runtime_files}
            if any(value['sha256'] != input_before[str(build / name)] for name, value in receipt['runtime'].items()):
                raise RuntimeError('deployed runtime differs from selected build bytes')
            if run_manifest is not None:
                # The immutable plan names these stage destinations; after staging
                # both the manifest inputs and the deployed bytes must still bind.
                from .gamescope_snapshot import verify_run_manifest
                verify_run_manifest(run_dir)
            if recorder.process is None or recorder.process.poll() is not None:
                raise RuntimeError('continuous recorder exited before the route')
            route_start = time.monotonic() - recorder.started
            checkpoints = CreativeCheckpoints(session.target, session.save_dir, root=checkpoint_root)
            receipt['checkpoint_root'] = str(checkpoints.root)
            receipt['checkpoint_sources'] = {}
            for step in scenario.steps:
                if step.raw.get('do') == 'load_checkpoint':
                    name = step.raw['name']
                    checkpoint = checkpoints.path(name)
                    receipt['checkpoint_sources'][name] = {
                        str(path.relative_to(checkpoint)): sha256(path)
                        for path in sorted(checkpoint.rglob('*')) if path.is_file()}
            report = runner_factory(scenario, session, channel, checkpoints=checkpoints, log=log).run()
            route_ok = (report.ok and all(step.status == 'ok' for step in report.steps)
                        and report.scenario == scenario.name and report.target == scenario.target
                        and report.build == session.build
                        and len(report.steps) == len(scenario.steps)
                        and all(result.index == step.index and result.description == step.describe()
                                for result, step in zip(report.steps, scenario.steps)))
            persisted_report = json.loads((run_dir / 'report.json').read_text())
            receipt['route'] = {'status': 'passed' if route_ok else 'failed',
                                'report': artifact(run_dir / 'report.json'),
                                'steps': copy.deepcopy(persisted_report.get('steps', [])),
                                'predicates_passed': route_ok,
                                'execution_identity': {
                                    'scenario': scenario.name, 'target': scenario.target,
                                    'build': session.build,
                                    'route_source_sha256': receipt['route_source']['sha256'],
                                    'runtime_sha256': {name: value['sha256']
                                        for name, value in receipt['runtime'].items()}},
                                'diagnosis': 'route predicates only; inspect raw report before attributing failure to an example'}
            route_end = time.monotonic() - recorder.started
            receipt['route']['capture_interval'] = {
                'start_seconds': route_start, 'end_seconds': route_end}
            set_route_interval = getattr(recorder, 'set_route_interval', None)
            if callable(set_route_interval) and route_end > route_start:
                set_route_interval(route_start, route_end)
            check_capture = getattr(session, 'check_capture', None)
            if callable(check_capture):
                try:
                    check_capture()
                    receipt['capture_gate'] = {'status': 'passed'}
                except BaseException as error:
                    receipt['capture_gate'] = {'status': 'failed',
                        'error': f'{type(error).__name__}: {error}'}
                    log(receipt['capture_gate']['error'])
            if recorder.process.poll() is not None:
                recorder.error = 'continuous recorder exited before route completion'
                receipt['capture_gate'] = {'status': 'failed', 'error': recorder.error}
        except BaseException as error:
            receipt['route'] = {'status': 'failed', 'error': f'{type(error).__name__}: {error}',
                                'diagnosis': 'boot/control/route failure; not automatically a Lua-example defect'}
            log(receipt['route']['error'])
        finally:
            try:
                session.teardown()
                receipt['cleanup'] = getattr(session, 'cleanup_receipt', {'status': 'passed'})
            except BaseException as error:
                receipt['cleanup'] = dict(getattr(session, 'cleanup_receipt', {'status': 'failed'}))
                receipt['cleanup']['status'] = 'failed'
                receipt['cleanup']['error'] = f'{type(error).__name__}: {error}'
            driver_log.close()
            receipt['boot_attempts'] = boot_evidence(run_dir, budget)
            try:
                if run_manifest is not None:
                    verify_run_manifest(run_dir)
                after = snapshot(source)
                (run_dir / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n')
                receipt['source_unchanged'] = after == source_before
                receipt['inputs_unchanged'] = all(Path(path).is_file() and sha256(Path(path)) == expected for path, expected in input_before.items())
            except (OSError, ValueError) as error:
                receipt['source_unchanged'] = False
                receipt['identity_error'] = str(error)
        continuous = run_dir / 'continuous.mp4'
        receipt['media'] = {'status': 'retained_failure_recording', 'error': recorder.error}
        if continuous.is_file():
            receipt['media']['continuous'] = artifact(continuous)
        if (options.backend != 'linux-wine-k1-gamescope'
                and receipt['route']['status'] == 'passed' and not recorder.error
                and receipt['cleanup']['status'] == 'passed'
                and receipt.get('source_unchanged') is True and receipt.get('inputs_unchanged') is True):
            try:
                media = renderer(run_dir, marker=recorder.marker, route_start=route_start,
                                 ffmpeg=options.ffmpeg, ffprobe=options.ffprobe)
                receipt['media'] = {'status': 'passed', **media}
            except Exception as error:
                receipt['media']['status'] = 'failed'
                receipt['media']['error'] = f'{type(error).__name__}: {error}'
        elif recorder.error:
            receipt['media']['status'] = 'failed'
        receipt['ok'] = (receipt['route']['status'] == 'passed' and receipt['media']['status'] == 'passed'
                         and receipt['cleanup']['status'] == 'passed' and receipt.get('source_unchanged') is True
                         and receipt.get('inputs_unchanged') is True
                         and receipt['boot_attempts']['acceptance_eligible'] is True)
        if options.backend == 'linux-wine-k1-gamescope' and session.owned_window is not None:
            from .display_backends import admit_backend, detect_host, schema2_receipt
            console_steps = [step for step in scenario.steps if step.raw.get('do') == 'console_command']
            console_correlated = bool(console_steps) and all(
                (run_dir / f'console-command-{step.index}.json').is_file() for step in console_steps)
            recorder_snapshot = recorder.receipt()
            receipt.update(schema2_receipt(
                facts=detect_host(), capabilities=admit_backend(options.backend, detect_host()),
                lease=session.lease, window=session.owned_window, recorder=recorder_snapshot,
                route_passed=receipt['route']['status'] == 'passed',
                console_correlated=console_correlated, cleanup=receipt['cleanup'],
                source_unchanged=receipt.get('source_unchanged') is True,
                inputs_unchanged=receipt.get('inputs_unchanged') is True,
                visual_status='pending', route_receipt=receipt['route'],
                capture_gate=receipt.get('capture_gate')))
        if not receipt['boot_attempts']['acceptance_eligible']:
            # creative_accept.accept() proceeds only from a pending review.
            receipt['ok'] = False
            receipt['acceptance_ready'] = False
            if isinstance(receipt.get('visual_review'), dict):
                receipt['visual_review']['status'] = 'refused_boot_budget'
                receipt['visual_review']['refusal'] = receipt['boot_attempts']['refusal']
        receipt['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (run_dir / 'creative-run.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--backend', required=True, help='linux-wine-k1 or linux-wine-k1-gamescope; other platforms fail unsupported')
    result.add_argument('--target', help='optional consistency check against route target')
    result.add_argument('--script', action='append', required=True, help='example-relative or explicit Lua path; repeat for probes/observers')
    result.add_argument('--route', required=True, help='existing ScenarioRunner TOML path or scenario name')
    for name in ('source', 'build-dir', 'staged', 'wineprefix', 'checkpoint-root', 'output'):
        result.add_argument('--' + name)
    result.add_argument('--capture-fps', type=int, default=60, help='real X11 capture sampling rate, 1..120; no interpolation')
    result.add_argument('--width', type=int, default=1024)
    result.add_argument('--height', type=int, default=768)
    result.add_argument('--boot-timeout', type=float, default=120)
    result.add_argument('--dev-max-boot-attempts', type=int, metavar='N',
                        help='development only: allow up to N (1..5) game launches; never acceptance-eligible. '
                             'Default: exactly one launch')
    result.add_argument('--ffmpeg', default='ffmpeg')
    result.add_argument('--ffprobe', default='ffprobe')
    result.add_argument('--marker', default=CREATIVE_MARKER, help='native log regex selecting first creative action for the clip')
    result.add_argument('--capture-marker', action='append', default=[], metavar='NAME=REGEX',
                        help='portable named native-log marker; repeat as needed')
    result.add_argument('--cadence-start-marker', help='named marker beginning cadence acceptance interval')
    result.add_argument('--cadence-end-marker', help='named marker ending cadence acceptance interval')
    result.add_argument('--cleanup-commitment-log',
                        help='Gamescope: existing operator file outside the run directory; receives every cleanup-ledger head')
    return result


def main(argv=None):
    # Ensure a service stop runs the same owned-recorder/session finally path.
    previous = signal.getsignal(signal.SIGTERM)
    def terminated(signum, frame):
        raise KeyboardInterrupt('SIGTERM')
    signal.signal(signal.SIGTERM, terminated)
    try:
        receipt = run_creative(parser().parse_args(argv))
    except (ValueError, OSError, RuntimeError, ScenarioError, CheckpointError, re.error, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'phase': 'preflight', 'error': str(error)}))
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps({'ok': receipt['ok'], 'run_dir': receipt['run_dir'],
                      'route': receipt['route']['status'], 'media': receipt['media']['status']}))
    return 0 if receipt['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

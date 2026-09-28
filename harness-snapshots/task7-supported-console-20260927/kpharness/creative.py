"""Portable creative-run receipts with an explicit host launch/capture adapter.

    PYTHONPATH=scripts/harness python3 -m kpharness.creative --help

macOS is a distinct backend, not a Wine alias. Unsupported backends fail before
creating directories or touching a game. Current executable adapter: Linux K1/Wine.
"""
from __future__ import annotations

import argparse
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


def backend(identifier: str):
    if identifier != 'linux-wine-k1' or not sys.platform.startswith('linux'):
        raise UnsupportedBackend(f'{identifier}: no validated launch/memory/capture adapter on this host; no files changed')
    from .creative_wine import LinuxWineCreativeSession, claim_directory, disjoint, source_receipt
    from .recording import X11Recorder
    return LinuxWineCreativeSession, X11Recorder, claim_directory, disjoint, source_receipt


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
        yield


def retired_script_paths(root: Path) -> tuple[set[str], set[Path]]:
    # Public curation follows the checked manifest, not a basename ban. This
    # reads repository metadata only; never inspect a game to validate scripts.
    manifest_path = Path(__file__).resolve().parents[3] / 'tools/tests/examples/manifest.json'
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


def run_creative(options, *, adapter_factory=backend, runner_factory=CreativeRunner, renderer=render) -> dict:
    session_type, recorder_type, claim, disjoint, snapshot = adapter_factory(options.backend)
    if not 0 < options.boot_timeout <= 600 or not math.isfinite(options.boot_timeout):
        raise ValueError('boot timeout must be finite and in (0,600] seconds')
    if any(n <= 0 or n > 4096 or n % 2 for n in (options.width, options.height)):
        raise ValueError('screen dimensions must be positive even values up to4096')
    if not 1 <= options.capture_fps <= 120:
        raise ValueError('capture FPS must be an integer in [1,120]')
    re.compile(options.marker)
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
    with live_lock(lock):
        # Never use a name match to kill another game. Refuse a concurrent K1,
        # even in another prefix; actual teardown filters owned prefix AND cwd.
        from .session import pids_by_name
        if pids_by_name('swkotor.exe'):
            raise RuntimeError('an existing K1 game is running; refusing concurrent creative launch')
        stage, prefix = claim(stage, source), claim(prefix, source)
        run_dir.mkdir(parents=True, exist_ok=False)
        source_before = snapshot(source)
        input_before = {str(p): sha256(p) for p in [route, *originals, *(build / f for f in targets.get(scenario.target).runtime_files)]}
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
        recorder = recorder_type(run_dir, ffmpeg=options.ffmpeg, fps=options.capture_fps, marker_pattern=options.marker)
        driver_log = (run_dir / 'driver.log').open('w')
        def log(message):
            print(message, flush=True); driver_log.write(message + '\n'); driver_log.flush()
        session = session_type(source=source, scripts=frozen, recorder=recorder, run_dir=run_dir,
                               build_dir=str(build), staged=str(stage), wineprefix=str(prefix),
                               boot_timeout=options.boot_timeout, screen=(options.width, options.height), log=log)
        receipt = {'schema': 1, 'backend': options.backend, 'target': scenario.target,
                   'run_dir': str(run_dir), 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'source': str(source), 'stage': str(stage), 'wineprefix': str(prefix), 'shared_lock': str(lock),
                   'inputs': input_before, 'route_source': artifact(route_copy),
                   'route': {'status': 'not_started'}, 'media': {'status': 'not_started'},
                   'cleanup': {'status': 'not_started'}, 'source_preservation_scope': list(source_before),
                   'scope': 'route and media execution; no automatic per-example semantic/live predicate promotion', 'ok': False}
        (run_dir / 'source-before.json').write_text(json.dumps(source_before, indent=2) + '\n')
        route_start = 0.0
        try:
            channel = session.boot(resources=list(scenario.resources.values()))
            receipt['build'] = session.build
            receipt['deployed_scripts'] = session.deployed
            receipt['runtime'] = {name: artifact(session.game_dir / name) for name in targets.get(scenario.target).runtime_files}
            if any(value['sha256'] != input_before[str(build / name)] for name, value in receipt['runtime'].items()):
                raise RuntimeError('deployed runtime differs from selected build bytes')
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
            route_ok = report.ok and all(step.status == 'ok' for step in report.steps)
            receipt['route'] = {'status': 'passed' if route_ok else 'failed',
                                'report': artifact(run_dir / 'report.json'),
                                'diagnosis': 'route predicates only; inspect raw report before attributing failure to an example'}
            if recorder.process.poll() is not None:
                recorder.error = 'continuous recorder exited before route completion'
        except BaseException as error:
            receipt['route'] = {'status': 'failed', 'error': f'{type(error).__name__}: {error}',
                                'diagnosis': 'boot/control/route failure; not automatically a Lua-example defect'}
            log(receipt['route']['error'])
        finally:
            try:
                session.teardown()
                receipt['cleanup'] = {'status': 'passed'}
            except BaseException as error:
                receipt['cleanup'] = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
            driver_log.close()
            try:
                after = snapshot(source)
                (run_dir / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n')
                receipt['source_unchanged'] = after == source_before
                receipt['inputs_unchanged'] = all(Path(path).is_file() and sha256(Path(path)) == expected for path, expected in input_before.items())
            except OSError as error:
                receipt['source_unchanged'] = False
                receipt['identity_error'] = str(error)
        continuous = run_dir / 'continuous.mp4'
        receipt['media'] = {'status': 'retained_failure_recording', 'error': recorder.error}
        if continuous.is_file():
            receipt['media']['continuous'] = artifact(continuous)
        if (receipt['route']['status'] == 'passed' and not recorder.error
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
                         and receipt.get('inputs_unchanged') is True)
        receipt['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (run_dir / 'creative-run.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--backend', required=True, help='linux-wine-k1; macos-k1/macos-k2 currently fail unsupported')
    result.add_argument('--target', help='optional consistency check against route target')
    result.add_argument('--script', action='append', required=True, help='example-relative or explicit Lua path; repeat for probes/observers')
    result.add_argument('--route', required=True, help='existing ScenarioRunner TOML path or scenario name')
    for name in ('source', 'build-dir', 'staged', 'wineprefix', 'checkpoint-root', 'output'):
        result.add_argument('--' + name)
    result.add_argument('--capture-fps', type=int, default=60, help='real X11 capture sampling rate, 1..120; no interpolation')
    result.add_argument('--width', type=int, default=1024)
    result.add_argument('--height', type=int, default=768)
    result.add_argument('--boot-timeout', type=float, default=120)
    result.add_argument('--ffmpeg', default='ffmpeg')
    result.add_argument('--ffprobe', default='ffprobe')
    result.add_argument('--marker', default=CREATIVE_MARKER, help='native log regex selecting first creative action for the clip')
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

"""Three log/tick helpers layered on the existing ScenarioRunner TOML steps."""
from __future__ import annotations

import json
import re
import time

from .scenario import ScenarioRunner, _StepFailure


class CreativeRunner(ScenarioRunner):
    log_offset = 0

    def sync_cursor(self):
        # Snapshot once. Draining until empty starves actions under continuous
        # probe traffic and can outlast a six-second creative effect.
        watermark = self.ch.status().get('events_seq')
        if type(watermark) is not int or watermark < 0:
            raise _StepFailure('status lacks a valid events_seq watermark')
        self.ch.cursor = max(self.ch.cursor, watermark)
        return self.ch.cursor

    def _capture_check(self):
        check = getattr(self.session, 'check_capture', None)
        if callable(check): check()

    def run_step(self, step):
        self._capture_check()
        result = super().run_step(step)
        self._capture_check()
        return result

    def _do(self, step):
        capture_check = getattr(self.session, 'check_capture', None)
        if callable(capture_check):
            capture_check()
        raw = step.raw
        verb = raw.get('do')
        if verb not in {'mark_log', 'await_log', 'advance_ticks'}:
            result = super()._do(step)
            if callable(capture_check):
                capture_check()
            return result
        path = self.session.runtime_log
        if verb == 'mark_log':
            self.log_offset = path.stat().st_size if path.exists() else 0
            result = f'native log offset {self.log_offset}'
            if callable(capture_check): capture_check()
            return result
        timeout = float(raw.get('timeout', 120))
        if not 0 < timeout <= 600:
            raise _StepFailure('creative helper timeout must be in (0,600] seconds')
        deadline = time.monotonic() + timeout
        if verb == 'advance_ticks':
            ticks = raw.get('ticks')
            if type(ticks) is not int or not 1 <= ticks <= 100000:
                raise _StepFailure('advance_ticks requires ticks in1..100000')
            clock = raw.get('clock', 'server')
            if clock not in {'server', 'client'}:
                raise _StepFailure('advance_ticks clock must be server or client')
            tick_key = clock + '_tick'
            start = int(self.ch.state()[tick_key])
            target = start + ticks
        else:
            pattern = re.compile(raw['pattern'])
            minimum, maximum = raw.get('minimum', 1), raw.get('maximum')
            if type(minimum) is not int or minimum < 0 or (maximum is not None and (type(maximum) is not int or maximum < minimum)):
                raise _StepFailure('invalid native log match bounds')
        while True:
            if callable(capture_check): capture_check()
            state = self.ch.state()
            if verb == 'advance_ticks':
                tick = int(state[tick_key])
                if tick < start:
                    raise _StepFailure(f'{clock} tick reset before requested interval', state=state)
                if tick >= target:
                    if callable(capture_check): capture_check()
                    return f'observed {clock} ticks {start} -> {tick}'
            else:
                if path.exists():
                    if path.stat().st_size < self.log_offset:
                        raise _StepFailure('native log truncated after mark_log', state=state)
                    with path.open('rb') as stream:
                        stream.seek(self.log_offset)
                        lines = [line for line in stream.read().decode('utf-8', 'replace').splitlines() if pattern.search(line)]
                else:
                    lines = []
                if maximum is not None and len(lines) > maximum:
                    raise _StepFailure('too many matching native log lines', state=state)
                if len(lines) >= minimum:
                    (self.run_dir / f'log-gate-{step.index}.json').write_text(json.dumps(
                        {'pattern': raw['pattern'], 'offset': self.log_offset, 'lines': lines}, indent=2) + '\n')
                    if callable(capture_check): capture_check()
                    return f'native log matched {len(lines)} lines'
            verdict = self.watchdog.check(state)
            if verdict:
                raise _StepFailure(str(verdict), verdict=verdict, state=state)
            if time.monotonic() >= deadline:
                raise _StepFailure(f'{verb} predicate not reached', state=state)
            time.sleep(.2)

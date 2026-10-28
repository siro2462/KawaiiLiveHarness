"""Bounded filesystem request protocol; DONE is checked after the last call."""
import json
import time


def request_stream(root, max_calls, request_timeout=7200, done_timeout=120, poll=.25):
    n = 1
    deadline = time.monotonic() + request_timeout
    while True:
        if (root / 'stop_requested.json').exists():
            raise RuntimeError('Controller requested stop')
        path = root / 'requests' / f'R{n:04}.json'
        done_path = root / 'requests/DONE.json'
        if n > max_calls and path.exists():
            raise RuntimeError('Actual request exceeds call budget')
        if done_path.exists():
            done = json.loads(done_path.read_text(encoding='utf-8-sig'))
            if type(done.get('calls')) is not int or not 0 <= done['calls'] <= max_calls:
                raise ValueError('Invalid DONE call count')
            if n > done['calls']:
                if n - 1 != done['calls'] or path.exists():
                    raise ValueError('DONE/request count mismatch')
                return
            if not path.exists():
                raise ValueError('DONE claims a missing request')
        if n <= max_calls and path.exists():
            yield n, path
            n += 1
            deadline = time.monotonic() + (done_timeout if n > max_calls else request_timeout)
            continue
        if time.monotonic() > deadline:
            raise TimeoutError('DONE absent after budget' if n > max_calls else 'Controller request absent')
        time.sleep(poll)

"""Atomic JSON state replacement with bounded Windows sharing retries."""
import json
import os
import tempfile
import time
from pathlib import Path

def write(path, data, timeout=10.0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        deadline = time.monotonic() + timeout
        delay = .02
        while True:
            try:
                os.replace(temp, path)
                return
            except OSError as exc:
                if os.name != 'nt' or getattr(exc, 'winerror', None) not in (5, 32, 33) or time.monotonic() >= deadline:
                    raise
                time.sleep(min(delay, max(0, deadline-time.monotonic())))
                delay = min(.2, delay*2)
    finally:
        temp.unlink(missing_ok=True)

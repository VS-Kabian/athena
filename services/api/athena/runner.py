"""Run registry + concurrency gate for research runs.

- A strong reference to each run's asyncio.Task (so the fire-and-forget task isn't GC'd, and can
  actually be cancelled).
- A lazily-created global semaphore that bounds how many runs execute at once (extras queue).
"""
import asyncio

from .config import settings

_TASKS: dict[str, asyncio.Task] = {}
_sem: asyncio.Semaphore | None = None


def register(run_id: str, task: asyncio.Task) -> None:
    _TASKS[run_id] = task
    task.add_done_callback(lambda _t: _TASKS.pop(run_id, None))


def cancel_task(run_id: str) -> bool:
    t = _TASKS.get(run_id)
    if t and not t.done():
        t.cancel()
        return True
    return False


def active() -> int:
    return len(_TASKS)


def semaphore() -> asyncio.Semaphore:
    # lazy so it binds to the running loop, not import-time. The bound comes from
    # settings.max_concurrent_runs (single source of truth; honors .env) instead of a separate
    # os.environ read here, so a value set only in .env is respected by the enforcing component (F-017).
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(settings.max_concurrent_runs)
    return _sem

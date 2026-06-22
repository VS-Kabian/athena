import asyncio

_TERMINAL = ("done", "error", "cancelled", "failed")
_MAX_RUNS = 512      # bound retained backlogs so many runs can't grow memory without limit
_MAX_BACKLOG = 5000  # per-run event cap (ring buffer); oldest events drop, newest always kept


class EventBus:
    """In-process event bus with a per-run append-only backlog and replay-by-index subscribers.

    Each subscriber tracks its own position, so: (1) events published before the client connects
    are still delivered, (2) multiple subscribers (two tabs) each get the FULL stream instead of
    racing to consume a shared queue, and (3) a reconnecting client replays from the start. The
    backlog is bounded by run count; old runs are evicted FIFO.
    """

    def __init__(self):
        self._backlog: dict[str, list[dict]] = {}
        self._offset: dict[str, int] = {}   # events dropped from the front of each run's backlog
        self._waiters: dict[str, asyncio.Event] = {}
        self._cancelled: set[str] = set()
        self._evicted: set[str] = set()     # runs whose backlog was reclaimed -> tell live subscribers

    def _evt(self, run_id: str) -> asyncio.Event:
        e = self._waiters.get(run_id)
        if e is None:
            e = asyncio.Event()
            self._waiters[run_id] = e
        return e

    async def publish(self, run_id: str, event: dict):
        if run_id not in self._backlog:
            self._evicted.discard(run_id)                    # a fresh run reusing this id is live again
            if len(self._backlog) >= _MAX_RUNS:
                oldest = next(iter(self._backlog))           # FIFO-evict the oldest run's backlog
                self._backlog.pop(oldest, None)
                self._offset.pop(oldest, None)
                self._cancelled.discard(oldest)
                self._evicted.add(oldest)
                w = self._waiters.pop(oldest, None)
                if w is not None:
                    w.set()                                  # wake any blocked subscriber so it can exit
                if len(self._evicted) > _MAX_RUNS:
                    self._evicted.clear()                    # bound; stale entries only matter to live subs
        bl = self._backlog.setdefault(run_id, [])
        bl.append(event)
        if len(bl) > _MAX_BACKLOG:                           # ring-buffer: drop oldest, keep newest
            drop = len(bl) - _MAX_BACKLOG
            del bl[:drop]
            self._offset[run_id] = self._offset.get(run_id, 0) + drop
        self._evt(run_id).set()                              # wake every subscriber
        if event.get("type") in _TERMINAL:
            self._cancelled.discard(run_id)

    async def subscribe_seq(self, run_id: str, last_event_id: int | None = None):
        """Yield ``(seq, event)`` where ``seq`` is the event's absolute index (the SSE ``id:``).
        ``last_event_id`` resumes AFTER that index, so a reconnecting client receives only NEWER events
        instead of replaying the whole backlog (which would re-append every source, double counters, ...)."""
        # absolute event index across the run's lifetime (survives ring-buffer drops). A resume starts
        # just past the last id the client confirmed; the offset clamp below handles a resume point that
        # already fell out of the ring buffer.
        i = 0 if last_event_id is None else max(int(last_event_id) + 1, 0)
        while True:
            if run_id in self._evicted and not self._backlog.get(run_id):
                return   # run's backlog was FIFO-evicted -> nothing left to deliver; end the stream cleanly
            off = self._offset.get(run_id, 0)
            if i < off:
                i = off                                      # fell behind dropped events -> resume at oldest kept
            backlog = self._backlog.get(run_id, [])
            while i - off < len(backlog):
                ev = backlog[i - off]
                seq = i
                i += 1
                yield seq, ev
                if ev["type"] in _TERMINAL:
                    self._cancelled.discard(run_id)
                    return
            evt = self._evt(run_id)
            evt.clear()
            cur = self._backlog.get(run_id, [])
            if i - self._offset.get(run_id, 0) < len(cur):   # publish raced our clear -> don't sleep
                continue
            await evt.wait()

    async def subscribe(self, run_id: str):
        """Backward-compatible bare-event stream (replays from the start)."""
        async for _seq, ev in self.subscribe_seq(run_id):
            yield ev

    def cancel(self, run_id: str): self._cancelled.add(run_id)
    def is_cancelled(self, run_id: str) -> bool: return run_id in self._cancelled


bus = EventBus()

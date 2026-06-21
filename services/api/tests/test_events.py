import pytest, asyncio
from athena.api.events import EventBus

@pytest.mark.asyncio
async def test_publish_and_subscribe():
    bus = EventBus()
    got = []
    async def consume():
        async for ev in bus.subscribe("run1"):
            got.append(ev)
            if ev["type"] == "done": break
    task = asyncio.create_task(consume())
    await bus.publish("run1", {"type": "status", "data": {"s": "searching"}})
    await bus.publish("run1", {"type": "done", "data": {}})
    await asyncio.wait_for(task, timeout=2)
    assert got[0]["type"] == "status" and got[-1]["type"] == "done"

@pytest.mark.asyncio
async def test_cancel_flag():
    bus = EventBus()
    bus.cancel("run1")
    assert bus.is_cancelled("run1")


@pytest.mark.asyncio
async def test_events_published_before_subscribe_are_replayed():
    bus = EventBus()
    await bus.publish("run2", {"type": "round_start", "data": {"round": 1}})
    await bus.publish("run2", {"type": "done", "data": {}})
    got = []
    async for ev in bus.subscribe("run2"):           # subscribes AFTER the events were published
        got.append(ev)
    assert [e["type"] for e in got] == ["round_start", "done"]


@pytest.mark.asyncio
async def test_two_subscribers_each_get_the_full_stream():
    bus = EventBus()
    async def consume():
        out = []
        async for ev in bus.subscribe("run3"):
            out.append(ev["type"])
            if ev["type"] == "done":
                break
        return out
    t1 = asyncio.create_task(consume())
    t2 = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await bus.publish("run3", {"type": "source", "data": {}})
    await bus.publish("run3", {"type": "done", "data": {}})
    a, b = await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2)
    assert a == ["source", "done"] and b == ["source", "done"]   # neither tab loses events


@pytest.mark.asyncio
async def test_backlog_is_ring_buffered(monkeypatch):
    """A long run can't grow a run's backlog without limit: oldest events drop, newest are kept,
    and a late subscriber still replays from the oldest retained event through the terminal one."""
    import athena.api.events as ev
    monkeypatch.setattr(ev, "_MAX_BACKLOG", 5)
    bus = ev.EventBus()
    for i in range(8):
        await bus.publish("r", {"type": "source", "data": {"i": i}})
    await bus.publish("r", {"type": "done", "data": {}})
    assert len(bus._backlog["r"]) <= 5                  # capped
    assert bus._offset["r"] == 4                        # 9 events - 5 kept = 4 dropped
    got = []
    async for e in bus.subscribe("r"):                  # subscribes AFTER the ring dropped events
        got.append(e)
        if e["type"] == "done":
            break
    assert got[-1]["type"] == "done"                    # terminal always delivered
    idxs = [e["data"]["i"] for e in got if e["type"] == "source"]
    assert idxs == [4, 5, 6, 7]                         # only the newest survived, in order

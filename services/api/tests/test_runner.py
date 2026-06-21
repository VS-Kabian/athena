import asyncio
import pytest
from athena import runner


@pytest.mark.asyncio
async def test_register_and_autocleanup():
    async def quick():
        return 1
    t = asyncio.create_task(quick())
    runner.register("r1", t)
    assert "r1" in runner._TASKS
    await t
    await asyncio.sleep(0)        # let the done-callback run
    assert "r1" not in runner._TASKS


@pytest.mark.asyncio
async def test_cancel_task():
    async def slow():
        await asyncio.sleep(10)
    t = asyncio.create_task(slow())
    runner.register("r2", t)
    assert runner.cancel_task("r2") is True
    with pytest.raises(asyncio.CancelledError):
        await t
    assert runner.cancel_task("missing") is False


def test_semaphore_is_singleton():
    assert runner.semaphore() is runner.semaphore()

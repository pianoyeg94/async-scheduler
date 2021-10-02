# async-scheduler (work in progress!)

Current capabilities:
1) Scheduling of coroutines can happen only in terms of "run every second, five seconds and so on"


What's lacking for an initial release:
1) Scheduling in terms of datetime objects;
2) Scheduling using cron patterns;
3) Test coverage, comments and documentation.


Example of how the "library" can be used in its current state (main.py):
```python
import asyncio
import signal

from src import PeriodicCoroScheduler

SIGNALS = (signal.SIGTERM, signal.SIGINT)


async def on_shutdown(loop: asyncio.AbstractEventLoop) -> None:
    await scheduler.close()
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    
    loop.stop()


# `discover_modules` parameter is used to find and register coroutines
# from different modules (should be provided as a list of dot-separated
# string paths)
scheduler = PeriodicCoroScheduler(discover_modules=[])


@scheduler.register(run_every=1)
async def coro1() -> None:
    print('Simulating an http request in coro1')
    await asyncio.sleep(1)


@scheduler.register(run_every=3)
async def coro2() -> None:
    print('Simulating a DB query over the network in coro2')
    await asyncio.sleep(1)


def main() -> None:
    loop = asyncio.get_event_loop()
    for s in SIGNALS:
        loop.add_signal_handler(s, lambda: asyncio.create_task(on_shutdown(loop)))
    
    loop.create_task(scheduler.start())
    
    try:
        loop.run_forever()
    finally:
        loop.close()


if __name__ == '__main__':
    main()
```
As a result you should get "Simulating an http request in coro1" printed every second 
and "Simulating a DB query over the network in coro2" every 3 seconds until you hit Ctrl+C.

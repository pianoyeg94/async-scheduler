# async-scheduler (work in progress!)

Current capabilities:
1) Scheduling of coroutines can happen only in terms of "run every second, five seconds and so on"


What's lacking for an initial release:
1) Scheduling in terms of datetime objects;
2) Scheduling using cron patterns;
3) Test coverage, comments and documentation.


Example of how the "library" can be used in its current state:
```
import asyncio


loop = asyncio.get_event_loop()
# `discover_modules` parameter is used to find and register coroutines
# from different modules (should be provided as a list of dot-separated string paths)
scheduler = PeriodicCoroScheduler(discover_modules=[], loop=loop)

@scheduler.register(run_every=1)
async def coro1():
    await asyncio.sleep(0)
    print('From coro1')


@scheduler.register(run_every=3)
async def coro2():
    await asyncio.sleep(0)
    print('From coro2')
    
    
if __name__ == '__main__':
    loop.create_task(scheduler.start())
    loop.run_forever()
```

As a result coro1 will run every second and coro2 every 3 seconds.

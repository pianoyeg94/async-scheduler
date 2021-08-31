import asyncio
import heapq
import importlib
import weakref
from collections.abc import Coroutine
from typing import Any, Callable, Iterable, Optional

Corofunc = Callable[..., Coroutine[Any, Any, Any]]


class SchedulerHandle:

    def __init__(
        self,
        corofunc: Corofunc,
        schedule_every: int,
        loop: asyncio.AbstractEventLoop
    ) -> None:
        self.loop = loop
        self.corofunc = corofunc
        self.schedule_every = schedule_every
        self.next_schedule = 0

    def schedule_coro(self) -> asyncio.Task:
        task = self.loop.create_task(self.corofunc())
        task.add_done_callback(self._done_callback)
        return task

    def _done_callback(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            context = {'message': 'Periodic task processing failed.',
                       'corofunc': self.corofunc,
                       'exception': exc}
            self.loop.call_exception_handler(context)

    def __hash__(self) -> int:
        return hash(self.corofunc)

    def __gt__(self, other: 'SchedulerHandle') -> bool:
        if isinstance(other, SchedulerHandle):
            return self.next_schedule > other.next_schedule
        return NotImplemented

    def __ge__(self, other: 'SchedulerHandle') -> bool:
        if isinstance(other, SchedulerHandle):
            return self.__gt__(other) or self.__eq__(other)
        return NotImplemented

    def __eq__(self, other: 'SchedulerHandle') -> bool:
        if isinstance(other, SchedulerHandle):
            return self.next_schedule == other.next_schedule
        return NotImplemented


class PeriodicCoroScheduler:
  
    def __init__(
        self,
        discover_modules: Iterable[str],
        loop: Optional[asyncio.AbstractEventLoop] = None
    ) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._discover_modules = discover_modules
        self._schedule: list[SchedulerHandle] = []
        self._started = self._loop.create_future()
        self._beat_fut: Optional[asyncio.Future] = None
        self._running_tasks = weakref.WeakSet()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def started(self) -> bool:
        return self._started.done()

    def register(self, run_every: int) -> Callable[[Corofunc], Corofunc]:
        def register_corofunc(corofunc: Corofunc) -> Corofunc:
            if not asyncio.iscoroutinefunction(corofunc):
                raise TypeError(
                    f'Expected a coroutine function, got {type(corofunc)}.'
                )
            if self._closed:
                raise RuntimeError(
                    'Cannot register tasks after scheduler was closed.'
                )
            if self._started.done():
                raise RuntimeError(
                    'Cannot register tasks when scheduler is already running.'
                )

            self._schedule.append(SchedulerHandle(
                corofunc=corofunc,
                schedule_every=run_every,
                loop=self._loop)
            )
            return corofunc

        return register_corofunc

    async def start(self) -> Optional[asyncio.Task]:
        if self._closed:
            raise RuntimeError(
                'Cannot start an already closed scheduler.'
            )
        if self._started.done():
            return

        for module in self._discover_modules:
            importlib.import_module(module)

        heapq.heapify(self._schedule)
        task = self._loop.create_task(self._iterate_schedule())
        task.add_done_callback(self._handle_exception)
        await self._started
        return task

    async def close(self, timeout=None) -> None:
        if not self._started.done():
            raise RuntimeError(
                'Cannot close a scheduler that is not running.'
            )
        if self._closed:
            return

        self._beat_fut, beat_fut = None, self._beat_fut
        if beat_fut is not None:
            beat_fut.cancel()
        for task in self._running_tasks:
            task.cancel()
        gathering_fut = asyncio.gather(
            *[task for task in self._running_tasks],
            return_exceptions=True
        )
        try:
            await asyncio.wait_for(gathering_fut, timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                'Could not close scheduler gracefully within the given timeout.'
            )
        finally:
            self._closed = True

    async def _iterate_schedule(self) -> None:
        self._started.set_result(None)
        if not self._schedule:
            self._closed = True
            return

        while True:
            after = max(self._schedule[0].next_schedule - self._loop.time(), 0)
            fut = self._loop.create_future()
            timer_handle = self._loop.call_later(
                after,
                self._schedule_tasks,
                fut
            )
            self._beat_fut = fut
            try:
                await fut
            except asyncio.CancelledError:
                break
            finally:
                timer_handle.cancel()
                self._beat_fut = None

    def _schedule_tasks(self, fut: asyncio.Future) -> None:
        if fut.cancelled():
            return

        end_time = self._loop.time()
        ready = []
        for handle in self._schedule:
            if handle.next_schedule >= end_time:
                break
            handle.next_schedule = self._loop.time() + handle.schedule_every
            ready.append(handle)

        heapq.heapify(self._schedule)
        for handle in ready:
            self._running_tasks.add(handle.schedule_coro())

        if not fut.cancelled():
            fut.set_result(None)

    def _handle_exception(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except (SystemExit, KeyboardInterrupt):
            self._closed = True
            raise
        except BaseException as exc:
            self._beat_fut, beat_fut = None, self._beat_fut
            if beat_fut is not None:
                beat_fut.cancel()
            for task in self._running_tasks:
                task.cancel()
            self._closed = True
            context = {'message': 'Scheduler closed with exception.',
                       'scheduler': self,
                       'exception': exc}
            self._loop.call_exception_handler(context)
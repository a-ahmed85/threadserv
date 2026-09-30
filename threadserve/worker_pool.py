"""Fixed-size thread pool that owns connections submitted to it.

Design decisions:
- Backpressure: submit() uses queue.put_nowait() and returns False on
  queue.Full rather than blocking. A blocked accept loop can't tell a
  client anything useful while stuck; a bool the caller can act on
  immediately (e.g. write a 503 and close) is strictly more useful.
- Shutdown: queue.Queue is already internally synchronized, so there's no
  extra lock around put()/get(). To stop N worker threads that may all be
  blocked in queue.get(), shutdown() pushes exactly one sentinel (None)
  per worker -- each worker's loop treats None as "exit." Because the
  queue is FIFO, any connections already queued ahead of the sentinels are
  handled to completion first: shutdown drains in-flight work for free,
  with no special-case logic needed for it.
- A handler that raises is caught and swallowed at the worker-loop level:
  one bad connection must never permanently kill a worker thread.
"""

from __future__ import annotations

import queue
import socket
import threading
import time
from typing import Callable

ConnectionHandlerFn = Callable[[socket.socket, tuple[str, int], int], None]

_SHUTDOWN_SENTINEL = None


class WorkerPool:
    def __init__(self, num_workers: int, queue_capacity: int, handler: ConnectionHandlerFn):
        self._num_workers = num_workers
        self._handler = handler
        self._queue: queue.Queue = queue.Queue(maxsize=queue_capacity)
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for worker_id in range(self._num_workers):
            thread = threading.Thread(
                target=self._worker_loop,
                args=(worker_id,),
                name=f"worker-{worker_id}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def submit(self, conn: socket.socket, addr: tuple[str, int]) -> bool:
        try:
            self._queue.put_nowait((conn, addr))
            return True
        except queue.Full:
            return False

    def shutdown(self, drain_timeout: float) -> None:
        for _ in range(self._num_workers):
            self._queue.put(_SHUTDOWN_SENTINEL)

        deadline = time.monotonic() + drain_timeout
        for thread in self._threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)

    def _worker_loop(self, worker_id: int) -> None:
        while True:
            item = self._queue.get()
            if item is _SHUTDOWN_SENTINEL:
                return
            conn, addr = item
            try:
                self._handler(conn, addr, worker_id)
            except Exception:
                pass

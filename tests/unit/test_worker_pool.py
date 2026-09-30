import threading

from threadserve.worker_pool import WorkerPool


def test_submitted_connection_is_handled_by_a_worker():
    handled = []
    done = threading.Event()

    def handler(conn, addr, worker_id):
        handled.append((conn, addr, worker_id))
        done.set()

    pool = WorkerPool(num_workers=2, queue_capacity=4, handler=handler)
    pool.start()
    try:
        assert pool.submit("conn-1", ("127.0.0.1", 5000)) is True
        assert done.wait(timeout=1.0), "handler was not invoked in time"
        assert len(handled) == 1
        conn, addr, worker_id = handled[0]
        assert conn == "conn-1"
        assert addr == ("127.0.0.1", 5000)
        assert worker_id in (0, 1)
    finally:
        pool.shutdown(drain_timeout=1.0)


def test_submit_returns_false_when_queue_is_full():
    release = threading.Event()
    started = threading.Event()

    def blocking_handler(conn, addr, worker_id):
        started.set()
        release.wait(timeout=5.0)

    pool = WorkerPool(num_workers=1, queue_capacity=1, handler=blocking_handler)
    pool.start()
    try:
        assert pool.submit("a", ("x", 1)) is True
        assert started.wait(timeout=1.0), "worker never picked up the first connection"

        # The single worker is now busy with "a". The queue (capacity 1) has
        # room for exactly one more pending connection.
        assert pool.submit("b", ("x", 1)) is True
        # Now the queue is full and the worker is still busy: this must be
        # rejected immediately rather than blocking the caller.
        assert pool.submit("c", ("x", 1)) is False
    finally:
        release.set()
        pool.shutdown(drain_timeout=1.0)


def test_shutdown_drains_in_flight_work_before_stopping_workers():
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()

    def blocking_handler(conn, addr, worker_id):
        started.set()
        release.wait(timeout=5.0)
        finished.set()

    pool = WorkerPool(num_workers=1, queue_capacity=4, handler=blocking_handler)
    pool.start()
    assert pool.submit("a", ("x", 1)) is True
    assert started.wait(timeout=1.0), "worker never picked up the in-flight connection"

    # Let the in-flight handler proceed, then shut down. Because the queue
    # is FIFO, "a" was queued before any shutdown sentinel could be, so the
    # worker is guaranteed to finish handling it before it sees a sentinel
    # and exits -- no sleep-based timing needed to prove this.
    release.set()
    pool.shutdown(drain_timeout=2.0)

    assert finished.is_set()
    for worker_thread in pool._threads:
        assert not worker_thread.is_alive()


def test_worker_survives_a_handler_that_raises():
    calls = []
    done = threading.Event()

    def flaky_handler(conn, addr, worker_id):
        calls.append(conn)
        if conn == "bad":
            raise RuntimeError("boom")
        done.set()

    pool = WorkerPool(num_workers=1, queue_capacity=4, handler=flaky_handler)
    pool.start()
    try:
        assert pool.submit("bad", ("x", 1)) is True
        assert pool.submit("good", ("x", 1)) is True
        assert done.wait(timeout=1.0), "worker thread died after a handler exception"
        assert calls == ["bad", "good"]
    finally:
        pool.shutdown(drain_timeout=1.0)

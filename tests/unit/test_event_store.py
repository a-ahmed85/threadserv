import threading
import time

from threadserve.store.event_store import EventStore
from threadserve.store.models import Event


# --- add() -----------------------------------------------------------

def test_add_returns_populated_event():
    store = EventStore(capacity=10)
    before = time.time()
    event = store.add(type="deploy", severity="info", message="deployed v1", timestamp=None)
    after = time.time()

    assert isinstance(event, Event)
    assert isinstance(event.id, str) and event.id
    assert event.type == "deploy"
    assert event.severity == "info"
    assert event.message == "deployed v1"
    assert isinstance(event.timestamp, float)
    assert isinstance(event.received_at, float)
    assert before <= event.received_at <= after
    # timestamp defaults to the same "now" as received_at when not given
    assert before <= event.timestamp <= after


def test_add_respects_explicit_timestamp():
    store = EventStore(capacity=10)
    explicit_ts = 1_000_000.5
    event = store.add(type="deploy", severity="warning", message="m", timestamp=explicit_ts)

    assert event.timestamp == explicit_ts
    # received_at is still "now", not overwritten by the explicit timestamp
    assert event.received_at != explicit_ts
    assert event.received_at > explicit_ts


# --- list_recent() -----------------------------------------------------

def test_list_recent_is_most_recent_first():
    store = EventStore(capacity=10)
    e1 = store.add(type="a", severity="info", message="first", timestamp=None)
    e2 = store.add(type="a", severity="info", message="second", timestamp=None)
    e3 = store.add(type="a", severity="info", message="third", timestamp=None)

    recent = store.list_recent(limit=10)

    assert [e.id for e in recent] == [e3.id, e2.id, e1.id]


def test_list_recent_respects_limit():
    store = EventStore(capacity=10)
    for i in range(5):
        store.add(type="a", severity="info", message=str(i), timestamp=None)

    recent = store.list_recent(limit=2)

    assert len(recent) == 2
    assert recent[0].message == "4"
    assert recent[1].message == "3"


def test_list_recent_filters_by_severity():
    store = EventStore(capacity=10)
    store.add(type="a", severity="info", message="i1", timestamp=None)
    store.add(type="a", severity="error", message="e1", timestamp=None)
    store.add(type="a", severity="info", message="i2", timestamp=None)
    store.add(type="a", severity="error", message="e2", timestamp=None)

    errors = store.list_recent(limit=10, severity="error")

    assert [e.message for e in errors] == ["e2", "e1"]
    assert all(e.severity == "error" for e in errors)


def test_list_recent_never_exceeds_limit_even_with_filter():
    store = EventStore(capacity=10)
    for i in range(5):
        store.add(type="a", severity="info", message=str(i), timestamp=None)

    recent = store.list_recent(limit=2, severity="info")

    assert len(recent) == 2


def test_list_recent_returns_a_copy_not_a_live_view():
    store = EventStore(capacity=10)
    store.add(type="a", severity="info", message="one", timestamp=None)

    snapshot = store.list_recent(limit=10)
    store.add(type="a", severity="info", message="two", timestamp=None)

    assert len(snapshot) == 1


# --- count() -------------------------------------------------------------

def test_count_reflects_number_of_events_added():
    store = EventStore(capacity=100)
    assert store.count() == 0

    for i in range(7):
        store.add(type="a", severity="info", message=str(i), timestamp=None)

    assert store.count() == 7


def test_count_is_capped_at_capacity():
    capacity = 5
    store = EventStore(capacity=capacity)

    for i in range(capacity * 3):
        store.add(type="a", severity="info", message=str(i), timestamp=None)
        assert store.count() <= capacity

    assert store.count() == capacity


# --- counts_by_severity() -------------------------------------------------

def test_counts_by_severity_after_mixed_adds():
    store = EventStore(capacity=100)
    store.add(type="a", severity="info", message="1", timestamp=None)
    store.add(type="a", severity="info", message="2", timestamp=None)
    store.add(type="a", severity="warning", message="3", timestamp=None)
    store.add(type="a", severity="error", message="4", timestamp=None)
    store.add(type="a", severity="critical", message="5", timestamp=None)
    store.add(type="a", severity="info", message="6", timestamp=None)

    counts = store.counts_by_severity()

    assert counts["info"] == 3
    assert counts["warning"] == 1
    assert counts["error"] == 1
    assert counts["critical"] == 1


def test_counts_by_severity_correct_after_eviction():
    capacity = 10
    store = EventStore(capacity=capacity)

    for i in range(capacity):
        store.add(type="a", severity="info", message=f"info-{i}", timestamp=None)

    counts_before = store.counts_by_severity()
    assert counts_before["info"] == capacity
    assert store.count() == capacity

    # this push evicts the oldest "info" event
    store.add(type="a", severity="error", message="err", timestamp=None)

    counts_after = store.counts_by_severity()
    assert store.count() == capacity
    assert counts_after["info"] == capacity - 1
    assert counts_after.get("error", 0) == 1


# --- concurrency -----------------------------------------------------------

def test_concurrent_adds_do_not_lose_updates():
    num_threads = 20
    adds_per_thread = 100
    store = EventStore(capacity=num_threads * adds_per_thread * 2)  # large enough: nothing evicts

    def worker():
        for i in range(adds_per_thread):
            store.add(type="a", severity="info", message=str(i), timestamp=None)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert store.count() == num_threads * adds_per_thread
    assert store.counts_by_severity()["info"] == num_threads * adds_per_thread

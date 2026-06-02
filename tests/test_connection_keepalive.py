from __future__ import annotations
 
import os
import sys
import threading
import time
from unittest.mock import MagicMock
 
import pytest
 
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
 
from database.connection import ConnectionKeepAlive, HEARTBEAT_QUERY
 
 
def _make_connection() -> MagicMock:
    """A fake DB-API connection whose cursor records executed queries."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn
 
 
def test_ping_executes_heartbeat_query():
    conn = _make_connection()
    keepalive = ConnectionKeepAlive(conn, interval=30.0)
 
    assert keepalive.ping() is True
    conn.cursor.assert_called_once()
    conn.cursor.return_value.execute.assert_called_once_with(HEARTBEAT_QUERY)
 
 
def test_ping_returns_false_on_failure_and_does_not_raise():
    conn = _make_connection()
    conn.cursor.return_value.execute.side_effect = RuntimeError("connection reset")
    keepalive = ConnectionKeepAlive(conn, interval=30.0)
 
    # A failed ping must be swallowed so the loop survives a transient drop.
    assert keepalive.ping() is False
 
 
def test_start_launches_background_thread_and_stop_joins_it():
    conn = _make_connection()
    keepalive = ConnectionKeepAlive(conn, interval=30.0)
 
    assert keepalive.is_running is False
    keepalive.start()
    assert keepalive.is_running is True
 
    keepalive.stop()
    assert keepalive.is_running is False
 
 
def test_background_loop_pings_on_interval():
    # Use a tiny interval so the loop ticks during the test, and an Event to
    # detect the first ping deterministically rather than sleeping blindly.
    conn = _make_connection()
    pinged = threading.Event()
    conn.cursor.return_value.execute.side_effect = lambda *_a, **_k: pinged.set()
 
    keepalive = ConnectionKeepAlive(conn, interval=0.05)
    keepalive.start()
    try:
        assert pinged.wait(timeout=2.0), "expected at least one ping within 2s"
    finally:
        keepalive.stop()
 
    conn.cursor.return_value.execute.assert_called_with(HEARTBEAT_QUERY)
 
 
def test_stop_is_prompt_and_does_not_wait_full_interval():
    # Large interval; stop() must return quickly via the stop Event, not block
    # for the whole interval.
    conn = _make_connection()
    keepalive = ConnectionKeepAlive(conn, interval=60.0)
    keepalive.start()
 
    start = time.monotonic()
    keepalive.stop()
    elapsed = time.monotonic() - start
 
    assert elapsed < 5.0
    assert keepalive.is_running is False
 
 
def test_double_start_is_noop():
    conn = _make_connection()
    keepalive = ConnectionKeepAlive(conn, interval=60.0)
    keepalive.start()
    first_thread = keepalive._thread
    keepalive.start()  # should be ignored, not spawn a second thread
    assert keepalive._thread is first_thread
    keepalive.stop()
 
 
def test_invalid_arguments_rejected():
    with pytest.raises(ValueError):
        ConnectionKeepAlive(None, interval=30.0)
    with pytest.raises(ValueError):
        ConnectionKeepAlive(_make_connection(), interval=0)
    with pytest.raises(ValueError):
        ConnectionKeepAlive(_make_connection(), interval=-5)
 
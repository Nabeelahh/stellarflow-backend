from __future__ import annotations

from analytics.window import SlidingWindowBuffer


def test_sliding_window_buffer_retains_most_recent_entries() -> None:
    buffer = SlidingWindowBuffer[int]()
    buffer.extend(range(120))

    assert len(buffer) == 100
    assert buffer.to_list() == list(range(20, 120))


def test_sliding_window_buffer_appends_and_discards_oldest() -> None:
    buffer = SlidingWindowBuffer[int]()
    for i in range(100):
        buffer.append(i)

    assert len(buffer) == 100
    assert buffer.to_list()[0] == 0

    buffer.append(100)
    assert len(buffer) == 100
    assert buffer.to_list()[0] == 1
    assert buffer.to_list()[-1] == 100

"""stream_buffer.py — zero-copy JSON stream parser using memoryview.

Accepts raw network binary blocks and locates newline-delimited JSON frames
without allocating intermediate string objects, reducing GC pressure during
high-volume market-volatility spikes.
"""
from __future__ import annotations

import json
from typing import Any, Generator

_NEWLINE = ord("\n")


class StreamBuffer:
    """Accumulate binary chunks and yield parsed JSON objects zero-copy."""

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes | bytearray | memoryview) -> Generator[Any, None, None]:
        """Append *data* and yield every complete newline-delimited JSON frame.

        A memoryview over the internal bytearray is used during the scan phase
        to slice frame boundaries without intermediate string copies.  The view
        is released before the buffer is trimmed so the bytearray can resize.
        """
        self._buf += data  # single extend, no str conversion

        frames: list[bytes] = []
        start = 0

        view = memoryview(self._buf)
        for i in range(len(view)):
            if view[i] == _NEWLINE:
                if i > start:
                    frames.append(bytes(view[start:i]))
                start = i + 1
        consumed = start
        view.release()  # release before resizing

        del self._buf[:consumed]  # keep only the incomplete trailing fragment

        for frame in frames:
            yield json.loads(frame)

    def reset(self) -> None:
        """Discard all buffered data."""
        self._buf.clear()


__all__ = ["StreamBuffer"]

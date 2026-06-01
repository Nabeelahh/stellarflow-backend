from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


class TransientRateStore:
    """Async-safe shared rate map with lock isolation for write cycles.

    Write operations acquire an asyncio.Lock to prevent race conditions and
    memory mutation overwrites. Read operations are non-blocking.
    """

    def __init__(self) -> None:
        self._rates: Dict[str, Any] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def set(self, key: str, value: Any) -> None:
        """Safely write a rate value under the async lock."""
        async with self._lock:
            self._rates[key] = value

    async def update(self, updates: Dict[str, Any]) -> None:
        """Safely apply a batch of rate updates under the async lock."""
        async with self._lock:
            self._rates.update(updates)

    def get(self, key: str) -> Optional[Any]:
        """Non-blocking read — safe to call without acquiring the lock."""
        return self._rates.get(key)

    def snapshot(self) -> Dict[str, Any]:
        """Return a shallow copy of the current rate map without blocking."""
        return dict(self._rates)

    async def delete(self, key: str) -> None:
        """Remove a key under the async lock."""
        async with self._lock:
            self._rates.pop(key, None)


# Module-level singleton for shared use across feed workers.
transient_store = TransientRateStore()

__all__ = ["TransientRateStore", "transient_store"]
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS: int = 5000
POLL_INTERVAL_S: float = POLL_INTERVAL_MS / 1000


async def _fetch_endpoint(
    session: aiohttp.ClientSession, url: str
) -> Optional[Dict[str, Any]]:
    """Fetch a single backup exchange endpoint and return parsed JSON."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning("REST fallback: %s returned HTTP %d", url, resp.status)
    except Exception as exc:
        logger.error("REST fallback fetch error for %s: %s", url, exc)
    return None


async def poll_rest_fallbacks(
    endpoints: List[str],
    on_data: Any,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Poll backup exchange endpoints concurrently at a fixed 5000ms interval.

    Parameters
    ----------
    endpoints:  List of backup REST URLs to query each cycle.
    on_data:    Async callable invoked with (url, payload) for each success.
    stop_event: Optional asyncio.Event; polling stops when it is set.
    """
    if stop_event is None:
        stop_event = asyncio.Event()

    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            tasks = [_fetch_endpoint(session, url) for url in endpoints]
            results = await asyncio.gather(*tasks)
            for url, payload in zip(endpoints, results):
                if payload is not None:
                    await on_data(url, payload)
            await asyncio.sleep(POLL_INTERVAL_S)


__all__ = ["poll_rest_fallbacks", "POLL_INTERVAL_MS"]
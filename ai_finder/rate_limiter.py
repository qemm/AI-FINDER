"""
rate_limiter.py — Per-engine rate limiting, User-Agent rotation, and backoff.

Provides a central :class:`RateLimiter` that:

* Enforces per-engine randomised delays between consecutive requests via an
  ``asyncio.Lock`` (so concurrent callers for the same engine are serialised).
* Rotates request ``User-Agent`` headers from a realistic browser pool to
  reduce fingerprinting by search engines and VCS APIs.
* Exposes a fixed-pause retry helper for 429 / CAPTCHA responses.

Typical usage
-------------
    from ai_finder.rate_limiter import RateLimiter

    rl = RateLimiter()

    # Before each search-engine request:
    await rl.acquire("google")
    headers = rl.get_headers(base_headers)
    async with session.get(url, params=params, headers=headers) as resp:
        ...

    # When a 429 is returned, sleep the engine-specific backoff duration:
    await asyncio.sleep(rl.get_backoff_pause("google"))
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Optional, TypeVar

# ---------------------------------------------------------------------------
# User-Agent pool
# ---------------------------------------------------------------------------

#: Realistic browser User-Agent strings rotated to reduce bot fingerprinting.
USER_AGENT_POOL: tuple[str, ...] = (
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RateLimiterConfig:
    """Delay and backoff parameters for a single engine or API endpoint.

SADRFWSDF    Parameters
    ----------
    min_delay:
        Minimum number of seconds to wait before sending a request.
    max_delay:
        Maximum number of seconds to wait before sending a request.
        The actual delay is sampled uniformly from ``[min_delay, max_delay]``
        to add jitter and reduce predictable timing patterns.
    backoff_pause:
        Fixed number of seconds to sleep when a 429 or CAPTCHA response is
        received before retrying the request once.
    max_retries:
        Number of retry attempts allowed after a rate-limit response.
        Currently only ``1`` retry is supported by :meth:`RateLimiter.execute_with_retry`.
    """

    min_delay: float
    max_delay: float
    backoff_pause: float
    max_retries: int = 1


#: Default per-engine rate limiting configuration.
DEFAULT_CONFIGS: dict[str, RateLimiterConfig] = {
    "duckduckgo": RateLimiterConfig(min_delay=3.0,  max_delay=7.0,   backoff_pause=45.0),
    "google":     RateLimiterConfig(min_delay=10.0, max_delay=20.0,  backoff_pause=120.0),
    "bing":       RateLimiterConfig(min_delay=4.0,  max_delay=9.0,   backoff_pause=60.0),
    "yandex":     RateLimiterConfig(min_delay=5.0,  max_delay=12.0,  backoff_pause=90.0),
    # Official JSON APIs — light delay only, no scraping = no CAPTCHA.
    # backoff_pause for google_cse is 2 h because 429 = daily quota exhausted.
    "google_cse": RateLimiterConfig(min_delay=1.0,  max_delay=2.0,   backoff_pause=7200.0),
    "brave":      RateLimiterConfig(min_delay=1.0,  max_delay=2.0,   backoff_pause=60.0),
    "github":     RateLimiterConfig(min_delay=2.0,  max_delay=4.0,   backoff_pause=60.0),
    "gitlab":     RateLimiterConfig(min_delay=1.0,  max_delay=3.0,   backoff_pause=30.0),
    "default":    RateLimiterConfig(min_delay=1.0,  max_delay=3.0,   backoff_pause=30.0),
}

# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

_T = TypeVar("_T")


class RateLimiter:
    """Central rate limiting controller for search engine and API requests.

    Manages per-engine jittered delays, User-Agent rotation, and fixed-pause
    retry on rate-limit responses (HTTP 429).

    Parameters
    ----------
    configs:
        Mapping of engine names to :class:`RateLimiterConfig` instances.
        Any engine not present in the dict falls back to the ``"default"``
        entry.  When ``None`` the module-level :data:`DEFAULT_CONFIGS` are
        used.
    """

    def __init__(
        self,
        configs: Optional[dict[str, RateLimiterConfig]] = None,
    ) -> None:
        self._configs: dict[str, RateLimiterConfig] = (
            configs if configs is not None else DEFAULT_CONFIGS
        )
        # Per-engine asyncio.Lock — created lazily to avoid requiring a
        # running event loop at construction time.
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self, engine: str) -> RateLimiterConfig:
        """Return the :class:`RateLimiterConfig` for *engine*.

        Falls back to ``"default"`` when the engine name is not explicitly
        configured.
        """
        return self._configs.get(engine) or self._configs.get(
            "default", RateLimiterConfig(1.0, 3.0, 30.0)
        )

    def _get_lock(self, engine: str) -> asyncio.Lock:
        """Return (creating if necessary) the asyncio.Lock for *engine*."""
        if engine not in self._locks:
            self._locks[engine] = asyncio.Lock()
        return self._locks[engine]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(self, engine: str) -> None:
        """Acquire a time slot for *engine*, sleeping to respect rate limits.

        Concurrent callers for the **same engine** are serialised through a
        per-engine ``asyncio.Lock`` so that only one coroutine sleeps and
        then proceeds at a time.  This prevents a burst of coroutines from
        all sleeping concurrently and then hitting the engine simultaneously.

        The sleep duration is sampled uniformly from
        ``[min_delay, max_delay]`` (both inclusive) to add timing jitter.

        Parameters
        ----------
        engine:
            Logical engine name matching a key in the ``configs`` dict
            (e.g. ``"google"``, ``"github"``).  Unknown names fall back to
            the ``"default"`` config.
        """
        cfg = self._get_config(engine)
        async with self._get_lock(engine):
            delay = random.uniform(cfg.min_delay, cfg.max_delay)
            await asyncio.sleep(delay)

    def get_headers(self, base_headers: dict[str, str]) -> dict[str, str]:
        """Return a copy of *base_headers* with a randomly rotated User-Agent.

        All other headers including ``Authorization``, ``Accept``, and
        ``PRIVATE-TOKEN`` are preserved unchanged.

        Parameters
        ----------
        base_headers:
            The headers dict to copy and patch.

        Returns
        -------
        dict[str, str]
            New dict with ``User-Agent`` replaced by a random entry from
            :data:`USER_AGENT_POOL`.
        """
        headers = dict(base_headers)
        headers["User-Agent"] = random.choice(USER_AGENT_POOL)
        return headers

    def get_backoff_pause(self, engine: str) -> float:
        """Return the configured backoff pause duration (in seconds) for *engine*.

        Parameters
        ----------
        engine:
            Logical engine name.  Unknown names fall back to ``"default"``.

        Returns
        -------
        float
            Number of seconds to sleep before retrying after a rate-limit
            response.
        """
        return self._get_config(engine).backoff_pause

    async def execute_with_retry(
        self,
        engine: str,
        coro_factory: Callable[[], Awaitable[_T]],
        is_rate_limited: Callable[[_T], bool],
    ) -> _T:
        """Execute *coro_factory()* with a single fixed-pause retry on rate-limit.

        Parameters
        ----------
        engine:
            Engine name used to look up the ``backoff_pause`` duration.
        coro_factory:
            Zero-argument callable that returns a new awaitable each time it
            is called.  Invoked once initially, and once more on retry.
        is_rate_limited:
            Predicate applied to the result.  When it returns ``True`` the
            method sleeps :meth:`get_backoff_pause` seconds then retries
            *once*.

        Returns
        -------
        _T
            The result of the last ``coro_factory()`` invocation.
        """
        result = await coro_factory()
        if is_rate_limited(result):
            pause = self.get_backoff_pause(engine)
            await asyncio.sleep(pause)
            result = await coro_factory()
        return result

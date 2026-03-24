"""
tests/test_rate_limiter.py — Unit tests for ai_finder.rate_limiter.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ai_finder.rate_limiter import (
    DEFAULT_CONFIGS,
    USER_AGENT_POOL,
    RateLimiter,
    RateLimiterConfig,
)


# ---------------------------------------------------------------------------
# RateLimiterConfig
# ---------------------------------------------------------------------------


def test_config_fields():
    cfg = RateLimiterConfig(min_delay=1.0, max_delay=3.0, backoff_pause=30.0)
    assert cfg.min_delay == 1.0
    assert cfg.max_delay == 3.0
    assert cfg.backoff_pause == 30.0
    assert cfg.max_retries == 1


# ---------------------------------------------------------------------------
# DEFAULT_CONFIGS
# ---------------------------------------------------------------------------


def test_default_configs_contains_all_engines():
    for engine in ("duckduckgo", "google", "bing", "yandex", "github", "gitlab", "default"):
        assert engine in DEFAULT_CONFIGS, f"Missing config for {engine!r}"


def test_default_configs_delay_ordering():
    # Stricter engines (google, yandex) should have higher min delays than gitlab
    assert DEFAULT_CONFIGS["google"].min_delay > DEFAULT_CONFIGS["gitlab"].min_delay
    assert DEFAULT_CONFIGS["yandex"].min_delay > DEFAULT_CONFIGS["gitlab"].min_delay


# ---------------------------------------------------------------------------
# USER_AGENT_POOL
# ---------------------------------------------------------------------------


def test_user_agent_pool_is_non_empty():
    assert len(USER_AGENT_POOL) >= 5


def test_user_agent_pool_entries_look_like_browsers():
    for ua in USER_AGENT_POOL:
        assert "Mozilla" in ua


# ---------------------------------------------------------------------------
# RateLimiter.get_headers
# ---------------------------------------------------------------------------


def test_get_headers_rotates_user_agent():
    rl = RateLimiter()
    base = {"User-Agent": "old-ua", "Accept": "text/html", "Authorization": "token abc"}
    result = rl.get_headers(base)

    assert result["User-Agent"] in USER_AGENT_POOL
    assert result["Accept"] == "text/html"
    assert result["Authorization"] == "token abc"
    assert base["User-Agent"] == "old-ua"  # original unchanged


def test_get_headers_preserves_extra_keys():
    rl = RateLimiter()
    base = {"User-Agent": "x", "PRIVATE-TOKEN": "my-token", "X-Custom": "val"}
    result = rl.get_headers(base)
    assert result["PRIVATE-TOKEN"] == "my-token"
    assert result["X-Custom"] == "val"


def test_get_headers_ua_varies_over_calls():
    rl = RateLimiter()
    base = {"User-Agent": "x"}
    uas = {rl.get_headers(base)["User-Agent"] for _ in range(50)}
    # With 10 UAs and 50 draws we expect at least 2 distinct values
    assert len(uas) >= 2


# ---------------------------------------------------------------------------
# RateLimiter.get_backoff_pause
# ---------------------------------------------------------------------------


def test_get_backoff_pause_known_engine():
    rl = RateLimiter()
    assert rl.get_backoff_pause("google") == DEFAULT_CONFIGS["google"].backoff_pause


def test_get_backoff_pause_unknown_engine_falls_back_to_default():
    rl = RateLimiter()
    assert rl.get_backoff_pause("unknown-engine") == DEFAULT_CONFIGS["default"].backoff_pause


# ---------------------------------------------------------------------------
# RateLimiter.acquire — delay range respected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_calls_sleep_within_range():
    rl = RateLimiter()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("ai_finder.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        await rl.acquire("google")

    assert len(sleep_calls) == 1
    cfg = DEFAULT_CONFIGS["google"]
    assert cfg.min_delay <= sleep_calls[0] <= cfg.max_delay


@pytest.mark.asyncio
async def test_acquire_unknown_engine_uses_default_range():
    rl = RateLimiter()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("ai_finder.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        await rl.acquire("nonexistent")

    cfg = DEFAULT_CONFIGS["default"]
    assert cfg.min_delay <= sleep_calls[0] <= cfg.max_delay


@pytest.mark.asyncio
async def test_acquire_serialises_concurrent_requests():
    """Concurrent acquire() calls for the same engine run serially, not in parallel."""
    rl = RateLimiter()
    acquired: list[int] = []
    real_sleep = asyncio.sleep  # keep reference before patching

    async def fake_sleep(seconds: float) -> None:
        await real_sleep(0)  # yield without going through the mock

    async def worker(idx: int) -> None:
        with patch("ai_finder.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
            await rl.acquire("github")
        acquired.append(idx)

    await asyncio.gather(worker(0), worker(1), worker(2))
    # All workers must eventually acquire
    assert sorted(acquired) == [0, 1, 2]


# ---------------------------------------------------------------------------
# RateLimiter.execute_with_retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_with_retry_no_rate_limit():
    rl = RateLimiter()
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return "ok"

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("ai_finder.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        result = await rl.execute_with_retry("github", factory, lambda r: r == "rate_limited")

    assert result == "ok"
    assert call_count == 1
    assert sleep_calls == []  # no backoff triggered


@pytest.mark.asyncio
async def test_execute_with_retry_retries_once_on_rate_limit():
    rl = RateLimiter()
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "rate_limited"
        return "ok"

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("ai_finder.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        result = await rl.execute_with_retry("github", factory, lambda r: r == "rate_limited")

    assert result == "ok"
    assert call_count == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == DEFAULT_CONFIGS["github"].backoff_pause


@pytest.mark.asyncio
async def test_execute_with_retry_does_not_retry_twice():
    """If the retry also hits a rate-limit, the second result is returned as-is."""
    rl = RateLimiter()
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return "rate_limited"

    async def fake_sleep(_: float) -> None:
        pass

    with patch("ai_finder.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        result = await rl.execute_with_retry("bing", factory, lambda r: r == "rate_limited")

    # Still returns the last result; only one retry is performed
    assert result == "rate_limited"
    assert call_count == 2

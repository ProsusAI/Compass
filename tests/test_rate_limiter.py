"""Tests for the token-bucket rate limiter."""

import asyncio
import time
import unittest.mock

from odysseus.eval.rate_limiter import TokenBucketRateLimiter


async def test_acquire_basic():
    """Basic acquire should succeed immediately when capacity is available."""
    limiter = TokenBucketRateLimiter(requests_per_minute=60, tokens_per_minute=10_000)
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1  # Should be near-instant


async def test_acquire_respects_request_limit():
    """After exhausting request capacity, acquire should block."""
    # Use 120 rpm = 2/sec, so refilling 1 slot takes ~0.5s
    limiter = TokenBucketRateLimiter(requests_per_minute=120, tokens_per_minute=100_000)
    # Exhaust all 120 request slots
    for _ in range(120):
        await limiter.acquire()
    # Next should block until refill
    start = time.monotonic()
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    elapsed = time.monotonic() - start
    assert elapsed > 0.3  # Had to wait for refill


async def test_consume_tokens_drives_negative():
    """Consuming more tokens than available should make subsequent acquire wait."""
    # 6000 tpm = 100/sec. Consuming 200 extra → needs 2s to refill
    limiter = TokenBucketRateLimiter(requests_per_minute=6000, tokens_per_minute=6000)
    await limiter.acquire()
    limiter.consume_tokens(6200)  # Drive token balance negative by 200
    start = time.monotonic()
    await asyncio.wait_for(limiter.acquire(), timeout=5.0)
    elapsed = time.monotonic() - start
    assert elapsed > 0.5  # Had to wait for token refill


async def test_concurrent_acquire():
    """Multiple concurrent acquires should be serialized by capacity."""
    limiter = TokenBucketRateLimiter(requests_per_minute=300, tokens_per_minute=100_000)
    results: list[float] = []

    async def worker():
        await limiter.acquire()
        results.append(time.monotonic())

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    await asyncio.gather(*tasks)
    assert len(results) == 5  # All completed (initial balance = 300)


async def test_acquire_with_fake_clock():
    """Fake clock controls refill: time must advance for exhausted bucket to refill."""
    current_time = 0.0

    def fake_time() -> float:
        nonlocal current_time
        return current_time

    limiter = TokenBucketRateLimiter(
        requests_per_minute=2,
        tokens_per_minute=100_000,
        time_fn=fake_time,
    )
    # Exhaust both request slots
    await limiter.acquire()
    await limiter.acquire()

    # Without advancing time, acquire must block (sleep is called)
    sleep_called = False

    async def record_and_advance(duration):
        nonlocal sleep_called, current_time
        sleep_called = True
        current_time += duration  # Simulate time passing during sleep

    with unittest.mock.patch("asyncio.sleep", side_effect=record_and_advance):
        await limiter.acquire()

    assert sleep_called, "Rate limiter must sleep when request bucket is empty"
    # Confirm fake clock was used (last_refill reflects fake time, not wall clock)
    assert limiter._last_refill > 0.0  # noqa: SLF001

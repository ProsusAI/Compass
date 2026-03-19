"""Tests for the token-bucket rate limiter."""

import asyncio
import time

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
    limiter = TokenBucketRateLimiter(requests_per_minute=2, tokens_per_minute=100_000)
    # Exhaust request capacity
    await limiter.acquire()
    await limiter.acquire()
    # Third should block
    start = time.monotonic()
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    elapsed = time.monotonic() - start
    assert elapsed > 0.3  # Had to wait for refill


async def test_consume_tokens_drives_negative():
    """Consuming more tokens than available should make subsequent acquire wait."""
    limiter = TokenBucketRateLimiter(requests_per_minute=100, tokens_per_minute=100)
    await limiter.acquire()
    limiter.consume_tokens(200)  # Drive token balance negative
    start = time.monotonic()
    await asyncio.wait_for(limiter.acquire(), timeout=3.0)
    elapsed = time.monotonic() - start
    assert elapsed > 0.3  # Had to wait for token refill


async def test_concurrent_acquire():
    """Multiple concurrent acquires should be serialized by capacity."""
    limiter = TokenBucketRateLimiter(requests_per_minute=5, tokens_per_minute=100_000)
    results: list[float] = []

    async def worker():
        await limiter.acquire()
        results.append(time.monotonic())

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    await asyncio.gather(*tasks)
    assert len(results) == 5  # All completed

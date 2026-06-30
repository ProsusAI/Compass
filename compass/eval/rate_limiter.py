# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Token-bucket rate limiter with request and token budgets."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class TokenBucketRateLimiter:
    """Dual-bucket rate limiter: requests/min and tokens/min.

    - acquire() blocks until both a request slot and positive token balance are available.
    - consume_tokens() deducts tokens after a call completes (non-blocking).
    """

    def __init__(
        self,
        requests_per_minute: int,
        tokens_per_minute: int,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._rpm = requests_per_minute
        self._tpm = tokens_per_minute

        self._request_balance: float = float(requests_per_minute)
        self._token_balance: float = float(tokens_per_minute)

        self._time_fn = time_fn or time.monotonic
        self._last_refill = self._time_fn()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill both buckets based on elapsed time."""
        now = self._time_fn()
        elapsed = now - self._last_refill
        self._last_refill = now

        self._request_balance = min(
            float(self._rpm),
            self._request_balance + elapsed * self._rpm / 60.0,
        )
        self._token_balance = min(
            float(self._tpm),
            self._token_balance + elapsed * self._tpm / 60.0,
        )

    async def acquire(self) -> None:
        """Wait until both a request slot and positive token balance are available."""
        while True:
            async with self._lock:
                self._refill()
                if self._request_balance >= 1.0 and self._token_balance > 0:
                    self._request_balance -= 1.0
                    return

                # Calculate wait time for whichever bucket is limiting
                wait_request = (1.0 - self._request_balance) / (self._rpm / 60.0) if self._request_balance < 1.0 else 0
                wait_tokens = (-self._token_balance) / (self._tpm / 60.0) if self._token_balance <= 0 else 0
                wait = max(wait_request, wait_tokens, 0.01)

            await asyncio.sleep(wait)

    def consume_tokens(self, tokens: int) -> None:
        """Deduct tokens after a call completes. May drive balance negative.

        Thread-safety note: this method is intentionally lock-free. Under asyncio's
        cooperative multitasking model, only one coroutine executes at a time between
        await points. Since this method is synchronous (no await), it runs atomically
        with respect to other coroutines — no concurrent mutation of _token_balance is
        possible. The GIL provides the same guarantee for threaded callers, though this
        class is designed for single-threaded asyncio use only.
        """
        self._token_balance -= tokens

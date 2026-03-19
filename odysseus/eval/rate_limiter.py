"""Token-bucket rate limiter with request and token budgets."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Dual-bucket rate limiter: requests/min and tokens/min.

    - acquire() blocks until both a request slot and positive token balance are available.
    - consume_tokens() deducts tokens after a call completes (non-blocking).
    """

    def __init__(self, requests_per_minute: int, tokens_per_minute: int) -> None:
        self._rpm = requests_per_minute
        self._tpm = tokens_per_minute

        self._request_balance: float = float(requests_per_minute)
        self._token_balance: float = float(tokens_per_minute)

        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill both buckets based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        self._request_balance = min(
            float(self._rpm),
            self._request_balance + elapsed * self._rpm,
        )
        self._token_balance = min(
            float(self._tpm),
            self._token_balance + elapsed * self._tpm,
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
                wait_request = (1.0 - self._request_balance) / float(self._rpm) if self._request_balance < 1.0 else 0
                wait_tokens = (-self._token_balance) / float(self._tpm) if self._token_balance <= 0 else 0
                wait = max(wait_request, wait_tokens, 0.01)

            await asyncio.sleep(wait)

    def consume_tokens(self, tokens: int) -> None:
        """Deduct tokens after a call completes. May drive balance negative."""
        self._token_balance -= tokens

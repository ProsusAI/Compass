# THP-89 — Design and Implement Concurrency Engine

**Type:** Task  
**Status:** To Do  
**Epic:** [THP-75](https://prosus-thymo-thesis.atlassian.net/browse/THP-75) — Eval framework Code  
**Jira:** [THP-89](https://prosus-thymo-thesis.atlassian.net/browse/THP-89)

## Description

Develop the concurrency engine using asyncio and aiohttp, including per-backend concurrency limits, token bucket rate limiting, and a retry layer with exponential backoff for failed requests.

## What to build

The concurrency layer already has a solid foundation. `odysseus/eval/rate_limiter.py` contains `TokenBucketRateLimiter` (dual-bucket: requests/min + tokens/min), and `odysseus/eval/controller.py` contains `_eval_with_retry()`. This task should harden and complete those components:

### `odysseus/eval/rate_limiter.py` — harden `TokenBucketRateLimiter`

The class is implemented. Review and verify:

- **Thread/task safety** — the `asyncio.Lock` in `acquire()` prevents races between concurrent coroutines. Confirm `consume_tokens()` (synchronous, no lock) cannot race with `_refill()` in a meaningful way given Python's GIL and the async event loop model.
- **Precision** — ensure that the wait calculation accounts for both buckets simultaneously and wakes as soon as *both* constraints are satisfied.
- **Testability** — consider accepting a `time_fn` parameter to allow injection of a fake clock in tests.

### `odysseus/eval/controller.py` — harden `_eval_with_retry()`

The private function is implemented. Review and verify:

- **Semaphore ordering** — `acquire()` (rate limiter) must be called *before* entering the semaphore to prevent a deadlock where all semaphore slots are held by coroutines blocked on rate limiting.
- **Backoff correctness** — exponential backoff sleeps *outside* the semaphore, freeing the slot during the wait.
- **Timeout scope** — `asyncio.wait_for` wraps only `backend.call()`, not the rate limiter or semaphore wait.
- **Token deduction** — `consume_tokens()` is called post-call because the exact token count is unknown beforehand; a negative balance is allowed and will cause subsequent `acquire()` calls to wait for refill.

### Optional: extract into a dedicated module

If the retry/rate-limit logic grows, consider extracting `_eval_with_retry` into `odysseus/eval/concurrency.py` and importing it from the controller.

## How it links with the rest of the codebase

| Touch point | Detail |
|---|---|
| `odysseus/eval/rate_limiter.py` | `TokenBucketRateLimiter` — the concurrency engine's core primitive. |
| `odysseus/eval/controller.py` | `_eval_with_retry()` owns the semaphore + rate limiter + retry logic. `run()` creates both the limiter and semaphore from `ConcurrencyConfig` and `RetryConfig`. |
| `odysseus/eval/models.py` | `ConcurrencyConfig` (max_concurrent_requests, requests_per_minute, tokens_per_minute) and `RetryConfig` (max_attempts, backoff_factor, per_call_timeout_seconds) configure this layer. |
| `odysseus/eval/protocols.py` | `Backend.call()` is the async function wrapped by `asyncio.wait_for`. |
| THP-113 (Backend Registry) | Must be complete before real end-to-end concurrency testing — provides a concrete `Backend` implementation. |

## Dependencies between tasks

- **Blocked by THP-113** (Backend Registry) for integration testing with a real `Backend`.
- THP-92 (Run Controller) wires everything together; concurrency parameters come from `RunConfig`.

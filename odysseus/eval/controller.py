"""Run controller — orchestrates a single evaluation run."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from odysseus.eval.models import (
    EvalResult,
    Example,
    RetryConfig,
    RunConfig,
    RunReport,
    RunSummary,
)
from odysseus.eval.pricing import ModelPricing, compute_cost
from odysseus.eval.protocols import RunDependencies
from odysseus.eval.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


async def run(config: RunConfig, deps: RunDependencies) -> RunReport:
    """Execute a full evaluation run.

    1. Load prompt and data
    2. Fan out concurrent evaluations with rate limiting and retry
    3. Compute metrics
    4. Write outputs
    5. Return report
    """
    start_time = datetime.now(UTC)
    logger.info(
        "Starting evaluation run: backend=%s, data=%s, split=%s",
        config.backend,
        config.data_source,
        config.data_split,
    )

    # 1. Load prompt and data
    prompt = deps.prompt_manager.load(config.prompt_version)
    examples = deps.dataset_manager.load(config.data_source, config.data_split)
    logger.info("Loaded %d examples", len(examples))

    # 2. Create parent directories for output
    Path(config.output.results_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.output.report_path).parent.mkdir(parents=True, exist_ok=True)

    # 3. Evaluate
    rate_limiter = TokenBucketRateLimiter(
        requests_per_minute=deps.requests_per_minute,
        tokens_per_minute=deps.tokens_per_minute,
    )
    semaphore = asyncio.Semaphore(config.concurrency.max_concurrent_requests)

    tasks = [
        _eval_with_retry(
            deps.backend, prompt, example, config.retry, rate_limiter, semaphore, deps.backend.pricing
        )
        for example in examples
    ]
    results = await asyncio.gather(*tasks)

    # 4. Compute metrics
    metrics = deps.metrics_engine.compute(list(results), examples, config.metrics)

    # 5. Build report
    end_time = datetime.now(UTC)
    succeeded = sum(1 for r in results if r.error is None)
    failed = len(results) - succeeded
    total_cost = sum(r.cost or 0.0 for r in results)

    summary = RunSummary(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        total_cost=total_cost,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=(end_time - start_time).total_seconds(),
    )

    report = RunReport(
        config=config,
        metrics=metrics,
        results=list(results),
        summary=summary,
    )

    logger.info(
        "Run complete: %d/%d succeeded, cost=$%.4f, duration=%.1fs",
        succeeded,
        len(results),
        total_cost,
        summary.duration_seconds,
    )

    # 6. Write outputs
    deps.results_collector.write_results(list(results), config.output.results_path)
    deps.results_collector.write_report(report, config.output.report_path)

    return report


async def _eval_with_retry(
    backend: Any,
    prompt: str,
    example: Example,
    retry_config: RetryConfig,
    rate_limiter: TokenBucketRateLimiter,
    semaphore: asyncio.Semaphore,
    pricing: ModelPricing | None = None,
) -> EvalResult:
    """Evaluate a single example with retry and rate limiting."""
    model_name: str = backend.model_name
    last_error: str | None = None
    latency_ms: float = 0.0

    for attempt in range(1, retry_config.max_attempts + 1):
        await rate_limiter.acquire()
        async with semaphore:
            start = time.monotonic()
            try:
                output, usage = await asyncio.wait_for(
                    backend.call(prompt, example),
                    timeout=retry_config.per_call_timeout_seconds,
                )
                latency_ms = (time.monotonic() - start) * 1000

                # Post-call token accounting
                total_tokens = usage.input_tokens + usage.cached_tokens + usage.output_tokens
                rate_limiter.consume_tokens(total_tokens)

                cost = compute_cost(pricing, usage)

                logger.debug("Example %s succeeded on attempt %d", example.id, attempt)
                return EvalResult(
                    example_id=example.id,
                    model=model_name,
                    output=output,
                    error=None,
                    latency_ms=latency_ms,
                    retries=attempt - 1,
                    token_usage=usage,
                    cost=cost,
                )

            except Exception as exc:
                latency_ms = (time.monotonic() - start) * 1000
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Example %s failed on attempt %d: %s", example.id, attempt, last_error)

        # Backoff before retry (outside semaphore)
        if attempt < retry_config.max_attempts:
            backoff = retry_config.backoff_factor**attempt
            await asyncio.sleep(backoff)

    # All retries exhausted
    return EvalResult(
        example_id=example.id,
        model=model_name,
        output=None,
        error=last_error,
        latency_ms=latency_ms,
        retries=retry_config.max_attempts - 1,
        token_usage=None,
        cost=None,
    )

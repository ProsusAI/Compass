"""Run controller — orchestrates a single evaluation run."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from compass.eval.models import (
    EvalResult,
    Example,
    RetryConfig,
    RunConfig,
    RunFingerprint,
    RunReport,
    RunSummary,
)
from compass.eval.pricing import ModelPricing, compute_cost
from compass.eval.protocols import RunDependencies
from compass.eval.rate_limiter import TokenBucketRateLimiter

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
        "Starting evaluation run: backend=%s, data=%s",
        config.backend,
        config.data_source,
    )

    # 1. Load prompt and data
    prompt = deps.prompt_manager.load(config.prompt_version)
    examples = deps.dataset_manager.load(config.data_source)
    logger.info("Loaded %d examples", len(examples))

    # 2. Create parent directories for output
    Path(config.output.results_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.output.report_path).parent.mkdir(parents=True, exist_ok=True)

    # 3. Resume: validate fingerprint before reusing cached results
    fingerprint = RunFingerprint.from_config(config)
    stored_fingerprint = deps.results_collector.read_fingerprint(config.output.results_path)

    if stored_fingerprint is not None and stored_fingerprint == fingerprint:
        # Fingerprint matches — safe to resume
        completed_ids = deps.results_collector.read_completed_ids(config.output.results_path)
        if completed_ids:
            logger.info("Resuming: found %d completed examples from previous run", len(completed_ids))
    elif Path(config.output.results_path).exists():
        # Fingerprint missing or mismatched — discard stale results
        if stored_fingerprint is None:
            logger.warning(
                "Discarding results file with no fingerprint (legacy format): %s",
                config.output.results_path,
            )
        else:
            logger.warning("Discarding stale results file (config changed): %s", config.output.results_path)
        completed_ids: set[str] = set()
        deps.results_collector.write_fingerprint(fingerprint, config.output.results_path)
    else:
        # No existing file — write fingerprint to start fresh
        completed_ids = set()
        deps.results_collector.write_fingerprint(fingerprint, config.output.results_path)

    remaining_examples = [ex for ex in examples if ex.id not in completed_ids]

    # 4. Evaluate remaining examples, streaming results to disk
    rate_limiter = (
        deps.rate_limiter
        if deps.rate_limiter is not None
        else TokenBucketRateLimiter(
            requests_per_minute=deps.requests_per_minute,
            tokens_per_minute=deps.tokens_per_minute,
        )
    )
    semaphore = asyncio.Semaphore(config.concurrency.max_concurrent_requests)

    # Map futures back to examples for ordering
    future_to_example: dict[asyncio.Task[EvalResult], Example] = {}
    for example in remaining_examples:
        task = asyncio.create_task(
            _eval_with_retry(deps.backend, prompt, example, config.retry, rate_limiter, semaphore, deps.backend.pricing)
        )
        future_to_example[task] = example

    new_results: list[EvalResult] = []
    for coro in asyncio.as_completed(future_to_example):
        result = await coro
        new_results.append(result)
        deps.results_collector.append_result(result, config.output.results_path)

    # 5. Reconstruct full results list (resumed + new) in original example order
    new_results_by_id = {r.example_id: r for r in new_results}
    resumed_results = _load_resumed_results(config.output.results_path, completed_ids)
    results_by_id = {**{r.example_id: r for r in resumed_results}, **new_results_by_id}
    results = [results_by_id[ex.id] for ex in examples if ex.id in results_by_id]

    # 6. Compute metrics
    metrics = deps.metrics_engine.compute(results, examples, config.metrics)
    confidence_intervals = deps.metrics_engine.compute_cis(results, examples, config.metrics)

    # 7. Build report
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
        confidence_intervals=confidence_intervals if confidence_intervals else None,
    )

    logger.info(
        "Run complete: %d/%d succeeded, cost=$%.4f, duration=%.1fs",
        succeeded,
        len(results),
        total_cost,
        summary.duration_seconds,
    )

    # 8. Write final outputs (overwrites the streaming file with canonical order)
    deps.results_collector.write_results(results, config.output.results_path, fingerprint)
    deps.results_collector.write_report(report, config.output.report_path)

    return report


def _load_resumed_results(results_path: str, completed_ids: set[str]) -> list[EvalResult]:
    """Load EvalResults for previously completed examples from the partial results file."""
    if not completed_ids:
        return []
    results: list[EvalResult] = []
    p = Path(results_path)
    if not p.exists():
        return results
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if record.get("__meta__"):
                continue
            if record.get("example_id") in completed_ids:
                results.append(EvalResult.model_validate(record))
        except (json.JSONDecodeError, Exception):
            continue
    return results


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
                total_tokens = (
                    usage.input_tokens
                    + usage.cached_tokens
                    + usage.cache_write_5m_tokens
                    + usage.cache_write_1h_tokens
                    + usage.output_tokens
                )
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

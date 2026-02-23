"""Periodic metric collector service.

Extends ``AsyncServiceBase`` to run a background collection loop that
reads from existing scattered data sources (PerfTracker, CacheManager,
FrameworkLLMAdapter, ServiceRegistry, psutil) and mirrors their values
into the unified prometheus ``REGISTRY``.

The collector does NOT replace existing data sources. It acts as an
adapter that unifies heterogeneous metrics into the prometheus model
for consistent querying via ``/api/monitoring/metrics``.
"""

import asyncio
from typing import Any, Dict, List, Optional

import psutil
from astrbot.api import logger

from ...core.interfaces import IMetricsProvider, ServiceLifecycle
from ...core.patterns import AsyncServiceBase, ServiceRegistry
from .metrics import (
    ACTIVE_LEARNING_SESSIONS,
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    CACHE_SIZE,
    HOOK_DURATION,
    LLM_ERRORS_TOTAL,
    LLM_REQUEST_DURATION,
    LLM_REQUESTS_TOTAL,
    SERVICE_STATUS,
    SYSTEM_CPU_PERCENT,
    SYSTEM_MEMORY_PERCENT,
    SYSTEM_MEMORY_USED_BYTES,
)

# Mapping from ServiceLifecycle enum to numeric gauge value.
_STATUS_MAP: Dict[str, float] = {
    ServiceLifecycle.RUNNING.value: 1.0,
    ServiceLifecycle.STOPPED.value: 0.0,
    ServiceLifecycle.ERROR.value: -1.0,
    ServiceLifecycle.CREATED.value: 0.0,
    ServiceLifecycle.INITIALIZING.value: 0.5,
    ServiceLifecycle.STOPPING.value: 0.0,
}


class MetricCollector(AsyncServiceBase):
    """Periodically collects metrics from existing subsystems.

    Args:
        interval: Seconds between collection cycles (default 30).
        perf_tracker: Optional ``PerfTracker`` instance.
        cache_manager: Optional ``CacheManager`` instance.
        llm_adapter: Optional ``FrameworkLLMAdapter`` instance.
        service_registry: Optional ``ServiceRegistry`` instance.
        progressive_learning: Optional progressive-learning service
            for active-session counting.
    """

    def __init__(
        self,
        interval: float = 30.0,
        perf_tracker: Optional[Any] = None,
        cache_manager: Optional[Any] = None,
        llm_adapter: Optional[Any] = None,
        service_registry: Optional[ServiceRegistry] = None,
        progressive_learning: Optional[Any] = None,
    ) -> None:
        super().__init__("metric_collector")
        self._interval = interval
        self._perf_tracker = perf_tracker
        self._cache_manager = cache_manager
        self._llm_adapter = llm_adapter
        self._service_registry = service_registry
        self._progressive_learning = progressive_learning
        self._task: Optional[asyncio.Task] = None
        self._extra_providers: Dict[str, IMetricsProvider] = {}

        # Track previous counter values to compute deltas. prometheus
        # Counter is monotonically increasing, so we increment by delta
        # rather than setting an absolute value.
        self._prev_cache_hits: Dict[str, int] = {}
        self._prev_cache_misses: Dict[str, int] = {}
        self._prev_llm_calls: Dict[str, int] = {}
        self._prev_llm_errors: Dict[str, int] = {}

    # -- Lifecycle ----------------------------------------------------------

    async def _do_start(self) -> bool:
        self._task = asyncio.create_task(self._collection_loop())
        logger.info("[MetricCollector] Collection loop started")
        return True

    async def _do_stop(self) -> bool:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[MetricCollector] Collection loop stopped")
        return True

    # -- Public API ---------------------------------------------------------

    def register_source(self, name: str, provider: IMetricsProvider) -> None:
        """Register an additional ``IMetricsProvider`` as a collection source."""
        self._extra_providers[name] = provider

    # -- Collection loop ----------------------------------------------------

    async def _collection_loop(self) -> None:
        """Run periodic collection until cancelled."""
        try:
            while True:
                try:
                    await self._collect_all()
                except Exception as exc:
                    logger.warning(f"[MetricCollector] Collection cycle error: {exc}")
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.debug("[MetricCollector] Collection loop cancelled")

    async def _collect_all(self) -> None:
        """Execute all collection steps."""
        self._collect_system_metrics()
        self._collect_perf_tracker_metrics()
        self._collect_cache_metrics()
        self._collect_llm_metrics()
        self._collect_service_metrics()
        self._collect_learning_sessions()

    # -- Individual collectors ----------------------------------------------

    def _collect_system_metrics(self) -> None:
        """Read system resource usage via psutil."""
        try:
            SYSTEM_CPU_PERCENT.set(psutil.cpu_percent(interval=0))
            mem = psutil.virtual_memory()
            SYSTEM_MEMORY_PERCENT.set(mem.percent)
            SYSTEM_MEMORY_USED_BYTES.set(mem.used)
        except Exception as exc:
            logger.debug(f"[MetricCollector] psutil error: {exc}")

    def _collect_perf_tracker_metrics(self) -> None:
        """Mirror PerfTracker rolling averages into HOOK_DURATION."""
        if not self._perf_tracker:
            return
        try:
            data = self._perf_tracker.get_perf_data(recent_limit=0)
            for key in ("total_ms", "social_ctx_ms", "v2_ctx_ms",
                        "diversity_ms", "jargon_ms", "few_shots_ms"):
                avg_key = f"avg_{key}"
                if avg_key in data:
                    step_name = key.replace("_ms", "")
                    value_sec = data[avg_key] / 1000.0
                    HOOK_DURATION.labels(
                        hook_name="llm_hook", step=step_name,
                    ).observe(value_sec)
        except Exception as exc:
            logger.debug(f"[MetricCollector] PerfTracker error: {exc}")

    def _collect_cache_metrics(self) -> None:
        """Read CacheManager hit/miss stats and sizes."""
        if not self._cache_manager:
            return
        try:
            hit_rates = self._cache_manager.get_hit_rates()
            for cache_name, stats in hit_rates.items():
                hits = stats.get("hits", 0)
                misses = stats.get("misses", 0)

                prev_hits = self._prev_cache_hits.get(cache_name, 0)
                prev_misses = self._prev_cache_misses.get(cache_name, 0)

                delta_hits = max(0, hits - prev_hits)
                delta_misses = max(0, misses - prev_misses)

                if delta_hits > 0:
                    CACHE_HITS_TOTAL.labels(cache_name=cache_name).inc(delta_hits)
                if delta_misses > 0:
                    CACHE_MISSES_TOTAL.labels(cache_name=cache_name).inc(delta_misses)

                self._prev_cache_hits[cache_name] = hits
                self._prev_cache_misses[cache_name] = misses

            # Cache sizes
            for cache_name in ("affection", "memory", "state", "relation",
                               "conversation", "summary", "general"):
                size_info = self._cache_manager.get_stats(cache_name)
                if size_info:
                    CACHE_SIZE.labels(cache_name=cache_name).set(
                        size_info.get("size", 0),
                    )
        except Exception as exc:
            logger.debug(f"[MetricCollector] CacheManager error: {exc}")

    def _collect_llm_metrics(self) -> None:
        """Read FrameworkLLMAdapter call statistics."""
        if not self._llm_adapter:
            return
        if not hasattr(self._llm_adapter, "get_call_statistics"):
            return
        try:
            stats = self._llm_adapter.get_call_statistics()
            for provider_type, data in stats.items():
                if provider_type == "overall":
                    continue

                calls = data.get("total_calls", 0)
                prev_calls = self._prev_llm_calls.get(provider_type, 0)
                delta = max(0, calls - prev_calls)
                if delta > 0:
                    LLM_REQUESTS_TOTAL.labels(
                        provider_type=provider_type, status="total",
                    ).inc(delta)
                self._prev_llm_calls[provider_type] = calls

                errors = data.get("error_count", 0)
                prev_errors = self._prev_llm_errors.get(provider_type, 0)
                delta_errors = max(0, errors - prev_errors)
                if delta_errors > 0:
                    LLM_ERRORS_TOTAL.labels(
                        provider_type=provider_type, error_type="general",
                    ).inc(delta_errors)
                self._prev_llm_errors[provider_type] = errors

                avg_ms = data.get("avg_response_time_ms", 0)
                if avg_ms > 0:
                    LLM_REQUEST_DURATION.labels(
                        provider_type=provider_type, model="unknown",
                    ).observe(avg_ms / 1000.0)
        except Exception as exc:
            logger.debug(f"[MetricCollector] LLM adapter error: {exc}")

    def _collect_service_metrics(self) -> None:
        """Read ServiceRegistry service statuses."""
        if not self._service_registry:
            return
        try:
            statuses = self._service_registry.get_service_status()
            for name, status_str in statuses.items():
                value = _STATUS_MAP.get(status_str, 0.0)
                SERVICE_STATUS.labels(service_name=name).set(value)
        except Exception as exc:
            logger.debug(f"[MetricCollector] ServiceRegistry error: {exc}")

    def _collect_learning_sessions(self) -> None:
        """Count active learning sessions."""
        if not self._progressive_learning:
            return
        try:
            if hasattr(self._progressive_learning, "learning_active"):
                active = sum(
                    1 for v in self._progressive_learning.learning_active.values()
                    if v
                )
                ACTIVE_LEARNING_SESSIONS.set(active)
        except Exception as exc:
            logger.debug(f"[MetricCollector] Learning session error: {exc}")

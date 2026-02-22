"""Unified performance monitoring module.

Provides prometheus-based metric collection, async-aware instrumentation,
service health checking, and on-demand profiling via stdlib + optional
``yappi`` backend.

Quick start::

    from services.monitoring import timed, timer, count_errors
    from services.monitoring.metrics import LLM_REQUEST_DURATION

    @timed(LLM_REQUEST_DURATION, labels={"provider_type": "filter", "model": "gpt-4"})
    async def call_llm(...):
        ...
"""

from .metrics import (
    REGISTRY,
    get_registry,
    LLM_REQUEST_DURATION,
    LLM_REQUESTS_TOTAL,
    LLM_ERRORS_TOTAL,
    MESSAGES_PROCESSED_TOTAL,
    MESSAGE_PROCESSING_DURATION,
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    CACHE_SIZE,
    SERVICE_STATUS,
    ACTIVE_LEARNING_SESSIONS,
    SYSTEM_CPU_PERCENT,
    SYSTEM_MEMORY_PERCENT,
    SYSTEM_MEMORY_USED_BYTES,
    HOOK_DURATION,
)
from .instrumentation import timed, timer, count_errors, monitored, set_debug_mode, is_debug_mode
from .collector import MetricCollector
from .health_checker import HealthChecker, HealthStatus
from .profiler import ProfileSession

__all__ = [
    # Registry
    "REGISTRY",
    "get_registry",
    # Metric instances
    "LLM_REQUEST_DURATION",
    "LLM_REQUESTS_TOTAL",
    "LLM_ERRORS_TOTAL",
    "MESSAGES_PROCESSED_TOTAL",
    "MESSAGE_PROCESSING_DURATION",
    "CACHE_HITS_TOTAL",
    "CACHE_MISSES_TOTAL",
    "CACHE_SIZE",
    "SERVICE_STATUS",
    "ACTIVE_LEARNING_SESSIONS",
    "SYSTEM_CPU_PERCENT",
    "SYSTEM_MEMORY_PERCENT",
    "SYSTEM_MEMORY_USED_BYTES",
    "HOOK_DURATION",
    # Instrumentation
    "timed",
    "timer",
    "count_errors",
    "monitored",
    "set_debug_mode",
    "is_debug_mode",
    # Services
    "MetricCollector",
    "HealthChecker",
    "HealthStatus",
    "ProfileSession",
]

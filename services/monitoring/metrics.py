"""Prometheus metric definitions and dedicated registry.

All metric instances are registered on a plugin-scoped ``CollectorRegistry``
rather than the global default, preventing conflicts with other prometheus
instrumentation in the host process and simplifying test isolation.

Metric naming follows the Prometheus convention:
    <namespace>_<subsystem>_<unit>
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Dedicated registry (isolated from the global default registry).
REGISTRY = CollectorRegistry()

# -- LLM metrics ----------------------------------------------------------

LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM request latency in seconds",
    labelnames=["provider_type", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

LLM_REQUESTS_TOTAL = Counter(
    "llm_requests_total",
    "Total number of LLM requests",
    labelnames=["provider_type", "status"],
    registry=REGISTRY,
)

LLM_ERRORS_TOTAL = Counter(
    "llm_errors_total",
    "Total number of LLM errors",
    labelnames=["provider_type", "error_type"],
    registry=REGISTRY,
)

# -- Message pipeline metrics ----------------------------------------------

MESSAGES_PROCESSED_TOTAL = Counter(
    "messages_processed_total",
    "Total messages processed by the learning pipeline",
    labelnames=["group_id", "stage"],
    registry=REGISTRY,
)

MESSAGE_PROCESSING_DURATION = Histogram(
    "message_processing_duration_seconds",
    "Message processing latency in seconds",
    labelnames=["stage"],
    registry=REGISTRY,
)

# -- Cache metrics ---------------------------------------------------------

CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total cache hit count",
    labelnames=["cache_name"],
    registry=REGISTRY,
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total cache miss count",
    labelnames=["cache_name"],
    registry=REGISTRY,
)

CACHE_SIZE = Gauge(
    "cache_current_size",
    "Current number of entries in a cache",
    labelnames=["cache_name"],
    registry=REGISTRY,
)

# -- Service health metrics ------------------------------------------------

SERVICE_STATUS = Gauge(
    "service_status",
    "Service lifecycle status (1=running, 0=stopped, -1=error)",
    labelnames=["service_name"],
    registry=REGISTRY,
)

ACTIVE_LEARNING_SESSIONS = Gauge(
    "active_learning_sessions",
    "Number of currently active learning sessions",
    registry=REGISTRY,
)

# -- System metrics (populated by collector via psutil) --------------------

SYSTEM_CPU_PERCENT = Gauge(
    "system_cpu_percent",
    "System CPU usage percentage",
    registry=REGISTRY,
)

SYSTEM_MEMORY_PERCENT = Gauge(
    "system_memory_percent",
    "System memory usage percentage",
    registry=REGISTRY,
)

SYSTEM_MEMORY_USED_BYTES = Gauge(
    "system_memory_used_bytes",
    "System memory used in bytes",
    registry=REGISTRY,
)

# -- Hook performance metrics ---------------------------------------------

HOOK_DURATION = Histogram(
    "hook_duration_seconds",
    "Hook execution duration in seconds",
    labelnames=["hook_name", "step"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=REGISTRY,
)


def get_registry() -> CollectorRegistry:
    """Return the plugin's dedicated metric registry."""
    return REGISTRY
